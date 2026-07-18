from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel, UUID4

from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import verify_api_key

router = APIRouter(tags=["Follow-ups Manager"])
settings = get_settings()
logger = get_logger(__name__)


# Schemas
class AttachmentProfileCreate(BaseModel):
    name: str

class AttachmentProfileFileResponse(BaseModel):
    id: UUID4
    profile_id: UUID4
    file_name: str
    file_path: str
    file_size: int
    content_type: str
    created_at: str

class AttachmentProfileResponse(BaseModel):
    id: UUID4
    name: str
    created_at: str
    files: List[AttachmentProfileFileResponse] = []

class FollowUpStepConfig(BaseModel):
    step_number: int
    delay_days: int
    ai_rewrite_enabled: bool
    attachment_profile_id: Optional[UUID4] = None

class FollowUpSettingsResponse(BaseModel):
    max_follow_ups: int
    stop_on_reply: bool
    follow_up_sequence_config: List[FollowUpStepConfig]

class FollowUpSettingsUpdate(BaseModel):
    max_follow_ups: int
    stop_on_reply: bool
    follow_up_sequence_config: List[FollowUpStepConfig]

class FollowUpQueueItemResponse(BaseModel):
    id: UUID4
    customer_id: UUID4
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    step_number: int
    attachment_profile_name: Optional[str] = None
    scheduled_datetime: Optional[str] = None
    draft_status: str
    ai_rewrite_enabled: bool
    ai_draft_body: Optional[str] = None
    current_schedule: bool = False

class RescheduleRequest(BaseModel):
    smart_instruction: str

class QueueActionRequest(BaseModel):
    action: str # send_now | skip | pause | resume


# Endpoints

@router.get("/attachment-profiles", response_model=List[AttachmentProfileResponse])
async def get_attachment_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    profiles_res = await db.execute(
        text("SELECT id, name, created_at FROM follow_up_attachment_profiles WHERE organization_id = :org_id ORDER BY created_at DESC"),
        {"org_id": org_id}
    )
    profiles = []
    for row in profiles_res.fetchall():
        p_id, p_name, p_created = row
        files_res = await db.execute(
            text("SELECT id, profile_id, file_name, file_path, file_size, content_type, created_at FROM follow_up_attachment_files WHERE profile_id = :p_id"),
            {"p_id": p_id}
        )
        files = []
        for f_row in files_res.fetchall():
            files.append(AttachmentProfileFileResponse(
                id=f_row[0],
                profile_id=f_row[1],
                file_name=f_row[2],
                file_path=f_row[3],
                file_size=f_row[4],
                content_type=f_row[5],
                created_at=f_row[6].isoformat() if f_row[6] else ""
            ))
        profiles.append(AttachmentProfileResponse(
            id=p_id,
            name=p_name,
            created_at=p_created.isoformat() if p_created else "",
            files=files
        ))
    return profiles


