from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


AGENCY_AWARENESS_STATUSES = (
    "active",
    "inactive",
    "needs_review",
    "ready_to_connect",
    "not_connected",
    "insufficient_data",
)

AGENCY_AWARENESS_CONFIDENCE = ("low", "medium", "high")

AGENCY_MANUAL_RECORD_TYPES = ("activity", "blocker", "note", "win", "loss", "plan", "update")


class AgencyManualRecord(TimestampMixin, Base):
    __tablename__ = "agency_manual_records"
    __table_args__ = (
        CheckConstraint(
            "record_type in ('activity', 'blocker', 'note', 'win', 'loss', 'plan', 'update')",
            name="ck_agency_manual_records_type",
        ),
        CheckConstraint(
            "confidence in ('low', 'medium', 'high')",
            name="ck_agency_manual_records_confidence",
        ),
        Index("ix_agency_manual_records_domain", "domain_id"),
        Index("ix_agency_manual_records_type", "record_type"),
        Index("ix_agency_manual_records_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[str] = mapped_column(String(80), nullable=False)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    details: Mapped[str | None] = mapped_column(Text(), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgencyAwarenessSnapshot(TimestampMixin, Base):
    __tablename__ = "agency_awareness_snapshots"
    __table_args__ = (
        CheckConstraint(
            "overall_status in ('healthy', 'needs_review', 'needs_attention', 'degraded', 'insufficient_data')",
            name="ck_agency_awareness_snapshots_status",
        ),
        CheckConstraint(
            "visibility_score >= 0 and visibility_score <= 100",
            name="ck_agency_awareness_snapshots_visibility_score",
        ),
        CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 100",
            name="ck_agency_awareness_snapshots_confidence_score",
        ),
        Index("ix_agency_awareness_snapshots_generated_at", "generated_at"),
        Index("ix_agency_awareness_snapshots_status", "overall_status"),
        Index("ix_agency_awareness_snapshots_stale", "stale"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    overall_status: Mapped[str] = mapped_column(String(40), nullable=False)
    active_domains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    inactive_domains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_domains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    not_connected_domains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    domain_records: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    visibility_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    top_focus_area: Mapped[str] = mapped_column(String(160), nullable=False)
    next_best_move: Mapped[str] = mapped_column(Text(), nullable=False)
    snapshot_source: Mapped[str] = mapped_column(String(40), default="live", nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    missing_inputs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    degraded_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
