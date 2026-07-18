from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid
import time
import httpx
import asyncio
from typing import List, Optional
from pydantic import BaseModel, UUID4

from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/engagement", tags=["Email Engagement"])
settings = get_settings()
logger = get_logger(__name__)


# Schemas
class EngagementSettingsResponse(BaseModel):
    auto_engagement: bool
    schedule: str
    preferred_send_time: str
    timezone: str
    emails_per_week: int
    min_gap_days: int
    allowed_weekdays: List[int]
    batch_size: int
    delay_seconds: int

class EngagementSettingsUpdate(BaseModel):
    auto_engagement: bool
    schedule: str
    preferred_send_time: str
    timezone: str
    emails_per_week: int
    min_gap_days: int
    allowed_weekdays: List[int]
    batch_size: int
    delay_seconds: int

class EngagementRunResponse(BaseModel):
    success: bool
    execution_id: UUID4
    status: str

class EngagementStatusResponse(BaseModel):
    id: UUID4
    status: str
    trigger_type: str
    total_customers: int
    processed: int
    sent: int
    failed: int
    skipped: int
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    error_message: Optional[str] = None

class LogEntryResponse(BaseModel):
    id: UUID4
    status: str
    message: str
    created_at: str

class EngagementStatusDetail(BaseModel):
    execution: EngagementStatusResponse
    logs: List[LogEntryResponse]

class ScheduledStartRequest(BaseModel):
    organization_id: UUID4
    trigger_type: str = "scheduled"
    workflow_execution_id: Optional[str] = None

class ScheduledStartResponse(BaseModel):
    already_running: bool
    execution_id: UUID4
    workflow_execution_id: Optional[str] = None
    status: str
    started_at: str
    total_customers: int

class ExecutionCompletionRequest(BaseModel):
    status: str # completed | failed
    processed: int
    sent: int
    failed: int
    skipped: int
    error_message: Optional[str] = None

class ProgressUpdateRequest(BaseModel):
    total_customers: Optional[int] = None
    processed: Optional[int] = None
    sent: Optional[int] = None
    failed: Optional[int] = None
    skipped: Optional[int] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    log_status: Optional[str] = None # sent | failed | skipped (for log entry)
    log_message: Optional[str] = None # message string (for log entry)
    customer_id: Optional[UUID4] = None


# Endpoints

@router.get("/settings", response_model=EngagementSettingsResponse)
async def get_settings_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get organization-specific engagement settings.
    """
    org_id = current_user.organization_id
    res = await db.execute(
        text("SELECT auto_engagement, schedule, preferred_send_time, timezone, emails_per_week, min_gap_days, allowed_weekdays, batch_size, delay_seconds FROM organization_engagement_settings WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    row = res.fetchone()
    if not row:
        # Fallback if not populated
        return EngagementSettingsResponse(
            auto_engagement=False,
            schedule="daily",
            preferred_send_time="09:00",
            timezone="UTC",
            emails_per_week=3,
            min_gap_days=2,
            allowed_weekdays=[1, 2, 3, 4, 5],
            batch_size=50,
            delay_seconds=5
        )
    return EngagementSettingsResponse(
        auto_engagement=row[0],
        schedule=row[1],
        preferred_send_time=row[2],
        timezone=row[3],
        emails_per_week=row[4],
        min_gap_days=row[5],
        allowed_weekdays=row[6] if row[6] is not None else [1,2,3,4,5],
        batch_size=row[7],
        delay_seconds=row[8]
    )


@router.put("/settings", response_model=EngagementSettingsResponse)
async def update_settings_endpoint(
    payload: EngagementSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update organization-specific engagement settings.
    """
    org_id = current_user.organization_id
    import json
    allowed_weekdays_json = json.dumps(payload.allowed_weekdays)
    
    await db.execute(
        text("""
            INSERT INTO organization_engagement_settings (
                organization_id, auto_engagement, schedule, preferred_send_time, timezone, 
                emails_per_week, min_gap_days, allowed_weekdays, batch_size, delay_seconds, updated_at
            ) VALUES (
                :org_id, :auto_engagement, :schedule, :preferred_send_time, :timezone,
                :emails_per_week, :min_gap_days, CAST(:allowed_weekdays AS jsonb), :batch_size, :delay_seconds, NOW()
            )
            ON CONFLICT (organization_id) DO UPDATE SET
                auto_engagement = EXCLUDED.auto_engagement,
                schedule = EXCLUDED.schedule,
                preferred_send_time = EXCLUDED.preferred_send_time,
                timezone = EXCLUDED.timezone,
                emails_per_week = EXCLUDED.emails_per_week,
                min_gap_days = EXCLUDED.min_gap_days,
                allowed_weekdays = EXCLUDED.allowed_weekdays,
                batch_size = EXCLUDED.batch_size,
                delay_seconds = EXCLUDED.delay_seconds,
                updated_at = NOW()
        """),
        {
            "org_id": org_id,
            "auto_engagement": payload.auto_engagement,
            "schedule": payload.schedule,
            "preferred_send_time": payload.preferred_send_time,
            "timezone": payload.timezone,
            "emails_per_week": payload.emails_per_week,
            "min_gap_days": payload.min_gap_days,
            "allowed_weekdays": allowed_weekdays_json,
            "batch_size": payload.batch_size,
            "delay_seconds": payload.delay_seconds
        }
    )
    await db.commit()
    return payload


