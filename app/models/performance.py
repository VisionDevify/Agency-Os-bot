from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class TeamPerformanceSnapshot(TimestampMixin, Base):
    __tablename__ = "team_performance_snapshots"
    __table_args__ = (
        CheckConstraint("workload_score >= 0 and workload_score <= 100", name="ck_team_performance_workload"),
        CheckConstraint("reliability_score >= 0 and reliability_score <= 100", name="ck_team_performance_reliability"),
        Index("ix_team_performance_user_id", "user_id"),
        Index("ix_team_performance_role", "role"),
        Index("ix_team_performance_period", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_overdue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opportunities_reviewed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opportunities_successful: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_response_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workload_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reliability_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
