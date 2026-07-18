from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from app.core.config import get_settings
from app.core.logging import get_logger
import httpx
import uuid
from typing import Optional

router = APIRouter(prefix="/api/v1/attachments", tags=["Email Attachments"])
settings = get_settings()
logger = get_logger(__name__)

# Max file size constraint: 20 MB (20 * 1024 * 1024 bytes)
MAX_FILE_SIZE = 20 * 1024 * 1024


async def _supabase_request(method: str, url: str, headers: dict, **kwargs):
    """
    Performs a single Supabase HTTP request using a fresh client per call.
    Avoids asyncio.CancelledError from nested async-with context managers in ASGI.
    """
    client = httpx.AsyncClient(timeout=30.0)
    try:
        response = await client.request(method, url, headers=headers, **kwargs)
        return response
    finally:
        await client.aclose()

@router.get("")
async def get_attachments(
    page: int = 1,
    limit: int = 10,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves the list of attachments for the current organization, optionally matching search terms.
    """
    org_id = current_user.organization_id
    offset = (page - 1) * limit

    query_str = "SELECT * FROM email_attachments WHERE organization_id = :org_id"
    count_str = "SELECT COUNT(*) FROM email_attachments WHERE organization_id = :org_id"
    params = {"org_id": org_id}

    if q:
        query_str += " AND file_name ILIKE :q"
        count_str += " AND file_name ILIKE :q"
        params["q"] = f"%{q}%"

    query_str += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    try:
        res = await db.execute(text(query_str), params)
        attachments_rows = res.fetchall()

        count_res = await db.execute(text(count_str), {k: v for k, v in params.items() if k not in ("limit", "offset")})
        total = count_res.scalar()

        # Format attachments list
        attachments = []
        for r in attachments_rows:
            attachments.append({
                "id": str(r.id),
                "organization_id": str(r.organization_id),
                "attachment_name": r.file_name,
                "file_name": r.file_name,
                "attachment_type": r.file_type,
                "file_type": r.file_type,
                "storage_path": r.file_path,
                "file_path": r.file_path,
                "is_active": getattr(r, "is_active", True),
                "attach_to_every_email": getattr(r, "attach_to_every_email", False),
                "file_size": getattr(r, "file_size", 0),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "industry_tag": r.industry_tag
            })

        return {"attachments": attachments, "total": total}
    except Exception as e:
        logger.error("Failed to query attachments list", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve email attachments."
        )

@router.get("/{id}")
async def get_attachment(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves metadata details of a single attachment.
    """
    org_id = current_user.organization_id
    try:
        res = await db.execute(
            text("SELECT * FROM email_attachments WHERE id = :id AND organization_id = :org_id"),
            {"id": id, "org_id": org_id}
        )
        r = res.fetchone()
        if not r:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found."
            )
        return {
            "id": str(r.id),
            "organization_id": str(r.organization_id),
            "attachment_name": r.file_name,
            "attachment_type": r.file_type,
            "storage_path": r.file_path,
            "is_active": getattr(r, "is_active", True),
            "attach_to_every_email": getattr(r, "attach_to_every_email", False),
            "file_size": getattr(r, "file_size", 0),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "industry_tag": r.industry_tag
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error("Failed to retrieve attachment details", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving attachment details."
        )

@router.get("/{id}/download")
async def download_attachment(
    id: uuid.UUID,
    preview: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Secure download/preview endpoint.
    If preview=True, redirects to a secure temporary Supabase CDN Signed URL (instant load).
    Otherwise, streams proxy bytes directly (compatible with tests and workflows).
    """
    org_id = current_user.organization_id
    from app.db.session import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT file_path, file_name FROM email_attachments WHERE id = :id AND organization_id = :org_id"),
            {"id": id, "org_id": org_id}
        )
        r = res.fetchone()
        if not r:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found."
            )
        file_path, file_name = r

    import mimetypes, os
    storage_basename = os.path.basename(file_path)
    parts = storage_basename.split('_', 1)
    original_filename = parts[1] if len(parts) > 1 else storage_basename

    # 1. Direct Signed URL redirect for instant preview
    if preview:
        supabase_sign_file_url = f"{settings.supabase_url}/storage/v1/object/sign/tenant-attachments/{file_path}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    supabase_sign_file_url,
                    json={"expiresIn": 900},
                    headers={
                        "apikey": settings.supabase_service_role_key,
                        "Authorization": f"Bearer {settings.supabase_service_role_key}",
                        "Content-Type": "application/json"
                    }
                )
                if res.status_code == 200:
                    signed_path = res.json().get("signedURL") or res.json().get("signedUrl")
                    if signed_path:
                        if not signed_path.startswith("/storage/v1"):
                            signed_path = f"/storage/v1{signed_path}"
                        full_signed_url = f"{settings.supabase_url}{signed_path}" if signed_path.startswith('/') else signed_path
                        from fastapi.responses import RedirectResponse
                        return RedirectResponse(url=full_signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        except Exception as e:
            logger.error("Failed to generate Supabase signed URL, falling back to proxy stream", error=str(e))

    # 2. Streaming proxy fallback (or normal download)
    import mimetypes
    mime_type, _ = mimetypes.guess_type(original_filename)
    media_type = mime_type or "application/pdf"
    supabase_download_url = f"{settings.supabase_url}/storage/v1/object/authenticated/tenant-attachments/{file_path}"

    async def file_streamer():
        client = httpx.AsyncClient(timeout=30.0)
        try:
            async with client.stream(
                "GET",
                supabase_download_url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"
                }
            ) as response:
                if response.status_code != 200:
                    yield b"Failed to retrieve file from Supabase storage."
                    return
                async for chunk in response.aiter_bytes():
                    yield chunk
        except Exception as e:
            logger.error("Failed to stream attachment from Supabase fallback", error=str(e))
            yield f"Error: {str(e)}".encode('utf-8')
        finally:
            await client.aclose()

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        file_streamer(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{original_filename}",
            "Cache-Control": "private, no-cache",
        }
    )

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_attachment(
    file: UploadFile = File(...),
    attachment_name: Optional[str] = Form(None),
    attachment_type: str = Form(...),
    always_attach: bool = Form(True), # Defaults to true (Always Attach ON)
    status_state: str = Form("active"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Accepts only PDF attachments (up to 20MB), uploads to Supabase storage, and inserts a db record.
    """
    # 1. File type validation (PDF and common images)
    ALLOWED_EXTENSIONS = ('.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp')
    ALLOWED_MIME_TYPES = ('application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp')
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(ALLOWED_EXTENSIONS) or file.content_type in ALLOWED_MIME_TYPES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents and images (PNG, JPEG, GIF, WEBP) are allowed."
        )

    # 2. File size validation
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of 20MB. Size: {file_size / (1024*1024):.2f}MB"
        )

    org_id = current_user.organization_id
    file_id = uuid.uuid4()
    storage_path = f"{org_id}/{file_id}_{file.filename}"
    display_name = attachment_name.strip() if (attachment_name and attachment_name.strip()) else file.filename

    # 3. Upload to Supabase 'tenant-attachments' bucket
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
                detail=f"Supabase Storage upload failed: {res.text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error("Failed Supabase upload request", error=str(e), exc_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Attachment upload error [{type(e).__name__}]: {str(e)}"
        )

    # 4. Insert database record
    is_active = (status_state == "active")
    attachment_id = uuid.uuid4()

    try:
        await db.execute(
            text("""
                INSERT INTO email_attachments (id, organization_id, file_name, file_type, file_path, is_active, attach_to_every_email, file_size, created_at, updated_at)
                VALUES (:id, :org_id, :file_name, :file_type, :file_path, :is_active, :attach_to_every_email, :file_size, NOW(), NOW())
            """),
            {
                "id": attachment_id,
                "org_id": org_id,
                "file_name": display_name,
                "file_type": attachment_type,
                "file_path": storage_path,
                "is_active": is_active,
                "attach_to_every_email": always_attach,
                "file_size": file_size
            }
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        import traceback
        traceback.print_exc()
        logger.error("Failed to insert attachment record", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save attachment metadata: {str(e)}"
        )

    return {"id": str(attachment_id), "file_name": display_name, "storage_path": storage_path}

@router.put("/{id}")
async def update_attachment(
    id: uuid.UUID,
    attachment_name: str,
    attachment_type: str,
    always_attach: bool,
    is_active: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Updates the attachment's metadata variables.
    """
    org_id = current_user.organization_id
    try:
        res = await db.execute(
            text("""
                UPDATE email_attachments 
                SET file_name = :file_name, file_type = :file_type, attach_to_every_email = :always, is_active = :active, updated_at = NOW()
                WHERE id = :id AND organization_id = :org_id
            """),
            {
                "id": id,
                "org_id": org_id,
                "file_name": attachment_name,
                "file_type": attachment_type,
                "always": always_attach,
                "active": is_active
            }
        )
        await db.commit()
        return {"success": True}
    except Exception as e:
        await db.rollback()
        logger.error("Failed to update attachment metadata", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update attachment metadata."
        )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Deletes the attachment row from postgres and wipes the file from Supabase.
    """
    org_id = current_user.organization_id
    res = await db.execute(
        text("SELECT file_path FROM email_attachments WHERE id = :id AND organization_id = :org_id"),
        {"id": id, "org_id": org_id}
    )
    r = res.fetchone()
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found."
        )

    file_path = r[0]

    # Delete from Supabase Storage
    supabase_delete_url = f"{settings.supabase_url}/storage/v1/object/tenant-attachments/{file_path}"
    try:
        await _supabase_request(
            "DELETE",
            supabase_delete_url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}"
            }
        )
    except Exception as err:
        logger.warning("Supabase storage deletion failure (continuing database cleanup)", error=str(err))

    # Delete from postgres
    try:
        await db.execute(
            text("DELETE FROM email_attachments WHERE id = :id AND organization_id = :org_id"),
            {"id": id, "org_id": org_id}
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("Failed to delete attachment row", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete attachment record."
        )

@router.post("/{id}/replace")
async def replace_attachment(
    id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Replaces the PDF binary data inside Supabase storage and updates metadata stats.
    """
    try:
        ALLOWED_EXTENSIONS = ('.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp')
        ALLOWED_MIME_TYPES = ('application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp')
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith(ALLOWED_EXTENSIONS) or file.content_type in ALLOWED_MIME_TYPES):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF documents and images (PNG, JPEG, GIF, WEBP) are allowed."
            )

        file_content = await file.read()
        file_size = len(file_content)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds maximum allowed 20MB limit."
            )

        org_id = current_user.organization_id
        res = await db.execute(
            text("SELECT file_path FROM email_attachments WHERE id = :id AND organization_id = :org_id"),
            {"id": id, "org_id": org_id}
        )
        r = res.fetchone()
        if not r:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment record not found."
            )

        old_file_path = r[0]

        # Delete old file from Supabase
        supabase_delete_url = f"{settings.supabase_url}/storage/v1/object/tenant-attachments/{old_file_path}"
        try:
            await _supabase_request(
                "DELETE",
                supabase_delete_url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"
                }
            )
        except Exception as err:
            logger.warning("Replacing file: old Supabase deletion skipped", error=str(err))

        # Upload new file
        file_id = uuid.uuid4()
        new_storage_path = f"{org_id}/{file_id}_{file.filename}"
        supabase_upload_url = f"{settings.supabase_url}/storage/v1/object/tenant-attachments/{new_storage_path}"

        try:
            upload_res = await _supabase_request(
                "POST",
                supabase_upload_url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": file.content_type or "application/octet-stream"
                },
                content=file_content
            )
            if upload_res.status_code not in (200, 201):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Supabase Storage replace upload failed: {upload_res.text}"
                )
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error("Failed to replace object upload", error=str(e), exc_type=type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Replace attachment upload error [{type(e).__name__}]: {str(e)}"
            )

        # Update database
        try:
            await db.execute(
                text("""
                    UPDATE email_attachments 
                    SET file_name = :file_name, file_path = :file_path, file_size = :file_size, updated_at = NOW()
                    WHERE id = :id AND organization_id = :org_id
                """),
                {
                    "id": id,
                    "org_id": org_id,
                    "file_name": file.filename,
                    "file_path": new_storage_path,
                    "file_size": file_size
                }
            )
            await db.commit()
            return {"success": True, "file_name": file.filename, "storage_path": new_storage_path}
        except Exception as e:
            await db.rollback()
            logger.error("Failed to update replace record", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update database metadata."
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server replacement error: {str(e)}"
        )
