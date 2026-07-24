"""
===========================================================

File:
ai_reply.py

Purpose:
SQLAlchemy model representing organization AI reply settings.

Why this file exists:
Maps the organization_ai_settings table to an ORM model.

Used By:
AI Reply Engine
Database Migrations
AIReplyService

Responsibilities:
- Define database columns for organization_ai_settings

===========================================================
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Uuid, JSON
from app.db.base import Base

class OrganizationAiSettings(Base):
    __tablename__ = "organization_ai_settings"

    organization_id = Column(Uuid, primary_key=True, index=True)
    ai_enabled = Column(Boolean, nullable=False, default=False)
    company_name = Column(String, nullable=True)
    reply_tone = Column(String, nullable=False, default="professional")
    ai_writing_instructions = Column(String, nullable=True)
    email_signature = Column(String, nullable=True)
    default_cc_emails = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
