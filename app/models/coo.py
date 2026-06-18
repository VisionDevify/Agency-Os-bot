from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

PRIORITY_SEVERITIES = ("info", "warning", "critical")
PRIORITY_URGENCIES = ("low", "normal", "high", "urgent")
PRIORITY_STATUSES = ("open", "routed", "acknowledged", "resolved", "dismissed")


class PriorityItem(TimestampMixin, Base):
    __tablename__ = "priority_items"
    __table_args__ = (
        CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_priority_items_severity",
        ),
        CheckConstraint(
            "urgency in ('low', 'normal', 'high', 'urgent')",
            name="ck_priority_items_urgency",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 100", name="ck_priority_items_confidence"),
        CheckConstraint("business_impact >= 0 and business_impact <= 100", name="ck_priority_items_business_impact"),
        CheckConstraint("score >= 0 and score <= 100", name="ck_priority_items_score"),
        CheckConstraint(
            "status in ('open', 'routed', 'acknowledged', 'resolved', 'dismissed')",
            name="ck_priority_items_status",
        ),
        UniqueConstraint(
            "source_type",
            "source_id",
            "category",
            name="uq_priority_items_source_category",
        ),
        Index("ix_priority_items_source", "source_type", "source_id"),
        Index("ix_priority_items_category", "category"),
        Index("ix_priority_items_status", "status"),
        Index("ix_priority_items_score", "score"),
        Index("ix_priority_items_recommended_owner", "recommended_owner"),
        Index("ix_priority_items_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    urgency: Mapped[str] = mapped_column(String(40), default="normal", nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    business_impact: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    explanation: Mapped[str] = mapped_column(Text(), nullable=False)
    recommended_owner: Mapped[str] = mapped_column(String(80), default="Manager", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
