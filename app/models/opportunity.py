from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

OPPORTUNITY_PLATFORMS = ("x", "instagram", "reddit", "other")
OPPORTUNITY_STATUSES = ("discovered", "reviewing", "approved", "assigned", "completed", "rejected", "archived")
OPPORTUNITY_PRIORITIES = ("low", "normal", "high", "critical")
OPPORTUNITY_SOURCE_TYPES = ("manual", "creator_watch", "own_post")
OPPORTUNITY_RESULT_STATUSES = ("not_posted", "posted", "skipped", "failed", "rejected")
CREATOR_WATCH_PLATFORMS = ("x", "instagram", "other")
CREATOR_WATCH_PRIORITIES = ("low", "normal", "high", "critical")
CREATOR_WATCH_STATUSES = ("active", "disabled", "archived")
POST_WATCH_PLATFORMS = ("x", "instagram", "other")
POST_WATCH_STATUSES = ("recent", "attention_needed", "assigned", "archived")
POST_WATCH_TYPES = ("image", "video", "text", "thread", "story", "reel", "other")
POST_WATCH_ATTENTION_LEVELS = ("monitor", "engage", "urgent")
COMMENT_STRATEGY_ANGLES = (
    "curiosity",
    "question",
    "agreement",
    "relatable",
    "story",
    "authority",
    "contrarian",
    "soft_cta",
    "humor",
    "educational",
    "supportive",
)


class OpportunitySource(TimestampMixin, Base):
    __tablename__ = "opportunity_sources"
    __table_args__ = (
        CheckConstraint(
            "platform in ('x', 'instagram', 'reddit', 'other')",
            name="ck_opportunity_sources_platform",
        ),
        Index("ix_opportunity_sources_platform", "platform"),
        Index("ix_opportunity_sources_name", "name"),
        Index("ix_opportunity_sources_niche", "niche"),
        Index("ix_opportunity_sources_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opportunities: Mapped[list["Opportunity"]] = relationship(
        back_populates="source",
        lazy="selectin",
    )


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "platform in ('x', 'instagram', 'reddit', 'other')",
            name="ck_opportunities_platform",
        ),
        CheckConstraint("score >= 0 and score <= 100", name="ck_opportunities_score"),
        CheckConstraint(
            "status in ('discovered', 'reviewing', 'approved', 'assigned', 'completed', 'rejected', 'archived')",
            name="ck_opportunities_status",
        ),
        CheckConstraint(
            "priority in ('low', 'normal', 'high', 'critical')",
            name="ck_opportunities_priority",
        ),
        CheckConstraint(
            "source_type is null or source_type in ('manual', 'creator_watch', 'own_post')",
            name="ck_opportunities_source_type",
        ),
        Index("ix_opportunities_source_id", "source_id"),
        Index("ix_opportunities_source_ref", "source_type", "source_reference_id"),
        Index("ix_opportunities_platform", "platform"),
        Index("ix_opportunities_model_brand_id", "model_brand_id"),
        Index("ix_opportunities_assigned_to_user_id", "assigned_to_user_id"),
        Index("ix_opportunities_status", "status"),
        Index("ix_opportunities_priority", "priority"),
        Index("ix_opportunities_score", "score"),
        Index("ix_opportunities_niche", "niche"),
        Index("ix_opportunities_due_at", "due_at"),
        Index("ix_opportunities_is_demo", "is_demo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("opportunity_sources.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_brand_id: Mapped[int | None] = mapped_column(ForeignKey("model_brands.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority: Mapped[str] = mapped_column(String(40), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="discovered", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    suggested_angle: Mapped[str | None] = mapped_column(Text(), nullable=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[OpportunitySource | None] = relationship(back_populates="opportunities", lazy="selectin")
    model_brand: Mapped["ModelBrand | None"] = relationship("ModelBrand", lazy="selectin")
    assigned_to: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_to_user_id], lazy="selectin")


class OpportunityResult(TimestampMixin, Base):
    __tablename__ = "opportunity_results"
    __table_args__ = (
        CheckConstraint(
            "status in ('not_posted', 'posted', 'skipped', 'failed', 'rejected')",
            name="ck_opportunity_results_status",
        ),
        Index("ix_opportunity_results_opportunity_id", "opportunity_id"),
        Index("ix_opportunity_results_posted_by_user_id", "posted_by_user_id"),
        Index("ix_opportunity_results_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="not_posted", nullable=False)
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    opportunity: Mapped[Opportunity] = relationship(lazy="selectin")
    posted_by: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id], lazy="selectin")


class CreatorWatch(TimestampMixin, Base):
    __tablename__ = "creator_watches"
    __table_args__ = (
        CheckConstraint(
            "platform in ('x', 'instagram', 'other')",
            name="ck_creator_watches_platform",
        ),
        CheckConstraint(
            "priority in ('low', 'normal', 'high', 'critical')",
            name="ck_creator_watches_priority",
        ),
        CheckConstraint(
            "status in ('active', 'disabled', 'archived')",
            name="ck_creator_watches_status",
        ),
        Index("ix_creator_watches_platform", "platform"),
        Index("ix_creator_watches_creator_username", "creator_username"),
        Index("ix_creator_watches_niche", "niche"),
        Index("ix_creator_watches_priority", "priority"),
        Index("ix_creator_watches_status", "status"),
        Index("ix_creator_watches_assigned_model_id", "assigned_model_id"),
        Index("ix_creator_watches_assigned_team_id", "assigned_team_id"),
        Index("ix_creator_watches_assigned_chatter_id", "assigned_chatter_id"),
        Index("ix_creator_watches_is_active", "is_active"),
        Index("ix_creator_watches_is_demo", "is_demo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    creator_name: Mapped[str] = mapped_column(String(180), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    creator_username: Mapped[str] = mapped_column(String(160), nullable=False)
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[str] = mapped_column(String(40), default="normal", nullable=False)
    assigned_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_team_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_chatter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assigned_model: Mapped["ModelBrand | None"] = relationship("ModelBrand", lazy="selectin")
    assigned_chatter: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_chatter_id], lazy="selectin")


class PostWatch(TimestampMixin, Base):
    __tablename__ = "post_watches"
    __table_args__ = (
        CheckConstraint(
            "platform in ('x', 'instagram', 'other')",
            name="ck_post_watches_platform",
        ),
        CheckConstraint(
            "status in ('recent', 'attention_needed', 'assigned', 'archived')",
            name="ck_post_watches_status",
        ),
        CheckConstraint(
            "post_type in ('image', 'video', 'text', 'thread', 'story', 'reel', 'other')",
            name="ck_post_watches_post_type",
        ),
        CheckConstraint(
            "attention_level in ('monitor', 'engage', 'urgent')",
            name="ck_post_watches_attention_level",
        ),
        Index("ix_post_watches_model_brand_id", "model_brand_id"),
        Index("ix_post_watches_account_id", "account_id"),
        Index("ix_post_watches_platform", "platform"),
        Index("ix_post_watches_status", "status"),
        Index("ix_post_watches_attention_level", "attention_level"),
        Index("ix_post_watches_assigned_chatter_id", "assigned_chatter_id"),
        Index("ix_post_watches_assigned_team_id", "assigned_team_id"),
        Index("ix_post_watches_created_at", "created_at"),
        Index("ix_post_watches_is_demo", "is_demo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_brand_id: Mapped[int] = mapped_column(ForeignKey("model_brands.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    post_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    post_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="recent", nullable=False)
    attention_level: Mapped[str] = mapped_column(String(40), default="monitor", nullable=False)
    assigned_chatter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_team_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    model_brand: Mapped["ModelBrand"] = relationship("ModelBrand", lazy="selectin")
    account: Mapped["Account | None"] = relationship("Account", lazy="selectin")
    assigned_chatter: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_chatter_id], lazy="selectin")


