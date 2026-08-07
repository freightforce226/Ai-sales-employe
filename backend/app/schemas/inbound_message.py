from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class InboundAttachment(BaseModel):
    filename: str
    content_type: str
    size: int
    content_id: Optional[str] = None
    is_inline: bool = False
    payload: Optional[bytes] = None

class InboundMessage(BaseModel):
    provider_message_id: str
    internet_message_id: str
    provider: str
    conversation_id: Optional[str] = None
    thread_id: Optional[str] = None
    subject: str
    html_body: str
    plain_text_body: str
    from_email: str
    from_name: Optional[str] = None
    to_recipients: List[str]
    cc_recipients: List[str]
    received_at: datetime
    has_attachments: bool
    attachments: List[InboundAttachment] = []
    in_reply_to: Optional[str] = None
    references: Optional[str] = None

class InboundSyncResult(BaseModel):
    messages: List[InboundMessage]
    new_cursor: str
    provider: str
