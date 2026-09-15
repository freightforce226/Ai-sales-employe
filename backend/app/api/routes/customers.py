from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from app.services.customer_service import CustomerService
from app.services.customer_journey_service import CustomerJourneyService
from app.schemas.journey import CustomerJourneyResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import UUID

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])

# Schema definitions
class CustomerCreate(BaseModel):
    company_name: str = Field(..., min_length=1)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    designation: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    linkedin: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    shipment_mode: Optional[str] = None
    trade_direction: Optional[str] = None
    customer_type: Optional[str] = None
    trade_region: Optional[str] = None
    goods_description: Optional[str] = None

class CustomerUpdate(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    designation: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    linkedin: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    shipment_mode: Optional[str] = None
    trade_direction: Optional[str] = None
    customer_type: Optional[str] = None
    trade_region: Optional[str] = None
    goods_description: Optional[str] = None
    raw_company_name: Optional[str] = None
    raw_contact_name: Optional[str] = None

class CustomerResponse(BaseModel):
    id: UUID
    company_name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    segment: Optional[str] = None
    engagement_readiness: str
    last_email: Optional[str] = None
    imported_on: Optional[str] = ""
    status: str
    designation: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    linkedin: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    shipment_mode: Optional[str] = None
    trade_direction: Optional[str] = None
    customer_type: Optional[str] = None
    trade_region: Optional[str] = None
    goods_description: Optional[str] = None
    raw_company_name: Optional[str] = None
    raw_contact_name: Optional[str] = None
    is_suppressed: bool = False
    suppression_reason: Optional[str] = None
    bounce_reason: Optional[str] = None
    suppressed_at: Optional[str] = None

class TimelineEvent(BaseModel):
    subject: str
    sent_at: str
    delivery_status: str

class CustomerDetailResponse(CustomerResponse):
    import_batch_id: Optional[UUID] = None
    import_batch_name: Optional[str] = None
    total_emails_sent: int = 0
    assigned_template: Optional[str] = None
    assigned_attachment: Optional[str] = None
    last_subject: Optional[str] = None
    last_delivery_status: Optional[str] = None
    last_message_id: Optional[str] = None
    emails_this_week: int = 0
    emails_this_month: int = 0
    timeline: List[TimelineEvent] = []

class CustomersListResponse(BaseModel):
    customers: List[CustomerResponse]
    total: int
    page: int
    limit: int

class CustomerStatsResponse(BaseModel):
    total_customers: int
    ready_count: int
    segment_breakdown: Dict[str, int]
    country_breakdown: Dict[str, int]

class FilterValuesResponse(BaseModel):
    industries: List[str]
    countries: List[str]
    segments: List[str]

class BulkDeleteRequest(BaseModel):
    ids: List[UUID]


@router.get("", response_model=CustomersListResponse)
async def get_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    q: Optional[str] = None,
    industry: Optional[str] = None,
    country: Optional[str] = None,
    segment: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerService(db, current_user.organization_id)
    customers, total = await service.get_customers(page, limit, q, industry, country, segment)
    return CustomersListResponse(customers=customers, total=total, page=page, limit=limit)


@router.get("/stats", response_model=CustomerStatsResponse)
async def get_customer_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerService(db, current_user.organization_id)
    stats_data = await service.get_stats()
    return CustomerStatsResponse(**stats_data)


@router.get("/filters", response_model=FilterValuesResponse)
async def get_filter_values(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerService(db, current_user.organization_id)
    filter_data = await service.get_filters()
    return FilterValuesResponse(**filter_data)


@router.get("/{id}", response_model=CustomerDetailResponse)
async def get_customer(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerService(db, current_user.organization_id)
    customer = await service.get_customer_by_id(id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return CustomerDetailResponse(**customer)


@router.put("/{id}", response_model=CustomerResponse)
async def update_customer(
    id: UUID,
    request: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerService(db, current_user.organization_id)
    customer = await service.update_customer(
        id,
        request.company_name,
        request.contact_name,
        request.contact_email,
        request.industry,
        request.country
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    await db.commit()
    return CustomerResponse(**customer)


@router.delete("/{id}")
async def delete_customer(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerService(db, current_user.organization_id)
    success = await service.delete_customer(id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    await db.commit()
    return {"success": True}


@router.post("/bulk-delete")
async def bulk_delete_customers(
    request: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerService(db, current_user.organization_id)
    deleted_count = await service.bulk_delete_customers(request.ids)
    await db.commit()
    return {"success": True, "deleted_count": deleted_count}


@router.get("/{id}/journey", response_model=CustomerJourneyResponse)
async def get_customer_journey(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    service = CustomerJourneyService(db, current_user.organization_id)
    return await service.get_journey(id)


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    from app.core.normalization import (
        normalize_company_name,
        normalize_contact_name,
        normalize_email,
        validate_email_syntax,
        normalize_phone,
        normalize_website,
        normalize_shipment_mode,
        normalize_trade_direction,
        normalize_country,
        derive_trade_region
    )
    import uuid

    org_id = current_user.organization_id

    # Normalize fields
    company_name = normalize_company_name(payload.company_name)
    if not company_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Normalized company name cannot be empty.")

    contact_name = normalize_contact_name(payload.contact_name) if payload.contact_name else None
    contact_email = normalize_email(payload.contact_email) if payload.contact_email else None
    raw_contact_email_val = payload.contact_email.strip() if payload.contact_email else None

    email_validation_status = "valid"
    email_validation_error = None
    if contact_email:
        is_val, val_err = validate_email_syntax(contact_email)
        if not is_val:
            email_validation_status = "invalid"
            email_validation_error = val_err

    phone = normalize_phone(payload.phone) if payload.phone else None
    website = normalize_website(payload.website) if payload.website else None
    linkedin = normalize_website(payload.linkedin) if payload.linkedin else None
    shipment_mode = normalize_shipment_mode(payload.shipment_mode) if payload.shipment_mode else None
    trade_direction = normalize_trade_direction(payload.trade_direction) if payload.trade_direction else None
    country = normalize_country(payload.country) if payload.country else None
    trade_region = payload.trade_region or (derive_trade_region(country) if country else None)


    # Perform Duplicate Check (unrestricted by deleted_at to avoid database UniqueViolationError)
    if contact_email:
        dup_res = await db.execute(
            text("SELECT id FROM customers WHERE organization_id = :org_id AND contact_email = :email"),
            {"org_id": org_id, "email": contact_email}
        )
        if dup_res.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A customer with contact email '{contact_email}' already exists."
            )
    else:
        if contact_name:
            dup_res = await db.execute(
                text("""
                    SELECT id FROM customers 
                    WHERE organization_id = :org_id 
                      AND company_name = :company_name 
                      AND contact_name = :contact_name
                """),
                {"org_id": org_id, "company_name": company_name, "contact_name": contact_name}
            )
        else:
            dup_res = await db.execute(
                text("""
                    SELECT id FROM customers 
                    WHERE organization_id = :org_id 
                      AND company_name = :company_name 
                      AND contact_name IS NULL
                """),
                {"org_id": org_id, "company_name": company_name}
            )
        if dup_res.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A customer with company name '{company_name}' already exists."
            )

    customer_id = uuid.uuid4()
    
    from sqlalchemy.exc import IntegrityError
    try:
        await db.execute(
            text("""
                INSERT INTO customers (
                    id, organization_id, company_name, contact_name, contact_email,
                    industry, country, designation, phone, website, linkedin,
                    address, city, state, shipment_mode, trade_direction,
                    customer_type, trade_region, goods_description,
                    raw_company_name, raw_contact_name, raw_contact_email,
                    email_validation_status, email_validation_error, created_at, updated_at
                ) VALUES (
                    :id, :org_id, :company_name, :contact_name, :contact_email,
                    :industry, :country, :designation, :phone, :website, :linkedin,
                    :address, :city, :state, :shipment_mode, :trade_direction,
                    :customer_type, :trade_region, :goods_description,
                    :raw_company_name, :raw_contact_name, :raw_contact_email,
                    :validation_status, :validation_error, NOW(), NOW()
                )
            """),
            {
                "id": customer_id,
                "org_id": org_id,
                "company_name": company_name,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "industry": payload.industry,
                "country": country,
                "designation": payload.designation,
                "phone": phone,
                "website": website,
                "linkedin": linkedin,
                "address": payload.address,
                "city": payload.city,
                "state": payload.state,
                "shipment_mode": shipment_mode,
                "trade_direction": trade_direction,
                "customer_type": payload.customer_type,
                "trade_region": trade_region,
                "goods_description": payload.goods_description,
                "raw_company_name": payload.company_name,
                "raw_contact_name": payload.contact_name,
                "raw_contact_email": raw_contact_email_val,
                "validation_status": email_validation_status,
                "validation_error": email_validation_error
            }
        )

        await db.commit()
    except IntegrityError as integrity_err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A customer with this contact email or company details already exists."
        )

    service = CustomerService(db, org_id)
    cust_data = await service.get_customer_by_id(customer_id)
    if not cust_data:
        raise HTTPException(status_code=500, detail="Failed to retrieve created customer details.")
    
    return CustomerResponse(**cust_data)
