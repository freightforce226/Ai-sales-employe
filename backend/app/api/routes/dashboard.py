from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from datetime import datetime, timedelta, timezone
import uuid

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

@router.get("/metrics")
async def get_dashboard_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id

    try:
        # 1. Total contacts
        contacts_res = await db.execute(
            text("SELECT count(*) FROM customers WHERE organization_id = :org_id AND deleted_at IS NULL"),
            {"org_id": org_id}
        )
        total_contacts = contacts_res.scalar() or 0

        # 2. Customers under automation (active campaign enrollments OR pending follow-up schedule)
        automation_res = await db.execute(
            text("""
                SELECT COUNT(DISTINCT customer_id) 
                FROM (
                    SELECT customer_id 
                    FROM campaign_enrollments 
                    WHERE organization_id = :org_id 
                      AND CAST(enrollment_status AS VARCHAR) = 'active'
                    UNION
                    SELECT customer_id 
                    FROM follow_up_schedule 
                    WHERE organization_id = :org_id 
                      AND CAST(status AS VARCHAR) IN ('pending', 'paused', 'scheduled')
                ) sub
            """),
            {"org_id": org_id}
        )
        customers_under_automation = automation_res.scalar() or 0

        # For backward compatibility, also fetch total_campaigns count
        campaigns_res = await db.execute(
            text("SELECT count(*) FROM campaigns WHERE organization_id = :org_id AND deleted_at IS NULL"),
            {"org_id": org_id}
        )
        total_campaigns = campaigns_res.scalar() or 0

        # 3. Emails sent
        emails_res = await db.execute(
            text("SELECT count(*) FROM email_log WHERE organization_id = :org_id"),
            {"org_id": org_id}
        )
        total_emails = emails_res.scalar() or 0

        # 4. Response rate
        replies_res = await db.execute(
            text("""
                SELECT COUNT(DISTINCT el.customer_id) 
                FROM email_log el
                JOIN customers c ON el.customer_id = c.id
                WHERE el.organization_id = :org_id 
                  AND el.direction = 'inbound'
                  AND c.contact_email NOT LIKE '%@freightforce.ai'
                  AND c.contact_email NOT LIKE 'golupandit82094%'
            """),
            {"org_id": org_id}
        )
        total_replies = replies_res.scalar() or 0
        response_rate = round((total_replies / total_emails * 100), 1) if total_emails > 0 else 0.0

        # Replies today (in the last 24 hours)
        replies_today_res = await db.execute(
            text("""
                SELECT COUNT(DISTINCT el.customer_id) 
                FROM email_log el
                JOIN customers c ON el.customer_id = c.id
                WHERE el.organization_id = :org_id 
                  AND el.direction = 'inbound' 
                  AND el.received_at >= NOW() - INTERVAL '24 hours'
                  AND c.contact_email NOT LIKE '%@freightforce.ai'
                  AND c.contact_email NOT LIKE 'golupandit82094%'
            """),
            {"org_id": org_id}
        )
        replies_today = replies_today_res.scalar() or 0

        # 5. Recent leads/customers
        leads_res = await db.execute(
            text("""
                SELECT id, company_name, contact_name, contact_email, last_contact_date, created_at 
                FROM customers 
                WHERE organization_id = :org_id AND deleted_at IS NULL 
                ORDER BY created_at DESC 
                LIMIT 5
            """),
            {"org_id": org_id}
        )
        leads = []
        for row in leads_res.fetchall():
            leads.append({
                "id": str(row[0]),
                "company_name": row[1],
                "contact_name": row[2],
                "contact_email": row[3],
                "last_contact": str(row[4]) if row[4] else None,
                "created_at": str(row[5]) if row[5] else None
            })

        # 6. Fetch sender display name dynamically
        sender_res = await db.execute(
            text("""
                SELECT u.full_name, o.display_name 
                FROM organizations o
                LEFT JOIN tenant_integrations ti ON o.id = ti.organization_id
                LEFT JOIN users u ON ti.mailbox_email = u.email
                WHERE o.id = :org_id
                LIMIT 1
            """),
            {"org_id": org_id}
        )
        sender_row = sender_res.fetchone()
        if sender_row:
            user_full_name, org_display_name = sender_row
            sender_display_name = user_full_name or org_display_name or "Amplus Agent"
        else:
            sender_display_name = "Amplus Agent"

        # 7. Recent activity from CustomerJourneyService (fully deduplicated)
        from app.services.customer_journey_service import CustomerJourneyService
        journey_service = CustomerJourneyService(db, org_id)
        events = await journey_service.get_organization_activities(limit=50)
        
        activities = []
        for evt in events:
            try:
                dt = datetime.fromisoformat(evt.timestamp)
                time_str = dt.strftime("%b %d, %H:%M")
            except Exception:
                time_str = evt.timestamp

            event_name = evt.title
            details_str = evt.subtitle
            if evt.event_type == 'email_sent':
                event_name = "Email Sent"
                details_str = evt.subtitle
            elif evt.event_type == 'reply_received':
                event_name = "🟢 Customer Replied"
                details_str = evt.subtitle
            elif evt.event_type == 'csv_imported':
                event_name = "Customer Imported"
                details_str = evt.subtitle
            elif evt.event_type == 'followup_scheduled':
                event_name = "Follow-up Scheduled"
                details_str = evt.subtitle

            activities.append({
                "id": evt.id,
                "time": time_str,
                "timestamp": evt.timestamp,
                "event": event_name,
                "details": details_str,
                "module": evt.module,
                "event_type": evt.event_type,
                "status": evt.status,
                "title": evt.title,
                "subtitle": evt.subtitle,
                "icon": evt.icon,
                "color": evt.color,
                "expandable": evt.expandable,
                "mail": evt.mail if evt.mail else None,
                "attachments": evt.attachments or [],
                "step_number": evt.step_number
            })

        # Engagement Widget Metrics
        sent_today_res = await db.execute(
            text("SELECT count(*) FROM email_log WHERE organization_id = :org_id AND sent_at >= NOW() - INTERVAL '24 hours'"),
            {"org_id": org_id}
        )
        sent_today = sent_today_res.scalar() or 0

        failed_today_res = await db.execute(
            text("SELECT count(*) FROM email_log WHERE organization_id = :org_id AND delivery_status = 'failed' AND sent_at >= NOW() - INTERVAL '24 hours'"),
            {"org_id": org_id}
        )
        failed_today = failed_today_res.scalar() or 0

        ready_res = await db.execute(
            text("SELECT count(*) FROM customers WHERE organization_id = :org_id AND contact_email IS NOT NULL AND deleted_at IS NULL"),
            {"org_id": org_id}
        )
        pending = ready_res.scalar() or 0

        settings_res = await db.execute(
            text("SELECT preferred_send_time, timezone, auto_engagement FROM organization_engagement_settings WHERE organization_id = :org_id"),
            {"org_id": org_id}
        )
        s_row = settings_res.fetchone()
        next_run = "Not Scheduled"
        if s_row and s_row[2]:
            next_run = f"{s_row[0]} ({s_row[1]})"

        engagement_widget = {
            "sent_today": sent_today,
            "failed": failed_today,
            "pending": pending,
            "next_auto_run": next_run
        }

        return {
            "metrics": {
                "total_contacts": total_contacts,
                "total_campaigns": total_campaigns,
                "customers_under_automation": customers_under_automation,
                "total_emails_sent": total_emails,
                "response_rate": f"{response_rate}%",
                "replies_received": total_replies,
                "replies_today": replies_today
            },
            "leads": leads,
            "activities": activities,
            "engagement": engagement_widget
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch CRM metrics: {str(e)}"
        )

