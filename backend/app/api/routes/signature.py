from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import bleach
import uuid
import httpx
from typing import Optional

from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.signature import OrganizationSignatureSchema, SignatureDeleteResponse
from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(prefix="/api/v1/organization/settings/signature", tags=["Organization Signature"])
settings = get_settings()
logger = get_logger(__name__)

ALLOWED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
ALLOWED_IMAGE_MIME_TYPES = ('image/png', 'image/jpeg', 'image/webp')
MAX_BANNER_SIZE = 2 * 1024 * 1024  # 2MB

def compile_signature_html(
    sender_name: str, 
    designation: str, 
    department: Optional[str] = None, 
    phone: Optional[str] = None, 
    website: Optional[str] = None, 
    linkedin_url: Optional[str] = None
) -> str:
    """
    Helper to automatically compile clean, sanitized signature HTML from structured profile fields.
    """
    if not sender_name and not designation:
        return ""

    parts = ["Best regards,"]
    
    if sender_name:
        parts.append(f"<strong>{sender_name}</strong>")
        
    title_parts = []
    if designation:
        title_parts.append(designation)
    if department:
        title_parts.append(department)
    if title_parts:
        parts.append(" - ".join(title_parts))
        
    contact_parts = []
    if phone:
        contact_parts.append(f"Phone: {phone}")
    if contact_parts:
        parts.append(" | ".join(contact_parts))
        
    web_parts = []
    if website:
        web_parts.append(f"Web: {website}")
    if linkedin_url:
        web_parts.append(f"LinkedIn: {linkedin_url}")
    if web_parts:
        parts.append(" | ".join(web_parts))
        
    return f"<p>{'<br>'.join(parts)}</p>"

async def _supabase_request(method: str, url: str, headers: dict, **kwargs):
    client = httpx.AsyncClient(timeout=30.0)
    try:
        response = await client.request(method, url, headers=headers, **kwargs)
        return response
    finally:
        await client.aclose()

async def generate_signed_url(file_path: str) -> str:
    """
    Generates a 10-year signed URL for private Supabase storage objects.
    """
    if not file_path:
        return ""
    supabase_sign_file_url = f"{settings.supabase_url}/storage/v1/object/sign/tenant-attachments/{file_path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                supabase_sign_file_url,
                json={"expiresIn": 315360000},  # 10 years
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "application/json"
                }
            )
            if res.status_code == 200:
                signed_path = res.json().get("signedURL") or res.json().get("signedUrl")
                if signed_path:
                    url_out = f"{settings.supabase_url}/storage/v1{signed_path}" if signed_path.startswith('/') else signed_path
                    logger.info("SIGNATURE RENDER ENGINE - GENERATED SIGNED BANNER URL", stored_path=file_path, generated_url=url_out)
                    return url_out
    except Exception as e:
        logger.error("Failed to generate signature banner signed URL", error=str(e))
    return ""