@router.post("/run", response_model=EngagementRunResponse)
async def run_engagement_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Trigger manual execution of the email engagement workflow.
    Guarantees execution lock to prevent parallel runs for the same organization.
    """
    org_id = current_user.organization_id

    # 1. Concurrency check: Ensure no other execution is active
    active_res = await db.execute(
        text("SELECT id FROM engagement_executions WHERE organization_id = :org_id AND status IN ('started', 'running')"),
        {"org_id": org_id}
    )
    if active_res.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An engagement execution is already running for this organization."
        )

    # 2. Setup execution tracking row
    execution_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO engagement_executions (
                id, organization_id, trigger_type, status, started_by_user, started_at
            ) VALUES (
                :id, :org_id, 'manual', 'started', :user_id, NOW()
            )
        """),
        {
            "id": execution_id,
            "org_id": org_id,
            "user_id": current_user.id
        }
    )
    await db.commit()

    # 3. Fire and forget trigger to n8n webhook asynchronously
    n8n_url = settings.n8n_engagement_webhook_url
    logger.info("Triggering n8n manual engagement workflow", url=n8n_url, execution_id=str(execution_id))
    
    # We execute this inside a background task or quick async call to prevent request blocking
    async def trigger_n8n():
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    n8n_url,
                    json={
                        "organization_id": str(org_id),
                        "execution_id": str(execution_id),
                        "manual": True
                    },
                    headers={"X-API-Key": settings.n8n_service_api_key}
                )
                res.raise_for_status()
        except Exception as trigger_err:
            logger.error("Failed to trigger n8n manual engagement webhook", error=str(trigger_err))
            # Automatically fail the execution record if trigger failed to connect
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("UPDATE engagement_executions SET status = 'failed', error_message = :err, completed_at = NOW() WHERE id = :id"),
                    {"id": execution_id, "err": f"Failed to reach n8n workflow: {str(trigger_err)}"}
                )
                await session.commit()

    # Run the trigger task asynchronously
    from app.db.session import AsyncSessionLocal # local import for background session safety
    asyncio.create_task(trigger_n8n())

    return EngagementRunResponse(
        success=True,
        execution_id=execution_id,
        status="started"
    )


