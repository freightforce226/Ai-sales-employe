import smtplib
import imaplib
from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db_session
from app.core.encryption import encrypt_token, decrypt_token
from app.core.exceptions import EmailSendError
from app.core.auth import get_current_user
from app.models.user import User

from app.providers.base import run_blocking_operation

router = APIRouter(prefix="/smtp", tags=["smtp"])

# 1. Presets configuration owned by the backend
PRESETS = {
    "hostinger": {
        "name": "Hostinger",
        "smtp_host": "smtp.hostinger.com",
        "smtp_port": 465,
        "smtp_security": "ssl_tls",
        "imap_host": "imap.hostinger.com",
        "imap_port": 993,
        "imap_security": "ssl_tls"
    },
    "zoho": {
        "name": "Zoho Mail",
        "smtp_host": "smtp.zoho.com",
        "smtp_port": 465,
        "smtp_security": "ssl_tls",
        "imap_host": "imap.zoho.com",
        "imap_port": 993,
        "imap_security": "ssl_tls"
    },
    "titan": {
        "name": "Titan Mail",
        "smtp_host": "smtp.titan.email",
        "smtp_port": 465,
        "smtp_security": "ssl_tls",
        "imap_host": "imap.titan.email",
        "imap_port": 993,
        "imap_security": "ssl_tls"
    },
    "godaddy": {
        "name": "GoDaddy",
        "smtp_host": "smtpout.secureserver.net",
        "smtp_port": 465,
        "smtp_security": "ssl_tls",
        "imap_host": "imap.secureserver.net",
        "imap_port": 993,
        "imap_security": "ssl_tls"
    },
    "namecheap": {
        "name": "Private Email (Namecheap)",
        "smtp_host": "mail.privateemail.com",
        "smtp_port": 465,
        "smtp_security": "ssl_tls",
        "imap_host": "mail.privateemail.com",
        "imap_port": 993,
        "imap_security": "ssl_tls"
    },
    "office365": {
        "name": "Microsoft 365 (SMTP/IMAP)",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_security": "ssl_tls"
    },
    "cpanel": {
        "name": "cPanel Webmail",
        "smtp_host": "mail.yourdomain.com",
        "smtp_port": 465,
        "smtp_security": "ssl_tls",
        "imap_host": "mail.yourdomain.com",
        "imap_port": 993,
        "imap_security": "ssl_tls"
    }
}


class SmtpConfigRequest(BaseModel):
    mailbox_email: str = Field(..., description="Public mailbox email address")
    auth_username: Optional[str] = Field(None, description="Username for server authentication if different from email")
    password: str = Field(..., description="Plain password to test and encrypt, or __UNCHANGED__")
    smtp_host: str = Field(...)
    smtp_port: int = Field(...)
    smtp_security: str = Field("ssl_tls", description="ssl_tls or starttls")
    imap_host: str = Field(...)
    imap_port: int = Field(...)
    imap_security: str = Field("ssl_tls")
    send_test_email: bool = Field(False)


def _validate_smtp_imap_login(req: SmtpConfigRequest):
    """
    Validates connections and credentials against external SMTP and IMAP servers.
    """
    username = req.auth_username if req.auth_username else req.mailbox_email
    
    # 1. SMTP validation
    smtp_conn = None
    try:
        if req.smtp_security == "ssl_tls":
            smtp_conn = smtplib.SMTP_SSL(req.smtp_host, req.smtp_port, timeout=10)
        else:
            smtp_conn = smtplib.SMTP(req.smtp_host, req.smtp_port, timeout=10)
            if req.smtp_security == "starttls":
                smtp_conn.ehlo()
                smtp_conn.starttls()
                smtp_conn.ehlo()
        smtp_conn.login(username, req.password)
    except Exception as smtp_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SMTP validation failed: {str(smtp_err)}"
        )
    finally:
        if smtp_conn:
            try:
                smtp_conn.quit()
            except Exception:
                pass

    # 2. IMAP validation
    imap_conn = None
    try:
        if req.imap_security == "ssl_tls":
            imap_conn = imaplib.IMAP4_SSL(req.imap_host, req.imap_port, timeout=10)
        else:
            imap_conn = imaplib.IMAP4(req.imap_host, req.imap_port, timeout=10)
        imap_conn.login(username, req.password)
    except Exception as imap_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IMAP validation failed: {str(imap_err)}"
        )
    finally:
        if imap_conn:
            try:
                imap_conn.logout()
            except Exception:
                pass


def _send_test_email_sync(req: SmtpConfigRequest):
    """
    Synchronous helper to send a test email.
    """
    smtp_conn = None
    try:
        username = req.auth_username if req.auth_username else req.mailbox_email
        if req.smtp_security == "ssl_tls":
            smtp_conn = smtplib.SMTP_SSL(req.smtp_host, req.smtp_port, timeout=10)
        else:
            smtp_conn = smtplib.SMTP(req.smtp_host, req.smtp_port, timeout=10)
            if req.smtp_security == "starttls":
                smtp_conn.ehlo()
                smtp_conn.starttls()
                smtp_conn.ehlo()
        smtp_conn.login(username, req.password)
        
        from email.mime.text import MIMEText
        msg = MIMEText("This is a verification test email from FreightForce AI Sales Employee.", "plain")
        msg["Subject"] = "FreightForce SMTP Connection Verification Test"
        msg["From"] = req.mailbox_email
        msg["To"] = req.mailbox_email
        
        smtp_conn.sendmail(req.mailbox_email, [req.mailbox_email], msg.as_string())
    except Exception as send_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection verification email send failed: {str(send_err)}"
        )
    finally:
        if smtp_conn:
            try:
                smtp_conn.quit()
            except Exception:
                pass


