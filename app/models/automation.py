from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

AUTOMATION_CATEGORIES = (
    "infrastructure",
    "operations",
    "notifications",
    "reports",
    "intelligence",
    "opportunities",
    "system",
)
AUTOMATION_RULE_STATUSES = (
    "draft",
    "simulated",
    "pending_approval",
    "approved",
    "active",
    "paused",
    "retired",
    "failed",
    # Legacy statuses kept readable for existing production rows.
    "disabled",
    "archived",
)
AUTOMATION_SIMULATION_STATUSES = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "expired",
    # Legacy review statuses kept for Sprint 9/10 compatibility.
    "draft",
    "simulated",
    "approved",
    "rejected",
)
AUTOMATION_RISK_LEVELS = ("low", "medium", "high", "critical")
AUTOMATION_RUN_STATUSES = ("pending", "running", "succeeded", "failed", "skipped", "rolled_back")
AUTOMATION_STEP_STATUSES = ("pending", "running", "succeeded", "failed", "skipped", "rolled_back")
AUTOMATION_ROLLBACK_STATUSES = ("not_needed", "available", "completed", "failed")
AUTOMATION_APPROVAL_STATUSES = ("pending", "approved", "rejected", "expired")
AUTOMATION_SCHEDULE_TYPES = ("manual", "hourly", "daily", "weekly", "event_based")


class AutomationRule(TimestampMixin, Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        CheckConstraint(
            "category in ('infrastructure', 'operations', 'notifications', 'reports', "
            "'intelligence', 'opportunities', 'system')",
            name="ck_automation_rules_category",
        ),
        CheckConstraint(
            "status in ('draft', 'simulated', 'pending_approval', 'approved', 'active', "
            "'paused', 'retired', 'failed', 'disabled', 'archived')",
            name="ck_automation_rules_status",
        ),
        CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_automation_rules_risk_level",
        ),
        Index("ix_automation_rules_name", "name"),
        Index("ix_automation_rules_category", "category"),
        Index("ix_automation_rules_automation_type", "automation_type"),
        Index("ix_automation_rules_status", "status"),
        Index("ix_automation_rules_trigger_type", "trigger_type"),
        Index("ix_automation_rules_risk_level", "risk_level"),
        Index("ix_automation_rules_created_by_user_id", "created_by_user_id"),
        Index("ix_automation_rules_approved_by_user_id", "approved_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    category: Mapped[str] = mapped_column(String(40), default="system", nullable=False)
    # Kept as a stable slug for older screens/tests and migration compatibility.
    automation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(120), default="manual", nullable=False)
    trigger_config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    conditions_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    actions_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rollback_plan_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), default="low", nullable=False)
    requires_owner_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_simulated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id], lazy="selectin")
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_user_id], lazy="selectin")
    simulations: Mapped[list["AutomationSimulationRun"]] = relationship(back_populates="rule", lazy="selectin")
    runs: Mapped[list["AutomationRun"]] = relationship(back_populates="rule", lazy="selectin")
    approvals: Mapped[list["AutomationApproval"]] = relationship(back_populates="rule", lazy="selectin")
    schedules: Mapped[list["AutomationSchedule"]] = relationship(back_populates="rule", lazy="selectin")


class AutomationSimulationRun(Base):
    __tablename__ = "automation_simulation_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'expired', "
            "'draft', 'simulated', 'approved', 'rejected')",
            name="ck_automation_simulation_runs_status",
        ),
        CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_automation_simulation_runs_risk_level",
        ),
        Index("ix_automation_simulation_runs_rule_id", "automation_rule_id"),
        Index("ix_automation_simulation_runs_automation_type", "automation_type"),
        Index("ix_automation_simulation_runs_status", "status"),
        Index("ix_automation_simulation_runs_risk_level", "risk_level"),
        Index("ix_automation_simulation_runs_simulated_by_user_id", "simulated_by_user_id"),
        Index("ix_automation_simulation_runs_created_at", "created_at"),
        Index("ix_automation_simulation_runs_finished_at", "finished_at"),
        Index("ix_automation_simulation_runs_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    automation_name: Mapped[str] = mapped_column(String(160), nullable=False)
    automation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="succeeded", nullable=False)
    simulated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_scope: Mapped[str] = mapped_column(String(160), nullable=False)
    would_trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    would_succeed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    would_fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    affected_entities_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    impact_summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), default="low", nullable=False)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    rule: Mapped[AutomationRule | None] = relationship(back_populates="simulations", lazy="selectin")
    simulated_by: Mapped["User"] = relationship("User", lazy="selectin")


