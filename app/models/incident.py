from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

INCIDENT_SEVERITIES = ("info", "warning", "critical")
INCIDENT_STATUSES = ("open", "investigating", "resolved", "archived")
INCIDENT_SOURCE_TYPES = ("manual", "account", "proxy", "automation", "system")


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_incidents_severity",
        ),
        CheckConstraint(
            "status in ('open', 'investigating', 'resolved', 'archived')",
            name="ck_incidents_status",
        ),
        CheckConstraint(
            "source_type is null or source_type in "
            "('manual', 'account', 'proxy', 'automation', 'system')",
            name="ck_incidents_source_type",
        ),
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_source", "source_type", "source_id"),
        Index("ix_incidents_assigned_user_id", "assigned_user_id"),
        Index("ix_incidents_model_brand_id", "model_brand_id"),
        Index("ix_incidents_account_id", "account_id"),
        Index("ix_incidents_proxy_id", "proxy_id"),
        Index("ix_incidents_owner_user_id", "owner_user_id"),
        Index("ix_incidents_assigned_to_user_id", "assigned_to_user_id"),
        Index("ix_incidents_created_by_user_id", "created_by_user_id"),
        Index("ix_incidents_escalation_level", "escalation_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="warning", nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    model_brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxies.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    escalation_level: Mapped[int] = mapped_column(default=0, nullable=False)
    escalation_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    last_escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    model_brand: Mapped["ModelBrand | None"] = relationship("ModelBrand", lazy="selectin")
    account: Mapped["Account | None"] = relationship("Account", lazy="selectin")
    proxy: Mapped["Proxy | None"] = relationship("Proxy", lazy="selectin")
    owner: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[owner_user_id],
        lazy="selectin",
    )
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
    resolved_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[resolved_by_user_id],
        lazy="selectin",
    )
    timeline_entries: Mapped[list["IncidentTimeline"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IncidentTimeline(TimestampMixin, Base):
    __tablename__ = "incident_timeline"
    __table_args__ = (
        Index("ix_incident_timeline_incident_id", "incident_id"),
        Index("ix_incident_timeline_actor_user_id", "actor_user_id"),
        Index("ix_incident_timeline_event_type", "event_type"),
        Index("ix_incident_timeline_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(Text(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="timeline_entries")
    actor: Mapped["User | None"] = relationship("User", foreign_keys=[actor_user_id], lazy="selectin")
