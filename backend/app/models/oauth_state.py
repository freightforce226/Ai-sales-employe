"""
Purpose of this file.
SQLAlchemy model for tracking OAuth flow state.
Responsibility of this file.
Storing and validating the state parameter during the OAuth flow to prevent CSRF attacks and link to a tenant.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Uuid

from app.db.base import Base


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id = Column(Uuid, nullable=False, index=True)
    state = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
