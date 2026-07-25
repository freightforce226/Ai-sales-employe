"""
===========================================================

File:
ai_reply.py

Purpose:
Pydantic schemas/DTOs for validating and formatting AI Reply settings and generation requests.

Why this file exists:
Ensures correct request payload structures and serialized response models.

Used By:
AI Reply API Router
AIReplyService

Responsibilities:
- Validate settings update requests
- Format settings query responses
- Validate generate draft requests
- Format generate draft responses

===========================================================
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

class AIReplySettingsResponse(BaseModel):
    organization_id: UUID
    ai_enabled: bool
    company_name: Optional[str] = None
    reply_tone: str
    ai_writing_instructions: Optional[str] = None
    email_signature: Optional[str] = None
    default_cc_emails: List[EmailStr]

    model_config = {
        "from_attributes": True
    }

class AIReplySettingsUpdate(BaseModel):
    ai_enabled: Optional[bool] = None
    company_name: Optional[str] = None
    reply_tone: Optional[str] = None
    ai_writing_instructions: Optional[str] = None
    email_signature: Optional[str] = None
    default_cc_emails: Optional[List[EmailStr]] = None

class AIReplyGenerateRequest(BaseModel):
    organization_id: Optional[UUID] = None
    customer_id: UUID
    thread_id: str
    latest_customer_email: Optional[str] = None
    customer_reply_text: Optional[str] = None



class AIReplyGenerateResponse(BaseModel):
    subject: str
    reply_body: str
    suggested_cc_emails: List[str]
    generation_time: datetime
    provider: str
    model: str

class AIReplyPendingResponse(BaseModel):
    reply_id: UUID
    organization_id: UUID
    organization_name: str
    customer_id: UUID
    customer_name: str
    customer_email: str
    mailbox_email: Optional[str] = None
    thread_id: str
    conversation_id: Optional[str] = None
    message_id: str
    internet_message_id: Optional[str] = None
    subject: str
    latest_email_html: str
    customer_reply_text: str
    received_datetime: datetime
    reply_tone: str
    default_cc: List[str]
    ai_writing_instructions: Optional[str] = None
    email_signature: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class AIReplyCompleteRequest(BaseModel):
    reply_id: UUID
    graph_message_id: str
    sent_at: datetime

    @field_validator("graph_message_id")
    @classmethod
    def validate_graph_message_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("invalid_graph_message_id")
        return v


class AIReplyCompleteResponse(BaseModel):
    success: bool
    reply_id: UUID
    graph_message_id: str
    sent_at: datetime
    delivery_status: str


class AIReplyLockRequest(BaseModel):
    reply_id: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    organization_id: UUID



class AIReplyLockResponse(BaseModel):
    success: bool
    status: Optional[str] = None
    reason: Optional[str] = None
    reply_id: Optional[UUID] = None
    organization_id: UUID
    customer_id: Optional[UUID] = None
    thread_id: Optional[str] = None
    message_id: Optional[str] = None
    customer_reply_text: Optional[str] = None






