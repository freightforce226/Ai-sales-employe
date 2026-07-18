from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, DateTime, Date, Uuid, ForeignKey
from app.db.base import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False, index=True)
    import_batch_id = Column(Uuid, ForeignKey("import_batches.id"), nullable=True, index=True)
    company_name = Column(String, nullable=False)
    industry = Column(String, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    country = Column(String, nullable=True)
    last_shipment_date = Column(Date, nullable=True)
    last_contact_date = Column(Date, nullable=True)
    source = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
