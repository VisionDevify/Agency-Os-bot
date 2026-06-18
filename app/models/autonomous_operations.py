from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

OPERATIONS_STATUSES = ("pending", "ready", "running", "completed", "blocked", "failed", "skipped")
OPERATIONS_PRIORITIES = ("low", "normal", "high", "urgent")
FOLLOW_UP_STATUSES = ("pending", "completed", "blocked", "failed", "skipped")


class OperationsWorkflow(TimestampMixin, Base):
    __tablename__ = "operations_workflows"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'ready', 'running', 'completed', 'blocked', 'failed', 'skipped')",
            name="ck_operations_workflows_status",
        ),
        Index("ix_operations_workflows_type", "workflow_type"),
        Index("ix_operations_workflows_source", "source_type", "source_id"),
        Index("ix_operations_workflows_status", "status"),
        Index("ix_operations_workflows_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)

    actions: Mapped[list["OperationsAction"]] = relationship(
        "OperationsAction",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class OperationsAction(TimestampMixin, Base):
    __tablename__ = "operations_actions"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'ready', 'running', 'completed', 'blocked', 'failed', 'skipped')",
            name="ck_operations_actions_status",
        ),
        CheckConstraint(
            "priority in ('low', 'normal', 'high', 'urgent')",
            name="ck_operations_actions_priority",
        ),
        Index("ix_operations_actions_workflow_id", "workflow_id"),
        Index("ix_operations_actions_status", "status"),
        Index("ix_operations_actions_priority", "priority"),
        Index("ix_operations_actions_assigned_user_id", "assigned_user_id"),
        Index("ix_operations_actions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("operations_workflows.id", ondelete="CASCADE"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(40), default="normal", nullable=False)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)

    workflow: Mapped[OperationsWorkflow] = relationship("OperationsWorkflow", back_populates="actions", lazy="selectin")
    assigned_user: Mapped["User | None"] = relationship("User", lazy="selectin")


class FollowUp(TimestampMixin, Base):
    __tablename__ = "follow_ups"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'completed', 'blocked', 'failed', 'skipped')",
            name="ck_follow_ups_status",
        ),
        Index("ix_follow_ups_source", "source_type", "source_id"),
        Index("ix_follow_ups_status", "status"),
        Index("ix_follow_ups_due_at", "due_at"),
        Index("ix_follow_ups_assigned_user_id", "assigned_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    assigned_user: Mapped["User | None"] = relationship("User", lazy="selectin")
