import uuid
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db_session, AsyncSessionLocal
from app.core.auth import get_current_user
from app.models.user import User
from app.services.marketing_service import MarketingService
from app.core.security import verify_api_key
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/marketing", tags=["Marketing Engine"])

status_update_semaphore = asyncio.Semaphore(5)

def get_optional_db() -> Optional[AsyncSession]:
    return None

from datetime import datetime

# Pydantic Schemas
class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    campaign_type: str = "Promotion"
    audience_filters: Dict[str, Any] = Field(default_factory=dict)
    custom_prompt: Optional[str] = None
    scheduled_at: Optional[datetime] = None

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    campaign_type: Optional[str] = None
    audience_filters: Optional[Dict[str, Any]] = None
    custom_prompt: Optional[str] = None
    status: Optional[str] = None
    scheduled_at: Optional[datetime] = None

class AIConfigUpdate(BaseModel):
    system_prompt: str
    campaign_prompt: str
    model: str = "gemini-2.5-flash"
    temperature: float = 0.7
    prompt_version: str = "1.0"
    is_active: bool = True

class GenerateContentRequest(BaseModel):
    user_prompt: Optional[str] = None
    structured_parameters: Optional[Dict[str, Any]] = None
    force_regenerate: bool = False

class ApproveContentRequest(BaseModel):
    attachments: Optional[List[Dict[str, Any]]] = None

class ContentUpdate(BaseModel):
    subject: str
    html_body: str
    plain_text: Optional[str] = None

class PreviewRequest(BaseModel):
    filters: Dict[str, Any]


