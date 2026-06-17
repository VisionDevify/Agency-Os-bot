from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

NOTIFICATION_DIGEST_STATUSES = ("open", "sent", "archived")
NOTIFICATION_DIGEST_PRIORITIES = ("low", "normal", "critical")


class TeamOnboardingChecklist(TimestampMixin, Base):
    __tablename__ = "team_onboarding_checklists"
    __table_args__ = (
        CheckConstraint(
            "readiness_score >= 0 and readiness_score <= 100",
            name="ck_team_onboarding_checklists_readiness_score",
        ),
        Index("ix_team_onboarding_checklists_user_id", "user_id", unique=True),
        Index("ix_team_onboarding_checklists_readiness_score", "readiness_score"),
        Index("ix_team_onboarding_checklists_onboarded", "onboarded"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role_assigned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timezone_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    availability_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    help_center_viewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    readiness_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="selectin")
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id], lazy="selectin")


class NotificationDigest(TimestampMixin, Base):
    __tablename__ = "notification_digests"
    __table_args__ = (
        CheckConstraint(
            "status in ('open', 'sent', 'archived')",
            name="ck_notification_digests_status",
        ),
        CheckConstraint(
            "priority in ('low', 'normal', 'critical')",
            name="ck_notification_digests_priority",
        ),
        Index("ix_notification_digests_user_id", "user_id"),
        Index("ix_notification_digests_purpose", "purpose"),
        Index("ix_notification_digests_status", "status"),
        Index("ix_notification_digests_priority", "priority"),
        Index("ix_notification_digests_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(80), default="operations", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    priority: Mapped[str] = mapped_column(String(40), default="low", nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    items_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User | None"] = relationship("User", lazy="selectin")

