from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


DECISION_TREND_WINDOWS = ("daily", "weekly", "monthly")
DECISION_TREND_DIRECTIONS = ("improving", "stable", "declining", "insufficient_data")
PREDICTION_TYPES = (
    "likely_next_priority",
    "recurring_risk",
    "likely_blocker",
    "upcoming_setup_need",
    "stale_decision_warning",
    "repeated_friction_warning",
)
PREDICTION_CONFIDENCE = ("low", "medium", "high")
PREDICTION_STATUSES = (
    "shown",
    "opened",
    "helpful",
    "not_helpful",
    "remind_later",
    "dismissed",
    "acted_on",
    "proven_correct",
    "proven_wrong",
)


class DecisionQualityTrend(TimestampMixin, Base):
    __tablename__ = "decision_quality_trends"
    __table_args__ = (
        CheckConstraint(
            "time_window in ('daily', 'weekly', 'monthly')",
            name="ck_decision_quality_trends_window",
        ),
        CheckConstraint(
            "trend_direction in ('improving', 'stable', 'declining', 'insufficient_data')",
            name="ck_decision_quality_trends_direction",
        ),
        CheckConstraint("decisions_shown >= 0", name="ck_decision_quality_trends_shown"),
        CheckConstraint("decisions_opened >= 0", name="ck_decision_quality_trends_opened"),
        CheckConstraint("decisions_acted_on >= 0", name="ck_decision_quality_trends_acted"),
        CheckConstraint("decisions_resolved >= 0", name="ck_decision_quality_trends_resolved"),
        CheckConstraint("decisions_ignored >= 0", name="ck_decision_quality_trends_ignored"),
        CheckConstraint("usefulness_score_avg >= 0 and usefulness_score_avg <= 100", name="ck_decision_quality_trends_usefulness"),
        CheckConstraint("confidence_accuracy_avg >= 0 and confidence_accuracy_avg <= 100", name="ck_decision_quality_trends_confidence"),
        CheckConstraint("recommendation_score_avg >= 0 and recommendation_score_avg <= 100", name="ck_decision_quality_trends_recommendation"),
        UniqueConstraint("category", "time_window", name="uq_decision_quality_trends_category_window"),
        Index("ix_decision_quality_trends_category", "category"),
        Index("ix_decision_quality_trends_direction", "trend_direction"),
        Index("ix_decision_quality_trends_window", "time_window"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    time_window: Mapped[str] = mapped_column(String(20), nullable=False)
    decisions_shown: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decisions_opened: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decisions_acted_on: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decisions_resolved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decisions_ignored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usefulness_score_avg: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_accuracy_avg: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommendation_score_avg: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trend_direction: Mapped[str] = mapped_column(String(40), default="insufficient_data", nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text(), default="Not enough evidence yet.", nullable=False)


class PredictiveCOOPrediction(TimestampMixin, Base):
    __tablename__ = "predictive_coo_predictions"
    __table_args__ = (
        CheckConstraint(
            "prediction_type in ('likely_next_priority', 'recurring_risk', 'likely_blocker', "
            "'upcoming_setup_need', 'stale_decision_warning', 'repeated_friction_warning')",
            name="ck_predictive_coo_predictions_type",
        ),
        CheckConstraint(
            "confidence in ('low', 'medium', 'high')",
            name="ck_predictive_coo_predictions_confidence",
        ),
        CheckConstraint(
            "status in ('shown', 'opened', 'helpful', 'not_helpful', 'remind_later', 'dismissed', "
            "'acted_on', 'proven_correct', 'proven_wrong')",
            name="ck_predictive_coo_predictions_status",
        ),
        Index("ix_predictive_coo_predictions_type", "prediction_type"),
        Index("ix_predictive_coo_predictions_status", "status"),
        Index("ix_predictive_coo_predictions_created_at", "created_at"),
        Index("ix_predictive_coo_predictions_evidence_key", "evidence_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_title: Mapped[str] = mapped_column(String(220), nullable=False)
    prediction_type: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    recommended_next_action: Mapped[str] = mapped_column(Text(), nullable=False)
    can_wait: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="shown", nullable=False)
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_on_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_key: Mapped[str] = mapped_column(String(220), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
