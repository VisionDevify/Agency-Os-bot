from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

NOTIFICATION_TARGET_TYPES = ("telegram_user", "telegram_group", "telegram_channel")
NOTIFICATION_TARGET_PURPOSES = ("owner", "operations", "incidents", "automation_logs", "testing")


class DailyBriefing(Base):
    __tablename__ = "daily_briefings"
    __table_args__ = (
        Index("ix_daily_briefings_briefing_date", "briefing_date"),
        Index("ix_daily_briefings_generated_by_user_id", "generated_by_user_id"),
        Index("ix_daily_briefings_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    briefing_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agency_health_score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text(), nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    recommendations_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AccountabilitySnapshot(Base):
    __tablename__ = "accountability_snapshots"
    __table_args__ = (
        Index("ix_accountability_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_accountability_snapshots_user_id", "user_id"),
        Index("ix_accountability_snapshots_date_user", "snapshot_date", "user_id"),
        Index("ix_accountability_snapshots_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    roles_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    assigned_open_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_tasks_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overdue_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assigned_open_incidents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_incidents_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class NotificationTarget(TimestampMixin, Base):
    __tablename__ = "notification_targets"
    __table_args__ = (
        CheckConstraint(
            "target_type in ('telegram_user', 'telegram_group', 'telegram_channel')",
            name="ck_notification_targets_target_type",
        ),
        CheckConstraint(
            "purpose in ('owner', 'operations', 'incidents', 'automation_logs', 'testing')",
            name="ck_notification_targets_purpose",
        ),
        Index("ix_notification_targets_name", "name"),
        Index("ix_notification_targets_target_type", "target_type"),
        Index("ix_notification_targets_purpose", "purpose"),
        Index("ix_notification_targets_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
