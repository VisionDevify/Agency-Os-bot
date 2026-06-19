from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

SOCIAL_PLATFORMS = ("x", "instagram", "reddit", "other")
SOCIAL_FOLLOWER_TIERS = ("unknown", "nano", "micro", "mid", "macro", "mega")
SOCIAL_COMPLIANCE_STATUSES = ("approved", "needs_review", "review_required", "blocked")
SOCIAL_SOURCE_METHODS = (
    "manual",
    "approved_export",
    "official_api",
    "compliant_public_source",
    "future_connector",
    "unknown",
    "private_scrape",
    "unauthorized_scrape",
    "bypassed_rate_limit",
    "evasion",
    "stolen_export",
    "unsupported",
)
SOCIAL_PROTECTED_ACTIONS = ("ingest", "evaluate", "rank", "recommend", "convert_to_opportunity", "alert", "learn")
SOCIAL_VALIDATION_OUTCOMES = (
    "passed",
    "failed",
    "missing_required_field",
    "unsupported_source",
    "review_required",
)
SOCIAL_EVENT_CATEGORIES = (
    "discovery",
    "comment",
    "profile",
    "compliance",
    "evaluation",
    "opportunity",
    "learning",
    "alert",
    "system",
)
SOCIAL_EVENT_STATUSES = ("success", "warning", "failed", "skipped", "pending", "blocked", "resolved")
SOCIAL_EVENT_SEVERITIES = ("info", "low", "medium", "high", "critical")
SOCIAL_REVIEW_STATUSES = ("new", "reviewing", "reviewed", "skipped", "opportunity_created", "archived")
SOCIAL_SIGNAL_SEVERITIES = ("info", "warning", "critical")
SOCIAL_SIGNAL_STATUSES = ("open", "acknowledged", "resolved", "dismissed")
SOCIAL_SOURCE_TYPES = ("manual", "official_api", "approved_export", "approved_browser_capture")
SOCIAL_DISCOVERY_RUN_TYPES = ("manual_url", "manual_source", "csv_import", "official_api_placeholder", "approved_public_import")
SOCIAL_DISCOVERY_RUN_STATUSES = ("pending", "running", "succeeded", "failed")
SOCIAL_DISCOVERY_LEAD_STATUSES = ("new", "reviewed", "converted_to_opportunity", "skipped", "archived")
SOCIAL_DISCOVERY_SOURCE_TYPES = ("manual", "csv_export", "official_api_placeholder", "approved_public_import_placeholder")


class SocialSource(TimestampMixin, Base):
    __tablename__ = "social_sources"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_sources_platform"),
        CheckConstraint(
            "follower_tier in ('unknown', 'nano', 'micro', 'mid', 'macro', 'mega')",
            name="ck_social_sources_follower_tier",
        ),
        CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_sources_compliance",
        ),
        CheckConstraint(
            "source_type in ('manual', 'official_api', 'approved_export', 'approved_browser_capture')",
            name="ck_social_sources_source_type",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_sources_source_method",
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
    source_method: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
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
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_posts_compliance",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_posts_source_method",
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
    source_method: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
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
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_opportunity_scores_compliance",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_opportunity_scores_source_method",
        ),
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
    source_method: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)
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


