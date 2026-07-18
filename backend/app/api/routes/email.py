"""
Purpose of this file.
FastAPI router for email endpoints.
Responsibility of this file.
Handling incoming HTTP requests from n8n to send emails.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db_session
from app.schemas.email import EmailRequest, EmailResponse
from app.services.email_service import EmailService

router = APIRouter(prefix="/api/v1/email", tags=["Email"])


@router.post("/send", response_model=EmailResponse, dependencies=[Depends(verify_api_key)])
async def send_email(
    request: EmailRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Send an email via Microsoft Graph API for a specific tenant.
    Secured by API Key authentication.
    """
    from app.core.debug_logger import log_to_request_file
    import json
    
    # Stage 1: Request DTO
    raw_attachments = []
    if request.attachments:
        for a in request.attachments:
            d = a.model_dump()
            if "id" in d and d["id"]:
                d["id"] = str(d["id"])
            raw_attachments.append(d)
    log_to_request_file(f"Attachment Lifecycle Stage 1 - Raw Request DTO Attachments: {json.dumps(raw_attachments)}")
    
    # Stage 2: Pydantic model
    log_to_request_file(f"Attachment Lifecycle Stage 2 - Validated Pydantic Attachment Model Count: {len(request.attachments)} | Filenames: {[a.filename for a in request.attachments]}")
    
    email_service = EmailService(session)
    return await email_service.send_tenant_email(request)
