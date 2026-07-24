import uuid
import time
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger
from app.clients.microsoft_graph_client import MicrosoftGraphClient
from app.services.token_service import TokenService

logger = get_logger(__name__)

class InboundSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.graph_client = MicrosoftGraphClient()
        self.token_service = TokenService(db)

    async def sync_all_active_mailboxes(self, organization_ids: list = None) -> dict:
        """
        Main runner: loads all active integrations, performs isolated sync,
        and aggregates processed statistics. Optionally filters by organization_ids.
        """
        start_time = time.time()
        # Load active mailboxes
        query = """
            SELECT id, organization_id, mailbox_email, last_graph_delta_link 
            FROM tenant_integrations 
            WHERE is_active = true
        """
        params = {}
        if organization_ids:
            query += " AND organization_id = ANY(:org_ids)"
            params["org_ids"] = list(organization_ids)

        res = await self.db.execute(text(query), params)
        integrations = res.fetchall()

        logger.info(f"Loaded {len(integrations)} active tenant integrations for synchronization.")

        # Log skipped inactive mailboxes for visibility
        inactive_query = """
            SELECT mailbox_email, organization_id 
            FROM tenant_integrations 
            WHERE is_active = false
        """
        if organization_ids:
            inactive_query += " AND organization_id = ANY(:org_ids)"
        
        inactive_res = await self.db.execute(text(inactive_query), params)
        for inactive_row in inactive_res.fetchall():
            logger.info(
                "Skipping synchronization because the mailbox integration is inactive.",
                org_id=str(inactive_row[1]),
                mailbox=inactive_row[0],
                reason="is_active = false"
            )

        stats = {
            "organizations_processed": 0,
            "mailboxes_processed": 0,
            "messages_scanned": 0,
            "messages_inserted": 0,
            "duplicates_skipped": 0,
            "reply_detected": 0,
            "schedules_completed": 0,
            "campaigns_completed": 0,
            "messages_skipped_unknown_sender": 0,
            "reply_candidates": 0,
            "reply_matches": 0,
            "errors": [],
            "duration_seconds": 0
        }

        for row in integrations:
            integration_id = row[0]
            org_id = row[1]
            mailbox_email = row[2]
            delta_link = row[3]

            logger.info("Initializing inbox delta sync for mailbox", org_id=str(org_id), mailbox=mailbox_email)
            try:
                # 1. Update sync_started_at
                await self.db.execute(text("""
                    UPDATE tenant_integrations
                    SET sync_started_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                """), {"id": integration_id})
                await self.db.commit()

                # 2. Refresh/Retrieve access token
                access_token = await self.token_service.get_valid_access_token(org_id)

                # 3. Fetch messages using Graph Delta Query
                delta_res = await self.graph_client.fetch_inbox_messages_delta(access_token, delta_link)
                messages = delta_res.get("messages", [])
                new_delta_link = delta_res.get("delta_link")

                stats["mailboxes_processed"] += 1
                stats["organizations_processed"] += 1

                # 4. Process each message
                for msg in messages:
                    stats["messages_scanned"] += 1
                    processed = await self._process_inbound_message(org_id, msg, mailbox_email)
                    if processed["inserted"]:
                        stats["messages_inserted"] += 1
                    elif processed["skipped"]:
                        stats["duplicates_skipped"] += 1
                    elif processed.get("skipped_unknown_sender"):
                        stats["messages_skipped_unknown_sender"] += 1

                    if processed["reply_detected"]:
                        stats["reply_detected"] += 1
                        stats["reply_matches"] += 1
                    if processed.get("reply_candidate"):
                        stats["reply_candidates"] += 1
                    if processed.get("schedule_completed"):
                        stats["schedules_completed"] += 1
                    if processed.get("campaign_completed"):
                        stats["campaigns_completed"] += 1

                # 5. Update completed state and delta links
                await self.db.execute(text("""
                    UPDATE tenant_integrations
                    SET last_graph_delta_link = :delta_link,
                        sync_completed_at = NOW(),
                        last_successful_sync = NOW(),
                        last_sync_error = NULL,
                        updated_at = NOW()
                    WHERE id = :id
                """), {"id": integration_id, "delta_link": new_delta_link})
                await self.db.commit()

            except Exception as e:
                await self.db.rollback()
                err_msg = f"Mailbox {mailbox_email} failed: {str(e)}"
                stats["errors"].append(err_msg)
                logger.error("Failed to sync mailbox", org_id=str(org_id), mailbox=mailbox_email, error=str(e))
                
                try:
                    await self.db.execute(text("""
                        UPDATE tenant_integrations
                        SET last_sync_error = :err,
                            updated_at = NOW()
                        WHERE id = :id
                    """), {"id": integration_id, "err": str(e)})
                    await self.db.commit()
                except Exception as inner_err:
                    logger.error("Failed to write sync error to database", error=str(inner_err))
                    await self.db.rollback()

        stats["duration_seconds"] = int(time.time() - start_time)
        return stats

    async def _process_inbound_message(self, org_id: uuid.UUID, msg: dict, mailbox_email: str = "unknown_mailbox") -> dict:
        """
        Deduplicates, inserts inbound message into email_log, and triggers reply matching.
        """
        result = {
            "inserted": False,
            "skipped": False,
            "skipped_unknown_sender": False,
            "reply_candidate": False,
            "reply_detected": False,
            "schedule_completed": False,
            "campaign_completed": False
        }
        graph_message_id = msg.get("id")
        internet_message_id = msg.get("internetMessageId")
        conversation_id = msg.get("conversationId")

        if not graph_message_id:
            return result

        # Priority Deduplication: Check if already stored by checking graph ID, internet message ID, or conversation thread + message ID
        dup_check = await self.db.execute(text("""
            SELECT 1 FROM email_log 
            WHERE (graph_message_id = CAST(:g_id AS VARCHAR) AND :g_id IS NOT NULL)
               OR (internet_message_id = CAST(:i_id AS VARCHAR) AND :i_id IS NOT NULL)
               OR (conversation_id = CAST(:c_id AS VARCHAR) AND internet_message_id = CAST(:i_id AS VARCHAR) AND :c_id IS NOT NULL AND :i_id IS NOT NULL)
            LIMIT 1
        """), {
            "g_id": graph_message_id,
            "i_id": internet_message_id,
            "c_id": conversation_id
        })
        if dup_check.fetchone():
            logger.info("Duplicate message skipped", graph_message_id=graph_message_id)
            result["skipped"] = True
            return result

        # Parse from address and check customer matching
        from_dict = msg.get("from", {})
        from_email = from_dict.get("emailAddress", {}).get("address")
        if not from_email:
            return result

        # Retrieve matching customer
        cust_check = await self.db.execute(text("""
            SELECT id FROM customers 
            WHERE contact_email = :email AND organization_id = :org_id 
            LIMIT 1
        """), {"email": from_email, "org_id": org_id})
        cust_row = cust_check.fetchone()
        customer_id = cust_row[0] if cust_row else None

        if not customer_id:
            logger.info(
                "Skipping inbound message because sender is unknown",
                mailbox=mailbox_email,
                sender_email=from_email,
                subject=msg.get("subject", ""),
                reason="Unknown sender"
            )
            result["skipped_unknown_sender"] = True
            return result

        result["reply_candidate"] = True

        # Retrieve extended properties (references & in-reply-to)
        references = None
        in_reply_to = None
        for prop in msg.get("singleValueExtendedProperties", []):
            if prop.get("id") == "String 0x1039":
                references = prop.get("value")
            elif prop.get("id") == "String 0x1042":
                in_reply_to = prop.get("value")

        # Parse dates
        received_str = msg.get("receivedDateTime")
        received_at = datetime.now(timezone.utc)
        if received_str:
            try:
                received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
            except Exception:
                pass

        # Insert email_log
        log_id = uuid.uuid4()
        subject = msg.get("subject", "")
        body = msg.get("body", {}).get("content", "")
        has_attachments = msg.get("hasAttachments", False)

        await self.db.execute(text("""
            INSERT INTO email_log (
                id, organization_id, customer_id, direction, email_type, 
                subject, body, has_attachment, sent_at, received_at, 
                delivery_status, graph_message_id, conversation_id, thread_id, 
                internet_message_id, "references", in_reply_to, created_at
            ) VALUES (
                :id, :org_id, :customer_id, 'inbound', 'followup', 
                :subject, :body, :has_attachment, :received_at, :received_at, 
                'delivered', :graph_message_id, CAST(:conversation_id AS VARCHAR), CAST(:thread_id AS VARCHAR), 
                :internet_message_id, :references, :in_reply_to, NOW()
            )
        """), {
            "id": log_id,
            "org_id": org_id,
            "customer_id": customer_id,
            "subject": subject,
            "body": body,
            "has_attachment": has_attachments,
            "received_at": received_at,
            "graph_message_id": graph_message_id,
            "conversation_id": conversation_id,
            "thread_id": conversation_id,
            "internet_message_id": internet_message_id,
            "references": references,
            "in_reply_to": in_reply_to
        })
        await self.db.commit()
        result["inserted"] = True

        # Perform Reply Detection if sender matches a customer
        if customer_id:
            reply_result = await self._run_reply_detection(
                org_id=org_id,
                customer_id=customer_id,
                from_email=from_email,
                subject=subject,
                conversation_id=conversation_id,
                internet_message_id=internet_message_id,
                in_reply_to=in_reply_to,
                references=references,
                received_at=received_at,
                graph_message_id=graph_message_id
            )
            result["reply_detected"] = reply_result.get("matched", False)
            result["schedule_completed"] = reply_result.get("schedule_completed", False)
            result["campaign_completed"] = reply_result.get("campaign_completed", False)

        return result

    async def _run_reply_detection(
        self, org_id: uuid.UUID, customer_id: uuid.UUID, from_email: str,
        subject: str, conversation_id: str, internet_message_id: str,
        in_reply_to: str, references: str, received_at: datetime, graph_message_id: str
    ) -> dict:
        """
        Production-grade thread-centric reply matching and filtering.
        """
        import re
        res_dict = {"matched": False, "schedule_completed": False, "campaign_completed": False}

        # 1. Filter out false positives (OOO, bounces, notifications)
        subj_lower = subject.lower()
        auto_subjects = [
            "out of office", "automatic response", "auto reply", "autoresponse", 
            "vacation", "delivery status notification", "delivery failure", 
            "undeliverable", "returned mail", "mail delivery failure", "bounce",
            "spam notification"
        ]
        if any(pat in subj_lower for pat in auto_subjects):
            logger.info("Ignored false positive subject pattern", subject=subject)
            return res_dict

        # Load active sequence settings
        settings_res = await self.db.execute(text("""
            SELECT stop_on_reply FROM organization_engagement_settings 
            WHERE organization_id = :org_id
        """), {"org_id": org_id})
        settings_row = settings_res.fetchone()
        stop_on_reply = bool(settings_row[0]) if settings_row else False

        # Load previous outbound emails sent to this customer from this organization
        outbound_res = await self.db.execute(text("""
            SELECT id, sent_at, subject, conversation_id, internet_message_id 
            FROM email_log
            WHERE customer_id = :cust_id 
              AND organization_id = :org_id
              AND direction = 'outbound'
              AND email_type IN ('engagement', 'followup')
            ORDER BY sent_at DESC
        """), {"cust_id": customer_id, "org_id": org_id})
        outbound_emails = outbound_res.fetchall()

        if not outbound_emails:
            logger.info("No previous outbound emails found for customer. Skipping reply matching.", customer_id=str(customer_id))
            return res_dict

        # Thread Matching Logic
        matched = False
        reason = ""
        matched_outbound = None

        # Rule 1: In-Reply-To
        if not matched and in_reply_to:
            for out in outbound_emails:
                if out[4] and out[4].strip() == in_reply_to.strip():
                    matched = True
                    reason = "Matched In-Reply-To headers"
                    matched_outbound = out
                    break

        # Rule 2: References
        if not matched and references:
            for out in outbound_emails:
                if out[4] and out[4].strip() in references:
                    matched = True
                    reason = "Matched References headers"
                    matched_outbound = out
                    break

        # Rule 3: Internet Message ID
        if not matched and internet_message_id:
            for out in outbound_emails:
                if out[4] and out[4].strip() == internet_message_id.strip():
                    matched = True
                    reason = "Matched internetMessageId"
                    matched_outbound = out
                    break

        # Rule 4: Conversation ID / Thread ID
        if not matched and conversation_id:
            for out in outbound_emails:
                if out[3] and out[3].strip() == conversation_id.strip():
                    matched = True
                    reason = "Matched conversationId"
                    matched_outbound = out
                    break

        # Rule 5: Normalized Subject (Fallback)
        if not matched:
            def normalize_sub(s):
                if not s:
                    return ""
                return re.sub(r'^(re|fwd|reply|aw|ref):\s*', '', s, flags=re.IGNORECASE).strip().lower()
            
            norm_inbound = normalize_sub(subject)
            for out in outbound_emails:
                if out[2] and normalize_sub(out[2]) == norm_inbound:
                    matched = True
                    reason = "Matched Subject normalization"
                    matched_outbound = out
                    break

        # Verification: Timestamp fallback validation (reply sent after outbound)
        if matched and matched_outbound:
            source_sent_at = matched_outbound[1]
            if received_at <= source_sent_at:
                logger.info("Reply discarded because received timestamp is older than source sent date")
                return res_dict

        if matched:
            logger.info("Reply matching success", reason=reason, customer_id=str(customer_id))
            res_dict["matched"] = True

            # Find if there is an active follow-up schedule item for this customer
            sched_res = await self.db.execute(text("""
                SELECT s.id, s.step_number, s.campaign_id
                FROM follow_up_schedule s
                WHERE s.organization_id = :org_id 
                  AND s.customer_id = :cust_id 
                  AND CAST(s.status AS VARCHAR) IN ('pending', 'paused', 'scheduled')
                ORDER BY s.step_number ASC
                LIMIT 1
            """), {"org_id": org_id, "cust_id": customer_id})
            sched_row = sched_res.fetchone()

            if sched_row:
                schedule_id = sched_row[0]
                campaign_id = sched_row[2]

                # Update reply detection metadata
                await self.db.execute(text("""
                    UPDATE follow_up_schedule
                    SET reply_detected_at = NOW(),
                        reply_message_id = :msg_id,
                        reply_thread_id = :conv_id,
                        reply_subject = :subject,
                        reply_from = :from_email,
                        reply_reason = :reason,
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": schedule_id,
                    "msg_id": graph_message_id,
                    "conv_id": conversation_id,
                    "subject": subject,
                    "from_email": from_email,
                    "reason": reason
                })

                # If stop-on-reply sequence rule enabled
                if stop_on_reply:
                    await self.db.execute(text("""
                        UPDATE follow_up_schedule
                        SET status = 'completed',
                            completed_at = NOW(),
                            updated_at = NOW()
                        WHERE id = :id
                    """), {"id": schedule_id})
                    res_dict["schedule_completed"] = True

                    # Terminate active campaign enrollment sequence
                    if campaign_id:
                        await self.db.execute(text("""
                            UPDATE campaign_enrollments
                            SET enrollment_status = 'completed',
                                exited_at = NOW(),
                                exit_reason = :reason,
                                updated_at = NOW()
                            WHERE customer_id = :cust_id 
                              AND campaign_id = :camp_id 
                              AND enrollment_status = 'active'
                        """), {
                            "cust_id": customer_id,
                            "campaign_id": campaign_id,
                            "reason": f"Reply detected: {reason}"
                        })
                        res_dict["campaign_completed"] = True
                    else:
                        await self.db.execute(
                            text("""
                                UPDATE campaign_enrollments
                                SET enrollment_status = 'completed',
                                    exited_at = NOW(),
                                    exit_reason = :reason,
                                    updated_at = NOW()
                                WHERE customer_id = :cust_id AND organization_id = :org_id AND enrollment_status = 'active'
                            """),
                            {"cust_id": customer_id, "org_id": org_id, "reason": f"Reply detected: {reason}"}
                        )
                        res_dict["campaign_completed"] = True

            await self.db.commit()

        return res_dict
