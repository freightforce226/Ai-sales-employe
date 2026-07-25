from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr

from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.models.user import User, UserRole

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/settings", tags=["Organization Settings"])

class OrganizationProfileUpdate(BaseModel):
    display_name: str
    phone_number: Optional[str] = None
    website: Optional[str] = None
    timezone: Optional[str] = "UTC"
    country: Optional[str] = None

class OrganizationSettingsUpdate(BaseModel):
    sender_display_name: Optional[str] = None
    reply_to_email: Optional[str] = None
    default_signature: Optional[str] = None
    cc_emails: List[str] = []
    bcc_emails: List[str] = []
    ai_enabled: bool = False
    reply_style: str = "Professional"
    reply_length: str = "Medium"
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 15
    business_hours_enabled: bool = True
    working_days: List[str] = ["Mon","Tue","Wed","Thu","Fri"]
    start_time: str = "09:00"
    end_time: str = "18:00"
    notify_failed_replies: bool = True
    notify_outlook_disconnect: bool = True
    daily_summary_enabled: bool = False

class SettingsUpdateRequest(BaseModel):
    profile: OrganizationProfileUpdate
    settings: OrganizationSettingsUpdate

@router.get("")
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    org_id = current_user.organization_id

    # 1. Fetch profile from organizations
    res_org = await db.execute(
        text("SELECT id, name, display_name, logo_url, plan_tier, phone_number, website, timezone, country, created_at FROM organizations WHERE id = :org_id"),
        {"org_id": org_id}
    )
    org_row = res_org.fetchone()
    if not org_row:
        raise HTTPException(status_code=404, detail="Organization not found")

    # 2. Fetch or seed settings from organization_settings
    res_set = await db.execute(
        text("SELECT * FROM organization_settings WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    set_row = res_set.fetchone()
    if not set_row:
        # Seed default settings
        await db.execute(
            text("INSERT INTO organization_settings (organization_id) VALUES (:org_id) ON CONFLICT DO NOTHING"),
            {"org_id": org_id}
        )
        await db.commit()
        res_set = await db.execute(
            text("SELECT * FROM organization_settings WHERE organization_id = :org_id"),
            {"org_id": org_id}
        )
        set_row = res_set.fetchone()

    # 3. Fetch Outlook oauth status
    res_out = await db.execute(
        text("SELECT mailbox_email, is_active, last_refreshed_at FROM tenant_integrations WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    out_row = res_out.fetchone()
    outlook_info = {
        "connected": out_row.is_active if out_row else False,
        "connected_account": out_row.mailbox_email if out_row else None,
        "last_sync": out_row.last_refreshed_at if out_row else None
    }

    # 4. Map settings fields cleanly
    # Note: set_row is a Row object. Let's build a dict safely mapping array fields
    # PostgreSQL arrays come back as lists in Python/SQLAlchemy
    cc_list = list(set_row.cc_emails) if set_row.cc_emails is not None else []
    bcc_list = list(set_row.bcc_emails) if set_row.bcc_emails is not None else []
    days_list = list(set_row.working_days) if set_row.working_days is not None else []

    settings_dict = {
        "sender_display_name": set_row.sender_display_name,
        "reply_to_email": set_row.reply_to_email,
        "default_signature": set_row.default_signature,
        "cc_emails": cc_list,
        "bcc_emails": bcc_list,
        "ai_enabled": set_row.ai_enabled,
        "reply_style": set_row.reply_style,
        "reply_length": set_row.reply_length,
        "scheduler_enabled": set_row.scheduler_enabled,
        "scheduler_interval_minutes": set_row.scheduler_interval_minutes,
        "business_hours_enabled": set_row.business_hours_enabled,
        "working_days": days_list,
        "start_time": set_row.start_time,
        "end_time": set_row.end_time,
        "last_scheduler_run": set_row.last_scheduler_run,
        "notify_failed_replies": set_row.notify_failed_replies,
        "notify_outlook_disconnect": set_row.notify_outlook_disconnect,
        "daily_summary_enabled": set_row.daily_summary_enabled
    }

    profile_dict = {
        "display_name": org_row.display_name,
        "phone_number": org_row.phone_number,
        "website": org_row.website,
        "timezone": org_row.timezone or "UTC",
        "country": org_row.country
    }

    system_dict = {
        "organization_id": org_row.id,
        "created_date": org_row.created_at,
        "current_plan": org_row.plan_tier,
        "ai_sales_employee_version": "1.2.0-MVP"
    }

    return {
        "profile": profile_dict,
        "settings": settings_dict,
        "outlook": outlook_info,
        "system": system_dict,
        "is_admin": current_user.role == UserRole.org_admin
    }

@router.put("")
async def update_settings(
    payload: SettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    # Enforce authorization: Only Organization Admin
    if current_user.role != UserRole.org_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Organization Admins can modify settings."
        )

    org_id = current_user.organization_id

    # Execute updates inside a single database transaction
    try:
        # 1. Update organizations table
        await db.execute(
            text("""
                UPDATE organizations
                SET display_name = :display_name,
                    phone_number = :phone_number,
                    website = :website,
                    timezone = :timezone,
                    country = :country,
                    updated_at = NOW()
                WHERE id = :org_id
            """),
            {
                "org_id": org_id,
                "display_name": payload.profile.display_name,
                "phone_number": payload.profile.phone_number,
                "website": payload.profile.website,
                "timezone": payload.profile.timezone,
                "country": payload.profile.country
            }
        )

        # 2. Update organization_settings table
        await db.execute(
            text("""
                UPDATE organization_settings
                SET sender_display_name = :sender_display_name,
                    reply_to_email = :reply_to_email,
                    default_signature = :default_signature,
                    cc_emails = :cc_emails,
                    bcc_emails = :bcc_emails,
                    ai_enabled = :ai_enabled,
                    reply_style = :reply_style,
                    reply_length = :reply_length,
                    scheduler_enabled = :scheduler_enabled,
                    scheduler_interval_minutes = :scheduler_interval_minutes,
                    business_hours_enabled = :business_hours_enabled,
                    working_days = :working_days,
                    start_time = :start_time,
                    end_time = :end_time,
                    notify_failed_replies = :notify_failed_replies,
                    notify_outlook_disconnect = :notify_outlook_disconnect,
                    daily_summary_enabled = :daily_summary_enabled,
                    updated_at = NOW()
                WHERE organization_id = :org_id
            """),
            {
                "org_id": org_id,
                "sender_display_name": payload.settings.sender_display_name,
                "reply_to_email": payload.settings.reply_to_email,
                "default_signature": payload.settings.default_signature,
                "cc_emails": payload.settings.cc_emails,
                "bcc_emails": payload.settings.bcc_emails,
                "ai_enabled": payload.settings.ai_enabled,
                "reply_style": payload.settings.reply_style,
                "reply_length": payload.settings.reply_length,
                "scheduler_enabled": payload.settings.scheduler_enabled,
                "scheduler_interval_minutes": payload.settings.scheduler_interval_minutes,
                "business_hours_enabled": payload.settings.business_hours_enabled,
                "working_days": payload.settings.working_days,
                "start_time": payload.settings.start_time,
                "end_time": payload.settings.end_time,
                "notify_failed_replies": payload.settings.notify_failed_replies,
                "notify_outlook_disconnect": payload.settings.notify_outlook_disconnect,
                "daily_summary_enabled": payload.settings.daily_summary_enabled
            }
        )

        await db.commit()
        return {"success": True}

    except Exception as e:
        await db.rollback()
        logger.error("Failed to save organization settings", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {str(e)}"
        )
