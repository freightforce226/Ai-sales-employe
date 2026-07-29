"""
Purpose of this file.
SQLAlchemy model for tenant integrations.
Responsibility of this file.
Mapping the tenant_integrations table in Supabase to Python code.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Uuid, Enum, Integer

from app.db.base import Base

class IntegrationProvider(str, enum.Enum):
    microsoft_graph = "microsoft_graph"
    google_workspace = "google_workspace"
    smtp = "smtp"


class TenantIntegration(Base):
    __tablename__ = "tenant_integrations"

    organization_id = Column(Uuid, primary_key=True, index=True)
    provider = Column(
        Enum(IntegrationProvider, name="integration_provider", inherit_schema=True),
        nullable=False,
        default=IntegrationProvider.microsoft_graph
    )
    mailbox_email = Column(String, nullable=False)
    encrypted_access_token = Column(String, nullable=True)
    encrypted_refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_refreshed_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(String, nullable=True)

    # SMTP/IMAP settings
    auth_username = Column(String, nullable=True)
    encrypted_password = Column(String, nullable=True)
    smtp_host = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_security = Column(String, nullable=True)
    imap_host = Column(String, nullable=True)
    imap_port = Column(Integer, nullable=True)
    imap_security = Column(String, nullable=True)
    last_sync_cursor = Column(String, nullable=True)

