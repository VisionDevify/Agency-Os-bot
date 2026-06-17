from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

RECOMMENDATION_SEVERITIES = ("info", "warning", "critical")
RECOMMENDATION_STATUSES = ("open", "acknowledged", "dismissed", "resolved")


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_recommendations_severity",
        ),
        CheckConstraint(
            "status in ('open', 'acknowledged', 'dismissed', 'resolved')",
            name="ck_recommendations_status",
        ),
        Index("ix_recommendations_type", "recommendation_type"),
        Index("ix_recommendations_severity", "severity"),
        Index("ix_recommendations_status", "status"),
        Index("ix_recommendations_entity", "entity_type", "entity_id"),
        Index("ix_recommendations_generated_from_event_id", "generated_from_event_id"),
        Index("ix_recommendations_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    generated_from_event_id: Mapped[int | None] = mapped_column(ForeignKey("event_logs.id"), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
