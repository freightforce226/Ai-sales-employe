from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Uuid, ForeignKey, UniqueConstraint
from app.db.base import Base

class FollowUpAiCache(Base):
    __tablename__ = "follow_up_ai_cache"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id = Column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    step_number = Column(Integer, nullable=False)
    cache_key = Column(String(64), nullable=False)
    generated_subject = Column(String(255), nullable=False)
    generated_body_template = Column(String, nullable=False)
    prompt_version = Column(String(20), nullable=False, default="followup_v2")
    model_used = Column(String(50), nullable=False)
    tokens_consumed = Column(Integer, default=0)
    hit_count = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "step_number", "cache_key", name="uq_org_step_cache_key"),
    )
