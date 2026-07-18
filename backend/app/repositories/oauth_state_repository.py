"""
Purpose of this file.
Repository for managing OAuthState database operations.
Responsibility of this file.
Providing an async interface for CRUD operations on oauth_states.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_state import OAuthState


class OAuthStateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_state(self, organization_id: UUID, state: str, expires_at: datetime) -> OAuthState:
        oauth_state = OAuthState(
            organization_id=organization_id,
            state=state,
            expires_at=expires_at,
        )
        self.session.add(oauth_state)
        await self.session.commit()
        await self.session.refresh(oauth_state)
        return oauth_state

    async def get_and_delete_state(self, state: str) -> Optional[OAuthState]:
        result = await self.session.execute(
            select(OAuthState).where(OAuthState.state == state)
        )
        oauth_state = result.scalar_one_or_none()
        
        if oauth_state:
            await self.session.execute(delete(OAuthState).where(OAuthState.id == oauth_state.id))
            await self.session.commit()
            
        return oauth_state
