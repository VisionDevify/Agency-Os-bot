from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

ACCOUNT_PLATFORMS = ("instagram", "x", "onlyfans", "email", "other")
ACCOUNT_STATUSES = ("healthy", "warning", "critical", "disabled", "archived")
ACCOUNT_AUTH_STATUSES = (
    "not_connected",
    "connected",
    "needs_login",
    "needs_2fa",
    "expired",
    "locked",
)
ACCOUNT_AUTH_SESSION_STATUSES = (
    "pending",
    "waiting_for_code",
    "submitted",
    "success",
    "failed",
    "expired",
    "cancelled",
)
ACCOUNT_CODE_TYPES = ("email", "sms", "authenticator", "backup_code")


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "platform in ('instagram', 'x', 'onlyfans', 'email', 'other')",
            name="ck_accounts_platform",
        ),
        CheckConstraint(
            "status in ('healthy', 'warning', 'critical', 'disabled', 'archived')",
            name="ck_accounts_status",
        ),
        CheckConstraint(
            "auth_status in "
            "('not_connected', 'connected', 'needs_login', 'needs_2fa', 'expired', 'locked')",
            name="ck_accounts_auth_status",
        ),
        Index("ix_accounts_model_brand_id", "model_brand_id"),
        Index("ix_accounts_platform", "platform"),
        Index("ix_accounts_status", "status"),
        Index("ix_accounts_auth_status", "auth_status"),
        Index("ix_accounts_username", "username"),
        Index("ix_accounts_is_demo", "is_demo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    platform: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    username: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="healthy", nullable=False)
    auth_status: Mapped[str] = mapped_column(String(40), default="not_connected", nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connected_email_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connected_phone_mask: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assigned_proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxies.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_brand: Mapped["ModelBrand | None"] = relationship("ModelBrand", lazy="selectin")
    assigned_proxy: Mapped["Proxy | None"] = relationship(
        "Proxy",
        back_populates="accounts",
        lazy="selectin",
    )
    auth_sessions: Mapped[list["AccountAuthSession"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AccountAuthSession(TimestampMixin, Base):
    __tablename__ = "account_auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "status in "
            "('pending', 'waiting_for_code', 'submitted', 'success', 'failed', 'expired', 'cancelled')",
            name="ck_account_auth_sessions_status",
        ),
        Index("ix_account_auth_sessions_account_id", "account_id"),
        Index("ix_account_auth_sessions_status", "status"),
        Index("ix_account_auth_sessions_expires_at", "expires_at"),
        Index("ix_account_auth_sessions_requested_by_user_id", "requested_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    handled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account: Mapped[Account] = relationship(back_populates="auth_sessions", lazy="selectin")


class AccountVerificationCode(Base):
    __tablename__ = "account_verification_codes"
    __table_args__ = (
        CheckConstraint(
            "code_type in ('email', 'sms', 'authenticator', 'backup_code')",
            name="ck_account_verification_codes_code_type",
        ),
        Index("ix_account_verification_codes_auth_session_id", "auth_session_id"),
        Index("ix_account_verification_codes_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    auth_session_id: Mapped[int] = mapped_column(
        ForeignKey("account_auth_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    code_type: Mapped[str] = mapped_column(String(40), nullable=False)
    submitted_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
