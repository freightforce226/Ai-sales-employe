from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.core.auth import get_current_user, settings
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.repositories.user_repository import UserRepository
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.user import UserResponse
from app.schemas.organization import BrandingResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from uuid import UUID
import httpx

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

# Schema definitions
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: str
    company_website: Optional[str] = None
    company_country: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#2563EB"
    secondary_color: str = "#0F172A"
    accent_color: str = "#F97316"

class SignupResponse(BaseModel):
    user_id: UUID
    email: str
    confirmation_required: bool

class SessionRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = 3600

class MeResponse(BaseModel):
    user: UserResponse
    organization: Optional[UUID] = None
    role: str
    branding: Optional[BrandingResponse] = None


# Utility to set HttpOnly cookies
def set_auth_cookies(response: Response, access_token: str, refresh_token: str, expires_in: int = 3600):
    is_prod = settings.environment == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=expires_in,
        path="/"
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=is_prod,
            samesite="lax",
            max_age=30 * 24 * 3600, # 30 days
            path="/"
        )

# Utility to clear cookies
def clear_auth_cookies(response: Response):
    is_prod = settings.environment == "production"
    response.delete_cookie(key="access_token", path="/", secure=is_prod, samesite="lax")
    response.delete_cookie(key="refresh_token", path="/", secure=is_prod, samesite="lax")

@router.post("/signup", response_model=SignupResponse)
async def signup(request: SignupRequest, response: Response, db: AsyncSession = Depends(get_db_session)):
    """
    1. Sign up user in Supabase.
    2. Create Organization.
    3. Save User Profile as Org Owner in database.
    4. Set HttpOnly cookies.
    """
    user_repo = UserRepository(db)
    org_repo = OrganizationRepository(db)

    # Check if user already exists
    existing_user = await user_repo.get_by_email(request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # 1. Sign up user in Supabase Auth using Admin API (completely bypasses email confirmation/verification emails)
    use_admin_api = True
    session = None
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if use_admin_api:
                # Use Admin API to create and auto-confirm user (bypassing email rates limits & confirmation in dev)
                signup_url = f"{settings.supabase_url}/auth/v1/admin/users"
                sb_response = await client.post(
                    signup_url,
                    json={
                        "email": request.email,
                        "password": request.password,
                        "email_confirm": True
                    },
                    headers={
                        "apikey": settings.supabase_service_role_key,
                        "Authorization": f"Bearer {settings.supabase_service_role_key}"
                    }
                )
                if sb_response.status_code != 201 and sb_response.status_code != 200:
                    sb_error = sb_response.json()
                    error_msg = sb_error.get("msg") or sb_error.get("error_description") or "Failed to create user via admin API"
                    raise HTTPException(
                        status_code=sb_response.status_code,
                        detail=error_msg
                    )
                
                sb_data = sb_response.json()
                auth_user_id = UUID(sb_data["id"])
                
                # Automatically login the user to obtain a session
                token_url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
                login_response = await client.post(
                    token_url,
                    json={"email": request.email, "password": request.password},
                    headers={"apikey": settings.supabase_anon_key}
                )
                if login_response.status_code == 200:
                    session = login_response.json()
            else:
                # Standard signup
                signup_url = f"{settings.supabase_url}/auth/v1/signup"
                sb_response = await client.post(
                    signup_url,
                    json={"email": request.email, "password": request.password},
                    headers={"apikey": settings.supabase_anon_key}
                )
                if sb_response.status_code != 200:
                    sb_error = sb_response.json()
                    error_msg = sb_error.get("msg") or sb_error.get("error_description") or "Failed to sign up in authentication provider"
                    raise HTTPException(
                        status_code=sb_response.status_code,
                        detail=error_msg
                    )
                
                sb_data = sb_response.json()
                session = sb_data.get("session")
                if "user" in sb_data:
                    auth_user_id = UUID(sb_data["user"]["id"])
                else:
                    auth_user_id = UUID(sb_data["id"])
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Auth provider communication error: {str(e)}"
            )

    # 2. Create Organization
    slug = request.company_name.lower().replace(" ", "-").replace("_", "-")
    theme_config = {
        "primary_color": request.primary_color,
        "secondary_color": request.secondary_color,
        "accent_color": request.accent_color,
        "favicon_url": request.favicon_url,
        "website": request.company_website,
        "country": request.company_country
    }
    
    org = await org_repo.create_organization(
        name=slug,
        display_name=request.company_name,
        logo_url=request.logo_url,
        theme_config=theme_config
    )

    # 3. Create User Profile
    user = await user_repo.create_user(
        organization_id=org.id,
        auth_user_id=auth_user_id,
        full_name=request.full_name,
        email=request.email,
        role=UserRole.org_admin
    )

    # 4. Set cookies if session returned immediately
    if session:
        set_auth_cookies(
            response,
            access_token=session["access_token"],
            refresh_token=session.get("refresh_token"),
            expires_in=session.get("expires_in", 3600)
        )

    return SignupResponse(
        user_id=user.id,
        email=user.email,
        confirmation_required=(session is None)
    )

