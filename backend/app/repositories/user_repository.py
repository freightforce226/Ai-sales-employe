from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, UserRole

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_auth_user_id(self, auth_user_id: UUID) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.auth_user_id == auth_user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        organization_id: UUID,
        auth_user_id: UUID,
        full_name: str,
        email: str,
        role: UserRole = UserRole.sales_user,
    ) -> User:
        user = User(
            organization_id=organization_id,
            auth_user_id=auth_user_id,
            full_name=full_name,
            email=email,
            role=role,
            is_active=True,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
