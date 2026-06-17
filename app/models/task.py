from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

TASK_STATUSES = ("open", "in_progress", "blocked", "complete", "archived")
TASK_PRIORITIES = ("low", "normal", "high", "urgent")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status in ('open', 'in_progress', 'blocked', 'complete', 'archived')",
            name="ck_tasks_status",
        ),
        CheckConstraint(
            "priority in ('low', 'normal', 'high', 'urgent')",
            name="ck_tasks_priority",
        ),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_priority", "priority"),
        Index("ix_tasks_model_brand_id", "model_brand_id"),
        Index("ix_tasks_account_id", "account_id"),
        Index("ix_tasks_assigned_to_user_id", "assigned_to_user_id"),
        Index("ix_tasks_created_by_user_id", "created_by_user_id"),
        Index("ix_tasks_due_at", "due_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    priority: Mapped[str] = mapped_column(String(40), default="normal", nullable=False)
    model_brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    model_brand: Mapped["ModelBrand | None"] = relationship("ModelBrand", lazy="selectin")
    account: Mapped["Account | None"] = relationship("Account", lazy="selectin")
    assigned_to: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assigned_to_user_id],
        lazy="selectin",
    )
    created_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )
