from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.providers.base import BaseEmailProvider
from app.providers.microsoft import MicrosoftGraphProvider
from app.providers.smtp_imap import SmtpImapProvider

class EmailProviderFactory:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def get_provider_for_tenant(self, org_id: UUID) -> BaseEmailProvider:
        """
        Resolves the appropriate provider for the tenant.
        """
        try:
            res = await self.db.execute(
                text("SELECT provider FROM tenant_integrations WHERE organization_id = :org_id"),
                {"org_id": org_id}
            )
            row = res.fetchone()
            if row and row[0] == "smtp":
                return SmtpImapProvider()
        except Exception:
            pass
        return MicrosoftGraphProvider()
