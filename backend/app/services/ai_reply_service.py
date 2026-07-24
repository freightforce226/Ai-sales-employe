"""
===========================================================

File:
ai_reply_service.py

Purpose:
Orchestrates the settings management and email draft generation for the AI Reply Engine.

Why this file exists:
Implements business rules, prompt building, and thread context extraction separate from API routing.

Used By:
AI Reply Engine
AI Reply API Router

Responsibilities:
- Manage organization AI reply settings (retrieve, update)
- Extract previous email thread history as context (chronological, cleaned plain text, max 10 messages)
- Construct natural prompts based on AI writing instructions, context, date, and hallucination rules
- Coordinate text generation via LLMService and format the final draft response

===========================================================
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
import json
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from bs4 import BeautifulSoup

from app.models.ai_reply import OrganizationAiSettings
from app.schemas.ai_reply import AIReplySettingsUpdate, AIReplyGenerateResponse, AIReplyPendingResponse, AIReplyCompleteRequest, AIReplyLockRequest
from app.services.llm_service import LLMService
from app.core.logging import get_logger

logger = get_logger(__name__)

class AIReplyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMService()

    async def get_settings(self, org_id: UUID) -> OrganizationAiSettings:
        """
        Retrieves the AI settings for an organization. Creates default settings if missing.
        """
        res = await self.db.execute(
            text("SELECT organization_id, ai_enabled, company_name, reply_tone, ai_writing_instructions, email_signature, default_cc_emails FROM organization_ai_settings WHERE organization_id = :org_id"),
            {"org_id": org_id}
        )
        row = res.fetchone()
        if not row:
            # Create default settings record
            await self.db.execute(
                text("""
                    INSERT INTO organization_ai_settings (organization_id, ai_enabled, reply_tone, default_cc_emails)
                    VALUES (:org_id, FALSE, 'professional', '[]'::jsonb)
                """),
                {"org_id": org_id}
            )
            await self.db.commit()
            
            # Fetch again
            res = await self.db.execute(
                text("SELECT organization_id, ai_enabled, company_name, reply_tone, ai_writing_instructions, email_signature, default_cc_emails FROM organization_ai_settings WHERE organization_id = :org_id"),
                {"org_id": org_id}
            )
            row = res.fetchone()

        org_id_val, ai_enabled, company_name, reply_tone, ai_writing_instructions, email_signature, default_cc_emails = row
        
        # Parse JSON default_cc_emails safely
        cc_list = []
        if default_cc_emails:
            if isinstance(default_cc_emails, str):
                try:
                    cc_list = json.loads(default_cc_emails)
                except Exception:
                    cc_list = []
            elif isinstance(default_cc_emails, list):
                cc_list = default_cc_emails
                
        settings_model = OrganizationAiSettings(
            organization_id=org_id_val,
            ai_enabled=ai_enabled,
            company_name=company_name,
            reply_tone=reply_tone,
            ai_writing_instructions=ai_writing_instructions,
            email_signature=email_signature,
            default_cc_emails=cc_list
        )
        return settings_model

    async def update_settings(self, org_id: UUID, update_dto: AIReplySettingsUpdate) -> OrganizationAiSettings:
        """
        Updates the organization AI settings.
        """
        await self.get_settings(org_id)
        
        updates = []
        params = {"org_id": org_id}
        
        if update_dto.ai_enabled is not None:
            updates.append("ai_enabled = :ai_enabled")
            params["ai_enabled"] = update_dto.ai_enabled
        if update_dto.company_name is not None:
            updates.append("company_name = :company_name")
            params["company_name"] = update_dto.company_name
        if update_dto.reply_tone is not None:
            updates.append("reply_tone = :reply_tone")
            params["reply_tone"] = update_dto.reply_tone
        if update_dto.ai_writing_instructions is not None:
            updates.append("ai_writing_instructions = :ai_writing_instructions")
            params["ai_writing_instructions"] = update_dto.ai_writing_instructions
        if update_dto.email_signature is not None:
            updates.append("email_signature = :email_signature")
            params["email_signature"] = update_dto.email_signature
        if update_dto.default_cc_emails is not None:
            updates.append("default_cc_emails = :default_cc_emails")
            params["default_cc_emails"] = json.dumps(update_dto.default_cc_emails)
            
        if updates:
            query = f"UPDATE organization_ai_settings SET {', '.join(updates)}, updated_at = NOW() WHERE organization_id = :org_id"
            await self.db.execute(text(query), params)
            await self.db.commit()
            
        return await self.get_settings(org_id)

    async def build_thread_context(self, org_id: UUID, customer_id: UUID, thread_id: str, customer_reply_text: str) -> dict:
        """
        Loads the previous conversation from email_log in chronological order, cleans the HTML,
        applies clean thread rules, limits to 10 most recent messages, and returns the context.
        """
        res = await self.db.execute(
            text("""
                SELECT direction, subject, body, sent_at 
                FROM email_log 
                WHERE organization_id = :org_id 
                  AND customer_id = :customer_id 
                  AND thread_id = :thread_id 
                ORDER BY sent_at ASC
            """),
            {"org_id": org_id, "customer_id": customer_id, "thread_id": thread_id}
        )
        rows = res.fetchall()

        # Limit to the most recent 10 messages to control context window and token usage
        if len(rows) > 10:
            rows = rows[-10:]

        subject = "New Inquiry"
        thread_messages = []

        for direction, sub, body, sent_at in rows:
            if sub:
                subject = sub
            clean_body = self._clean_context_message(body)
            if clean_body:
                sender = "Customer" if direction == "inbound" else "Our Team"
                thread_messages.append(f"[{sent_at.isoformat()}] {sender}: {clean_body}")

        cleaned_latest = self._clean_context_message(customer_reply_text)
        thread_context_str = "\n".join(thread_messages)
        
        return {
            "subject": subject,
            "thread_context": thread_context_str,
            "cleaned_latest_email": cleaned_latest
        }

    def build_reply_prompt(self, ai_settings: OrganizationAiSettings, context_dict: dict) -> str:
        """
        Assembles all prompt components matching prompt, tone, signature, and anti-hallucination rules.
        """
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        company = ai_settings.company_name or "our logistics firm"
        tone = ai_settings.reply_tone
        instructions = ai_settings.ai_writing_instructions or "Keep replies brief, warm, and helpful."
        thread_history = context_dict["thread_context"]
        latest_msg = context_dict["cleaned_latest_email"]
        subject = context_dict["subject"]

        # Prompt with strict context, signature omission, first vs follow-up determination, and hallucination rules
        prompt = f"""
