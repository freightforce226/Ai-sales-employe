from typing import Optional, Any, Dict
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.organization import Organization, PlanTier

class OrganizationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, org_id: UUID) -> Optional[Organization]:
        result = await self.session.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Organization]:
        result = await self.session.execute(select(Organization).where(Organization.name == name))
        return result.scalar_one_or_none()

    async def get_by_custom_domain(self, domain: str) -> Optional[Organization]:
        result = await self.session.execute(select(Organization).where(Organization.custom_domain == domain))
        return result.scalar_one_or_none()

    async def create_organization(
        self,
        name: str,
        display_name: str,
        logo_url: Optional[str] = None,
        theme_config: Optional[Dict[str, Any]] = None,
        plan_tier: PlanTier = PlanTier.pilot,
    ) -> Organization:
        org = Organization(
            name=name,
            display_name=display_name,
            logo_url=logo_url,
            theme_config=theme_config,
            plan_tier=plan_tier,
            is_active=True,
        )
        self.session.add(org)
        await self.session.commit()
        await self.session.refresh(org)
        return org

    async def update_branding(
        self,
        org_id: UUID,
        logo_url: Optional[str],
        theme_config: Dict[str, Any],
    ) -> Optional[Organization]:
        org = await self.get_by_id(org_id)
        if org:
            if logo_url:
                org.logo_url = logo_url
            org.theme_config = theme_config
            await self.session.commit()
            await self.session.refresh(org)
        return org
