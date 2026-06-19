from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


BOT_MESSAGE_TYPES = (
    "temporary_navigation",
    "persistent_alert",
    "persistent_report",
    "persistent_approval",
    "persistent_export",
    "error_fallback",
)


class BotChatMessage(TimestampMixin, Base):
    __tablename__ = "bot_chat_messages"
    __table_args__ = (
        CheckConstraint(
            "message_type in ("
            "'temporary_navigation',"
            "'persistent_alert',"
            "'persistent_report',"
            "'persistent_approval',"
            "'persistent_export',"
            "'error_fallback'"
            ")",
            name="ck_bot_chat_messages_type",
        ),
        Index("ix_bot_chat_messages_chat_user", "chat_id", "user_id"),
        Index("ix_bot_chat_messages_type_active", "message_type", "is_active"),
        Index("ix_bot_chat_messages_message", "chat_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_type: Mapped[str] = mapped_column(String(40), nullable=False)
    page: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delete_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delete_error: Mapped[str | None] = mapped_column(String(160), nullable=True)

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
