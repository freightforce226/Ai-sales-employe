from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from uuid import UUID
from app.repositories.customer_repository import CustomerRepository

class CustomerService:
    def __init__(self, db: AsyncSession, org_id: UUID):
        self.repo = CustomerRepository(db, org_id)

    def calculate_readiness(self, email: Optional[str], company: Optional[str]) -> str:
        if not email or "@" not in email:
            return "EMAIL_MISSING"
        if not company:
            return "NOT_ELIGIBLE"
        return "READY"

    def calculate_status(self, enrollment_status: Optional[str], exit_reason: Optional[str]) -> str:
        if not enrollment_status:
            return "NOT_CONTACTED"
        status_upper = enrollment_status.upper()
        if status_upper == "ACTIVE":
            return "ACTIVE"
        if status_upper == "PAUSED":
            return "PAUSED"
        if status_upper == "COMPLETED":
            reason_lower = (exit_reason or "").lower()
            if "reply" in reason_lower:
                return "EXITED_REPLIED"
            if "unsubscribe" in reason_lower:
                return "EXITED_UNSUBSCRIBED"
            return "COMPLETED"
        return "NOT_CONTACTED"

    async def get_customers(
        self,
        page: int,
        limit: int,
        q: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        segment: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        rows, total = await self.repo.get_customers(page, limit, q, industry, country, segment)
        customers = []
        for r in rows:
            c_id, company, name, email, ind, cntry, seg, last_email_date, created_at, enrollment_status, exit_reason = r
            readiness = self.calculate_readiness(email, company)
            status_val = self.calculate_status(enrollment_status, exit_reason)

            customers.append({
                "id": c_id,
                "company_name": company,
                "contact_name": name,
                "contact_email": email,
                "industry": ind,
                "country": cntry,
                "segment": seg,
                "engagement_readiness": readiness,
                "last_email": str(last_email_date) if last_email_date else None,
                "imported_on": created_at.strftime("%Y-%m-%d") if created_at else "",
                "status": status_val
            })
        return customers, total

    async def get_customer_by_id(self, customer_id: UUID) -> Optional[Dict[str, Any]]:
        row = await self.repo.get_customer_by_id(customer_id)
        if not row:
            return None

        c_id, company, name, email, ind, cntry, seg, last_email_date, created_at, batch_id, batch_name, batch_date, enrollment_status, exit_reason = row
        readiness = self.calculate_readiness(email, company)
        status_val = self.calculate_status(enrollment_status, exit_reason)

        # Query database for engagement timeline and stats
        from sqlalchemy import text
        
        # 1. Total emails sent count
        total_emails_res = await self.repo.db.execute(
            text("SELECT COUNT(*) FROM email_log WHERE customer_id = :customer_id AND organization_id = :org_id"),
            {"customer_id": customer_id, "org_id": self.repo.org_id}
        )
        total_emails = total_emails_res.scalar() or 0

        # 2. Sent this week (last 7 days)
        week_emails_res = await self.repo.db.execute(
            text("SELECT COUNT(*) FROM email_log WHERE customer_id = :customer_id AND organization_id = :org_id AND sent_at >= NOW() - INTERVAL '7 days'"),
            {"customer_id": customer_id, "org_id": self.repo.org_id}
        )
        emails_this_week = week_emails_res.scalar() or 0

        # 3. Sent this month (last 30 days)
        month_emails_res = await self.repo.db.execute(
            text("SELECT COUNT(*) FROM email_log WHERE customer_id = :customer_id AND organization_id = :org_id AND sent_at >= NOW() - INTERVAL '30 days'"),
            {"customer_id": customer_id, "org_id": self.repo.org_id}
        )
        emails_this_month = month_emails_res.scalar() or 0

        # 4. Latest sent details
        latest_email_res = await self.repo.db.execute(
            text("SELECT subject, delivery_status, graph_message_id, sent_at FROM email_log WHERE customer_id = :customer_id AND organization_id = :org_id ORDER BY sent_at DESC LIMIT 1"),
            {"customer_id": customer_id, "org_id": self.repo.org_id}
        )
        latest_row = latest_email_res.fetchone()
        last_subject = latest_row[0] if latest_row else None
        last_delivery_status = str(latest_row[1]) if latest_row and latest_row[1] is not None else None
        last_message_id = latest_row[2] if latest_row else None
        


        # 5. Timeline list
        timeline_res = await self.repo.db.execute(
            text("SELECT subject, sent_at, delivery_status FROM email_log WHERE customer_id = :customer_id AND organization_id = :org_id ORDER BY sent_at DESC LIMIT 10"),
            {"customer_id": customer_id, "org_id": self.repo.org_id}
        )
        timeline = []
        for row_t in timeline_res.fetchall():
            timeline.append({
                "subject": row_t[0],
                "sent_at": row_t[1].isoformat() if row_t[1] else "",
                "delivery_status": str(row_t[2]) if row_t[2] is not None else "UNKNOWN"
            })

        return {
            "id": c_id,
            "company_name": company,
            "contact_name": name,
            "contact_email": email,
            "industry": ind,
            "country": cntry,
            "segment": seg,
            "engagement_readiness": readiness,
            "last_email": str(last_email_date) if last_email_date else None,
            "imported_on": created_at.strftime("%Y-%m-%d") if created_at else "",
            "status": status_val,
            "import_batch_id": batch_id,
            "import_batch_name": batch_name,
            "total_emails_sent": total_emails,
            "assigned_template": None,
            "assigned_attachment": None,
            "last_subject": last_subject,
            "last_delivery_status": last_delivery_status,
            "last_message_id": last_message_id,
            "emails_this_week": emails_this_week,
            "emails_this_month": emails_this_month,
            "timeline": timeline
        }

    async def update_customer(
        self,
        customer_id: UUID,
        company_name: str,
        contact_name: Optional[str],
        contact_email: Optional[str],
        industry: Optional[str],
        country: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        success = await self.repo.update_customer(
            customer_id, company_name, contact_name, contact_email, industry, country
        )
        if not success:
            return None
        return await self.get_customer_by_id(customer_id)

    async def delete_customer(self, customer_id: UUID) -> bool:
        return await self.repo.delete_customer(customer_id)

    async def bulk_delete_customers(self, customer_ids: List[UUID]) -> int:
        return await self.repo.bulk_delete_customers(customer_ids)

    async def get_stats(self) -> Dict[str, Any]:
        total_customers, segment_breakdown, country_breakdown = await self.repo.get_stats()

        # Compute readiness stats based on simplified backend evaluation
        all_customers = await self.repo.get_all_customers_for_readiness()
        ready_count = 0
        for r in all_customers:
            _, company, email, _ = r
            if self.calculate_readiness(email, company) == "READY":
                ready_count += 1

        return {
            "total_customers": total_customers,
            "ready_count": ready_count,
            "segment_breakdown": segment_breakdown,
            "country_breakdown": country_breakdown
        }

    async def get_filters(self) -> Dict[str, Any]:
        industries, countries, segments = await self.repo.get_filters()
        return {
            "industries": industries,
            "countries": countries,
            "segments": segments
        }
