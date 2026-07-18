from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class EmailBrandingSchema(BaseModel):
    sender_name: Optional[str] = Field(None, max_length=255)
    designation: Optional[str] = Field(None, max_length=255)
    reply_email: Optional[EmailStr] = Field(None)
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=255)
    linkedin: Optional[str] = Field(None, max_length=255)
    company_logo: Optional[str] = Field(None)
    signature_html: Optional[str] = Field(None)
    signature_plain: Optional[str] = Field(None)

    class Config:
        from_attributes = True
