from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.auth import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.email_branding import EmailBrandingSchema

router = APIRouter(prefix="/api/v1/organization/settings", tags=["Organization settings"])

@router.get("/email-branding", response_model=EmailBrandingSchema)
async def get_email_branding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get organization's email branding settings.
    """
    org_id = current_user.organization_id
    
    # Query database
    res = await db.execute(
        text("""
            SELECT sender_name, designation, reply_email, phone, website, linkedin, company_logo, signature_html, signature_plain
            FROM organization_email_branding
            WHERE organization_id = :org_id
        """),
        {"org_id": org_id}
    )
    row = res.fetchone()
    
    if not row:
        # Insert default row
        await db.execute(
            text("""
                INSERT INTO organization_email_branding (organization_id, sender_name, designation, reply_email, phone, website, linkedin, signature_html, signature_plain)
                VALUES (
                    :org_id, 'Sanjay', 'Customer Relationship Manager', 'info@freightforce.ai', 
                    '+1 (555) 0199', 'www.freightforce.ai', 'linkedin.com/company/freightforce',
                    '<p>Best regards,<br><strong>Sanjay</strong><br>Customer Relationship Manager<br>FreightForce</p>',
                    'Best regards,\nSanjay\nCustomer Relationship Manager\nFreightForce'
                )
            """),
            {"org_id": org_id}
        )
        await db.commit()
        
        # Re-query
        res = await db.execute(
            text("""
                SELECT sender_name, designation, reply_email, phone, website, linkedin, company_logo, signature_html, signature_plain
                FROM organization_email_branding
                WHERE organization_id = :org_id
            """),
            {"org_id": org_id}
        )
        row = res.fetchone()
        
    keys = ["sender_name", "designation", "reply_email", "phone", "website", "linkedin", "company_logo", "signature_html", "signature_plain"]
    data = dict(zip(keys, row))
    return EmailBrandingSchema(**data)

@router.put("/email-branding", response_model=EmailBrandingSchema)
async def update_email_branding(
    payload: EmailBrandingSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update organization's email branding settings.
    """
    org_id = current_user.organization_id
    
    await db.execute(
        text("""
            INSERT INTO organization_email_branding (
                organization_id, sender_name, designation, reply_email, phone, website, linkedin, company_logo, signature_html, signature_plain, updated_at
            ) VALUES (
                :org_id, :sender_name, :designation, :reply_email, :phone, :website, :linkedin, :company_logo, :signature_html, :signature_plain, NOW()
            )
            ON CONFLICT (organization_id) DO UPDATE SET
                sender_name = EXCLUDED.sender_name,
                designation = EXCLUDED.designation,
                reply_email = EXCLUDED.reply_email,
                phone = EXCLUDED.phone,
                website = EXCLUDED.website,
                linkedin = EXCLUDED.linkedin,
                company_logo = EXCLUDED.company_logo,
                signature_html = EXCLUDED.signature_html,
                signature_plain = EXCLUDED.signature_plain,
                updated_at = NOW();
        """),
        {
            "org_id": org_id,
            "sender_name": payload.sender_name,
            "designation": payload.designation,
            "reply_email": payload.reply_email,
            "phone": payload.phone,
            "website": payload.website,
            "linkedin": payload.linkedin,
            "company_logo": payload.company_logo,
            "signature_html": payload.signature_html,
            "signature_plain": payload.signature_plain
        }
    )
    await db.commit()
    return payload