class AutomationRun(TimestampMixin, Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped', 'rolled_back')",
            name="ck_automation_runs_status",
        ),
        CheckConstraint(
            "rollback_status in ('not_needed', 'available', 'completed', 'failed')",
            name="ck_automation_runs_rollback_status",
        ),
        Index("ix_automation_runs_rule_id", "automation_rule_id"),
        Index("ix_automation_runs_status", "status"),
        Index("ix_automation_runs_started_by_user_id", "started_by_user_id"),
        Index("ix_automation_runs_started_at", "started_at"),
        Index("ix_automation_runs_finished_at", "finished_at"),
        Index("ix_automation_runs_trigger_event_id", "trigger_event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_rule_id: Mapped[int] = mapped_column(ForeignKey("automation_rules.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_event_id: Mapped[int | None] = mapped_column(ForeignKey("event_logs.id"), nullable=True)
    affected_entities_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    result_summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    rollback_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rollback_status: Mapped[str] = mapped_column(String(40), default="not_needed", nullable=False)

    rule: Mapped[AutomationRule] = relationship(back_populates="runs", lazy="selectin")
    started_by: Mapped["User | None"] = relationship("User", lazy="selectin")
    steps: Mapped[list["AutomationRunStep"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AutomationRunStep(Base):
    __tablename__ = "automation_run_steps"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped', 'rolled_back')",
            name="ck_automation_run_steps_status",
        ),
        Index("ix_automation_run_steps_run_id", "automation_run_id"),
        Index("ix_automation_run_steps_action_type", "action_type"),
        Index("ix_automation_run_steps_status", "status"),
        Index("ix_automation_run_steps_entity", "entity_type", "entity_id"),
        Index("ix_automation_run_steps_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_run_id: Mapped[int] = mapped_column(
        ForeignKey("automation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[AutomationRun] = relationship(back_populates="steps", lazy="selectin")


class AutomationApproval(Base):
    __tablename__ = "automation_approvals"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'expired')",
            name="ck_automation_approvals_status",
        ),
        Index("ix_automation_approvals_rule_id", "automation_rule_id"),
        Index("ix_automation_approvals_requested_by_user_id", "requested_by_user_id"),
        Index("ix_automation_approvals_approved_by_user_id", "approved_by_user_id"),
        Index("ix_automation_approvals_status", "status"),
        Index("ix_automation_approvals_created_at", "created_at"),
        Index("ix_automation_approvals_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_rule_id: Mapped[int] = mapped_column(ForeignKey("automation_rules.id"), nullable=False)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    approval_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rule: Mapped[AutomationRule] = relationship(back_populates="approvals", lazy="selectin")
    requested_by: Mapped["User"] = relationship("User", foreign_keys=[requested_by_user_id], lazy="selectin")
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_user_id], lazy="selectin")


class AutomationSchedule(TimestampMixin, Base):
    __tablename__ = "automation_schedules"
    __table_args__ = (
        CheckConstraint(
            "schedule_type in ('manual', 'hourly', 'daily', 'weekly', 'event_based')",
            name="ck_automation_schedules_type",
        ),
        Index("ix_automation_schedules_rule_id", "automation_rule_id"),
        Index("ix_automation_schedules_type", "schedule_type"),
        Index("ix_automation_schedules_is_active", "is_active"),
        Index("ix_automation_schedules_next_run_at", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_rule_id: Mapped[int] = mapped_column(ForeignKey("automation_rules.id"), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    time_of_day_local: Mapped[str | None] = mapped_column(String(10), nullable=True)
    day_of_week: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rule: Mapped[AutomationRule] = relationship(back_populates="schedules", lazy="selectin")