async def _resolve_config_password(org_id: UUID, password_val: str, db: AsyncSession) -> str:
    if password_val != "__UNCHANGED__":
        return password_val
        
    res = await db.execute(
        text("SELECT encrypted_password FROM tenant_integrations WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    row = res.fetchone()
    if not row or not row[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No saved credentials found. Please input a password."
        )
    return decrypt_token(row[0])


@router.get("/presets")
async def get_presets(current_user: User = Depends(get_current_user)):
    return PRESETS


@router.post("/test")
async def test_smtp_connection(
    req: SmtpConfigRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    resolved_pw = await _resolve_config_password(current_user.organization_id, req.password, db)
    req.password = resolved_pw
    
    await run_blocking_operation(_validate_smtp_imap_login, req)
    
    if req.send_test_email:
        await run_blocking_operation(_send_test_email_sync, req)

    return {"status": "success", "message": "SMTP and IMAP connection validated successfully"}


@router.post("/connect")
async def connect_smtp_provider(
    req: SmtpConfigRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    resolved_pw = await _resolve_config_password(current_user.organization_id, req.password, db)
    req.password = resolved_pw
    
    # Enforce active login checks before persistence
    await run_blocking_operation(_validate_smtp_imap_login, req)
    
    encrypted_pw = encrypt_token(req.password)
    
    # Save/Update integration record
    org_id = current_user.organization_id
    try:
        await db.execute(
            text("""
                INSERT INTO tenant_integrations (
                    organization_id, provider, mailbox_email, auth_username, encrypted_password,
                    smtp_host, smtp_port, smtp_security, imap_host, imap_port, imap_security,
                    is_active, token_expires_at, encrypted_access_token, encrypted_refresh_token
                ) VALUES (
                    :org_id, 'smtp', :mailbox, :auth_user, :enc_pw,
                    :smtp_h, :smtp_p, :smtp_sec, :imap_h, :imap_p, :imap_sec,
                    true, NULL, NULL, NULL
                )
                ON CONFLICT (organization_id, provider) DO UPDATE SET
                    mailbox_email = EXCLUDED.mailbox_email,
                    auth_username = EXCLUDED.auth_username,
                    encrypted_password = EXCLUDED.encrypted_password,
                    smtp_host = EXCLUDED.smtp_host,
                    smtp_port = EXCLUDED.smtp_port,
                    smtp_security = EXCLUDED.smtp_security,
                    imap_host = EXCLUDED.imap_host,
                    imap_port = EXCLUDED.imap_port,
                    imap_security = EXCLUDED.imap_security,
                    is_active = true,
                    encrypted_access_token = NULL,
                    encrypted_refresh_token = NULL,
                    token_expires_at = NULL
            """),
            {
                "org_id": org_id,
                "mailbox": req.mailbox_email,
                "auth_user": req.auth_username,
                "enc_pw": encrypted_pw,
                "smtp_h": req.smtp_host,
                "smtp_p": req.smtp_port,
                "smtp_sec": req.smtp_security,
                "imap_h": req.imap_host,
                "imap_p": req.imap_port,
                "imap_sec": req.imap_security
            }
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist integration: {str(e)}"
        )
        
    return {"status": "success", "message": "SMTP/IMAP provider connected successfully"}


@router.get("/status")
async def get_smtp_status(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(
        text("""
            SELECT provider, mailbox_email, smtp_host, imap_host, is_active 
            FROM tenant_integrations 
            WHERE organization_id = :org_id
        """),
        {"org_id": current_user.organization_id}
    )
    row = res.fetchone()
    if not row or row[0] != "smtp":
        return {"connected": False, "provider": row[0] if row else None}
        
    return {
        "connected": True,
        "provider": "smtp",
        "mailbox_email": row[1],
        "smtp_host": row[2],
        "imap_host": row[3],
        "is_active": row[4]
    }


@router.delete("/disconnect")
async def disconnect_smtp_provider(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    try:
        await db.execute(
            text("""
                UPDATE tenant_integrations 
                SET provider = 'microsoft_graph',
                    is_active = false,
                    auth_username = NULL,
                    encrypted_password = NULL,
                    smtp_host = NULL,
                    smtp_port = NULL,
                    smtp_security = NULL,
                    imap_host = NULL,
                    imap_port = NULL,
                    imap_security = NULL,
                    last_sync_cursor = NULL
                WHERE organization_id = :org_id
            """),
            {"org_id": current_user.organization_id}
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect provider: {str(e)}"
        )
        
    return {"status": "success", "message": "SMTP/IMAP provider disconnected successfully"}
