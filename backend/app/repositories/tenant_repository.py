"""
Purpose of this file.
Repository for managing TenantIntegration database operations.
Responsibility of this file.
Providing an async interface for CRUD operations on tenant_integrations.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_integration import TenantIntegration


class TenantIntegrationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_organization_id(self, organization_id: UUID) -> Optional[TenantIntegration]:
        result = await self.session.execute(
            select(TenantIntegration).where(TenantIntegration.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def upsert_integration(
        self,
        organization_id: UUID,
        mailbox_email: str,
        encrypted_access_token: str,
        encrypted_refresh_token: str,
        token_expires_at: datetime,
    ) -> TenantIntegration:
        integration = await self.get_by_organization_id(organization_id)
        if integration:
            integration.mailbox_email = mailbox_email
            integration.encrypted_access_token = encrypted_access_token
            integration.encrypted_refresh_token = encrypted_refresh_token
            integration.token_expires_at = token_expires_at
            integration.is_active = True
            integration.last_refreshed_at = datetime.now(timezone.utc)
            integration.last_sync_error = None
        else:
            integration = TenantIntegration(
                organization_id=organization_id,
                mailbox_email=mailbox_email,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                token_expires_at=token_expires_at,
                is_active=True,
                last_refreshed_at=datetime.now(timezone.utc),
            )
            self.session.add(integration)
        
        await self.session.commit()
        await self.session.refresh(integration)
        return integration

    async def update_error_state(self, organization_id: UUID, error_message: str) -> None:
        await self.session.execute(
            update(TenantIntegration)
            .where(TenantIntegration.organization_id == organization_id)
            .values(last_sync_error=error_message, is_active=False)
        )
        await self.session.commit()
