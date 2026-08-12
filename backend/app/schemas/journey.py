from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from uuid import UUID

class JourneyEvent(BaseModel):
    id: str
    module: str
    event_type: str
    status: str
    timestamp: str
    title: str
    subtitle: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    expandable: bool = False
    metadata: Optional[Dict[str, Any]] = None
    mail: Optional[Dict[str, Any]] = None
    attachments: Optional[List[str]] = None
    step_number: Optional[int] = None

class CustomerJourneyResponse(BaseModel):
    customer_id: UUID
    timeline: List[JourneyEvent]
