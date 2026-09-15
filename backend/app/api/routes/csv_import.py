from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
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
import re

from app.services.ocr_service import OCRService

router = APIRouter(prefix="/api/v1/import", tags=["CSV Import"])
settings = get_settings()
logger = get_logger(__name__)

class StartImportRequest(BaseModel):
    storage_path: str
    column_mapping: Dict[str, str]
    headers: List[str]
    header_row: int = Field(0, ge=0, le=20)
    file_name: Optional[str] = "import.csv"

from app.core.normalization import (
    normalize_company_name,
    normalize_contact_name,
    clean_designation_cell,
    extract_designation_v2,
    split_primary_contact,
    parse_location,
    normalize_email,
    validate_email_syntax,
    normalize_phone,
    normalize_website,
    normalize_shipment_mode,
    normalize_trade_direction,
    normalize_country,
    derive_trade_region
)

def parse_uploaded_file(file_content: bytes, filename: str, sheet_name: Optional[str] = None) -> tuple[List[List[str]], List[str]]:
    """
    Parses any uploaded spreadsheet/text file in-memory using capability-based matching.
    Returns a tuple (rows, sheet_names).
    """
    MAX_FILE_SIZE = 50 * 1024 * 1024
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File exceeds maximum allowed size of 50MB."
        )

    # Try XLSX / XLSM (openpyxl)
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        sheet_names = wb.sheetnames
        rows = []
        if sheet_name and sheet_name in sheet_names:
            sheet = wb[sheet_name]
            for r in sheet.iter_rows(values_only=True):
                rows.append([str(val) if val is not None else '' for val in r])
        else:
            # Detect automatically
            max_non_empty_cells = -1
            for sheet in wb.worksheets:
                filled_cells = 0
                temp_rows = []
                for r in sheet.iter_rows(values_only=True):
                    if any(val is not None and str(val).strip() != '' for val in r):
                        filled_cells += sum(1 for val in r if val is not None and str(val).strip() != '')
                        temp_rows.append([str(val) if val is not None else '' for val in r])
                if filled_cells > max_non_empty_cells:
                    max_non_empty_cells = filled_cells
                    rows = temp_rows
        return rows, sheet_names
    except Exception:
        pass

    # Try XLS (xlrd)
    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=file_content)
        sheet_names = wb.sheet_names()
        rows = []
        if sheet_name and sheet_name in sheet_names:
            sheet = wb.sheet_by_name(sheet_name)
            for r_idx in range(sheet.nrows):
                r = sheet.row_values(r_idx)
                rows.append([str(val) if val is not None else '' for val in r])
        else:
            # Detect automatically
            max_non_empty_cells = -1
            for sheet_idx in range(wb.nsheets):
                sheet = wb.sheet_by_index(sheet_idx)
                filled_cells = 0
                temp_rows = []
                for r_idx in range(sheet.nrows):
                    r = sheet.row_values(r_idx)
                    if any(val is not None and str(val).strip() != '' for val in r):
                        filled_cells += sum(1 for val in r if val is not None and str(val).strip() != '')
                        temp_rows.append([str(val) if val is not None else '' for val in r])
                if filled_cells > max_non_empty_cells:
                    max_non_empty_cells = filled_cells
                    rows = temp_rows
        return rows, sheet_names
    except Exception:
        pass

    # Try parsing as text-based (CSV / TSV / TXT)
    text = None
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            text = file_content.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is not None:
        delimiter = ','
        sample = text[:2000]
        if '\t' in sample:
            if filename.lower().endswith('.tsv') or sample.count('\t') > sample.count(','):
                delimiter = '\t'
        try:
            f = io.StringIO(text)
            reader = csv.reader(f, delimiter=delimiter)
            rows = list(reader)
            return rows, []
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The uploaded file format is unsupported, corrupted, or could not be parsed."
    )

def score_row(cells: list[str]) -> int:
    clean_cells = [str(c).strip().lower() for c in cells if str(c).strip() != '']
    if len(clean_cells) <= 1:
        return 0
        
    confidence_keywords = [
        'company', 'importer', 'contact', 'email', 'mail', 'phone', 'address', 
        'industry', 'sector', 'website', 'linkedin', 'name', 's/l', 'serial', 
        'goods', 'description', 'detail', 'client', 'phone number', 'zip', 
        'state', 'city', 'country', 'visit', 'remarks'
    ]
    
    ignore_phrases = [
        'importers list', 'customer report', 'export data', 'report list', 
        'export list', 'export report', 'import list', 'import report',
        'customer visit report'
    ]
    
    score = 0
    row_text = ' '.join(clean_cells)
    for phrase in ignore_phrases:
        if phrase in row_text:
            score -= 50
            
    for cell in clean_cells:
        if len(cell) > 40:
            score -= 15
            continue
        for kw in confidence_keywords:
            if cell == kw:
                score += 25
            elif kw in cell:
                score += 10
        score += 1
    return max(0, score)

def detect_header_row(rows: list[list[str]]) -> int:
    best_index = 0
    max_score = -1
    limit = min(15, len(rows))
    for i in range(limit):
        score = score_row(rows[i])
        if score > max_score:
            max_score = score
            best_index = i
    return best_index