class CommentStrategy(TimestampMixin, Base):
    __tablename__ = "comment_strategies"
    __table_args__ = (
        CheckConstraint(
            "angle in ('curiosity', 'question', 'agreement', 'relatable', 'story', 'authority', 'contrarian', "
            "'soft_cta', 'humor', 'educational', 'supportive')",
            name="ck_comment_strategies_angle",
        ),
        CheckConstraint("curiosity_score >= 0 and curiosity_score <= 100", name="ck_comment_strategies_curiosity_score"),
        CheckConstraint("engagement_score >= 0 and engagement_score <= 100", name="ck_comment_strategies_engagement_score"),
        CheckConstraint("risk_score >= 0 and risk_score <= 100", name="ck_comment_strategies_risk_score"),
        Index("ix_comment_strategies_opportunity_id", "opportunity_id"),
        Index("ix_comment_strategies_angle", "angle"),
        Index("ix_comment_strategies_risk_score", "risk_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True)
    angle: Mapped[str] = mapped_column(String(40), nullable=False)
    tone: Mapped[str] = mapped_column(String(80), nullable=False)
    sample_comment: Mapped[str | None] = mapped_column(Text(), nullable=True)
    curiosity_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    engagement_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text(), nullable=True)
    why_it_might_work: Mapped[str | None] = mapped_column(Text(), nullable=True)
    suggested_use_case: Mapped[str | None] = mapped_column(Text(), nullable=True)

    opportunity: Mapped["Opportunity | None"] = relationship("Opportunity", lazy="selectin")
