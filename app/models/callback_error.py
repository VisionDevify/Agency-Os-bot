from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CallbackErrorLog(TimestampMixin, Base):
    __tablename__ = "callback_error_logs"
    __table_args__ = (
        Index("ix_callback_error_logs_created_at", "created_at"),
        Index("ix_callback_error_logs_page", "page"),
        Index("ix_callback_error_logs_exception_type", "exception_type"),
        Index("ix_callback_error_logs_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    callback_data: Mapped[str | None] = mapped_column(String(260), nullable=True)
    page: Mapped[str | None] = mapped_column(String(220), nullable=True)
    affected_screen: Mapped[str | None] = mapped_column(String(220), nullable=True)
    exception_type: Mapped[str] = mapped_column(String(120), nullable=False)
    error_message: Mapped[str] = mapped_column(Text(), nullable=False)