You are an experienced freight sales executive representing {company}.
The current date and time is {current_date}.
The email thread subject is: "{subject}".

Here is the conversation history:
---
{thread_history}
---

The customer has just sent this email:
---
{latest_msg}
---

Your task is to write a short, natural acknowledgement reply email to the customer.

Strict Prompt Rules:
1. Determine naturally whether this is the customer's first email or a follow-up. Do not make standard follow-up assumptions if it is a new inquiry.
2. Base the acknowledgement entirely on the actual topic in the conversation history. Do not assume the shipment is about route optimization unless routing is explicitly mentioned.
3. If the customer discusses pricing, documentation, customs, warehousing, scheduling, booking, or other logistics topics, acknowledge that specific topic naturally.
4. Sound completely human. NEVER mention AI, prompt variables, or sound like a template.
5. Invites the customer to share any additional shipment information if needed (e.g. weight, dimensions, origin, destination).
6. Crucial: NEVER negotiate pricing, NEVER promise shipment dates, NEVER confirm bookings, and NEVER make any business commitments.
7. Anti-hallucination rule: If the required details are unavailable, do not guess, do not invent, and do not promise anything. Acknowledge and state that our team is currently reviewing.
8. Signature constraint: Do NOT generate any closing block or signature components. You must NEVER generate words like 'Regards', 'Best Regards', 'Kind Regards', 'Thanks & Regards', 'Sincerely', a sender name, designation, phone number, email address, or company website signature. Return only the narrative body text.
9. Tone requirement: {tone}.
10. Mention shipment optimization ONLY when it is naturally relevant. Do not force this sentence into every reply. If the customer's reply does not require discussing logistics, simply acknowledge naturally.

