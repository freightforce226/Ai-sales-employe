import re
import json
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, Field, validator
from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/v1/templates", tags=["Templates"])

ALLOWED_PLACEHOLDERS = {
    "company_name",
    "contact_name",
    "industry",
    "country",
    "website",
    "phone",
    "sender_name",
    "sender_company",
    "current_date"
}

def sanitize_html(html: str) -> str:
    """
    Remove potentially dangerous tags and event handlers to prevent XSS.
    """
    if not html:
        return ""
    # Strip script tags and their content
    html = re.sub(r'(?i)<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html)
    # Strip iframe tags and their content
    html = re.sub(r'(?i)<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>', '', html)
    # Strip object tags and their content
    html = re.sub(r'(?i)<object\b[^<]*(?:(?!<\/object>)<[^<]*)*<\/object>', '', html)
    # Strip embed tags and their content
    html = re.sub(r'(?i)<embed\b[^<]*(?:(?!<\/embed>)<[^<]*)*<\/embed>', '', html)
    # Strip inline javascript handlers (like onload, onclick)
    html = re.sub(r'(?i)\bon[a-z]+\s*=\s*(["\'])(.*?)\1', '', html)
    return html

def validate_placeholders(content: str):
    """
    Check for malformed, misspelled, or single-braced placeholders.
    """
    if not content:
        return

    # Check that counts of '{{' and '}}' are equal
    if content.count('{{') != content.count('}}'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed placeholder tag detected. Ensure all placeholder tags are enclosed in double curly braces, e.g. {{company_name}}."
        )

    # Find matches of {{ ... }}
    matches = re.findall(r'\{\{(.*?)\}\}', content)
    if len(matches) != content.count('{{'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed placeholder tag detected. Ensure all placeholder tags are enclosed in double curly braces, e.g. {{company_name}}."
        )

    for brace in matches:
        if '{' in brace or '}' in brace:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Malformed placeholder tag: {{{{{brace}}}}}. Do not nest braces."
            )
        
        clean_brace = brace.strip()
        if clean_brace not in ALLOWED_PLACEHOLDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid placeholder tag: {{{{{brace}}}}}. Only allowed variables are: {', '.join(sorted(ALLOWED_PLACEHOLDERS))}"
            )
        if brace != clean_brace:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Malformed placeholder tag: {{{{{brace}}}}}. Do not include extra spaces inside the braces."
            )

    # Check for single curly braces enclosing allowed variables
    single_braces = re.findall(r'(?<!\{)\{([a-zA-Z0-9_ ]+)\}(?!\})', content)
    for tag in single_braces:
        clean_tag = tag.strip()
        if clean_tag in ALLOWED_PLACEHOLDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Malformed placeholder: {{{tag}}}. Did you mean {{{{{clean_tag}}}}}?"
            )

# Pydantic Schemas
class TemplateCreate(BaseModel):
    template_name: str = Field(..., max_length=100)
    industry: str
    subject: str = Field(..., max_length=200)
    body: str
    status: str = Field("draft")
    template_type: Optional[str] = "engagement"

    @validator('status')
    def validate_status(cls, v):
        if v not in ("active", "draft"):
            raise ValueError("Status must be 'active' or 'draft'")
        return v

class TemplateUpdate(BaseModel):
    template_name: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = None
    subject: Optional[str] = Field(None, max_length=200)
    body: Optional[str] = None
    status: Optional[str] = None
    template_type: Optional[str] = None

    @validator('status')
    def validate_status(cls, v):
        if v is not None and v not in ("active", "draft"):
            raise ValueError("Status must be 'active' or 'draft'")
        return v

class TemplateResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    template_name: str
    name: str
    industry: str
    industry_tag: str
    subject: str
    example_subject: str
    body: str
    example_body: str
    status: str
    is_active: bool
    template_type: str
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

class TemplatesListResponse(BaseModel):
    templates: List[TemplateResponse]
    total: int
    page: int
    limit: int