@router.post("/seed")
async def seed_demo_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id

    # Check if data already exists to prevent duplicate seeding
    check_contacts = await db.execute(
        text("SELECT count(*) FROM customers WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    if check_contacts.scalar() > 0:
        return {"success": True, "message": "Demo data already exists"}

    try:
        now = datetime.now(timezone.utc)
        
        # 1. Create a Campaign
        campaign_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO campaigns (id, organization_id, name, description, status, target_segment, target_industry, cadence_per_week, total_steps, created_at, updated_at)
                VALUES (:id, :org_id, :name, :description, 'active', 'cold_outreach', 'Freight Forwarding', 3.0, 3, :now, :now)
            """),
            {
                "id": campaign_id,
                "org_id": org_id,
                "name": "APAC Logistics Partners Outreach",
                "description": "Outbound email campaign introducing automated freight forwarding options to APAC region importers.",
                "now": now
            }
        )

        # 2. Create Customers (Leads)
        leads_data = [
            ("Apex Freight Services", "Marcus Vance", "marcus.vance@apex-freight.com", "Logistics"),
            ("Global Logistics Group", "Sarah Jenkins", "s.jenkins@globallogistics.com", "Supply Chain"),
            ("Oceanic Transport Co.", "David Miller", "d.miller@oceanictransport.co", "Shipping"),
            ("EuroForwarding LLC", "Elena Rostova", "e.rostova@euroforward.eu", "Freight Forwarding"),
            ("Pacific Cargo Inc.", "Kenji Sato", "k.sato@pacificcargo.jp", "Manufacturing")
        ]

        lead_ids = []
        for idx, (company, name, email, ind) in enumerate(leads_data):
            c_id = uuid.uuid4()
            lead_ids.append(c_id)
            await db.execute(
                text("""
                    INSERT INTO customers (id, organization_id, company_name, contact_name, contact_email, industry, source, created_at, updated_at)
                    VALUES (:id, :org_id, :company, :name, :email, :ind, 'csv_import', :created_at, :created_at)
                """),
                {
                    "id": c_id,
                    "org_id": org_id,
                    "company": company,
                    "name": name,
                    "email": email,
                    "ind": ind,
                    "created_at": now - timedelta(days=idx)
                }
            )

        # 3. Create Email Log (Activities)
        activities = [
            (lead_ids[0], "APAC Logistics Alliance Intro", "outbound", now - timedelta(hours=4), None),
            (lead_ids[1], "Re: APAC Logistics Alliance Intro", "inbound", now - timedelta(hours=2), now - timedelta(hours=2)),
            (lead_ids[2], "Re: APAC Logistics Alliance Intro", "inbound", now - timedelta(days=1), now - timedelta(days=1))
        ]

        for cust_id, subject, direction, event_time, replied_time in activities:
            sent_val = event_time if direction == "outbound" else None
            rec_val = event_time if direction == "inbound" else None
            
            await db.execute(
                text("""
                    INSERT INTO email_log (id, organization_id, customer_id, campaign_id, direction, email_type, subject, body, has_attachment, sent_at, received_at, replied_at, delivery_status, created_at)
                    VALUES (:id, :org_id, :cust_id, :camp_id, :direction, 'first_touch', :subj, 'Demo email body content...', false, :sent_at, :received_at, :replied_at, 'delivered', :created_at)
                """),
                {
                    "id": uuid.uuid4(),
                    "org_id": org_id,
                    "cust_id": cust_id,
                    "camp_id": campaign_id,
                    "direction": direction,
                    "subj": subject,
                    "sent_at": sent_val,
                    "received_at": rec_val,
                    "replied_at": replied_time,
                    "created_at": event_time
                }
            )

        await db.commit()
        return {"success": True, "message": "Demo data successfully seeded"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed demo CRM data: {str(e)}"
        )
