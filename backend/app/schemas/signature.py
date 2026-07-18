from typing import Optional
from pydantic import BaseModel, Field

class OrganizationSignatureSchema(BaseModel):
    is_configured: bool = Field(False)
    sender_name: Optional[str] = Field("", max_length=255)
    designation: Optional[str] = Field("", max_length=255)
    department: Optional[str] = Field("", max_length=255)
    phone: Optional[str] = Field("", max_length=50)
    website: Optional[str] = Field("", max_length=255)
    linkedin_url: Optional[str] = Field("", max_length=255)
    signature_html: Optional[str] = Field("")
    
    # Optional image metadata fields
    footer_image_name: Optional[str] = Field(None, max_length=255)
    footer_image_content_type: Optional[str] = Field(None, max_length=100)
    footer_image_size: Optional[int] = Field(None)
    footer_image_path: Optional[str] = Field(None)
    footer_image_url: Optional[str] = Field("")
    
    updated_at: Optional[str] = Field(None)

    class Config:
        from_attributes = True
        
class SignatureDeleteResponse(BaseModel):
    success: bool
    message: str
