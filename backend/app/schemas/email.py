"""
Purpose of this file.
Pydantic schemas for email requests.
Responsibility of this file.
Validating the structure and types of incoming email sending requests from n8n.
"""

from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, UUID4


class AttachmentItem(BaseModel):
    id: UUID4
    storage_path: str
    filename: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    download_url: Optional[str] = None


class EmailRequest(BaseModel):
    organization_id: UUID4 = Field(..., description="The ID of the organization sending the email")
    customer_email: EmailStr = Field(..., description="The recipient's email address")
    subject: str = Field(..., min_length=1)
    body: Optional[str] = Field(None, description="Legacy fallback body")
    html_body: Optional[str] = Field(None, description="HTML body content")
    plain_text_body: Optional[str] = Field(None, description="Plain text fallback body")
    attachments: List[AttachmentItem] = Field(default_factory=list, description="Array of attachment metadata objects")
    strict_attachment_mode: bool = Field(False, description="Fail entire email if any attachment download fails")
    template_id: Optional[UUID4] = Field(None, description="The ID of the template used (for multi-tenant checks)")
    execution_id: Optional[UUID4] = Field(None, description="The ID of the active execution context (for multi-tenant checks)")
    thread_id: Optional[str] = Field(None, description="Microsoft Graph Conversation/Thread ID")
    conversation_id: Optional[str] = Field(None, description="Alias or standard Conversation ID")
    internet_message_id: Optional[str] = Field(None, description="RFC5322 Message-ID")
    references: Optional[str] = Field(None, description="RFC5322 references header value")
    in_reply_to: Optional[str] = Field(None, description="RFC5322 in-reply-to message ID")

    @field_validator("customer_email", mode="before")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.lower()
        return v

    @model_validator(mode="after")
    def validate_body_fields(self) -> "EmailRequest":
        # Body priority: html_body -> body -> plain_text_body
        if not self.html_body:
            if self.body:
                self.html_body = self.body
            elif self.plain_text_body:
                self.html_body = self.plain_text_body
            else:
                raise ValueError("At least one body content field must be provided (html_body, body, or plain_text_body)")
        return self


class EmailResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    sent_at: Optional[str] = None


class EmailErrorResponse(BaseModel):
    success: bool = False
    error: str
