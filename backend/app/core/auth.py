from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.repositories.user_repository import UserRepository
from app.models.user import User
from app.core.config import get_settings
from uuid import UUID
import httpx

settings = get_settings()

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        # Fallback to Authorization Header for compatibility (e.g. n8n or client bypasses)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing"
        )

    # Resolve Supabase user verification URL
    user_url = f"{settings.supabase_url}/auth/v1/user"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                user_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": settings.supabase_anon_key
                }
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired authentication token"
                )
            
            user_data = response.json()
            auth_user_id = UUID(user_data["id"])
            
            user_repo = UserRepository(db)
            user = await user_repo.get_by_auth_user_id(auth_user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not onboarded in database"
                )
            
            return user
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Authentication failed: {str(e)}"
            )
