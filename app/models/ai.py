from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.search import utcnow


AI_AUDIT_STATUSES = (
    "succeeded",
    "failed",
    "blocked_by_critic",
    "fallback_used",
    "not_configured",
    "rate_limited",
    "timeout",
)


class AIAuditLog(TimestampMixin, Base):
    __tablename__ = "ai_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "status in ('succeeded', 'failed', 'blocked_by_critic', 'fallback_used', 'not_configured', 'rate_limited', 'timeout')",
            name="ck_ai_audit_logs_status",
        ),
        CheckConstraint("evidence_count >= 0", name="ck_ai_audit_logs_evidence_count"),
        Index("ix_ai_audit_logs_use_case", "use_case"),
        Index("ix_ai_audit_logs_status", "status"),
        Index("ix_ai_audit_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    use_case: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_input_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_output_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    safe_error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=utcnow)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
