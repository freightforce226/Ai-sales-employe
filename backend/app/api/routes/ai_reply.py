"""
===========================================================

File:
ai_reply.py

Purpose:
FastAPI router defining endpoints for the AI Reply Engine.

Why this file exists:
Exposes AI settings management and draft generation endpoints to the frontend/clients.

Used By:
FastAPI Application Router
Frontend / External Integrations

Responsibilities:
- Route GET /api/v1/ai-reply/settings to fetch settings
- Route PUT /api/v1/ai-reply/settings to update settings
- Route POST /api/v1/ai-reply/generate-draft to produce acknowledgement drafts

===========================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Optional

from sqlalchemy import text
from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.core.security import verify_api_key
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.ai_reply import AIReplySettingsResponse, AIReplySettingsUpdate, AIReplyGenerateRequest, AIReplyGenerateResponse, AIReplyPendingResponse, AIReplyCompleteRequest, AIReplyCompleteResponse, AIReplyLockRequest, AIReplyLockResponse
from app.services.ai_reply_service import AIReplyService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/ai-reply", tags=["AI Reply Engine"])

@router.get("/settings", response_model=AIReplySettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Fetch AI Reply Engine settings for the authenticated user's organization.
    """
    service = AIReplyService(db)
    return await service.get_settings(current_user.organization_id)

@router.put("/settings", response_model=AIReplySettingsResponse)
async def update_settings(
    request: AIReplySettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update AI Reply Engine settings for the authenticated user's organization.
    """
    service = AIReplyService(db)
    return await service.update_settings(current_user.organization_id, request)

@router.post("/generate-draft", response_model=AIReplyGenerateResponse, dependencies=[Depends(verify_api_key)])
async def generate_reply_draft(
    request: AIReplyGenerateRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Generate an email acknowledgement draft for the given customer and conversation thread.
    Does NOT send any emails.
    Secured by API Key authentication for backend-to-backend integration.
    """
    service = AIReplyService(db)
    try:
        org_id = request.organization_id
        if not org_id:
            res = await db.execute(
                text("SELECT organization_id FROM customers WHERE id = :cust_id"),
                {"cust_id": request.customer_id}
            )
            row = res.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Customer not found."
                )
            org_id = row[0]

        customer_reply_text = request.customer_reply_text or request.latest_customer_email
        if not customer_reply_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either customer_reply_text or latest_customer_email must be provided."
            )

        return await service.generate_reply_draft(
            org_id=org_id,
            customer_id=request.customer_id,
            thread_id=request.thread_id,
            customer_reply_text=customer_reply_text
        )
    except ValueError as ve:
        if str(ve) == "already_processing":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="already_processing"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AI Reply generation endpoint failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate an AI draft right now. Please try again later."
        )

@router.get("/pending", response_model=List[AIReplyPendingResponse], dependencies=[Depends(verify_api_key)])
async def get_pending_replies(
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieve all pending, unacknowledged inbound customer replies for AI-enabled organizations.
    Secured by API Key authentication.
    """
    service = AIReplyService(db)
    try:
        res = await service.get_pending_replies()
        logger.info("Raw pending replies list before return", count=len(res))
        return res
    except Exception as e:
        logger.error("Failed to retrieve pending replies", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pending replies: {str(e)}"
        )

@router.post("/complete", response_model=AIReplyCompleteResponse, dependencies=[Depends(verify_api_key)])
async def complete_reply(
    payload: AIReplyCompleteRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Mark an AI reply as completed, update reply status, and persist send timestamps.
    """
    service = AIReplyService(db)
    try:
        res = await service.complete_reply(payload)
        return AIReplyCompleteResponse(
            success=res["success"],
            reply_id=res["reply_id"],
            graph_message_id=res["graph_message_id"],
            sent_at=res["sent_at"],
            delivery_status=res["delivery_status"]
        )
    except ValueError as ve:
        if str(ve) == "reply_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="reply_not_found"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error("Failed to complete AI reply", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete AI reply: {str(e)}"
        )

@router.post("/lock", response_model=AIReplyLockResponse, dependencies=[Depends(verify_api_key)])
async def lock_reply(
    payload: AIReplyLockRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Atomically acquire a processing lock for a pending AI reply before generation begins.
    """
    service = AIReplyService(db)
    try:
        res = await service.lock_reply(payload)
        return AIReplyLockResponse(
            success=res["success"],
            status=res.get("status"),
            reason=res.get("reason"),
            reply_id=res.get("reply_id"),
            organization_id=res["organization_id"],
            customer_id=res.get("customer_id"),
            thread_id=res.get("thread_id"),
            message_id=res.get("message_id"),
            customer_reply_text=res.get("customer_reply_text")
        )
    except Exception as e:
        logger.error("Failed to acquire reply lock", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to acquire reply lock: {str(e)}"
        )

@router.post("/fail", dependencies=[Depends(verify_api_key)])
async def fail_reply(
    payload: AIReplyLockRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Release lock on failure, transitioning status back to 'delivered' and clearing queued_at.
    """
    service = AIReplyService(db)
    try:
        res = await service.fail_reply(payload)
        return res
    except Exception as e:
        logger.error("Failed to release lock on failure", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release lock on failure: {str(e)}"
        )


@router.get("/dashboard")
async def get_operations_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = AIReplyService(db)
    try:
        return await service.get_operations_dashboard(current_user.organization_id)
    except Exception as e:
        logger.error("Failed to fetch operations dashboard KPIs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/list")
async def get_operations_list(
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = AIReplyService(db)
    try:
        return await service.get_operations_list(
            org_id=current_user.organization_id,
            search=search,
            status=status
        )
    except Exception as e:
        logger.error("Failed to fetch operations list", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{reply_id}")
async def get_operations_detail(
    reply_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = AIReplyService(db)
    try:
        return await service.get_operations_detail(current_user.organization_id, reply_id)
    except ValueError as ve:
        if str(ve) == "reply_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="reply_not_found"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error("Failed to fetch operations detail", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )



