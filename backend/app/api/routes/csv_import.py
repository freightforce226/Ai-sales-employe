from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
import io
import csv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from app.core.config import get_settings
from app.core.logging import get_logger
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import httpx
import uuid
import json

router = APIRouter(prefix="/api/v1/import", tags=["CSV Import"])
settings = get_settings()
logger = get_logger(__name__)

class StartImportRequest(BaseModel):
    storage_path: str
    column_mapping: Dict[str, str]
    headers: List[str]
    header_row: int = Field(0, ge=0, le=20)
    file_name: Optional[str] = "import.csv"

@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    header_row: int = Form(0),
    current_user: User = Depends(get_current_user)
):
    """
    Normalizes a CSV file based on the header_row, uploads it to Supabase Storage, and returns the relative storage path.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported."
        )

    file_content = await file.read()

    # Try decoding fallbacks: utf-8-sig, utf-8, latin-1, cp1252
    text = None
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            text = file_content.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode CSV file. Only UTF-8, Latin-1, or CP1252 encodings are supported."
        )

    # Detect original line endings
    line_terminator = "\r\n" if "\r\n" in text else "\n"

    try:
        f = io.StringIO(text)
        reader = csv.reader(f)
        rows = list(reader)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV format: {str(e)}"
        )

    # Validate empty CSV file
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV is empty"
        )

    # Validate header row bounds (Don't trust frontend)
    if header_row < 0:
        header_row = 0

    if header_row >= len(rows):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid header_row index: {header_row}. File only has {len(rows)} rows."
        )

    # Validate header row is not empty
    header = rows[header_row]
    if not any(str(c).strip() for c in header):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Detected header row is empty"
        )

    # Normalize rows: slice from header_row and filter out blank rows
    raw_normalized_rows = rows[header_row:]
    normalized_rows = [
        r for r in raw_normalized_rows
        if any(str(c).strip() for c in r)
    ]

    if not normalized_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV contains no data after normalization"
        )

    # Rebuild normalized CSV with consistent line endings and preserve quoted commas/values
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=line_terminator)
    writer.writerows(normalized_rows)
    normalized_content = out.getvalue().encode("utf-8")

    # Generate a unique path: organization_id/batch_id_filename
    org_id = current_user.organization_id
    file_id = uuid.uuid4()
    storage_path = f"{org_id}/{file_id}_{file.filename}"

    # Upload ONLY the normalized CSV to Supabase Storage bucket named 'csv-imports'
    supabase_upload_url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{storage_path}"
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                supabase_upload_url,
                content=normalized_content,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "text/csv"
                }
            )
            
            # Support both 200 and 201 statuses
            if res.status_code not in (200, 201):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Supabase Storage upload failed: {res.text}"
                )
            
            return {
                "storage_path": storage_path, 
                "file_name": file.filename,
                "header_row_used": header_row
            }
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Upload request error: {str(e)}"
            )

@router.post("/start")
async def start_import(
    request: StartImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Creates the import batch record in postgres and triggers the existing n8n webhook.
    """
    org_id = current_user.organization_id
    batch_id = uuid.uuid4()

    try:
        # Create initial import batch record
        await db.execute(
            text("""
                INSERT INTO import_batches (id, organization_id, status, file_name, file_path, header_row_used, successful_rows, failed_rows, total_rows, error_log)
                VALUES (:id, :org_id, 'processing', :file_name, :file_path, :header_row, 0, 0, 0, '[]')
            """),
            {
                "id": batch_id,
                "org_id": org_id,
                "file_name": request.file_name,
                "file_path": request.storage_path,
                "header_row": request.header_row
            }
        )
        await db.commit()
        
        # Persist successful mappings per organization for future imports
        try:
            mapping_res = await db.execute(
                text("SELECT id, headers FROM import_mappings WHERE organization_id = :org_id"),
                {"org_id": org_id}
            )
            existing_mappings = mapping_res.fetchall()
            
            matched_mapping_id = None
            target_headers_set = set(request.headers)
            for row in existing_mappings:
                row_id, row_headers = row
                # row_headers is a JSON array or list in DB
                try:
                    loaded_headers = json.loads(row_headers) if isinstance(row_headers, str) else row_headers
                except Exception:
                    loaded_headers = row_headers
                
                if isinstance(loaded_headers, list) and set(loaded_headers) == target_headers_set:
                    matched_mapping_id = row_id
                    break
            
            mapping_name = f"Template for {request.file_name}"
            if matched_mapping_id:
                await db.execute(
                    text("""
                        UPDATE import_mappings 
                        SET column_mapping = :column_mapping, updated_at = NOW(), mapping_name = :name
                        WHERE id = :id
                    """),
                    {
                        "id": matched_mapping_id,
                        "column_mapping": json.dumps(request.column_mapping),
                        "name": mapping_name
                    }
                )
            else:
                await db.execute(
                    text("""
                        INSERT INTO import_mappings (id, organization_id, mapping_name, headers, column_mapping)
                        VALUES (:id, :org_id, :name, :headers, :column_mapping)
                    """),
                    {
                        "id": uuid.uuid4(),
                        "org_id": org_id,
                        "name": mapping_name,
                        "headers": json.dumps(request.headers),
                        "column_mapping": json.dumps(request.column_mapping)
                    }
                )
            await db.commit()
        except Exception as mapping_err:
            logger.error("Failed to persist successful import mapping template", error=str(mapping_err))
            # Fallback rollback if mapping transaction failed, without affecting the main batch
            await db.rollback()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize import batch: {str(e)}"
        )

    # Trigger existing n8n Workflow 1 Webhook
    n8n_webhook_url = settings.n8n_webhook_url
    
    payload = {
        "import_batch_id": str(batch_id),
        "organization_id": str(org_id),
        "storage_path": request.storage_path,
        "header_row": request.header_row,
        "column_mapping": request.column_mapping
    }
    headers = {
        "X-API-Key": settings.n8n_service_api_key
    }
    
    logger.info(
        "Triggering n8n Webhook Workflow 1",
        webhook_url=n8n_webhook_url,
        request_body=payload,
        request_headers=headers
    )
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                n8n_webhook_url,
                json=payload,
                headers=headers,
                timeout=10.0
            )
            logger.info(
                "n8n Webhook response received",
                status_code=response.status_code,
                response_body=response.text
            )
            
            if response.status_code < 200 or response.status_code >= 300:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"n8n Webhook returned non-2xx status code {response.status_code}: {response.text}"
                )
        except Exception as e:
            logger.error("n8n webhook execution failed", error=str(e))
            # Update import batch status to failed and store the error log
            await db.execute(
                text("""
                    UPDATE import_batches 
                    SET status = 'failed', error_log = :error_log, completed_at = NOW() 
                    WHERE id = :id AND organization_id = :org_id
                """),
                {
                    "id": batch_id,
                    "org_id": org_id,
                    "error_log": json.dumps([{"error": f"Webhook trigger failure: {str(e)}"}])
                }
            )
            await db.commit()
            
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to trigger n8n CSV Import workflow: {str(e)}"
            )

    return {"batch_id": batch_id, "status": "processing"}