class SocialDiscoverySourceConfig(TimestampMixin, Base):
    __tablename__ = "social_discovery_source_configs"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_discovery_configs_platform"),
        CheckConstraint(
            "source_type in ('manual', 'csv_export', 'official_api_placeholder', 'approved_public_import_placeholder')",
            name="ck_social_discovery_configs_source_type",
        ),
        CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_discovery_configs_compliance",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_discovery_configs_source_method",
        ),
        Index("ix_social_discovery_configs_platform", "platform"),
        Index("ix_social_discovery_configs_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    source_method: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    reference_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    compliance_status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SocialDiscoveryRun(TimestampMixin, Base):
    __tablename__ = "social_discovery_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type in ('manual_url', 'manual_source', 'csv_import', 'official_api_placeholder', 'approved_public_import')",
            name="ck_social_discovery_runs_type",
        ),
        CheckConstraint("status in ('pending', 'running', 'succeeded', 'failed')", name="ck_social_discovery_runs_status"),
        Index("ix_social_discovery_runs_status", "status"),
        Index("ix_social_discovery_runs_type", "run_type"),
        Index("ix_social_discovery_runs_started_by", "started_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    source_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_discovery_source_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SocialDiscoveryLead(TimestampMixin, Base):
    __tablename__ = "social_discovery_leads"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_discovery_leads_platform"),
        CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_social_discovery_leads_confidence"),
        CheckConstraint("opportunity_score >= 0 and opportunity_score <= 100", name="ck_social_discovery_leads_score"),
        CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_discovery_leads_compliance",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_discovery_leads_source_method",
        ),
        CheckConstraint(
            "status in ('new', 'reviewed', 'converted_to_opportunity', 'skipped', 'archived')",
            name="ck_social_discovery_leads_status",
        ),
        Index("ix_social_discovery_leads_run_id", "discovery_run_id"),
        Index("ix_social_discovery_leads_platform", "platform"),
        Index("ix_social_discovery_leads_niche", "niche"),
        Index("ix_social_discovery_leads_score", "opportunity_score"),
        Index("ix_social_discovery_leads_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    discovery_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_discovery_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    social_source_id: Mapped[int | None] = mapped_column(ForeignKey("social_sources.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    source_name: Mapped[str] = mapped_column(String(180), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    post_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason_found: Mapped[str] = mapped_column(Text(), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    opportunity_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    source_method: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)
    recommended_angle: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="new", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SocialComplianceLog(Base):
    __tablename__ = "social_compliance_logs"
    __table_args__ = (
        CheckConstraint(
            "action in ('ingest', 'evaluate', 'rank', 'recommend', 'convert_to_opportunity', 'alert', 'learn')",
            name="ck_social_compliance_logs_action",
        ),
        CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_compliance_logs_compliance",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_compliance_logs_source_method",
        ),
        CheckConstraint(
            "validation_outcome in ('passed', 'failed', 'missing_required_field', 'unsupported_source', 'review_required')",
            name="ck_social_compliance_logs_validation",
        ),
        Index("ix_social_compliance_logs_entity", "entity_type", "entity_id"),
        Index("ix_social_compliance_logs_action", "action"),
        Index("ix_social_compliance_logs_allowed", "allowed"),
        Index("ix_social_compliance_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    source_method: Mapped[str] = mapped_column(String(80), nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(40), nullable=False)
    validation_outcome: Mapped[str] = mapped_column(String(80), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    evidence_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SocialEvent(Base):
    __tablename__ = "social_events"
    __table_args__ = (
        CheckConstraint(
            "event_category in ('discovery', 'comment', 'profile', 'compliance', 'evaluation', 'opportunity', 'learning', 'alert', 'system')",
            name="ck_social_events_category",
        ),
        CheckConstraint(
            "status in ('success', 'warning', 'failed', 'skipped', 'pending', 'blocked', 'resolved')",
            name="ck_social_events_status",
        ),
        CheckConstraint(
            "severity in ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_social_events_severity",
        ),
        Index("ix_social_events_type", "event_type"),
        Index("ix_social_events_category", "event_category"),
        Index("ix_social_events_entity", "entity_type", "entity_id"),
        Index("ix_social_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    event_category: Mapped[str] = mapped_column(String(80), nullable=False)
    source_module: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SocialCommentProfile(TimestampMixin, Base):
    __tablename__ = "social_comment_profiles"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_comment_profiles_platform"),
        CheckConstraint(
            "status in ('new', 'watching', 'ignored', 'converted_to_opportunity', 'archived')",
            name="ck_social_comment_profiles_status",
        ),
        CheckConstraint("avg_comment_quality >= 0 and avg_comment_quality <= 100", name="ck_social_comment_profiles_quality"),
        CheckConstraint("avg_engagement >= 0 and avg_engagement <= 100", name="ck_social_comment_profiles_engagement"),
        CheckConstraint("potential_value_score >= 0 and potential_value_score <= 100", name="ck_social_comment_profiles_value"),
        CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_comment_profiles_compliance",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_comment_profiles_source_method",
        ),
        UniqueConstraint("platform", "username", name="uq_social_comment_profiles_platform_username"),
        Index("ix_social_comment_profiles_platform", "platform"),
        Index("ix_social_comment_profiles_username", "username"),
        Index("ix_social_comment_profiles_status", "status"),
        Index("ix_social_comment_profiles_score", "potential_value_score"),
        Index("ix_social_comment_profiles_compliance", "compliance_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    username: Mapped[str] = mapped_column(String(160), nullable=False)
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    observed_comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_comment_quality: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_engagement: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repeated_appearance_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    potential_value_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="new", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_method: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)

    observations: Mapped[list["SocialCommentProfileObservation"]] = relationship(back_populates="profile", lazy="selectin")


class SocialComment(TimestampMixin, Base):
    __tablename__ = "social_comments"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_comments_platform"),
        CheckConstraint("quality_score >= 0 and quality_score <= 100", name="ck_social_comments_quality"),
        CheckConstraint("engagement_score >= 0 and engagement_score <= 100", name="ck_social_comments_engagement"),
        CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_comments_compliance",
        ),
        CheckConstraint(
            "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', 'future_connector', "
            "'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', 'evasion', 'stolen_export', 'unsupported')",
            name="ck_social_comments_source_method",
        ),
        Index("ix_social_comments_platform", "platform"),
        Index("ix_social_comments_post_reference", "post_reference"),
        Index("ix_social_comments_author", "author_username"),
        Index("ix_social_comments_compliance", "compliance_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    post_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    post_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    author_username: Mapped[str] = mapped_column(String(160), nullable=False)
    author_profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    comment_text: Mapped[str] = mapped_column(Text(), nullable=False)
    comment_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detected_angle: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quality_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_method: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)

    observations: Mapped[list["SocialCommentProfileObservation"]] = relationship(back_populates="comment", lazy="selectin")


class SocialCommentProfileObservation(Base):
    __tablename__ = "social_comment_profile_observations"
    __table_args__ = (
        CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_comment_observations_platform"),
        CheckConstraint("engagement_score >= 0 and engagement_score <= 100", name="ck_social_comment_observations_engagement"),
        CheckConstraint("quality_score >= 0 and quality_score <= 100", name="ck_social_comment_observations_quality"),
        Index("ix_social_comment_observations_profile_id", "profile_id"),
        Index("ix_social_comment_observations_comment_id", "comment_id"),
        Index("ix_social_comment_observations_observed_at", "observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("social_comment_profiles.id", ondelete="CASCADE"), nullable=False)
    comment_id: Mapped[int] = mapped_column(ForeignKey("social_comments.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason_flagged: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    profile: Mapped[SocialCommentProfile] = relationship(back_populates="observations", lazy="selectin")
    comment: Mapped[SocialComment] = relationship(back_populates="observations", lazy="selectin")
