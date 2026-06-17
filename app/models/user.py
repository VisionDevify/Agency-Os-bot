from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.permissions import Role


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'active', 'disabled', 'denied')",
            name="ck_users_status",
        ),
        CheckConstraint(
            "time_format in ('12h', '24h')",
            name="ck_users_time_format",
        ),
        Index("ix_users_telegram_id", "telegram_id"),
        Index("ix_users_status", "status"),
        Index("ix_users_language", "language"),
        Index("ix_users_country", "country"),
        Index("ix_users_timezone", "timezone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    language: Mapped[str] = mapped_column(String(40), default="English", nullable=False)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    time_format: Mapped[str] = mapped_column(String(8), default="12h", nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )
    availability: Mapped["UserAvailability | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


AVAILABILITY_STATUSES = ("on_shift", "off_shift", "away", "vacation", "unavailable")
SUPPORTED_LANGUAGES = ("English", "Spanish", "Portuguese", "Tagalog / Filipino", "Serbian")
TIME_FORMATS = ("12h", "24h")


class UserAvailability(TimestampMixin, Base):
    __tablename__ = "user_availability"
    __table_args__ = (
        CheckConstraint(
            "status in ('on_shift', 'off_shift', 'away', 'vacation', 'unavailable')",
            name="ck_user_availability_status",
        ),
        Index("ix_user_availability_user_id", "user_id"),
        Index("ix_user_availability_status", "status"),
        Index("ix_user_availability_timezone", "timezone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="off_shift", nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    shift_start_local: Mapped[time | None] = mapped_column(Time(), nullable=True)
    shift_end_local: Mapped[time | None] = mapped_column(Time(), nullable=True)
    quiet_hours_start_local: Mapped[time | None] = mapped_column(Time(), nullable=True)
    quiet_hours_end_local: Mapped[time | None] = mapped_column(Time(), nullable=True)

    user: Mapped[User] = relationship(back_populates="availability")
