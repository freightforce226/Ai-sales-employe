from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
import re
import html
from app.schemas.journey import JourneyEvent, CustomerJourneyResponse

def to_business_reason(reason: Optional[str]) -> str:
    if not reason:
        return "The customer replied to your email. Automation has been paused until you continue the conversation."
    reason_lower = reason.lower()
    if any(pat in reason_lower for pat in ("in-reply-to", "references", "subject normalization", "conversationid", "reply detected", "stopped by reply")):
        return "The customer replied to your email. Automation has been paused until you continue the conversation."
    if "sequence stopped" in reason_lower:
        return "Automation Paused"
    return reason

def normalize_email_body(body: str) -> str:
    if not body:
        return ""
    
    # 1. Convert HTML to readable plain text
    text = re.sub(r'<style([\s\S]*?)<\/style>', '', body, flags=re.IGNORECASE)
    text = re.sub(r'<script([\s\S]*?)<\/script>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<head([\s\S]*?)<\/head>', '', text, flags=re.IGNORECASE)
    
    text = re.sub(r'</div\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p\s*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li\s*>', '  * ', text, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    text = re.sub(r'<[^>]+>', '', text)
    
    # 2. Decode HTML entities
    text = html.unescape(text)
    
    # 3. Clean up MIME artifacts & Transport Headers
    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        if re.match(r'^(MIME-Version|Content-Type|Content-Transfer-Encoding|Message-ID|X-Outlook|Thread-Topic|Thread-Index|References|In-Reply-To):', line, re.IGNORECASE):
            continue
        clean_lines.append(line)
    text = "\n".join(clean_lines)
    
    # 4. Handle Outlook Quoted Junk / History
    quote_markers = [
        r'From:\s+',
        r'________________________________',
        r'Original Message',
        r'^-+ Original Message -+$',
        r'^On\s+.*,\s+.*wrote:$',
        r'^On\s+.*wrote:$'
    ]
    
    split_idx = -1
    for marker in quote_markers:
        match = re.search(marker, text, re.IGNORECASE | re.MULTILINE)
        if match:
            if split_idx == -1 or match.start() < split_idx:
                split_idx = match.start()
                
    if split_idx != -1:
        reply_part = text[:split_idx].strip()
        quoted_part = text[split_idx:].strip()
        quoted_clean = re.sub(r'^(From|To|Sent|Date|Subject|Cc):.*$', '', quoted_part, flags=re.IGNORECASE | re.MULTILINE)
        quoted_clean = "\n".join([l for l in quoted_clean.splitlines() if l.strip()])
        
        text = reply_part + "\n\n------------------------------\nPrevious Email\n------------------------------\n\n" + quoted_clean
        
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()

def find_matching_email(schedule_row, all_emails, matched_email_ids) -> Optional[tuple]:
    s_id, step_num, status, scheduled_dt, completed_at, reply_detected_at, reply_reason, message_id, reply_thread_id, reply_subject, *extra = schedule_row
    
    # 1. Message ID
    if message_id:
        for email in all_emails:
            if email[1] == 'outbound' and email[8] == message_id and email[0] not in matched_email_ids:
                return email
                
    # 2. Reply Thread
    if reply_thread_id:
        for email in all_emails:
            if email[1] == 'outbound' and email[12] == reply_thread_id and email[0] not in matched_email_ids:
                return email
                
    # 3. Conversation ID / Thread ID fallback
    if reply_thread_id:
        for email in all_emails:
            if email[1] == 'outbound' and email[12] == reply_thread_id and email[0] not in matched_email_ids:
                return email

    # 4. Subject similarity
    if reply_subject:
        clean_reply_sub = reply_subject.lower().replace("re:", "").replace("fw:", "").strip()
        for email in all_emails:
            if email[1] == 'outbound' and email[0] not in matched_email_ids:
                clean_email_sub = email[2].lower().replace("re:", "").replace("fw:", "").strip()
                if clean_reply_sub and clean_email_sub and (clean_reply_sub in clean_email_sub or clean_email_sub in clean_reply_sub):
                    return email

    # 5. Customer + Step + Timestamp window
    target_dt = completed_at or scheduled_dt
    if target_dt:
        for email in all_emails:
            if email[1] == 'outbound' and email[0] not in matched_email_ids:
                email_dt = email[4] or email[9]
                if email_dt:
                    diff = abs((email_dt - target_dt).total_seconds())
                    if diff <= 3600: # 1 hour window
                        return email
                        
    return None

class CustomerJourneyService:
    def __init__(self, db: AsyncSession, org_id: UUID):
        self.db = db
        self.org_id = org_id

    async def get_journey(self, customer_id: UUID) -> CustomerJourneyResponse:
        timeline: List[JourneyEvent] = []

        # 0. Fetch sender display name dynamically (joining org, tenant_integrations and users)
        sender_res = await self.db.execute(
            text("""
                SELECT u.full_name, o.display_name 
                FROM organizations o
                LEFT JOIN tenant_integrations ti ON o.id = ti.organization_id
                LEFT JOIN users u ON ti.mailbox_email = u.email
                WHERE o.id = :org_id
                LIMIT 1
            """),
            {"org_id": self.org_id}
        )
        sender_row = sender_res.fetchone()
        if sender_row:
            user_full_name, org_display_name = sender_row
            sender_display_name = user_full_name or org_display_name or "Amplus Agent"
        else:
            sender_display_name = "Amplus Agent"

        # 1. Fetch Customer details, CSV batch, and Campaign Enrollment
        c_res = await self.db.execute(
            text("""
                SELECT c.created_at, c.import_batch_id, ib.file_name, c.contact_email,
                       (SELECT CAST(ce.enrollment_status AS VARCHAR) FROM campaign_enrollments ce WHERE ce.customer_id = c.id ORDER BY ce.created_at DESC LIMIT 1) as enrollment_status,
                       (SELECT ce.exit_reason FROM campaign_enrollments ce WHERE ce.customer_id = c.id ORDER BY ce.created_at DESC LIMIT 1) as exit_reason
                FROM customers c
                LEFT JOIN import_batches ib ON c.import_batch_id = ib.id
                WHERE c.id = :customer_id AND c.organization_id = :org_id AND c.deleted_at IS NULL
            """),
            {"customer_id": customer_id, "org_id": self.org_id}
        )
        c_row = c_res.fetchone()
        if not c_row:
            return CustomerJourneyResponse(customer_id=customer_id, timeline=[])

        created_at, batch_id, batch_name, contact_email, enrollment_status, exit_reason = c_row

        # Add Customer Imported Event
        csv_time = created_at.astimezone(timezone.utc).isoformat() if created_at else datetime.now(timezone.utc).isoformat()
        timeline.append(JourneyEvent(
            id=f"csv-import-{customer_id}",
            module="CSV",
            event_type="csv_imported",
            status="completed",
            timestamp=csv_time,
            title="Customer Imported",
            subtitle=f"Imported from {batch_name}" if batch_name else "Manual Import",
            icon="UploadCloud",
            color="blue",
            expandable=False,
            description=f"Customer registered in workspace via {batch_name or 'manual input'}."
        ))

        # 2. Fetch all Email Logs for the customer
        email_res = await self.db.execute(
            text("""
                SELECT id, direction, subject, body, sent_at, received_at, replied_at, delivery_status, graph_message_id, created_at, has_attachment, CAST(email_type AS VARCHAR), thread_id
                FROM email_log
                WHERE customer_id = :customer_id AND organization_id = :org_id
                ORDER BY created_at ASC
            """),
            {"customer_id": customer_id, "org_id": self.org_id}
        )
        all_emails = email_res.fetchall()

        # Batch fetch all attachments for the customer's emails to avoid N+1 queries
        attachments_res = await self.db.execute(
            text("""
                SELECT email_log_id, file_name 
                FROM email_attachments 
                WHERE email_log_id IN (
                    SELECT id FROM email_log WHERE customer_id = :customer_id AND organization_id = :org_id
                )
            """),
            {"customer_id": customer_id, "org_id": self.org_id}
        )
        attachments_map = {}
        for att_row in attachments_res.fetchall():
            el_id_str = str(att_row[0])
            att_name = att_row[1]
            if el_id_str not in attachments_map:
                attachments_map[el_id_str] = []
            attachments_map[el_id_str].append(att_name)

        # 3. Fetch Follow-up Schedule Events
        schedule_res = await self.db.execute(
            text("""
                SELECT id, step_number, status, scheduled_datetime, completed_at, reply_detected_at, reply_reason, message_id, reply_thread_id, reply_subject, draft_status
                FROM follow_up_schedule
                WHERE customer_id = :customer_id AND organization_id = :org_id
                ORDER BY step_number ASC
            """),
            {"customer_id": customer_id, "org_id": self.org_id}
        )
        all_schedules = schedule_res.fetchall()

        schedule_msg_ids = {row[7] for row in all_schedules if row[7]}
        email_map_by_msg_id = {row[8]: row for row in all_emails if row[8]}

        # Build timeline from Email Logs (filtering out follow-ups)
        for row in all_emails:
            e_id, direction, subject, body, sent_at, received_at, replied_at, delivery_status, graph_msg_id, created_at, has_attachment, email_type, thread_id = row
            
            is_followup = (direction == 'outbound') and (graph_msg_id in schedule_msg_ids)
            if is_followup:
                continue

            atts = attachments_map.get(str(e_id), [])
            t_val = sent_at or received_at or created_at
            t_iso = t_val.astimezone(timezone.utc).isoformat() if t_val else datetime.now(timezone.utc).isoformat()

            if direction == "inbound":
                timeline.append(JourneyEvent(
                    id=str(e_id),
                    module="AI Reply",
                    event_type="reply_received",
                    status="Finished",
                    timestamp=t_iso,
                    title="Customer Replied",
                    subtitle=subject,
                    icon="Mail",
                    color="emerald",
                    expandable=True,
                    description=f"Customer reply received from {contact_email}.",
                    mail={
                        "id": str(e_id),
                        "subject": subject,
                        "body": normalize_email_body(body),
                        "direction": "Customer Reply",
                        "message_id": None,
                        "thread_id": None,
                        "delivery_status": "Finished",
                        "sender": contact_email,
                        "recipient": sender_display_name,
                        "timestamp": t_iso,
                        "email_type": "reply"
                    },
                    attachments=atts
                ))
            elif direction == "outbound":
                if email_type == 'reply':
                    if delivery_status == 'pending_review':
                        timeline.append(JourneyEvent(
                            id=str(e_id),
                            module="AI Reply",
                            event_type="ai_reply_drafted",
                            status="pending",
                            timestamp=t_iso,
                            title="AI Reply Drafted",
                            subtitle="Waiting for Approval",
                            icon="Bot",
                            color="purple",
                            expandable=True,
                            description="AI generated draft response to customer reply.",
                            mail={
                                "id": str(e_id),
                                "subject": subject,
                                "body": normalize_email_body(body),
                                "direction": "Email Sent",
                                "delivery_status": "Waiting for Approval",
                                "message_id": None,
                                "thread_id": None,
                                "sender": sender_display_name,
                                "recipient": contact_email,
                                "timestamp": t_iso,
                                "email_type": "reply_draft"
                            },
                            attachments=atts
                        ))
                    else:
                        timeline.append(JourneyEvent(
                            id=str(e_id),
                            module="AI Reply",
                            event_type="ai_reply_sent",
                            status="Finished",
                            timestamp=t_iso,
                            title="Email Sent",
                            subtitle=subject,
                            icon="CheckSquare",
                            color="emerald",
                            expandable=True,
                            description="AI draft approved and reply sent to customer.",
                            mail={
                                "id": str(e_id),
                                "subject": subject,
                                "body": normalize_email_body(body),
                                "direction": "Email Sent",
                                "delivery_status": delivery_status or "sent",
                                "message_id": None,
                                "thread_id": None,
                                "sender": sender_display_name,
                                "recipient": contact_email,
                                "timestamp": t_iso,
                                "email_type": "reply_sent"
                            },
                            attachments=atts
                        ))
                else:
                    is_failed = delivery_status in ("failed", "bounced")
                    title = "Email Sent Failed" if is_failed else "Email Sent"
                    color = "red" if is_failed else "emerald"
                    timeline.append(JourneyEvent(
                        id=str(e_id),
                        module="Engagement",
                        event_type="email_failed" if is_failed else "email_sent",
                        status=delivery_status or "sent",
                        timestamp=t_iso,
                        title=title,
                        subtitle=subject,
                        icon="Send",
                        color=color,
                        expandable=True,
                        description=f"Outreach message sent to {contact_email}.",
                        mail={
                            "id": str(e_id),
                            "subject": subject,
                            "body": normalize_email_body(body),
                            "direction": "Email Sent",
                            "delivery_status": delivery_status or "sent",
                            "message_id": None,
                            "thread_id": None,
                            "sender": sender_display_name,
                            "recipient": contact_email,
                            "timestamp": t_iso,
                            "email_type": "initial_outreach"
                        },
                        attachments=atts
                    ))

        # Build timeline from follow-up schedule
        is_sequence_stopped = (enrollment_status in ('completed', 'exited')) or any(row[5] is not None for row in all_schedules)
        matched_email_ids = set()

        for row in all_schedules:
            s_id, step_num, status, scheduled_dt, completed_at, reply_detected_at, reply_reason, message_id, reply_thread_id, reply_subject, draft_status = row

            mail_row = find_matching_email(row, all_emails, matched_email_ids)

            if mail_row:
                e_id, _, subject, body, sent_at, received_at, replied_at, delivery_status, graph_msg_id, created_at, has_attachment, email_type, thread_id = mail_row
                matched_email_ids.add(e_id)
                atts = attachments_map.get(str(e_id), [])
                t_val = sent_at or created_at or completed_at
                t_iso = t_val.astimezone(timezone.utc).isoformat() if t_val else datetime.now(timezone.utc).isoformat()
                is_failed = delivery_status in ("failed", "bounced")

                timeline.append(JourneyEvent(
                    id=str(s_id),
                    module="Follow-up Email",
                    event_type="followup_sent",
                    status=delivery_status or "sent",
                    timestamp=t_iso,
                    title="Email Sent",
                    subtitle=f"Follow-up Email Step {step_num}: {subject}",
                    icon="CheckCircle",
                    color="red" if is_failed else "emerald",
                    expandable=True,
                    description=f"Follow-up email step {step_num} sent successfully.",
                    mail={
                        "id": str(e_id),
                        "subject": subject,
                        "body": normalize_email_body(body),
                        "direction": "Email Sent",
                        "delivery_status": delivery_status or "sent",
                        "message_id": None,
                        "thread_id": None,
                        "sender": sender_display_name,
                        "recipient": contact_email,
                        "timestamp": t_iso,
                        "email_type": "followup"
                    },
                    attachments=atts,
                    step_number=step_num
                ))
            else:
                t_val = completed_at or reply_detected_at or scheduled_dt or datetime.now(timezone.utc)
                t_iso = t_val.astimezone(timezone.utc).isoformat()

                if draft_status == 'pending_review':
                    timeline.append(JourneyEvent(
                        id=f"sched-pending-{s_id}",
                        module="Follow-up Email",
                        event_type="followup_pending_review",
                        status="pending",
                        timestamp=t_iso,
                        title="Waiting for Approval",
                        subtitle=f"Follow-up Email Step {step_num}",
                        icon="Calendar",
                        color="indigo",
                        expandable=False,
                        description=f"Follow-up email step {step_num} is waiting for supervisor approval.",
                        step_number=step_num
                    ))
                elif status in ('pending', 'scheduled'):
                    if not is_sequence_stopped:
                        timeline.append(JourneyEvent(
                            id=f"sched-{s_id}",
                            module="Follow-up Email",
                            event_type="followup_scheduled",
                            status=status,
                            timestamp=t_iso,
                            title="Email Scheduled",
                            subtitle=f"Follow-up Email Step {step_num}",
                            icon="Calendar",
                            color="indigo",
                            expandable=False,
                            description=f"Automatic follow-up scheduled to run at {scheduled_dt}.",
                            step_number=step_num
                        ))
                elif status == 'cancelled':
                    timeline.append(JourneyEvent(
                        id=f"sched-cancelled-{s_id}",
                        module="Follow-up Email",
                        event_type="cancelled",
                        status=status,
                        timestamp=t_iso,
                        title="Cancelled",
                        subtitle=f"Follow-up Email Step {step_num}",
                        icon="X",
                        color="slate",
                        expandable=False,
                        description=f"Follow-up email step {step_num} was cancelled.",
                        step_number=step_num
                    ))
                elif status == 'skipped':
                    timeline.append(JourneyEvent(
                        id=f"sched-skipped-{s_id}",
                        module="Follow-up Email",
                        event_type="skipped",
                        status=status,
                        timestamp=t_iso,
                        title="Skipped",
                        subtitle=f"Follow-up Email Step {step_num}",
                        icon="Clock",
                        color="slate",
                        expandable=False,
                        description=f"Follow-up email step {step_num} was skipped.",
                        step_number=step_num
                    ))

            if reply_detected_at:
                rep_iso = reply_detected_at.astimezone(timezone.utc).isoformat()
                timeline.append(JourneyEvent(
                    id=f"stop-{s_id}",
                    module="Follow-up Email",
                    event_type="sequence_stopped",
                    status="completed",
                    timestamp=rep_iso,
                    title="Automation Paused",
                    subtitle="The customer replied to your email. Automation has been paused until you continue the conversation.",
                    icon="X",
                    color="red",
                    expandable=False,
                    description="Automation paused.",
                    step_number=step_num
                ))

        # Sort the base timeline chronologically (oldest -> newest)
        timeline.sort(key=lambda x: x.timestamp)

        # Inject "Wait" events dynamically
        final_timeline: List[JourneyEvent] = []
        for i, event in enumerate(timeline):
            if i > 0 and event.event_type in ("followup_sent", "followup_scheduled"):
                prev_event = timeline[i-1]
                if prev_event.event_type != "csv_imported":
                    try:
                        curr_dt = datetime.fromisoformat(event.timestamp)
                        prev_dt = datetime.fromisoformat(prev_event.timestamp)
                        diff = curr_dt - prev_dt
                        if diff.total_seconds() > 3600:
                            if diff.days > 0:
                                wait_str = f"{diff.days} days"
                            else:
                                wait_str = f"{int(diff.total_seconds() // 3600)} hours"
                            
                            wait_dt = prev_dt + timedelta(seconds=1)
                            final_timeline.append(JourneyEvent(
                                id=f"wait-{event.id}",
                                module="Follow-up Email",
                                event_type="wait",
                                status="completed",
                                timestamp=wait_dt.astimezone(timezone.utc).isoformat(),
                                title="Wait Duration",
                                subtitle=f"Waiting for {wait_str}",
                                icon="Clock",
                                color="slate",
                                expandable=False,
                                description="Waiting for customer response before triggering next step."
                            ))
                    except Exception:
                        pass
            
            final_timeline.append(event)

        # Inject Conversation Closed terminal event if enrollment_status is completed/exited AND no pending/scheduled/paused follow-ups exist AND not stopped by reply
        has_pending_followup = any(row[2] in ('pending', 'scheduled', 'paused') for row in all_schedules)
        has_reply_detected = any(row[5] is not None for row in all_schedules)
        is_reply_exit = (exit_reason and any(pat in exit_reason.lower() for pat in ("reply", "in-reply-to"))) or has_reply_detected
        is_closed = enrollment_status and enrollment_status.lower() in ('completed', 'exited') and not has_pending_followup and not is_reply_exit
        
        if is_closed:
            last_timestamp = final_timeline[-1].timestamp if final_timeline else datetime.now(timezone.utc).isoformat()
            try:
                last_dt = datetime.fromisoformat(last_timestamp)
                closed_time = (last_dt + timedelta(seconds=2)).astimezone(timezone.utc).isoformat()
            except Exception:
                closed_time = datetime.now(timezone.utc).isoformat()
                
            final_timeline.append(JourneyEvent(
                id=f"closed-{customer_id}",
                module="Campaign",
                event_type="conversation_finished",
                status="completed",
                timestamp=closed_time,
                title="Conversation Finished",
                subtitle="Sequence Finished",
                icon="Lock",
                color="slate",
                expandable=False,
                description="Automation sequence finished."
            ))

        return CustomerJourneyResponse(customer_id=customer_id, timeline=final_timeline)

    async def get_organization_activities(self, limit: int = 5, exclude_future: bool = True) -> List[JourneyEvent]:
        # 1a. Fetch latest INBOUND (reply) emails – guaranteed slots so replies are never crowded out
        # Fetch up to limit*6 so recent replies from the past 7 days always surface
        inbound_res = await self.db.execute(
            text("""
                SELECT el.id, el.direction, el.subject, el.body, el.sent_at, el.received_at, el.replied_at, el.delivery_status, el.graph_message_id, el.created_at, el.has_attachment, CAST(el.email_type AS VARCHAR), el.thread_id,
                       c.contact_email, COALESCE(c.contact_name, 'Unknown Contact') as contact_name, COALESCE(c.company_name, 'Unknown Company') as company_name
                FROM email_log el
                LEFT JOIN customers c ON el.customer_id = c.id
                WHERE el.organization_id = :org_id AND el.direction = 'inbound'
                  AND el.created_at >= NOW() - INTERVAL '7 days'
                ORDER BY el.created_at DESC
                LIMIT :limit
            """),
            {"org_id": self.org_id, "limit": limit * 6}
        )
        # 1b. Fetch latest OUTBOUND emails
        outbound_res = await self.db.execute(
            text("""
                SELECT el.id, el.direction, el.subject, el.body, el.sent_at, el.received_at, el.replied_at, el.delivery_status, el.graph_message_id, el.created_at, el.has_attachment, CAST(el.email_type AS VARCHAR), el.thread_id,
                       c.contact_email, COALESCE(c.contact_name, 'Unknown Contact') as contact_name, COALESCE(c.company_name, 'Unknown Company') as company_name
                FROM email_log el
                LEFT JOIN customers c ON el.customer_id = c.id
                WHERE el.organization_id = :org_id AND el.direction = 'outbound'
                ORDER BY el.created_at DESC
                LIMIT :limit
            """),
            {"org_id": self.org_id, "limit": limit}
        )
        emails = list(inbound_res.fetchall()) + list(outbound_res.fetchall())

        # 2. Fetch latest follow-up schedule items
        schedule_res = await self.db.execute(
            text("""
                SELECT f.id, f.step_number, CAST(f.status AS VARCHAR), f.scheduled_datetime, f.completed_at, f.reply_detected_at, f.reply_reason, f.message_id,
                       c.contact_email, COALESCE(c.contact_name, 'Unknown Contact') as contact_name, COALESCE(c.company_name, 'Unknown Company') as company_name,
                       f.reply_thread_id, f.reply_subject
                FROM follow_up_schedule f
                LEFT JOIN customers c ON f.customer_id = c.id
                WHERE f.organization_id = :org_id
                ORDER BY f.created_at DESC
                LIMIT :limit
            """),
            {"org_id": self.org_id, "limit": limit * 2}
        )
        schedules = schedule_res.fetchall()

        # 3. Fetch latest import batches
        import_res = await self.db.execute(
            text("""
                SELECT id, file_name, successful_rows, created_at
                FROM import_batches
                WHERE organization_id = :org_id AND status = 'completed'
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"org_id": self.org_id, "limit": limit}
        )
        imports = import_res.fetchall()

        # Fetch sender display name once
        sender_res = await self.db.execute(
            text("""
                SELECT u.full_name, o.display_name 
                FROM organizations o
                LEFT JOIN tenant_integrations ti ON o.id = ti.organization_id
                LEFT JOIN users u ON ti.mailbox_email = u.email
                WHERE o.id = :org_id
                LIMIT 1
            """),
            {"org_id": self.org_id}
        )
        sender_row = sender_res.fetchone()
        if sender_row:
            user_full_name, org_display_name = sender_row
            sender_display_name = user_full_name or org_display_name or "Amplus Agent"
        else:
            sender_display_name = "Amplus Agent"

        timeline: List[JourneyEvent] = []

        # Map imports
        for row in imports:
            b_id, file_name, succ_rows, created_at = row
            t_iso = created_at.astimezone(timezone.utc).isoformat()
            timeline.append(JourneyEvent(
                id=f"csv-import-{b_id}",
                module="CSV",
                event_type="csv_imported",
                status="completed",
                timestamp=t_iso,
                title="Customer Imported",
                subtitle=f"Imported from {file_name}" if file_name else "Manual Import",
                icon="UploadCloud",
                color="blue",
                expandable=False,
                description=f"CSV import completed. File: {file_name} ({succ_rows} contacts)."
            ))

        # Map emails
        schedule_msg_ids = {s[7] for s in schedules if s[7]}
        for row in emails:
            e_id, direction, subject, body, sent_at, received_at, replied_at, delivery_status, graph_msg_id, created_at, has_attachment, email_type, thread_id, c_email, c_name, c_company = row
            
            is_followup = (direction == 'outbound') and (graph_msg_id in schedule_msg_ids)
            if is_followup:
                continue

            t_val = sent_at or received_at or created_at
            t_iso = t_val.astimezone(timezone.utc).isoformat()

            if direction == "inbound":
                timeline.append(JourneyEvent(
                    id=str(e_id),
                    module="AI Reply",
                    event_type="reply_received",
                    status="completed",
                    timestamp=t_iso,
                    title="🟢 Customer Replied",
                    subtitle=f"From {c_name} ({c_company})",
                    icon="Mail",
                    color="emerald",
                    expandable=True,
                    description=f"Inbound reply received from customer {c_email}.",
                    mail={
                        "id": str(e_id),
                        "subject": subject,
                        "body": normalize_email_body(body),
                        "direction": "inbound",
                        "message_id": graph_msg_id,
                        "thread_id": thread_id,
                        "delivery_status": "completed",
                        "sender": c_email,
                        "recipient": sender_display_name,
                        "timestamp": t_iso,
                        "email_type": "reply"
                    }
                ))
            elif direction == "outbound":
                title = "Reply Sent" if email_type == 'reply' else "Initial Outreach"
                timeline.append(JourneyEvent(
                    id=str(e_id),
                    module="Engagement",
                    event_type="email_sent",
                    status=delivery_status or "sent",
                    timestamp=t_iso,
                    title=title,
                    subtitle=f"Subject: '{subject}' to {c_name}",
                    icon="Send",
                    color="emerald",
                    expandable=True,
                    description=f"Outreach message sent to {c_email}.",
                    mail={
                        "id": str(e_id),
                        "subject": subject,
                        "body": normalize_email_body(body),
                        "direction": "outbound",
                        "delivery_status": delivery_status or "sent",
                        "message_id": graph_msg_id,
                        "thread_id": thread_id,
                        "sender": sender_display_name,
                        "recipient": c_email,
                        "timestamp": t_iso,
                        "email_type": "initial_outreach"
                    }
                ))

        # Map schedules
        for row in schedules:
            s_id, step_num, status, scheduled_dt, completed_at, reply_detected_at, reply_reason, message_id, c_email, c_name, c_company, reply_thread_id, reply_subject = row

            if completed_at:
                continue

            if scheduled_dt and status in ('pending', 'paused', 'scheduled'):
                sch_iso = scheduled_dt.astimezone(timezone.utc).isoformat()
                now_iso = datetime.now(timezone.utc).isoformat()
                # In the org-level feed, only show UPCOMING schedules (not overdue pending)
                if sch_iso > now_iso:
                    timeline.append(JourneyEvent(
                        id=f"sched-{s_id}",
                        module="Follow-up Email",
                        event_type="followup_scheduled",
                        status=status,
                        timestamp=sch_iso,
                        title=f"Follow-up Email Step {step_num} Scheduled",
                        subtitle=f"Step {step_num} scheduled for {c_name}",
                        icon="Calendar",
                        color="indigo",
                        expandable=False,
                        description=f"Automatic follow-up scheduled to run at {scheduled_dt}.",
                        step_number=step_num
                    ))

            if reply_detected_at:
                rep_iso = reply_detected_at.astimezone(timezone.utc).isoformat()
                clean_reason = to_business_reason(reply_reason)
                timeline.append(JourneyEvent(
                    id=f"stop-{s_id}",
                    module="Follow-up Email",
                    event_type="sequence_stopped",
                    status="completed",
                    timestamp=rep_iso,
                    title="Sequence Stopped",
                    subtitle=f"Reason: {clean_reason}",
                    icon="X",
                    color="red",
                    expandable=False,
                    description=f"Auto-enrichment sequence terminated due to customer response.",
                    step_number=step_num
                ))

        # Sort chronologically DESC
        timeline.sort(key=lambda x: x.timestamp, reverse=True)
        
        now_str = datetime.now(timezone.utc).isoformat()
        if exclude_future:
            timeline = [evt for evt in timeline if evt.timestamp <= now_str]
            
        return timeline[:limit]
