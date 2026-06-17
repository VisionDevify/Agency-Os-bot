from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

INTELLIGENCE_SEVERITIES = ("info", "warning", "critical")
INTELLIGENCE_SIGNAL_STATUSES = ("open", "acknowledged", "resolved", "dismissed")
ISSUE_PATTERN_STATUSES = ("active", "acknowledged", "resolved", "dismissed")
TREND_WINDOWS = ("daily", "weekly", "monthly")
TREND_DIRECTIONS = ("up", "down", "flat", "volatile")
OVERLOAD_STATUSES = ("normal", "elevated", "overloaded", "critical")
INTELLIGENCE_RUN_TYPES = (
    "pattern_detection",
    "trend_analysis",
    "workload_analysis",
    "recommendation_generation",
    "executive_briefing",
    "opportunity_scoring",
)
INTELLIGENCE_RUN_STATUSES = ("pending", "running", "succeeded", "failed")


class IntelligenceSignal(TimestampMixin, Base):
    __tablename__ = "intelligence_signals"
    __table_args__ = (
        CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_intelligence_signals_severity",
        ),
        CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 100",
            name="ck_intelligence_signals_confidence",
        ),
        CheckConstraint(
            "occurrence_count >= 0",
            name="ck_intelligence_signals_occurrence_count",
        ),
        CheckConstraint(
            "status in ('open', 'acknowledged', 'resolved', 'dismissed')",
            name="ck_intelligence_signals_status",
        ),
        Index("ix_intelligence_signals_type", "signal_type"),
        Index("ix_intelligence_signals_severity", "severity"),
        Index("ix_intelligence_signals_entity", "entity_type", "entity_id"),
        Index("ix_intelligence_signals_status", "status"),
        Index("ix_intelligence_signals_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_type: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)


class IssuePattern(TimestampMixin, Base):
    __tablename__ = "issue_patterns"
    __table_args__ = (
        CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_issue_patterns_severity",
        ),
        CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 100",
            name="ck_issue_patterns_confidence",
        ),
        CheckConstraint("occurrence_count >= 0", name="ck_issue_patterns_occurrence_count"),
        CheckConstraint(
            "status in ('active', 'acknowledged', 'resolved', 'dismissed')",
            name="ck_issue_patterns_status",
        ),
        Index("ix_issue_patterns_type", "pattern_type"),
        Index("ix_issue_patterns_severity", "severity"),
        Index("ix_issue_patterns_entity", "entity_type", "entity_id"),
        Index("ix_issue_patterns_status", "status"),
        Index("ix_issue_patterns_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    severity: Mapped[str] = mapped_column(String(40), default="warning", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    related_event_ids_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrendSnapshot(Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (
        CheckConstraint(
            "comparison_window in ('daily', 'weekly', 'monthly')",
            name="ck_trend_snapshots_window",
        ),
        CheckConstraint(
            "trend_direction in ('up', 'down', 'flat', 'volatile')",
            name="ck_trend_snapshots_direction",
        ),
        Index("ix_trend_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_trend_snapshots_metric", "metric_name"),
        Index("ix_trend_snapshots_entity", "entity_type", "entity_id"),
        Index("ix_trend_snapshots_window", "comparison_window"),
        Index("ix_trend_snapshots_direction", "trend_direction"),
        Index("ix_trend_snapshots_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    value_numeric: Mapped[int] = mapped_column(Integer, nullable=False)
    comparison_window: Mapped[str] = mapped_column(String(40), default="daily", nullable=False)
    trend_direction: Mapped[str] = mapped_column(String(40), default="flat", nullable=False)
    percent_change: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WorkloadSnapshot(Base):
    __tablename__ = "workload_snapshots"
    __table_args__ = (
        CheckConstraint(
            "overload_status in ('normal', 'elevated', 'overloaded', 'critical')",
            name="ck_workload_snapshots_overload_status",
        ),
        CheckConstraint("workload_score >= 0", name="ck_workload_snapshots_score"),
        Index("ix_workload_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_workload_snapshots_user_id", "user_id"),
        Index("ix_workload_snapshots_overload_status", "overload_status"),
        Index("ix_workload_snapshots_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    open_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overdue_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_incidents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_incidents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_tasks_24h: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_incidents_24h: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    availability_status: Mapped[str] = mapped_column(String(40), default="off_shift", nullable=False)
    workload_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overload_status: Mapped[str] = mapped_column(String(40), default="normal", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExecutiveInsight(TimestampMixin, Base):
    __tablename__ = "executive_insights"
    __table_args__ = (
        CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_executive_insights_severity",
        ),
        CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 100",
            name="ck_executive_insights_confidence",
        ),
        CheckConstraint(
            "status in ('open', 'acknowledged', 'resolved', 'dismissed')",
            name="ck_executive_insights_status",
        ),
        Index("ix_executive_insights_type", "insight_type"),
        Index("ix_executive_insights_severity", "severity"),
        Index("ix_executive_insights_status", "status"),
        Index("ix_executive_insights_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    insight_type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text(), nullable=False)
    source_signal_ids_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)


class IntelligenceRun(Base):
    __tablename__ = "intelligence_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type in ('pattern_detection', 'trend_analysis', 'workload_analysis', "
            "'recommendation_generation', 'executive_briefing', 'opportunity_scoring')",
            name="ck_intelligence_runs_type",
        ),
        CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed')",
            name="ck_intelligence_runs_status",
        ),
        Index("ix_intelligence_runs_type", "run_type"),
        Index("ix_intelligence_runs_status", "status"),
        Index("ix_intelligence_runs_started_by", "started_by_user_id"),
        Index("ix_intelligence_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
