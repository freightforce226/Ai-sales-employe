import base64
import time
import mimetypes
import os
import httpx
import asyncio
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.providers import EmailProviderFactory, BaseEmailProvider
from app.core.exceptions import EmailSendError, GraphApiError, TenantNotFoundError
from app.core.logging import get_logger
from app.schemas.email import EmailRequest, EmailResponse
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

# Execution-scoped cache dictionary: key = storage_path
_attachment_cache = {}
CACHE_TTL_SECONDS = 300

# Read-only configuration caches to optimize database N+1 queries
_org_settings_cache = {}
_org_ai_settings_cache = {}
_tenant_mailbox_cache = {}
_signature_cache = {}


def _clean_old_cache_entries():
    now = time.time()
    expired = [k for k, v in _attachment_cache.items() if now - v["cached_at"] > CACHE_TTL_SECONDS]
    for k in expired:
        del _attachment_cache[k]


async def _fetch_and_cache_attachment(storage_path: str, strict: bool, stats: dict) -> Optional[dict]:
    from app.core.debug_logger import log_to_request_file
    _clean_old_cache_entries()

    # Check cache
    if storage_path in _attachment_cache:
        entry = _attachment_cache[storage_path]
        if time.time() - entry["cached_at"] <= CACHE_TTL_SECONDS:
            logger.info("Attachment Cache HIT", storage_path=storage_path)
            log_to_request_file(f"Attachment Cache HIT for storage_path: {storage_path}")
            stats["hits"] += 1
            return {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": entry["file_name"],
                "contentType": entry["content_type"],
                "contentBytes": entry["content_bytes"]
            }

    logger.info("Attachment Cache MISS", storage_path=storage_path)
    log_to_request_file(f"Attachment Cache MISS. Commencing download for storage_path: {storage_path}")
    stats["misses"] += 1
    supabase_download_url = f"{settings.supabase_url}/storage/v1/object/authenticated/tenant-attachments/{storage_path}"
    log_to_request_file(f"Downloading from Supabase: {supabase_download_url}")

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(
                supabase_download_url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"
                }
            )
            log_to_request_file(f"Supabase download response status code: {res.status_code}")
            if res.status_code != 200:
                raise Exception(f"Supabase returned status {res.status_code}: {res.text}")

            content = res.content
            file_size = len(content)
            elapsed = time.time() - start_time
            logger.info("Downloaded Size", size=file_size, elapsed_seconds=elapsed, storage_path=storage_path)
            log_to_request_file(f"Downloaded attachment file successfully. Size: {file_size} bytes, Time taken: {elapsed:.3f}s")
            stats["total_bytes"] += file_size

            # Derive mimetype and filename
            content_type = res.headers.get("Content-Type")
            if not content_type or content_type == "application/octet-stream":
                m_type, _ = mimetypes.guess_type(storage_path)
                content_type = m_type or "application/pdf"

            storage_basename = os.path.basename(storage_path)
            parts = storage_basename.split('_', 1)
            file_name = parts[1] if len(parts) > 1 else storage_basename

            log_to_request_file(f"Converting file '{file_name}' to base64 format...")
            base64_str = base64.b64encode(content).decode("utf-8")
            log_to_request_file(f"Base64 encoding completed successfully. String length: {len(base64_str)} chars")

            # Store in cache
            _attachment_cache[storage_path] = {
                "content_bytes": base64_str,
                "content_type": content_type,
                "file_name": file_name,
                "size": file_size,
                "cached_at": time.time()
            }

            return {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": file_name,
                "contentType": content_type,
                "contentBytes": base64_str
            }
    except Exception as e:
        logger.error("Failed to download attachment", storage_path=storage_path, error=str(e))
        log_to_request_file(f"Failed to download or convert attachment from storage_path '{storage_path}'. Error: {str(e)}")
        if strict:
            raise EmailSendError(f"Attachment download failed for {storage_path}: {str(e)}")
        logger.warning("Skipping failed attachment (strict_attachment_mode is False)", storage_path=storage_path, error=str(e))
        return None


