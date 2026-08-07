from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.core.auth import get_current_user
from app.models.user import User
from app.services.customer_service import CustomerService
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])

# Schema definitions
class CustomerUpdate(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None

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
    imported_on: str
    status: str

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
