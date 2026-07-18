from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Uuid, ForeignKey
from app.db.base import Base

class OrganizationSignature(Base):
    __tablename__ = "organization_signatures"

    organization_id = Column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    sender_name = Column(String(255), nullable=False)
    designation = Column(String(255), nullable=False)
    department = Column(String(255), nullable=True)
    sender_email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)
    linkedin_url = Column(String(255), nullable=True)
    signature_html = Column(String, nullable=False)
    
    # Optional Banner Strip Metadata
    footer_image_name = Column(String(255), nullable=True)
    footer_image_content_type = Column(String(100), nullable=True)
    footer_image_size = Column(Integer, nullable=True)
    footer_image_path = Column(String, nullable=True)
    
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
