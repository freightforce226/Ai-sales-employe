"""
Purpose of this file.
FastAPI application entry point.
Responsibility of this file.
Initializing the app, registering middleware, routes, and exception handlers.
"""

import socket

# Force IPv4 resolution globally to prevent TLS/SSL handshake timeouts on IPv6/NAT64 networks
_orig_getaddrinfo = socket.getaddrinfo
def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == socket.AF_UNSPEC or family == socket.AF_INET6:
        family = socket.AF_INET
    return _orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _patched_getaddrinfo

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import email, oauth, auth, dashboard, csv_import, customers, templates, attachments, engagement, follow_ups, ai_reply
from app.core.config import get_settings
from app.core.exceptions import (
    EmailSendError,
    GraphApiError,
    TenantNotFoundError,
    TokenExpiredError,
    TokenRefreshError,
)
from app.core.logging import configure_logging, get_logger
from app.schemas.email import EmailErrorResponse

settings = get_settings()
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting up FastAPI application", 
        environment=settings.environment,
        n8n_webhook_url=settings.n8n_webhook_url,
        n8n_service_api_key=settings.n8n_service_api_key
    )
    
    # Initialize DB schemas/tables if missing
    from app.db.migrations import run_engagement_migrations, run_ai_reply_migrations, run_organization_settings_migrations
    try:
        await run_engagement_migrations()
        await run_ai_reply_migrations()
        await run_organization_settings_migrations()
        from sqlalchemy import text
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            # 1. CREATE TABLE
            try:
                await session.execute(text("""
                    CREATE TABLE IF NOT EXISTS import_mappings (
                        id UUID PRIMARY KEY,
                        organization_id UUID NOT NULL,
                        mapping_name TEXT,
                        headers JSONB NOT NULL,
                        column_mapping JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await session.commit()
            except Exception as table_err:
                await session.rollback()
                logger.warning("Table import_mappings already exists or table creation was skipped", error=str(table_err))

            # 2. CREATE INDEX
            try:
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_import_mappings_org ON import_mappings(organization_id)
                """))
                await session.commit()
            except Exception as index_err:
                await session.rollback()
                logger.warning("Index idx_import_mappings_org already exists or index creation was skipped", error=str(index_err))

            # 3. ALTER TABLE FOR IMPORT BATCHES
            try:
                await session.execute(text("""
                    ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS header_row_used INTEGER DEFAULT 0
                """))
                await session.commit()
            except Exception as alter_err:
                await session.rollback()
                logger.warning("Column header_row_used already exists or column migration was skipped", error=str(alter_err))

            # 4. ALTER TABLE FOR EMAIL ATTACHMENTS (Migrations complete)
            # try:
            #     await session.execute(text("""
            #         ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
            #     """))
            #     await session.execute(text("""
            #         ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS attach_to_every_email BOOLEAN DEFAULT FALSE;
            #     """))
            #     await session.execute(text("""
            #         ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS file_size INTEGER DEFAULT 0;
            #     """))
            #     await session.execute(text("""
            #         ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
            #     """))
            #     await session.execute(text("""
            #         ALTER TABLE email_attachments ALTER COLUMN email_log_id DROP NOT NULL;
            #     """))
            #     await session.commit()
            # except Exception as attachment_alter_err:
            #     await session.rollback()
            #     logger.warning("Columns on email_attachments already exist or migration was skipped", error=str(attachment_alter_err))

            logger.info("Successfully verified database schemas and table columns")
    except Exception as e:
        logger.error("Failed to initialize database schemas", error=str(e))

    # Spawn background task loop for stale lock recovery
    import asyncio
    from app.services.ai_reply_service import AIReplyService
    from app.db.session import AsyncSessionLocal

    async def run_stale_lock_recovery():
        logger.info(
            "Stale AI reply lock recovery worker started.",
            interval_minutes=settings.ai_reply_recovery_interval_minutes,
            lock_timeout_minutes=settings.ai_reply_lock_timeout_minutes
        )
        # Immediate scan on startup
        try:
            async with AsyncSessionLocal() as session:
                service = AIReplyService(session)
                await service.recover_stale_locks(timeout_minutes=settings.ai_reply_lock_timeout_minutes)
        except Exception as startup_scan_err:
            logger.error("Error during initial startup stale lock recovery scan", error=str(startup_scan_err))

        while True:
            try:
                await asyncio.sleep(settings.ai_reply_recovery_interval_minutes * 60)
                async with AsyncSessionLocal() as session:
                    service = AIReplyService(session)
                    await service.recover_stale_locks(timeout_minutes=settings.ai_reply_lock_timeout_minutes)
            except asyncio.CancelledError:
                logger.info("Stale AI reply lock recovery task cancelled.")
                break
            except Exception as loop_err:
                logger.error("Error in stale AI reply lock recovery loop", error=str(loop_err))

    recovery_task = asyncio.create_task(run_stale_lock_recovery())

    yield
    recovery_task.cancel()
    logger.info("Shutting down FastAPI application")