IMPORTANT:
- Return ONLY the email reply body.
- Do NOT generate:
  - Best Regards
  - Regards
  - Thanks & Regards
  - Sincerely
  - Signature
  - Name
  - Job title
  - Company name
  - Phone number
  - Email address
  - Banner
  - Footer
  - Separator lines (---, ___, etc.)

AI Writing Instructions:
{instructions}

Reply Body text only (do NOT include subject, signatures, or placeholders):
"""
        return prompt

    async def generate_reply_draft(self, org_id: UUID, customer_id: UUID, thread_id: str, customer_reply_text: str) -> AIReplyGenerateResponse:
        """
        Orchestrates thread loading, prompt building, LLM execution, signature formatting, and returns the draft.
        """
        start_time = datetime.now(timezone.utc)
        
        # 1. Fetch AI Settings
        ai_settings = await self.get_settings(org_id)
        
        # 2. Extract thread context
        context_dict = await self.build_thread_context(org_id, customer_id, thread_id, customer_reply_text)
        
        # 3. Build Prompt
        prompt = self.build_reply_prompt(ai_settings, context_dict)
        
        # 4. Generate reply text
        draft_body = ""
        if ai_settings.ai_enabled:
            draft_body = await self.llm.generate_text(prompt, org_id=str(org_id), thread_id=thread_id)
            logger.info("Raw Gemini response before sanitization (attempt 1)", raw_body=draft_body)
            draft_body = self.sanitize_llm_reply(draft_body)
            logger.info("Sanitized response after sanitize_llm_reply (attempt 1)", sanitized_body=draft_body)

            # Check if sanitized body is empty or too short (< 10 non-whitespace chars)
            non_ws_count = len([c for c in draft_body if not c.isspace()])
            if non_ws_count < 10:
                logger.warning("Sanitized draft body is too short (attempt 1), retrying LLM generation once...", non_ws_count=non_ws_count)
                draft_body = await self.llm.generate_text(prompt, org_id=str(org_id), thread_id=thread_id)
                logger.info("Raw Gemini response before sanitization (attempt 2)", raw_body=draft_body)
                draft_body = self.sanitize_llm_reply(draft_body)
                logger.info("Sanitized response after sanitize_llm_reply (attempt 2)", sanitized_body=draft_body)
                
                if len([c for c in draft_body if not c.isspace()]) < 10:
                    logger.warning("Sanitized draft body is still too short after retry. Using fallback acknowledgement.")
                    draft_body = self.llm._get_fallback_reply()
        else:
            draft_body = self.llm._get_fallback_reply()
            logger.info("Raw fallback response", raw_body=draft_body)
            draft_body = self.sanitize_llm_reply(draft_body)
            logger.info("Sanitized fallback response", sanitized_body=draft_body)
            
        # Append email signature if configured
        if ai_settings.email_signature:
            draft_body = f"{draft_body}\n\n--\n{ai_settings.email_signature}"
            
        # Parse suggested CC emails
        cc_emails = ai_settings.default_cc_emails if isinstance(ai_settings.default_cc_emails, list) else []

        
        return AIReplyGenerateResponse(
            subject=f"Re: {context_dict['subject']}" if not context_dict['subject'].lower().startswith("re:") else context_dict['subject'],
            reply_body=draft_body,
            suggested_cc_emails=[str(e) for e in cc_emails],
            generation_time=start_time,
            provider="Google",
            model=self.llm.model_name
        )

    async def get_pending_replies(self) -> List[AIReplyPendingResponse]:
        """
        Retrieves all inbound customer replies that are not yet acknowledged.
        """
        query = """
            SELECT 
                el.id AS reply_id,
                el.organization_id,
                o.display_name AS organization_name,
                el.customer_id,
                c.contact_name AS customer_name,
                c.contact_email AS customer_email,
                aoe.mailbox_email,
                el.thread_id,
                el.conversation_id,
                el.graph_message_id AS message_id,
                el.subject,
                el.body AS latest_email,
                el.sent_at AS received_datetime,
                settings.reply_tone,
                settings.default_cc_emails AS default_cc,
                settings.ai_writing_instructions,
                COALESCE(sig.signature_html, settings.email_signature) AS email_signature,
                el.internet_message_id
            FROM email_log el
            JOIN customers c ON el.customer_id = c.id
            JOIN organizations o ON el.organization_id = o.id
            JOIN organization_ai_settings settings ON el.organization_id = settings.organization_id
            LEFT JOIN organization_signatures sig ON el.organization_id = sig.organization_id
            LEFT JOIN active_organizations_for_engagement aoe ON el.organization_id = aoe.organization_id
            WHERE el.direction = 'inbound'
              AND el.delivery_status = 'delivered'
              AND settings.ai_enabled = TRUE
              AND EXISTS (
                  SELECT 1 FROM email_log el_prev
                  WHERE el_prev.direction = 'outbound'
                    AND el_prev.customer_id = el.customer_id
                    AND el_prev.organization_id = el.organization_id
                    AND el_prev.sent_at < el.sent_at
                    AND (
                        (el_prev.thread_id = el.thread_id AND el_prev.thread_id IS NOT NULL AND el.thread_id IS NOT NULL)
                        OR (el_prev.conversation_id = el.conversation_id AND el_prev.conversation_id IS NOT NULL AND el.conversation_id IS NOT NULL)
                        OR (el_prev.internet_message_id = el.in_reply_to AND el_prev.internet_message_id IS NOT NULL)
                        OR (el.references LIKE '%' || el_prev.internet_message_id || '%' AND el_prev.internet_message_id IS NOT NULL AND el.references IS NOT NULL)
                        OR (
                            LOWER(REGEXP_REPLACE(el.subject, '^(re|fwd|reply|aw|ref):\s*', '', 'i')) = LOWER(REGEXP_REPLACE(el_prev.subject, '^(re|fwd|reply|aw|ref):\s*', '', 'i'))
                            AND el.subject IS NOT NULL AND el_prev.subject IS NOT NULL
                        )
                    )
              )
              AND NOT EXISTS (
                  SELECT 1 FROM email_log el_out 
                  WHERE el_out.direction = 'outbound' 
                    AND el_out.customer_id = el.customer_id
                    AND el_out.organization_id = el.organization_id
                    AND el_out.sent_at > el.sent_at
                    AND (
                        (el_out.thread_id = el.thread_id AND el_out.thread_id IS NOT NULL AND el.thread_id IS NOT NULL)
                        OR (el_out.conversation_id = el.conversation_id AND el_out.conversation_id IS NOT NULL AND el.conversation_id IS NOT NULL)
                        OR (el_out.in_reply_to = el.internet_message_id AND el_out.in_reply_to IS NOT NULL)
                        OR (el_out.references LIKE '%' || el.internet_message_id || '%' AND el.internet_message_id IS NOT NULL AND el_out.references IS NOT NULL)
                    )
              )
            ORDER BY el.sent_at ASC
        """
        
        res = await self.db.execute(text(query))
        rows = res.fetchall()
        
        pending_list = []
        for r in rows:
            reply_id, org_id, org_name, cust_id, cust_name, cust_email, mailbox_email, thread_id, conv_id, msg_id, subject, latest_email, received_dt, reply_tone, default_cc, instructions, signature, internet_msg_id = r
            
            # Map default_cc safely
            cc_emails = []
            if default_cc:
                if isinstance(default_cc, str):
                    try:
                        cc_emails = json.loads(default_cc)
                    except Exception:
                        cc_emails = []
                elif isinstance(default_cc, list):
                    cc_emails = default_cc
                    
            clean_text = self._clean_context_message(latest_email)
            
            pending_list.append(
                AIReplyPendingResponse(
                    reply_id=reply_id,
                    organization_id=org_id,
                    organization_name=org_name,
                    customer_id=cust_id,
                    customer_name=cust_name,
                    customer_email=cust_email,
                    mailbox_email=mailbox_email,
                    thread_id=thread_id,
                    conversation_id=conv_id,
                    message_id=msg_id,
                    internet_message_id=internet_msg_id,
                    subject=subject,
                    latest_email_html=latest_email or "",
                    customer_reply_text=clean_text or "",
                    received_datetime=received_dt,
                    reply_tone=reply_tone,
                    default_cc=[str(e) for e in cc_emails],
                    ai_writing_instructions=instructions,
                    email_signature=signature
                )
            )
            
        logger.info(f"Pending replies found: {len(pending_list)}")
        for item in pending_list:
            logger.info(
                "Pending reply detail",
                organization=item.organization_name,
                customer=item.customer_name,
                thread_id=item.thread_id
            )
            
        return pending_list

    async def complete_reply(self, payload: AIReplyCompleteRequest) -> dict:
        """
        Marks the AI reply as completed, updates status, and persists details.
        """
        # 1. Update email log status and timestamps
        await self.db.execute(
            text("""
                UPDATE email_log
                SET delivery_status = 'sent',
                    sent_at = COALESCE(:sent_at, sent_at),
                    queued_at = NULL
                WHERE graph_message_id = :message_id
            """),
            {
                "message_id": payload.message_id,
                "sent_at": datetime.fromisoformat(payload.sent_at.replace("Z", "+00:00")) if payload.sent_at else None
            }
        )
        
        # 2. Find details from the outbound email log if not passed
        res = await self.db.execute(
            text("SELECT organization_id, customer_id, thread_id, in_reply_to FROM email_log WHERE graph_message_id = :message_id"),
            {"message_id": payload.message_id}
        )
        row = res.fetchone()
        if row:
            org_id, customer_id, thread_id, in_reply_to = row
            # Update the parent inbound email's status to 'sent' (completed)
            await self.db.execute(
                text("""
                    UPDATE email_log
                    SET delivery_status = 'sent',
                        queued_at = NULL
                    WHERE organization_id = :org_id
                      AND direction = 'inbound'
                      AND (thread_id = :thread_id OR internet_message_id = :in_reply_to)
                      AND delivery_status = 'queued'
                """),
                {
                    "org_id": org_id,
                    "thread_id": thread_id,
                    "in_reply_to": in_reply_to
                }
            )
            # Update follow_up_schedule status if there is a matching schedule
            await self.db.execute(
                text("""
                    UPDATE follow_up_schedule
                    SET status = 'completed',
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE organization_id = :org_id
                      AND customer_id = :customer_id
                      AND (reply_thread_id = :thread_id OR reply_message_id = :in_reply_to)
                      AND status != 'completed'
                """),
                {
                    "org_id": org_id,
                    "customer_id": customer_id,
                    "thread_id": thread_id,
                    "in_reply_to": in_reply_to
                }
            )
            
        await self.db.commit()
        return {"success": True, "message_id": payload.message_id}

    async def lock_reply(self, payload: AIReplyLockRequest) -> dict:
        """
        Atomically acquires a processing lock on a specific pending AI reply.
        """
        org_id = payload.organization_id
        target_id = None
        resolved_org_id = org_id
        resolved_customer_id = None
        resolved_thread_id = None
        resolved_graph_message_id = None
        resolved_body = None
        current_status = None
        path_used = None

        # 1. Log BEFORE lookup
        logger.info(
            "Lock lookup start",
            organization_id=str(org_id),
            reply_id=str(payload.reply_id) if payload.reply_id else None,
            message_id=payload.message_id,
            thread_id=payload.thread_id
        )

        # Priority 1: reply_id (email_log.id)
        if payload.reply_id:
            path_used = "reply_id"
            res = await self.db.execute(
                text("""
                    SELECT id, organization_id, customer_id, thread_id, graph_message_id, body, delivery_status FROM email_log
                    WHERE id = :reply_id
                    LIMIT 1
                """),
                {"reply_id": payload.reply_id}
            )
            row = res.fetchone()
            if row:
                target_id, resolved_org_id, resolved_customer_id, resolved_thread_id, resolved_graph_message_id, resolved_body, current_status = row

        # Priority 2: message_id (graph_message_id)
        elif payload.message_id:
            path_used = "graph_message_id"
            res = await self.db.execute(
                text("""
                    SELECT id, organization_id, customer_id, thread_id, graph_message_id, body, delivery_status FROM email_log
                    WHERE organization_id = :org_id
                      AND graph_message_id = :message_id
                    LIMIT 1
                """),
                {"org_id": org_id, "message_id": payload.message_id}
            )
            row = res.fetchone()
            if row:
                target_id, resolved_org_id, resolved_customer_id, resolved_thread_id, resolved_graph_message_id, resolved_body, current_status = row

        # Priority 3: thread_id
        elif payload.thread_id:
            path_used = "thread_id"
            res = await self.db.execute(
                text("""
                    SELECT id, organization_id, customer_id, thread_id, graph_message_id, body, delivery_status FROM email_log
                    WHERE organization_id = :org_id
                      AND thread_id = :thread_id
                      AND direction = 'inbound'
                    ORDER BY received_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                """),
                {"org_id": org_id, "thread_id": payload.thread_id}
            )
            row = res.fetchone()
            if row:
                target_id, resolved_org_id, resolved_customer_id, resolved_thread_id, resolved_graph_message_id, resolved_body, current_status = row

        # Clean customer reply text
        clean_text = self._clean_context_message(resolved_body) if resolved_body else None

        # 2. Log AFTER lookup
        if target_id:
            logger.info(
                "Lock lookup complete",
                resolved_id=str(target_id),
                graph_message_id=resolved_graph_message_id,
                thread_id=resolved_thread_id,
                delivery_status=current_status
            )
        else:
            logger.info(
                "Lock lookup complete: no record found",
                path_used=path_used
            )
            return {
                "success": False,
                "status": None,
                "reason": "reply_not_found",
                "reply_id": payload.reply_id,
                "organization_id": org_id,
                "customer_id": None,
                "thread_id": payload.thread_id,
                "message_id": payload.message_id,
                "customer_reply_text": None
            }

        if current_status != 'delivered':
            logger.info("Lock update blocked: status is not delivered", target_id=str(target_id), current_status=current_status)
            return {
                "success": False,
                "status": None,
                "reason": "already_processing",
                "reply_id": target_id,
                "organization_id": resolved_org_id,
                "customer_id": resolved_customer_id,
                "thread_id": resolved_thread_id,
                "message_id": resolved_graph_message_id,
                "customer_reply_text": clean_text
            }

        # 3. Log BEFORE update
        logger.info("Lock update start", target_id=str(target_id))

        # Atomically lock the specific record by its primary key
        lock_res = await self.db.execute(
            text("""
                UPDATE email_log
                SET delivery_status = 'queued',
                    queued_at = NOW()
                WHERE id = :target_id
                  AND delivery_status = 'delivered'
            """),
            {"target_id": target_id}
        )
        await self.db.commit()

        # 4. Log AFTER update
        rows_affected = lock_res.rowcount
        logger.info("Lock update complete", target_id=str(target_id), rows_affected=rows_affected)

        if rows_affected > 0:
            return {
                "success": True,
                "status": "processing",
                "reason": None,
                "reply_id": target_id,
                "organization_id": resolved_org_id,
                "customer_id": resolved_customer_id,
                "thread_id": resolved_thread_id,
                "message_id": resolved_graph_message_id,
                "customer_reply_text": clean_text
            }
        else:
            return {
                "success": False,
                "status": None,
                "reason": "already_processing",
                "reply_id": target_id,
                "organization_id": resolved_org_id,
                "customer_id": resolved_customer_id,
                "thread_id": resolved_thread_id,
                "message_id": resolved_graph_message_id,
                "customer_reply_text": clean_text
            }





    def _clean_context_message(self, body_html: str) -> str:
        """
        Strips HTML tags, tracking pixels, email headers, previous signatures,
        separators, and empty lines to build a clean conversation context.
        """
        if not body_html:
            return ""
            
        # 1. Strip HTML tags and metadata using BeautifulSoup
        soup = BeautifulSoup(body_html, "html.parser")
        
        # Remove tracking pixels
        for img in soup.find_all("img"):
            img.decompose()
        for tag in soup(["script", "style", "head", "title", "meta", "link"]):
            tag.decompose()
            
        text_out = soup.get_text(separator="\n")
        
        # 2. Clean email lines and strip signatures/separators/headers
        lines = []
        for line in text_out.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue
                
            # If we hit the start of email headers or previous threads, stop parsing
            if any(line_stripped.lower().startswith(prefix) for prefix in [
                "from:", "sent:", "to:", "subject:", "cc:", "bcc:", "date:",
                "on ", "original message", "---original message---", "-----original message-----"
            ]):
                break
                
            # Skip Outlook/Gmail reply lines
            if line_stripped.startswith("---") or line_stripped.startswith("___") or line_stripped.startswith(">"):
                continue
                
            # Skip signature starts to avoid appending huge signatures to prompt context
            if any(line_stripped.lower() == sig_start for sig_start in [
                "regards", "regards,", "best regards", "best regards,", "thanks", "thanks,", "thanks & regards",
                "kind regards", "kind regards,", "sincerely", "sincerely,", "warm regards", "warm regards,"
            ]):
                break  # Stop parsing remainder of email as it's typically the signature block
                
            lines.append(line_stripped)
            
        return "\n".join(lines)

    def sanitize_llm_reply(self, body_text: str) -> str:
        """
        Scans lines from the bottom of the email text up, locating any common closing phrases
        (e.g., Regards, Thanks, Sincerely, etc.) and strips them along with any trailing
        name, designation, or signature block.
        """
        if not body_text:
            return ""
            
        lines = body_text.splitlines()
        
        closing_keywords = [
            "regards", "best regards", "kind regards", "thanks", "thanks & regards",
            "thanks and regards", "sincerely", "warm regards", "yours sincerely", "best", "warmest regards"
        ]
        
        # Strip trailing empty lines and separators
        while lines and (not lines[-1].strip() or lines[-1].strip() in ["--", "---", "___", "__"]):
            lines.pop()

        for i in range(len(lines) - 1, -1, -1):
            line_stripped = lines[i].strip()
            line_lower = line_stripped.lower().rstrip(".,!:")
            
            is_closing = False
            # 1. Exact match on closing keywords
            if line_lower in closing_keywords:
                is_closing = True
            # 2. Starts with a closing keyword/phrase and has a short length (not a full sentence)
            elif any(line_lower.startswith(kw) for kw in closing_keywords):
                words = line_stripped.split()
                if len(words) < 5:
                    is_closing = True
                    
            if is_closing:
                result_lines = lines[:i]
                while result_lines and (not result_lines[-1].strip() or result_lines[-1].strip() in ["--", "---", "___", "__"]):
                    result_lines.pop()
                return "\n".join(result_lines).strip()
                
        return "\n".join(lines).strip()

    async def fail_reply(self, payload: AIReplyLockRequest) -> dict:
        """
        Releases the lock on a reply by changing status from 'queued' to 'delivered' and setting queued_at to NULL.
        """
        org_id = payload.organization_id
        target_id = None
        
        # Priority 1: reply_id
        if payload.reply_id:
            res = await self.db.execute(
                text("SELECT id FROM email_log WHERE id = :reply_id LIMIT 1"),
                {"reply_id": payload.reply_id}
            )
            row = res.fetchone()
            if row:
                target_id = row[0]
                
        # Priority 2: message_id (graph_message_id)
        elif payload.message_id:
            res = await self.db.execute(
                text("SELECT id FROM email_log WHERE organization_id = :org_id AND graph_message_id = :message_id LIMIT 1"),
                {"org_id": org_id, "message_id": payload.message_id}
            )
            row = res.fetchone()
            if row:
                target_id = row[0]
                
        # Priority 3: thread_id
        elif payload.thread_id:
            res = await self.db.execute(
                text("""
                    SELECT id FROM email_log 
                    WHERE organization_id = :org_id 
                      AND thread_id = :thread_id 
                      AND direction = 'inbound'
                    ORDER BY received_at DESC NULLS LAST, created_at DESC 
                    LIMIT 1
                """),
                {"org_id": org_id, "thread_id": payload.thread_id}
            )
            row = res.fetchone()
            if row:
                target_id = row[0]
                
        if not target_id:
            return {"success": False, "reason": "reply_not_found"}
            
        res = await self.db.execute(
            text("""
                UPDATE email_log
                SET delivery_status = 'delivered',
                    queued_at = NULL
                WHERE id = :target_id
                  AND delivery_status = 'queued'
            """),
            {"target_id": target_id}
        )
        await self.db.commit()
        
        return {"success": res.rowcount > 0}

    async def recover_stale_locks(self, timeout_minutes: int) -> int:
        """
        Scans and releases stale locks that have been in 'queued' status for longer than timeout_minutes.
        """
        # Find stale records first to log structured metrics for each
        res_stale = await self.db.execute(
            text("""
                SELECT id, queued_at, NOW() as recovered_at, 
                       EXTRACT(EPOCH FROM (NOW() - queued_at))/60 as lock_age_minutes
                FROM email_log
                WHERE direction = 'inbound'
                  AND delivery_status = 'queued'
                  AND queued_at < NOW() - (:timeout_minutes * INTERVAL '1 minute')
            """),
            {"timeout_minutes": timeout_minutes}
        )
        stale_rows = res_stale.fetchall()
        
        for r in stale_rows:
            reply_id, queued_at, recovered_at, lock_age_minutes = r
            logger.info(
                "Recovered stale AI reply lock",
                reply_id=str(reply_id),
                queued_at=queued_at.isoformat() if queued_at else None,
                recovered_at=recovered_at.isoformat() if recovered_at else None,
                lock_age_minutes=int(lock_age_minutes) if lock_age_minutes is not None else None
            )
            
        # Perform the actual update
        res_update = await self.db.execute(
            text("""
                UPDATE email_log
                SET delivery_status = 'delivered',
                    queued_at = NULL
                WHERE direction = 'inbound'
                  AND delivery_status = 'queued'
                  AND queued_at < NOW() - (:timeout_minutes * INTERVAL '1 minute')
            """),
            {"timeout_minutes": timeout_minutes}
        )
        await self.db.commit()
        
        logger.info(f"Recovery scan completed. Recovered {res_update.rowcount} stale locks.")
        return res_update.rowcount

