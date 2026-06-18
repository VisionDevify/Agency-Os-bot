from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

PROXY_STATUSES = ("healthy", "warning", "critical", "disabled")
PROXY_ROTATION_STATUSES = ("started", "succeeded", "failed", "rolled_back")
PROXY_HEALTH_CHECK_TYPES = ("simulated", "connectivity", "location", "full")
PROXY_HEALTH_CHECK_STATUSES = ("passed", "failed", "warning", "skipped")


class Proxy(TimestampMixin, Base):
    __tablename__ = "proxies"
    __table_args__ = (
        CheckConstraint(
            "status in ('healthy', 'warning', 'critical', 'disabled')",
            name="ck_proxies_status",
        ),
        CheckConstraint("health_score >= 0 and health_score <= 100", name="ck_proxies_health_score"),
        CheckConstraint("port >= 0 and port <= 65535", name="ck_proxies_port"),
        Index("ix_proxies_provider", "provider"),
        Index("ix_proxies_status", "status"),
        Index("ix_proxies_health_score", "health_score"),
        Index("ix_proxies_target_location", "target_country", "target_state", "target_city"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    base_username: Mapped[str] = mapped_column(String(160), nullable=False)
    session_suffix: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_session_suffix: Mapped[str | None] = mapped_column(String(80), nullable=True)
    encrypted_password: Mapped[str] = mapped_column(Text(), nullable=False)
    generated_username: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="healthy", nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    target_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rotation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_rotation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    connection_test_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    location_mismatch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rotation_success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rotation_failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accounts: Mapped[list["Account"]] = relationship(
        "Account",
        back_populates="assigned_proxy",
        lazy="selectin",
    )
    rotation_history: Mapped[list["ProxyRotationHistory"]] = relationship(
        back_populates="proxy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    health_check_results: Mapped[list["ProxyHealthCheckResult"]] = relationship(
        back_populates="proxy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProxyRotationHistory(Base):
    __tablename__ = "proxy_rotation_history"
    __table_args__ = (
        CheckConstraint(
            "status in ('started', 'succeeded', 'failed', 'rolled_back')",
            name="ck_proxy_rotation_history_status",
        ),
        Index("ix_proxy_rotation_history_proxy_id", "proxy_id"),
        Index("ix_proxy_rotation_history_status", "status"),
        Index("ix_proxy_rotation_history_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_id: Mapped[int] = mapped_column(
        ForeignKey("proxies.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_session_suffix: Mapped[str | None] = mapped_column(String(80), nullable=True)
    new_session_suffix: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    detected_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    proxy: Mapped[Proxy] = relationship(back_populates="rotation_history", lazy="selectin")


class ProxyHealthCheckResult(Base):
    __tablename__ = "proxy_health_check_results"
    __table_args__ = (
        CheckConstraint(
            "check_type in ('simulated', 'connectivity', 'location', 'full')",
            name="ck_proxy_health_check_results_check_type",
        ),
        CheckConstraint(
            "status in ('passed', 'failed', 'warning', 'skipped')",
            name="ck_proxy_health_check_results_status",
        ),
        Index("ix_proxy_health_check_results_proxy_id", "proxy_id"),
        Index("ix_proxy_health_check_results_check_type", "check_type"),
        Index("ix_proxy_health_check_results_status", "status"),
        Index("ix_proxy_health_check_results_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_id: Mapped[int] = mapped_column(
        ForeignKey("proxies.id", ondelete="CASCADE"),
        nullable=False,
    )
    check_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_ip_masked: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detected_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_match: Mapped[bool | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    proxy: Mapped[Proxy] = relationship(back_populates="health_check_results", lazy="selectin")