# Endpoints
@router.post("/campaigns", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Creates a new marketing campaign. Validates unique constraints scoped by tenant.
    """
    org_id = current_user.organization_id
    campaign_id = uuid.uuid4()

    # Check unique constraint manually to return clean 409 error
    exist_res = await db.execute(
        text("SELECT id FROM marketing_campaigns WHERE organization_id = :org_id AND name = :name"),
        {"org_id": org_id, "name": payload.name}
    )
    if exist_res.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A campaign with name '{payload.name}' already exists."
        )

    try:
        import json
        await db.execute(
            text("""
                INSERT INTO marketing_campaigns (
                    id, organization_id, name, description, audience_filters, 
                    campaign_type, custom_prompt, status, scheduled_at, created_at, updated_at
                ) VALUES (
                    :id, :org_id, :name, :description, CAST(:filters AS jsonb), 
                    :campaign_type, :custom_prompt, 'draft', :scheduled_at, NOW(), NOW()
                )
            """),
            {
                "id": campaign_id,
                "org_id": org_id,
                "name": payload.name,
                "description": payload.description,
                "filters": json.dumps(payload.audience_filters),
                "campaign_type": payload.campaign_type,
                "custom_prompt": payload.custom_prompt,
                "scheduled_at": payload.scheduled_at
            }
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create campaign: {str(e)}")

    return {"id": str(campaign_id), "status": "draft", "name": payload.name}


@router.get("/campaigns", response_model=List[Dict[str, Any]])
async def list_campaigns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Lists all campaigns for the organization.
    """
    org_id = current_user.organization_id
    res = await db.execute(
        text("""
            SELECT id, name, description, audience_filters, status, campaign_type, custom_prompt, 
                   scheduled_at, started_at, completed_at, created_at 
            FROM marketing_campaigns 
            WHERE organization_id = :org_id 
            ORDER BY created_at DESC
        """),
        {"org_id": org_id}
    )
    return [dict(row._mapping) for row in res.fetchall()]


@router.get("/campaigns/{campaign_id}", response_model=Dict[str, Any])
async def get_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Gets campaign details. Prevents cross-tenant access.
    """
    org_id = current_user.organization_id
    res = await db.execute(
        text("""
            SELECT id, name, description, audience_filters, status, campaign_type, custom_prompt, 
                   scheduled_at, started_at, completed_at, created_at 
            FROM marketing_campaigns 
            WHERE id = :id AND organization_id = :org_id
        """),
        {"id": campaign_id, "org_id": org_id}
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return dict(row._mapping)


@router.put("/campaigns/{campaign_id}", response_model=Dict[str, Any])
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Updates campaign settings. Prevents cross-tenant modifications.
    """
    org_id = current_user.organization_id

    # Verify exists
    verify = await db.execute(
        text("SELECT status FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
        {"id": campaign_id, "org_id": org_id}
    )
    row = verify.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    
    current_status = row[0]
    
    # We only allow filter modifications if the status is completed.
    # Otherwise, modifying filters for draft, audience_locked, approved, running is rejected.
    if payload.audience_filters is not None:
        if current_status != "completed":
            raise HTTPException(status_code=400, detail="Campaign filters can only be modified for completed campaigns.")

    # Construct dynamic updates
    update_parts = []
    params = {"id": campaign_id, "org_id": org_id}
    
    import json
    update_data = payload.dict(exclude_unset=True)
    
    # If the campaign is completed and we are editing filters, we return the status to 'draft' and invalidate recipients
    should_reset_to_draft = False
    if current_status == "completed" and "audience_filters" in update_data and update_data["audience_filters"] is not None:
        should_reset_to_draft = True
        update_data["status"] = "draft"

    for field in ("name", "description", "campaign_type", "custom_prompt", "status", "scheduled_at"):
        if field in update_data:
            update_parts.append(f"{field} = :{field}")
            params[field] = update_data[field]

    if "audience_filters" in update_data and update_data["audience_filters"] is not None:
        update_parts.append("audience_filters = :filters")
        params["filters"] = json.dumps(update_data["audience_filters"])

    if not update_parts:
        return {"id": str(campaign_id), "status": current_status}

    try:
        if should_reset_to_draft:
            await db.execute(
                text("DELETE FROM marketing_campaign_recipients WHERE campaign_id = :id"),
                {"id": campaign_id}
            )
        update_query = f"UPDATE marketing_campaigns SET {', '.join(update_parts)}, updated_at = NOW() WHERE id = :id AND organization_id = :org_id"
        await db.execute(text(update_query), params)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update campaign: {str(e)}")

    return {"id": str(campaign_id), "success": True, "status": "draft" if should_reset_to_draft else current_status}


@router.post("/preview", response_model=Dict[str, Any])
async def preview_audience(
    payload: PreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Calculates dynamic matching customer counts and returns a sample preview. Read-only.
    """
    org_id = current_user.organization_id
    service = MarketingService(db)

    count = await service.get_audience_count(org_id, payload.filters)
    preview = await service.get_audience_preview(org_id, payload.filters, limit=20)
    
    return {
        "count": count,
        "sample": preview,
        "filters_applied": payload.filters
    }


@router.post("/campaigns/{campaign_id}/lock", response_model=Dict[str, Any])
async def lock_campaign_audience(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Freezes campaign recipients lists as a snapshot.
    """
    org_id = current_user.organization_id
    service = MarketingService(db)

    try:
        inserted = await service.lock_audience(org_id, campaign_id)
        return {"success": True, "recipients_locked": inserted}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audience lock error: {str(e)}")


@router.get("/campaigns/{campaign_id}/recipients", response_model=List[Dict[str, Any]])
async def get_campaign_recipients(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Returns frozen recipient list snapshots with their customer master properties and statuses.
    """
    org_id = current_user.organization_id
    try:
        res = await db.execute(
            text("""
                SELECT r.id, r.status, r.created_at, r.sent_at,
                       c.company_name, c.contact_name, c.contact_email, c.country,
                       c.shipment_mode, c.trade_direction, c.industry,
                       es.id AS suppression_id, es.bounce_reason AS bounce_reason, es.suppressed_at AS suppressed_at
                FROM marketing_campaign_recipients r
                JOIN customers c ON r.customer_id = c.id
                LEFT JOIN email_suppressions es ON es.organization_id = :org_id AND lower(es.email_address) = lower(c.contact_email)
                WHERE r.campaign_id = :campaign_id AND r.organization_id = :org_id
                ORDER BY c.company_name ASC
            """),
            {"campaign_id": campaign_id, "org_id": org_id}
        )
        rows = res.fetchall()
        recipients = []
        for r in rows:
            is_supp = r.suppression_id is not None or r.status in ("skipped", "hard_bounce_suppressed")
            rec_status = "skipped" if is_supp else r.status
            recipients.append({
                "id": str(r.id),
                "status": rec_status,
                "is_suppressed": is_supp,
                "skip_reason": "hard_bounce_suppressed" if is_supp else None,
                "bounce_reason": r.bounce_reason if is_supp else None,
                "suppressed_at": r.suppressed_at.isoformat() if is_supp and r.suppressed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "company_name": r.company_name,
                "contact_name": r.contact_name,
                "contact_email": r.contact_email,
                "country": r.country,
                "shipment_mode": r.shipment_mode,
                "trade_direction": r.trade_direction,
                "industry": r.industry
            })
        return recipients
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch recipients: {str(e)}")


@router.get("/ai-config", response_model=Dict[str, Any])
async def get_ai_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves Marketing AI configuration for the authenticated tenant.
    """
    org_id = current_user.organization_id
    res = await db.execute(
        text("SELECT system_prompt, campaign_prompt, model, temperature, prompt_version, is_active FROM marketing_ai_configs WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    row = res.fetchone()
    if not row:
        return {
            "system_prompt": "You are a professional B2B logistics cargo marketing assistant.",
            "campaign_prompt": "Write professional B2B email campaigns focused on freight solutions.",
            "model": "gemini-2.5-flash",
            "temperature": 0.7,
            "prompt_version": "1.0",
            "is_active": True
        }
    return dict(row._mapping)


@router.put("/ai-config", response_model=Dict[str, Any])
async def update_ai_config(
    payload: AIConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Upserts the tenant's AI configuration.
    """
    org_id = current_user.organization_id
    try:
        await db.execute(
            text("""
                INSERT INTO marketing_ai_configs (
                    organization_id, system_prompt, campaign_prompt, model, 
                    temperature, prompt_version, is_active, updated_at
                ) VALUES (
                    :org_id, :system, :campaign, :model, :temp, :version, :active, NOW()
                ) ON CONFLICT (organization_id) DO UPDATE SET
                    system_prompt = EXCLUDED.system_prompt,
                    campaign_prompt = EXCLUDED.campaign_prompt,
                    model = EXCLUDED.model,
                    temperature = EXCLUDED.temperature,
                    prompt_version = EXCLUDED.prompt_version,
                    is_active = EXCLUDED.is_active,
                    updated_at = NOW()
            """),
            {
                "org_id": org_id,
                "system": payload.system_prompt,
                "campaign": payload.campaign_prompt,
                "model": payload.model,
                "temp": payload.temperature,
                "version": payload.prompt_version,
                "active": payload.is_active
            }
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save AI configuration: {str(e)}")

    return {"success": True}


@router.post("/campaigns/{campaign_id}/generate-content", response_model=Dict[str, Any])
async def generate_campaign_content(
    campaign_id: uuid.UUID,
    payload: GenerateContentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Triggers AI generation and returns content version. Respects prompt caching rules.
    """
    org_id = current_user.organization_id
    service = MarketingService(db)

    try:
        content = await service.get_or_generate_content(
            org_id, 
            campaign_id, 
            payload.user_prompt, 
            force_regenerate=payload.force_regenerate,
            structured_parameters=payload.structured_parameters
        )
        return content
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content generation error: {str(e)}")


@router.get("/campaigns/{campaign_id}/contents", response_model=List[Dict[str, Any]])
async def get_campaign_content_versions(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Fetches all content versions generated for a specific campaign.
    """
    org_id = current_user.organization_id
    
    # Verify campaign ownership
    verify = await db.execute(
        text("SELECT id FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
        {"id": campaign_id, "org_id": org_id}
    )
    if not verify.fetchone():
        raise HTTPException(status_code=404, detail="Campaign not found.")

    res = await db.execute(
        text("""
            SELECT id, version, subject, preview_text, html_body, plain_text, 
                   prompt_version, status, created_at 
            FROM marketing_campaign_contents 
            WHERE campaign_id = :campaign_id 
            ORDER BY version DESC
        """),
        {"campaign_id": campaign_id}
    )
    return [dict(row._mapping) for row in res.fetchall()]


@router.put("/campaigns/{campaign_id}/contents/{content_id}", response_model=Dict[str, Any])
async def update_campaign_content(
    campaign_id: uuid.UUID,
    content_id: uuid.UUID,
    payload: ContentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Updates the subject, html_body, and plain_text of a generated campaign content version.
    """
    org_id = current_user.organization_id
    verify = await db.execute(
        text("SELECT id FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
        {"id": campaign_id, "org_id": org_id}
    )
    if not verify.fetchone():
        raise HTTPException(status_code=404, detail="Campaign not found.")

    try:
        plain_text = payload.plain_text or payload.html_body
        await db.execute(
            text("""
                UPDATE marketing_campaign_contents 
                SET subject = :subject, html_body = :html_body, plain_text = :plain_text, updated_at = NOW()
                WHERE id = :content_id AND campaign_id = :campaign_id
            """),
            {
                "subject": payload.subject,
                "html_body": payload.html_body,
                "plain_text": plain_text,
                "content_id": content_id,
                "campaign_id": campaign_id
            }
        )
        await db.commit()
        return {"success": True}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update campaign content: {str(e)}")


@router.post("/campaigns/{campaign_id}/contents/{content_id}/approve", response_model=Dict[str, Any])
async def approve_campaign_content_version(
    campaign_id: uuid.UUID,
    content_id: uuid.UUID,
    payload: Optional[ApproveContentRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Approves the chosen content version for campaign launch.
    """
    org_id = current_user.organization_id
    service = MarketingService(db)

    attachments = payload.attachments if payload else None

    try:
        await service.approve_content(org_id, campaign_id, content_id, attachments)
        return {"success": True}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content approval error: {str(e)}")


@router.post("/campaigns/{campaign_id}/activate", response_model=Dict[str, Any])
async def activate_marketing_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Activates the campaign, making it running/active. Enforces only one active campaign.
    """
    org_id = current_user.organization_id
    service = MarketingService(db)

    try:
        await service.activate_campaign(org_id, campaign_id)
        return {"success": True}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Campaign activation error: {str(e)}")


@router.delete("/campaigns/{campaign_id}", response_model=Dict[str, Any])
async def delete_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Deletes a campaign if it is in draft or approved/completed state.
    Active/running campaigns cannot be deleted to prevent execution corruption.
    """
    org_id = current_user.organization_id
    verify = await db.execute(
        text("SELECT status FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
        {"id": campaign_id, "org_id": org_id}
    )
    row = verify.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    
    current_status = row[0]
    if current_status == "active":
        raise HTTPException(status_code=400, detail="Cannot delete an active running campaign. Pause or complete it first.")

    try:
        await db.execute(
            text("DELETE FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
            {"id": campaign_id, "org_id": org_id}
        )
        await db.commit()
        return {"success": True}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete campaign: {str(e)}")


@router.post("/campaigns/{campaign_id}/duplicate", response_model=Dict[str, Any])
async def duplicate_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Duplicates an existing campaign structure as a new draft.
    """
    org_id = current_user.organization_id
    verify = await db.execute(
        text("SELECT name, description, audience_filters, campaign_type, custom_prompt FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
        {"id": campaign_id, "org_id": org_id}
    )
    row = verify.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    
    name, description, audience_filters, campaign_type, custom_prompt = row
    
    # Generate unique name
    new_name = f"Copy of {name}"
    idx = 1
    while True:
        exist_res = await db.execute(
            text("SELECT id FROM marketing_campaigns WHERE organization_id = :org_id AND name = :name"),
            {"org_id": org_id, "name": new_name}
        )
        if not exist_res.fetchone():
            break
        new_name = f"Copy of {name} ({idx})"
        idx += 1

    new_id = uuid.uuid4()
    try:
        import json
        await db.execute(
            text("""
                INSERT INTO marketing_campaigns (
                    id, organization_id, name, description, audience_filters, 
                    campaign_type, custom_prompt, status, created_at, updated_at
                ) VALUES (
                    :id, :org_id, :name, :description, :filters, 
                    :campaign_type, :custom_prompt, 'draft', NOW(), NOW()
                )
            """),
            {
                "id": new_id,
                "org_id": org_id,
                "name": new_name,
                "description": description,
                "filters": json.dumps(audience_filters) if audience_filters else None,
                "campaign_type": campaign_type,
                "custom_prompt": custom_prompt
            }
        )
        await db.commit()
        return {"id": str(new_id), "status": "draft", "name": new_name}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to duplicate campaign: {str(e)}")


@router.get("/campaigns/{campaign_id}/execution-progress", response_model=Dict[str, Any])
async def get_campaign_execution_progress(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves lightweight real-time progress details of a campaign execution.
    Isolates by tenant organization_id.
    """
    org_id = current_user.organization_id
    try:
        # Verify campaign ownership and fetch status
        verify = await db.execute(
            text("SELECT status FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
            {"id": campaign_id, "org_id": org_id}
        )
        row = verify.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Campaign not found.")
        status = row[0]

        # Calculate counts directly from marketing_campaign_recipients table
        res_counts = await db.execute(
            text("""
                SELECT 
                    COUNT(id) as total,
                    COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                    COUNT(CASE WHEN status = 'sending' THEN 1 END) as sending,
                    COUNT(CASE WHEN status = 'skipped' THEN 1 END) as skipped
                FROM marketing_campaign_recipients
                WHERE campaign_id = :campaign_id AND organization_id = :org_id
            """),
            {"campaign_id": campaign_id, "org_id": org_id}
        )
        counts = res_counts.fetchone()
        
        total = counts.total if counts else 0
        sent = counts.sent if counts else 0
        failed = counts.failed if counts else 0
        pending = counts.pending if counts else 0
        sending = counts.sending if counts else 0
        skipped = counts.skipped if counts else 0
        
        completed = sent + failed + skipped
        progress_percent = round((completed / total * 100), 1) if total > 0 else 0.0

        return {
            "campaign_id": str(campaign_id),
            "status": status,
            "total": total,
            "sent": sent,
            "failed": failed,
            "pending": pending,
            "sending": sending,
            "skipped": skipped,
            "completed": completed,
            "progress_percent": progress_percent
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load execution progress: {str(e)}")


@router.get("/campaigns/{campaign_id}/analytics", response_model=Dict[str, Any])
async def get_campaign_analytics(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves campaign-level metrics and recipient-level engagement logs.
    """
    org_id = current_user.organization_id
    try:
        verify = await db.execute(
            text("SELECT name FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
            {"id": campaign_id, "org_id": org_id}
        )
        row = verify.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Campaign not found.")
        campaign_name = row[0]

        res_counts = await db.execute(
            text("""
                SELECT 
                    COUNT(r.id) as total_targeted,
                    COUNT(CASE WHEN r.status = 'sent' THEN 1 END) as sent_count,
                    COUNT(CASE WHEN r.status = 'failed' THEN 1 END) as failed_count
                FROM marketing_campaign_recipients r
                WHERE r.campaign_id = :campaign_id AND r.organization_id = :org_id
            """),
            {"campaign_id": campaign_id, "org_id": org_id}
        )
        counts = res_counts.fetchone()
        total_targeted = counts.total_targeted if counts else 0
        sent_count = counts.sent_count if counts else 0
        failed_count = counts.failed_count if counts else 0

        res_email_counts = await db.execute(
            text("""
                SELECT 
                    COUNT(id) as email_sent,
                    COUNT(CASE WHEN delivery_status = 'failed' THEN 1 END) as email_failed,
                    COUNT(CASE WHEN replied_at IS NOT NULL THEN 1 END) as email_replied
                FROM email_log
                WHERE marketing_campaign_id = :campaign_id AND organization_id = :org_id
            """),
            {"campaign_id": campaign_id, "org_id": org_id}
        )
        email_counts = res_email_counts.fetchone()
        
        email_sent = email_counts.email_sent if email_counts else 0
        email_failed = email_counts.email_failed if email_counts else 0
        email_replied = email_counts.email_replied if email_counts else 0

        final_sent = max(sent_count, email_sent)
        final_failed = max(failed_count, email_failed)
        final_replied = email_replied
        
        reply_rate = round((final_replied / final_sent * 100), 2) if final_sent > 0 else 0.0

        res_recipients = await db.execute(
            text("""
                SELECT r.id, r.status, r.created_at,
                       c.company_name, c.contact_name, c.contact_email, c.country,
                       c.shipment_mode, c.trade_direction, c.industry,
                       el.id as email_log_id, el.sent_at, el.delivery_status, el.replied_at, el.created_at as last_activity
                FROM marketing_campaign_recipients r
                JOIN customers c ON r.customer_id = c.id
                LEFT JOIN email_log el ON el.marketing_campaign_id = r.campaign_id AND el.customer_id = r.customer_id AND el.organization_id = :org_id
                WHERE r.campaign_id = :campaign_id AND r.organization_id = :org_id
                ORDER BY c.company_name ASC
            """),
            {"campaign_id": campaign_id, "org_id": org_id}
        )
        recipient_rows = res_recipients.fetchall()
        recipient_details = []
        for r in recipient_rows:
            recipient_details.append({
                "id": str(r.id),
                "company_name": r.company_name,
                "contact_name": r.contact_name,
                "contact_email": r.contact_email,
                "country": r.country,
                "shipment_mode": r.shipment_mode,
                "trade_direction": r.trade_direction,
                "industry": r.industry,
                "status": r.status,
                "email_log_id": str(r.email_log_id) if r.email_log_id else None,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "delivery_status": r.delivery_status or r.status,
                "replied_at": r.replied_at.isoformat() if r.replied_at else None,
                "last_activity": r.last_activity.isoformat() if r.last_activity else None,
                "failure_reason": "Outbound execution error" if r.status == 'failed' else None
            })

        return {
            "campaign_id": str(campaign_id),
            "campaign_name": campaign_name,
            "metrics": {
                "total_targeted": total_targeted,
                "sent": final_sent,
                "delivered": final_sent - final_failed,
                "opened": 0,
                "replied": final_replied,
                "failed": final_failed,
                "open_rate": 0.0,
                "reply_rate": reply_rate
            },
            "recipients": recipient_details
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load analytics: {str(e)}")


# --- n8n Orchestrated Execution Endpoints (Secured by API Key) ---

class ClaimResponse(BaseModel):
    claimed: bool
    campaign_id: Optional[uuid.UUID] = None
    organization_id: Optional[uuid.UUID] = None
    subject: Optional[str] = None
    html_body: Optional[str] = None
    plain_text: Optional[str] = None
    attachments: List[Dict[str, Any]] = []


class RecipientUpdate(BaseModel):
    status: str  # 'sent' or 'failed'


@router.post("/executions/claim", response_model=ClaimResponse, dependencies=[Depends(verify_api_key)])
async def claim_campaign_for_execution(db: AsyncSession = Depends(get_db_session)):
    """
    Scans for eligible campaigns (active or approved + scheduled time reached, or stale running campaigns),
    atomically claims one, marks its status as 'running', and returns campaign details and approved content.
    """
    try:
        # 1. Atomic query to find and claim next campaign
        res = await db.execute(
            text("""
                UPDATE marketing_campaigns
                SET status = 'running', started_at = NOW(), updated_at = NOW()
                WHERE id = (
                    SELECT id 
                    FROM marketing_campaigns
                    WHERE (status = 'active') 
                       OR (status = 'approved' AND scheduled_at <= NOW())
                       OR (status = 'running' AND (
                           updated_at <= NOW() - INTERVAL '15 minutes'
                           OR EXISTS (
                               SELECT 1 FROM marketing_campaign_recipients r 
                               WHERE r.campaign_id = marketing_campaigns.id 
                                 AND r.status = 'sending' 
                                 AND r.claimed_at <= NOW() - INTERVAL '15 minutes'
                           )
                       ))
                    ORDER BY COALESCE(scheduled_at, created_at) ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, organization_id
            """)
        )
        row = res.fetchone()
        if not row:
            return ClaimResponse(claimed=False)

        campaign_id, org_id = row

        # Stale recovery: Find all recipients that have been in 'sending' state for > 15 minutes.
        # Check recipient claimed_at lease state.
        stale_res = await db.execute(
            text("""
                SELECT r.id, r.customer_id, c.contact_email, cont.subject
                FROM marketing_campaign_recipients r
                JOIN customers c ON r.customer_id = c.id
                JOIN marketing_campaigns camp ON r.campaign_id = camp.id
                LEFT JOIN marketing_campaign_contents cont ON cont.campaign_id = camp.id AND cont.status = 'approved'
                WHERE r.campaign_id = :campaign_id 
                  AND r.status = 'sending' 
                  AND r.claimed_at <= NOW() - INTERVAL '15 minutes'
            """),
            {"campaign_id": campaign_id}
        )
        stale_rows = stale_res.fetchall()

        # Resolve email provider dynamically via factory
        from app.providers import EmailProviderFactory
        provider = None
        try:
            factory = EmailProviderFactory(db)
            provider = await factory.get_provider_for_tenant(org_id)
            
            # Resolve and attach pre-resolved credentials to prevent loop database queries during sentitems check
            prov_type_res = await db.execute(
                text("SELECT provider FROM tenant_integrations WHERE organization_id = :org_id"),
                {"org_id": org_id}
            )
            prov_type_row = prov_type_res.fetchone()
            provider_type = prov_type_row[0] if prov_type_row else "microsoft"
            
            if provider_type == "microsoft":
                from app.services.token_service import TokenService
                token_service = TokenService(db)
                access_token = await token_service.get_valid_access_token(org_id)
                provider.pre_resolved_token = access_token
            elif provider_type == "smtp":
                from app.core.encryption import decrypt_token
                smtp_res = await db.execute(
                    text("""
                        SELECT mailbox_email, auth_username, encrypted_password, 
                               smtp_host, smtp_port, smtp_security 
                        FROM tenant_integrations 
                        WHERE organization_id = :org_id
                    """),
                    {"org_id": org_id}
                )
                smtp_row = smtp_res.fetchone()
                if smtp_row:
                    mailbox_email_smtp, auth_username, encrypted_password, smtp_host, smtp_port, smtp_security = smtp_row
                    password = decrypt_token(encrypted_password)
                    username = auth_username if auth_username else mailbox_email_smtp
                    provider.pre_resolved_settings = {
                        "mailbox_email": mailbox_email_smtp,
                        "username": username,
                        "password": password,
                        "host": smtp_host,
                        "port": smtp_port,
                        "security": smtp_security
                    }
        except Exception as e:
            logger.warning(f"Could not resolve provider or credentials for recovery on campaign {campaign_id}: {str(e)}")

        for stale in stale_rows:
            rec_id, cust_id, email, subject = stale
            subject = subject or "Marketing Campaign Outreach"
            
            # Check local email_log
            log_res = await db.execute(
                text("SELECT id FROM email_log WHERE marketing_campaign_id = :camp_id AND customer_id = :cust_id LIMIT 1"),
                {"camp_id": campaign_id, "cust_id": cust_id}
            )
            if log_res.fetchone():
                await db.execute(
                    text("UPDATE marketing_campaign_recipients SET status = 'sent', sent_at = NOW() WHERE id = :id"),
                    {"id": rec_id}
                )
                continue

            # Verify on provider sentitems
            sent_meta = {"retrieval_success": False}
            if provider:
                try:
                    sent_meta = await provider.get_sent_metadata(
                        org_id=org_id,
                        subject=subject,
                        to_email=email,
                        db_session=None
                    )
                except Exception as ex:
                    logger.warning(f"SentItems recovery query failed for recipient {rec_id}: {str(ex)}")

            if sent_meta.get("retrieval_success"):
                # Retroactive log insert
                email_log_id = uuid.uuid4()
                await db.execute(
                    text("""
                        INSERT INTO email_log (
                            id, organization_id, customer_id, marketing_campaign_id, direction, 
                            email_type, subject, body, has_attachment, sent_at, delivery_status, graph_message_id,
                            conversation_id, thread_id, internet_message_id, created_at
                        ) VALUES (
                            :id, :org_id, :customer_id, :mkt_campaign_id, 'outbound', 
                            'campaign', :subject, '<p>Recovered Sent Email</p>', false, NOW(), 'sent', :graph_message_id,
                            :conversation_id, :thread_id, :internet_message_id, NOW()
                        ) ON CONFLICT (marketing_campaign_id, customer_id) WHERE marketing_campaign_id IS NOT NULL DO NOTHING
                    """),
                    {
                        "id": email_log_id,
                        "org_id": org_id,
                        "customer_id": cust_id,
                        "mkt_campaign_id": campaign_id,
                        "subject": subject,
                        "graph_message_id": sent_meta.get("id"),
                        "conversation_id": sent_meta.get("conversation_id"),
                        "thread_id": sent_meta.get("conversation_id"),
                        "internet_message_id": sent_meta.get("internet_message_id")
                    }
                )
                await db.execute(
                    text("UPDATE marketing_campaign_recipients SET status = 'sent', sent_at = NOW() WHERE id = :id"),
                    {"id": rec_id}
                )
            else:
                # Reset to pending for clean retry
                await db.execute(
                    text("UPDATE marketing_campaign_recipients SET status = 'pending', claimed_at = NULL WHERE id = :id"),
                    {"id": rec_id}
                )

        await db.commit()

        # Check if campaign has zero recipients and autocomplete if necessary
        count_res = await db.execute(
            text("SELECT COUNT(*) FROM marketing_campaign_recipients WHERE campaign_id = :campaign_id"),
            {"campaign_id": campaign_id}
        )
        recip_count = count_res.scalar() or 0
        if recip_count == 0:
            await db.execute(
                text("""
                    UPDATE marketing_campaigns
                    SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                    WHERE id = :campaign_id
                """),
                {"campaign_id": campaign_id}
            )
            await db.commit()

        # 2. Get approved content and attachments
        content_res = await db.execute(
            text("""
                SELECT subject, html_body, plain_text, attachments
                FROM marketing_campaign_contents
                WHERE campaign_id = :campaign_id AND status = 'approved'
                LIMIT 1
            """),
            {"campaign_id": campaign_id}
        )
        content_row = content_res.fetchone()
        if not content_row:
            # Fallback to general draft content if no content is marked approved
            content_res = await db.execute(
                text("""
                    SELECT subject, html_body, plain_text, attachments
                    FROM marketing_campaign_contents
                    WHERE campaign_id = :campaign_id
                    ORDER BY version DESC
                    LIMIT 1
                """),
                {"campaign_id": campaign_id}
            )
            content_row = content_res.fetchone()

        subject = "Marketing Campaign Outreach"
        html_body = "<p>Hello</p>"
        plain_text = "Hello"
        attachments = []

        if content_row:
            subject = content_row[0] or subject
            html_body = content_row[1] or html_body
            plain_text = content_row[2] or plain_text
            attachments = content_row[3] or []

        return ClaimResponse(
            claimed=True,
            campaign_id=campaign_id,
            organization_id=org_id,
            subject=subject,
            html_body=html_body,
            plain_text=plain_text,
            attachments=attachments
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed claiming campaign: {str(e)}")


@router.get("/executions/{campaign_id}/recipients", response_model=List[Dict[str, Any]], dependencies=[Depends(verify_api_key)])
async def get_execution_recipients(
    campaign_id: uuid.UUID,
    request: Request = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Returns paginated pending campaign recipients with customer names and emails for rendering personalization.
    Atomically transitions status to 'sending' and records claimed_at using row locking.
    """
    import time
    start_time = time.perf_counter()
    try:
        # Diagnostic headers parsing
        client_ip = "unknown"
        user_agent = "unknown"
        referer = "unknown"
        request_id = str(uuid.uuid4())
        
        if request is not None:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            referer = request.headers.get("referer", "unknown")
            request_id = request.headers.get("x-request-id", request_id)
        
        # Resolve caller type
        caller = "unknown"
        if "n8n" in user_agent.lower() or "axios" in user_agent.lower():
            caller = "n8n/http-client"
        elif "mozilla" in user_agent.lower() or "chrome" in user_agent.lower() or "safari" in user_agent.lower():
            caller = "browser/frontend"

        # Enforce backend safety cap: max 50 items per batch
        effective_limit = min(limit, 50)

        # Count pending BEFORE update
        pending_before_res = await db.execute(
            text("SELECT COUNT(*) FROM marketing_campaign_recipients WHERE campaign_id = :campaign_id AND status = 'pending'"),
            {"campaign_id": campaign_id}
        )
        pending_before = pending_before_res.scalar()

        # Atomic lock and update
        claim_res = await db.execute(
            text("""
                UPDATE marketing_campaign_recipients
                SET status = 'sending', claimed_at = NOW()
                WHERE id IN (
                    SELECT id
                    FROM marketing_campaign_recipients
                    WHERE campaign_id = :campaign_id AND status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id
            """),
            {"campaign_id": campaign_id, "limit": effective_limit}
        )
        rows = claim_res.fetchall()
        selected_ids_count = len(rows)
        
        if not rows:
            await db.commit()
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            print(
                f"[RECIPIENT_DIAGNOSTIC] "
                f"timestamp={time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}.{int((time.time() % 1) * 1000):03d} | "
                f"request_id={request_id} | "
                f"campaign_id={campaign_id} | "
                f"client_ip={client_ip} | "
                f"user_agent={user_agent} | "
                f"referer={referer} | "
                f"limit={limit} | "
                f"effective_limit={effective_limit} | "
                f"pending_before={pending_before} | "
                f"selected=0 | "
                f"response=0 | "
                f"duration_ms={duration_ms:.2f} | "
                f"caller={caller}"
            )
            return []

        recipient_ids = [r[0] for r in rows]
        
        # Query details for the claimed recipients
        res = await db.execute(
            text("""
                SELECT r.id, r.customer_id, c.contact_name, c.contact_email
                FROM marketing_campaign_recipients r
                JOIN customers c ON r.customer_id = c.id
                WHERE r.id = ANY(:ids)
                ORDER BY r.created_at ASC
            """),
            {"ids": list(recipient_ids)}
        )
        detail_rows = res.fetchall()
        await db.commit()
        
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        response_items_count = len(detail_rows)
        print(
            f"[RECIPIENT_DIAGNOSTIC] "
            f"timestamp={time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}.{int((time.time() % 1) * 1000):03d} | "
            f"request_id={request_id} | "
            f"campaign_id={campaign_id} | "
            f"client_ip={client_ip} | "
            f"user_agent={user_agent} | "
            f"referer={referer} | "
            f"limit={limit} | "
            f"effective_limit={effective_limit} | "
            f"pending_before={pending_before} | "
            f"selected={selected_ids_count} | "
            f"response={response_items_count} | "
            f"duration_ms={duration_ms:.2f} | "
            f"caller={caller} | "
            f"first_3={[str(rid)[:8] for rid in recipient_ids[:3]]} | "
            f"last_3={[str(rid)[:8] for rid in recipient_ids[-3:]]}"
        )
        
        return [
            {
                "recipient_id": str(r.id),
                "customer_id": str(r.customer_id),
                "contact_name": r.contact_name or "Valued Customer",
                "contact_email": r.contact_email
            }
            for r in detail_rows
        ]
    except Exception as e:
        await db.rollback()
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        print(f"[RECIPIENT_DIAGNOSTIC] ERROR: campaign_id={campaign_id} | limit={limit} | error={str(e)} | duration_ms={duration_ms:.2f}")
        raise HTTPException(status_code=500, detail=f"Failed getting recipients: {str(e)}")


@router.post("/executions/recipients/{recipient_id}/status", response_model=Dict[str, Any], dependencies=[Depends(verify_api_key)])
async def update_execution_recipient_status(
    recipient_id: uuid.UUID,
    payload: RecipientUpdate,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Updates the snapshot recipient outcome status to 'sent' or 'failed'.
    Automatically triggers campaign completion when no pending recipients remain.
    """
    if payload.status not in ["sent", "failed"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'sent' or 'failed'")

    try:
        ts_col = "sent_at" if payload.status == "sent" else "failed_at"
        
        # 1. Update recipient status and timestamp
        await db.execute(
            text(f"""
                UPDATE marketing_campaign_recipients
                SET status = :status, {ts_col} = NOW()
                WHERE id = :recipient_id
            """),
            {"status": payload.status, "recipient_id": recipient_id}
        )

        # 2. Retrieve campaign ID associated with this recipient
        camp_id_res = await db.execute(
            text("SELECT campaign_id FROM marketing_campaign_recipients WHERE id = :id"),
            {"id": recipient_id}
        )
        camp_id_row = camp_id_res.fetchone()
        if camp_id_row:
            campaign_uuid = camp_id_row[0]
            
            # Atomic conditional completion check query.
            # Only marks campaign completed if there are no pending or sending recipients left
            # for this campaign.
            # Terminally checks status is in ('active', 'running') to prevent moving backward.
            await db.execute(
                text("""
                    UPDATE marketing_campaigns
                    SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                    WHERE id = :campaign_id
                      AND status IN ('active', 'running')
                      AND NOT EXISTS (
                          SELECT 1
                          FROM marketing_campaign_recipients
                          WHERE campaign_id = :campaign_id
                            AND status IN ('pending', 'sending')
                      )
                """),
                {"campaign_id": campaign_uuid}
            )

        await db.commit()
        return {"success": True}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed updating recipient status: {str(e)}")


@router.get("/email-logs/{email_log_id}", response_model=Dict[str, Any])
async def get_email_log_detail(
    email_log_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves the subject, html_body (mapped from body), plain_text_body, and recipients for a sent email.
    """
    try:
        res = await db.execute(
            text("""
                SELECT subject, body, sent_at, customer_id
                FROM email_log
                WHERE id = :id AND organization_id = :org_id
            """),
            {"id": email_log_id, "org_id": current_user.organization_id}
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email log entry not found.")
            
        subject, body, sent_at, customer_id = row
        
        # Get customer email/name
        cust_res = await db.execute(
            text("SELECT contact_email, contact_name FROM customers WHERE id = :id"),
            {"id": customer_id}
        )
        cust_row = cust_res.fetchone()
        to_email = cust_row[0] if cust_row else ""
        to_name = cust_row[1] if cust_row else ""
        
        return {
            "id": str(email_log_id),
            "subject": subject,
            "body": body,  # HTML representation
            "sent_at": sent_at.isoformat() if sent_at else None,
            "to_email": to_email,
            "to_name": to_name
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{campaign_id}/complete", response_model=Dict[str, Any], dependencies=[Depends(verify_api_key)])
async def complete_campaign_execution(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Transition campaign status to 'completed' and record completion timestamp.
    """
    try:
        await db.execute(
            text("""
                UPDATE marketing_campaigns
                SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                WHERE id = :campaign_id
            """),
            {"campaign_id": campaign_id}
        )
        await db.commit()
        return {"success": True}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed completing campaign: {str(e)}")

