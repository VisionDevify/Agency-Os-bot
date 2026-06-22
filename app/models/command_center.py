from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


SCORE_CONFIDENCE_LEVELS = ("low", "medium", "high")
SCORE_MOVEMENTS = ("up", "down", "flat")


class ScoreSnapshot(TimestampMixin, Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (
        CheckConstraint("score_percent >= 0 and score_percent <= 100", name="ck_score_snapshots_percent"),
        CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_score_snapshots_confidence"),
        CheckConstraint("movement in ('up', 'down', 'flat')", name="ck_score_snapshots_movement"),
        Index("ix_score_snapshots_name", "score_name"),
        Index("ix_score_snapshots_generated_at", "generated_at"),
        Index("ix_score_snapshots_evidence_version", "evidence_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    score_name: Mapped[str] = mapped_column(String(80), nullable=False)
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    movement: Mapped[str] = mapped_column(String(20), default="flat", nullable=False)
    movement_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delta_period: Mapped[str] = mapped_column(String(20), default="week", nullable=False)
    reason_for_change: Mapped[str] = mapped_column(Text(), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(160), nullable=False)
    score_breakdown: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
