"""
Purpose of this file.
Service logic for the Microsoft OAuth flow.
Responsibility of this file.
Orchestrating state generation, token exchange, encryption, and storage of tokens.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.microsoft_oauth_client import MicrosoftOAuthClient
from app.core.encryption import encrypt_token
from app.core.logging import get_logger
from app.repositories.oauth_state_repository import OAuthStateRepository
from app.repositories.tenant_repository import TenantIntegrationRepository

logger = get_logger(__name__)


class OAuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.oauth_state_repo = OAuthStateRepository(session)
        self.tenant_repo = TenantIntegrationRepository(session)
        self.oauth_client = MicrosoftOAuthClient()

    async def generate_auth_url(self, organization_id: UUID) -> str:
        state_value = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        await self.oauth_state_repo.create_state(
            organization_id=organization_id,
            state=state_value,
            expires_at=expires_at,
        )
        
        auth_url = self.oauth_client.get_authorization_url(state_value)
        logger.info("Generated OAuth authorization URL", organization_id=organization_id)
        return auth_url

    async def handle_callback(self, code: str, state: str) -> None:
        oauth_state = await self.oauth_state_repo.get_and_delete_state(state)
        
        if not oauth_state:
            logger.warning("Invalid or missing OAuth state", state=state)
            raise ValueError("Invalid OAuth state")
            
        # Timezone-aware comparison
        if oauth_state.expires_at < datetime.now(timezone.utc):
            logger.warning("Expired OAuth state", state=state, organization_id=oauth_state.organization_id)
            raise ValueError("OAuth state expired")

        organization_id = oauth_state.organization_id
        
        try:
            token_response = await self.oauth_client.exchange_code_for_token(code)
            access_token = token_response["access_token"]
            refresh_token = token_response.get("refresh_token")
            expires_in = token_response.get("expires_in", 3600)
            
            if not refresh_token:
                raise ValueError("No refresh token received from Microsoft")

            mailbox_email = await self.oauth_client.get_user_email(access_token)
            
            encrypted_access_token = encrypt_token(access_token)
            encrypted_refresh_token = encrypt_token(refresh_token)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            await self.tenant_repo.upsert_integration(
                organization_id=organization_id,
                mailbox_email=mailbox_email,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                token_expires_at=token_expires_at,
            )
            logger.info("Successfully completed OAuth flow", organization_id=organization_id, mailbox_email=mailbox_email)
            
        except Exception as e:
            logger.error("Failed to complete OAuth callback", organization_id=organization_id, error=str(e))
            raise
