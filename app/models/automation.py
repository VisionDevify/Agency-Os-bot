from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

AUTOMATION_RULE_STATUSES = ("draft", "active", "disabled", "archived")
AUTOMATION_SIMULATION_STATUSES = ("draft", "simulated", "approved", "rejected", "expired")
AUTOMATION_RISK_LEVELS = ("low", "medium", "high", "critical")


class AutomationRule(TimestampMixin, Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'active', 'disabled', 'archived')",
            name="ck_automation_rules_status",
        ),
        Index("ix_automation_rules_name", "name"),
        Index("ix_automation_rules_automation_type", "automation_type"),
        Index("ix_automation_rules_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    automation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AutomationSimulationRun(Base):
    __tablename__ = "automation_simulation_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'simulated', 'approved', 'rejected', 'expired')",
            name="ck_automation_simulation_runs_status",
        ),
        CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_automation_simulation_runs_risk_level",
        ),
        Index("ix_automation_simulation_runs_automation_type", "automation_type"),
        Index("ix_automation_simulation_runs_status", "status"),
        Index("ix_automation_simulation_runs_risk_level", "risk_level"),
        Index("ix_automation_simulation_runs_simulated_by_user_id", "simulated_by_user_id"),
        Index("ix_automation_simulation_runs_created_at", "created_at"),
        Index("ix_automation_simulation_runs_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_name: Mapped[str] = mapped_column(String(160), nullable=False)
    automation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="simulated", nullable=False)
    simulated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_scope: Mapped[str] = mapped_column(String(160), nullable=False)
    would_trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    would_succeed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    would_fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), default="low", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
