import base64
import time
import mimetypes
import os
import httpx
import asyncio
import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

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


async def _fetch_and_cache_attachment(org_id: uuid.UUID, storage_path: str, strict: bool, stats: dict) -> Optional[dict]:
    from app.core.debug_logger import log_to_request_file
    import uuid
    _clean_old_cache_entries()

    # Partitioned key for tenant safety
    cache_key = f"{org_id}:{storage_path}"

    # Check cache
    if cache_key in _attachment_cache:
        entry = _attachment_cache[cache_key]
        if time.time() - entry["cached_at"] <= CACHE_TTL_SECONDS:
            logger.info("Attachment Cache HIT", storage_path=storage_path, org_id=str(org_id))
            log_to_request_file(f"Attachment Cache HIT for org_id: {org_id}, storage_path: {storage_path}")
            stats["hits"] += 1
            return {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": entry["file_name"],
                "contentType": entry["content_type"],
                "contentBytes": entry["content_bytes"]
            }

    logger.info("Attachment Cache MISS", storage_path=storage_path, org_id=str(org_id))
    log_to_request_file(f"Attachment Cache MISS. Commencing download for org_id: {org_id}, storage_path: {storage_path}")
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
            _attachment_cache[cache_key] = {
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
        logger.error("Failed to download attachment", storage_path=storage_path, org_id=str(org_id), error=str(e))
        log_to_request_file(f"Failed to download or convert attachment from storage_path '{storage_path}'. Error: {str(e)}")
        if strict:
            raise EmailSendError(f"Attachment download failed for {storage_path}: {str(e)}")
        logger.warning("Skipping failed attachment (strict_attachment_mode is False)", storage_path=storage_path, error=str(e))
        return None


class EmailService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.provider_factory = EmailProviderFactory(session)

    @staticmethod
    async def _is_email_suppressed(org_id, email_address: str, db: AsyncSession) -> bool:
        """
        Phase 2B — Check whether an email address has a confirmed hard-bounce suppression
        record for this organisation.

        Uses the composite index idx_email_suppressions_lookup(organization_id, lower(email_address))
        for an O(1) lookup.  Returns True if the address is suppressed and no email should
        be sent; False otherwise.

        This check is intentionally lightweight: a single SELECT with LIMIT 1.  It uses a
        fresh DB query (not a cache) so suppression records inserted by BounceDetectionService
        are immediately honoured without a server restart.
        """
        try:
            res = await db.execute(
                text("""
                    SELECT 1
                    FROM email_suppressions
                    WHERE organization_id = :org_id
                      AND lower(email_address) = lower(:email)
                    LIMIT 1
                """),
                {"org_id": org_id, "email": email_address},
            )
            return res.fetchone() is not None
        except Exception as lookup_err:
            # Safety: if the suppression table is unavailable, fail open (allow send)
            # to avoid blocking legitimate email during an infrastructure incident.
            logger.warning(
                "Phase 2B: Suppression lookup failed; allowing send (fail-open)",
                org_id=str(org_id),
                email=email_address,
                error=str(lookup_err),
            )
            return False


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
        # NOTE: db_session=None forces provider to use pre_resolved_token/settings.
        # Transaction A has already closed the session and resolved credentials.
        return await provider.send_email(
            org_id=request.organization_id,
            recipient=request.customer_email,
            subject=request.subject,
            html_body=final_html_body,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            attachments=graph_attachments,
            db_session=None,
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
        # NOTE: db_session=None forces provider to use pre_resolved_token/settings.
        # Transaction A has already closed the session and resolved credentials.
        return await provider.send_reply(
            org_id=request.organization_id,
            parent_message_id=parent_message_id,
            html_body=final_html_body,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            attachments=graph_attachments,
            db_session=None,
            sender_display_name=sender_display_name,
            subject=request.subject
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

        # Resolve customer_email if missing or empty
        if not request.customer_email and request.customer_id:
            cust_res = await self.session.execute(
                text("SELECT contact_email FROM customers WHERE id = :cid AND organization_id = :oid"),
                {"cid": request.customer_id, "oid": request.organization_id}
            )
            cust_row = cust_res.fetchone()
            if cust_row and cust_row[0]:
                request.customer_email = cust_row[0]
                logger.info("Resolved customer_email from customer_id", customer_id=str(request.customer_id), email=request.customer_email)

        recipient = request.customer_email
        subject = request.subject

        # ─────────────────────────────────────────────────────────────────────
        # PHASE 2B — HARD-BOUNCE SUPPRESSION GUARD
        # This runs before Transaction A, before any SMTP call, before any
        # attachment download, and before any expensive metadata reads.
        # If the recipient is suppressed the method returns immediately with
        # skipped=True.  The caller (campaign / follow-up engine) must treat
        # this as an intentional, non-retryable skip — NOT as a send failure.
        # ─────────────────────────────────────────────────────────────────────
        if recipient:
            suppressed = await EmailService._is_email_suppressed(
                org_id=request.organization_id,
                email_address=recipient,
                db=self.session,
            )
            if suppressed:
                log_msg = (
                    f"[Phase 2B] Hard-bounce suppression: skipping send to '{recipient}' "
                    f"for org {request.organization_id}. No SMTP call will be made."
                )
                logger.warning(log_msg)
                log_to_request_file(log_msg)
                await self.session.close()
                return EmailResponse(
                    success=True,
                    skipped=True,
                    skip_reason="hard_bounce_suppressed",
                    message_id=None,
                    sent_at=None,
                )

        if request.parent_message_id or request.in_reply_to or request.references:
            import re
            clean_sub = re.sub(r'^(?:(re|fwd|reply):\s*)+', '', subject, flags=re.I).strip()
            request.subject = f"Re: {clean_sub}"
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

        # ==========================================
        # TRANSACTION A: READ METADATA & LOCKS
        # ==========================================
        customer_id = None
        contact_name = "Team"
        company_name = "your company"
        mailbox_email = "N/A"
        org_cc = []
        org_bcc = []
        sender_display_name = None
        legacy_cc_list = []
        parent_graph_message_id = None
        is_reply_expected = False
        resolved_attachments_meta = []
        provider_type = "microsoft" # default
        sig_config = None

        try:
            # 1. Customer lookup
            async with StepTracker(2, "Customer lookup"):
                cust_res = await self.session.execute(
                    text("SELECT id, contact_name, company_name FROM customers WHERE contact_email = :email AND organization_id = :org_id"),
                    {"email": request.customer_email, "org_id": request.organization_id}
                )
                cust_row = cust_res.fetchone()
                if not cust_row:
                    raise Exception("SaaS Multi-tenant verification failed: Customer tenant mismatch.")
                customer_id = str(cust_row[0])
                if cust_row[1]:
                    contact_name = str(cust_row[1])
                company_name = str(cust_row[2]) if cust_row[2] else "your company"
                log_to_request_file(f"Customer lookup result: ID={customer_id}, contact_name={contact_name}, company_name={company_name}")

                # Perform campaign email personalization (support canonical {{contact_name}} and legacy {contact_name})
                resolved_contact_name = contact_name
                if not resolved_contact_name or resolved_contact_name.strip().lower() in ["", "team", "unknown contact", "valued customer", "unknown"]:
                    resolved_contact_name = "there"

                if request.subject:
                    request.subject = request.subject.replace("{{contact_name}}", resolved_contact_name).replace("{contact_name}", resolved_contact_name)
                    request.subject = request.subject.replace("{{customer_company_name}}", company_name).replace("{customer_company_name}", company_name)
                if request.html_body:
                    request.html_body = request.html_body.replace("{{contact_name}}", resolved_contact_name).replace("{contact_name}", resolved_contact_name)
                    request.html_body = request.html_body.replace("{{customer_company_name}}", company_name).replace("{customer_company_name}", company_name)

            # 2. Idempotency Check (Local DB)
            if request.marketing_campaign_id and customer_id:
                dup_res = await self.session.execute(
                    text("SELECT id FROM email_log WHERE marketing_campaign_id = :camp_id AND customer_id = :cust_id LIMIT 1"),
                    {"camp_id": request.marketing_campaign_id, "cust_id": customer_id}
                )
                if dup_res.fetchone():
                    logger.warning("Idempotency Blocked: Email already sent to customer for this campaign", campaign_id=str(request.marketing_campaign_id), customer_id=customer_id)
                    await self.session.close()
                    return EmailResponse(
                        success=True,
                        message_id="IDEMPOTENT_SKIP",
                        sent_at=datetime.now(timezone.utc).isoformat()
                    )

            # 3. Mailbox lookup
            async with StepTracker(3, "Mailbox lookup"):
                org_id_str = str(request.organization_id)
                now = time.time()
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

            # 4. Resolve provider type
            prov_res = await self.session.execute(
                text("SELECT provider FROM tenant_integrations WHERE organization_id = :org_id"),
                {"org_id": request.organization_id}
            )
            prov_row = prov_res.fetchone()
            if prov_row:
                provider_type = prov_row[0]

            # 5. CC/BCC Organization Settings
            org_settings_res = await self.session.execute(text("""
                SELECT cc_emails, bcc_emails, sender_display_name FROM organization_settings WHERE organization_id = :org_id
            """), {"org_id": request.organization_id})
            org_settings_row = org_settings_res.fetchone()
            if org_settings_row:
                org_cc = org_settings_row[0] or []
                org_bcc = org_settings_row[1] or []
                sender_display_name = org_settings_row[2]

            # 6. Legacy CC Settings
            settings_res = await self.session.execute(text("""
                SELECT default_cc_emails FROM organization_ai_settings WHERE organization_id = :org_id
            """), {"org_id": request.organization_id})
            settings_row = settings_res.fetchone()
            if settings_row and settings_row[0]:
                import json
                legacy_cc_list = json.loads(settings_row[0]) if isinstance(settings_row[0], str) else settings_row[0]

            # 7. Parent reply resolution
            if request.parent_message_id:
                parent_graph_message_id = request.parent_message_id
                is_reply_expected = True
                
                # Fetch parent details to populate references and in_reply_to (supports both inbound and outbound parents)
                res_headers = await self.session.execute(text("""
                    SELECT internet_message_id, "references"
                    FROM email_log
                    WHERE (graph_message_id = :p_id OR id::text = :p_id)
                      AND organization_id = :org_id
                    LIMIT 1
                """), {
                    "p_id": parent_graph_message_id,
                    "org_id": request.organization_id
                })
                row_headers = res_headers.fetchone()
                if row_headers:
                    parent_internet_id, parent_refs = row_headers
                    if parent_internet_id:
                        if not request.in_reply_to:
                            request.in_reply_to = parent_internet_id
                        if not request.references:
                            refs_list = []
                            if parent_refs:
                                refs_list = parent_refs.split()
                            refs_list.append(parent_internet_id)
                            request.references = " ".join(refs_list)
            elif request.references or request.in_reply_to:
                is_reply_expected = True
                res_parent = await self.session.execute(text("""
                    SELECT graph_message_id 
                    FROM email_log 
                    WHERE organization_id = :org_id 
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
                    # Fetch details to populate references and in_reply_to if missing
                    res_headers = await self.session.execute(text("""
                        SELECT internet_message_id, "references"
                        FROM email_log
                        WHERE graph_message_id = :p_id
                          AND organization_id = :org_id
                        LIMIT 1
                    """), {
                        "p_id": parent_graph_message_id,
                        "org_id": request.organization_id
                    })
                    row_headers = res_headers.fetchone()
                    if row_headers:
                        parent_internet_id, parent_refs = row_headers
                        if parent_internet_id:
                            if not request.in_reply_to:
                                request.in_reply_to = parent_internet_id
                            if not request.references:
                                refs_list = []
                                if parent_refs:
                                    refs_list = parent_refs.split()
                                refs_list.append(parent_internet_id)
                                request.references = " ".join(refs_list)
            elif getattr(request, "marketing_campaign_id", None) is None and customer_id:
                # Controlled fallback for follow-up sends arriving without parent metadata:
                # Look up the customer's most recent outbound engagement or follow-up email for this tenant
                res_outbound_parent = await self.session.execute(text("""
                    SELECT graph_message_id, internet_message_id, "references"
                    FROM email_log
                    WHERE organization_id = :org_id
                      AND customer_id = :cust_id
                      AND direction = 'outbound'
                      AND marketing_campaign_id IS NULL
                      AND graph_message_id IS NOT NULL
                    ORDER BY sent_at DESC
                    LIMIT 1
                """), {
                    "org_id": request.organization_id,
                    "cust_id": customer_id
                })
                row_out = res_outbound_parent.fetchone()
                if row_out:
                    parent_graph_message_id = row_out[0]
                    parent_internet_id, parent_refs = row_out[1], row_out[2]
                    is_reply_expected = True
                    if parent_internet_id:
                        if not request.in_reply_to:
                            request.in_reply_to = parent_internet_id
                        if not request.references:
                            refs_list = []
                            if parent_refs:
                                refs_list = parent_refs.split()
                            refs_list.append(parent_internet_id)
                            request.references = " ".join(refs_list)
                    logger.info("Auto-resolved parent email for follow-up send", parent_graph_id=parent_graph_message_id, in_reply_to=request.in_reply_to)


            # 8. Attachment storage path resolution
            if request.attachments:
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
                    resolved_attachments_meta.append({
                        "id": att.id,
                        "storage_path": storage_path,
                        "filename": att.filename
                    })

            # 9. Get branding signatures
            sig_config = await branding_service.get_signature(request.organization_id)

            # 10. Pre-resolve provider credentials/settings in Transaction A
            access_token = None
            smtp_settings = None
            if provider_type == "microsoft":
                from app.services.token_service import TokenService
                token_service = TokenService(self.session)
                access_token = await token_service.get_valid_access_token(request.organization_id)
                log_to_request_file("Successfully pre-resolved Microsoft Graph OAuth token.")
            elif provider_type == "smtp":
                from app.core.encryption import decrypt_token
                smtp_res = await self.session.execute(
                    text("""
                        SELECT mailbox_email, auth_username, encrypted_password, 
                               smtp_host, smtp_port, smtp_security 
                        FROM tenant_integrations 
                        WHERE organization_id = :org_id
                    """),
                    {"org_id": request.organization_id}
                )
                smtp_row = smtp_res.fetchone()
                if not smtp_row:
                    raise EmailSendError("No SMTP integration settings found for organization.")
                
                mailbox_email_smtp, auth_username, encrypted_password, smtp_host, smtp_port, smtp_security = smtp_row
                if not smtp_host or not smtp_port or not encrypted_password:
                    raise EmailSendError("SMTP connection settings are incomplete.")
                
                password = decrypt_token(encrypted_password)
                username = auth_username if auth_username else mailbox_email_smtp
                
                smtp_settings = {
                    "mailbox_email": mailbox_email_smtp,
                    "username": username,
                    "password": password,
                    "host": smtp_host,
                    "port": smtp_port,
                    "security": smtp_security
                }
                log_to_request_file("Successfully pre-resolved SMTP server connection settings.")

            # ==========================================
            # COMMIT & RELEASE CONNECTION FOR TRANSACTION A
            # ==========================================
            await self.session.commit()
            await self.session.close()
            log_to_request_file("DB Connection Audit: Transaction A successfully committed & session connection released to pool.")

        except Exception as e:
            handle_diagnostic_failure("Transaction A reads", e, locals())
            await self.session.rollback()
            await self.session.close()
            raise e

        # ==========================================
        # EXTERNAL NETWORK OPERATIONS (No DB connection held)
        # ==========================================
        
        # 1. Download attachments from Supabase storage
        graph_attachments = []
        try:
            async with StepTracker(4, "Download attachment"):
                if resolved_attachments_meta:
                    stats = {"hits": 0, "misses": 0, "total_bytes": 0}
                    tasks = []
                    for att_meta in resolved_attachments_meta:
                        sp = att_meta["storage_path"]
                        if sp:
                            tasks.append(
                                _fetch_and_cache_attachment(
                                    request.organization_id,
                                    sp,
                                    request.strict_attachment_mode,
                                    stats
                                )
                            )
                        elif request.strict_attachment_mode:
                            raise EmailSendError(f"Attachment storage path could not be resolved for ID: {att_meta['id']}")
                    
                    if tasks:
                        results = await asyncio.gather(*tasks)
                        graph_attachments = [r for r in results if r is not None]
                attachment_insert_completed = True
        except Exception as e:
            handle_diagnostic_failure("Download attachment", e, locals())
            raise e

        # Instantiate provider factory with a temporary scoped session
        provider = None
        try:
            async with AsyncSessionLocal() as factory_session:
                factory = EmailProviderFactory(factory_session)
                provider = await factory.get_provider_for_tenant(request.organization_id)
                # Sever DB session reference to prevent pool checkout/leaks during slow provider network requests
                provider.db_session = None
                if hasattr(provider, "db"):
                    provider.db = None
            
            # Attach pre-resolved credentials/settings to the provider instance
            if provider_type == "microsoft" and access_token:
                provider.pre_resolved_token = access_token
            elif provider_type == "smtp" and smtp_settings:
                provider.pre_resolved_settings = smtp_settings
            log_to_request_file("DB Connection Audit: Pre-resolved credentials successfully attached to the email provider.")
        except Exception as e:
            handle_diagnostic_failure("Provider Resolution", e, locals())
            raise e

        # 2. Render HTML & Plain Text
        try:
            async with StepTracker(5, "Render HTML and Plain Text"):
                cleaned_body = branding_service.clean_and_format_body(request.html_body)
                
                final_html_body = branding_service.render_html_email(
                    body_content=cleaned_body,
                    signature_html=sig_config.signature_html if sig_config else None,
                    banner_url=sig_config.footer_image_url if sig_config else None
                )
                
                # Check if footer image exists and append it as inline attachment
                if sig_config and sig_config.footer_image_path and sig_config.footer_image_url:
                    try:
                        img_att = await _fetch_and_cache_attachment(
                            request.organization_id,
                            sig_config.footer_image_path,
                            strict=False,
                            stats={"hits": 0, "misses": 0, "total_bytes": 0}
                        )
                        if img_att:
                            img_att["isInline"] = True
                            img_att["contentId"] = "signature_image"
                            graph_attachments.append(img_att)
                            # Perform exact replacement of signed URL with cid:signature_image (idempotent, only if signed URL is present)
                            if sig_config.footer_image_url in final_html_body:
                                final_html_body = final_html_body.replace(sig_config.footer_image_url, "cid:signature_image")
                    except Exception as img_err:
                        logger.warning("Failed to fetch signature footer image for inline attachment", error=str(img_err))
                
                final_plain_body = branding_service.render_plain_email(final_html_body)
        except Exception as e:
            handle_diagnostic_failure("HTML rendering", e, locals())
            raise e

        # CC and BCC lists compilation
        primary_to = request.customer_email.strip().lower()
        raw_cc_list = list(request.cc_emails or [])
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

        # 3. Provider Check (Idempotency against MS Graph)
        # Prior to sending, check if Outlook Sent Items already holds this message to protect crash recovery path
        # NOTE: db_session=None forces provider to use pre_resolved_token/settings (no DB connection held).
        try:
            sent_meta_pre = await provider.get_sent_metadata(
                org_id=request.organization_id,
                subject=request.subject,
                to_email=request.customer_email,
                db_session=None
            )
            if sent_meta_pre.get("retrieval_success"):
                logger.warning("Microsoft Graph Sent Items HIT: Outbound mail was already successfully accepted.", customer=request.customer_email, subject=request.subject)
                # Retroactively write email log inside Transaction B
                async with AsyncSessionLocal() as write_db:
                    email_log_id = uuid.uuid4()
                    has_attachment = len(request.attachments) > 0 if request.attachments else False
                    email_type_val = "campaign" if getattr(request, "marketing_campaign_id", None) else "engagement"
                    
                    await write_db.execute(
                        text("""
                            INSERT INTO email_log (
                                id, organization_id, customer_id, campaign_id, marketing_campaign_id, direction, 
                                email_type, subject, body, has_attachment, sent_at, delivery_status, graph_message_id,
                                conversation_id, thread_id, internet_message_id, "references", in_reply_to, created_at
                            ) VALUES (
                                :id, :org_id, :customer_id, :campaign_id, :mkt_campaign_id, 'outbound', 
                                CAST(:email_type AS public.email_type), :subject, :body, :has_attachment, NOW(), 'sent', :graph_message_id,
                                :conversation_id, :thread_id, :internet_message_id, :references, :in_reply_to, NOW()
                            ) ON CONFLICT (marketing_campaign_id, customer_id) WHERE marketing_campaign_id IS NOT NULL DO NOTHING
                        """),
                        {
                            "id": email_log_id,
                            "org_id": request.organization_id,
                            "customer_id": customer_id,
                            "campaign_id": None,
                            "mkt_campaign_id": getattr(request, "marketing_campaign_id", None),
                            "email_type": email_type_val,
                            "subject": request.subject,
                            "body": final_html_body,
                            "has_attachment": has_attachment,
                            "graph_message_id": sent_meta_pre.get("id"),
                            "conversation_id": sent_meta_pre.get("conversation_id"),
                            "thread_id": sent_meta_pre.get("conversation_id"),
                            "internet_message_id": sent_meta_pre.get("internet_message_id"),
                            "references": request.references,
                            "in_reply_to": request.in_reply_to
                        }
                    )
                    await write_db.commit()
                
                return EmailResponse(
                    success=True,
                    message_id=sent_meta_pre.get("id"),
                    sent_at=datetime.now(timezone.utc).isoformat()
                )
        except Exception as provider_recovery_err:
            logger.warning("Provider recovery sentitems query failed or returned empty", error=str(provider_recovery_err))

        # 4. Dispatch Email via Provider
        message_id = "N/A"
        try:
            if is_reply_expected:
                if not parent_graph_message_id:
                    error_msg = "Threaded reply expected but no valid parent Graph message could be resolved."
                    log_to_request_file(f"Delivery Failed: {error_msg}")
                    logger.error(error_msg)
                    raise EmailSendError(error_msg)
                    
                async with StepTracker(6, "Send Threaded Reply"):
                    # No DB session here. Provider uses pre_resolved_token/settings.
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
                    # No DB session here. Provider uses pre_resolved_token/settings.
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
            raise e

        # ==========================================
        # TRANSACTION B: LOG WRITE & OUTCOME RECORDING
        # ==========================================
        true_msg_id = message_id
        true_conv_id = request.conversation_id or request.thread_id
        true_thread_id = request.thread_id or request.conversation_id
        true_internet_id = request.internet_message_id or message_id
        
        if not true_thread_id:
            true_thread_id = message_id
        if not true_conv_id:
            true_conv_id = message_id

        # Query Sent Items folder for metadata — no DB session needed (uses pre_resolved_token).
        # Optimization: Only query Sent Items for Microsoft Graph provider where thread IDs are required.
        # SMTP already has exact Message-ID and requires zero blocking WAN folder polling.
        if provider_type == "microsoft":
            try:
                sent_meta = await provider.get_sent_metadata(
                    org_id=request.organization_id,
                    subject=request.subject,
                    to_email=request.customer_email,
                    db_session=None
                )
                if sent_meta.get("retrieval_success"):
                    true_msg_id = sent_meta.get("id") or true_msg_id
                    true_conv_id = sent_meta.get("conversation_id") or true_conv_id
                    true_thread_id = sent_meta.get("conversation_id") or true_thread_id
                    true_internet_id = sent_meta.get("internet_message_id") or true_internet_id
            except Exception as meta_ex:
                logger.warning("Failed to query Sent Items metadata", error=str(meta_ex))

        # Insert email_log inside Transaction B
        try:
            async with AsyncSessionLocal() as write_db:
                email_log_id = uuid.uuid4()
                has_attachment = len(request.attachments) > 0 if request.attachments else False
                email_type_val = "campaign" if getattr(request, "marketing_campaign_id", None) else "engagement"
                
                # ON CONFLICT DO NOTHING ensures database-level uniqueness locks
                await write_db.execute(
                    text("""
                        INSERT INTO email_log (
                            id, organization_id, customer_id, campaign_id, marketing_campaign_id, direction, 
                            email_type, subject, body, has_attachment, sent_at, delivery_status, graph_message_id,
                            conversation_id, thread_id, internet_message_id, "references", in_reply_to, created_at
                        ) VALUES (
                            :id, :org_id, :customer_id, :campaign_id, :mkt_campaign_id, 'outbound', 
                            CAST(:email_type AS public.email_type), :subject, :body, :has_attachment, NOW(), 'sent', :graph_message_id,
                            :conversation_id, :thread_id, :internet_message_id, :references, :in_reply_to, NOW()
                        ) ON CONFLICT (marketing_campaign_id, customer_id) WHERE marketing_campaign_id IS NOT NULL DO NOTHING
                    """),
                    {
                        "id": email_log_id,
                        "org_id": request.organization_id,
                        "customer_id": customer_id,
                        "campaign_id": None,
                        "mkt_campaign_id": getattr(request, "marketing_campaign_id", None),
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
                await write_db.commit()
                email_log_insert_completed = True
        except Exception as e:
            handle_diagnostic_failure("Save Email History inside Transaction B", e, locals())
            raise e

        try:
            response = EmailResponse(
                success=True,
                message_id=message_id,
                sent_at=datetime.now(timezone.utc).isoformat(),
            )
            logger.info(response.model_dump())
            log_to_request_file(f"Response returned to FastAPI:\n{response.model_dump_json(indent=2)}")
            return response
        except Exception as serialization_error:
            handle_diagnostic_failure("Response Serialization", serialization_error, locals())
            raise serialization_error
