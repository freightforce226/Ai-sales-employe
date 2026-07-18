from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    full_name: str
    email: EmailStr

class UserCreate(UserBase):
    organization_id: UUID
    auth_user_id: UUID
    role: str = "sales_user"

class UserResponse(UserBase):
    id: UUID
    organization_id: UUID
    auth_user_id: UUID
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserProfileResponse(BaseModel):
    user: UserResponse
    organization: Optional[UUID] = None
    role: str
