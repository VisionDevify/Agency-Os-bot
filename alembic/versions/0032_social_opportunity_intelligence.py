"""social opportunity intelligence

Revision ID: 0032_social_opp_intel
Revises: 0031_proxy_placeholder_cleanup
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0032_social_opp_intel"
down_revision: str | None = "0031_proxy_placeholder_cleanup"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("creator_watches", sa.Column("watch_reason", sa.Text(), nullable=True))
    op.add_column("creator_watches", sa.Column("historical_score", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("creator_watches", sa.Column("last_useful_post_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_creator_watches_historical_score",
        "creator_watches",
        "historical_score >= 0 and historical_score <= 100",
    )
    op.create_index("ix_creator_watches_historical_score", "creator_watches", ["historical_score"])
    op.create_index("ix_creator_watches_last_useful_post_at", "creator_watches", ["last_useful_post_at"])

    op.create_table(
        "social_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("creator_username", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=True),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("follower_tier", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("source_type", sa.String(length=60), nullable=False, server_default="manual"),
        sa.Column("compliance_status", sa.String(length=40), nullable=False, server_default="approved"),
        sa.Column("watch_reason", sa.Text(), nullable=True),
        sa.Column("historical_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_useful_post_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_sources_platform"),
        sa.CheckConstraint(
            "follower_tier in ('unknown', 'nano', 'micro', 'mid', 'macro', 'mega')",
            name="ck_social_sources_follower_tier",
        ),
        sa.CheckConstraint(
            "compliance_status in ('approved', 'review_required', 'blocked')",
            name="ck_social_sources_compliance",
        ),
        sa.CheckConstraint(
            "source_type in ('manual', 'official_api', 'approved_export', 'approved_browser_capture')",
            name="ck_social_sources_source_type",
        ),
        sa.CheckConstraint("historical_score >= 0 and historical_score <= 100", name="ck_social_sources_historical_score"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_sources_platform", "social_sources", ["platform"])
    op.create_index("ix_social_sources_username", "social_sources", ["creator_username"])
    op.create_index("ix_social_sources_niche", "social_sources", ["niche"])
    op.create_index("ix_social_sources_follower_tier", "social_sources", ["follower_tier"])
    op.create_index("ix_social_sources_compliance", "social_sources", ["compliance_status"])
    op.create_index("ix_social_sources_active", "social_sources", ["is_active"])

    op.create_table(
        "social_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("social_source_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("post_url", sa.String(length=500), nullable=True),
        sa.Column("post_reference", sa.String(length=500), nullable=False),
        sa.Column("post_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("content_summary", sa.Text(), nullable=True),
        sa.Column("engagement_signals_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("audience_fit", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("niche_match", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("creator_relevance", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("competition_level", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("content_quality", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("comment_activity_quality", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("compliance_status", sa.String(length=40), nullable=False, server_default="approved"),
        sa.Column("compliance_notes", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="new"),
        sa.Column("is_private_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["social_source_id"], ["social_sources.id"], ondelete="SET NULL"),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_posts_platform"),
        sa.CheckConstraint(
            "compliance_status in ('approved', 'review_required', 'blocked')",
            name="ck_social_posts_compliance",
        ),
        sa.CheckConstraint(
            "review_status in ('new', 'reviewing', 'reviewed', 'skipped', 'opportunity_created', 'archived')",
            name="ck_social_posts_review_status",
        ),
        sa.CheckConstraint("audience_fit >= 0 and audience_fit <= 100", name="ck_social_posts_audience_fit"),
        sa.CheckConstraint("niche_match >= 0 and niche_match <= 100", name="ck_social_posts_niche_match"),
        sa.CheckConstraint("creator_relevance >= 0 and creator_relevance <= 100", name="ck_social_posts_creator_relevance"),
        sa.CheckConstraint("competition_level >= 0 and competition_level <= 100", name="ck_social_posts_competition_level"),
        sa.CheckConstraint("content_quality >= 0 and content_quality <= 100", name="ck_social_posts_content_quality"),
        sa.CheckConstraint(
            "comment_activity_quality >= 0 and comment_activity_quality <= 100",
            name="ck_social_posts_comment_activity_quality",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_posts_source_id", "social_posts", ["social_source_id"])
    op.create_index("ix_social_posts_platform", "social_posts", ["platform"])
    op.create_index("ix_social_posts_post_time", "social_posts", ["post_time"])
    op.create_index("ix_social_posts_review_status", "social_posts", ["review_status"])
    op.create_index("ix_social_posts_compliance", "social_posts", ["compliance_status"])
    op.create_index("ix_social_posts_niche", "social_posts", ["niche"])

    op.create_table(
        "social_opportunity_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("social_post_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("components_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("best_timing_window", sa.String(length=120), nullable=True),
        sa.Column("suggested_engagement_angle", sa.String(length=80), nullable=True),
        sa.Column("confidence_summary", sa.Text(), nullable=True),
        sa.Column("compliance_warning", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["social_post_id"], ["social_posts.id"], ondelete="CASCADE"),
        sa.CheckConstraint("score >= 0 and score <= 100", name="ck_social_opportunity_scores_score"),
        sa.CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 100",
            name="ck_social_opportunity_scores_confidence",
        ),
        sa.CheckConstraint(
            "status in ('new', 'reviewing', 'reviewed', 'skipped', 'opportunity_created', 'archived')",
            name="ck_social_opportunity_scores_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("social_post_id", name="uq_social_opportunity_scores_post"),
    )
    op.create_index("ix_social_opportunity_scores_post_id", "social_opportunity_scores", ["social_post_id"])
    op.create_index("ix_social_opportunity_scores_opportunity_id", "social_opportunity_scores", ["opportunity_id"])
    op.create_index("ix_social_opportunity_scores_score", "social_opportunity_scores", ["score"])
    op.create_index("ix_social_opportunity_scores_confidence", "social_opportunity_scores", ["confidence_score"])
    op.create_index("ix_social_opportunity_scores_status", "social_opportunity_scores", ["status"])

    op.create_table(
        "social_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("social_source_id", sa.Integer(), nullable=True),
        sa.Column("social_post_id", sa.Integer(), nullable=True),
        sa.Column("social_opportunity_score_id", sa.Integer(), nullable=True),
        sa.Column("signal_type", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["social_opportunity_score_id"], ["social_opportunity_scores.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["social_post_id"], ["social_posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["social_source_id"], ["social_sources.id"], ondelete="SET NULL"),
        sa.CheckConstraint("severity in ('info', 'warning', 'critical')", name="ck_social_signals_severity"),
        sa.CheckConstraint(
            "status in ('open', 'acknowledged', 'resolved', 'dismissed')",
            name="ck_social_signals_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_signals_source_id", "social_signals", ["social_source_id"])
    op.create_index("ix_social_signals_post_id", "social_signals", ["social_post_id"])
    op.create_index("ix_social_signals_score_id", "social_signals", ["social_opportunity_score_id"])
    op.create_index("ix_social_signals_type", "social_signals", ["signal_type"])
    op.create_index("ix_social_signals_status", "social_signals", ["status"])
    op.create_index("ix_social_signals_severity", "social_signals", ["severity"])

    op.create_table(
        "social_source_performance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("social_source_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("engagement_angle", sa.String(length=80), nullable=True),
        sa.Column("reviewed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profile_visits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("historical_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_outcome", sa.String(length=40), nullable=True),
        sa.Column("best_timing_window", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["social_source_id"], ["social_sources.id"], ondelete="SET NULL"),
        sa.CheckConstraint("historical_score >= 0 and historical_score <= 100", name="ck_social_source_performance_score"),
        sa.CheckConstraint("success_rate >= 0 and success_rate <= 100", name="ck_social_source_performance_success_rate"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("social_source_id", "niche", "engagement_angle", name="uq_social_source_performance_bucket"),
    )
    op.create_index("ix_social_source_performance_source_id", "social_source_performance", ["social_source_id"])
    op.create_index("ix_social_source_performance_niche", "social_source_performance", ["niche"])
    op.create_index("ix_social_source_performance_angle", "social_source_performance", ["engagement_angle"])
    op.create_index("ix_social_source_performance_score", "social_source_performance", ["historical_score"])


def downgrade() -> None:
    op.drop_index("ix_social_source_performance_score", table_name="social_source_performance")
    op.drop_index("ix_social_source_performance_angle", table_name="social_source_performance")
    op.drop_index("ix_social_source_performance_niche", table_name="social_source_performance")
    op.drop_index("ix_social_source_performance_source_id", table_name="social_source_performance")
    op.drop_table("social_source_performance")

    op.drop_index("ix_social_signals_severity", table_name="social_signals")
    op.drop_index("ix_social_signals_status", table_name="social_signals")
    op.drop_index("ix_social_signals_type", table_name="social_signals")
    op.drop_index("ix_social_signals_score_id", table_name="social_signals")
    op.drop_index("ix_social_signals_post_id", table_name="social_signals")
    op.drop_index("ix_social_signals_source_id", table_name="social_signals")
    op.drop_table("social_signals")

    op.drop_index("ix_social_opportunity_scores_status", table_name="social_opportunity_scores")
    op.drop_index("ix_social_opportunity_scores_confidence", table_name="social_opportunity_scores")
    op.drop_index("ix_social_opportunity_scores_score", table_name="social_opportunity_scores")
    op.drop_index("ix_social_opportunity_scores_opportunity_id", table_name="social_opportunity_scores")
    op.drop_index("ix_social_opportunity_scores_post_id", table_name="social_opportunity_scores")
    op.drop_table("social_opportunity_scores")

    op.drop_index("ix_social_posts_niche", table_name="social_posts")
    op.drop_index("ix_social_posts_compliance", table_name="social_posts")
    op.drop_index("ix_social_posts_review_status", table_name="social_posts")
    op.drop_index("ix_social_posts_post_time", table_name="social_posts")
    op.drop_index("ix_social_posts_platform", table_name="social_posts")
    op.drop_index("ix_social_posts_source_id", table_name="social_posts")
    op.drop_table("social_posts")

    op.drop_index("ix_social_sources_active", table_name="social_sources")
    op.drop_index("ix_social_sources_compliance", table_name="social_sources")
    op.drop_index("ix_social_sources_follower_tier", table_name="social_sources")
    op.drop_index("ix_social_sources_niche", table_name="social_sources")
    op.drop_index("ix_social_sources_username", table_name="social_sources")
    op.drop_index("ix_social_sources_platform", table_name="social_sources")
    op.drop_table("social_sources")

    op.drop_index("ix_creator_watches_last_useful_post_at", table_name="creator_watches")
    op.drop_index("ix_creator_watches_historical_score", table_name="creator_watches")
    op.drop_constraint("ck_creator_watches_historical_score", "creator_watches", type_="check")
    op.drop_column("creator_watches", "last_useful_post_at")
    op.drop_column("creator_watches", "historical_score")
    op.drop_column("creator_watches", "watch_reason")