@router.post("/login")
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db_session)):
    """
    Exchange email/password with Supabase, set HttpOnly cookies, return user profile.
    """
    token_url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            sb_response = await client.post(
                token_url,
                json={"email": request.email, "password": request.password},
                headers={"apikey": settings.supabase_anon_key}
            )
            if sb_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            sb_data = sb_response.json()
            access_token = sb_data["access_token"]
            refresh_token = sb_data.get("refresh_token")
            expires_in = sb_data.get("expires_in", 3600)
            auth_user_id = UUID(sb_data["user"]["id"])
            
            # Fetch user profile from database to confirm existence
            user_repo = UserRepository(db)
            user = await user_repo.get_by_auth_user_id(auth_user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not completed"
                )
                
            set_auth_cookies(response, access_token, refresh_token, expires_in)
            return {"success": True, "user_id": user.id}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Login failed: {str(e)}"
            )

@router.post("/logout")
async def logout(response: Response):
    """
    Clear access and refresh token cookies.
    """
    clear_auth_cookies(response)
    return {"success": True}

@router.post("/refresh")
async def refresh(request: Request, response: Response):
    """
    Refresh access token using refresh token cookie.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing"
        )
        
    token_url = f"{settings.supabase_url}/auth/v1/token?grant_type=refresh_token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            sb_response = await client.post(
                token_url,
                json={"refresh_token": refresh_token},
                headers={"apikey": settings.supabase_anon_key}
            )
            if sb_response.status_code != 200:
                clear_auth_cookies(response)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session expired"
                )
            
            sb_data = sb_response.json()
            set_auth_cookies(
                response,
                access_token=sb_data["access_token"],
                refresh_token=sb_data.get("refresh_token"),
                expires_in=sb_data.get("expires_in", 3600)
            )
            return {"success": True}
        except Exception as e:
            clear_auth_cookies(response)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Refresh session failed: {str(e)}"
            )

@router.post("/session")
async def set_session(request: SessionRequest, response: Response, db: AsyncSession = Depends(get_db_session)):
    """
    Establish session and set HttpOnly cookies using an access_token/refresh_token.
    This is used after email verification redirects.
    """
    user_url = f"{settings.supabase_url}/auth/v1/user"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            sb_response = await client.get(
                user_url,
                headers={
                    "Authorization": f"Bearer {request.access_token}",
                    "apikey": settings.supabase_anon_key
                }
            )
            if sb_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid session token"
                )
            
            sb_data = sb_response.json()
            auth_user_id = UUID(sb_data["id"])
            
            user_repo = UserRepository(db)
            user = await user_repo.get_by_auth_user_id(auth_user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found in database"
                )
                
            set_auth_cookies(
                response,
                access_token=request.access_token,
                refresh_token=request.refresh_token,
                expires_in=request.expires_in or 3600
            )
            return {"success": True, "user_id": user.id}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set session: {str(e)}"
            )

@router.get("/me", response_model=MeResponse)
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    """
    Returns user details, organization ID, role, and branding settings.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(current_user.organization_id)
    
    branding_info = None
    if org:
        branding_info = BrandingResponse(
            company_name=org.display_name,
            logo_url=org.logo_url,
            theme_config=org.theme_config or {}
        )
        
    return MeResponse(
        user=UserResponse.from_orm(current_user),
        organization=current_user.organization_id,
        role=current_user.role,
        branding=branding_info
    )

