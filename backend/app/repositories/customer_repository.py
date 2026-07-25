from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from uuid import UUID

class CustomerRepository:
    def __init__(self, db: AsyncSession, org_id: UUID):
        self.db = db
        self.org_id = org_id

    async def get_customers(
        self,
        page: int,
        limit: int,
        q: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        segment: Optional[str] = None
    ) -> tuple[List[Any], int]:
        offset = (page - 1) * limit
        
        query_str = " FROM customers c"
        if segment:
            query_str += " JOIN customer_segments cs ON c.id = cs.customer_id AND cs.organization_id = :org_id"
            
        query_str += " WHERE c.organization_id = :org_id AND c.deleted_at IS NULL"
        params = {"org_id": self.org_id}
 
        if q:
            query_str += " AND (c.company_name ILIKE :q OR c.contact_name ILIKE :q OR c.contact_email ILIKE :q)"
            params["q"] = f"%{q}%"
        if industry:
            query_str += " AND c.industry = :industry"
            params["industry"] = industry
        if country:
            query_str += " AND c.country = :country"
            params["country"] = country
        if segment:
            query_str += " AND cs.segment_type = :segment"
            params["segment"] = segment
 
        # Count Query
        count_res = await self.db.execute(text(f"SELECT COUNT(DISTINCT c.id) {query_str}"), params)
        total = count_res.scalar() or 0
 
        # Data Query
        select_fields = """
            SELECT c.id, c.company_name, c.contact_name, c.contact_email, c.industry, c.country, 
                   (SELECT cs2.segment_type FROM customer_segments cs2 WHERE cs2.customer_id = c.id LIMIT 1) as segment_type,
                   c.last_contact_date, c.created_at
        """
        data_query = text(f"{select_fields} {query_str} ORDER BY c.created_at DESC LIMIT :limit OFFSET :offset")
        params["limit"] = limit
        params["offset"] = offset
 
        res = await self.db.execute(data_query, params)
        rows = res.fetchall()
 
        return rows, total

    async def get_customer_by_id(self, customer_id: UUID) -> Optional[Any]:
        res = await self.db.execute(
            text("""
                SELECT c.id, c.company_name, c.contact_name, c.contact_email, c.industry, c.country, 
                       cs.segment_type, c.last_contact_date, c.created_at, c.import_batch_id,
                       ib.file_name, ib.created_at
                FROM customers c
                LEFT JOIN customer_segments cs ON c.id = cs.customer_id AND cs.organization_id = :org_id
                LEFT JOIN import_batches ib ON c.import_batch_id = ib.id AND ib.organization_id = :org_id
                WHERE c.id = :id AND c.organization_id = :org_id AND c.deleted_at IS NULL
            """),
            {"id": customer_id, "org_id": self.org_id}
        )
        return res.fetchone()

    async def update_customer(
        self,
        customer_id: UUID,
        company_name: str,
        contact_name: Optional[str],
        contact_email: Optional[str],
        industry: Optional[str],
        country: Optional[str]
    ) -> bool:
        res = await self.db.execute(
            text("""
                UPDATE customers
                SET company_name = :company_name,
                    contact_name = :contact_name,
                    contact_email = :contact_email,
                    industry = :industry,
                    country = :country,
                    updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id AND deleted_at IS NULL
            """),
            {
                "id": customer_id,
                "org_id": self.org_id,
                "company_name": company_name,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "industry": industry,
                "country": country
            }
        )
        return res.rowcount > 0

    async def delete_customer(self, customer_id: UUID) -> bool:
        res = await self.db.execute(
            text("UPDATE customers SET deleted_at = NOW() WHERE id = :id AND organization_id = :org_id AND deleted_at IS NULL"),
            {"id": customer_id, "org_id": self.org_id}
        )
        return res.rowcount > 0

    async def bulk_delete_customers(self, customer_ids: List[UUID]) -> int:
        if not customer_ids:
            return 0
        res = await self.db.execute(
            text("""
                UPDATE customers 
                SET deleted_at = NOW() 
                WHERE id = ANY(:ids) AND organization_id = :org_id AND deleted_at IS NULL
            """),
            {"ids": list(customer_ids), "org_id": self.org_id}
        )
        return res.rowcount

    async def get_stats(self) -> tuple[int, Dict[str, int], Dict[str, int]]:
        # Total count
        total_res = await self.db.execute(
            text("SELECT COUNT(*) FROM customers WHERE organization_id = :org_id AND deleted_at IS NULL"),
            {"org_id": self.org_id}
        )
        total_customers = total_res.scalar() or 0

        # Segments breakdown
        seg_res = await self.db.execute(
            text("""
                SELECT cs.segment_type, COUNT(*) 
                FROM customers c
                JOIN customer_segments cs ON c.id = cs.customer_id
                WHERE c.organization_id = :org_id AND c.deleted_at IS NULL
                GROUP BY cs.segment_type
            """),
            {"org_id": self.org_id}
        )
        segment_breakdown = {str(row[0]): row[1] for row in seg_res.fetchall()}

        # Country breakdown
        cntry_res = await self.db.execute(
            text("""
                SELECT country, COUNT(*) 
                FROM customers 
                WHERE organization_id = :org_id AND deleted_at IS NULL AND country IS NOT NULL
                GROUP BY country
                LIMIT 10
            """),
            {"org_id": self.org_id}
        )
        country_breakdown = {str(row[0]): row[1] for row in cntry_res.fetchall()}

        return total_customers, segment_breakdown, country_breakdown

    async def get_filters(self) -> tuple[List[str], List[str], List[str]]:
        # Distinct industries
        ind_res = await self.db.execute(
            text("SELECT DISTINCT industry FROM customers WHERE organization_id = :org_id AND deleted_at IS NULL AND industry IS NOT NULL"),
            {"org_id": self.org_id}
        )
        industries = [row[0] for row in ind_res.fetchall()]

        # Distinct countries
        cntry_res = await self.db.execute(
            text("SELECT DISTINCT country FROM customers WHERE organization_id = :org_id AND deleted_at IS NULL AND country IS NOT NULL"),
            {"org_id": self.org_id}
        )
        countries = [row[0] for row in cntry_res.fetchall()]

        # Distinct segments
        seg_res = await self.db.execute(
            text("""
                SELECT DISTINCT cs.segment_type 
                FROM customers c
                JOIN customer_segments cs ON c.id = cs.customer_id
                WHERE c.organization_id = :org_id AND c.deleted_at IS NULL
            """),
            {"org_id": self.org_id}
        )
        segments = [str(row[0]) for row in seg_res.fetchall() if row[0]]

        return sorted(industries), sorted(countries), sorted(segments)

    async def get_all_customers_for_readiness(self) -> List[Any]:
        res = await self.db.execute(
            text("SELECT id, company_name, contact_email, industry FROM customers WHERE organization_id = :org_id AND deleted_at IS NULL"),
            {"org_id": self.org_id}
        )
        return res.fetchall()
