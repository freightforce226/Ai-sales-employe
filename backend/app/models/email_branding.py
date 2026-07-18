from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, DateTime, Uuid, Text
from app.db.base import Base

class OrganizationEmailBranding(Base):
    __tablename__ = "organization_email_branding"

    organization_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    sender_name = Column(String(255), nullable=True)
    designation = Column(String(255), nullable=True)
    reply_email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)
    linkedin = Column(String(255), nullable=True)
    company_logo = Column(Text, nullable=True)
    signature_html = Column(Text, nullable=True)
    signature_plain = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