def map_db_to_response(row) -> TemplateResponse:
    # row index: id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at
    status_str = "active" if row[7] else "draft"
    return TemplateResponse(
        id=row[0],
        organization_id=row[1],
        template_name=row[3],
        name=row[3],
        industry=row[6],
        industry_tag=row[6],
        subject=row[4],
        example_subject=row[4],
        body=row[5],
        example_body=row[5],
        status=status_str,
        is_active=row[7],
        template_type=row[2] or "engagement",
        created_by=row[8],
        created_at=row[9],
        updated_at=row[10]
    )

@router.get("/industries", response_model=List[str])
async def get_industries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get a list of standardized industries for templates selection.
    """
    standard_industries = ["Steel", "Chemicals", "Textiles", "Electronics", "Automotive", "Agriculture", "Manufacturing", "Food & Beverage", "Retail", "Energy"]
    try:
        res = await db.execute(
            text("SELECT DISTINCT industry FROM customers WHERE organization_id = :org_id AND industry IS NOT NULL"),
            {"org_id": current_user.organization_id}
        )
        db_industries = [row[0] for row in res.fetchall() if row[0]]
        # Merge standard list and distinct DB industries while preserving casing/uniqueness
        all_industries = sorted(list(set(standard_industries + db_industries)))
        return all_industries
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch industries: {str(e)}"
        )

@router.get("", response_model=TemplatesListResponse)
async def get_templates(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    q: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    sort: str = "recently_updated",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    List, search, filter, and paginate templates.
    """
    org_id = current_user.organization_id
    offset = (page - 1) * limit

    # Build filters
    conditions = ["organization_id = :org_id"]
    params = {"org_id": org_id}

    if q:
        conditions.append("(name ILIKE :q OR example_subject ILIKE :q OR industry_tag ILIKE :q)")
        params["q"] = f"%{q}%"
    
    if industry:
        conditions.append("industry_tag = :industry")
        params["industry"] = industry

    if status:
        conditions.append("is_active = :is_active")
        params["is_active"] = True if status == "active" else False

    # Sorting
    order_clause = "updated_at DESC"
    if sort == "name_asc":
        order_clause = "name ASC"
    elif sort == "created_date":
        order_clause = "created_at DESC"
    elif sort == "industry":
        order_clause = "industry_tag ASC"

    where_str = " AND ".join(conditions)

    try:
        # Get total count
        count_res = await db.execute(
            text(f"SELECT count(*) FROM email_templates WHERE {where_str}"),
            params
        )
        total = count_res.scalar()

        # Get rows
        params["limit"] = limit
        params["offset"] = offset
        res = await db.execute(
            text(f"""
                SELECT id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at
                FROM email_templates
                WHERE {where_str}
                ORDER BY {order_clause}
                LIMIT :limit OFFSET :offset
            """),
            params
        )
        rows = res.fetchall()
        templates = [map_db_to_response(r) for r in rows]

        return TemplatesListResponse(templates=templates, total=total, page=page, limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch templates: {str(e)}"
        )

@router.get("/{id}", response_model=TemplateResponse)
async def get_template(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get a single template by ID.
    """
    try:
        res = await db.execute(
            text("""
                SELECT id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at
                FROM email_templates
                WHERE id = :id AND organization_id = :org_id
            """),
            {"id": id, "org_id": current_user.organization_id}
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found."
            )
        return map_db_to_response(row)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch template details: {str(e)}"
        )

@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Create a new template.
    """
    # 1. Validation checks
    validate_placeholders(payload.subject)
    validate_placeholders(payload.body)

    # 2. HTML Sanitization
    sanitized_body = sanitize_html(payload.body)

    template_id = uuid.uuid4()
    is_active = True if payload.status == "active" else False

    try:
        await db.execute(
            text("""
                INSERT INTO email_templates (id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at)
                VALUES (:id, :org_id, :type, :name, :subject, :body, :industry, :is_active, :created_by, NOW(), NOW())
            """),
            {
                "id": template_id,
                "org_id": current_user.organization_id,
                "type": payload.template_type or "engagement",
                "name": payload.template_name,
                "subject": payload.subject,
                "body": sanitized_body,
                "industry": payload.industry,
                "is_active": is_active,
                "created_by": current_user.id
            }
        )
        await db.commit()

        # Fetch and return the newly created row
        res = await db.execute(
            text("""
                SELECT id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at
                FROM email_templates
                WHERE id = :id
            """),
            {"id": template_id}
        )
        return map_db_to_response(res.fetchone())
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )

