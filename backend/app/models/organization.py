from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Uuid, Enum, JSON
from app.db.base import Base
import enum

class PlanTier(str, enum.Enum):
    pilot = "pilot"
    standard = "standard"
    premium = "premium"
    enterprise = "enterprise"

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    logo_url = Column(String, nullable=True)
    theme_config = Column(JSON, nullable=True)  # Store colors, favicon, etc.
    custom_domain = Column(String, nullable=True, unique=True, index=True)
    plan_tier = Column(Enum(PlanTier, name="plan_tier", inherit_schema=True), nullable=False, default=PlanTier.pilot)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