@router.get("/batches/{id}")
async def get_batch_status(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Returns the real-time statistics and status of the selected batch.
    """
    try:
        res = await db.execute(
            text("""
                SELECT status, file_name, successful_rows, failed_rows, total_rows, created_at
                FROM import_batches
                WHERE id = :id AND organization_id = :org_id
            """),
            {"id": id, "org_id": current_user.organization_id}
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import batch not found."
            )
        
        successful = row[2] or 0
        failed = row[3] or 0
        total = row[4] or 0
        return {
            "id": id,
            "status": row[0],
            "file_name": row[1],
            "success_count": successful,
            "duplicate_count": 0,
            "error_count": failed,
            "processed_rows": successful + failed,
            "total_rows": total,
            "created_at": str(row[5])
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch batch progress: {str(e)}"
        )

@router.get("/batches/{id}/errors")
async def get_batch_errors(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Exposes error details logged by n8n during validation.
    """
    try:
        res = await db.execute(
            text("SELECT error_log FROM import_batches WHERE id = :id AND organization_id = :org_id"),
            {"id": id, "org_id": current_user.organization_id}
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import batch not found."
            )
        
        errors = []
        if row[0]:
            try:
                errors = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except Exception:
                errors = []
        return {"errors": errors}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch batch error logs: {str(e)}"
        )

@router.get("/history")
async def get_import_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Lists past batches processed for the organization.
    """
    try:
        res = await db.execute(
            text("""
                SELECT id, file_name, status, successful_rows, failed_rows, total_rows, created_at
                FROM import_batches
                WHERE organization_id = :org_id
                ORDER BY created_at DESC
            """),
            {"org_id": current_user.organization_id}
        )
        history = []
        for r in res.fetchall():
            successful = r[3] or 0
            failed = r[4] or 0
            history.append({
                "id": str(r[0]),
                "file_name": r[1],
                "status": r[2],
                "success_count": successful,
                "duplicate_count": 0,
                "error_count": failed,
                "total_rows": r[5] or 0,
                "created_at": str(r[6])
            })
        return history
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch history logs: {str(e)}"
        )

@router.get("/mappings")
async def get_saved_mappings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Fetches all saved column mappings/templates for the organization.
    """
    try:
        res = await db.execute(
            text("""
                SELECT id, mapping_name, headers, column_mapping, created_at
                FROM import_mappings
                WHERE organization_id = :org_id
                ORDER BY updated_at DESC
            """),
            {"org_id": current_user.organization_id}
        )
        mappings = []
        for r in res.fetchall():
            mappings.append({
                "id": str(r[0]),
                "mapping_name": r[1],
                "headers": r[2],
                "column_mapping": r[3],
                "created_at": str(r[4])
            })
        return mappings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch saved mappings: {str(e)}"
        )