@router.get("", response_model=OrganizationSignatureSchema)
async def get_signature(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get organization's email signature settings.
    If not configured, returns is_configured=False with empty fields.
    """
    org_id = current_user.organization_id
    
    res = await db.execute(
        text("""
            SELECT sender_name, designation, department, phone, website, linkedin_url, signature_html,
                   footer_image_name, footer_image_content_type, footer_image_size, footer_image_path, updated_at
            FROM organization_signatures
            WHERE organization_id = :org_id
        """),
        {"org_id": org_id}
    )
    row = res.fetchone()
    
    if not row:
        return OrganizationSignatureSchema(
            is_configured=False,
            sender_name="",
            designation="",
            department="",
            phone="",
            website="",
            linkedin_url="",
            signature_html="",
            footer_image_url="",
            updated_at=None
        )

    keys = [
        "sender_name", "designation", "department", "phone", "website", "linkedin_url", "signature_html",
        "footer_image_name", "footer_image_content_type", "footer_image_size", "footer_image_path"
    ]
    
    data = {"is_configured": True}
    for key, val in zip(keys, row[:11]):
        data[key] = val if val is not None else ""
        
    if row[11]:
        data["updated_at"] = row[11].isoformat()
        
    # Generate public signed URL
    data["footer_image_url"] = await generate_signed_url(data.get("footer_image_path"))
        
    return OrganizationSignatureSchema(**data)

@router.put("", response_model=OrganizationSignatureSchema)
async def update_signature(
    payload: OrganizationSignatureSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update or create organization signature settings.
    Automatically generates the signature HTML on the backend.
    """
    org_id = current_user.organization_id
    
    # 1. Compile signature HTML dynamically from structured profile fields
    generated_html = compile_signature_html(
        sender_name=payload.sender_name or "",
        designation=payload.designation or "",
        department=payload.department,
        phone=payload.phone,
        website=payload.website,
        linkedin_url=payload.linkedin_url
    )
    
    # 2. Sanitize signature HTML using bleach
    from bleach.css_sanitizer import CSSSanitizer
    allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'span', 'a', 'div', 'img']
    allowed_attrs = {
        'a': ['href', 'title', 'target'],
        'span': ['style'],
        'p': ['style'],
        'div': ['style'],
        'img': ['src', 'alt', 'style', 'width', 'height']
    }
    allowed_styles = ['color', 'font-size', 'font-family', 'font-weight', 'line-height', 'margin', 'padding', 'border']
    css_sanitizer = CSSSanitizer(allowed_css_properties=allowed_styles)
    
    sanitized_html = bleach.clean(
        generated_html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        css_sanitizer=css_sanitizer,
        strip=True
    )
    
    await db.execute(
        text("""
            INSERT INTO organization_signatures (
                organization_id, sender_name, designation, department, sender_email, phone, website, linkedin_url, signature_html,
                footer_image_name, footer_image_content_type, footer_image_size, footer_image_path, updated_at
            ) VALUES (
                :org_id, :sender_name, :designation, :department, '', :phone, :website, :linkedin_url, :signature_html,
                :footer_image_name, :footer_image_content_type, :footer_image_size, :footer_image_path, NOW()
            )
            ON CONFLICT (organization_id) DO UPDATE SET
                sender_name = EXCLUDED.sender_name,
                designation = EXCLUDED.designation,
                department = EXCLUDED.department,
                sender_email = EXCLUDED.sender_email,
                phone = EXCLUDED.phone,
                website = EXCLUDED.website,
                linkedin_url = EXCLUDED.linkedin_url,
                signature_html = EXCLUDED.signature_html,
                footer_image_name = EXCLUDED.footer_image_name,
                footer_image_content_type = EXCLUDED.footer_image_content_type,
                footer_image_size = EXCLUDED.footer_image_size,
                footer_image_path = EXCLUDED.footer_image_path,
                updated_at = NOW();
        """),
        {
            "org_id": org_id,
            "sender_name": payload.sender_name or "",
            "designation": payload.designation or "",
            "department": payload.department or None,
            "phone": payload.phone or None,
            "website": payload.website or None,
            "linkedin_url": payload.linkedin_url or None,
            "signature_html": sanitized_html,
            "footer_image_name": payload.footer_image_name or None,
            "footer_image_content_type": payload.footer_image_content_type or None,
            "footer_image_size": payload.footer_image_size or None,
            "footer_image_path": payload.footer_image_path or None
        }
    )
    await db.commit()
    
    result_dict = payload.model_dump()
    result_dict["signature_html"] = sanitized_html
    result_dict["is_configured"] = True
    result_dict["footer_image_url"] = await generate_signed_url(payload.footer_image_path)
    return OrganizationSignatureSchema(**result_dict)

@router.delete("", response_model=SignatureDeleteResponse)
async def delete_signature(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Delete organization signature settings.
    """
    org_id = current_user.organization_id
    
    await db.execute(
        text("DELETE FROM organization_signatures WHERE organization_id = :org_id"),
        {"org_id": org_id}
    )
    await db.commit()
    return SignatureDeleteResponse(success=True, message="Signature deleted successfully.")

@router.post("/banner")
async def upload_signature_banner(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Accepts banner images (up to 2MB), uploads to generic organization-assets bucket path,
    and returns storage path with image metadata.
    """
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(ALLOWED_IMAGE_EXTENSIONS) or file.content_type in ALLOWED_IMAGE_MIME_TYPES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PNG, JPG, JPEG and WEBP images are allowed."
        )

    file_content = await file.read()
    file_size = len(file_content)
    if file_size > MAX_BANNER_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Banner exceeds maximum allowed size of 2MB."
        )

    org_id = current_user.organization_id
    file_id = uuid.uuid4()
    storage_path = f"organization-assets/{org_id}/signatures/{file_id}_{file.filename}"
    
    supabase_upload_url = f"{settings.supabase_url}/storage/v1/object/tenant-attachments/{storage_path}"
    
    try:
        res = await _supabase_request(
            "POST",
            supabase_upload_url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": file.content_type or "application/octet-stream"
            },
            content=file_content
        )
        if res.status_code not in (200, 201):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Supabase Storage banner upload failed: {res.text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed Supabase banner upload request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Banner upload error."
        )

    public_url = await generate_signed_url(storage_path)
    return {
        "footer_image_name": file.filename,
        "footer_image_content_type": file.content_type,
        "footer_image_size": file_size,
        "footer_image_path": storage_path,
        "footer_image_url": public_url
    }