app = FastAPI(
    title="FreightForce AI - Outlook Integration Service",
    description="Multi-tenant service for sending emails via Microsoft Graph API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    import time
    import traceback
    import secrets
    from app.core.logging import request_id_var
    from app.core.debug_logger import init_request_log, log_to_request_file
    
    # Generate unique 6-character hex request ID and set in ContextVar
    req_id = secrets.token_hex(3)
    token_token = request_id_var.set(req_id)

    # Initialize physical file log for this request
    init_request_log(req_id)
    log_to_request_file(f"Incoming Request: {request.method} {request.url.path}")

    # Exclude logs polling endpoints from verbose spam if log_level is not DEBUG
    is_poll_endpoint = "status" in request.url.path or "metrics" in request.url.path or "health" in request.url.path
    should_log_info = settings.log_level.upper() == "DEBUG" or not is_poll_endpoint

    start_time = time.time()
    org_id = request.headers.get("X-Organization-ID") or "N/A"
    
    # Read payload safely
    body_str = "N/A"
    cust_id = "N/A"
    mailbox_email = "N/A"
    recipient = "N/A"
    subject = "N/A"
    attachment_count = 0

    if request.method in ("POST", "PUT", "PATCH"):
        try:
            req_body = await request.body()
            body_str = req_body.decode("utf-8", errors="ignore")
            log_to_request_file(f"Raw Request Payload: {body_str}")
            
            # Parse payload to extract variables safely for logging
            import json
            payload_data = json.loads(body_str)
            
            # Redact sensitive access tokens or credentials
            for sensitive_key in ("access_token", "refresh_token", "encrypted_access_token", "encrypted_refresh_token", "client_secret", "api_key", "password"):
                if sensitive_key in payload_data:
                    payload_data[sensitive_key] = "[REDACTED]"
            
            # Re-serialize clean payload
            clean_body_str = json.dumps(payload_data)

            # Extract fields for observability
            org_id = payload_data.get("organization_id", org_id)
            cust_id = payload_data.get("customer_id", cust_id)
            mailbox_email = payload_data.get("mailbox_email", mailbox_email)
            recipient = payload_data.get("customer_email", recipient)
            subject = payload_data.get("subject", subject)
            attachment_count = len(payload_data.get("attachments", [])) if payload_data.get("attachments") else 0
            
            async def receive():
                return {"type": "http.request", "body": req_body, "more_body": False}
            request._receive = receive
        except Exception as payload_err:
            log_to_request_file(f"Error reading request payload: {str(payload_err)}")

    try:
        response = await call_next(request)
        duration = int((time.time() - start_time) * 1000)
        if should_log_info:
            logger.info(f"{request.method} {request.url.path} - {response.status_code} in {duration}ms")
        log_to_request_file(f"Response Sent: {response.status_code} in {duration}ms")
        return response
    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        tb_str = traceback.format_exc()
        
        # Log details to file
        log_to_request_file(f"HTTP 500 ERROR:\n{tb_str}")
        
        logger.exception(
            "HTTP 500 Internal Server Error details",
            request_id=f"[REQ-{req_id}]",
            method=request.method,
            path=request.url.path,
            duration_ms=duration,
            exception_type=type(e).__name__,
            exception_message=str(e),
            traceback=tb_str,
            organization_id=str(org_id),
            customer_id=str(cust_id),
            mailbox=str(mailbox_email),
            recipient=str(recipient),
            subject=str(subject),
            attachment_count=attachment_count,
            request_payload=body_str
        )
        raise e
    finally:
        request_id_var.reset(token_token)


from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from app.core.debug_logger import log_validation_error, log_to_request_file
    
    # Format detailed validation errors
    errors = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "")
        received = err.get("input", "N/A")
        type_ = err.get("type", "")
        errors.append(f"Field: {field} | Received Value: {received} | Error: {msg} | Type: {type_}")
        
    error_summary = "\n".join(errors)
    log_validation_error(f"URL: {request.url.path}\n{error_summary}")
    log_to_request_file(f"Pydantic ValidationError (422):\n{error_summary}")
    
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())}
    )



@app.exception_handler(TenantNotFoundError)
async def tenant_not_found_exception_handler(request: Request, exc: TenantNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=EmailErrorResponse(success=False, error=str(exc)).model_dump(),
    )


@app.exception_handler(TokenRefreshError)
@app.exception_handler(TokenExpiredError)
async def token_error_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=EmailErrorResponse(success=False, error=str(exc)).model_dump(),
    )


@app.exception_handler(GraphApiError)
@app.exception_handler(EmailSendError)
async def email_send_error_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=EmailErrorResponse(success=False, error=str(exc)).model_dump(),
    )


# Register routes
from app.api.routes import organization
from app.api.routes import signature
from app.api.routes import settings as org_settings
app.include_router(oauth.router, prefix="/api/v1/oauth")
app.include_router(auth.router)
app.include_router(email.router)
app.include_router(dashboard.router)
app.include_router(csv_import.router)
app.include_router(customers.router)
app.include_router(templates.router)
app.include_router(attachments.router)
app.include_router(engagement.router)
app.include_router(organization.router)
app.include_router(signature.router)
app.include_router(follow_ups.router, prefix="/api/v1/follow-ups")
app.include_router(follow_ups.router, prefix="/api/v1/followups")
app.include_router(ai_reply.router)
app.include_router(org_settings.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Basic health check endpoint.
    """
    return {"status": "healthy", "environment": settings.environment}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=(settings.environment == "development"))
