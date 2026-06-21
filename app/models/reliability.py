from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


CALLBACK_LATENCY_RESULTS = (
    "succeeded",
    "fallback_used",
    "failed_safe",
    "timed_out",
    "stale",
    "duplicate",
)
CALLBACK_LATENCY_LABELS = ("excellent", "good", "slow", "bad", "dead")
RELIABILITY_JOB_STATES = (
    "queued",
    "running",
    "checking",
    "uploading",
    "verifying",
    "summarizing",
    "completed",
    "failed",
    "timed_out",
    "cancelled",
)


class CallbackLatencyRecord(TimestampMixin, Base):
    __tablename__ = "callback_latency_records"
    __table_args__ = (
        CheckConstraint(
            "result in ('succeeded', 'fallback_used', 'failed_safe', 'timed_out', 'stale', 'duplicate')",
            name="ck_callback_latency_records_result",
        ),
        CheckConstraint(
            "latency_label in ('excellent', 'good', 'slow', 'bad', 'dead')",
            name="ck_callback_latency_records_label",
        ),
        Index("ix_callback_latency_records_route", "callback_route"),
        Index("ix_callback_latency_records_result", "result"),
        Index("ix_callback_latency_records_label", "latency_label"),
        Index("ix_callback_latency_records_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    callback_route: Mapped[str] = mapped_column(String(220), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    render_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    render_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edit_or_send_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ack_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    render_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    search_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    latency_label: Mapped[str] = mapped_column(String(20), nullable=False)
    safe_error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ReliabilityJob(TimestampMixin, Base):
    __tablename__ = "reliability_jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'running', 'checking', 'uploading', 'verifying', 'summarizing', "
            "'completed', 'failed', 'timed_out', 'cancelled')",
            name="ck_reliability_jobs_status",
        ),
        CheckConstraint(
            "progress_percent is null or (progress_percent >= 0 and progress_percent <= 100)",
            name="ck_reliability_jobs_progress",
        ),
        Index("ix_reliability_jobs_job_id", "job_id", unique=True),
        Index("ix_reliability_jobs_type", "job_type"),
        Index("ix_reliability_jobs_status", "status"),
        Index("ix_reliability_jobs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_step: Mapped[str] = mapped_column(String(160), default="Queued", nullable=False)
    related_chat_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    related_message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    safe_error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ResponseCacheEntry(TimestampMixin, Base):
    __tablename__ = "response_cache_entries"
    __table_args__ = (
        Index("ix_response_cache_entries_key", "cache_key", unique=True),
        Index("ix_response_cache_entries_expires", "expires_at"),
        Index("ix_response_cache_entries_source_commit", "source_commit"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    evidence_version: Mapped[str] = mapped_column(String(120), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_commit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    safe_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    contains_sensitive_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
