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
from app.core.logging import get_logger
from app.schemas.inbound_message import InboundSyncResult

logger = get_logger(__name__)

def is_transient_smtp_error(exception: Exception) -> bool:
    e_str = str(exception).lower()
    is_auth_error = (
        isinstance(exception, smtplib.SMTPAuthenticationError) or
        "auth" in e_str or
        "login" in e_str or
        "credentials" in e_str or
        "535" in e_str
    )
    is_recipient_or_perm_error = (
        isinstance(exception, smtplib.SMTPRecipientsRefused) or
        isinstance(exception, smtplib.SMTPSenderRefused) or
        "550" in e_str or
        "551" in e_str or
        "552" in e_str or
        "553" in e_str or
        "554" in e_str or
        "recipient rejected" in e_str or
        "mailbox unavailable" in e_str
    )
    return not (is_auth_error or is_recipient_or_perm_error)

class SmtpImapProvider(BaseEmailProvider):
    _locks = {}
    _locks_lock = asyncio.Lock()
    _smtp_pools = {}

    async def _get_smtp_settings(self, org_id: UUID, db_session: AsyncSession) -> Dict[str, Any]:
        """
        Retrieves and decrypts the SMTP connection configurations for the organization.
        If pre_resolved_settings is available (set by EmailService during Transaction A),
        it is returned directly without any database query.
        """
        if getattr(self, "pre_resolved_settings", None):
            return self.pre_resolved_settings
        if db_session is None:
            raise EmailSendError(
                "SMTP settings are not pre-resolved and no db_session was provided. "
                "Ensure credentials are resolved during Transaction A."
            )
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

    async def _get_imap_settings(self, org_id: UUID, db_session: AsyncSession) -> Dict[str, Any]:
        """
        Retrieves and decrypts the IMAP connection configurations for the organization.
        """
        res = await db_session.execute(
            text("""
                SELECT mailbox_email, auth_username, encrypted_password, 
                       imap_host, imap_port, imap_security 
                FROM tenant_integrations 
                WHERE organization_id = :org_id
            """),
            {"org_id": org_id}
        )
        row = res.fetchone()
        if not row:
            raise EmailSendError("No SMTP/IMAP integration settings found for organization.")
        
        mailbox_email, auth_username, encrypted_password, imap_host, imap_port, imap_security = row
        if not imap_host or not imap_port or not encrypted_password:
            raise EmailSendError("IMAP connection settings are incomplete.")
        
        password = decrypt_token(encrypted_password)
        username = auth_username if auth_username else mailbox_email
        
        return {
            "mailbox_email": mailbox_email,
            "username": username,
            "password": password,
            "host": imap_host,
            "port": imap_port,
            "security": imap_security
        }

    def _connect_smtp(self, settings: Dict[str, Any], debug_metrics: Dict[str, Any] = None) -> smtplib.SMTP:
        """
        Helper method to establish a connection and log in to SMTP.
        """
        import time
        from app.core.config import get_settings
        config = get_settings()
        debug_enabled = config.smtp_debug_logging

        host = settings["host"]
        port = settings["port"]
        security = settings["security"]
        username = settings["username"]
        password = settings["password"]
        
        t0 = time.perf_counter()
        try:
            if security == "ssl_tls":
                server = smtplib.SMTP_SSL(host, port, timeout=120)
            else:
                server = smtplib.SMTP(host, port, timeout=120)
                if security == "starttls":
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
            
            t1 = time.perf_counter()
            if debug_metrics is not None:
                debug_metrics["connection_time_ms"] = int((t1 - t0) * 1000)
                
            server.set_debuglevel(0)
            if debug_enabled:
                logger.info(
                    "SMTP Debug - Connection Metadata",
                    host=host,
                    port=port,
                    security=security,
                    authenticated_mailbox=username,
                    timeout=15,
                    smtp_class=type(server).__name__
                )
                
            server.login(username, password)
            t2 = time.perf_counter()
            if debug_metrics is not None:
                debug_metrics["authentication_time_ms"] = int((t2 - t1) * 1000)
                
            return server
        except Exception as e:
            raise EmailSendError(f"SMTP connection/authentication failed: {str(e)}")

    def _get_or_create_pooled_smtp(
        self,
        settings: Dict[str, Any],
        org_id: str,
        mailbox_email: str,
        debug_metrics: Dict[str, Any] = None
    ) -> smtplib.SMTP:
        """
        Retrieves a warm, healthy SMTP connection from the tenant-scoped pool
        or creates a new connection if none are available or healthy.
        Key = organization_id + mailbox_email to enforce 100% tenant isolation.
        """
        pool_key = f"{org_id}:{mailbox_email}"
        import time

        # Try reusing an existing warm connection
        if pool_key in self._smtp_pools and self._smtp_pools[pool_key]:
            server = self._smtp_pools[pool_key].pop()
            t0 = time.perf_counter()
            try:
                status, _ = server.noop()
                if status == 250:
                    if debug_metrics is not None:
                        debug_metrics["connection_reused"] = True
                        debug_metrics["connection_time_ms"] = int((time.perf_counter() - t0) * 1000)
                    logger.info("SMTP Pooled Connection HIT (NOOP healthy)", pool_key=pool_key)
                    return server
            except Exception:
                logger.info("SMTP Pooled Connection STALE (NOOP failed), closing and reconnecting", pool_key=pool_key)
                try:
                    server.close()
                except Exception:
                    pass

        # Connect fresh if pool empty or connection stale
        server = self._connect_smtp(settings, debug_metrics)
        if debug_metrics is not None:
            debug_metrics["connection_reused"] = False
        return server

    def _release_pooled_smtp(self, pool_key: str, server: smtplib.SMTP, is_healthy: bool):
        """
        Returns a healthy SMTP connection back to the tenant-scoped pool.
        Max 2 connections per mailbox.
        """
        if not is_healthy or server is None:
            if server:
                try:
                    server.close()
                except Exception:
                    pass
            return

        if pool_key not in self._smtp_pools:
            self._smtp_pools[pool_key] = []

        if len(self._smtp_pools[pool_key]) < 2:
            self._smtp_pools[pool_key].append(server)
            logger.info("SMTP Connection returned to warm pool", pool_key=pool_key, pool_size=len(self._smtp_pools[pool_key]))
        else:
            try:
                server.close()
            except Exception:
                pass

    def _send_email_sync(
        self, 
        settings: Dict[str, Any], 
        sender: str, 
        recipients: List[str], 
        msg_str: str,
        debug_metrics: Dict[str, Any] = None,
        context_info: Dict[str, Any] = None
    ) -> None:
        """
        Synchronous helper using tenant-scoped warm SMTP connection pool
        with protocol-level step-by-step latency instrumentation.
        """
        import time
        from app.core.config import get_settings
        config = get_settings()
        debug_enabled = config.smtp_debug_logging

        t0 = time.perf_counter()
        org_id = context_info.get("organization_id") if context_info else "default"
        mailbox_email = settings.get("mailbox_email") or sender
        pool_key = f"{org_id}:{mailbox_email}"

        t_acq_start = time.perf_counter()
        server = self._get_or_create_pooled_smtp(settings, org_id, mailbox_email, debug_metrics)
        t_acq_end = time.perf_counter()
        
        acq_duration_ms = int((t_acq_end - t_acq_start) * 1000)
        is_healthy = True

        mime_bytes_len = len(msg_str.encode("utf-8")) if isinstance(msg_str, str) else len(msg_str)

        try:
            t_sendmail_start = time.perf_counter()
            result = server.sendmail(sender, recipients, msg_str)
            t_sendmail_end = time.perf_counter()
            sendmail_total_ms = int((t_sendmail_end - t_sendmail_start) * 1000)

            logger.info(
                "SMTP_TRANSMISSION_SUCCESS",
                pool_key=pool_key,
                mime_bytes=mime_bytes_len,
                acquire_ms=acq_duration_ms,
                sendmail_total_ms=sendmail_total_ms
            )
            
            if debug_metrics is not None:
                debug_metrics["sendmail_time_ms"] = sendmail_total_ms
                debug_metrics["sendmail_result"] = result
                debug_metrics["mime_bytes"] = mime_bytes_len
                
        except Exception as e:
            is_healthy = False
            logger.error(
                "SMTP_PROTOCOL_TRACE_ERROR",
                pool_key=pool_key,
                mime_bytes=mime_bytes_len,
                acquire_ms=acq_duration_ms,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                exception_type=type(e).__name__,
                error=str(e)
            )
            raise e
        finally:
            self._release_pooled_smtp(pool_key, server, is_healthy)
            if debug_metrics is not None:
                debug_metrics["total_smtp_duration_ms"] = int((time.perf_counter() - t0) * 1000)

    async def _send_with_retry(
        self, 
        settings: Dict[str, Any], 
        sender: str, 
        recipients: List[str], 
        msg_str: str,
        context_info: Dict[str, Any] = None
    ) -> None:
        """
        Runs the SMTP transmission logic via run_blocking_operation with Tenacity retry support.
        """
        mailbox_email = settings.get("mailbox_email") or sender
        async with self._locks_lock:
            if mailbox_email not in self._locks:
                self._locks[mailbox_email] = asyncio.Lock()
            lock = self._locks[mailbox_email]

        async with lock:
            import time
            from app.core.config import get_settings
            config = get_settings()
            debug_enabled = config.smtp_debug_logging

            debug_metrics = {
                "connection_time_ms": 0,
                "authentication_time_ms": 0,
                "sendmail_time_ms": 0,
                "quit_time_ms": 0,
                "total_smtp_duration_ms": 0,
                "sendmail_result": {}
            }
            
            attempt_count = 0
            try:
                for attempt in Retrying(
                    reraise=True,
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=2, max=10),
                    retry=retry_if_exception(is_transient_smtp_error)
                ):
                    with attempt:
                        attempt_count += 1
                        if debug_enabled and context_info is not None:
                            context_info["retry_attempt"] = attempt_count
                            
                        await run_blocking_operation(
                            self._send_email_sync,
                            settings,
                            sender,
                            recipients,
                            msg_str,
                            debug_metrics,
                            context_info
                        )
                        
                if debug_enabled:
                    logger.info(
                        "SMTP Delivery Summary",
                        host=settings.get("host"),
                        port=settings.get("port"),
                        tls_mode=settings.get("security"),
                        recipients=recipients,
                        cc=context_info.get("cc") if context_info else [],
                        bcc=context_info.get("bcc") if context_info else [],
                        message_id=context_info.get("message_id") if context_info else None,
                        sendmail_result=debug_metrics.get("sendmail_result"),
                        total_duration_ms=debug_metrics.get("total_smtp_duration_ms"),
                        status="Success"
                    )
                    logger.info("No downstream relay evidence available from smtplib.")
            except Exception as e:
                if debug_enabled:
                    logger.error(
                        "SMTP Delivery Summary",
                        host=settings.get("host"),
                        port=settings.get("port"),
                        tls_mode=settings.get("security"),
                        recipients=recipients,
                        cc=context_info.get("cc") if context_info else [],
                        bcc=context_info.get("bcc") if context_info else [],
                        message_id=context_info.get("message_id") if context_info else None,
                        sendmail_result=debug_metrics.get("sendmail_result") if debug_metrics else None,
                        total_duration_ms=debug_metrics.get("total_smtp_duration_ms") if debug_metrics else None,
                        status="Failure",
                        error=str(e)
                    )
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
        db_session: AsyncSession,
        plain_text_body: str = None,
        sender_display_name: Optional[str] = None
    ) -> str:
        settings = await self._get_smtp_settings(org_id, db_session)
        
        try:
            import re
            
            has_inline = any(att.get("isInline") for att in attachments) if attachments else False
            
            # 1. Define parent/body container structure
            if attachments:
                if has_inline:
                    msg = MIMEMultipart("mixed")
                    related_container = MIMEMultipart("related")
                    msg.attach(related_container)
                    body_container = MIMEMultipart("alternative")
                    related_container.attach(body_container)
                    mime_tree = "multipart/mixed -> multipart/related -> multipart/alternative -> [text/plain, text/html]"
                else:
                    msg = MIMEMultipart("mixed")
                    body_container = MIMEMultipart("alternative")
                    msg.attach(body_container)
                    mime_tree = "multipart/mixed -> multipart/alternative -> [text/plain, text/html]"
            else:
                msg = MIMEMultipart("alternative")
                body_container = msg
                mime_tree = "multipart/alternative -> [text/plain, text/html]"
                
            from email.utils import formataddr
            if sender_display_name and sender_display_name.strip():
                msg["From"] = formataddr((sender_display_name.strip(), settings["mailbox_email"]))
            else:
                msg["From"] = settings["mailbox_email"]
                
            msg["To"] = recipient
            msg["Subject"] = subject
            
            from email.utils import make_msgid
            msg_id = make_msgid(domain=settings["host"])
            msg["Message-ID"] = msg_id
            
            if cc_emails:
                msg["Cc"] = ", ".join(cc_emails)
            
            # 2. Derive plain text fallback body if not provided
            if not plain_text_body:
                plain_body = re.sub(r'<br\s*/?>', '\n', html_body, flags=re.I)
                plain_body = re.sub(r'<p\s*/?>', '\n\n', plain_body, flags=re.I)
                plain_body = re.sub(r'<[^>]+>', '', plain_body)
                plain_body = plain_body.strip()
            else:
                plain_body = plain_text_body
            
            # 3. Attach text and html parts with explicit utf-8 encoding
            body_container.attach(MIMEText(plain_body, "plain", "utf-8"))
            body_container.attach(MIMEText(html_body, "html", "utf-8"))
            
            # 4. Attach files if present (after the body container)
            if attachments:
                for att in attachments:
                    name = att.get("name", "attachment")
                    content_bytes = base64.b64decode(att.get("contentBytes", ""))
                    content_type = att.get("contentType", "application/octet-stream")
                    is_inline = att.get("isInline", False)
                    cid_name = att.get("contentId")
                    
                    part = MIMEBase(*content_type.split("/", 1))
                    part.set_payload(content_bytes)
                    encoders.encode_base64(part)
                    
                    if is_inline and cid_name:
                        part.add_header("Content-ID", f"<{cid_name}>")
                        part.add_header("Content-Disposition", f"inline; filename={name}")
                        related_container.attach(part)
                    else:
                        part.add_header("Content-Disposition", f"attachment; filename={name}")
                        msg.attach(part)
            
            recipients = [recipient]
            if cc_emails:
                recipients.extend(cc_emails)
            if bcc_emails:
                recipients.extend(bcc_emails)
                
            # Log all requested details temporarily before send
            att_metadata = [{"name": att.get("name"), "size_bytes": len(att.get("contentBytes", ""))} for att in attachments] if attachments else []
            logger.info(
                "TEMPORARY SMTP SEND AUDIT (send_email)",
                content_type=msg.get_content_type(),
                mime_hierarchy=mime_tree,
                first_300_html=html_body[:300],
                html_charset="utf-8",
                num_attachments=len(attachments) if attachments else 0,
                attachments_metadata=att_metadata
            )
                
            context_info = {
                "organization_id": str(org_id),
                "customer_id": None,
                "sender": settings["mailbox_email"],
                "recipient": recipient,
                "cc": cc_emails,
                "bcc": bcc_emails,
                "message_id": msg_id,
                "internet_message_id": msg_id,
                "references": None,
                "in_reply_to": None,
                "subject": subject,
                "recipient_count": len(recipients),
                "attachment_count": len(attachments) if attachments else 0
            }
                
            # Assert exactly one To header exists
            to_headers = msg.get_all("To")
            if to_headers and len(to_headers) > 1:
                raise EmailSendError("Duplicate To header detected. Aborting SMTP transmission.")
                
            await self._send_with_retry(settings, settings["mailbox_email"], recipients, msg.as_string(), context_info)
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
        db_session: AsyncSession,
        plain_text_body: str = None,
        sender_display_name: Optional[str] = None,
        subject: Optional[str] = None
    ) -> str:
        local_db = db_session
        is_local_session = False
        if local_db is None:
            from app.db.session import AsyncSessionLocal
            local_db = AsyncSessionLocal()
            is_local_session = True

        try:
            settings = await self._get_smtp_settings(org_id, local_db)
            
            # 1. Fetch parent email details & recipient first
            parent_internet_id = None
            parent_refs = None
            recipient = None
            parent_subject = None
            resolved_cust_id = None
            
            # Fetch parent internet headers (try exact parent ID first, then fallback to any matching direction)
            try:
                parent_res = await local_db.execute(
                    text("""
                        SELECT internet_message_id, "references" 
                        FROM email_log 
                        WHERE (graph_message_id = :p_id OR id::text = :p_id OR internet_message_id = :p_id) 
                          AND organization_id = :org_id
                        ORDER BY (CASE WHEN direction = 'inbound' THEN 1 ELSE 2 END), sent_at DESC
                        LIMIT 1
                    """),
                    {"p_id": parent_message_id, "org_id": org_id}
                )
                row = parent_res.fetchone()
                if row:
                    parent_internet_id, parent_refs = row
            except Exception:
                pass

            # Fetch recipient & parent subject (prefer inbound to get customer's email, fallback to any matching outbound row)
            cust_res = await local_db.execute(
                text("""
                    SELECT c.contact_email, el.subject, el.customer_id FROM email_log el
                    JOIN customers c ON el.customer_id = c.id
                    WHERE (el.graph_message_id = :p_id OR el.id::text = :p_id OR el.internet_message_id = :p_id)
                      AND el.organization_id = :org_id
                    ORDER BY (CASE WHEN el.direction = 'inbound' THEN 1 ELSE 2 END), el.sent_at DESC
                    LIMIT 1
                """),
                {"p_id": parent_message_id, "org_id": org_id}
            )
            cust_row = cust_res.fetchone()
            if cust_row:
                recipient = cust_row[0]
                parent_subject = cust_row[1]
                resolved_cust_id = cust_row[2]
            else:
                raise EmailSendError("Cannot resolve recipient details for reply.")

                
            # Compute final subject: prioritize passed subject parameter if present, fallback to parent_subject
            target_subject = subject if subject and subject.strip() else parent_subject
            if target_subject and target_subject.strip():
                import re
                clean_sub = re.sub(r'^(?:(re|fwd|reply):\s*)+', '', target_subject.strip(), flags=re.I).strip()
                final_subject = f"Re: {clean_sub}"
            else:
                final_subject = "Re: Reply"
        finally:
            if is_local_session and local_db:
                await local_db.close()

        try:
            import re
            
            has_inline = any(att.get("isInline") for att in attachments) if attachments else False
            
            # 2. Define parent/body container structure
            if attachments:
                if has_inline:
                    msg = MIMEMultipart("mixed")
                    related_container = MIMEMultipart("related")
                    msg.attach(related_container)
                    body_container = MIMEMultipart("alternative")
                    related_container.attach(body_container)
                    mime_tree = "multipart/mixed -> multipart/related -> multipart/alternative -> [text/plain, text/html]"
                else:
                    msg = MIMEMultipart("mixed")
                    body_container = MIMEMultipart("alternative")
                    msg.attach(body_container)
                    mime_tree = "multipart/mixed -> multipart/alternative -> [text/plain, text/html]"
            else:
                msg = MIMEMultipart("alternative")
                body_container = msg
                mime_tree = "multipart/alternative -> [text/plain, text/html]"
                
            from email.utils import formataddr
            if sender_display_name and sender_display_name.strip():
                msg["From"] = formataddr((sender_display_name.strip(), settings["mailbox_email"]))
            else:
                msg["From"] = settings["mailbox_email"]
                
            msg["To"] = recipient
            msg["Subject"] = final_subject
            
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
                
            # 3. Derive plain text fallback body if not provided
            if not plain_text_body:
                plain_body = re.sub(r'<br\s*/?>', '\n', html_body, flags=re.I)
                plain_body = re.sub(r'<p\s*/?>', '\n\n', plain_body, flags=re.I)
                plain_body = re.sub(r'<[^>]+>', '', plain_body)
                plain_body = plain_body.strip()
            else:
                plain_body = plain_text_body
            
            # 4. Attach text and html parts with explicit utf-8 encoding
            body_container.attach(MIMEText(plain_body, "plain", "utf-8"))
            body_container.attach(MIMEText(html_body, "html", "utf-8"))
            
            # 5. Attach files if present (after the body container)
            if attachments:
                for att in attachments:
                    name = att.get("name", "attachment")
                    content_bytes = base64.b64decode(att.get("contentBytes", ""))
                    content_type = att.get("contentType", "application/octet-stream")
                    is_inline = att.get("isInline", False)
                    cid_name = att.get("contentId")
                    
                    part = MIMEBase(*content_type.split("/", 1))
                    part.set_payload(content_bytes)
                    encoders.encode_base64(part)
                    
                    if is_inline and cid_name:
                        part.add_header("Content-ID", f"<{cid_name}>")
                        part.add_header("Content-Disposition", f"inline; filename={name}")
                        related_container.attach(part)
                    else:
                        part.add_header("Content-Disposition", f"attachment; filename={name}")
                        msg.attach(part)

            recipients = [recipient]
            if cc_emails:
                recipients.extend(cc_emails)
            if bcc_emails:
                recipients.extend(bcc_emails)
                
            # Log all requested details temporarily before send
            att_metadata = [{"name": att.get("name"), "size_bytes": len(att.get("contentBytes", ""))} for att in attachments] if attachments else []
            logger.info(
                "TEMPORARY SMTP SEND AUDIT (send_reply)",
                content_type=msg.get_content_type(),
                mime_hierarchy=mime_tree,
                first_300_html=html_body[:300],
                html_charset="utf-8",
                num_attachments=len(attachments) if attachments else 0,
                attachments_metadata=att_metadata
            )
            
            context_info = {
                "organization_id": str(org_id),
                "customer_id": str(resolved_cust_id) if resolved_cust_id else None,
                "sender": settings["mailbox_email"],
                "recipient": recipient,
                "cc": cc_emails,
                "bcc": bcc_emails,
                "message_id": msg_id,
                "internet_message_id": msg_id,
                "references": parent_refs,
                "in_reply_to": parent_internet_id,
                "subject": msg["Subject"],
                "recipient_count": len(recipients),
                "attachment_count": len(attachments) if attachments else 0
            }
                
            # Assert singleton headers are not duplicated (Part 2)
            for header in ["From", "To", "Subject", "Message-ID", "In-Reply-To"]:
                values = msg.get_all(header)
                if values and len(values) > 1:
                    raise EmailSendError(f"Duplicate RFC5322 singleton header detected: {header}")
                
            await self._send_with_retry(settings, settings["mailbox_email"], recipients, msg.as_string(), context_info)
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
    ) -> InboundSyncResult:
        import imaplib
        import email
        import socket
        from datetime import datetime, timezone
        from app.schemas.inbound_message import InboundMessage, InboundSyncResult, InboundAttachment
        
        settings = await self._get_imap_settings(org_id, db_session)
        host = settings["host"]
        port = settings["port"]
        username = settings["username"]
        password = settings["password"]
        security = settings["security"]
        
        # Determine sync cursor
        last_cursor = 0
        if sync_state:
            try:
                last_cursor = int(sync_state)
            except Exception:
                pass
        
        if last_cursor == 0:
            cursor_res = await db_session.execute(
                text("SELECT last_sync_cursor FROM tenant_integrations WHERE organization_id = :org_id"),
                {"org_id": org_id}
            )
            row = cursor_res.fetchone()
            if row and row[0]:
                try:
                    last_cursor = int(row[0])
                except Exception:
                    pass

        def perform_imap_sync() -> tuple[list[InboundMessage], int]:
            nonlocal last_cursor
            logger.info("INSTRUMENT: Inside perform_imap_sync. Setting default timeout to 15s...")
            socket.setdefaulttimeout(15.0)
            if security == "ssl_tls" or port == 993:
                logger.info(f"INSTRUMENT: Establishing SSL/TLS connection to {host}:{port}...")
                mail = imaplib.IMAP4_SSL(host, port)
                logger.info("INSTRUMENT: SSL/TLS connection established successfully.")
            else:
                logger.info(f"INSTRUMENT: Establishing non-SSL connection to {host}:{port}...")
                mail = imaplib.IMAP4(host, port)
                logger.info("INSTRUMENT: Non-SSL connection established successfully.")
                
            try:
                logger.info(f"INSTRUMENT: Logging in as user {username}...")
                mail.login(username, password)
                logger.info("INSTRUMENT: Logged in successfully. Selecting INBOX...")
                mail.select("INBOX")
                logger.info("INSTRUMENT: INBOX selected successfully.")
                
                if last_cursor == 0:
                    logger.info("First sync detected. Performing initial offset...")
                    status, data = mail.uid("search", None, "ALL")
                    if status != "OK":
                        logger.error(f"UID SEARCH ALL failed with status {status}. Response: {data}")
                        return [], last_cursor
                    
                    if not data or not data[0]:
                        logger.info("Empty mailbox detected during first sync. Setting cursor to 0.")
                        return [], 0
                        
                    uids = [int(u) for u in data[0].split()]
                    if not uids:
                        logger.info("Empty mailbox (no UIDs) detected during first sync. Setting cursor to 0.")
                        return [], 0
                        
                    highest_uid = max(uids)
                    logger.info(f"First sync: offsetting cursor to highest UID {highest_uid}. Historical import skipped.")
                    return [], highest_uid
                
                # Subsequent incremental syncs: Query specifically for UIDs strictly greater than last_cursor
                search_query = f"UID {last_cursor + 1}:*"
                status, max_uid_data = mail.uid("search", None, search_query)
                if status != "OK" or not max_uid_data or not max_uid_data[0]:
                    logger.info(f"No new messages found in INBOX for {search_query}.")
                    return [], last_cursor
                    
                mailbox_uids = sorted([int(u) for u in max_uid_data[0].split() if int(u) > last_cursor])
                if not mailbox_uids:
                    return [], last_cursor
                
                uids = mailbox_uids
                logger.info(f"Incremental sync: {len(uids)} new UIDs to sync after last_cursor {last_cursor}.", uids=uids)
                
                normalized_messages = []

                max_uid = max(max(mailbox_uids), last_cursor)
                
                # Fetch message bodies in batches of 50 to minimize socket round-trip latency
                import re
                BATCH_SIZE = 50
                for i in range(0, len(uids), BATCH_SIZE):
                    batch_uids = uids[i:i+BATCH_SIZE]
                    uid_str = ",".join(str(u) for u in batch_uids)
                    logger.info(f"INSTRUMENT: Fetching message bodies in bulk for UIDs: {uid_str}...")
                    
                    fetch_status, fetch_data = mail.uid("fetch", uid_str, "(BODY.PEEK[])")
                    
                    # Map UID -> Raw Email bytes
                    uid_raw_map = {}
                    if fetch_status == "OK" and fetch_data:
                        for part in fetch_data:
                            if isinstance(part, tuple):
                                header = part[0].decode('utf-8', errors='ignore')
                                uid_match = re.search(r"UID\s+(\d+)", header, re.IGNORECASE)
                                if uid_match:
                                    m_uid = int(uid_match.group(1))
                                    uid_raw_map[m_uid] = part[1]
                                    
                    for uid in batch_uids:
                        max_uid = max(max_uid, uid)
                        raw_email = uid_raw_map.get(uid)
                        
                        # Fallback to single fetch if bulk response was incomplete for this UID
                        if not raw_email:
                            logger.info(f"INSTRUMENT: Bulk fetch fallback for UID: {uid}...")
                            fetch_status_fallback, fetch_data_fallback = mail.uid("fetch", str(uid), "(BODY.PEEK[])")
                            if fetch_status_fallback == "OK" and fetch_data_fallback:
                                for fallback_part in fetch_data_fallback:
                                    if isinstance(fallback_part, tuple):
                                        raw_email = fallback_part[1]
                                        break
                                        
                        if not raw_email:
                            logger.info(f"INSTRUMENT: No raw email data extracted for UID: {uid}")
                            continue
                            
                        logger.info(f"INSTRUMENT: Parsing raw message bytes to MIME for UID: {uid}...")
                        parsed_msg = email.message_from_bytes(raw_email)
                        logger.info(f"INSTRUMENT: MIME structure parsed successfully for UID: {uid}")
                        
                        def decode_hdr(val):
                            if not val:
                                return ""
                            import email.header
                            decoded_parts = email.header.decode_header(val)
                            res_parts = []
                            for v, cs in decoded_parts:
                                if isinstance(v, bytes):
                                    dec_cs = cs or "utf-8"
                                    try:
                                        res_parts.append(v.decode(dec_cs, errors="ignore"))
                                    except Exception:
                                        res_parts.append(v.decode("latin-1", errors="ignore"))
                                else:
                                    res_parts.append(str(v))
                            return "".join(res_parts).strip()
                            
                        subject = decode_hdr(parsed_msg.get("Subject"))
                        from_header = parsed_msg.get("From") or ""
                        from_name, from_email = email.utils.parseaddr(from_header)
                        from_name = decode_hdr(from_name)
                        
                        def parse_addresses(header_name):
                            addrs = parsed_msg.get_all(header_name, [])
                            res = []
                            for name_addr in email.utils.getaddresses(addrs):
                                if name_addr[1]:
                                    res.append(name_addr[1].strip().lower())
                            return res
                            
                        to_recipients = parse_addresses("To")
                        cc_recipients = parse_addresses("Cc")
                        
                        msg_id = (parsed_msg.get("Message-ID") or "").strip()
                        in_reply_to = (parsed_msg.get("In-Reply-To") or "").strip()
                        references = (parsed_msg.get("References") or "").strip()
                        references = " ".join(references.split())
                        
                        date_header = parsed_msg.get("Date")
                        received_at = datetime.now(timezone.utc)
                        if date_header:
                            try:
                                received_at = email.utils.parsedate_to_datetime(date_header)
                            except Exception:
                                pass
                                
                        # Extract bodies and attachments
                        plain_text_body = ""
                        html_body = ""
                        attachments = []
                        
                        for part in parsed_msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = part.get("Content-Disposition") or ""
                            
                            if "attachment" in content_disposition or part.get_filename():
                                filename = part.get_filename() or "attachment"
                                filename = decode_hdr(filename)
                                payload_bytes = part.get_payload(decode=True) or b""
                                size = len(payload_bytes)
                                content_id = part.get("Content-ID")
                                if content_id:
                                    content_id = content_id.strip("<>")
                                is_inline = "inline" in content_disposition
                                attachments.append(
                                    InboundAttachment(
                                        filename=filename,
                                        content_type=content_type,
                                        size=size,
                                        content_id=content_id,
                                        is_inline=is_inline,
                                        payload=None
                                    )
                                )
                            else:
                                if content_type == "text/plain":
                                    payload = part.get_payload(decode=True) or b""
                                    charset = part.get_content_charset() or "utf-8"
                                    plain_text_body = payload.decode(charset, errors="ignore")
                                elif content_type == "text/html":
                                    payload = part.get_payload(decode=True) or b""
                                    charset = part.get_content_charset() or "utf-8"
                                    html_body = payload.decode(charset, errors="ignore")
                                    
                        if plain_text_body and not html_body:
                            html_body = f"<html><body><p>{plain_text_body.replace(chr(10), '<br>')}</p></body></html>"
                        elif html_body and not plain_text_body:
                            from bs4 import BeautifulSoup
                            try:
                                soup = BeautifulSoup(html_body, "html.parser")
                                plain_text_body = soup.get_text()
                            except Exception:
                                plain_text_body = html_body
                                
                        normalized_messages.append(
                            InboundMessage(
                                provider_message_id=str(uid),
                                internet_message_id=msg_id,
                                provider="smtp_imap",
                                conversation_id=msg_id,
                                thread_id=msg_id,
                                subject=subject,
                                html_body=html_body,
                                plain_text_body=plain_text_body,
                                from_email=from_email,
                                from_name=from_name,
                                to_recipients=to_recipients,
                                cc_recipients=cc_recipients,
                                received_at=received_at,
                                has_attachments=len(attachments) > 0,
                                attachments=attachments,
                                in_reply_to=in_reply_to,
                                references=references
                            )
                        )
                
                return normalized_messages, max_uid
            finally:
                try:
                    mail.close()
                except Exception:
                    pass
                try:
                    mail.logout()
                except Exception:
                    pass
                    
        messages, new_max_uid = await run_blocking_operation(perform_imap_sync)
        
        return InboundSyncResult(
            messages=messages,
            new_cursor=str(new_max_uid),
            provider="smtp_imap"
        )