class EmailService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.provider_factory = EmailProviderFactory(session)

    async def _send_new_email(
        self,
        request: EmailRequest,
        provider: BaseEmailProvider,
        final_html_body: str,
        graph_attachments: list,
        cc_emails: list,
        bcc_emails: list,
        prefix: str,
        sender_display_name: Optional[str] = None
    ) -> str:
        from app.core.debug_logger import log_to_request_file
        log_to_request_file("Executing Scenario 2: Standard Outbound Email (sendMail)")
        return await provider.send_email(
            org_id=request.organization_id,
            recipient=request.customer_email,
            subject=request.subject,
            html_body=final_html_body,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            attachments=graph_attachments,
            db_session=self.session,
            sender_display_name=sender_display_name
        )

    async def _send_threaded_reply(
        self,
        request: EmailRequest,
        provider: BaseEmailProvider,
        final_html_body: str,
        graph_attachments: list,
        parent_message_id: str,
        cc_emails: list,
        bcc_emails: list,
        prefix: str,
        sender_display_name: Optional[str] = None
    ) -> str:
        from app.core.debug_logger import log_to_request_file
        log_to_request_file(f"Executing Scenario 1: Threaded Reply on parent message ID {parent_message_id}")
        return await provider.send_reply(
            org_id=request.organization_id,
            parent_message_id=parent_message_id,
            html_body=final_html_body,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            attachments=graph_attachments,
            db_session=self.session,
            sender_display_name=sender_display_name
        )

    async def send_tenant_email(self, request: EmailRequest) -> EmailResponse:
        import traceback
        import uuid
        import sys
        import time
        from app.core.logging import request_id_var
        from app.core.debug_logger import log_to_request_file
        from app.services.email_branding_service import EmailBrandingService
        
        overall_start_time = time.perf_counter()
        req_id = request_id_var.get() or "UNKNOWN"
        prefix = f"[REQ-{req_id}] "

        log_to_request_file(f"Validated EmailRequest:\n{request.model_dump_json(indent=2)}")

        branding_service = EmailBrandingService(self.session)

        # Traceability status flags
        smtp_send_completed = False
        email_log_insert_completed = False
        attachment_insert_completed = False
        followup_scheduling_completed = False
        embedding_generation_started = False
        campaign_enrollment_update_completed = False

        recipient = request.customer_email
        subject = request.subject

        class StepTracker:
            def __init__(self, num: int, name: str):
                self.num = num
                self.name = name
            async def __aenter__(self):
                msg = f"[STEP {self.num}] {self.name} - START"
                print(f"{prefix}{msg}", flush=True)
                log_to_request_file(msg)
                self.start_time = time.perf_counter()
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                elapsed = int((time.perf_counter() - self.start_time) * 1000)
                if exc_type is not None:
                    msg = f"[STEP {self.num}] {self.name} - FAILED ({elapsed} ms)"
                    print(f"{prefix}{msg}", flush=True)
                    log_to_request_file(msg)
                else:
                    msg = f"[STEP {self.num}] {self.name} - SUCCESS ({elapsed} ms)"
                    print(f"{prefix}{msg}", flush=True)
                    log_to_request_file(msg)

        # Diagnostic Helper
        def handle_diagnostic_failure(stage: str, exc: Exception, local_vars: dict):
            duration = f"{time.perf_counter() - overall_start_time:.2f}"
            req = local_vars.get("request")
            
            tb_frames = traceback.extract_tb(exc.__traceback__)
            failing_file = "Unknown"
            failing_line = "Unknown"
            if tb_frames:
                last_frame = tb_frames[-1]
                failing_file = last_frame.filename
                failing_line = last_frame.lineno

            org_name = "Amplus Logistics"
            cust_name = "Unknown"
            rec_email = recipient
            seq_step = "Unknown"
            camp_name = "Follow-up Campaign"
            sub_val = subject
            att_count = 0
            att_names = []
            
            if req:
                rec_email = req.customer_email or recipient
                sub_val = req.subject or subject
                att_count = len(req.attachments) if req.attachments else 0
                att_names = [a.filename for a in req.attachments] if req.attachments else []
                if getattr(req, "step_number", None):
                    seq_step = f"Step {req.step_number}"
                
            if local_vars.get("contact_name"):
                cust_name = local_vars.get("contact_name")
            elif local_vars.get("customer_row"):
                row = local_vars.get("customer_row")
                try:
                    cust_name = row[1] or row[2] or "Unknown"
                except Exception:
                    pass

            if local_vars.get("sender_display_name"):
                org_name = local_vars.get("sender_display_name")

            provider_val = "Microsoft Graph"
            if local_vars.get("smtp_send_completed") is not None or "smtp" in stage.lower():
                provider_val = "SMTP Provider"

            error_msg = f"{type(exc).__name__}: {str(exc)}"

            diag_msg = (
                "\n-------------------------------------------------\n"
                "EMAIL SEND FAILED\n"
                f"Organization     {org_name}\n"
                f"Customer         {cust_name}\n"
                f"Recipient        {rec_email}\n"
                f"Sequence         {seq_step}\n"
                f"Campaign         {camp_name}\n"
                f"Subject          {sub_val}\n"
                f"Attachments      {att_count}\n"
                f"Attachment Names {att_names}\n"
                f"Attempt          1\n"
                f"Duration         {duration} seconds\n"
                f"Provider         {provider_val}\n"
                f"Error            {error_msg}\n"
                "-------------------------------------------------"
            )
            print(diag_msg, file=sys.stderr, flush=True)
            log_to_request_file(diag_msg)
            logger.error("Email send path failure diagnostic", 
                         stage=stage, 
                         exc_class=type(exc).__name__, 
                         failing_file=failing_file,
                         failing_line=failing_line,
                         organization=org_name,
                         customer=cust_name,
                         recipient=rec_email,
                         sequence=seq_step,
                         campaign=camp_name,
                         subject=sub_val,
                         attachment_count=att_count,
                         attachment_names=att_names,
                         duration=f"{duration}s",
                         provider=provider_val,
                         error=error_msg)

        # STEP 1: Request received
        async with StepTracker(1, "Request received"):
            pass

        # STEP 2: Customer lookup
        logger.info("SELECT customer")
        log_to_request_file("Executing: SELECT customer")
        contact_name = "Team"
        try:
            async with StepTracker(2, "Customer lookup"):
                cust_res = await self.session.execute(
                    text("SELECT id, contact_name FROM customers WHERE contact_email = :email AND organization_id = :org_id"),
                    {"email": request.customer_email, "org_id": request.organization_id}
                )
                cust_row = cust_res.fetchone()
                if not cust_row:
                    raise Exception("SaaS Multi-tenant verification failed: Customer tenant mismatch.")
                customer_id = str(cust_row[0])
                if cust_row[1]:
                    contact_name = str(cust_row[1])
                log_to_request_file(f"Customer lookup result: ID={customer_id}, contact_name={contact_name}")
        except Exception as e:
            handle_diagnostic_failure("Customer lookup", e, locals())
            await self.session.rollback()
            raise e

        # STEP 3: Mailbox lookup
        logger.info("SELECT tenant_integrations")
        log_to_request_file("Executing: SELECT tenant_integrations")
        mailbox_email = "N/A"
        try:
            async with StepTracker(3, "Mailbox lookup"):
                now = time.time()
                org_id_str = str(request.organization_id)
                if org_id_str in _tenant_mailbox_cache and now - _tenant_mailbox_cache[org_id_str]["cached_at"] <= CACHE_TTL_SECONDS:
                    mailbox_email = _tenant_mailbox_cache[org_id_str]["data"]
                else:
                    tok_res = await self.session.execute(
                        text("SELECT mailbox_email FROM tenant_integrations WHERE organization_id = :org_id"),
                        {"org_id": request.organization_id}
                    )
                    row = tok_res.fetchone()
                    if row:
                        mailbox_email = row[0]
                    _tenant_mailbox_cache[org_id_str] = {"data": mailbox_email, "cached_at": now}
                log_to_request_file(f"Mailbox lookup result: mailbox_email={mailbox_email}")
        except Exception as e:
            handle_diagnostic_failure("Mailbox lookup", e, locals())
            await self.session.rollback()
            raise e

        # STEP 4: Download attachment
        graph_attachments = []
        log_to_request_file(f"Attachment Lifecycle Stage 3 - Email request object count: {len(request.attachments)} | Metadata: {request.attachments}")
        try:
            async with StepTracker(4, "Download attachment"):
                if request.attachments:
                    stats = {"hits": 0, "misses": 0, "total_bytes": 0}
                    tasks = []
                    for att in request.attachments:
                        storage_path = att.storage_path
                        if not storage_path and att.id:
                            res_att = await self.session.execute(
                                text("SELECT file_path FROM follow_up_attachment_files WHERE id = :id"),
                                {"id": att.id}
                            )
                            row_att = res_att.fetchone()
                            if row_att:
                                storage_path = row_att[0]
                        
                        if storage_path:
                            tasks.append(
                                _fetch_and_cache_attachment(
                                    storage_path,
                                    request.strict_attachment_mode,
                                    stats
                                )
                            )
                        elif request.strict_attachment_mode:
                            raise EmailSendError(f"Attachment storage path could not be resolved for ID: {att.id}")
                    
                    if tasks:
                        results = await asyncio.gather(*tasks)
                        graph_attachments = [r for r in results if r is not None]
                attachment_insert_completed = True
                log_to_request_file(f"Attachment download result: {len(graph_attachments)} attachments downloaded.")
        except Exception as e:
            handle_diagnostic_failure("Download attachment", e, locals())
            await self.session.rollback()
            raise e

        # Resolve email provider dynamically via factory
        try:
            factory = EmailProviderFactory(self.session)
            provider = await factory.get_provider_for_tenant(request.organization_id)
        except Exception as e:
            handle_diagnostic_failure("Provider Factory Resolution", e, locals())
            await self.session.rollback()
            raise e

        # Load Signature Settings
        try:
            org_id_str = str(request.organization_id)
            now = time.time()
            if org_id_str in _signature_cache and now - _signature_cache[org_id_str]["cached_at"] <= CACHE_TTL_SECONDS:
                sig_config = _signature_cache[org_id_str]["data"]
            else:
                sig_config = await branding_service.get_signature(request.organization_id)
                _signature_cache[org_id_str] = {"data": sig_config, "cached_at": now}
        except Exception as e:
            handle_diagnostic_failure("Signature Settings Load", e, locals())
            await self.session.rollback()
            raise e

        # STEP 5: Render HTML and Plain Text
        try:
            async with StepTracker(5, "Render HTML and Plain Text"):
                has_sep = "--" in request.html_body
                has_reg = "best regards" in request.html_body.lower() or "regards" in request.html_body.lower()
                has_sig = (sig_config.signature_html.lower() in request.html_body.lower()) if sig_config and sig_config.signature_html else False
                logger.info(
                    "Stage: Email Payload Builder (Before Rendering)",
                    reply_id=str(request.parent_message_id or "N/A"),
                    reply_body_length=len(request.html_body),
                    contains_separator=has_sep,
                    contains_best_regards=has_reg,
                    contains_org_signature=has_sig
                )

                cleaned_body = branding_service.clean_and_format_body(request.html_body)
                
                final_html_body = branding_service.render_html_email(
                    body_content=cleaned_body,
                    signature_html=sig_config.signature_html if sig_config else None,
                    banner_url=sig_config.footer_image_url if sig_config else None
                )
                
                # Check if footer image exists and append it as an inline attachment
                if sig_config and sig_config.footer_image_path:
                    try:
                        img_att = await _fetch_and_cache_attachment(
                            sig_config.footer_image_path,
                            strict=False,
                            stats={"hits": 0, "misses": 0, "total_bytes": 0}
                        )
                        if img_att:
                            img_att["isInline"] = True
                            img_att["contentId"] = "signature_image"
                            graph_attachments.append(img_att)
                            final_html_body = final_html_body.replace(sig_config.footer_image_url, "cid:signature_image")
                    except Exception as img_err:
                        logger.warning("Failed to fetch signature footer image for inline attachment", error=str(img_err))
                
                final_plain_body = branding_service.render_plain_email(final_html_body)

                has_sep_html = "--" in final_html_body
                has_reg_html = "best regards" in final_html_body.lower() or "regards" in final_html_body.lower()
                has_sig_html = (sig_config.signature_html.lower() in final_html_body.lower()) if sig_config and sig_config.signature_html else False
                logger.info(
                    "Stage: Email Payload Builder (After Rendering HTML)",
                    reply_id=str(request.parent_message_id or "N/A"),
                    reply_body_length=len(final_html_body),
                    contains_separator=has_sep_html,
                    contains_best_regards=has_reg_html,
                    contains_org_signature=has_sig_html
                )

                has_sep_plain = "--" in final_plain_body
                has_reg_plain = "best regards" in final_plain_body.lower() or "regards" in final_plain_body.lower()
                has_sig_plain = (sig_config.signature_html.lower() in final_plain_body.lower()) if sig_config and sig_config.signature_html else False
                logger.info(
                    "Stage: Email Payload Builder (After Rendering Plain Text)",
                    reply_id=str(request.parent_message_id or "N/A"),
                    reply_body_length=len(final_plain_body),
                    contains_separator=has_sep_plain,
                    contains_best_regards=has_reg_plain,
                    contains_org_signature=has_sig_plain
                )

                logger.info("FINAL HTML Email Body to be sent", body_length=len(final_html_body))
                logger.info("FINAL Plain Text Email Body to be sent", body_length=len(final_plain_body))

                _payload = {
                    "message": {
                        "subject": request.subject,
                        "body": {
                            "contentType": "HTML",
                            "content": final_html_body
                        },
                        "toRecipients": [
                            {
                                "emailAddress": {
                                    "address": request.customer_email
                                }
                            }
                        ]
                    },
                    "saveToSentItems": True
                }
                if graph_attachments:
                    _payload["message"]["attachments"] = graph_attachments
                import json
                log_to_request_file(f"Attachment Lifecycle Stage 6 - Final Graph payload immediately before sendMail(): attachments count = {len(graph_attachments)} | filenames = {[a.get('name') for a in graph_attachments if a]}")
                log_to_request_file(f"Graph API payload compiled:\n{json.dumps(_payload, indent=2)}")
        except Exception as e:
            handle_diagnostic_failure("HTML rendering", e, locals())
            await self.session.rollback()
            raise e

        # Resolve parent Graph message ID for threaded reply
        parent_graph_message_id = None
        is_reply_expected = False

        try:
            if request.parent_message_id:
                parent_graph_message_id = request.parent_message_id
                is_reply_expected = True
                log_to_request_file(f"Priority 1: Using parent_message_id directly from request: {parent_graph_message_id}")
            elif request.references or request.in_reply_to:
                is_reply_expected = True
                log_to_request_file("Priority 2: Request is expected to be a threaded reply. Attempting DB lookup...")
                res_parent = await self.session.execute(text("""
                    SELECT graph_message_id 
                    FROM email_log 
                    WHERE organization_id = :org_id 
                      AND direction = 'inbound' 
                      AND (thread_id = :thread_id OR internet_message_id = :references OR internet_message_id = :in_reply_to)
                      AND graph_message_id IS NOT NULL
                    ORDER BY sent_at DESC 
                    LIMIT 1
                """), {
                    "org_id": request.organization_id,
                    "thread_id": request.thread_id,
                    "references": request.references,
                    "in_reply_to": request.in_reply_to
                })
                row_parent = res_parent.fetchone()
                if row_parent:
                    parent_graph_message_id = row_parent[0]
                    log_to_request_file(f"Resolved parent Graph message ID from DB lookup: {parent_graph_message_id}")
                else:
                    log_to_request_file("DB lookup returned no matching parent inbound email.")
            else:
                log_to_request_file("Priority 3: Brand-new outbound message. Proceeding straight to sendMail flow.")
        except Exception as e:
            handle_diagnostic_failure("Parent Message Resolution", e, locals())
            await self.session.rollback()
            raise e

        # Load default CC/BCC/Sender Display Name from organization settings table
        org_cc = []
        org_bcc = []
        sender_display_name = None
        try:
            org_id_str = str(request.organization_id)
            now = time.time()
            if org_id_str in _org_settings_cache and now - _org_settings_cache[org_id_str]["cached_at"] <= CACHE_TTL_SECONDS:
                cached_settings = _org_settings_cache[org_id_str]["data"]
                org_cc = cached_settings["cc"]
                org_bcc = cached_settings["bcc"]
                sender_display_name = cached_settings["sender_display_name"]
            else:
                org_settings_res = await self.session.execute(text("""
                    SELECT cc_emails, bcc_emails, sender_display_name FROM organization_settings WHERE organization_id = :org_id
                """), {"org_id": request.organization_id})
                org_settings_row = org_settings_res.fetchone()
                if org_settings_row:
                    org_cc = org_settings_row[0] or []
                    org_bcc = org_settings_row[1] or []
                    sender_display_name = org_settings_row[2]
                _org_settings_cache[org_id_str] = {
                    "data": {"cc": org_cc, "bcc": org_bcc, "sender_display_name": sender_display_name},
                    "cached_at": now
                }
        except Exception as org_settings_ex:
            logger.warning("Failed to load CC/BCC/Sender Display Name from organization settings", error=str(org_settings_ex))

        primary_to = request.customer_email.strip().lower()

        # Build CC list
        raw_cc_list = list(request.cc_emails or [])
        
        # Load legacy default CC for backward compatibility on replies
        legacy_cc_list = []
        try:
            org_id_str = str(request.organization_id)
            now = time.time()
            if org_id_str in _org_ai_settings_cache and now - _org_ai_settings_cache[org_id_str]["cached_at"] <= CACHE_TTL_SECONDS:
                legacy_cc_list = _org_ai_settings_cache[org_id_str]["data"]
            else:
                settings_res = await self.session.execute(text("""
                    SELECT default_cc_emails FROM organization_ai_settings WHERE organization_id = :org_id
                """), {"org_id": request.organization_id})
                settings_row = settings_res.fetchone()
                if settings_row and settings_row[0]:
                    import json
                    legacy_cc_list = json.loads(settings_row[0]) if isinstance(settings_row[0], str) else settings_row[0]
                _org_ai_settings_cache[org_id_str] = {"data": legacy_cc_list, "cached_at": now}
        except Exception as settings_ex:
            logger.warning("Failed to load default CC emails from AI settings", error=str(settings_ex))

        if is_reply_expected:
            raw_cc_list.extend(legacy_cc_list)

        raw_cc_list.extend(org_cc)

        merged_cc = []
        seen_cc = set()
        for cc in raw_cc_list:
            if cc and cc.strip():
                clean_cc = cc.strip()
                clean_cc_lower = clean_cc.lower()
                if clean_cc_lower != primary_to and clean_cc_lower not in seen_cc:
                    merged_cc.append(clean_cc)
                    seen_cc.add(clean_cc_lower)

        # Build BCC list
        raw_bcc_list = list(request.bcc_emails or [])
        raw_bcc_list.extend(org_bcc)

        merged_bcc = []
        seen_bcc = set()
        for bcc in raw_bcc_list:
            if bcc and bcc.strip():
                clean_bcc = bcc.strip()
                clean_bcc_lower = clean_bcc.lower()
                if (clean_bcc_lower != primary_to and 
                    clean_bcc_lower not in seen_cc and 
                    clean_bcc_lower not in seen_bcc):
                    merged_bcc.append(clean_bcc)
                    seen_bcc.add(clean_bcc_lower)

        # STEP 6: Send Email
        try:
            if is_reply_expected:
                if not parent_graph_message_id:
                    error_msg = "Threaded reply expected but no valid parent Graph message could be resolved."
                    log_to_request_file(f"Delivery Failed: {error_msg}")
                    logger.error(error_msg)
                    raise EmailSendError(error_msg)
                    
                async with StepTracker(6, "Send Threaded Reply"):
                    message_id = await self._send_threaded_reply(
                        request=request,
                        provider=provider,
                        final_html_body=final_html_body,
                        graph_attachments=graph_attachments,
                        parent_message_id=parent_graph_message_id,
                        cc_emails=merged_cc,
                        bcc_emails=merged_bcc,
                        prefix=prefix,
                        sender_display_name=sender_display_name
                    )
            else:
                async with StepTracker(6, "Send Email"):
                    message_id = await self._send_new_email(
                        request=request,
                        provider=provider,
                        final_html_body=final_html_body,
                        graph_attachments=graph_attachments,
                        cc_emails=merged_cc,
                        bcc_emails=merged_bcc,
                        prefix=prefix,
                        sender_display_name=sender_display_name
                    )
            smtp_send_completed = True
            logger.info("EMAIL SEND SUCCESS")
            log_to_request_file(f"Email Send Success: message_id={message_id}")
        except Exception as e:
            handle_diagnostic_failure("Send Email", e, locals())
            if parent_graph_message_id:
                try:
                    await self.session.execute(
                        text("""
                            UPDATE email_log
                            SET delivery_status = 'delivered'
                            WHERE organization_id = :org_id
                              AND direction = 'inbound'
                              AND graph_message_id = :parent_id
                              AND delivery_status = 'queued'
                        """),
                        {"org_id": request.organization_id, "parent_id": parent_graph_message_id}
                    )
                    await self.session.commit()
                except Exception as revert_ex:
                    logger.warning("Failed to revert inbound email delivery_status on error", error=str(revert_ex))
            await self.session.rollback()
            raise e

        # Retrieve true message details from Sent Items dynamically
        true_msg_id = message_id
        true_conv_id = request.conversation_id or request.thread_id
        true_thread_id = request.thread_id or request.conversation_id
        true_internet_id = request.internet_message_id or message_id
        
        if not true_thread_id:
            true_thread_id = message_id
        if not true_conv_id:
            true_conv_id = message_id
            
        true_index = None
        
        try:
            logger.info("Attempting to retrieve sent message metadata from Sent Items folder")
            sent_meta = await provider.get_sent_metadata(
                org_id=request.organization_id,
                subject=request.subject,
                to_email=request.customer_email,
                db_session=self.session
            )
            if sent_meta.get("retrieval_success"):
                true_msg_id = sent_meta.get("id") or true_msg_id
                true_conv_id = sent_meta.get("conversation_id") or true_conv_id
                true_thread_id = sent_meta.get("conversation_id") or true_thread_id
                true_internet_id = sent_meta.get("internet_message_id") or true_internet_id
                true_index = sent_meta.get("conversation_index")
                
                logger.info(
                    "Outbound Email Audit - Graph Message Persisted",
                    conversationId=true_conv_id,
                    internetMessageId=true_internet_id,
                    id=true_msg_id,
                    conversationIndex=true_index,
                    retrieval_success=True,
                    retrieval_time_ms=sent_meta.get("retrieval_time_ms")
                )
            else:
                logger.warning(
                    "Outbound Email Audit - Sent Items retrieval failed or timed out",
                    retrieval_success=False,
                    retrieval_time_ms=sent_meta.get("retrieval_time_ms", 0)
                )
        except Exception as meta_ex:
            logger.warning("Failed to query Sent Items metadata", error=str(meta_ex), retrieval_success=False)

        # STEP 7: Save Email History
        logger.info("INSERT email_log")
        log_to_request_file("Executing: INSERT email_log")
        try:
            async with StepTracker(7, "Save Email History"):
                email_log_id = uuid.uuid4()
                has_attachment = len(request.attachments) > 0 if request.attachments else False

                # Resolve campaign_id and email_type dynamically from current scheduler state
                email_type_val = "engagement"
                campaign_id_val = None
                if customer_id:
                    # 1. Check if there is an active/pending follow-up schedule item for this customer
                    step_res = await self.session.execute(
                        text("""
                            SELECT campaign_id 
                            FROM follow_up_schedule 
                            WHERE customer_id = :cust_id 
                              AND organization_id = :org_id 
                              AND status::text IN ('pending', 'scheduled', 'paused')
                            ORDER BY step_number ASC 
                            LIMIT 1
                        """),
                        {"cust_id": customer_id, "org_id": request.organization_id}
                    )
                    step_row = step_res.fetchone()
                    if step_row:
                        email_type_val = "followup"
                        campaign_id_val = step_row[0]
                    
                    # 2. Fallback to active campaign enrollment
                    if not campaign_id_val:
                        enroll_res = await self.session.execute(
                            text("""
                                SELECT campaign_id 
                                FROM campaign_enrollments 
                                WHERE customer_id = :cust_id 
                                  AND organization_id = :org_id 
                                  AND enrollment_status = 'active'
                                LIMIT 1
                            """),
                            {"cust_id": customer_id, "org_id": request.organization_id}
                        )
                        enroll_row = enroll_res.fetchone()
                        if enroll_row:
                            campaign_id_val = enroll_row[0]

                await self.session.execute(
                    text("""
                        INSERT INTO email_log (
                            id, organization_id, customer_id, campaign_id, direction, 
                            email_type, subject, body, has_attachment, sent_at, delivery_status, graph_message_id,
                            conversation_id, thread_id, internet_message_id, "references", in_reply_to, created_at
                        ) VALUES (
                            :id, :org_id, :customer_id, :campaign_id, 'outbound', 
                            CAST(:email_type AS public.email_type), :subject, :body, :has_attachment, NOW(), 'sent', :graph_message_id,
                            :conversation_id, :thread_id, :internet_message_id, :references, :in_reply_to, NOW()
                        )
                    """),
                    {
                        "id": email_log_id,
                        "org_id": request.organization_id,
                        "customer_id": customer_id,
                        "campaign_id": campaign_id_val,
                        "email_type": email_type_val,
                        "subject": request.subject,
                        "body": final_html_body,
                        "has_attachment": has_attachment,
                        "graph_message_id": true_msg_id,
                        "conversation_id": true_conv_id,
                        "thread_id": true_thread_id,
                        "internet_message_id": true_internet_id,
                        "references": request.references,
                        "in_reply_to": request.in_reply_to
                    }
                )
                logger.info("FLUSH")
                await self.session.flush()
                email_log_insert_completed = True
                log_to_request_file("Email log insert result: Success")
        except Exception as e:
            handle_diagnostic_failure("Save Email History", e, locals())
            await self.session.rollback()
            raise e

        # STEP 8: Commit
        logger.info("COMMIT")
        log_to_request_file("Executing: COMMIT")
        try:
            async with StepTracker(8, "Commit"):
                await self.session.commit()
                log_to_request_file("Commit result: Success")
        except Exception as e:
            handle_diagnostic_failure("Commit", e, locals())
            await self.session.rollback()
            raise e

        # STEP 9: Verify Response Serialization
        try:
            response = EmailResponse(
                success=True,
                message_id=message_id,
                sent_at=datetime.now(timezone.utc).isoformat(),
            )
            logger.info(response.model_dump())
            log_to_request_file(f"Response returned to FastAPI:\n{response.model_dump_json(indent=2)}")
            print(f"Returning EmailResponse success={response.success} message_id={response.message_id} sent_at={response.sent_at}", flush=True)
            return response
        except Exception as serialization_error:
            handle_diagnostic_failure("Response Serialization", serialization_error, locals())
            raise serialization_error
