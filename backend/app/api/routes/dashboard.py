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

        # 2. Total campaigns
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
            text("SELECT count(*) FROM email_log WHERE organization_id = :org_id AND replied_at IS NOT NULL"),
            {"org_id": org_id}
        )
        total_replies = replies_res.scalar() or 0
        response_rate = round((total_replies / total_emails * 100), 1) if total_emails > 0 else 0.0

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

        # 6. Recent activity from email log
        activity_res = await db.execute(
            text("""
                SELECT e.subject, e.sent_at, e.received_at, c.contact_name, c.company_name
                FROM email_log e
                LEFT JOIN customers c ON e.customer_id = c.id
                WHERE e.organization_id = :org_id
                ORDER BY e.created_at DESC
                LIMIT 5
            """),
            {"org_id": org_id}
        )
        activities = []
        for row in activity_res.fetchall():
            subject = row[0]
            sent_at = row[1]
            received_at = row[2]
            contact_name = row[3] or "Unknown Contact"
            company_name = row[4] or "Unknown Company"
            
            event_time = sent_at or received_at or datetime.now(timezone.utc)
            event_type = "Email Sent" if sent_at else "Reply Received"
            details = f"Subject: '{subject}' to {contact_name}" if sent_at else f"AI analyzed response from {contact_name}"
            
            time_str = event_time.strftime("%b %d, %H:%M") if hasattr(event_time, "strftime") else str(event_time)

            activities.append({
                "event": event_type,
                "details": details,
                "time": time_str
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
                "total_emails_sent": total_emails,
                "response_rate": f"{response_rate}%"
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
