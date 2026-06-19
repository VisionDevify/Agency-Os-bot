"""Add social comment/profile intelligence tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_social_comment_profiles"
down_revision: str | None = "0036_recovery_prediction_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_METHOD_CHECK = (
    "source_method in ('manual', 'approved_export', 'official_api', 'compliant_public_source', "
    "'future_connector', 'unknown', 'private_scrape', 'unauthorized_scrape', 'bypassed_rate_limit', "
    "'evasion', 'stolen_export', 'unsupported')"
)


def _drop_check(table: str, name: str) -> None:
    op.drop_constraint(name, table, type_="check")


def upgrade() -> None:
    op.add_column("social_sources", sa.Column("source_method", sa.String(length=80), server_default="manual", nullable=False))
    op.create_check_constraint("ck_social_sources_source_method", "social_sources", SOURCE_METHOD_CHECK)
    _drop_check("social_sources", "ck_social_sources_compliance")
    op.create_check_constraint(
        "ck_social_sources_compliance",
        "social_sources",
        "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
    )

    op.add_column("social_posts", sa.Column("source_method", sa.String(length=80), server_default="manual", nullable=False))
    op.create_check_constraint("ck_social_posts_source_method", "social_posts", SOURCE_METHOD_CHECK)
    _drop_check("social_posts", "ck_social_posts_compliance")
    op.create_check_constraint(
        "ck_social_posts_compliance",
        "social_posts",
        "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
    )

    op.add_column("social_opportunity_scores", sa.Column("source_method", sa.String(length=80), server_default="manual", nullable=False))
    op.add_column("social_opportunity_scores", sa.Column("compliance_status", sa.String(length=40), server_default="approved", nullable=False))
    op.create_check_constraint("ck_social_opportunity_scores_source_method", "social_opportunity_scores", SOURCE_METHOD_CHECK)
    op.create_check_constraint(
        "ck_social_opportunity_scores_compliance",
        "social_opportunity_scores",
        "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
    )

    op.add_column("social_discovery_source_configs", sa.Column("source_method", sa.String(length=80), server_default="manual", nullable=False))
    op.create_check_constraint("ck_social_discovery_configs_source_method", "social_discovery_source_configs", SOURCE_METHOD_CHECK)
    _drop_check("social_discovery_source_configs", "ck_social_discovery_configs_compliance")
    op.create_check_constraint(
        "ck_social_discovery_configs_compliance",
        "social_discovery_source_configs",
        "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
    )

    op.add_column("social_discovery_leads", sa.Column("source_method", sa.String(length=80), server_default="manual", nullable=False))
    op.create_check_constraint("ck_social_discovery_leads_source_method", "social_discovery_leads", SOURCE_METHOD_CHECK)
    _drop_check("social_discovery_leads", "ck_social_discovery_leads_compliance")
    op.create_check_constraint(
        "ck_social_discovery_leads_compliance",
        "social_discovery_leads",
        "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
    )

    op.create_table(
        "social_compliance_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("source_method", sa.String(length=80), nullable=False),
        sa.Column("compliance_status", sa.String(length=40), nullable=False),
        sa.Column("validation_outcome", sa.String(length=80), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action in ('ingest', 'evaluate', 'rank', 'recommend', 'convert_to_opportunity', 'alert', 'learn')",
            name="ck_social_compliance_logs_action",
        ),
        sa.CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_compliance_logs_compliance",
        ),
        sa.CheckConstraint(SOURCE_METHOD_CHECK, name="ck_social_compliance_logs_source_method"),
        sa.CheckConstraint(
            "validation_outcome in ('passed', 'failed', 'missing_required_field', 'unsupported_source', 'review_required')",
            name="ck_social_compliance_logs_validation",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_compliance_logs_action", "social_compliance_logs", ["action"])
    op.create_index("ix_social_compliance_logs_allowed", "social_compliance_logs", ["allowed"])
    op.create_index("ix_social_compliance_logs_created_at", "social_compliance_logs", ["created_at"])
    op.create_index("ix_social_compliance_logs_entity", "social_compliance_logs", ["entity_type", "entity_id"])

    op.create_table(
        "social_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("event_category", sa.String(length=80), nullable=False),
        sa.Column("source_module", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("actor_type", sa.String(length=40), nullable=True),
        sa.Column("actor_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_category in ('discovery', 'comment', 'profile', 'compliance', 'evaluation', 'opportunity', 'learning', 'alert', 'system')",
            name="ck_social_events_category",
        ),
        sa.CheckConstraint(
            "status in ('success', 'warning', 'failed', 'skipped', 'pending', 'blocked', 'resolved')",
            name="ck_social_events_status",
        ),
        sa.CheckConstraint("severity in ('info', 'low', 'medium', 'high', 'critical')", name="ck_social_events_severity"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_events_category", "social_events", ["event_category"])
    op.create_index("ix_social_events_created_at", "social_events", ["created_at"])
    op.create_index("ix_social_events_entity", "social_events", ["entity_type", "entity_id"])
    op.create_index("ix_social_events_type", "social_events", ["event_type"])

    op.create_table(
        "social_comment_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("username", sa.String(length=160), nullable=False),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("observed_comment_count", sa.Integer(), nullable=False),
        sa.Column("avg_comment_quality", sa.Integer(), nullable=False),
        sa.Column("avg_engagement", sa.Integer(), nullable=False),
        sa.Column("repeated_appearance_count", sa.Integer(), nullable=False),
        sa.Column("potential_value_score", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_method", sa.String(length=80), nullable=False),
        sa.Column("compliance_status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_comment_profiles_platform"),
        sa.CheckConstraint(
            "status in ('new', 'watching', 'ignored', 'converted_to_opportunity', 'archived')",
            name="ck_social_comment_profiles_status",
        ),
        sa.CheckConstraint("avg_comment_quality >= 0 and avg_comment_quality <= 100", name="ck_social_comment_profiles_quality"),
        sa.CheckConstraint("avg_engagement >= 0 and avg_engagement <= 100", name="ck_social_comment_profiles_engagement"),
        sa.CheckConstraint("potential_value_score >= 0 and potential_value_score <= 100", name="ck_social_comment_profiles_value"),
        sa.CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_comment_profiles_compliance",
        ),
        sa.CheckConstraint(SOURCE_METHOD_CHECK, name="ck_social_comment_profiles_source_method"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "username", name="uq_social_comment_profiles_platform_username"),
    )
    op.create_index("ix_social_comment_profiles_compliance", "social_comment_profiles", ["compliance_status"])
    op.create_index("ix_social_comment_profiles_platform", "social_comment_profiles", ["platform"])
    op.create_index("ix_social_comment_profiles_score", "social_comment_profiles", ["potential_value_score"])
    op.create_index("ix_social_comment_profiles_status", "social_comment_profiles", ["status"])
    op.create_index("ix_social_comment_profiles_username", "social_comment_profiles", ["username"])

    op.create_table(
        "social_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("post_id", sa.String(length=120), nullable=True),
        sa.Column("post_reference", sa.String(length=500), nullable=False),
        sa.Column("author_username", sa.String(length=160), nullable=False),
        sa.Column("author_profile_url", sa.String(length=500), nullable=True),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("comment_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("reply_count", sa.Integer(), nullable=False),
        sa.Column("detected_angle", sa.String(length=80), nullable=True),
        sa.Column("sentiment", sa.String(length=40), nullable=True),
        sa.Column("quality_score", sa.Integer(), nullable=False),
        sa.Column("engagement_score", sa.Integer(), nullable=False),
        sa.Column("source_method", sa.String(length=80), nullable=False),
        sa.Column("compliance_status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_comments_platform"),
        sa.CheckConstraint("quality_score >= 0 and quality_score <= 100", name="ck_social_comments_quality"),
        sa.CheckConstraint("engagement_score >= 0 and engagement_score <= 100", name="ck_social_comments_engagement"),
        sa.CheckConstraint(
            "compliance_status in ('approved', 'needs_review', 'review_required', 'blocked')",
            name="ck_social_comments_compliance",
        ),
        sa.CheckConstraint(SOURCE_METHOD_CHECK, name="ck_social_comments_source_method"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_comments_author", "social_comments", ["author_username"])
    op.create_index("ix_social_comments_compliance", "social_comments", ["compliance_status"])
    op.create_index("ix_social_comments_platform", "social_comments", ["platform"])
    op.create_index("ix_social_comments_post_reference", "social_comments", ["post_reference"])

    op.create_table(
        "social_comment_profile_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.String(length=120), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engagement_score", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=False),
        sa.Column("reason_flagged", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_comment_observations_platform"),
        sa.CheckConstraint("engagement_score >= 0 and engagement_score <= 100", name="ck_social_comment_observations_engagement"),
        sa.CheckConstraint("quality_score >= 0 and quality_score <= 100", name="ck_social_comment_observations_quality"),
        sa.ForeignKeyConstraint(["comment_id"], ["social_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["social_comment_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_comment_observations_comment_id", "social_comment_profile_observations", ["comment_id"])
    op.create_index("ix_social_comment_observations_observed_at", "social_comment_profile_observations", ["observed_at"])
    op.create_index("ix_social_comment_observations_profile_id", "social_comment_profile_observations", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_social_comment_observations_profile_id", table_name="social_comment_profile_observations")
    op.drop_index("ix_social_comment_observations_observed_at", table_name="social_comment_profile_observations")
    op.drop_index("ix_social_comment_observations_comment_id", table_name="social_comment_profile_observations")
    op.drop_table("social_comment_profile_observations")

    op.drop_index("ix_social_comments_post_reference", table_name="social_comments")
    op.drop_index("ix_social_comments_platform", table_name="social_comments")
    op.drop_index("ix_social_comments_compliance", table_name="social_comments")
    op.drop_index("ix_social_comments_author", table_name="social_comments")
    op.drop_table("social_comments")

    op.drop_index("ix_social_comment_profiles_username", table_name="social_comment_profiles")
    op.drop_index("ix_social_comment_profiles_status", table_name="social_comment_profiles")
    op.drop_index("ix_social_comment_profiles_score", table_name="social_comment_profiles")
    op.drop_index("ix_social_comment_profiles_platform", table_name="social_comment_profiles")
    op.drop_index("ix_social_comment_profiles_compliance", table_name="social_comment_profiles")
    op.drop_table("social_comment_profiles")

    op.drop_index("ix_social_events_type", table_name="social_events")
    op.drop_index("ix_social_events_entity", table_name="social_events")
    op.drop_index("ix_social_events_created_at", table_name="social_events")
    op.drop_index("ix_social_events_category", table_name="social_events")
    op.drop_table("social_events")

    op.drop_index("ix_social_compliance_logs_entity", table_name="social_compliance_logs")
    op.drop_index("ix_social_compliance_logs_created_at", table_name="social_compliance_logs")
    op.drop_index("ix_social_compliance_logs_allowed", table_name="social_compliance_logs")
    op.drop_index("ix_social_compliance_logs_action", table_name="social_compliance_logs")
    op.drop_table("social_compliance_logs")

    _drop_check("social_discovery_leads", "ck_social_discovery_leads_compliance")
    op.create_check_constraint(
        "ck_social_discovery_leads_compliance",
        "social_discovery_leads",
        "compliance_status in ('approved', 'review_required', 'blocked')",
    )
    _drop_check("social_discovery_leads", "ck_social_discovery_leads_source_method")
    op.drop_column("social_discovery_leads", "source_method")

    _drop_check("social_discovery_source_configs", "ck_social_discovery_configs_compliance")
    op.create_check_constraint(
        "ck_social_discovery_configs_compliance",
        "social_discovery_source_configs",
        "compliance_status in ('approved', 'review_required', 'blocked')",
    )
    _drop_check("social_discovery_source_configs", "ck_social_discovery_configs_source_method")
    op.drop_column("social_discovery_source_configs", "source_method")

    _drop_check("social_opportunity_scores", "ck_social_opportunity_scores_compliance")
    _drop_check("social_opportunity_scores", "ck_social_opportunity_scores_source_method")
    op.drop_column("social_opportunity_scores", "compliance_status")
    op.drop_column("social_opportunity_scores", "source_method")

    _drop_check("social_posts", "ck_social_posts_compliance")
    op.create_check_constraint(
        "ck_social_posts_compliance",
        "social_posts",
        "compliance_status in ('approved', 'review_required', 'blocked')",
    )
    _drop_check("social_posts", "ck_social_posts_source_method")
    op.drop_column("social_posts", "source_method")

    _drop_check("social_sources", "ck_social_sources_compliance")
    op.create_check_constraint(
        "ck_social_sources_compliance",
        "social_sources",
        "compliance_status in ('approved', 'review_required', 'blocked')",
    )
    _drop_check("social_sources", "ck_social_sources_source_method")
    op.drop_column("social_sources", "source_method")
