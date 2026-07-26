"""
Purpose of this file.
FastAPI router for OAuth endpoints.
Responsibility of this file.
Handling incoming HTTP requests for starting OAuth flow and receiving the callback from Microsoft.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.models.user import User
from app.db.session import get_db_session
from app.schemas.oauth import OAuthCallbackResponse, OAuthConnectResponse
from app.core.config import get_settings
from app.services.oauth_service import OAuthService

router = APIRouter(tags=["OAuth"])
settings = get_settings()


@router.get("/connect", response_model=OAuthConnectResponse)
async def connect_oauth(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Initiate the Microsoft OAuth flow for a specific organization.
    """
    oauth_service = OAuthService(session)
    try:
        url = await oauth_service.generate_auth_url(current_user.organization_id)
        return OAuthConnectResponse(authorization_url=url)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        )


@router.get("/status")
async def get_oauth_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Check if the user's organization has a connected Outlook account.
    """
    oauth_service = OAuthService(session)
    integration = await oauth_service.tenant_repo.get_by_organization_id(current_user.organization_id)
    if not integration:
        return {"connected": False, "mailbox_email": None}
    return {
        "connected": integration.is_active,
        "mailbox_email": integration.mailbox_email
    }


from fastapi.responses import RedirectResponse

@router.get("/callback")
async def oauth_callback(
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="State value to prevent CSRF and link to tenant"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Handle the Microsoft OAuth callback, exchange code for tokens, store them securely, and redirect to frontend.
    """
    oauth_service = OAuthService(session)
    try:
        await oauth_service.handle_callback(code, state)
        return RedirectResponse(url=f"{settings.frontend_url}/dashboard?outlook=success")
    except ValueError as e:
        return RedirectResponse(url=f"{settings.frontend_url}/dashboard?outlook=error&error={str(e)}")
    except Exception:
        return RedirectResponse(url=f"{settings.frontend_url}/dashboard?outlook=error")