@router.get("/status/{execution_id}", response_model=EngagementStatusDetail)
async def get_execution_status_endpoint(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get detailed execution progress, counts, and live logs. Secured by tenant context.
    """
    org_id = current_user.organization_id

    # Get execution record
    exec_res = await db.execute(
        text("""
            SELECT id, status, trigger_type, total_customers, processed, sent, failed, skipped, started_at, completed_at, duration_seconds, error_message 
            FROM engagement_executions 
            WHERE id = :id AND organization_id = :org_id
        """),
        {"id": execution_id, "org_id": org_id}
    )
    exec_row = exec_res.fetchone()
    if not exec_row:
        raise HTTPException(status_code=404, detail="Engagement execution not found.")

    execution = EngagementStatusResponse(
        id=exec_row[0],
        status=exec_row[1],
        trigger_type=exec_row[2],
        total_customers=exec_row[3],
        processed=exec_row[4],
        sent=exec_row[5],
        failed=exec_row[6],
        skipped=exec_row[7],
        started_at=exec_row[8].isoformat() if exec_row[8] else "",
        completed_at=exec_row[9].isoformat() if exec_row[9] else None,
        duration_seconds=exec_row[10],
        error_message=exec_row[11]
    )

    # Get execution logs (paginated or last 100 for live terminal progress feed)
    logs_res = await db.execute(
        text("""
            SELECT id, status, message, created_at 
            FROM engagement_execution_logs 
            WHERE execution_id = :execution_id AND organization_id = :org_id 
            ORDER BY created_at ASC LIMIT 100
        """),
        {"execution_id": execution_id, "org_id": org_id}
    )
    logs = []
    for r in logs_res.fetchall():
        logs.append(LogEntryResponse(
            id=r[0],
            status=r[1],
            message=r[2],
            created_at=r[3].isoformat() if r[3] else ""
        ))

    return EngagementStatusDetail(execution=execution, logs=logs)


@router.get("/history", response_model=List[EngagementStatusResponse])
async def get_execution_history_endpoint(
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get organization execution history log. Secured by tenant context.
    """
    org_id = current_user.organization_id
    offset = (page - 1) * limit
    
    res = await db.execute(
        text("""
            SELECT id, status, trigger_type, total_customers, processed, sent, failed, skipped, started_at, completed_at, duration_seconds, error_message
            FROM engagement_executions
            WHERE organization_id = :org_id
            ORDER BY started_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"org_id": org_id, "limit": limit, "offset": offset}
    )
    
    history = []
    for r in res.fetchall():
        history.append(EngagementStatusResponse(
            id=r[0],
            status=r[1],
            trigger_type=r[2],
            total_customers=r[3],
            processed=r[4],
            sent=r[5],
            failed=r[6],
            skipped=r[7],
            started_at=r[8].isoformat() if r[8] else "",
            completed_at=r[9].isoformat() if r[9] else None,
            duration_seconds=r[10],
            error_message=r[11]
        ))
    return history


@router.post("/cancel/{execution_id}")
async def cancel_execution_endpoint(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Cancel a running or started campaign run batch.
    """
    org_id = current_user.organization_id

    # Verify execution exists and belongs to organization
    res = await db.execute(
        text("SELECT status, started_at FROM engagement_executions WHERE id = :id AND organization_id = :org_id"),
        {"id": execution_id, "org_id": org_id}
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Execution not found.")

    status_val, started_at = row
    if status_val not in ("started", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel execution in '{status_val}' status.")

    duration = int(time.time() - started_at.timestamp()) if started_at else 0
    await db.execute(
        text("""
            UPDATE engagement_executions 
            SET status = 'failed', 
                error_message = 'Cancelled by user', 
                completed_at = NOW(),
                duration_seconds = :duration
            WHERE id = :id AND organization_id = :org_id
        """),
        {"id": execution_id, "org_id": org_id, "duration": duration}
    )
    
    # Insert log entry
    log_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO engagement_execution_logs (id, execution_id, organization_id, status, message, created_at)
            VALUES (:log_id, :execution_id, :org_id, 'failed', 'Campaign run cancelled manually by user.', NOW())
        """),
        {"log_id": log_id, "execution_id": execution_id, "org_id": org_id}
    )
    
    await db.commit()
    return {"success": True}


@router.post("/update-progress", dependencies=[Depends(verify_api_key)])
async def update_progress_callback_endpoint(
    payload: ProgressUpdateRequest,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Secure callback endpoint for n8n workflow to push progress metrics and append execution log entries.
    """
    # 1. Fetch organization context from execution record
    exec_res = await db.execute(
        text("SELECT organization_id, started_at FROM engagement_executions WHERE id = :id"),
        {"id": execution_id}
    )
    row = exec_res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Execution ID not found.")
    org_id, started_at = row

    # 2. Build dynamic update expression
    updates = []
    params = {"id": execution_id}
    
    if payload.total_customers is not None:
        updates.append("total_customers = :total_customers")
        params["total_customers"] = payload.total_customers
    if payload.processed is not None:
        updates.append("processed = :processed")
        params["processed"] = payload.processed
    if payload.sent is not None:
        updates.append("sent = :sent")
        params["sent"] = payload.sent
    if payload.failed is not None:
        updates.append("failed = :failed")
        params["failed"] = payload.failed
    if payload.skipped is not None:
        updates.append("skipped = :skipped")
        params["skipped"] = payload.skipped
    if payload.status is not None:
        updates.append("status = :status")
        params["status"] = payload.status
        if payload.status in ("completed", "failed"):
            updates.append("completed_at = NOW()")
            # Calculate duration
            duration = int(time.time() - started_at.timestamp())
            updates.append("duration_seconds = :duration")
            params["duration"] = duration
    if payload.error_message is not None:
        updates.append("error_message = :error_message")
        params["error_message"] = payload.error_message

    if updates:
        update_query = f"UPDATE engagement_executions SET {', '.join(updates)} WHERE id = :id"
        await db.execute(text(update_query), params)

    # 3. Create execution log entry if log message is provided
    if payload.log_message and payload.log_status:
        log_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO engagement_execution_logs (id, execution_id, organization_id, customer_id, status, message, created_at)
                VALUES (:log_id, :execution_id, :org_id, :customer_id, :status, :message, NOW())
            """),
            {
                "log_id": log_id,
                "execution_id": execution_id,
                "org_id": org_id,
                "customer_id": payload.customer_id,
                "status": payload.log_status,
                "message": payload.log_message
            }
        )

    await db.commit()
    return {"success": True}


@router.post("/executions/start", response_model=ScheduledStartResponse, dependencies=[Depends(verify_api_key)])
async def start_scheduled_execution(
    payload: ScheduledStartRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Start scheduled engagement execution idempotently.
    Locks concurrency if another execution is active (pending, started, or running).
    """
    org_id = payload.organization_id

    # 1. Concurrency Check: Find any active execution
    active_res = await db.execute(
        text("""
            SELECT id, workflow_execution_id, status, started_at, total_customers 
            FROM engagement_executions 
            WHERE organization_id = :org_id 
              AND status IN ('pending', 'started', 'running')
            ORDER BY started_at DESC
            LIMIT 1
        """),
        {"org_id": org_id}
    )
    active_row = active_res.fetchone()
    if active_row:
        # Return existing execution details idempotently
        return ScheduledStartResponse(
            already_running=True,
            execution_id=active_row[0],
            workflow_execution_id=active_row[1],
            status=active_row[2],
            started_at=active_row[3].isoformat() if active_row[3] else "",
            total_customers=active_row[4]
        )

    # 2. Validate organization exists
    org_check = await db.execute(
        text("SELECT 1 FROM organizations WHERE id = :org_id"),
        {"org_id": org_id}
    )
    if not org_check.fetchone():
        raise HTTPException(status_code=404, detail="Organization not found.")

    # 3. Retrieve settings for calculation
    settings_res = await db.execute(
        text("""
            SELECT emails_per_week, min_gap_days, batch_size 
            FROM organization_engagement_settings 
            WHERE organization_id = :org_id
        """),
        {"org_id": org_id}
    )
    settings_row = settings_res.fetchone()
    if settings_row:
        weekly_cap, min_gap, batch_limit = settings_row
    else:
        weekly_cap, min_gap, batch_limit = 3, 2, 50

    # 4. Calculate eligible customer count via SQL function
    count_res = await db.execute(
        text("""
            SELECT COUNT(*) FROM get_engagement_eligible_customers(
                p_organization_id := :org_id,
                p_week_start := date_trunc('week', now())::date,
                p_weekly_cap := :weekly_cap,
                p_min_gap_days := :min_gap,
                p_batch_limit := :batch_limit,
                p_batch_offset := 0
            )
        """),
        {
            "org_id": org_id,
            "weekly_cap": weekly_cap,
            "min_gap": min_gap,
            "batch_limit": batch_limit
        }
    )
    total_customers = count_res.scalar() or 0

    # 5. Insert new execution record
    execution_id = uuid.uuid4()
    started_at_now = db.execute(text("SELECT NOW()"))
    started_at = (await started_at_now).scalar()
    
    await db.execute(
        text("""
            INSERT INTO engagement_executions (
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

    return ScheduledStartResponse(
        already_running=False,
        execution_id=execution_id,
        workflow_execution_id=payload.workflow_execution_id,
        status="started",
        started_at=started_at.isoformat() if started_at else "",
        total_customers=total_customers
    )


@router.post("/executions/{execution_id}/complete", dependencies=[Depends(verify_api_key)])
async def complete_execution(
    execution_id: uuid.UUID,
    payload: ExecutionCompletionRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Atomically complete or fail an active engagement campaign run inside a single transaction.
    """
    # 1. Fetch execution context
    res = await db.execute(
        text("SELECT status, started_at FROM engagement_executions WHERE id = :id"),
        {"id": execution_id}
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Execution not found.")

    started_at = row[1]

    # Calculate duration
    duration = 0
    if started_at:
        now_res = await db.execute(text("SELECT NOW()"))
        now_time = now_res.scalar()
        duration = int((now_time - started_at).total_seconds())

    # 2. Atomic Update
    await db.execute(
        text("""
            UPDATE engagement_executions
            SET status = :status,
                processed = :processed,
                sent = :sent,
                failed = :failed,
                skipped = :skipped,
                error_message = :error_message,
                completed_at = NOW(),
                duration_seconds = :duration
            WHERE id = :id
        """),
        {
            "id": execution_id,
            "status": payload.status,
            "processed": payload.processed,
            "sent": payload.sent,
            "failed": payload.failed,
            "skipped": payload.skipped,
            "error_message": payload.error_message,
            "duration": duration
        }
    )
    await db.commit()

    return {"success": True}

