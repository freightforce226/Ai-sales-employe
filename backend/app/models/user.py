from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Uuid, Enum, ForeignKey
from app.db.base import Base
import enum

class UserRole(str, enum.Enum):
    org_admin = "org_admin"
    sales_user = "sales_user"
    viewer = "viewer"

class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False, index=True)
    auth_user_id = Column(Uuid, nullable=False, unique=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    role = Column(Enum(UserRole, name="user_role", inherit_schema=True), nullable=False, default=UserRole.sales_user)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
