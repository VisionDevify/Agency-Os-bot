from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OpportunityPrediction(Base):
    __tablename__ = "opportunity_predictions"
    __table_args__ = (
        CheckConstraint("predicted_quality >= 0 and predicted_quality <= 100", name="ck_opportunity_predictions_quality"),
        CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_opportunity_predictions_confidence"),
        Index("ix_opportunity_predictions_opportunity_id", "opportunity_id"),
        Index("ix_opportunity_predictions_quality", "predicted_quality"),
        Index("ix_opportunity_predictions_chatter", "recommended_chatter_id"),
        Index("ix_opportunity_predictions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    predicted_quality: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    recommended_angle: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recommended_chatter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reasoning_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    risk_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
