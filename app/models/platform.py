from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


PLATFORM_IDENTIFIERS = (
    "instagram",
    "x",
    "onlyfans",
    "telegram",
    "email",
    "backup_storage",
    "system_alerts",
)

PLATFORM_CONNECTION_STATUSES = (
    "not_connected",
    "ready_to_connect",
    "connection_configured",
    "connected",
    "needs_review",
    "failed",
)

PLATFORM_APPROVED_METHODS = (
    "manual",
    "official_api",
    "approved_connector",
    "session_based",
    "not_configured",
)


class PlatformConnection(TimestampMixin, Base):
    __tablename__ = "platform_connections"
    __table_args__ = (
        CheckConstraint(
            "platform in ('instagram', 'x', 'onlyfans', 'telegram', 'email', 'backup_storage', 'system_alerts')",
            name="ck_platform_connections_platform",
        ),
        CheckConstraint(
            "status in ('not_connected', 'ready_to_connect', 'connection_configured', 'connected', 'needs_review', 'failed')",
            name="ck_platform_connections_status",
        ),
        CheckConstraint(
            "approved_method in ('manual', 'official_api', 'approved_connector', 'session_based', 'not_configured')",
            name="ck_platform_connections_approved_method",
        ),
        UniqueConstraint("platform", name="uq_platform_connections_platform"),
        Index("ix_platform_connections_platform", "platform"),
        Index("ix_platform_connections_status", "status"),
        Index("ix_platform_connections_approved_method", "approved_method"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="ready_to_connect", nullable=False)
    website_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    login_connected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stats_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stats_fresh: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notifications_configured: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    approved_method: Mapped[str] = mapped_column(String(40), default="not_configured", nullable=False)
    last_connection_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stats_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notification_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    next_action: Mapped[str | None] = mapped_column(Text(), nullable=True)
