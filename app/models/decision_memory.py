from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


DECISION_MEMORY_OUTCOMES = (
    "shown",
    "opened",
    "acted_on",
    "ignored",
    "resolved",
    "failed",
    "stale",
    "dismissed",
)

DECISION_MEMORY_LIFECYCLE_STATUSES = (
    "active",
    "opened",
    "in_progress",
    "waiting_for_evidence",
    "resolved",
    "dismissed",
    "stale",
)

DECISION_MEMORY_CATEGORIES = (
    "recovery",
    "system_health",
    "telegram_bot",
    "navigation",
    "notification",
    "platform_connection",
    "opportunity",
    "social_intelligence",
    "team",
    "learning",
    "friction",
    "setup",
    "deployment",
    "security",
    "general",
)

DECISION_MEMORY_SEVERITIES = ("healthy", "needs_review", "needs_attention", "critical")
DECISION_MEMORY_CONFIDENCE = ("high", "medium", "low")


class DecisionMemory(TimestampMixin, Base):
    __tablename__ = "decision_memory"
    __table_args__ = (
        CheckConstraint(
            "outcome in ('shown', 'opened', 'acted_on', 'ignored', 'resolved', 'failed', 'stale', 'dismissed')",
            name="ck_decision_memory_outcome",
        ),
        CheckConstraint(
            "lifecycle_status in ('active', 'opened', 'in_progress', 'waiting_for_evidence', 'resolved', 'dismissed', 'stale')",
            name="ck_decision_memory_lifecycle_status",
        ),
        CheckConstraint(
            "category in ('recovery', 'system_health', 'telegram_bot', 'navigation', 'notification', "
            "'platform_connection', 'opportunity', 'social_intelligence', 'team', 'learning', "
            "'friction', 'setup', 'deployment', 'security', 'general')",
            name="ck_decision_memory_category",
        ),
        CheckConstraint(
            "severity in ('healthy', 'needs_review', 'needs_attention', 'critical')",
            name="ck_decision_memory_severity",
        ),
        CheckConstraint(
            "confidence in ('high', 'medium', 'low')",
            name="ck_decision_memory_confidence",
        ),
        CheckConstraint("usefulness_score >= 0 and usefulness_score <= 100", name="ck_decision_memory_usefulness"),
        Index("ix_decision_memory_decision_id", "decision_id", unique=True),
        Index("ix_decision_memory_recommendation_id", "recommendation_id"),
        Index("ix_decision_memory_category", "category"),
        Index("ix_decision_memory_outcome", "outcome"),
        Index("ix_decision_memory_lifecycle", "lifecycle_status"),
        Index("ix_decision_memory_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_on_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ignored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), default="shown", nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    usefulness_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    owner_feedback: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evidence_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    source_records: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
