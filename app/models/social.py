from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

SOCIAL_PLATFORMS = ("x", "instagram", "reddit", "other")
SOCIAL_FOLLOWER_TIERS = ("unknown", "nano", "micro", "mid", "macro", "mega")
SOCIAL_COMPLIANCE_STATUSES = ("approved", "review_required", "blocked")
SOCIAL_REVIEW_STATUSES = ("new", "reviewing", "reviewed", "skipped", "opportunity_created", "archived")
SOCIAL_SIGNAL_SEVERITIES = ("info", "warning", "critical")
SOCIAL_SIGNAL_STATUSES = ("open", "acknowledged", "resolved", "dismissed")
SOCIAL_SOURCE_TYPES = ("manual", "official_api", "approved_export", "approved_browser_capture")


class SocialSource(TimestampMixin, Base):
    __tablename__ = "social_sources"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_sources_platform"),
        CheckConstraint(
            "follower_tier in ('unknown', 'nano', 'micro', 'mid', 'macro', 'mega')",
            name="ck_social_sources_follower_tier",
        ),
        CheckConstraint(
            "compliance_status in ('approved', 'review_required', 'blocked')",
            name="ck_social_sources_compliance",
        ),
        CheckConstraint(
            "source_type in ('manual', 'official_api', 'approved_export', 'approved_browser_capture')",
            name="ck_social_sources_source_type",
        ),
        CheckConstraint("historical_score >= 0 and historical_score <= 100", name="ck_social_sources_historical_score"),
        Index("ix_social_sources_platform", "platform"),
        Index("ix_social_sources_username", "creator_username"),
        Index("ix_social_sources_niche", "niche"),
        Index("ix_social_sources_follower_tier", "follower_tier"),
        Index("ix_social_sources_compliance", "compliance_status"),
        Index("ix_social_sources_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    creator_username: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    follower_tier: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    source_type: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)
    watch_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    historical_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_useful_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    posts: Mapped[list["SocialPost"]] = relationship(back_populates="source", lazy="selectin")
    performance_rows: Mapped[list["SocialSourcePerformance"]] = relationship(back_populates="source", lazy="selectin")


class SocialPost(TimestampMixin, Base):
    __tablename__ = "social_posts"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_posts_platform"),
        CheckConstraint(
            "compliance_status in ('approved', 'review_required', 'blocked')",
            name="ck_social_posts_compliance",
        ),
        CheckConstraint(
            "review_status in ('new', 'reviewing', 'reviewed', 'skipped', 'opportunity_created', 'archived')",
            name="ck_social_posts_review_status",
        ),
        CheckConstraint("audience_fit >= 0 and audience_fit <= 100", name="ck_social_posts_audience_fit"),
        CheckConstraint("niche_match >= 0 and niche_match <= 100", name="ck_social_posts_niche_match"),
        CheckConstraint("creator_relevance >= 0 and creator_relevance <= 100", name="ck_social_posts_creator_relevance"),
        CheckConstraint("competition_level >= 0 and competition_level <= 100", name="ck_social_posts_competition_level"),
        CheckConstraint("content_quality >= 0 and content_quality <= 100", name="ck_social_posts_content_quality"),
        CheckConstraint(
            "comment_activity_quality >= 0 and comment_activity_quality <= 100",
            name="ck_social_posts_comment_activity_quality",
        ),
        Index("ix_social_posts_source_id", "social_source_id"),
        Index("ix_social_posts_platform", "platform"),
        Index("ix_social_posts_post_time", "post_time"),
        Index("ix_social_posts_review_status", "review_status"),
        Index("ix_social_posts_compliance", "compliance_status"),
        Index("ix_social_posts_niche", "niche"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    social_source_id: Mapped[int | None] = mapped_column(ForeignKey("social_sources.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    post_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    post_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    engagement_signals_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    audience_fit: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    niche_match: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    creator_relevance: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    competition_level: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    content_quality: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    comment_activity_quality: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)
    compliance_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    review_status: Mapped[str] = mapped_column(String(40), default="new", nullable=False)
    is_private_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    source: Mapped[SocialSource | None] = relationship(back_populates="posts", lazy="selectin")
    scores: Mapped[list["SocialOpportunityScore"]] = relationship(back_populates="post", lazy="selectin")


class SocialOpportunityScore(TimestampMixin, Base):
    __tablename__ = "social_opportunity_scores"
    __table_args__ = (
        CheckConstraint("score >= 0 and score <= 100", name="ck_social_opportunity_scores_score"),
        CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_social_opportunity_scores_confidence"),
        CheckConstraint(
            "status in ('new', 'reviewing', 'reviewed', 'skipped', 'opportunity_created', 'archived')",
            name="ck_social_opportunity_scores_status",
        ),
        UniqueConstraint("social_post_id", name="uq_social_opportunity_scores_post"),
        Index("ix_social_opportunity_scores_post_id", "social_post_id"),
        Index("ix_social_opportunity_scores_opportunity_id", "opportunity_id"),
        Index("ix_social_opportunity_scores_score", "score"),
        Index("ix_social_opportunity_scores_confidence", "confidence_score"),
        Index("ix_social_opportunity_scores_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    social_post_id: Mapped[int] = mapped_column(ForeignKey("social_posts.id", ondelete="CASCADE"), nullable=False)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    components_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    best_timing_window: Mapped[str | None] = mapped_column(String(120), nullable=True)
    suggested_engagement_angle: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    compliance_warning: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="new", nullable=False)

    post: Mapped[SocialPost] = relationship(back_populates="scores", lazy="selectin")
    opportunity: Mapped["Opportunity | None"] = relationship("Opportunity", lazy="selectin")


class SocialSignal(TimestampMixin, Base):
    __tablename__ = "social_signals"
    __table_args__ = (
        CheckConstraint("severity in ('info', 'warning', 'critical')", name="ck_social_signals_severity"),
        CheckConstraint(
            "status in ('open', 'acknowledged', 'resolved', 'dismissed')",
            name="ck_social_signals_status",
        ),
        Index("ix_social_signals_source_id", "social_source_id"),
        Index("ix_social_signals_post_id", "social_post_id"),
        Index("ix_social_signals_score_id", "social_opportunity_score_id"),
        Index("ix_social_signals_type", "signal_type"),
        Index("ix_social_signals_status", "status"),
        Index("ix_social_signals_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    social_source_id: Mapped[int | None] = mapped_column(ForeignKey("social_sources.id", ondelete="SET NULL"), nullable=True)
    social_post_id: Mapped[int | None] = mapped_column(ForeignKey("social_posts.id", ondelete="SET NULL"), nullable=True)
    social_opportunity_score_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_opportunity_scores.id", ondelete="SET NULL"),
        nullable=True,
    )
    signal_type: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)


class SocialSourcePerformance(TimestampMixin, Base):
    __tablename__ = "social_source_performance"
    __table_args__ = (
        CheckConstraint("historical_score >= 0 and historical_score <= 100", name="ck_social_source_performance_score"),
        CheckConstraint("success_rate >= 0 and success_rate <= 100", name="ck_social_source_performance_success_rate"),
        UniqueConstraint("social_source_id", "niche", "engagement_angle", name="uq_social_source_performance_bucket"),
        Index("ix_social_source_performance_source_id", "social_source_id"),
        Index("ix_social_source_performance_niche", "niche"),
        Index("ix_social_source_performance_angle", "engagement_angle"),
        Index("ix_social_source_performance_score", "historical_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    social_source_id: Mapped[int | None] = mapped_column(ForeignKey("social_sources.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    engagement_angle: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    replies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    profile_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    historical_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    best_timing_window: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    source: Mapped[SocialSource | None] = relationship(back_populates="performance_rows", lazy="selectin")
