"""
Purpose of this file.
Service logic for managing Microsoft Graph access tokens.
Responsibility of this file.
Loading tenant tokens, checking expiration, refreshing tokens proactively, and returning a valid access token.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.microsoft_oauth_client import MicrosoftOAuthClient
from app.core.encryption import decrypt_token, encrypt_token
from app.core.logging import get_logger
from app.repositories.tenant_repository import TenantIntegrationRepository

logger = get_logger(__name__)


import time
_token_cache = {}

class TokenService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.tenant_repo = TenantIntegrationRepository(session)
        self.oauth_client = MicrosoftOAuthClient()

    async def get_valid_access_token(self, organization_id: UUID) -> str:
        org_id_str = str(organization_id)
        now = time.time()
        
        # Check cache: reuse if token is still valid for at least 3 minutes (180 seconds)
        if org_id_str in _token_cache:
            cache_entry = _token_cache[org_id_str]
            if cache_entry["expires_at"] - now > 180:
                return cache_entry["token"]
                
        integration = await self.tenant_repo.get_by_organization_id(organization_id)
        
        if not integration:
            logger.warning("No tenant integration found", organization_id=organization_id)
            raise ValueError("Integration not found")
            
        if not integration.is_active:
            logger.warning("Tenant integration is inactive", organization_id=organization_id)
            raise ValueError("Integration is inactive")

        # Proactively refresh if token expires in less than 5 minutes
        refresh_threshold = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        if integration.token_expires_at < refresh_threshold:
            logger.info("Token expired or expiring soon, refreshing", organization_id=organization_id)
            
            try:
                refresh_token_plaintext = decrypt_token(integration.encrypted_refresh_token)
                token_response = await self.oauth_client.refresh_token(refresh_token_plaintext)
                
                new_access_token = token_response["access_token"]
                new_refresh_token = token_response.get("refresh_token", refresh_token_plaintext)
                expires_in = token_response.get("expires_in", 3600)
                
                integration = await self.tenant_repo.upsert_integration(
                    organization_id=organization_id,
                    mailbox_email=integration.mailbox_email,
                    encrypted_access_token=encrypt_token(new_access_token),
                    encrypted_refresh_token=encrypt_token(new_refresh_token),
                    token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                )
                logger.info("Successfully refreshed token", organization_id=organization_id)
            except Exception as e:
                logger.error("Failed to refresh token", organization_id=organization_id, error=str(e))
                await self.tenant_repo.update_error_state(organization_id, "Failed to refresh token: " + str(e))
                raise ValueError("Failed to obtain valid access token")
                
        decrypted_token = decrypt_token(integration.encrypted_access_token)
        expires_at_timestamp = integration.token_expires_at.replace(tzinfo=timezone.utc).timestamp()
        
        _token_cache[org_id_str] = {
            "token": decrypted_token,
            "expires_at": expires_at_timestamp
        }
        return decrypted_token
