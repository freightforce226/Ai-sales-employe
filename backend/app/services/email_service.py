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

from app.clients.microsoft_graph_client import MicrosoftGraphClient
from app.core.exceptions import EmailSendError, GraphApiError, TenantNotFoundError, TokenRefreshError
from app.core.logging import get_logger
from app.schemas.email import EmailRequest, EmailResponse
from app.services.token_service import TokenService
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

# Execution-scoped cache dictionary: key = storage_path
_attachment_cache = {}
CACHE_TTL_SECONDS = 300


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
        self.token_service = TokenService(session)
        self.graph_client = MicrosoftGraphClient()

    async def _send_new_email(
        self,
        request: EmailRequest,
        access_token: str,
        final_html_body: str,
        graph_attachments: list,
        prefix: str
    ) -> str:
        from app.core.debug_logger import log_to_request_file
        log_to_request_file("Executing Scenario 2: Standard Outbound Email (sendMail)")
        return await self.graph_client.send_email(
            access_token=access_token,
            subject=request.subject,
            html_content=final_html_body,
            to_email=request.customer_email,
            attachments=graph_attachments
        )

    async def _send_threaded_reply(
        self,
        request: EmailRequest,
        access_token: str,
        final_html_body: str,
        graph_attachments: list,
        parent_message_id: str,
        cc_list: list,
        prefix: str
    ) -> str:
        from app.core.debug_logger import log_to_request_file
        log_to_request_file(f"Executing Scenario 1: Threaded Reply on parent message ID {parent_message_id}")
        draft_id = None
        max_attempts = 3
        last_err = None
        
        for attempt in range(max_attempts):
            try:
                # 1. Create draft reply
                draft_id = await self.graph_client.create_reply_draft(access_token, parent_message_id)
                
                # 2. Update draft body and CC list
                await self.graph_client.update_message_draft(
                    access_token=access_token,
                    draft_id=draft_id,
                    html_content=final_html_body,
                    cc_emails=cc_list
                )
                
                # 3. Add attachments if present
                if graph_attachments:
                    for attachment in graph_attachments:
                        attach_url = f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}/attachments"
                        headers_att = {
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        }
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            res_att = await client.post(attach_url, headers=headers_att, json=attachment)
                            if res_att.status_code not in (200, 201):
                                raise Exception(f"Failed to upload attachment: {res_att.text}")
                                
                # 4. Send draft reply
                await self.graph_client.send_draft(access_token, draft_id)
                
                logger.info("Successfully executed Graph reply flow")
                log_to_request_file("Successfully executed Graph reply flow")
                return draft_id
            except Exception as attempt_err:
                last_err = attempt_err
                logger.warning(f"Threaded reply attempt {attempt+1} failed: {str(attempt_err)}")
                log_to_request_file(f"Threaded reply attempt {attempt+1} failed: {str(attempt_err)}")
                
                # Cleanup draft if created
                if draft_id:
                    try:
                        await self.graph_client.delete_draft(access_token, draft_id)
                        log_to_request_file(f"Successfully cleaned up draft: {draft_id}")
                    except Exception as del_err:
                        logger.warning("Failed to delete failed draft during cleanup", error=str(del_err))
                    draft_id = None
                    
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2 ** attempt)
        else:
            logger.error("All threaded reply attempts failed. Aborting dispatch.")
            raise last_err

    async def send_tenant_email(self, request: EmailRequest) -> EmailResponse:
        import traceback
        import uuid
        from app.core.logging import request_id_var
        from app.core.debug_logger import log_to_request_file
        from app.services.email_branding_service import EmailBrandingService
        
        req_id = request_id_var.get() or "UNKNOWN"
        prefix = f"[REQ-{req_id}] "

        log_to_request_file(f"Validated EmailRequest:\n{request.model_dump_json(indent=2)}")

        branding_service = EmailBrandingService(self.session)

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
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Customer lookup: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("FAILED SELECT customer")
            await self.session.rollback()
            raise e

        # STEP 3: Mailbox lookup
        logger.info("SELECT tenant_integrations")
        log_to_request_file("Executing: SELECT tenant_integrations")
        mailbox_email = "N/A"
        try:
            async with StepTracker(3, "Mailbox lookup"):
                tok_res = await self.session.execute(
                    text("SELECT mailbox_email FROM tenant_integrations WHERE organization_id = :org_id"),
                    {"org_id": request.organization_id}
                )
                row = tok_res.fetchone()
                if row:
                    mailbox_email = row[0]
                log_to_request_file(f"Mailbox lookup result: mailbox_email={mailbox_email}")
        except Exception as e:
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Mailbox lookup: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("FAILED SELECT tenant_integrations")
            await self.session.rollback()
            raise e

        # STEP 4: Download attachment
        graph_attachments = []
        log_to_request_file(f"Attachment Lifecycle Stage 3 - Email request object count: {len(request.attachments)} | Metadata: {request.attachments}")
        try:
            async with StepTracker(4, "Download attachment"):
                if request.attachments:
                    stats = {"hits": 0, "misses": 0, "total_bytes": 0}
                    tasks = [
                        _fetch_and_cache_attachment(
                            att.storage_path,
                            request.strict_attachment_mode,
                            stats
                        )
                        for att in request.attachments
                    ]
                    results = await asyncio.gather(*tasks)
                    graph_attachments = [r for r in results if r is not None]
                log_to_request_file(f"Attachment download result: {len(graph_attachments)} attachments downloaded.")
        except Exception as e:
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Download attachment: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("ORIGINAL ERROR")
            await self.session.rollback()
            raise e

        # Load token
        log_to_request_file("Token refresh: Start")
        try:
            access_token = await self.token_service.get_valid_access_token(request.organization_id)
            log_to_request_file("Token refresh result: Success")
        except Exception as e:
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Token refresh: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("ORIGINAL ERROR")
            await self.session.rollback()
            raise e

        # Load Signature Settings
        try:
            sig_config = await branding_service.get_signature(request.organization_id)
        except Exception as e:
            logger.exception("Failed loading signature settings")
            await self.session.rollback()
            raise e

        # STEP 5: Render HTML and Plain Text
        try:
            async with StepTracker(5, "Render HTML and Plain Text"):
                # Clean body content
                cleaned_body = branding_service.clean_and_format_body(request.html_body)
                
                # Render final HTML including sanitized signature and optional footer banner
                final_html_body = branding_service.render_html_email(
                    body_content=cleaned_body,
                    signature_html=sig_config.signature_html,
                    banner_url=sig_config.footer_image_url
                )
                
                # Render plain-text fallback dynamically on-the-fly
                final_plain_body = branding_service.render_plain_email(final_html_body)

                # Structuring Graph API payload variables
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
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Upload attachment: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("ORIGINAL ERROR")
            await self.session.rollback()
            raise e

        # Resolve parent Graph message ID for threaded reply
        parent_graph_message_id = None
        is_reply_expected = False

        if request.parent_message_id:
            parent_graph_message_id = request.parent_message_id
            is_reply_expected = True
            log_to_request_file(f"Priority 1: Using parent_message_id directly from request: {parent_graph_message_id}")
        elif request.references or request.in_reply_to:
            # Priority 2: Expected to be a reply, parent_message_id missing -> lookup from DB
            is_reply_expected = True
            log_to_request_file("Priority 2: Request is expected to be a threaded reply. Attempting DB lookup...")
            try:
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
            except Exception as lookup_ex:
                logger.warning("Failed to lookup parent Graph message ID in DB", error=str(lookup_ex))
        else:
            # Priority 3: Brand-new outbound message -> Go straight to sendMail flow without DB query
            log_to_request_file("Priority 3: Brand-new outbound message. Proceeding straight to sendMail flow.")

        # Load default CC emails from organization AI settings table
        cc_list = []
        try:
            settings_res = await self.session.execute(text("""
                SELECT default_cc_emails FROM organization_ai_settings WHERE organization_id = :org_id
            """), {"org_id": request.organization_id})
            settings_row = settings_res.fetchone()
            if settings_row and settings_row[0]:
                import json
                cc_list = json.loads(settings_row[0]) if isinstance(settings_row[0], str) else settings_row[0]
        except Exception as settings_ex:
            logger.warning("Failed to load default CC emails from AI settings", error=str(settings_ex))

        # STEP 6: Send Graph Email
        try:
            if is_reply_expected:
                if not parent_graph_message_id:
                    # Do NOT thread unknown replies, raise delivery failure
                    error_msg = "Threaded reply expected but no valid parent Graph message could be resolved."
                    log_to_request_file(f"Delivery Failed: {error_msg}")
                    logger.error(error_msg)
                    raise EmailSendError(error_msg)
                    
                async with StepTracker(6, "Send Graph Threaded Reply"):
                    message_id = await self._send_threaded_reply(
                        request=request,
                        access_token=access_token,
                        final_html_body=final_html_body,
                        graph_attachments=graph_attachments,
                        parent_message_id=parent_graph_message_id,
                        cc_list=cc_list,
                        prefix=prefix
                    )
            else:
                async with StepTracker(6, "Send Graph Email"):
                    message_id = await self._send_new_email(
                        request=request,
                        access_token=access_token,
                        final_html_body=final_html_body,
                        graph_attachments=graph_attachments,
                        prefix=prefix
                    )
            logger.info("GRAPH API SUCCESS")
            log_to_request_file(f"Graph API Success: message_id={message_id}")
        except Exception as e:
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Send Graph Email: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("ORIGINAL ERROR")
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
        true_internet_id = request.internet_message_id
        true_index = None
        
        try:
            logger.info("Attempting to retrieve sent message metadata from Sent Items folder")
            sent_meta = await self.graph_client.get_sent_message_metadata(
                access_token=access_token,
                subject=request.subject,
                to_email=request.customer_email
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
                await self.session.execute(
                    text("""
                        INSERT INTO email_log (
                            id, organization_id, customer_id, campaign_id, direction, 
                            email_type, subject, body, has_attachment, sent_at, delivery_status, graph_message_id,
                            conversation_id, thread_id, internet_message_id, "references", in_reply_to, created_at
                        ) VALUES (
                            :id, :org_id, :customer_id, NULL, 'outbound', 
                            'engagement', :subject, :body, :has_attachment, NOW(), 'sent', :graph_message_id,
                            :conversation_id, :thread_id, :internet_message_id, :references, :in_reply_to, NOW()
                        )
                    """),
                    {
                        "id": email_log_id,
                        "org_id": request.organization_id,
                        "customer_id": customer_id,
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
                log_to_request_file("Email log insert result: Success")
        except Exception as e:
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Save Email History: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("FAILED INSERT email_log")
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
            tb_str = traceback.format_exc()
            print(type(e))
            print(repr(e))
            traceback.print_exc()
            log_to_request_file(f"Exception in Commit: {type(e)} - {repr(e)}\nTraceback:\n{tb_str}")
            logger.exception("FAILED COMMIT")
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
            tb_str = traceback.format_exc()
            print(type(serialization_error))
            print(repr(serialization_error))
            traceback.print_exc()
            log_to_request_file(f"Exception in response serialization: {type(serialization_error)} - {repr(serialization_error)}\nTraceback:\n{tb_str}")
            raise serialization_error
