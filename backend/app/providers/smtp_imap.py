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
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
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
        Synchronous helper to connect, send, and quit cleanly.
        """
        import time
        from app.core.config import get_settings
        config = get_settings()
        debug_enabled = config.smtp_debug_logging

        t0 = time.perf_counter()
        server = self._connect_smtp(settings, debug_metrics)
        try:
            t_start_send = time.perf_counter()
            result = server.sendmail(sender, recipients, msg_str)
            t_end_send = time.perf_counter()
            
            if debug_metrics is not None:
                debug_metrics["sendmail_time_ms"] = int((t_end_send - t_start_send) * 1000)
                debug_metrics["sendmail_result"] = result
                
            if debug_enabled and result:
                for rejected_rcpt, err_details in result.items():
                    logger.warning(
                        "SMTP Debug - Rejected Recipient Detail",
                        recipient=rejected_rcpt,
                        error_code=err_details[0] if isinstance(err_details, tuple) else None,
                        error_message=err_details[1] if isinstance(err_details, tuple) else str(err_details)
                    )
        except Exception as e:
            if debug_enabled:
                err_code = getattr(e, "smtp_code", -1)
                err_msg = getattr(e, "smtp_error", str(e))
                logger.error(
                    "SMTP Debug - Connection/Transmission Exception occurred",
                    exception_type=type(e).__name__,
                    smtp_error_code=err_code,
                    smtp_error_message=err_msg,
                    sender=sender,
                    recipients=recipients,
                    context=context_info
                )
            raise e
        finally:
            t_start_quit = time.perf_counter()
            try:
                server.close()
            except Exception:
                pass
            t_end_quit = time.perf_counter()
            if debug_metrics is not None:
                debug_metrics["quit_time_ms"] = int((t_end_quit - t_start_quit) * 1000)
                debug_metrics["total_smtp_duration_ms"] = int((t_end_quit - t0) * 1000)

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
        sender_display_name: Optional[str] = None
    ) -> str:
        settings = await self._get_smtp_settings(org_id, db_session)
        
        # 1. Fetch parent email details & recipient first
        parent_internet_id = None
        parent_refs = None
        recipient = None
        parent_subject = None
        resolved_cust_id = None
        
        # Fetch parent internet headers
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

        # Fetch recipient & parent subject
        cust_res = await db_session.execute(
            text("""
                SELECT c.contact_email, el.subject, el.customer_id FROM email_log el
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
            resolved_cust_id = cust_row[2]
        else:
            raise EmailSendError("Cannot resolve recipient details for reply.")
            
        # Compute final subject (Part 4 Investigation: Removed "Re: Reply" placeholder completely)
        if parent_subject:
            if parent_subject.lower().startswith("re:"):
                final_subject = parent_subject
            else:
                final_subject = f"Re: {parent_subject}"
        else:
            final_subject = "Re: Reply"

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
                
                # Subsequent incremental syncs
                search_query = f"UID {last_cursor + 1}:*"
                logger.info(f"Performing incremental UID search with query: {search_query}...")
                status, data = mail.uid("search", None, search_query)
                
                if status != "OK":
                    logger.error(f"Incremental UID search failed with status {status}. Response: {data}")
                    return [], last_cursor
                    
                if not data or not data[0]:
                    logger.info("No new messages found during incremental sync.")
                    return [], last_cursor
                    
                uids = [int(u) for u in data[0].split()]
                uids = sorted([u for u in uids if u > last_cursor])
                logger.info(f"Found {len(uids)} new messages to sync.", uids=uids)
                
                if not uids:
                    return [], last_cursor
                
                normalized_messages = []
                max_uid = last_cursor
                
                for uid in uids:
                    max_uid = max(max_uid, uid)
                    logger.info(f"INSTRUMENT: Fetching message body for UID: {uid}...")
                    fetch_status, fetch_data = mail.uid("fetch", str(uid), "(BODY.PEEK[])")
                    logger.info(f"INSTRUMENT: Fetch status: {fetch_status} for UID: {uid}")
                    if fetch_status != "OK" or not fetch_data:
                        continue
                        
                    raw_email = None
                    for part in fetch_data:
                        if isinstance(part, tuple):
                            raw_email = part[1]
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
                            tup = email.utils.parsedate_to_datetime(date_header)
                            if tup:
                                received_at = tup
                        except Exception:
                            pass
                            
                    html_body = ""
                    plain_text_body = ""
                    attachments = []
                    
                    for part in parsed_msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        
                        if "attachment" in content_disposition or part.get_filename():
                            filename = decode_hdr(part.get_filename() or "attachment")
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
