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

        # Find the most recent outbound message (previous assistant reply)
        prev_outbound = None
        for row in reversed(rows):
            direction, sub, body, sent_at = row
            if direction == "outbound":
                prev_outbound = row
                break

        subject = "New Inquiry"
        thread_messages = []

        if prev_outbound:
            direction, sub, body, sent_at = prev_outbound
            if sub:
                subject = sub
            clean_body = self._clean_context_message(body)
            if clean_body:
                thread_messages.append(f"[{sent_at.isoformat()}] Our Team: {clean_body}")

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
        company = ai_settings.company_name or "our logistics firm"
        thread_history = context_dict["thread_context"]
        latest_msg = context_dict["cleaned_latest_email"]
        subject = context_dict["subject"]

        prompt = f"""You are an experienced freight forwarding sales executive representing {company}.
The email subject is: "{subject}".

Previous conversation context:
{thread_history}

Customer's latest email:
"{latest_msg}"

Task: Write a very short, natural reply email to the customer's latest email.

Rules:
1. Persona: Experienced freight forwarding sales executive. Sound human, natural, and professional.
2. Preferred length: 20-50 words. Hard maximum: 60 words. Maximum: 3 short paragraphs. Use simple business English.
3. Reply ONLY to the customer's latest message.
4. Never explain logistics unless asked. Never oversell. Never repeat customer information.
5. If the customer only acknowledges, reply with a brief acknowledgement.
6. Do NOT generate any greeting (like Hi, Hello), closing phrase (Regards, Best Regards, Kind Regards, Sincerely), signature, company name, phone, designation, or separator (--).
7. Return ONLY the narrative body of the reply."""
        return prompt

    async def generate_reply_draft(self, org_id: UUID, customer_id: UUID, thread_id: str, customer_reply_text: str) -> AIReplyGenerateResponse:
        """
        Orchestrates thread loading, prompt building, LLM execution, signature formatting, and returns the draft.
        """
        start_time = datetime.now(timezone.utc)
        
        # 1. Fetch AI Settings
        ai_settings = await self.get_settings(org_id)

        # Resolve customer first name for greeting strategy
        res_cust = await self.db.execute(
            text("SELECT contact_name FROM customers WHERE id = :customer_id"),
            {"customer_id": customer_id}
        )
        row_cust = res_cust.fetchone()
        customer_name = row_cust[0] if row_cust else None
        
        first_name = None
        if customer_name:
            first_name = customer_name.strip().split()[0]
        greeting = f"Hi {first_name}," if first_name else "Hi,"
        
        # 2. Extract thread context
        context_dict = await self.build_thread_context(org_id, customer_id, thread_id, customer_reply_text)
        
        # 3. Build Prompt
        prompt = self.build_reply_prompt(ai_settings, context_dict)
        
        # 4. Generate reply text
        draft_body = ""
        if ai_settings.ai_enabled:
            raw_llm = await self.llm.generate_text(prompt, org_id=str(org_id), thread_id=thread_id)
            sanitized = self.sanitize_llm_reply(raw_llm)
            draft_body = f"{greeting}\n\n{sanitized}"
            
            # Log Stage 1: LLM Output (Raw)
            has_sep = "--" in raw_llm
            has_reg = "best regards" in raw_llm.lower() or "regards" in raw_llm.lower()
            has_sig = (ai_settings.email_signature.lower() in raw_llm.lower()) if ai_settings.email_signature else False
            logger.info(
                "Stage: LLM Output",
                reply_id=str(thread_id),
                reply_body_length=len(raw_llm),
                contains_separator=has_sep,
                contains_best_regards=has_reg,
                contains_org_signature=has_sig,
                raw_body=raw_llm
            )
            
            # Log Stage 2: sanitize_llm_reply Output
            has_sep = "--" in draft_body
            has_reg = "best regards" in draft_body.lower() or "regards" in draft_body.lower()
            has_sig = (ai_settings.email_signature.lower() in draft_body.lower()) if ai_settings.email_signature else False
            logger.info(
                "Stage: sanitize_llm_reply completed",
                reply_id=str(thread_id),
                reply_body_length=len(draft_body),
                contains_separator=has_sep,
                contains_best_regards=has_reg,
                contains_org_signature=has_sig,
                sanitized_body=draft_body
            )

            # Validation
            word_count = len(draft_body.split())
            non_ws_count = len([c for c in sanitized if not c.isspace()])
            
            if non_ws_count < 10 or self._is_signature_present(draft_body, ai_settings.email_signature) or word_count > 60:
                logger.warning(f"Draft invalid (words: {word_count}, non-ws: {non_ws_count}), retrying LLM generation once...")
                raw_llm = await self.llm.generate_text(prompt, org_id=str(org_id), thread_id=thread_id)
                sanitized = self.sanitize_llm_reply(raw_llm)
                draft_body = f"{greeting}\n\n{sanitized}"
                
                # Log Stage 1: LLM Output Retry (Raw)
                has_sep = "--" in raw_llm
                has_reg = "best regards" in raw_llm.lower() or "regards" in raw_llm.lower()
                has_sig = (ai_settings.email_signature.lower() in raw_llm.lower()) if ai_settings.email_signature else False
                logger.info(
                    "Stage: LLM Output (Retry Attempt)",
                    reply_id=str(thread_id),
                    reply_body_length=len(raw_llm),
                    contains_separator=has_sep,
                    contains_best_regards=has_reg,
                    contains_org_signature=has_sig,
                    raw_body=raw_llm
                )
                
                # Log Stage 2: sanitize_llm_reply Retry Output
                has_sep = "--" in draft_body
                has_reg = "best regards" in draft_body.lower() or "regards" in draft_body.lower()
                has_sig = (ai_settings.email_signature.lower() in draft_body.lower()) if ai_settings.email_signature else False
                logger.info(
                    "Stage: sanitize_llm_reply completed (Retry Attempt)",
                    reply_id=str(thread_id),
                    reply_body_length=len(draft_body),
                    contains_separator=has_sep,
                    contains_best_regards=has_reg,
                    contains_org_signature=has_sig,
                    sanitized_body=draft_body
                )
                
                # Check again
                word_count = len(draft_body.split())
                non_ws_count = len([c for c in sanitized if not c.isspace()])
                if non_ws_count < 10 or self._is_signature_present(draft_body, ai_settings.email_signature) or word_count > 60:
                    logger.warning("Sanitized draft body is still invalid after retry. Using fallback acknowledgement.")
                    fallback = self.llm._get_fallback_reply()
                    sanitized = self.sanitize_llm_reply(fallback)
                    draft_body = f"{greeting}\n\n{sanitized}"
        else:
            fallback = self.llm._get_fallback_reply()
            sanitized = self.sanitize_llm_reply(fallback)
            draft_body = f"{greeting}\n\n{sanitized}"
            
            has_sep = "--" in fallback
            has_reg = "best regards" in fallback.lower() or "regards" in fallback.lower()
            has_sig = (ai_settings.email_signature.lower() in fallback.lower()) if ai_settings.email_signature else False
            logger.info(
                "Stage: LLM Fallback Output",
                reply_id=str(thread_id),
                reply_body_length=len(fallback),
                contains_separator=has_sep,
                contains_best_regards=has_reg,
                contains_org_signature=has_sig,
                raw_body=fallback
            )
            
            has_sep = "--" in draft_body
            has_reg = "best regards" in draft_body.lower() or "regards" in draft_body.lower()
            has_sig = (ai_settings.email_signature.lower() in draft_body.lower()) if ai_settings.email_signature else False
            logger.info(
                "Stage: sanitize_llm_reply completed (Fallback)",
                reply_id=str(thread_id),
                reply_body_length=len(draft_body),
                contains_separator=has_sep,
                contains_best_regards=has_reg,
                contains_org_signature=has_sig,
                sanitized_body=draft_body
            )
            
        # 5. Strict assertion before response serialization
        if self._is_signature_present(draft_body, ai_settings.email_signature):
            logger.error("Strict Assertion failed: reply_body contains signature components after sanitization", body=draft_body)
            raise ValueError("Sanitization failed: reply_body still contains signature or signature components.")
            
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
        import time
        start_time = time.perf_counter()
        
        reply_id = payload.reply_id
        graph_message_id = payload.graph_message_id
        sent_at = payload.sent_at

        # 1. Fetch details by reply_id
        res = await self.db.execute(
            text("""
                SELECT id, organization_id, customer_id, thread_id, in_reply_to, delivery_status, graph_message_id, sent_at 
                FROM email_log 
                WHERE id = :reply_id
            """),
            {"reply_id": reply_id}
        )
        row = res.fetchone()
        if not row:
            logger.error("complete_reply - reply not found", reply_id=str(reply_id))
            raise ValueError("reply_not_found")
            
        (
            db_id, org_id, customer_id, thread_id, in_reply_to, 
            curr_delivery_status, curr_graph_message_id, curr_sent_at
        ) = row

        # Log before update
        logger.info(
            "AI Reply Complete Request Received",
            reply_id=str(reply_id),
            delivery_status=curr_delivery_status,
            graph_message_id=curr_graph_message_id,
            sent_at=curr_sent_at.isoformat() if curr_sent_at else None
        )

        # Idempotency check
        if curr_delivery_status == "sent":
            elapsed = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                "AI Reply Complete Idempotent Skip",
                reply_id=str(reply_id),
                graph_message_id=curr_graph_message_id,
                execution_time_ms=elapsed,
                followups_completed=0,
                status="sent"
            )
            return {
                "success": True,
                "reply_id": db_id,
                "graph_message_id": curr_graph_message_id,
                "sent_at": curr_sent_at,
                "delivery_status": "sent"
            }

        followups_completed = 0
        try:
            # 2. Update outbound email log status
            await self.db.execute(
                text("""
                    UPDATE email_log
                    SET delivery_status = 'sent',
                        graph_message_id = :graph_message_id,
                        sent_at = :sent_at,
                        queued_at = NULL
                    WHERE id = :reply_id
                """),
                {
                    "reply_id": reply_id,
                    "graph_message_id": graph_message_id,
                    "sent_at": sent_at
                }
            )

            # 3. Update the parent inbound email's status to 'sent'
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

            # 4. Update follow_up_schedule status if there is a matching schedule
            res_followup = await self.db.execute(
                text("""
                    UPDATE follow_up_schedule
                    SET status = 'completed',
                        completed_at = :sent_at,
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
                    "in_reply_to": in_reply_to,
                    "sent_at": sent_at
                }
            )
            followups_completed = res_followup.rowcount

            # Commit only after all updates succeed
            await self.db.commit()

        except Exception as e:
            logger.exception("AI Reply Complete Failed - rolling back transaction", reply_id=str(reply_id))
            await self.db.rollback()
            raise e

        elapsed = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "AI Reply Complete Success",
            reply_id=str(reply_id),
            graph_message_id=graph_message_id,
            execution_time_ms=elapsed,
            followups_completed=followups_completed,
            status="sent"
        )

        return {
            "success": True,
            "reply_id": reply_id,
            "graph_message_id": graph_message_id,
            "sent_at": sent_at,
            "delivery_status": "sent"
        }

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

    def _is_signature_present(self, text_body: str, sig_config: str | None) -> bool:
        if not text_body:
            return False
        text_lower = text_body.lower()
        forbidden_terms = [
            "--", "best regards", "regards", "thanks & regards",
            "phone", "mobile", "email"
        ]
        if sig_config:
            forbidden_terms.append(sig_config.lower())
        for term in forbidden_terms:
            if term in text_lower:
                return True
        return False

    async def get_operations_dashboard(self, org_id: UUID) -> dict:
        # 1. Waiting for Reply (direction = inbound, status = delivered, and NOT replied to)
        res_waiting = await self.db.execute(
            text("""
                SELECT COUNT(DISTINCT el.thread_id) 
                FROM email_log el
                WHERE el.organization_id = :org_id 
                  AND el.direction = 'inbound' 
                  AND el.delivery_status = 'delivered'
                  AND NOT EXISTS (
                      SELECT 1 FROM email_log outbound 
                      WHERE outbound.organization_id = el.organization_id 
                        AND outbound.direction = 'outbound' 
                        AND (outbound.thread_id = el.thread_id OR outbound.in_reply_to = el.internet_message_id)
                  )
            """),
            {"org_id": org_id}
        )
        waiting_count = res_waiting.scalar() or 0

        # 2. AI Preparing Reply (direction = inbound, status = queued)
        res_preparing = await self.db.execute(
            text("""
                SELECT COUNT(DISTINCT el.thread_id) 
                FROM email_log el
                WHERE el.organization_id = :org_id 
                  AND el.direction = 'inbound' 
                  AND el.delivery_status = 'queued'
            """),
            {"org_id": org_id}
        )
        preparing_count = res_preparing.scalar() or 0

        # 3. Replies Sent Today (direction = outbound, status = sent, sent today)
        res_sent = await self.db.execute(
            text("""
                SELECT COUNT(DISTINCT thread_id) 
                FROM email_log 
                WHERE organization_id = :org_id 
                  AND direction = 'outbound' 
                  AND delivery_status = 'sent' 
                  AND DATE(sent_at) = CURRENT_DATE
            """),
            {"org_id": org_id}
        )
        sent_count = res_sent.scalar() or 0

        # 4. Needs Attention (direction = inbound or outbound, status = failed)
        res_failed = await self.db.execute(
            text("""
                SELECT COUNT(DISTINCT thread_id) 
                FROM email_log 
                WHERE organization_id = :org_id 
                  AND delivery_status = 'failed'
            """),
            {"org_id": org_id}
        )
        failed_count = res_failed.scalar() or 0

        return {
            "waiting_for_reply": waiting_count,
            "ai_preparing_reply": preparing_count,
            "replies_sent_today": sent_count,
            "needs_attention": failed_count
        }

    async def get_operations_list(self, org_id: UUID, search: str | None = None, status: str | None = None) -> list:
        # Wrap the DISTINCT ON subquery so we can order by received_at DESC globally
        query_str = """
            SELECT * FROM (
                SELECT DISTINCT ON (el.thread_id) el.id AS reply_id, el.delivery_status, c.contact_name AS customer_name, 
                       c.company_name, el.subject, el.sent_at AS received_at, el.thread_id, el.graph_message_id,
                       (SELECT sent_at FROM email_log outbound 
                        WHERE outbound.organization_id = el.organization_id 
                          AND outbound.direction = 'outbound' 
                          AND (outbound.thread_id = el.thread_id OR outbound.in_reply_to = el.internet_message_id) 
                        ORDER BY outbound.sent_at DESC LIMIT 1) AS reply_time
                FROM email_log el
                JOIN customers c ON el.customer_id = c.id
                WHERE el.organization_id = :org_id
                  AND el.direction = 'inbound'
        """
        params = {"org_id": org_id}

        if status:
            if status == "Waiting for Reply":
                query_str += """ AND el.delivery_status = 'delivered'
                  AND NOT EXISTS (
                      SELECT 1 FROM email_log outbound 
                      WHERE outbound.organization_id = el.organization_id 
                        AND outbound.direction = 'outbound' 
                        AND (outbound.thread_id = el.thread_id OR outbound.in_reply_to = el.internet_message_id)
                  )"""
            elif status == "AI Preparing Reply":
                query_str += " AND el.delivery_status = 'queued'"
            elif status == "Reply Sent":
                query_str += " AND el.delivery_status = 'sent'"
            elif status == "Needs Attention":
                query_str += " AND el.delivery_status = 'failed'"

        if search:
            query_str += " AND (c.contact_name ILIKE :search OR c.company_name ILIKE :search OR el.subject ILIKE :search)"
            params["search"] = f"%{search}%"

        query_str += """
                ORDER BY el.thread_id, el.sent_at DESC
            ) sub
            ORDER BY sub.received_at DESC
        """

        res = await self.db.execute(text(query_str), params)
        rows = res.fetchall()

        items = []
        for r in rows:
            items.append({
                "reply_id": r.reply_id,
                "delivery_status": r.delivery_status,
                "customer_name": r.customer_name,
                "company_name": r.company_name,
                "subject": r.subject,
                "received_at": r.received_at,
                "thread_id": r.thread_id,
                "graph_message_id": r.graph_message_id,
                "reply_time": r.reply_time
            })
        return items

    async def get_operations_detail(self, org_id: UUID, reply_id: UUID) -> dict:
        import re
        def clean_html(raw_html: str) -> str:
            if not raw_html:
                return ""
            text = re.sub(r'<style[^>]*>.*?</style>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'<tr[^>]*>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</td>', '\t', text, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
            
            cleaned_lines = []
            for line in text.split('\n'):
                s_line = line.strip()
                if s_line:
                    s_line = re.sub(r'[ \t]+', ' ', s_line)
                    cleaned_lines.append(s_line)
                else:
                    if cleaned_lines and cleaned_lines[-1] != "":
                        cleaned_lines.append("")
            return '\n'.join(cleaned_lines).strip()

        res = await self.db.execute(
            text("""
                SELECT el.id, el.subject, el.body, el.sent_at AS received_at, el.queued_at, el.delivery_status, el.thread_id, el.internet_message_id,
                       c.contact_name AS customer_name, c.company_name, c.contact_email, settings.default_cc_emails
                FROM email_log el
                JOIN customers c ON el.customer_id = c.id
                JOIN organization_ai_settings settings ON el.organization_id = settings.organization_id
                WHERE el.id = :reply_id AND el.organization_id = :org_id
            """),
            {"reply_id": reply_id, "org_id": org_id}
        )
        row = res.fetchone()
        if not row:
            raise ValueError("reply_not_found")

        (
            db_id, subject, original_body, received_at, queued_at, delivery_status, thread_id, internet_message_id,
            customer_name, company_name, customer_email, default_cc
        ) = row

        clean_customer_msg = clean_html(original_body)

        res_out = await self.db.execute(
            text("""
                SELECT body, sent_at FROM email_log 
                WHERE organization_id = :org_id 
                  AND direction = 'outbound' 
                  AND (thread_id = :thread_id OR in_reply_to = :internet_message_id)
                ORDER BY sent_at DESC LIMIT 1
            """),
            {"org_id": org_id, "thread_id": thread_id, "internet_message_id": internet_message_id}
        )
        row_out = res_out.fetchone()
        final_sent_html = row_out[0] if row_out else None
        sent_at = row_out[1] if row_out else None

        clean_final_sent = clean_html(final_sent_html) if final_sent_html else None

        cc_list = []
        if default_cc:
            if isinstance(default_cc, str):
                try:
                    import json
                    cc_list = json.loads(default_cc)
                except Exception:
                    cc_list = []
            elif isinstance(default_cc, list):
                cc_list = default_cc

        recipients = {
            "to": [customer_email],
            "cc": cc_list,
            "bcc": []
        }

        timeline = []
        if received_at:
            timeline.append({"stage": "Customer Email Received", "timestamp": received_at})
        if queued_at:
            timeline.append({"stage": "AI Reply Prepared", "timestamp": queued_at})
        if delivery_status == 'sent' and sent_at:
            timeline.append({"stage": "Reply Sent Successfully", "timestamp": sent_at})

        return {
            "reply_id": db_id,
            "customer_name": customer_name,
            "company_name": company_name,
            "customer_email": customer_email,
            "subject": subject,
            "received_at": received_at,
            "original_body": clean_customer_msg,
            "final_sent": clean_final_sent,
            "final_sent_html": final_sent_html,
            "recipients": recipients,
            "timeline": timeline
        }

