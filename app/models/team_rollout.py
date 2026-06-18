from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

NOTIFICATION_DIGEST_STATUSES = ("open", "sent", "archived")
NOTIFICATION_DIGEST_PRIORITIES = ("low", "normal", "critical")
SETUP_WIZARD_STATUSES = ("started", "in_progress", "completed", "abandoned")


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


class SetupWizardState(TimestampMixin, Base):
    __tablename__ = "setup_wizard_states"
    __table_args__ = (
        CheckConstraint(
            "status in ('started', 'in_progress', 'completed', 'abandoned')",
            name="ck_setup_wizard_states_status",
        ),
        Index("ix_setup_wizard_states_owner_user_id", "owner_user_id"),
        Index("ix_setup_wizard_states_model_brand_id", "model_brand_id"),
        Index("ix_setup_wizard_states_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    model_brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(40), default="started", nullable=False)
    current_step: Mapped[str] = mapped_column(String(80), default="model", nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    missing_items_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship("User", lazy="selectin")
    model_brand: Mapped["ModelBrand | None"] = relationship("ModelBrand", lazy="selectin")


class FirstDayChecklist(TimestampMixin, Base):
    __tablename__ = "first_day_checklists"
    __table_args__ = (
        CheckConstraint(
            "completion_score >= 0 and completion_score <= 100",
            name="ck_first_day_checklists_completion_score",
        ),
        Index("ix_first_day_checklists_user_id", "user_id", unique=True),
        Index("ix_first_day_checklists_completion_score", "completion_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_first_model: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_accounts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_manager: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_team: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_creators: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_opportunities: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_opportunities: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generated_briefing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_activation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checked_production: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completion_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped["User"] = relationship("User", lazy="selectin")


class AgencyActivationState(Base):
    __tablename__ = "agency_activation_states"
    __table_args__ = (
        CheckConstraint("readiness_score >= 0 and readiness_score <= 100", name="ck_agency_activation_readiness_score"),
        CheckConstraint("models_ready >= 0 and models_ready <= 100", name="ck_agency_activation_models_ready"),
        CheckConstraint("accounts_ready >= 0 and accounts_ready <= 100", name="ck_agency_activation_accounts_ready"),
        CheckConstraint("teams_ready >= 0 and teams_ready <= 100", name="ck_agency_activation_teams_ready"),
        CheckConstraint("creators_ready >= 0 and creators_ready <= 100", name="ck_agency_activation_creators_ready"),
        CheckConstraint(
            "opportunities_ready >= 0 and opportunities_ready <= 100",
            name="ck_agency_activation_opportunities_ready",
        ),
        CheckConstraint(
            "notifications_ready >= 0 and notifications_ready <= 100",
            name="ck_agency_activation_notifications_ready",
        ),
        Index("ix_agency_activation_states_updated_at", "updated_at"),
        Index("ix_agency_activation_states_readiness_score", "readiness_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    models_ready: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accounts_ready: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    teams_ready: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    creators_ready: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opportunities_ready: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notifications_ready: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    readiness_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blockers_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommendations_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ActivationBlockerDecision(TimestampMixin, Base):
    __tablename__ = "activation_blocker_decisions"
    __table_args__ = (
        CheckConstraint(
            "status in ('skipped', 'not_needed')",
            name="ck_activation_blocker_decisions_status",
        ),
        UniqueConstraint(
            "blocker_code",
            "entity_type",
            "entity_id",
            name="uq_activation_blocker_decisions_key",
        ),
        Index("ix_activation_blocker_decisions_status", "status"),
        Index("ix_activation_blocker_decisions_blocker_code", "blocker_code"),
        Index("ix_activation_blocker_decisions_decided_by", "decided_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    blocker_code: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    decided_by: Mapped["User | None"] = relationship("User", lazy="selectin")


class DailyAutopilotSetting(TimestampMixin, Base):
    __tablename__ = "daily_autopilot_settings"
    __table_args__ = (
        Index("ix_daily_autopilot_settings_owner_user_id", "owner_user_id", unique=True),
        Index("ix_daily_autopilot_settings_is_enabled", "is_enabled"),
        Index("ix_daily_autopilot_settings_next_run_at", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    run_time_local: Mapped[str] = mapped_column(String(10), default="09:00", nullable=False)
    included_actions_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str | None] = mapped_column(String(240), nullable=True)

    owner: Mapped["User | None"] = relationship("User", lazy="selectin")