@router.put("/{id}", response_model=TemplateResponse)
async def update_template(
    id: uuid.UUID,
    payload: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update an existing template.
    """
    # Check if exists
    res = await db.execute(
        text("SELECT is_active, example_body, example_subject FROM email_templates WHERE id = :id AND organization_id = :org_id"),
        {"id": id, "org_id": current_user.organization_id}
    )
    existing = res.fetchone()
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found."
        )

    # 1. Validation checks
    if payload.subject is not None:
        validate_placeholders(payload.subject)
    if payload.body is not None:
        validate_placeholders(payload.body)

    # 2. HTML Sanitization
    sanitized_body = sanitize_html(payload.body) if payload.body is not None else None

    # Build dynamic update SQL
    updates = ["updated_at = NOW()"]
    params = {"id": id, "org_id": current_user.organization_id}

    if payload.template_name is not None:
        updates.append("name = :name")
        params["name"] = payload.template_name

    if payload.industry is not None:
        updates.append("industry_tag = :industry")
        params["industry"] = payload.industry

    if payload.subject is not None:
        updates.append("example_subject = :subject")
        params["subject"] = payload.subject

    if payload.body is not None:
        updates.append("example_body = :body")
        params["body"] = sanitized_body

    if payload.status is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = True if payload.status == "active" else False

    if payload.template_type is not None:
        updates.append("template_type = :type")
        params["type"] = payload.template_type

    updates_str = ", ".join(updates)

    try:
        await db.execute(
            text(f"""
                UPDATE email_templates
                SET {updates_str}
                WHERE id = :id AND organization_id = :org_id
            """),
            params
        )
        await db.commit()

        # Fetch and return the updated row
        res = await db.execute(
            text("""
                SELECT id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at
                FROM email_templates
                WHERE id = :id
            """),
            {"id": id}
        )
        return map_db_to_response(res.fetchone())
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update template: {str(e)}"
        )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Permanently delete a template. Hard delete only.
    """
    try:
        res = await db.execute(
            text("DELETE FROM email_templates WHERE id = :id AND organization_id = :org_id"),
            {"id": id, "org_id": current_user.organization_id}
        )
        if res.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found."
            )
        await db.commit()
    except Exception as e:
        await db.rollback()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete template: {str(e)}"
        )

@router.post("/{id}/duplicate", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_template(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Duplicate an existing template. Creates it as a Draft.
    """
    try:
        res = await db.execute(
            text("""
                SELECT organization_id, template_type, name, example_subject, example_body, industry_tag
                FROM email_templates
                WHERE id = :id AND organization_id = :org_id
            """),
            {"id": id, "org_id": current_user.organization_id}
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template to duplicate not found."
            )

        new_id = uuid.uuid4()
        new_name = f"Copy of {row[2]}"

        await db.execute(
            text("""
                INSERT INTO email_templates (id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at)
                VALUES (:id, :org_id, :type, :name, :subject, :body, :industry, FALSE, :created_by, NOW(), NOW())
            """),
            {
                "id": new_id,
                "org_id": current_user.organization_id,
                "type": row[1],
                "name": new_name,
                "subject": row[3],
                "body": row[4],
                "industry": row[5],
                "created_by": current_user.id
            }
        )
        await db.commit()

        # Fetch and return the new duplicated template
        res_new = await db.execute(
            text("""
                SELECT id, organization_id, template_type, name, example_subject, example_body, industry_tag, is_active, created_by, created_at, updated_at
                FROM email_templates
                WHERE id = :id
            """),
            {"id": new_id}
        )
        return map_db_to_response(res_new.fetchone())
    except Exception as e:
        await db.rollback()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to duplicate template: {str(e)}"
        )