@router.post("/attachment-profiles", response_model=AttachmentProfileResponse)
async def create_attachment_profile(
    payload: AttachmentProfileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    profile_id = uuid.uuid4()
    await db.execute(
        text("INSERT INTO follow_up_attachment_profiles (id, organization_id, name) VALUES (:id, :org_id, :name)"),
        {"id": profile_id, "org_id": org_id, "name": payload.name}
    )
    await db.commit()
    return AttachmentProfileResponse(
        id=profile_id,
        name=payload.name,
        created_at=datetime.utcnow().isoformat(),
        files=[]
    )


@router.delete("/attachment-profiles/{profile_id}")
async def delete_attachment_profile(
    profile_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    # Ensure profile belongs to organization
    res = await db.execute(
        text("SELECT 1 FROM follow_up_attachment_profiles WHERE id = :profile_id AND organization_id = :org_id"),
        {"profile_id": profile_id, "org_id": org_id}
    )
    if not res.fetchone():
        raise HTTPException(status_code=404, detail="Attachment Profile not found.")

    await db.execute(
        text("DELETE FROM follow_up_attachment_profiles WHERE id = :profile_id"),
        {"profile_id": profile_id}
    )
    await db.commit()
    return {"success": True}


@router.post("/attachment-profiles/{profile_id}/upload", response_model=AttachmentProfileFileResponse)
async def upload_profile_file(
    profile_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    # Ensure profile belongs to organization
    profile_res = await db.execute(
        text("SELECT name FROM follow_up_attachment_profiles WHERE id = :profile_id AND organization_id = :org_id"),
        {"profile_id": profile_id, "org_id": org_id}
    )
    if not profile_res.fetchone():
        raise HTTPException(status_code=404, detail="Attachment Profile not found.")

    # Upload to Supabase bucket or mock storage path for Phase 1
    # Save metadata row
    file_id = uuid.uuid4()
    mock_path = f"organization-assets/{org_id}/followups/{profile_id}/{file_id}_{file.filename}"
    file_content = await file.read()
    file_size = len(file_content)

    # Upload to Supabase 'tenant-attachments' bucket
    supabase_upload_url = f"{settings.supabase_url}/storage/v1/object/tenant-attachments/{mock_path}"
    try:
        from app.api.routes.attachments import _supabase_request
        res = await _supabase_request(
            "POST",
            supabase_upload_url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": file.content_type or "application/octet-stream"
            },
            content=file_content
        )
        if res.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"Supabase Storage upload failed: {res.text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed Supabase upload request for follow-up attachment", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Attachment upload error: {str(e)}"
        )

    await db.execute(
        text("""
            INSERT INTO follow_up_attachment_files (id, profile_id, file_name, file_path, file_size, content_type)
            VALUES (:id, :profile_id, :file_name, :file_path, :file_size, :content_type)
        """),
        {
            "id": file_id,
            "profile_id": profile_id,
            "file_name": file.filename,
            "file_path": mock_path,
            "file_size": file_size,
            "content_type": file.content_type or "application/octet-stream"
        }
    )
    await db.commit()

    return AttachmentProfileFileResponse(
        id=file_id,
        profile_id=profile_id,
        file_name=file.filename,
        file_path=mock_path,
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream",
        created_at=datetime.utcnow().isoformat()
    )


@router.delete("/attachment-profiles/files/{file_id}")
async def delete_profile_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    # Verify owner
    res = await db.execute(
        text("""
            SELECT 1 FROM follow_up_attachment_files f
            JOIN follow_up_attachment_profiles p ON f.profile_id = p.id
            WHERE f.id = :file_id AND p.organization_id = :org_id
        """),
        {"file_id": file_id, "org_id": org_id}
    )
    if not res.fetchone():
        raise HTTPException(status_code=404, detail="File not found.")

    await db.execute(
        text("DELETE FROM follow_up_attachment_files WHERE id = :file_id"),
        {"file_id": file_id}
    )
    await db.commit()
    return {"success": True}


@router.get("/settings", response_model=FollowUpSettingsResponse)
async def get_follow_up_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    res = await db.execute(
        text("SELECT max_follow_ups, stop_on_reply, follow_up_sequence_config FROM organization_engagement_settings WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    row = res.fetchone()
    if not row:
        return FollowUpSettingsResponse(
            max_follow_ups=3,
            stop_on_reply=True,
            follow_up_sequence_config=[]
        )
    
    # Parse jsonb config list
    config_list = row[2] if row[2] is not None else []
    return FollowUpSettingsResponse(
        max_follow_ups=row[0],
        stop_on_reply=row[1],
        follow_up_sequence_config=[FollowUpStepConfig(**item) for item in config_list]
    )


@router.put("/settings", response_model=FollowUpSettingsResponse)
async def update_follow_up_settings(
    payload: FollowUpSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    config_json = json.dumps([step.dict() for step in payload.follow_up_sequence_config], default=str)
    
    await db.execute(
        text("""
            UPDATE organization_engagement_settings
            SET max_follow_ups = :max_follow_ups,
                stop_on_reply = :stop_on_reply,
                follow_up_sequence_config = CAST(:config AS jsonb),
                updated_at = NOW()
            WHERE organization_id = :org_id
        """),
        {
            "org_id": org_id,
            "max_follow_ups": payload.max_follow_ups,
            "stop_on_reply": payload.stop_on_reply,
            "config": config_json
        }
    )
    await db.commit()
    return payload


@router.get("/queue", response_model=List[FollowUpQueueItemResponse])
async def get_follow_up_queue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    # Fetch from follow_up_schedule joined with customers and profiles
    res = await db.execute(
        text("""
            SELECT 
                f.id,
                f.customer_id,
                c.company_name,
                c.contact_email,
                f.step_number,
                ap.name,
                f.scheduled_datetime,
                f.draft_status,
                f.ai_rewrite_enabled,
                f.ai_draft_body,
                f.status,
                f.created_at
            FROM follow_up_schedule f
            JOIN customers c ON f.customer_id = c.id
            LEFT JOIN follow_up_attachment_profiles ap ON f.attachment_profile_id = ap.id
            WHERE f.organization_id = :org_id AND c.deleted_at IS NULL
            ORDER BY f.scheduled_datetime ASC
        """),
        {"org_id": org_id}
    )
    
    rows = res.fetchall()
    
    # Identify the newest pending/scheduled schedule for each customer
    newest_pending_by_customer = {}
    for r in rows:
        cust_id = r[1]
        status = r[10]
        created_at = r[11]
        
        # We consider pending/scheduled status as active/pending
        if status in ('pending', 'scheduled'):
            if cust_id not in newest_pending_by_customer:
                newest_pending_by_customer[cust_id] = (r[0], created_at)
            else:
                curr_id, curr_created = newest_pending_by_customer[cust_id]
                if created_at and (not curr_created or created_at > curr_created):
                    newest_pending_by_customer[cust_id] = (r[0], created_at)
                    
    queue = []
    for r in rows:
        cust_id = r[1]
        is_current = False
        if cust_id in newest_pending_by_customer and newest_pending_by_customer[cust_id][0] == r[0]:
            is_current = True
            
        queue.append(FollowUpQueueItemResponse(
            id=r[0],
            customer_id=r[1],
            customer_name=r[2],
            customer_email=r[3],
            step_number=r[4] or 1,
            attachment_profile_name=r[5],
            scheduled_datetime=r[6].isoformat() if r[6] else None,
            draft_status=r[7] or "scheduled",
            ai_rewrite_enabled=r[8] if r[8] is not None else True,
            ai_draft_body=r[9],
            current_schedule=is_current
        ))
    return queue


@router.post("/queue/{schedule_id}/reschedule", response_model=FollowUpQueueItemResponse)
async def smart_reschedule_queue_item(
    schedule_id: uuid.UUID,
    payload: RescheduleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    
    # 1. Fetch item
    res = await db.execute(
        text("SELECT id, scheduled_datetime FROM follow_up_schedule WHERE id = :id AND organization_id = :org_id"),
        {"id": schedule_id, "org_id": org_id}
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Follow up schedule item not found.")

    # 2. Parse smart instruction
    instruction = payload.smart_instruction.lower()
    now_dt = datetime.now()
    
    if "next week" in instruction:
        new_dt = now_dt + timedelta(days=7)
    elif "10 days" in instruction:
        new_dt = now_dt + timedelta(days=10)
    elif "monday" in instruction:
        # Calculate days until next Monday
        days_ahead = 0 - now_dt.weekday()
        if days_ahead <= 0: # Target is in current or past week
            days_ahead += 7
        new_dt = now_dt + timedelta(days=days_ahead)
        new_dt = new_dt.replace(hour=9, minute=0, second=0, microsecond=0)
    elif "month" in instruction:
        # Connect at the end of this month
        if now_dt.month == 12:
            next_month = now_dt.replace(year=now_dt.year + 1, month=1, day=1)
        else:
            next_month = now_dt.replace(month=now_dt.month + 1, day=1)
        new_dt = next_month - timedelta(days=1)
        new_dt = new_dt.replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        # Fallback default 3 days
        new_dt = now_dt + timedelta(days=3)

    # 3. Update DB
    await db.execute(
        text("""
            UPDATE follow_up_schedule 
            SET scheduled_datetime = :new_dt, 
                updated_at = NOW() 
            WHERE id = :id
        """),
        {"id": schedule_id, "new_dt": new_dt}
    )
    await db.commit()

    # Re-fetch item to return updated state
    updated_res = await db.execute(
        text("""
            SELECT 
                f.id,
                f.customer_id,
                c.company_name,
                c.contact_email,
                f.step_number,
                ap.name,
                f.scheduled_datetime,
                f.draft_status,
                f.ai_rewrite_enabled,
                f.ai_draft_body
            FROM follow_up_schedule f
            JOIN customers c ON f.customer_id = c.id
            LEFT JOIN follow_up_attachment_profiles ap ON f.attachment_profile_id = ap.id
            WHERE f.id = :id
        """),
        {"id": schedule_id}
    )
    r = updated_res.fetchone()
    
    return FollowUpQueueItemResponse(
        id=r[0],
        customer_id=r[1],
        customer_name=r[2],
        customer_email=r[3],
        step_number=r[4] or 1,
        attachment_profile_name=r[5],
        scheduled_datetime=r[6].isoformat() if r[6] else None,
        draft_status=r[7] or "scheduled",
        ai_rewrite_enabled=r[8] if r[8] is not None else True,
        ai_draft_body=r[9]
    )


@router.post("/queue/{schedule_id}/action")
async def queue_item_action(
    schedule_id: uuid.UUID,
    payload: QueueActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    
    # Verify owner
    res = await db.execute(
        text("SELECT draft_status FROM follow_up_schedule WHERE id = :id AND organization_id = :org_id"),
        {"id": schedule_id, "org_id": org_id}
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Follow up schedule item not found.")

    new_status = "scheduled"
    if payload.action == "send_now":
        new_status = "completed"
    elif payload.action == "skip":
        new_status = "cancelled"
    elif payload.action == "pause":
        new_status = "paused"
    elif payload.action == "resume":
        new_status = "scheduled"

    await db.execute(
        text("UPDATE follow_up_schedule SET draft_status = :status, updated_at = NOW() WHERE id = :id"),
        {"id": schedule_id, "status": new_status}
    )
    await db.commit()
    return {"success": True, "status": new_status}


@router.get("/files/{file_id}/download")
async def download_profile_file(
    file_id: uuid.UUID,
    preview: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    import httpx
    org_id = current_user.organization_id
    res = await db.execute(
        text("SELECT file_path, file_name, content_type FROM follow_up_attachment_files WHERE id = :id"),
        {"id": file_id}
    )
    r = res.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="File not found.")
    file_path, file_name, content_type = r
    
    # 1. Direct Signed URL redirect for instant preview
    import urllib.parse
    encoded_path = urllib.parse.quote(file_path)
    if preview:
        supabase_sign_file_url = f"{settings.supabase_url}/storage/v1/object/sign/tenant-attachments/{encoded_path}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                sign_res = await client.post(
                    supabase_sign_file_url,
                    json={"expiresIn": 900},
                    headers={
                        "apikey": settings.supabase_service_role_key,
                        "Authorization": f"Bearer {settings.supabase_service_role_key}",
                        "Content-Type": "application/json"
                    }
                )
                if sign_res.status_code == 200:
                    signed_path = sign_res.json().get("signedURL") or sign_res.json().get("signedUrl")
                    if signed_path:
                        if not signed_path.startswith("/storage/v1"):
                            signed_path = f"/storage/v1{signed_path}"
                        full_signed_url = f"{settings.supabase_url}{signed_path}" if signed_path.startswith('/') else signed_path
                        from fastapi.responses import RedirectResponse
                        return RedirectResponse(url=full_signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        except Exception as e:
            logger.error("Failed to generate Supabase signed URL for profile file", error=str(e))

    # 2. Streaming proxy fallback
    media_type = content_type or "application/octet-stream"
    supabase_download_url = f"{settings.supabase_url}/storage/v1/object/authenticated/tenant-attachments/{encoded_path}"

    async def file_streamer():
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                async with client.stream(
                    "GET",
                    supabase_download_url,
                    headers={
                        "apikey": settings.supabase_service_role_key,
                        "Authorization": f"Bearer {settings.supabase_service_role_key}"
                    }
                ) as response:
                    if response.status_code != 200:
                        yield b"Failed to retrieve file from Supabase storage."
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except Exception as e:
                logger.error("Failed to stream profile file", error=str(e))
                yield f"Error: {str(e)}".encode('utf-8')

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        file_streamer(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{file_name}",
            "Cache-Control": "private, no-cache",
        }
    )


# Executions tracking Schemas
class FollowUpScheduledStartRequest(BaseModel):
    organization_id: UUID4
    trigger_type: str = "scheduled"
    workflow_execution_id: Optional[str] = None

class FollowUpScheduledStartResponse(BaseModel):
    already_running: bool
    execution_id: UUID4
    workflow_execution_id: Optional[str] = None
    status: str
    started_at: str
    total_customers: int

class FollowUpExecutionCompletionRequest(BaseModel):
    status: str # completed | failed
    error_message: Optional[str] = None

class FollowUpExecutionResponse(BaseModel):
    id: UUID4
    status: str
    trigger_type: str
    total_customers: int
    due_count: int
    processed: int
    sent: int
    completed_count: int
    failed: int
    failed_count: int
    skipped: int
    skipped_count: int
    stopped_by_reply_count: int = 0
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    error_message: Optional[str] = None


@router.post("/executions/start", response_model=FollowUpScheduledStartResponse, dependencies=[Depends(verify_api_key)])
async def start_scheduled_followup_execution(
    payload: FollowUpScheduledStartRequest,
    db: AsyncSession = Depends(get_db_session)
):
    org_id = payload.organization_id

    # 1. Concurrency Check: Find any active execution
    active_res = await db.execute(
        text("""
            SELECT id, workflow_execution_id, status, started_at, total_customers 
            FROM follow_up_executions 
            WHERE organization_id = :org_id 
              AND status IN ('pending', 'started', 'running')
            ORDER BY started_at DESC
            LIMIT 1
        """),
        {"org_id": org_id}
    )
    active_row = active_res.fetchone()
    if active_row:
        return FollowUpScheduledStartResponse(
            already_running=True,
            execution_id=active_row[0],
            workflow_execution_id=active_row[1],
            status=active_row[2],
            started_at=active_row[3].isoformat() if active_row[3] else "",
            total_customers=active_row[4]
        )

    # 2. Validate organization
    org_check = await db.execute(
        text("SELECT 1 FROM organizations WHERE id = :org_id"),
        {"org_id": org_id}
    )
    if not org_check.fetchone():
        raise HTTPException(status_code=404, detail="Organization not found.")

    # 3. Calculate due followups count via SQL
    count_res = await db.execute(
        text("""
            SELECT COUNT(*) 
            FROM follow_up_schedule f
            JOIN customers c ON f.customer_id = c.id
            WHERE f.organization_id = :org_id 
              AND f.draft_status = 'scheduled'
              AND f.scheduled_datetime <= NOW()
              AND c.deleted_at IS NULL
        """),
        {"org_id": org_id}
    )
    total_customers = count_res.scalar() or 0

    # 4. Insert new execution record
    execution_id = uuid.uuid4()
    started_at_now = await db.execute(text("SELECT NOW()"))
    started_at = started_at_now.scalar()
    
    await db.execute(
        text("""
            INSERT INTO follow_up_executions (
                id, organization_id, workflow_execution_id, trigger_type, status, started_at,
                total_customers, processed, sent, failed, skipped
            ) VALUES (
                :id, :org_id, :workflow_execution_id, :trigger_type, 'started', :started_at,
                :total_customers, 0, 0, 0, 0
            )
        """),
        {
            "id": execution_id,
            "org_id": org_id,
            "workflow_execution_id": payload.workflow_execution_id,
            "trigger_type": payload.trigger_type,
            "started_at": started_at,
            "total_customers": total_customers
        }
    )
    await db.commit()

    return FollowUpScheduledStartResponse(
        already_running=False,
        execution_id=execution_id,
        workflow_execution_id=payload.workflow_execution_id,
        status="started",
        started_at=started_at.isoformat() if started_at else "",
        total_customers=total_customers
    )


@router.post("/executions/{execution_id}/complete", dependencies=[Depends(verify_api_key)])
async def complete_followup_execution(
    execution_id: uuid.UUID,
    payload: FollowUpExecutionCompletionRequest,
    db: AsyncSession = Depends(get_db_session)
):
    # 1. Fetch execution context with current metrics
    res = await db.execute(
        text("""
            SELECT status, started_at, processed, sent, failed, skipped, stopped_by_reply_count 
            FROM follow_up_executions 
            WHERE id = :id
        """),
        {"id": execution_id}
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Execution not found.")

    curr_status, started_at, processed, sent, failed, skipped, stopped_by_reply = row

    # 2. Check Idempotency
    if curr_status in ("completed", "failed"):
        return {
            "success": True,
            "already_completed": True
        }

    # 3. Calculate duration
    duration = 0
    if started_at:
        now_res = await db.execute(text("SELECT NOW()"))
        now_time = now_res.scalar()
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if now_time.tzinfo is None:
            now_time = now_time.replace(tzinfo=timezone.utc)
        duration = int((now_time - started_at).total_seconds())
        if duration < 0:
            duration = 0

    # 4. Atomic Update
    await db.execute(
        text("""
            UPDATE follow_up_executions
            SET status = :status,
                error_message = :error_message,
                completed_at = NOW(),
                duration_seconds = :duration,
                updated_at = NOW()
            WHERE id = :id
        """),
        {
            "id": execution_id,
            "status": payload.status,
            "error_message": payload.error_message,
            "duration": duration
        }
    )
    await db.commit()

    return {
        "success": True,
        "execution_id": str(execution_id),
        "status": payload.status,
        "processed": processed,
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "stopped_by_reply_count": stopped_by_reply,
        "duration_seconds": duration
    }


@router.get("/executions/history", response_model=List[FollowUpExecutionResponse])
async def get_followup_execution_history(
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id
    offset = (page - 1) * limit
    
    res = await db.execute(
        text("""
            SELECT id, status, trigger_type, total_customers, processed, sent, failed, skipped, started_at, completed_at, duration_seconds, error_message, stopped_by_reply_count
            FROM follow_up_executions
            WHERE organization_id = :org_id
            ORDER BY started_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"org_id": org_id, "limit": limit, "offset": offset}
    )
    
    history = []
    for r in res.fetchall():
        history.append(FollowUpExecutionResponse(
            id=r[0],
            status=r[1],
            trigger_type=r[2],
            total_customers=r[3],
            due_count=r[3],
            processed=r[4],
            sent=r[5],
            completed_count=r[5],
            failed=r[6],
            failed_count=r[6],
            skipped=r[7],
            skipped_count=r[7],
            stopped_by_reply_count=r[12],
            started_at=r[8].isoformat() if r[8] else "",
            completed_at=r[9].isoformat() if r[9] else None,
            duration_seconds=r[10],
            error_message=r[11]
        ))
    return history


# Follow-up Context Schemas
class FollowUpContextRequest(BaseModel):
    organization_id: UUID4
    customer_id: UUID4
    step_number: int

class FollowUpContextCustomer(BaseModel):
    id: UUID4
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    designation: Optional[str] = None

class FollowUpContextOrganization(BaseModel):
    name: Optional[str] = None
    mailbox_email: Optional[str] = None
    website: Optional[str] = None

class FollowUpContextSettings(BaseModel):
    step_number: int
    delay_days: int
    ai_rewrite_enabled: bool
    manual_review: bool
    generate_subject: bool

class FollowUpContextEmail(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    sent_at: Optional[str] = None

class FollowUpContextThreadItem(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    sent_at: Optional[str] = None
    direction: Optional[str] = None

class FollowUpContextFile(BaseModel):
    id: UUID4
    storage_path: str
    filename: str
    content_type: str
    file_size: int
    download_url: str

class FollowUpContextAttachmentProfile(BaseModel):
    id: UUID4
    name: str
    files: List[FollowUpContextFile] = []

class FollowUpContextResponse(BaseModel):
    organization_id: UUID4
    customer_id: UUID4
    schedule_id: UUID4
    customer: FollowUpContextCustomer
    organization: FollowUpContextOrganization
    followup: FollowUpContextSettings
    previous_email: Optional[FollowUpContextEmail] = None
    email_thread: List[FollowUpContextThreadItem] = []
    signature: Optional[dict] = None
    attachment_profile: Optional[FollowUpContextAttachmentProfile] = None
    reply_detected: bool = False
    can_send: bool = True
    stop_reason: Optional[str] = None
    attachment_profile_source: Optional[str] = None
    # Upgraded Reply Tracking Columns
    reply_detected_at: Optional[str] = None
    reply_message_id: Optional[str] = None
    reply_thread_id: Optional[str] = None
    reply_reason: Optional[str] = None
    last_inbound_email: Optional[FollowUpContextEmail] = None
    last_outbound_email: Optional[FollowUpContextEmail] = None


async def check_and_register_reply(
    db: AsyncSession,
    customer_id: uuid.UUID,
    organization_id: uuid.UUID,
    source_email_log_id: Optional[uuid.UUID],
    schedule_id: uuid.UUID,
    customer_email: str
) -> dict:
    """
    Checks for inbound replies matching thread headers (thread_id, conversation_id, internet_message_id, references, in_reply_to).
    Falls back to sender email/timestamp. Ignores OOO, Auto replies, and Bounces.
    If a valid reply is detected, persists it on follow_up_schedule.
    """
    logger.info(
        "Checking reply status",
        customer_id=str(customer_id),
        organization_id=str(organization_id),
        source_email_log_id=str(source_email_log_id) if source_email_log_id else "None",
        schedule_id=str(schedule_id)
    )

    reply_detected = False
    reply_reason = None
    reply_detected_at = None
    reply_message_id = None
    reply_thread_id = None
    reply_subject = None
    reply_from = None
    last_inbound = None
    last_outbound = None

    # Fetch last outbound details
    outbound_meta = {}
    if source_email_log_id:
        res = await db.execute(
            text("""
                SELECT id, thread_id, conversation_id, internet_message_id, "references", in_reply_to, sent_at, subject, body
                FROM email_log WHERE id = :source_id
            """),
            {"source_id": source_email_log_id}
        )
        row = res.fetchone()
        if row:
            outbound_meta = {
                "id": row[0],
                "thread_id": row[1],
                "conversation_id": row[2],
                "internet_message_id": row[3],
                "references": row[4],
                "in_reply_to": row[5],
                "sent_at": row[6],
                "subject": row[7],
                "body": row[8]
            }
            last_outbound = FollowUpContextEmail(
                subject=row[7],
                body=row[8],
                sent_at=row[6].isoformat() if row[6] else None
            )

    # Fetch all inbound emails for this customer
    res_inbound = await db.execute(
        text("""
            SELECT id, subject, body, sent_at, thread_id, conversation_id, internet_message_id, "references", in_reply_to, bounce_status, delivery_status
            FROM email_log
            WHERE customer_id = :customer_id AND organization_id = :org_id AND direction = 'inbound'
            ORDER BY sent_at DESC
        """),
        {"customer_id": customer_id, "org_id": organization_id}
    )
    inbound_emails = []
    for r in res_inbound.fetchall():
        inbound_emails.append({
            "id": r[0],
            "subject": r[1],
            "body": r[2],
            "sent_at": r[3],
            "thread_id": r[4],
            "conversation_id": r[5],
            "internet_message_id": r[6],
            "references": r[7],
            "in_reply_to": r[8],
            "bounce_status": r[9],
            "delivery_status": r[10]
        })

    if inbound_emails:
        latest = inbound_emails[0]
        last_inbound = FollowUpContextEmail(
            subject=latest["subject"],
            body=latest["body"],
            sent_at=latest["sent_at"].isoformat() if latest["sent_at"] else None
        )

    import re
    # Patterns to match Auto Replies, Out Of Office, and Bounces
    ooo_subject_pattern = re.compile(
        r"^(out of office|ooo|auto:?|auto-reply|autoreply|re-?delivery|undeliverable|returned mail|delivery status|failure notice|spam|blocked|failed|daemon|postmaster|automatic response|automatic reply)",
        re.IGNORECASE
    )

    for mail in inbound_emails:
        subject = mail["subject"] or ""
        body = mail["body"] or ""
        bounce_status = mail["bounce_status"]
        delivery_status = mail["delivery_status"]

        is_false_positive = False
        fp_reason = None

        if ooo_subject_pattern.match(subject.strip()):
            is_false_positive = True
            fp_reason = "Subject pattern matches auto-reply/OOO/bounce"
        elif "auto-submitted:" in body.lower() or "x-auto-response-suppress:" in body.lower():
            is_false_positive = True
            fp_reason = "Auto-submitted headers found in body"
        elif bounce_status and str(bounce_status).lower() in ("bounced", "failed"):
            is_false_positive = True
            fp_reason = f"Bounce status indicates failure: {bounce_status}"
        elif delivery_status and str(delivery_status).lower() in ("failed", "undelivered"):
            is_false_positive = True
            fp_reason = f"Delivery status indicates failure: {delivery_status}"

        if is_false_positive:
            logger.info(
                "Ignored false positive reply candidate",
                email_id=str(mail["id"]),
                subject=subject,
                reason=fp_reason,
                execution_id="N/A",
                schedule_id=str(schedule_id)
            )
            continue

        matched = False
        match_type = None

        # 1. Thread matching using headers
        if outbound_meta:
            if mail["thread_id"] and outbound_meta["thread_id"] and mail["thread_id"] == outbound_meta["thread_id"]:
                matched = True
                match_type = "thread_id"
            elif mail["conversation_id"] and outbound_meta["conversation_id"] and mail["conversation_id"] == outbound_meta["conversation_id"]:
                matched = True
                match_type = "conversation_id"
            elif mail["in_reply_to"] and outbound_meta["internet_message_id"] and mail["in_reply_to"] == outbound_meta["internet_message_id"]:
                matched = True
                match_type = "in_reply_to -> internet_message_id"
            elif mail["references"] and outbound_meta["internet_message_id"] and outbound_meta["internet_message_id"] in mail["references"]:
                matched = True
                match_type = "outbound internet_message_id in inbound references"
            elif outbound_meta["references"] and mail["internet_message_id"] and mail["internet_message_id"] in outbound_meta["references"]:
                matched = True
                match_type = "inbound internet_message_id in outbound references"

        if matched:
            reply_detected = True
            reply_reason = f"Thread Match ({match_type})"
            reply_detected_at = mail["sent_at"]
            reply_message_id = mail["internet_message_id"] or mail["id"]
            reply_thread_id = mail["thread_id"] or mail["conversation_id"]
            reply_subject = mail["subject"]
            reply_from = customer_email
            break
        else:
            # 2. Timestamp fallback matching
            source_sent_at = outbound_meta.get("sent_at")
            if source_sent_at and mail["sent_at"] > source_sent_at:
                reply_detected = True
                reply_reason = "Timestamp Fallback"
                reply_detected_at = mail["sent_at"]
                reply_message_id = mail["internet_message_id"] or mail["id"]
                reply_thread_id = mail["thread_id"] or mail["conversation_id"]
                reply_subject = mail["subject"]
                reply_from = customer_email
                break
            elif not source_sent_at:
                reply_detected = True
                reply_reason = "Inbound received (No Outbound Sentinel)"
                reply_detected_at = mail["sent_at"]
                reply_message_id = mail["internet_message_id"] or mail["id"]
                reply_thread_id = mail["thread_id"] or mail["conversation_id"]
                reply_subject = mail["subject"]
                reply_from = customer_email
                break

    # Persist detected reply in db
    if reply_detected:
        await db.execute(
            text("""
                UPDATE follow_up_schedule
                SET reply_detected_at = :reply_detected_at,
                    reply_message_id = :reply_message_id,
                    reply_thread_id = :reply_thread_id,
                    reply_subject = :reply_subject,
                    reply_from = :reply_from,
                    reply_reason = :reply_reason,
                    updated_at = NOW()
                WHERE id = :schedule_id
            """),
            {
                "reply_detected_at": reply_detected_at,
                "reply_message_id": str(reply_message_id) if reply_message_id else None,
                "reply_thread_id": str(reply_thread_id) if reply_thread_id else None,
                "reply_subject": reply_subject,
                "reply_from": reply_from,
                "reply_reason": reply_reason,
                "schedule_id": schedule_id
            }
        )
        await db.commit()

    # Log structured reply decision details
    logger.info(
        "Reply detection results",
        schedule_id=str(schedule_id),
        reply_detected=reply_detected,
        reason=reply_reason or "No reply detected",
        matched_thread=str(reply_thread_id) if reply_thread_id else "None",
        matched_message_id=str(reply_message_id) if reply_message_id else "None",
        matched_timestamp=str(reply_detected_at) if reply_detected_at else "None",
        confidence="High (Thread Match)" if reply_reason and "Thread Match" in reply_reason else ("Medium (Timestamp Fallback)" if reply_reason else "N/A")
    )

    return {
        "reply_detected": reply_detected,
        "reply_reason": reply_reason,
        "reply_detected_at": reply_detected_at.isoformat() if reply_detected_at else None,
        "reply_message_id": str(reply_message_id) if reply_message_id else None,
        "reply_thread_id": str(reply_thread_id) if reply_thread_id else None,
        "reply_subject": reply_subject,
        "reply_from": reply_from,
        "last_inbound_email": last_inbound,
        "last_outbound_email": last_outbound
    }


def sanitize_llm_email_body(body_html: str, sig_strip_list: list = None) -> str:
    if not body_html:
        return ""
    import re
    from bs4 import BeautifulSoup
    
    # 1. Parse HTML using BeautifulSoup
    soup = BeautifulSoup(body_html, "html.parser")
    
    # Remove CSS script blocks and style blocks
    for element in soup(["script", "style", "head", "title", "meta", "link"]):
        element.decompose()
        
    # Remove images
    for img in soup.find_all("img"):
        img.decompose()
        
    # 2. Extract plain text
    text_content = soup.get_text(separator="\n")
    
    # 3. Clean up the lines
    lines = [line.strip() for line in text_content.splitlines()]
    non_empty_lines = [line for line in lines if line]
    cleaned_text = "\n".join(non_empty_lines)
    
    # 4. Remove signature/regards/sender info at the end using regex patterns
    patterns = [
        r'(?i)(?:best\s+)?regards,?\s*[\r\n]+.*$',
        r'(?i)sincerely,?\s*[\r\n]+.*$',
        r'(?i)thanks\s+and\s+regards,?\s*[\r\n]+.*$',
        r'(?i)thank\s+you,?\s*[\r\n]+.*$',
        r'(?i)best\s+wishes,?\s*[\r\n]+.*$',
        r'(?i)kind\s+regards,?\s*[\r\n]+.*$',
        r'(?i)warm\s+regards,?\s*[\r\n]+.*$',
        
        # Phone numbers
        r'(?i)phone:\s*\+?[\d\s-]{7,15}',
        r'(?i)cell:\s*\+?[\d\s-]{7,15}',
        r'(?i)tel:\s*\+?[\d\s-]{7,15}',
    ]
    
    for pattern in patterns:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.DOTALL | re.MULTILINE).strip()
        
    # 5. Dynamically strip specific signature words (name, website, designation, phone) if provided
    if sig_strip_list:
        for word in sig_strip_list:
            if word and len(word.strip()) > 2:
                escaped_word = re.escape(word.strip())
                cleaned_text = re.sub(rf'(?i)\b{escaped_word}\b', '', cleaned_text)
                
    # Collapse multiple blank lines
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    
    return cleaned_text.strip()


@router.post("/context", response_model=FollowUpContextResponse)
async def get_follow_up_context(
    payload: FollowUpContextRequest,
    db: AsyncSession = Depends(get_db_session)
):
    import time
    start_time = time.perf_counter()
    from app.core.logging import request_id_var
    req_id = request_id_var.get() or "N/A"

    logger.info(
        "Retrieving follow-up context",
        organization_id=str(payload.organization_id),
        customer_id=str(payload.customer_id),
        step_number=payload.step_number,
        request_id=req_id
    )

    # 1. Customer Check & Tenant Verification
    cust_res = await db.execute(
        text("SELECT id, contact_name, contact_email, company_name, organization_id, deleted_at FROM customers WHERE id = :customer_id"),
        {"customer_id": payload.customer_id}
    )
    cust_row = cust_res.fetchone()
    if not cust_row or str(cust_row[4]) != str(payload.organization_id) or cust_row[5] is not None:
        raise HTTPException(status_code=404, detail="Customer not found or multi-tenant mismatch.")

    customer_data = FollowUpContextCustomer(
        id=cust_row[0],
        name=cust_row[1],
        email=cust_row[2],
        company=cust_row[3],
        designation=None
    )

    # 2. Retrieve Follow-up Sequence item
    sched_res = await db.execute(
        text("SELECT id, step_number, attachment_profile_id, ai_rewrite_enabled, source_email_log_id, scheduled_datetime FROM follow_up_schedule WHERE customer_id = :customer_id AND status = 'pending' AND step_number = :step_num"),
        {"customer_id": payload.customer_id, "step_num": payload.step_number}
    )
    sched_row = sched_res.fetchone()
    if not sched_row:
        raise HTTPException(status_code=404, detail="No pending follow-up schedule item found for this step.")

    schedule_id, _, attachment_profile_id, ai_rewrite_enabled, source_email_log_id, scheduled_datetime = (
        sched_row[0], sched_row[1], sched_row[2], sched_row[3], sched_row[4], sched_row[5]
    )

    # 3. Fetch active organization settings
    org_res = await db.execute(
        text("""
            SELECT o.name, o.custom_domain, aoe.mailbox_email 
            FROM organizations o
            LEFT JOIN active_organizations_for_engagement aoe ON aoe.organization_id = o.id
            WHERE o.id = :org_id
        """),
        {"org_id": payload.organization_id}
    )
    org_row = org_res.fetchone()
    if not org_row:
        raise HTTPException(status_code=404, detail="Organization not active or not found.")

    org_data = FollowUpContextOrganization(
        name=org_row[0],
        mailbox_email=org_row[2],
        website=org_row[1]
    )

    # 4. Verify mailbox/oauth integration
    settings_res = await db.execute(
        text("SELECT follow_up_sequence_config, stop_on_reply FROM organization_engagement_settings WHERE organization_id = :org_id"),
        {"org_id": payload.organization_id}
    )
    settings_row = settings_res.fetchone()
    if not settings_row:
        raise HTTPException(status_code=404, detail="Organization engagement settings not found.")

    config_list = settings_row[0]
    stop_on_reply = settings_row[1]

    step_cfg = None
    for item in config_list:
        if item.get("step_number") == payload.step_number:
            step_cfg = item
            break

    if not step_cfg or not step_cfg.get("is_enabled", True):
        raise HTTPException(status_code=400, detail="Requested follow-up step is disabled in sequence configuration.")

    followup_settings = FollowUpContextSettings(
        step_number=payload.step_number,
        delay_days=step_cfg.get("delay_days", 2),
        ai_rewrite_enabled=step_cfg.get("ai_rewrite_enabled", True),
        manual_review=step_cfg.get("manual_review", False),
        generate_subject=step_cfg.get("generate_subject", True)
    )

    # 5. Check reply (triggers stop_on_reply check using upgraded detector)
    reply_info = await check_and_register_reply(
        db=db,
        customer_id=payload.customer_id,
        organization_id=payload.organization_id,
        source_email_log_id=source_email_log_id,
        schedule_id=schedule_id,
        customer_email=cust_row[2] or ""
    )

    reply_detected = reply_info["reply_detected"]
    can_send = True
    stop_reason = None
    if reply_detected:
        if stop_on_reply:
            can_send = False
            stop_reason = "Stopped By Reply"

    # 8. Signature (query signature details first so we can strip it from previous body and thread logs)
    sig_res = await db.execute(
        text("SELECT sender_name, designation, department, sender_email, phone, website, linkedin_url, signature_html FROM organization_signatures WHERE organization_id = :org_id"),
        {"org_id": payload.organization_id}
    )
    sig_row = sig_res.fetchone()
    signature_data = None
    sig_strip_list = []
    if sig_row:
        signature_data = {
            "sender_name": sig_row[0],
            "designation": sig_row[1],
            "department": sig_row[2],
            "sender_email": sig_row[3],
            "phone": sig_row[4],
            "website": sig_row[5],
            "linkedin_url": sig_row[6],
            "signature_html": sig_row[7]
        }
        for val in [sig_row[0], sig_row[1], sig_row[2], sig_row[4], sig_row[5]]:
            if val and len(str(val).strip()) > 2:
                sig_strip_list.append(str(val).strip())

    # 6. Previous email log (sanitized)
    prev_email = None
    if source_email_log_id:
        email_res = await db.execute(
            text("SELECT subject, body, sent_at FROM email_log WHERE id = :email_id"),
            {"email_id": source_email_log_id}
        )
        email_row = email_res.fetchone()
        if email_row:
            sanitized_body = sanitize_llm_email_body(email_row[1], sig_strip_list)
            prev_email = FollowUpContextEmail(
                subject=email_row[0],
                body=sanitized_body,
                sent_at=email_row[2].isoformat() if email_row[2] else None
            )

    # 7. Email Thread (sanitized)
    thread_res = await db.execute(
        text("SELECT subject, body, sent_at, direction FROM email_log WHERE customer_id = :customer_id AND organization_id = :org_id ORDER BY sent_at ASC"),
        {"customer_id": payload.customer_id, "org_id": payload.organization_id}
    )
    email_thread = []
    for r in thread_res.fetchall():
        sanitized_body = sanitize_llm_email_body(r[1], sig_strip_list)
        email_thread.append(FollowUpContextThreadItem(
            subject=r[0],
            body=sanitized_body,
            sent_at=r[2].isoformat() if r[2] else None,
            direction=r[3]
        ))

    # 9. Attachment Profile with Fallback & Persistence
    attachment_profile = None
    attachment_profile_source = "schedule"
    
    if not attachment_profile_id:
        if settings_row and settings_row[0]:
            config_list = settings_row[0]
            for step_cfg in config_list:
                if step_cfg.get("step_number") == payload.step_number:
                    prof_id_str = step_cfg.get("attachment_profile_id")
                    if prof_id_str:
                        attachment_profile_id = uuid.UUID(prof_id_str)
                        attachment_profile_source = "fallback"
                        
                        # Persist back to database
                        await db.execute(
                            text("UPDATE follow_up_schedule SET attachment_profile_id = :prof_id, updated_at = NOW() WHERE id = :sched_id"),
                            {"prof_id": attachment_profile_id, "sched_id": schedule_id}
                        )
                        # We commit later or right away since we read it
                        await db.commit()
                    break

    if attachment_profile_id:
        prof_res = await db.execute(
            text("SELECT name FROM follow_up_attachment_profiles WHERE id = :prof_id"),
            {"prof_id": attachment_profile_id}
        )
        prof_row = prof_res.fetchone()
        if prof_row:
            files_res = await db.execute(
                text("SELECT id, file_name, file_path, content_type, file_size FROM follow_up_attachment_files WHERE profile_id = :prof_id"),
                {"prof_id": attachment_profile_id}
            )
            files = []
            for f in files_res.fetchall():
                files.append(FollowUpContextFile(
                    id=f[0],
                    filename=f[1],
                    storage_path=f[2],
                    content_type=f[3] or "application/octet-stream",
                    file_size=f[4] or 0,
                    download_url=f"/api/v1/followups/files/{f[0]}/download"
                ))
            attachment_profile = FollowUpContextAttachmentProfile(
                id=attachment_profile_id,
                name=prof_row[0],
                files=files
            )

    # 10. Fetch latest execution ID for logging purposes
    exec_res = await db.execute(
        text("SELECT id FROM follow_up_executions WHERE organization_id = :org_id ORDER BY started_at DESC LIMIT 1"),
        {"org_id": payload.organization_id}
    )
    execution_id = exec_res.scalar()

    elapsed = int((time.perf_counter() - start_time) * 1000)
    attachment_count = len(attachment_profile.files) if attachment_profile else 0
    logger.info(
        "Successfully retrieved follow-up context",
        organization_id=str(payload.organization_id),
        customer_id=str(payload.customer_id),
        schedule_id=str(schedule_id),
        execution_id=str(execution_id) if execution_id else "N/A",
        attachment_profile_id=str(attachment_profile_id) if attachment_profile_id else "N/A",
        attachment_count=attachment_count,
        reply_detected=reply_detected,
        step_number=payload.step_number,
        request_id=req_id,
        duration_ms=elapsed
    )

    return FollowUpContextResponse(
        organization_id=payload.organization_id,
        customer_id=payload.customer_id,
        schedule_id=schedule_id,
        customer=customer_data,
        organization=org_data,
        followup=followup_settings,
        previous_email=prev_email,
        email_thread=email_thread,
        signature=signature_data,
        attachment_profile=attachment_profile,
        reply_detected=reply_detected,
        can_send=can_send,
        stop_reason=stop_reason,
        attachment_profile_source=attachment_profile_source,
        reply_detected_at=reply_info.get("reply_detected_at"),
        reply_message_id=reply_info.get("reply_message_id"),
        reply_thread_id=reply_info.get("reply_thread_id"),
        reply_reason=reply_info.get("reply_reason"),
        last_inbound_email=reply_info.get("last_inbound_email"),
        last_outbound_email=reply_info.get("last_outbound_email")
    )


class FollowUpCompleteRequest(BaseModel):
    schedule_id: UUID4
    message_id: str

class FollowUpCompleteResponse(BaseModel):
    success: bool
    next_step_created: bool
    sequence_completed: bool = False

@router.post("/schedule/complete", response_model=FollowUpCompleteResponse)
async def complete_followup_schedule(
    payload: FollowUpCompleteRequest,
    db: AsyncSession = Depends(get_db_session)
):
    import time
    from app.core.logging import request_id_var
    req_id = request_id_var.get() or "N/A"

    logger.info(
        "Completing follow-up schedule",
        schedule_id=str(payload.schedule_id),
        message_id=payload.message_id,
        request_id=req_id
    )

    # 1. Validate schedule exists and get customer email/campaign info
    sched_res = await db.execute(
         text("""
             SELECT s.id, s.organization_id, s.customer_id, s.step_number, s.source_email_log_id, s.status, c.contact_email, s.campaign_id 
             FROM follow_up_schedule s
             JOIN customers c ON s.customer_id = c.id
             WHERE s.id = :sched_id
         """),
         {"sched_id": payload.schedule_id}
    )
    sched_row = sched_res.fetchone()
    if not sched_row:
        raise HTTPException(status_code=404, detail="Schedule not found.")

    organization_id, customer_id, step_number, source_email_log_id, current_status, contact_email, campaign_id = (
        sched_row[1], sched_row[2], sched_row[3], sched_row[4], sched_row[5], sched_row[6], sched_row[7]
    )

    # Load settings to check max_follow_ups and sequence status
    settings_res = await db.execute(
        text("SELECT max_follow_ups, stop_on_reply FROM organization_engagement_settings WHERE organization_id = :org_id"),
        {"org_id": organization_id}
    )
    settings_row = settings_res.fetchone()
    max_follow_ups = settings_row[0] if settings_row else 3
    stop_on_reply = bool(settings_row[1]) if settings_row else False

    next_step = step_number + 1
    sequence_completed = (next_step > max_follow_ups)

    # Idempotency check: if status is already completed
    if current_status == "completed":
        logger.info(
            "Schedule is already completed (idempotency check)",
            schedule_id=str(payload.schedule_id),
            request_id=req_id
        )
        return FollowUpCompleteResponse(
            success=True,
            next_step_created=False,
            sequence_completed=sequence_completed
        )

    # Wrap in Transaction 1 (Completion + Metrics update)
    next_step_created = False
    try:
        # Check for inbound replies from the customer using upgraded detector
        reply_info = await check_and_register_reply(
            db=db,
            customer_id=customer_id,
            organization_id=organization_id,
            source_email_log_id=source_email_log_id,
            schedule_id=payload.schedule_id,
            customer_email=contact_email or ""
        )
        reply_detected = reply_info["reply_detected"]

        async with db.begin_nested():
            # Update status, draft_status, completed_at, and message_id
            await db.execute(
                text("""
                    UPDATE follow_up_schedule
                    SET status = 'completed',
                        draft_status = 'completed',
                        completed_at = NOW(),
                        message_id = :message_id,
                        updated_at = NOW()
                    WHERE id = :sched_id
                """),
                {"sched_id": payload.schedule_id, "message_id": payload.message_id}
            )

            # Update metrics inside follow_up_executions
            exec_id_res = await db.execute(
                text("SELECT id, started_at FROM follow_up_executions WHERE organization_id = :org_id ORDER BY started_at DESC LIMIT 1"),
                {"org_id": organization_id}
            )
            exec_row = exec_id_res.fetchone()
            if exec_row:
                execution_id = exec_row[0]
                started_at = exec_row[1]
                duration = 0
                if started_at:
                    now_res = await db.execute(text("SELECT NOW()"))
                    now_time = now_res.scalar()
                    duration = int((now_time - started_at).total_seconds())

                if reply_detected and stop_on_reply:
                    await db.execute(
                        text("""
                            UPDATE follow_up_executions 
                            SET stopped_by_reply_count = stopped_by_reply_count + 1,
                                skipped = skipped + 1,
                                processed = processed + 1,
                                completed_at = NOW(),
                                duration_seconds = :duration,
                                updated_at = NOW() 
                            WHERE id = :exec_id
                        """),
                        {"exec_id": execution_id, "duration": duration}
                    )
                else:
                    await db.execute(
                        text("""
                            UPDATE follow_up_executions 
                            SET processed = processed + 1,
                                sent = sent + 1,
                                completed_at = NOW(),
                                duration_seconds = :duration,
                                updated_at = NOW() 
                            WHERE id = :exec_id
                        """),
                        {"exec_id": execution_id, "duration": duration}
                    )

                # Auto-complete execution if no pending schedules remain OR queue processing finishes
                pending_check = await db.execute(
                    text("SELECT 1 FROM follow_up_schedule WHERE organization_id = :org_id AND status = 'pending' LIMIT 1"),
                    {"org_id": organization_id}
                )
                progress_check = await db.execute(
                    text("SELECT processed, total_customers FROM follow_up_executions WHERE id = :exec_id"),
                    {"exec_id": execution_id}
                )
                prog_row = progress_check.fetchone()
                
                no_pending = pending_check.fetchone() is None
                queue_finished = prog_row is not None and prog_row[0] >= prog_row[1]
                
                if no_pending or queue_finished:
                    await db.execute(
                        text("""
                            UPDATE follow_up_executions
                            SET status = 'completed',
                                completed_at = NOW(),
                                updated_at = NOW()
                            WHERE id = :exec_id
                        """),
                        {"exec_id": execution_id}
                    )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(
            "Failed to complete follow-up schedule and metrics in Transaction 1",
            schedule_id=str(payload.schedule_id),
            error=str(e),
            request_id=req_id
        )
        raise HTTPException(status_code=500, detail=f"Database completion transaction error: {str(e)}")

    # 2. Re-read and Verify completion status
    verify_res = await db.execute(
        text("SELECT status, completed_at, message_id FROM follow_up_schedule WHERE id = :sched_id"),
        {"sched_id": payload.schedule_id}
    )
    verify_row = verify_res.fetchone()
    if not verify_row or verify_row[0] != "completed" or verify_row[1] is None or verify_row[2] is None:
        logger.error("Schedule verification failed after commit", schedule_id=str(payload.schedule_id))
        raise HTTPException(status_code=500, detail="Database verification failed: Schedule status was not persisted correctly.")

    # 3. Transaction 2: Enqueue next step OR mark sequence completed
    if sequence_completed:
        try:
            async with db.begin_nested():
                if campaign_id:
                    await db.execute(
                        text("""
                            UPDATE campaign_enrollments
                            SET enrollment_status = 'completed',
                                exited_at = NOW(),
                                exit_reason = 'Completed all configured follow-ups',
                                updated_at = NOW()
                            WHERE customer_id = :customer_id AND campaign_id = :campaign_id AND enrollment_status = 'active'
                        """),
                        {"customer_id": customer_id, "campaign_id": campaign_id}
                    )
                else:
                    await db.execute(
                        text("""
                            UPDATE campaign_enrollments
                            SET enrollment_status = 'completed',
                                exited_at = NOW(),
                                exit_reason = 'Completed all configured follow-ups',
                                updated_at = NOW()
                            WHERE customer_id = :customer_id AND organization_id = :org_id AND enrollment_status = 'active'
                        """),
                        {"customer_id": customer_id, "org_id": organization_id}
                    )
            await db.commit()
            logger.info("Transaction 2: Successfully marked customer campaign sequence finished", customer_id=str(customer_id))
        except Exception as e:
            await db.rollback()
            logger.error(
                "Transaction 2: Failed to mark campaign enrollment completed",
                customer_id=str(customer_id),
                error=str(e),
                request_id=req_id
            )
    elif not (reply_detected and stop_on_reply):
        try:
            async with db.begin_nested():
                enqueue_res = await db.execute(
                    text("SELECT public.enqueue_followup_step(:org_id, :cust_id, :log_id, :step_num)"),
                    {
                        "org_id": organization_id,
                        "cust_id": customer_id,
                        "log_id": source_email_log_id,
                        "step_num": next_step
                    }
                )
                new_fid = enqueue_res.scalar()
                if new_fid:
                    next_step_created = True
            await db.commit()
            logger.info("Transaction 2: Successfully enqueued next follow-up step", new_schedule_id=str(new_fid) if new_fid else "None")
        except Exception as e:
            await db.rollback()
            logger.error(
                "Transaction 2: Failed to enqueue next follow-up step. Current schedule completion remains intact.",
                schedule_id=str(payload.schedule_id),
                error=str(e),
                request_id=req_id
            )

    logger.info(
        "Successfully completed follow-up schedule",
        schedule_id=str(payload.schedule_id),
        next_step_created=next_step_created,
        sequence_completed=sequence_completed,
        request_id=req_id
    )

    return FollowUpCompleteResponse(
        success=True,
        next_step_created=next_step_created,
        sequence_completed=sequence_completed
    )


class FollowUpScheduleStatusRequest(BaseModel):
    schedule_id: UUID4

class FollowUpScheduleStatusData(BaseModel):
    id: UUID4
    status: str
    draft_status: Optional[str] = None
    step_number: int
    completed_at: Optional[datetime] = None
    message_id: Optional[str] = None
    customer_id: UUID4
    organization_id: UUID4
    updated_at: Optional[datetime] = None

class FollowUpScheduleStatusResponse(BaseModel):
    success: bool
    schedule: FollowUpScheduleStatusData

@router.post("/schedule/status", response_model=FollowUpScheduleStatusResponse, tags=["Follow Ups"])
async def get_followup_schedule_status(
    payload: FollowUpScheduleStatusRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Read-only endpoint to retrieve the latest status values of a schedule.
    """
    logger.info("Retrieving schedule status", schedule_id=str(payload.schedule_id))
    res = await db.execute(
        text("""
            SELECT id, status, draft_status, step_number, completed_at, message_id, customer_id, organization_id, updated_at
            FROM follow_up_schedule
            WHERE id = :sched_id
        """),
        {"sched_id": payload.schedule_id}
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found.")

    data = FollowUpScheduleStatusData(
        id=row[0],
        status=str(row[1]),
        draft_status=row[2],
        step_number=row[3],
        completed_at=row[4],
        message_id=row[5],
        customer_id=row[6],
        organization_id=row[7],
        updated_at=row[8]
    )
    return FollowUpScheduleStatusResponse(success=True, schedule=data)


class FollowUpInboundSyncResponse(BaseModel):
    organizations_processed: int
    mailboxes_processed: int
    messages_scanned: int
    messages_inserted: int
    duplicates_skipped: int
    reply_detected: int
    schedules_completed: int
    campaigns_completed: int
    messages_skipped_unknown_sender: int
    reply_candidates: int
    reply_matches: int
    errors: List[str]
    duration_seconds: int

@router.post("/sync-inbound", response_model=FollowUpInboundSyncResponse, tags=["Follow-ups Manager"])
async def trigger_inbound_polling(
    db: AsyncSession = Depends(get_db_session)
):
    """
    Trigger manual inbound synchronization across all active tenants using Graph Delta API.
    """
    from app.services.inbound_sync_service import InboundSyncService
    service = InboundSyncService(db)
    return await service.sync_all_active_mailboxes()

