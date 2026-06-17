from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

LEARNING_SOURCE_TYPES = (
    "task",
    "incident",
    "proxy",
    "account",
    "automation",
    "recommendation",
    "opportunity",
    "notification",
    "system",
)
LEARNING_OUTCOMES = ("success", "failure", "partial", "ignored", "unknown")
LEARNING_SEVERITIES = ("info", "warning", "critical")
PLAYBOOK_CATEGORIES = (
    "proxy",
    "account",
    "task",
    "incident",
    "automation",
    "notification",
    "opportunity",
    "system",
)
PLAYBOOK_RISK_LEVELS = ("low", "medium", "high", "critical")
PLAYBOOK_STATUSES = ("draft", "active", "needs_review", "retired")
PLAYBOOK_RUN_STATUSES = ("suggested", "approved", "running", "succeeded", "failed", "skipped", "rolled_back")
OUTCOME_MEMORY_TYPES = (
    "proxy_failure",
    "account_issue",
    "incident_pattern",
    "automation_result",
    "recommendation_result",
    "opportunity_result",
    "notification_failure",
    "task_overdue",
    "system_health",
)
CONFIDENCE_SUBJECT_TYPES = (
    "recommendation",
    "playbook",
    "automation",
    "proxy",
    "opportunity",
    "intelligence_signal",
    "issue_pattern",
)


class LearningEvent(Base):
    __tablename__ = "learning_events"
    __table_args__ = (
        CheckConstraint(
            "source_type in ('task', 'incident', 'proxy', 'account', 'automation', 'recommendation', "
            "'opportunity', 'notification', 'system')",
            name="ck_learning_events_source_type",
        ),
        CheckConstraint(
            "outcome in ('success', 'failure', 'partial', 'ignored', 'unknown')",
            name="ck_learning_events_outcome",
        ),
        CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_learning_events_severity",
        ),
        CheckConstraint(
            "confidence_score is null or (confidence_score >= 0 and confidence_score <= 100)",
            name="ck_learning_events_confidence",
        ),
        Index("ix_learning_events_type", "event_type"),
        Index("ix_learning_events_source", "source_type", "source_id"),
        Index("ix_learning_events_entity", "entity_type", "entity_id"),
        Index("ix_learning_events_outcome", "outcome"),
        Index("ix_learning_events_severity", "severity"),
        Index("ix_learning_events_created_by_user_id", "created_by_user_id"),
        Index("ix_learning_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    created_by: Mapped["User | None"] = relationship("User", lazy="selectin")


class Playbook(TimestampMixin, Base):
    __tablename__ = "playbooks"
    __table_args__ = (
        CheckConstraint(
            "category in ('proxy', 'account', 'task', 'incident', 'automation', 'notification', 'opportunity', 'system')",
            name="ck_playbooks_category",
        ),
        CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_playbooks_risk_level",
        ),
        CheckConstraint(
            "status in ('draft', 'active', 'needs_review', 'retired')",
            name="ck_playbooks_status",
        ),
        CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 100",
            name="ck_playbooks_confidence",
        ),
        CheckConstraint("success_count >= 0", name="ck_playbooks_success_count"),
        CheckConstraint("failure_count >= 0", name="ck_playbooks_failure_count"),
        UniqueConstraint("name", name="uq_playbooks_name"),
        Index("ix_playbooks_category", "category"),
        Index("ix_playbooks_risk_level", "risk_level"),
        Index("ix_playbooks_status", "status"),
        Index("ix_playbooks_confidence", "confidence_score"),
        Index("ix_playbooks_created_by_user_id", "created_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    diagnosis_steps_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resolution_steps_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    verification_steps_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rollback_steps_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(40), default="low", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_by: Mapped["User | None"] = relationship("User", lazy="selectin")
    runs: Mapped[list["PlaybookRun"]] = relationship(back_populates="playbook", lazy="selectin")


class PlaybookRun(Base):
    __tablename__ = "playbook_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('suggested', 'approved', 'running', 'succeeded', 'failed', 'skipped', 'rolled_back')",
            name="ck_playbook_runs_status",
        ),
        CheckConstraint(
            "confidence_before is null or (confidence_before >= 0 and confidence_before <= 100)",
            name="ck_playbook_runs_confidence_before",
        ),
        CheckConstraint(
            "confidence_after is null or (confidence_after >= 0 and confidence_after <= 100)",
            name="ck_playbook_runs_confidence_after",
        ),
        Index("ix_playbook_runs_playbook_id", "playbook_id"),
        Index("ix_playbook_runs_source", "source_type", "source_id"),
        Index("ix_playbook_runs_status", "status"),
        Index("ix_playbook_runs_started_by_user_id", "started_by_user_id"),
        Index("ix_playbook_runs_approved_by_user_id", "approved_by_user_id"),
        Index("ix_playbook_runs_created_at", "created_at"),
        Index("ix_playbook_runs_finished_at", "finished_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    playbook_id: Mapped[int] = mapped_column(ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="suggested", nullable=False)
    started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confidence_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    safe_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    playbook: Mapped[Playbook] = relationship(back_populates="runs", lazy="selectin")
    started_by: Mapped["User | None"] = relationship("User", foreign_keys=[started_by_user_id], lazy="selectin")
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_user_id], lazy="selectin")


class OutcomeMemory(TimestampMixin, Base):
    __tablename__ = "outcome_memory"
    __table_args__ = (
        CheckConstraint(
            "memory_type in ('proxy_failure', 'account_issue', 'incident_pattern', 'automation_result', "
            "'recommendation_result', 'opportunity_result', 'notification_failure', 'task_overdue', 'system_health')",
            name="ck_outcome_memory_type",
        ),
        CheckConstraint(
            "last_outcome in ('success', 'failure', 'partial', 'ignored', 'unknown')",
            name="ck_outcome_memory_last_outcome",
        ),
        CheckConstraint("occurrences >= 0", name="ck_outcome_memory_occurrences"),
        CheckConstraint("success_count >= 0", name="ck_outcome_memory_success_count"),
        CheckConstraint("failure_count >= 0", name="ck_outcome_memory_failure_count"),
        CheckConstraint("partial_count >= 0", name="ck_outcome_memory_partial_count"),
        CheckConstraint("ignored_count >= 0", name="ck_outcome_memory_ignored_count"),
        CheckConstraint("success_rate >= 0 and success_rate <= 100", name="ck_outcome_memory_success_rate"),
        UniqueConstraint("memory_key", name="uq_outcome_memory_key"),
        Index("ix_outcome_memory_type", "memory_type"),
        Index("ix_outcome_memory_entity", "entity_type", "entity_id"),
        Index("ix_outcome_memory_last_outcome", "last_outcome"),
        Index("ix_outcome_memory_success_rate", "success_rate"),
        Index("ix_outcome_memory_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    memory_key: Mapped[str] = mapped_column(String(240), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ignored_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_outcome: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ConfidenceRecord(Base):
    __tablename__ = "confidence_records"
    __table_args__ = (
        CheckConstraint(
            "subject_type in ('recommendation', 'playbook', 'automation', 'proxy', 'opportunity', "
            "'intelligence_signal', 'issue_pattern')",
            name="ck_confidence_records_subject_type",
        ),
        CheckConstraint(
            "previous_score is null or (previous_score >= 0 and previous_score <= 100)",
            name="ck_confidence_records_previous_score",
        ),
        CheckConstraint("new_score >= 0 and new_score <= 100", name="ck_confidence_records_new_score"),
        Index("ix_confidence_records_subject", "subject_type", "subject_id"),
        Index("ix_confidence_records_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(120), nullable=False)
    previous_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
