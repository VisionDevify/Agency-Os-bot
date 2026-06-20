from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


TEMPORARY_NAVIGATION = "temporary_navigation"
TEMPORARY_HELP = "temporary_help"
TEMPORARY_STATUS = "temporary_status"
TEMPORARY_ERROR = "temporary_error"
PERSISTENT_ALERT = "persistent_alert"
PERSISTENT_REPORT = "persistent_report"
PERSISTENT_EXPORT = "persistent_export"
PERSISTENT_APPROVAL = "persistent_approval"
PERSISTENT_INCIDENT = "persistent_incident"
PERSISTENT_DELIVERY = "persistent_delivery"
UNKNOWN_PRESERVE = "unknown_preserve"

MESSAGE_LABELS = (
    "temporary_navigation",
    "temporary_help",
    "temporary_status",
    "temporary_error",
    "persistent_alert",
    "persistent_report",
    "persistent_export",
    "persistent_approval",
    "persistent_incident",
    "persistent_delivery",
    "unknown_preserve",
)
TEMPORARY_MESSAGE_LABELS = tuple(label for label in MESSAGE_LABELS if label.startswith("temporary_"))
PERSISTENT_MESSAGE_LABELS = tuple(label for label in MESSAGE_LABELS if label.startswith("persistent_"))
PRESERVED_MESSAGE_LABELS = PERSISTENT_MESSAGE_LABELS + (UNKNOWN_PRESERVE,)

DELETION_STATUSES = (
    "active",
    "cleanup_started",
    "deleted",
    "already_missing",
    "forbidden",
    "too_old",
    "failed",
    "preserved",
)
TERMINAL_DELETION_STATUSES = ("deleted", "already_missing", "forbidden", "too_old", "failed", "preserved")

CLEANUP_RUN_STATUSES = ("running", "completed", "failed", "reused")


class BotChatMessage(TimestampMixin, Base):
    __tablename__ = "bot_chat_messages"
    __table_args__ = (
        CheckConstraint(
            "message_label in ("
            "'temporary_navigation',"
            "'temporary_help',"
            "'temporary_status',"
            "'temporary_error',"
            "'persistent_alert',"
            "'persistent_report',"
            "'persistent_export',"
            "'persistent_approval',"
            "'persistent_incident',"
            "'persistent_delivery',"
            "'unknown_preserve'"
            ")",
            name="ck_bot_chat_messages_label",
        ),
        CheckConstraint(
            "deletion_status in ("
            "'active',"
            "'cleanup_started',"
            "'deleted',"
            "'already_missing',"
            "'forbidden',"
            "'too_old',"
            "'failed',"
            "'preserved'"
            ")",
            name="ck_bot_chat_messages_deletion_status",
        ),
        Index("ix_bot_chat_messages_chat_user", "chat_id", "user_id"),
        Index("ix_bot_chat_messages_label_cleanup", "message_label", "deletion_status"),
        Index("ix_bot_chat_messages_active_nav", "chat_id", "user_id", "active_navigation"),
        Index("ix_bot_chat_messages_message", "chat_id", "message_id"),
        Index("ix_bot_chat_messages_cleanup_run", "cleanup_run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_label: Mapped[str] = mapped_column(String(40), nullable=False, default=UNKNOWN_PRESERVE)
    screen: Mapped[str | None] = mapped_column(String(160), nullable=True)
    active_navigation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deletion_status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    cleanup_batch_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cleanup_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    navigation_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    user = relationship("User")


class ChatCleanupRun(TimestampMixin, Base):
    __tablename__ = "chat_cleanup_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed', 'reused')",
            name="ck_chat_cleanup_runs_status",
        ),
        Index("ix_chat_cleanup_runs_chat", "chat_id", "started_at"),
        Index("ix_chat_cleanup_runs_run_id", "cleanup_run_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cleanup_run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preserved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_candidates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    remaining_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    concurrency_reuse_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user = relationship("User")


class ChatCleanupPreference(TimestampMixin, Base):
    __tablename__ = "chat_cleanup_preferences"
    __table_args__ = (
        Index("ix_chat_cleanup_preferences_chat_user", "chat_id", "user_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    clean_on_start: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user = relationship("User")
