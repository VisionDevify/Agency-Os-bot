from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


PREDICTION_OUTCOMES = (
    "pending",
    "proven_correct",
    "proven_wrong",
    "unresolved",
    "expired",
    "not_enough_evidence",
)

CALIBRATION_STATUSES = (
    "calibrated",
    "overconfident",
    "underconfident",
    "insufficient_data",
)


class PredictionOutcome(TimestampMixin, Base):
    __tablename__ = "prediction_outcomes"
    __table_args__ = (
        CheckConstraint(
            "outcome in ('pending', 'proven_correct', 'proven_wrong', 'unresolved', 'expired', 'not_enough_evidence')",
            name="ck_prediction_outcomes_outcome",
        ),
        CheckConstraint(
            "confidence_at_prediction in ('low', 'medium', 'high')",
            name="ck_prediction_outcomes_confidence",
        ),
        Index("ix_prediction_outcomes_prediction_id", "prediction_id"),
        Index("ix_prediction_outcomes_prediction_type", "prediction_type"),
        Index("ix_prediction_outcomes_category", "category"),
        Index("ix_prediction_outcomes_outcome", "outcome"),
        Index("ix_prediction_outcomes_evaluated_at", "evaluated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(
        ForeignKey("predictive_coo_predictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    prediction_type: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence_at_prediction: Mapped[str] = mapped_column(String(20), nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text(), default="Waiting for evidence.", nullable=False)
    evidence_records: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    correction_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