@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    header_row: int = Form(0),
    sheet_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    """
    Parses any supported file, normalizes it to a clean CSV in-memory,
    uploads it to Supabase Storage, and logs telemetry.
    """
    import time
    start_time = time.time()

    file_content = await file.read()
    
    # 1. Parse File
    parse_start = time.time()
    rows, sheet_names = parse_uploaded_file(file_content, file.filename, sheet_name=sheet_name)
    parse_time = time.time() - parse_start

    # Auto-detect header row if input is 0
    detected_header_row = header_row
    if header_row == 0:
        detected_header_row = detect_header_row(rows)

    if detected_header_row >= len(rows):
        detected_header_row = 0

    # Validate header row is not empty
    header = rows[detected_header_row]
    if not any(str(c).strip() for c in header):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Detected header row is empty"
        )

    # 2. Normalization
    norm_start = time.time()
    raw_normalized_rows = rows[detected_header_row:]
    normalized_rows = [
        r for r in raw_normalized_rows
        if any(str(c).strip() for c in r)
    ]

    if not normalized_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File contains no data after normalization"
        )

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(normalized_rows)
    normalized_content = out.getvalue().encode("utf-8")
    norm_time = time.time() - norm_start

    # 3. Upload to storage
    upload_start = time.time()
    org_id = current_user.organization_id
    file_id = uuid.uuid4()
    
    clean_filename = file.filename
    allowed_exts = ('.csv', '.tsv', '.txt', '.xlsx', '.xls', '.xlsm')
    for ext in allowed_exts:
        if clean_filename.lower().endswith(ext):
            clean_filename = clean_filename[:-len(ext)]
            break
    storage_filename = f"{clean_filename}.csv"
    storage_path = f"{org_id}/{file_id}_{storage_filename}"

    import urllib.parse
    safe_storage_path = urllib.parse.quote(storage_path)
    supabase_upload_url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{safe_storage_path}"
    
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
            
            if res.status_code not in (200, 201):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Supabase Storage upload failed: {res.text}"
                )
            upload_time = time.time() - upload_start
            total_time = time.time() - start_time

            logger.info(
                "Telemetry: File upload parsing completed",
                file_name=file.filename,
                rows_count=len(normalized_rows),
                parse_time_ms=int(parse_time * 1000),
                normalization_time_ms=int(norm_time * 1000),
                upload_time_ms=int(upload_time * 1000),
                total_time_ms=int(total_time * 1000)
            )
            
            client_headers = [str(h).strip() for h in header]
            all_rows_preview = rows[:15]
            return {
                "storage_path": storage_path, 
                "file_name": file.filename,
                "header_row_used": detected_header_row,
                "headers": client_headers,
                "all_rows_preview": all_rows_preview,
                "sheet_names": sheet_names
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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Validates, parses, normalizes, and extracts data from the uploaded file in-memory.
    Writes the standardized canonical CSV to a NEW storage path, updates the batch path,
    deletes the original file, and triggers the n8n webhook (Fail Fast Policy).
    """
    org_id = current_user.organization_id
    batch_id = uuid.uuid4()

    # Pre-create import batch record in processing state
    try:
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
                "header_row": 0
            }
        )
        await db.commit()
    except Exception as init_err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize import batch: {str(init_err)}"
        )

    import re
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    phone_pattern = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')

    def extract_contact_info(text: str) -> dict:
        if not text:
            return {}
        text_str = str(text).strip()
        
        valid_emails = []
        for e in email_pattern.findall(text_str):
            is_v, _ = validate_email_syntax(e)
            if is_v:
                valid_emails.append(e)
        phones = phone_pattern.findall(text_str)
        
        websites = []
        for word in text_str.split():
            word_clean = word.strip().lower()
            if 'www.' in word_clean or 'http://' in word_clean or 'https://' in word_clean:
                websites.append(word)
                
        email = valid_emails[0] if valid_emails else None

        phone = phones[0] if phones else None
        website = websites[0] if websites else None
        
        parts = [p.strip() for p in re.split(r'[\n\r|,|&|/]', text_str) if p.strip()]
        
        contact_name = None
        designation = None
        company_name = None
        
        for p in parts:
            if email and email in p:
                continue
            if phone and phone in p:
                continue
            if website and website in p:
                continue
                
            p_lower = p.lower()
            if any(title in p_lower for title in ('manager', 'director', 'ceo', 'vp', 'executive', 'sales', 'rep', 'lead', 'partner')):
                designation = p
                continue
                
            if not contact_name:
                if any(c.isalpha() for c in p) and len(p) < 40:
                    contact_name = p
            elif not company_name:
                if any(c.isalpha() for c in p) and len(p) < 80:
                    company_name = p
                    
        return {
            "email": email,
            "phone": phone,
            "website": website,
            "contact_name": contact_name,
            "designation": designation,
            "company_name": company_name
        }

    new_storage_path = request.storage_path.replace(".csv", "_normalized.csv")

    try:
        # 1. Download
        import urllib.parse
        safe_storage_path = urllib.parse.quote(request.storage_path)
        supabase_storage_url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{safe_storage_path}"
        async with httpx.AsyncClient() as client:
            res_down = await client.get(
                supabase_storage_url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"
                }
            )
            if res_down.status_code != 200:
                raise ValueError(f"Failed to retrieve uploaded file from Supabase Storage: {res_down.text}")
            csv_content = res_down.text

        # 2. Parse & Extract
        f = io.StringIO(csv_content)
        reader = csv.reader(f)
        rows = list(reader)
        if not rows:
            raise ValueError("Downloaded CSV is empty")
            
        original_headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:]

        # Get mapped column indices
        col_indices = {}
        for db_field in ('company_name', 'contact_name', 'contact_email', 'industry'):
            original_header = request.column_mapping.get(db_field)
            if original_header and original_header in original_headers:
                col_indices[db_field] = original_headers.index(original_header)
            else:
                col_indices[db_field] = None

        # Auto-match indices for additive V2 fields
        extra_indices = {
            "phone": None,
            "website": None,
            "designation": None,
            "address": None,
            "shipment_mode": None,
            "trade_direction": None,
            "country": None,
            "city": None,
            "state": None,
            "linkedin": None,
            "goods_description": None
        }
        
        # Check manual mapping first for V2 fields
        for key in extra_indices.keys():
            original_header = request.column_mapping.get(key)
            if original_header and original_header in original_headers:
                extra_indices[key] = original_headers.index(original_header)
        
        # Fallback to auto-match if not manually mapped
        for idx, h in enumerate(original_headers):
            h_lower = h.lower().strip()
            if extra_indices["phone"] is None and any(k in h_lower for k in ('phone', 'mobile', 'tel', 'contact no', 'telephone')):
                extra_indices["phone"] = idx
            elif extra_indices["website"] is None and any(k in h_lower for k in ('website', 'web', 'site', 'url')):
                extra_indices["website"] = idx
            elif extra_indices["designation"] is None and any(k in h_lower for k in ('designation', 'role', 'title', 'post')):
                extra_indices["designation"] = idx
            elif extra_indices["address"] is None and any(k in h_lower for k in ('address', 'addr')):
                extra_indices["address"] = idx
            elif extra_indices["shipment_mode"] is None and any(k in h_lower for k in ('shipment mode', 'mode of shipment', 'mode', 'transport')):
                extra_indices["shipment_mode"] = idx
            elif extra_indices["trade_direction"] is None and any(k in h_lower for k in ('trade direction', 'direction', 'import/export', 'inbound/outbound')):
                extra_indices["trade_direction"] = idx
            elif extra_indices["country"] is None and any(k in h_lower for k in ('country', 'location')):
                extra_indices["country"] = idx
            elif extra_indices["city"] is None and any(k in h_lower for k in ('city', 'town')):
                extra_indices["city"] = idx
            elif extra_indices["state"] is None and any(k in h_lower for k in ('state', 'province')):
                extra_indices["state"] = idx
            elif extra_indices["linkedin"] is None and 'linkedin' in h_lower:
                extra_indices["linkedin"] = idx
            elif extra_indices["goods_description"] is None and any(k in h_lower for k in ('goods description', 'goods', 'description', 'cargo', 'commodity', 'items')):
                extra_indices["goods_description"] = idx

        normalized_data = [[
            "company_name", 
            "contact_name", 
            "contact_email", 
            "industry",
            "phone",
            "website",
            "designation",
            "address",
            "shipment_mode",
            "trade_direction",
            "customer_type",
            "trade_region",
            "country",
            "city",
            "state",
            "linkedin",
            "goods_description",
            "raw_company_name",
            "raw_contact_name"
        ]]
        
        valid_count = 0
        invalid_count = 0
        data_row_index = 0  # tracks the 1-based data row position (header = row 1)
        batch_error_log = []
        valid_customer_ids = []

        for row in data_rows:
            if not row or not any(str(cell).strip() for cell in row):
                continue
            data_row_index += 1

                
            raw_company_cell = row[col_indices["company_name"]] if col_indices["company_name"] is not None and col_indices["company_name"] < len(row) else ""
            raw_name_cell = row[col_indices["contact_name"]] if col_indices["contact_name"] is not None and col_indices["contact_name"] < len(row) else ""
            raw_email_cell = row[col_indices["contact_email"]] if col_indices["contact_email"] is not None and col_indices["contact_email"] < len(row) else ""
            raw_industry_cell = row[col_indices["industry"]] if col_indices["industry"] is not None and col_indices["industry"] < len(row) else ""

            extracted_company = extract_contact_info(raw_company_cell)
            extracted_name = extract_contact_info(raw_name_cell)
            extracted_email = extract_contact_info(raw_email_cell)

            # Email mapping
            row_contact_email = raw_email_cell.strip()
            if not email_pattern.match(row_contact_email) and extracted_email.get("email"):
                row_contact_email = extracted_email["email"]
            if not row_contact_email and extracted_company.get("email"):
                row_contact_email = extracted_company["email"]
            if not row_contact_email and extracted_name.get("email"):
                row_contact_email = extracted_name["email"]
            row_contact_email = normalize_email(row_contact_email) or ""

            # Company name mapping
            row_company_name = raw_company_cell.strip()
            if not row_company_name and extracted_email.get("company_name"):
                row_company_name = extracted_email["company_name"]
            if not row_company_name and extracted_name.get("company_name"):
                row_company_name = extracted_name["company_name"]
            raw_company_name_preserved = row_company_name
            row_company_name = normalize_company_name(row_company_name)

            # Contact name mapping
            row_contact_name = raw_name_cell.strip()
            if not row_contact_name and extracted_email.get("contact_name"):
                row_contact_name = extracted_email["contact_name"]
            if not row_contact_name and extracted_company.get("contact_name"):
                row_contact_name = extracted_company["contact_name"]
            raw_contact_name_preserved = row_contact_name
            row_contact_name, derived_designation = split_primary_contact(row_contact_name)

            row_industry = raw_industry_cell.strip()

            def get_cell(key):
                idx = extra_indices[key]
                return row[idx].strip() if idx is not None and idx < len(row) else ""

            phone_val = normalize_phone(get_cell("phone")) or extracted_company.get("phone") or extracted_name.get("phone") or extracted_email.get("phone") or ""
            website_val = normalize_website(get_cell("website")) or extracted_company.get("website") or extracted_name.get("website") or extracted_email.get("website") or ""
            
            designation_val = get_cell("designation")
            if designation_val:
                designation_val = clean_designation_cell(designation_val)
            if not designation_val:
                designation_val = derived_designation or extract_designation_v2(raw_company_cell) or extracted_name.get("designation") or extracted_company.get("designation") or ""
            designation_val = designation_val.strip()
            
            # Safe country / address detection
            raw_country_cell = get_cell("country")
            address_val, city_val, state_val, country_val = parse_location(raw_country_cell)
            if not address_val:
                address_val = get_cell("address")
            if not city_val:
                city_val = get_cell("city")
            if not state_val:
                state_val = get_cell("state")
            if not country_val:
                country_val = raw_country_cell.strip()
                
            shipment_mode_val = normalize_shipment_mode(get_cell("shipment_mode")) or ""
            trade_direction_val = normalize_trade_direction(get_cell("trade_direction")) or ""
            linkedin_val = normalize_website(get_cell("linkedin")) or ""
            goods_description_val = get_cell("goods_description")
            
            # Set fallback mappings
            trade_region_val = derive_trade_region(country_val) or ""
            customer_type_val = "overseas" if country_val and country_val.lower() not in ("india", "domestic") else "domestic" if country_val else ""

            # Run strict email syntax validation
            raw_contact_email_preserved = raw_email_cell.strip()
            is_email_valid, email_val_err = validate_email_syntax(row_contact_email)
            validation_status = "valid" if is_email_valid else "invalid"

            if is_email_valid:
                normalized_data.append([
                    row_company_name,
                    row_contact_name,
                    row_contact_email,
                    row_industry,
                    phone_val,
                    website_val,
                    designation_val,
                    address_val or "",
                    shipment_mode_val,
                    trade_direction_val,
                    customer_type_val,
                    trade_region_val,
                    country_val or "",
                    city_val or "",
                    state_val or "",
                    linkedin_val,
                    goods_description_val,
                    raw_company_name_preserved,
                    raw_contact_name_preserved
                ])
                valid_count += 1
            # Insert Customer into database for tracking/correction (retained regardless of validation)
            cust_id = None
            # Always insert even if company_name is empty (use placeholder) so invalid row is visible/editable in history
            effective_company_name = row_company_name or raw_company_cell.strip() or "(Unknown Company)"
            if True:  # always attempt to persist for history tracking
                # Deduplication check for contact_email (unrestricted by deleted_at or validation_status to prevent UniqueViolationError)
                existing_cust = None
                if row_contact_email:
                    dup_check = await db.execute(
                        text("SELECT id FROM customers WHERE organization_id = :org_id AND contact_email = :email"),
                        {"org_id": org_id, "email": row_contact_email}
                    )
                    existing_cust = dup_check.fetchone()

                if existing_cust:
                    cust_id = existing_cust[0]
                    if is_email_valid:
                        valid_customer_ids.append(str(cust_id))
                else:
                    new_cust_id = uuid.uuid4()
                    from sqlalchemy.exc import IntegrityError
                    try:
                        await db.execute(
                            text("""
                                INSERT INTO customers (
                                    id, organization_id, import_batch_id, company_name, contact_name, contact_email,
                                    industry, country, phone, website, designation, address, city, state,
                                    shipment_mode, trade_direction, customer_type, trade_region, goods_description,
                                    raw_company_name, raw_contact_name, raw_contact_email,
                                    email_validation_status, email_validation_error, source, created_at, updated_at
                                ) VALUES (
                                    :id, :org_id, :batch_id, :company_name, :contact_name, :contact_email,
                                    :industry, :country, :phone, :website, :designation, :address, :city, :state,
                                    :shipment_mode, :trade_direction, :customer_type, :trade_region, :goods_description,
                                    :raw_company_name, :raw_contact_name, :raw_contact_email,
                                    :validation_status, :validation_error, 'csv_import', NOW(), NOW()
                                )
                            """),
                            {
                                "id": new_cust_id,
                                "org_id": org_id,
                                "batch_id": batch_id,
                                "company_name": effective_company_name,
                                "contact_name": row_contact_name or None,
                                "contact_email": row_contact_email if row_contact_email else None,
                                "industry": row_industry or None,
                                "country": country_val or None,
                                "phone": phone_val or None,
                                "website": website_val or None,
                                "designation": designation_val or None,
                                "address": address_val or None,
                                "city": city_val or None,
                                "state": state_val or None,
                                "shipment_mode": shipment_mode_val or None,
                                "trade_direction": trade_direction_val or None,
                                "customer_type": customer_type_val or None,
                                "trade_region": trade_region_val or None,
                                "goods_description": goods_description_val or None,
                                "raw_company_name": raw_company_name_preserved or None,
                                "raw_contact_name": raw_contact_name_preserved or None,
                                "raw_contact_email": raw_contact_email_preserved or None,
                                "validation_status": validation_status,
                                "validation_error": email_val_err if not is_email_valid else None
                            }
                        )
                        cust_id = new_cust_id
                        if is_email_valid:
                            valid_customer_ids.append(str(cust_id))
                    except IntegrityError:
                        # Existing record collided on constraint; lookup ID (only if email exists)
                        if row_contact_email:
                            existing_fallback = await db.execute(
                                text("SELECT id FROM customers WHERE organization_id = :org_id AND contact_email = :email"),
                                {"org_id": org_id, "email": row_contact_email}
                            )
                            fallback_row = existing_fallback.fetchone()
                            if fallback_row:
                                cust_id = fallback_row[0]

            if not is_email_valid:
                invalid_count += 1
                # row_number: header is row 1, data rows start at row 2
                row_num = data_row_index + 1
                error_entry = {
                    "row_number": row_num,
                    "customer_id": str(cust_id) if cust_id else None,
                    "company_name": row_company_name or raw_company_cell,
                    "contact_name": row_contact_name or raw_name_cell,
                    "original_email": raw_contact_email_preserved,
                    "error_type": "invalid_email_syntax",
                    "error_message": email_val_err or "Invalid email syntax",
                    "errors": [
                        {
                            "field": "contact_email",
                            "reason": email_val_err or "Invalid email syntax"
                        }
                    ]
                }
                batch_error_log.append(error_entry)



        # 3. Canonical Header Validation
        expected_headers = ["company_name", "contact_name", "contact_email", "industry"]
        actual_headers = normalized_data[0][:4]
        if actual_headers != expected_headers:
            raise ValueError(f"Canonical header mismatch. Expected {expected_headers}, got {actual_headers}")

        # 4. Generate standard CSV & Upload to NEW storage path
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerows(normalized_data)
        normalized_content = out.getvalue().encode("utf-8")

        safe_new_storage_path = urllib.parse.quote(new_storage_path)
        supabase_upload_url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{safe_new_storage_path}"

        async with httpx.AsyncClient() as client:
            res_up = await client.post(
                supabase_upload_url,
                content=normalized_content,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "text/csv"
                }
            )
            if res_up.status_code not in (200, 201):
                raise ValueError(f"Supabase Storage upload of normalized CSV failed: {res_up.text}")

        # 5. Update database batch with NEW path, row counts, and error log
        batch_status = "completed" if invalid_count == 0 else ("partial" if valid_count > 0 else "failed")
        await db.execute(
            text("""
                UPDATE import_batches 
                SET file_path = :file_path, 
                    successful_rows = :success_count,
                    failed_rows = :failed_count,
                    total_rows = :total_count,
                    status = :status,
                    error_log = :error_log,
                    completed_at = NOW()
                WHERE id = :id
            """),
            {
                "file_path": new_storage_path, 
                "success_count": valid_count,
                "failed_count": invalid_count,
                "total_count": valid_count + invalid_count,
                "status": batch_status,
                "error_log": json.dumps(batch_error_log),
                "id": batch_id
            }
        )
        await db.commit()


        # 6. Delete old file from storage
        supabase_delete_url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{safe_storage_path}"
        async with httpx.AsyncClient() as client:
            await client.delete(
                supabase_delete_url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"
                }
            )

        # 7. Persist Successful import mapping
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
                    text("UPDATE import_mappings SET column_mapping = :column_mapping, updated_at = NOW(), mapping_name = :name WHERE id = :id"),
                    {"id": matched_mapping_id, "column_mapping": json.dumps(request.column_mapping), "name": mapping_name}
                )
            else:
                await db.execute(
                    text("INSERT INTO import_mappings (id, organization_id, mapping_name, headers, column_mapping) VALUES (:id, :org_id, :name, :headers, :column_mapping)"),
                    {"id": uuid.uuid4(), "org_id": org_id, "name": mapping_name, "headers": json.dumps(request.headers), "column_mapping": json.dumps(request.column_mapping)}
                )
            await db.commit()
        except Exception as mapping_err:
            logger.error("Failed to persist successful import mapping template", error=str(mapping_err))
            await db.rollback()

    except Exception as norm_err:
        await db.rollback()
        # Mark batch as failed
        await db.execute(
            text("""
                UPDATE import_batches 
                SET status = 'failed', error_log = :error_log, completed_at = NOW() 
                WHERE id = :id
            """),
            {
                "id": batch_id,
                "error_log": json.dumps([{"error": f"Normalization Failure: {str(norm_err)}"}])
            }
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import normalization failed: {str(norm_err)}"
        )

    # 8. Define background task for triggering n8n Webhook
    payload = {
        "import_batch_id": str(batch_id),
        "organization_id": str(org_id),
        "storage_path": new_storage_path,
        "header_row": 0,
        "customer_count": valid_count,
        "customer_ids": valid_customer_ids,
        "column_mapping": {
            "company_name": "company_name",
            "contact_name": "contact_name",
            "contact_email": "contact_email",
            "industry": "industry",
            "phone": "phone",
            "website": "website",
            "designation": "designation",
            "address": "address",
            "shipment_mode": "shipment_mode",
            "trade_direction": "trade_direction",
            "customer_type": "customer_type",
            "trade_region": "trade_region",
            "country": "country",
            "city": "city",
            "state": "state",
            "linkedin": "linkedin",
            "goods_description": "goods_description",
            "raw_company_name": "raw_company_name",
            "raw_contact_name": "raw_contact_name"
        }
    }


    async def trigger_n8n_webhook_background_task(batch_id: uuid.UUID, payload: dict):
        from app.db.session import AsyncSessionLocal
        n8n_webhook_url = settings.n8n_webhook_url
        headers = {
            "X-API-Key": settings.n8n_service_api_key
        }
        
        logger.info(
            "Triggering n8n Webhook Workflow 1 in background",
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
                    timeout=60.0
                )
                logger.info(
                    "n8n Webhook response received in background",
                    status_code=response.status_code,
                    response_body=response.text
                )
                
                if response.status_code < 200 or response.status_code >= 300:
                    raise ValueError(f"n8n Webhook returned status code {response.status_code}: {response.text}")
            except Exception as webhook_err:
                logger.error("n8n webhook execution failed in background", error=str(webhook_err))
                # IMPORTANT: Do NOT overwrite error_log here — it contains the per-row validation errors.
                # Store webhook failure in a separate column or simply log it without touching error_log.
                async with AsyncSessionLocal() as background_db:
                    # Fetch existing error_log to preserve it
                    existing_res = await background_db.execute(
                        text("SELECT error_log FROM import_batches WHERE id = :id"),
                        {"id": batch_id}
                    )
                    existing_row = existing_res.fetchone()
                    existing_errors = []
                    if existing_row and existing_row[0]:
                        try:
                            existing_errors = json.loads(existing_row[0]) if isinstance(existing_row[0], str) else existing_row[0]
                        except Exception:
                            existing_errors = []
                    # Append webhook error without replacing validation errors
                    webhook_error_entry = {"webhook_error": f"Webhook trigger failure: {str(webhook_err)}"}
                    merged_errors = existing_errors + [webhook_error_entry]
                    await background_db.execute(
                        text("""
                            UPDATE import_batches 
                            SET status = 'failed', error_log = :error_log 
                            WHERE id = :id
                        """),
                        {
                            "id": batch_id,
                            "error_log": json.dumps(merged_errors)
                        }
                    )
                    await background_db.commit()

    background_tasks.add_task(trigger_n8n_webhook_background_task, batch_id, payload)
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
                SELECT status, file_name, successful_rows, failed_rows, total_rows, created_at, completed_at
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
            "created_at": str(row[5]),
            "completed_at": str(row[6]) if row[6] else None
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
                SELECT id, file_name, status, successful_rows, failed_rows, total_rows, created_at, completed_at
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
                "created_at": str(r[6]),
                "completed_at": str(r[7]) if r[7] else None
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


class OCRConfirmLead(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    linkedin: Optional[str] = None
    notes: Optional[str] = None
    bypass_duplicate: Optional[bool] = False

class OCRConfirmRequest(BaseModel):
    leads: List[OCRConfirmLead]


@router.post("/ocr/extract")
async def extract_ocr_leads(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    OCR + AI Lead extraction endpoint.
    Processes uploaded images using Google Gemini Vision, parses visible contact details,
    performs duplicate checks, and returns candidates for review.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 images allowed per request.")

    allowed_exts = {".png", ".jpg", ".jpeg", ".webp"}
    allowed_mimes = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

    image_payloads = []
    for upload_file in files:
        # 1. Filename validation
        filename_lower = upload_file.filename.lower()
        if not any(filename_lower.endswith(ext) for ext in allowed_exts):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file extension in '{upload_file.filename}'. Allowed formats: PNG, JPG, JPEG, WEBP."
            )

        # 2. Size validation (max 10MB)
        file_bytes = await upload_file.read()
        if len(file_bytes) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File '{upload_file.filename}' exceeds maximum allowed size of 10MB."
            )

        # 3. MIME validation
        mime_type = upload_file.content_type
        if mime_type not in allowed_mimes:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported content type '{mime_type}' in '{upload_file.filename}'."
            )

        image_payloads.append((file_bytes, mime_type))

    # Trigger OCR extraction outside of the database execution context.
    # The DB session has been initialized by Depends(get_db_session) but no query has been run yet,
    # ensuring the connection pool is not locked during slow external network I/O.
    service = OCRService(db)
    try:
        candidates = await service.extract_leads_from_images(image_payloads, org_id=str(current_user.organization_id))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google Gemini Vision API error: {str(e)}")

    # Re-acquire database session implicitly by running query execution for duplicate detection.
    for lead in candidates:
        email = lead.get("contact_email")
        company = lead.get("company_name")
        name = lead.get("contact_name")
        
        is_duplicate = False
        duplicate_reason = None
        
        if email:
            dup_res = await db.execute(
                text("SELECT id, company_name, contact_name FROM customers WHERE organization_id = :org_id AND contact_email = :email AND deleted_at IS NULL"),
                {"org_id": current_user.organization_id, "email": email}
            )
            row = dup_res.fetchone()
            if row:
                is_duplicate = True
                duplicate_reason = f"Email already registered to {row[1]} ({row[2]})"
        else:
            if name:
                dup_res = await db.execute(
                    text("SELECT id FROM customers WHERE organization_id = :org_id AND company_name = :company AND contact_name = :name AND deleted_at IS NULL"),
                    {"org_id": current_user.organization_id, "company": company, "name": name}
                )
                if dup_res.fetchone():
                    is_duplicate = True
                    duplicate_reason = "Contact and Company combination already exists"
            else:
                dup_res = await db.execute(
                    text("SELECT id FROM customers WHERE organization_id = :org_id AND company_name = :company AND contact_name IS NULL AND deleted_at IS NULL"),
                    {"org_id": current_user.organization_id, "company": company}
                )
                if dup_res.fetchone():
                    is_duplicate = True
                    duplicate_reason = "Company already exists with no primary contact"

        lead["is_duplicate"] = is_duplicate
        lead["duplicate_reason"] = duplicate_reason

    return {"candidates": candidates}


@router.post("/ocr/confirm")
async def confirm_ocr_leads(
    payload: OCRConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Saves confirmed lead candidates to the customers database scoped to the organization.
    """
    org_id = current_user.organization_id
    success_count = 0
    skipped_count = 0
    
    from sqlalchemy.exc import IntegrityError
    
    for lead in payload.leads:
        company_name = normalize_company_name(lead.company_name)
        if not company_name:
            continue
            
        contact_email = normalize_email(lead.contact_email) if lead.contact_email else None
        contact_name = normalize_contact_name(lead.contact_name) if lead.contact_name else None
        phone = normalize_phone(lead.phone) if lead.phone else None
        website = normalize_website(lead.website) if lead.website else None
        linkedin = normalize_website(lead.linkedin) if lead.linkedin else None
        country = normalize_country(lead.country) if lead.country else None
        trade_region = derive_trade_region(country) if country else None
        customer_type = "overseas" if country and country.lower() not in ("india", "domestic") else "domestic" if country else None
        
        # Email validation check
        is_email_valid, email_val_err = validate_email_syntax(contact_email)
        validation_status = "valid" if is_email_valid else "invalid"

        # Double check duplicate check logic scoped to organization
        if not lead.bypass_duplicate:
            if contact_email:
                dup_res = await db.execute(
                    text("SELECT id FROM customers WHERE organization_id = :org_id AND contact_email = :email AND deleted_at IS NULL"),
                    {"org_id": org_id, "email": contact_email}
                )
                if dup_res.fetchone():
                    skipped_count += 1
                    continue
            else:
                if contact_name:
                    dup_res = await db.execute(
                        text("SELECT id FROM customers WHERE organization_id = :org_id AND company_name = :company AND contact_name = :name AND deleted_at IS NULL"),
                        {"org_id": org_id, "company": company_name, "name": contact_name}
                    )
                    if dup_res.fetchone():
                        skipped_count += 1
                        continue
                else:
                    dup_res = await db.execute(
                        text("SELECT id FROM customers WHERE organization_id = :org_id AND company_name = :company AND contact_name IS NULL AND deleted_at IS NULL"),
                        {"org_id": org_id, "company": company_name}
                    )
                    if dup_res.fetchone():
                        skipped_count += 1
                        continue

        cust_id = uuid.uuid4()
        try:
            await db.execute(
                text("""
                    INSERT INTO customers (
                        id, organization_id, company_name, contact_name, contact_email,
                        phone, website, designation, address, city, state, country,
                        linkedin, notes, source, shipment_mode, trade_direction,
                        customer_type, trade_region, email_validation_status, email_validation_error,
                        raw_contact_email, created_at, updated_at
                    ) VALUES (
                        :id, :org_id, :company_name, :contact_name, :contact_email,
                        :phone, :website, :designation, :address, :city, :state, :country,
                        :linkedin, :notes, 'csv_import', '', '',
                        :customer_type, :trade_region, :validation_status, :validation_error,
                        :raw_contact_email, NOW(), NOW()
                    )
                """),
                {
                    "id": cust_id,
                    "org_id": org_id,
                    "company_name": company_name,
                    "contact_name": contact_name,
                    "contact_email": contact_email,
                    "phone": phone,
                    "website": website,
                    "designation": lead.designation,
                    "address": lead.address,
                    "city": lead.city,
                    "state": lead.state,
                    "country": country,
                    "linkedin": linkedin,
                    "notes": lead.notes,
                    "customer_type": customer_type,
                    "trade_region": trade_region,
                    "validation_status": validation_status,
                    "validation_error": email_val_err if not is_email_valid else None,
                    "raw_contact_email": lead.contact_email or None
                }
            )
            success_count += 1
        except IntegrityError:
            skipped_count += 1
            continue

    await db.commit()
    return {"success": True, "imported_count": success_count, "skipped_count": skipped_count}

class CorrectRowRequest(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    designation: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    shipment_mode: Optional[str] = None
    trade_direction: Optional[str] = None
    customer_type: Optional[str] = None
    trade_region: Optional[str] = None
    linkedin: Optional[str] = None
    goods_description: Optional[str] = None

def check_recovery_window_expiration(completed_at, created_at):
    from datetime import datetime, timezone
    terminal_time = completed_at or created_at
    if terminal_time:
        if terminal_time.tzinfo is None:
            terminal_time = terminal_time.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - terminal_time
        if age.total_seconds() > 10 * 3600:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="CSV error recovery window expired. Error recovery is available for 10 hours after import completion."
            )

@router.get("/batches/{id}/errors/download")
async def download_error_csv(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Downloads the normalized CSV from storage and streams a filtered copy containing only failed rows.
    """
    res = await db.execute(
        text("SELECT file_path, organization_id, error_log, completed_at, created_at FROM import_batches WHERE id = :id"),
        {"id": id}
    )
    batch = res.fetchone()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found.")
        
    file_path, org_id, error_log_raw, completed_at, created_at = batch
    if org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        
    check_recovery_window_expiration(completed_at, created_at)
        
    try:
        errors = json.loads(error_log_raw) if isinstance(error_log_raw, str) else (error_log_raw or [])
    except Exception:
        errors = []
        
    failed_row_map = {}
    for err in errors:
        r_num = err.get("row_number")
        errs_list = err.get("errors", [])
        reasons = [e.get("reason", "") for e in errs_list if isinstance(e, dict) and e.get("reason")]
        if not reasons and err.get("error_message"):
            reasons = [err.get("error_message")]
        failed_row_map[r_num] = {
            "errors_text": "; ".join(reasons) if reasons else "Validation error",
            "errors_type": err.get("error_type") or "validation"
        }

        
    import urllib.parse
    safe_path = urllib.parse.quote(file_path)
    url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{safe_path}"
    
    async with httpx.AsyncClient() as client:
        res_down = await client.get(
            url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}"
            }
        )
        if res_down.status_code != 200:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to retrieve import file.")
        csv_content = res_down.text
        
    f = io.StringIO(csv_content)
    reader = csv.reader(f)
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import file is empty.")
        
    headers = rows[0]
    new_headers = headers + ["Import Error", "Error Type", "Original Row Number"]
    
    def csv_generator():
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(new_headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        for idx, row in enumerate(rows[1:]):
            row_number = idx + 2
            if row_number in failed_row_map:
                err_info = failed_row_map[row_number]
                row_extended = row + [err_info["errors_text"], err_info["errors_type"], str(row_number)]
                writer.writerow(row_extended)
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
                
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        csv_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=import_errors_{id}.csv"}
    )

@router.get("/batches/{id}/errors/{row_number}")
async def get_batch_error_row(
    id: uuid.UUID,
    row_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves the specific failed row content from the batch's normalized CSV file.
    """
    res = await db.execute(
        text("SELECT file_path, organization_id, error_log, completed_at, created_at FROM import_batches WHERE id = :id"),
        {"id": id}
    )
    batch = res.fetchone()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found.")
        
    file_path, org_id, error_log_raw, completed_at, created_at = batch
    if org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        
    check_recovery_window_expiration(completed_at, created_at)
        
    try:
        errors = json.loads(error_log_raw) if isinstance(error_log_raw, str) else (error_log_raw or [])
    except Exception:
        errors = []
        
    row_error = None
    for err in errors:
        if err.get("row_number") == row_number:
            row_error = err
            break
            
    if not row_error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found in batch error log or already resolved.")
        
    row_dict = {}
    try:
        import urllib.parse
        safe_path = urllib.parse.quote(file_path)
        url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{safe_path}"
        
        async with httpx.AsyncClient() as client:
            res_down = await client.get(
                url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"
                }
            )
            if res_down.status_code == 200:
                csv_content = res_down.text
                f = io.StringIO(csv_content)
                reader = csv.reader(f)
                rows = list(reader)
                if len(rows) > 0 and 1 <= row_number - 1 < len(rows):
                    headers = rows[0]
                    row_data = rows[row_number - 1]
                    for idx, h in enumerate(headers):
                        row_dict[h] = row_data[idx] if idx < len(row_data) else ""
    except Exception as storage_err:
        logger.warning("Failed to fetch storage file row for error correction preview", error=str(storage_err))

    # Fallback to customer DB record if storage CSV row reading did not populate row_dict
    if not row_dict.get("company_name") and row_error.get("customer_id"):
        cust_res = await db.execute(
            text("""
                SELECT company_name, contact_name, contact_email, industry, phone, website, designation, address, city, state, country, shipment_mode, trade_direction, customer_type, trade_region, linkedin, goods_description
                FROM customers WHERE id = :cust_id AND organization_id = :org_id
            """),
            {"cust_id": uuid.UUID(row_error["customer_id"]), "org_id": org_id}
        )
        c_row = cust_res.fetchone()
        if c_row:
            row_dict = {
                "company_name": c_row[0] or "",
                "contact_name": c_row[1] or "",
                "contact_email": c_row[2] or row_error.get("original_email") or "",
                "industry": c_row[3] or "",
                "phone": c_row[4] or "",
                "website": c_row[5] or "",
                "designation": c_row[6] or "",
                "address": c_row[7] or "",
                "city": c_row[8] or "",
                "state": c_row[9] or "",
                "country": c_row[10] or "",
                "shipment_mode": c_row[11] or "",
                "trade_direction": c_row[12] or "",
                "customer_type": c_row[13] or "",
                "trade_region": c_row[14] or "",
                "linkedin": c_row[15] or "",
                "goods_description": c_row[16] or ""
            }

    if not row_dict.get("company_name"):
        row_dict = {
            "company_name": row_error.get("company_name") or "",
            "contact_name": row_error.get("contact_name") or "",
            "contact_email": row_error.get("original_email") or "",
            "industry": ""
        }

    return {
        "row_number": row_number,
        "row_data": row_dict,
        "errors": row_error.get("errors", [])
    }


@router.post("/batches/{id}/errors/{row_number}/correct")
async def correct_batch_error_row(
    id: uuid.UUID,
    row_number: int,
    payload: CorrectRowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Merges, validates, unique checks, inserts the customer, and atomically updates batch stats.
    """
    # 1. Fetch batch metadata
    res = await db.execute(
        text("SELECT file_path, organization_id, error_log, completed_at, created_at FROM import_batches WHERE id = :id"),
        {"id": id}
    )
    batch = res.fetchone()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found.")
        
    file_path, org_id, error_log_raw, completed_at, created_at = batch
    if org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        
    check_recovery_window_expiration(completed_at, created_at)
        
    try:
        errors = json.loads(error_log_raw) if isinstance(error_log_raw, str) else (error_log_raw or [])
    except Exception:
        errors = []
        
    row_error = None
    for err in errors:
        if err.get("row_number") == row_number:
            row_error = err
            break
            
    if not row_error:
        # Idempotency safety: row might have already been resolved
        return {"success": True, "already_corrected": True}
        
    # 2. Retrieve original row from Supabase Storage or error object
    original_dict = {
        "company_name": row_error.get("company_name", ""),
        "contact_name": row_error.get("contact_name", ""),
        "contact_email": row_error.get("original_email", "")
    }
    try:
        import urllib.parse
        safe_path = urllib.parse.quote(file_path)
        url = f"{settings.supabase_url}/storage/v1/object/csv-imports/{safe_path}"
        
        async with httpx.AsyncClient() as client:
            res_down = await client.get(
                url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"
                }
            )
            if res_down.status_code == 200:
                csv_content = res_down.text
                f = io.StringIO(csv_content)
                reader = csv.reader(f)
                rows = list(reader)
                if len(rows) > 0 and 1 <= row_number - 1 < len(rows):
                    headers = rows[0]
                    row_data = rows[row_number - 1]
                    for idx, h in enumerate(headers):
                        original_dict[h] = row_data[idx] if idx < len(row_data) else ""
    except Exception as storage_err:
        logger.warning("Failed to fetch storage file row for error correction merge", error=str(storage_err))

        
    # 3. Merge corrections & re-normalize
    merged = {
        "company_name": payload.company_name,
        "contact_name": payload.contact_name if payload.contact_name is not None else original_dict.get("contact_name", ""),
        "contact_email": payload.contact_email if payload.contact_email is not None else original_dict.get("contact_email", ""),
        "industry": payload.industry if payload.industry is not None else original_dict.get("industry", ""),
        "phone": payload.phone if payload.phone is not None else original_dict.get("phone", ""),
        "website": payload.website if payload.website is not None else original_dict.get("website", ""),
        "designation": payload.designation if payload.designation is not None else original_dict.get("designation", ""),
        "address": payload.address if payload.address is not None else original_dict.get("address", ""),
        "city": payload.city if payload.city is not None else original_dict.get("city", ""),
        "state": payload.state if payload.state is not None else original_dict.get("state", ""),
        "country": payload.country if payload.country is not None else original_dict.get("country", ""),
        "shipment_mode": payload.shipment_mode if payload.shipment_mode is not None else original_dict.get("shipment_mode", ""),
        "trade_direction": payload.trade_direction if payload.trade_direction is not None else original_dict.get("trade_direction", ""),
        "customer_type": payload.customer_type if payload.customer_type is not None else original_dict.get("customer_type", ""),
        "trade_region": payload.trade_region if payload.trade_region is not None else original_dict.get("trade_region", ""),
        "linkedin": payload.linkedin if payload.linkedin is not None else original_dict.get("linkedin", ""),
        "goods_description": payload.goods_description if payload.goods_description is not None else original_dict.get("goods_description", ""),
    }
    
    company_name = normalize_company_name(merged["company_name"])
    contact_name, derived_designation = split_primary_contact(merged["contact_name"] or "")
    if contact_name:
        contact_name = normalize_contact_name(contact_name)
    contact_email = normalize_email(merged["contact_email"])
    
    designation = merged["designation"]
    if designation:
        designation = clean_designation_cell(designation)
    if not designation:
        designation = derived_designation or ""
        
    phone = normalize_phone(merged["phone"])
    website = normalize_website(merged["website"])
    linkedin = normalize_website(merged["linkedin"])
    country = normalize_country(merged["country"])
    city = merged["city"].strip()
    state = merged["state"].strip()
    address = merged["address"].strip()
    shipment_mode = normalize_shipment_mode(merged["shipment_mode"])
    trade_direction = normalize_trade_direction(merged["trade_direction"])
    
    customer_type = merged["customer_type"]
    if not customer_type:
        customer_type = "overseas" if country and country.lower() not in ("india", "domestic") else "domestic" if country else ""
    trade_region = merged["trade_region"]
    if not trade_region:
        trade_region = derive_trade_region(country) or ""
        
    # 4. Run validation checks
    val_errors = []
    if not company_name:
        val_errors.append("Company name missing")
    if not contact_email:
        val_errors.append("Email missing")
    else:
        is_valid_email, email_err = validate_email_syntax(contact_email)
        if not is_valid_email:
            val_errors.append(f"Invalid email format: {email_err or contact_email}")
            
    if val_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": val_errors}
        )
        
    # 5. Check database organization duplicates
    dup_res = await db.execute(
        text("SELECT id FROM customers WHERE organization_id = :org_id AND contact_email = :email AND deleted_at IS NULL AND email_validation_status = 'valid'"),
        {"org_id": org_id, "email": contact_email}
    )
    if dup_res.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": ["Email already exists for this organization."]}
        )
        
    # 6. Check if an invalid retained customer record already exists for this import batch
    existing_retained_res = await db.execute(
        text("""
            SELECT id FROM customers 
            WHERE organization_id = :org_id 
              AND import_batch_id = :batch_id 
              AND (raw_contact_email = :raw_email OR contact_email = :raw_email OR company_name = :company_name)
              AND email_validation_status = 'invalid'
            LIMIT 1
        """),
        {
            "org_id": org_id, 
            "batch_id": id, 
            "raw_email": merged.get("contact_email") or "",
            "company_name": company_name
        }
    )
    retained_row = existing_retained_res.fetchone()

    if retained_row:
        cust_id = retained_row[0]
        await db.execute(
            text("""
                UPDATE customers SET
                    company_name = :company_name,
                    contact_name = :contact_name,
                    contact_email = :contact_email,
                    phone = :phone,
                    website = :website,
                    designation = :designation,
                    address = :address,
                    city = :city,
                    state = :state,
                    country = :country,
                    linkedin = :linkedin,
                    shipment_mode = :shipment_mode,
                    trade_direction = :trade_direction,
                    customer_type = :customer_type,
                    trade_region = :trade_region,
                    email_validation_status = 'valid',
                    email_validation_error = NULL,
                    updated_at = NOW()
                WHERE id = :cust_id
            """),
            {
                "cust_id": cust_id,
                "company_name": company_name,
                "contact_name": contact_name or None,
                "contact_email": contact_email,
                "phone": phone or None,
                "website": website or None,
                "designation": designation or None,
                "address": address or None,
                "city": city or None,
                "state": state or None,
                "country": country or None,
                "linkedin": linkedin or None,
                "shipment_mode": shipment_mode or "",
                "trade_direction": trade_direction or "",
                "customer_type": customer_type or "",
                "trade_region": trade_region or ""
            }
        )
    else:
        cust_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO customers (
                    id, organization_id, import_batch_id, company_name, contact_name, contact_email,
                    phone, website, designation, address, city, state, country,
                    linkedin, notes, source, shipment_mode, trade_direction,
                    customer_type, trade_region, email_validation_status, email_validation_error,
                    raw_contact_email, created_at, updated_at
                ) VALUES (
                    :id, :org_id, :batch_id, :company_name, :contact_name, :contact_email,
                    :phone, :website, :designation, :address, :city, :state, :country,
                    :linkedin, :notes, 'csv_import', :shipment_mode, :trade_direction,
                    :customer_type, :trade_region, 'valid', NULL,
                    :raw_contact_email, NOW(), NOW()
                )
            """),
            {
                "id": cust_id,
                "org_id": org_id,
                "batch_id": id,
                "company_name": company_name,
                "contact_name": contact_name or None,
                "contact_email": contact_email,
                "phone": phone or None,
                "website": website or None,
                "designation": designation or None,
                "address": address or None,
                "city": city or None,
                "state": state or None,
                "country": country or None,
                "linkedin": linkedin or None,
                "notes": merged.get("goods_description") or None,
                "shipment_mode": shipment_mode or "",
                "trade_direction": trade_direction or "",
                "customer_type": customer_type or "",
                "trade_region": trade_region or "",
                "raw_contact_email": merged.get("contact_email") or contact_email
            }
        )

    
    # 7. Atomic transaction lock & Update Batch Stats
    batch_lock_res = await db.execute(
        text("SELECT error_log, failed_rows, successful_rows, status FROM import_batches WHERE id = :id FOR UPDATE"),
        {"id": id}
    )
    batch_lock = batch_lock_res.fetchone()
    if not batch_lock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed to acquire lock on import batch.")
        
    current_error_log_raw, current_failed, current_success, current_status = batch_lock
    try:
        current_errors = json.loads(current_error_log_raw) if isinstance(current_error_log_raw, str) else (current_error_log_raw or [])
    except Exception:
        current_errors = []
        
    row_found = False
    new_errors = []
    for err in current_errors:
        if err.get("row_number") == row_number:
            row_found = True
        else:
            new_errors.append(err)
            
    if not row_found:
        await db.rollback()
        return {"success": True, "already_corrected": True}
        
    new_failed = max(0, current_failed - 1)
    new_success = current_success + 1
    
    if new_failed == 0:
        new_status = "completed"
    else:
        new_status = "partial" if current_status != "failed" else "failed"
        
    await db.execute(
        text("""
            UPDATE import_batches
            SET error_log = :error_log,
                failed_rows = :failed_rows,
                successful_rows = :successful_rows,
                status = :status,
                completed_at = CASE WHEN :failed_rows = 0 THEN NOW() ELSE completed_at END
            WHERE id = :id
        """),
        {
            "id": id,
            "error_log": json.dumps(new_errors),
            "failed_rows": new_failed,
            "successful_rows": new_success,
            "status": new_status
        }
    )
    
    await db.commit()
    return {
        "success": True, 
        "failed_rows": new_failed, 
        "successful_rows": new_success,
        "batch_status": new_status
    }



