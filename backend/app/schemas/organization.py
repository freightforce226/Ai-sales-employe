from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class OrganizationBase(BaseModel):
    name: str = Field(..., description="Organization unique slug/name")
    display_name: str = Field(..., description="Organization user-friendly name")
    logo_url: Optional[str] = None
    custom_domain: Optional[str] = None

class OrganizationCreate(OrganizationBase):
    theme_config: Optional[Dict[str, Any]] = None

class OrganizationResponse(OrganizationBase):
    id: UUID
    theme_config: Optional[Dict[str, Any]] = None
    plan_tier: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BrandingResponse(BaseModel):
    company_name: str
    logo_url: Optional[str] = None
    theme_config: Dict[str, Any] = Field(default_factory=dict)
