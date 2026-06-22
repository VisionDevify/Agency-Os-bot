from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


AGENCY_PLAN_STATUSES = ("active", "paused", "completed", "cancelled")
AGENCY_PLAN_CONFIDENCE = ("low", "medium", "high")
AGENCY_DRIFT_SEVERITIES = ("low", "medium", "high")
AGENCY_DRIFT_STATUSES = ("active", "needs_review", "resolved", "historical", "reappeared")


class AgencyPlan(TimestampMixin, Base):
    __tablename__ = "agency_plans"
    __table_args__ = (
        CheckConstraint("status in ('active', 'paused', 'completed', 'cancelled')", name="ck_agency_plans_status"),
        CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_agency_plans_confidence"),
        Index("ix_agency_plans_domain", "domain"),
        Index("ix_agency_plans_status", "status"),
        Index("ix_agency_plans_start_at", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_role: Mapped[str] = mapped_column(String(60), default="owner", nullable=False)
    expected_cadence: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_signal: Mapped[str] = mapped_column(String(180), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgencyExpectation(TimestampMixin, Base):
    __tablename__ = "agency_expectations"
    __table_args__ = (
        CheckConstraint("status in ('active', 'paused', 'completed', 'cancelled')", name="ck_agency_expectations_status"),
        CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_agency_expectations_confidence"),
        Index("ix_agency_expectations_plan_id", "plan_id"),
        Index("ix_agency_expectations_domain", "domain"),
        Index("ix_agency_expectations_status", "status"),
        Index("ix_agency_expectations_next_check_at", "next_check_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("agency_plans.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_cadence: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_signal: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgencyDriftFinding(TimestampMixin, Base):
    __tablename__ = "agency_drift_findings"
    __table_args__ = (
        CheckConstraint("severity in ('low', 'medium', 'high')", name="ck_agency_drift_findings_severity"),
        CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_agency_drift_findings_confidence"),
        CheckConstraint(
            "status in ('active', 'needs_review', 'resolved', 'historical', 'reappeared')",
            name="ck_agency_drift_findings_status",
        ),
        Index("ix_agency_drift_findings_plan_id", "plan_id"),
        Index("ix_agency_drift_findings_domain", "domain"),
        Index("ix_agency_drift_findings_status", "status"),
        Index("ix_agency_drift_findings_severity", "severity"),
        Index("ix_agency_drift_findings_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("agency_plans.id"), nullable=True)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    expected: Mapped[str] = mapped_column(Text(), nullable=False)
    observed: Mapped[str] = mapped_column(Text(), nullable=False)
    gap: Mapped[str] = mapped_column(Text(), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    next_best_move: Mapped[str] = mapped_column(Text(), nullable=False)
    evidence_records: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
