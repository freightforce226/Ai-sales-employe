import base64
import smtplib
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from tenacity import Retrying, stop_after_attempt, wait_exponential, retry_if_exception

from app.providers.base import BaseEmailProvider, run_blocking_operation
from app.core.encryption import decrypt_token
from app.core.exceptions import EmailSendError

def is_transient_smtp_error(exception: Exception) -> bool:
    e_str = str(exception).lower()
    is_auth_error = (
        isinstance(exception, smtplib.SMTPAuthenticationError) or
        "auth" in e_str or
        "login" in e_str or
        "credentials" in e_str or
        "535" in e_str
    )
    return not is_auth_error

class SmtpImapProvider(BaseEmailProvider):
    async def _get_smtp_settings(self, org_id: UUID, db_session: AsyncSession) -> Dict[str, Any]:
        """
        Retrieves and decrypts the SMTP connection configurations for the organization.
        """
        res = await db_session.execute(
            text("""
                SELECT mailbox_email, auth_username, encrypted_password, 
                       smtp_host, smtp_port, smtp_security 
                FROM tenant_integrations 
                WHERE organization_id = :org_id
            """),
            {"org_id": org_id}
        )
        row = res.fetchone()
        if not row:
            raise EmailSendError("No SMTP integration settings found for organization.")
        
        mailbox_email, auth_username, encrypted_password, smtp_host, smtp_port, smtp_security = row
        if not smtp_host or not smtp_port or not encrypted_password:
            raise EmailSendError("SMTP connection settings are incomplete.")
        
        password = decrypt_token(encrypted_password)
        username = auth_username if auth_username else mailbox_email
        
        return {
            "mailbox_email": mailbox_email,
            "username": username,
            "password": password,
            "host": smtp_host,
            "port": smtp_port,
            "security": smtp_security
        }

    def _connect_smtp(self, settings: Dict[str, Any]) -> smtplib.SMTP:
        """
        Helper method to establish a connection and log in to SMTP.
        """
        host = settings["host"]
        port = settings["port"]
        security = settings["security"]
        username = settings["username"]
        password = settings["password"]
        
        try:
            if security == "ssl_tls":
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                if security == "starttls":
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
            server.login(username, password)
            return server
        except Exception as e:
            raise EmailSendError(f"SMTP connection/authentication failed: {str(e)}")

    def _send_email_sync(self, settings: Dict[str, Any], sender: str, recipients: List[str], msg_str: str) -> None:
        """
        Synchronous helper to connect, send, and quit cleanly.
        """
        server = self._connect_smtp(settings)
        try:
            server.sendmail(sender, recipients, msg_str)
        finally:
            try:
                server.quit()
            except Exception:
                pass

    async def _send_with_retry(self, settings: Dict[str, Any], sender: str, recipients: List[str], msg_str: str) -> None:
        """
        Runs the SMTP transmission logic via run_blocking_operation with Tenacity retry support.
        """
        try:
            for attempt in Retrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception(is_transient_smtp_error)
            ):
                with attempt:
                    await run_blocking_operation(
                        self._send_email_sync,
                        settings,
                        sender,
                        recipients,
                        msg_str
                    )
        except Exception as e:
            raise EmailSendError(str(e))

    async def send_email(
        self,
        org_id: UUID,
        recipient: str,
        subject: str,
        html_body: str,
        cc_emails: List[str],
        bcc_emails: List[str],
        attachments: List[Dict[str, Any]],
        db_session: AsyncSession
    ) -> str:
        settings = await self._get_smtp_settings(org_id, db_session)
        
        try:
            msg = MIMEMultipart()
            msg["From"] = settings["mailbox_email"]
            msg["To"] = recipient
            msg["Subject"] = subject
            
            from email.utils import make_msgid
            msg_id = make_msgid(domain=settings["host"])
            msg["Message-ID"] = msg_id
            
            if cc_emails:
                msg["Cc"] = ", ".join(cc_emails)
            
            msg.attach(MIMEText(html_body, "html"))
            
            if attachments:
                for att in attachments:
                    name = att.get("name", "attachment")
                    content_bytes = base64.b64decode(att.get("contentBytes", ""))
                    content_type = att.get("contentType", "application/octet-stream")
                    
                    part = MIMEBase(*content_type.split("/", 1))
                    part.set_payload(content_bytes)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={name}"
                    )
                    msg.attach(part)
            
            recipients = [recipient]
            if cc_emails:
                recipients.extend(cc_emails)
            if bcc_emails:
                recipients.extend(bcc_emails)
                
            await self._send_with_retry(settings, settings["mailbox_email"], recipients, msg.as_string())
            return msg_id
        except Exception as e:
            raise EmailSendError(f"Failed to send SMTP email: {str(e)}")

    async def send_reply(
        self,
        org_id: UUID,
        parent_message_id: str,
        html_body: str,
        cc_emails: List[str],
        bcc_emails: List[str],
        attachments: List[Dict[str, Any]],
        db_session: AsyncSession
    ) -> str:
        settings = await self._get_smtp_settings(org_id, db_session)
        
        parent_internet_id = None
        parent_refs = None
        try:
            parent_res = await db_session.execute(
                text("""
                    SELECT internet_message_id, "references" 
                    FROM email_log 
                    WHERE (graph_message_id = :p_id OR id::text = :p_id) 
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"p_id": parent_message_id, "org_id": org_id}
            )
            row = parent_res.fetchone()
            if row:
                parent_internet_id, parent_refs = row
        except Exception:
            pass

        try:
            msg = MIMEMultipart()
            msg["From"] = settings["mailbox_email"]
            msg["To"] = parent_message_id
            msg["Subject"] = "Re: Reply"
            
            from email.utils import make_msgid
            msg_id = make_msgid(domain=settings["host"])
            msg["Message-ID"] = msg_id
            
            if parent_internet_id:
                msg["In-Reply-To"] = parent_internet_id
                
                refs_list = []
                if parent_refs:
                    refs_list = parent_refs.split()
                refs_list.append(parent_internet_id)
                
                if len(refs_list) > 10:
                    refs_list = [refs_list[0]] + refs_list[-9:]
                
                msg["References"] = " ".join(refs_list)

            if cc_emails:
                msg["Cc"] = ", ".join(cc_emails)
                
            msg.attach(MIMEText(html_body, "html"))
            
            if attachments:
                for att in attachments:
                    name = att.get("name", "attachment")
                    content_bytes = base64.b64decode(att.get("contentBytes", ""))
                    content_type = att.get("contentType", "application/octet-stream")
                    
                    part = MIMEBase(*content_type.split("/", 1))
                    part.set_payload(content_bytes)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={name}"
                    )
                    msg.attach(part)
            
            recipient = None
            cust_res = await db_session.execute(
                text("""
                    SELECT c.contact_email, el.subject FROM email_log el
                    JOIN customers c ON el.customer_id = c.id
                    WHERE (el.graph_message_id = :p_id OR el.id::text = :p_id)
                      AND el.organization_id = :org_id
                    LIMIT 1
                """),
                {"p_id": parent_message_id, "org_id": org_id}
            )
            cust_row = cust_res.fetchone()
            if cust_row:
                recipient = cust_row[0]
                parent_subject = cust_row[1]
                msg["To"] = recipient
                if not parent_subject.lower().startswith("re:"):
                    msg["Subject"] = f"Re: {parent_subject}"
                else:
                    msg["Subject"] = parent_subject
            else:
                raise EmailSendError("Cannot resolve recipient details for reply.")

            recipients = [recipient]
            if cc_emails:
                recipients.extend(cc_emails)
            if bcc_emails:
                recipients.extend(bcc_emails)
                
            await self._send_with_retry(settings, settings["mailbox_email"], recipients, msg.as_string())
            return msg_id
        except Exception as e:
            raise EmailSendError(f"Failed to send SMTP reply: {str(e)}")

    async def get_sent_metadata(
        self,
        org_id: UUID,
        subject: str,
        to_email: str,
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        # SMTP messages are sent instantly and standard Message-ID is generated on-the-fly.
        # We return retrieval_success: False since we don't query a remote Sent Items folder (unlike Microsoft REST API)
        return {"retrieval_success": False}

    async def sync_inbound_emails(
        self,
        org_id: UUID,
        sync_state: Optional[str],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        # To be implemented in Phase 2B
        return {"messages": [], "delta_link": sync_state}
