"""creator watch opportunity command center

Revision ID: 0018_creator_watch
Revises: 0017_team_rollout
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_creator_watch"
down_revision: str | None = "0017_team_rollout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creator_watches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("creator_name", sa.String(length=180), nullable=False),
        sa.Column("creator_username", sa.String(length=160), nullable=False),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=40), nullable=False, server_default="normal"),
        sa.Column("assigned_model_id", sa.Integer(), nullable=True),
        sa.Column("assigned_team_id", sa.Integer(), nullable=True),
        sa.Column("assigned_chatter_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'other')", name="ck_creator_watches_platform"),
        sa.CheckConstraint("priority in ('low', 'normal', 'high', 'critical')", name="ck_creator_watches_priority"),
        sa.ForeignKeyConstraint(["assigned_chatter_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_model_id"], ["model_brands.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_creator_watches_platform", "creator_watches", ["platform"])
    op.create_index("ix_creator_watches_creator_username", "creator_watches", ["creator_username"])
    op.create_index("ix_creator_watches_niche", "creator_watches", ["niche"])
    op.create_index("ix_creator_watches_priority", "creator_watches", ["priority"])
    op.create_index("ix_creator_watches_assigned_model_id", "creator_watches", ["assigned_model_id"])
    op.create_index("ix_creator_watches_assigned_team_id", "creator_watches", ["assigned_team_id"])
    op.create_index("ix_creator_watches_assigned_chatter_id", "creator_watches", ["assigned_chatter_id"])
    op.create_index("ix_creator_watches_is_active", "creator_watches", ["is_active"])

    op.create_table(
        "post_watches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_brand_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("post_reference", sa.String(length=500), nullable=False),
        sa.Column("post_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="recent"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'other')", name="ck_post_watches_platform"),
        sa.CheckConstraint("status in ('recent', 'attention_needed', 'assigned', 'archived')", name="ck_post_watches_status"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_brand_id"], ["model_brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_post_watches_model_brand_id", "post_watches", ["model_brand_id"])
    op.create_index("ix_post_watches_account_id", "post_watches", ["account_id"])
    op.create_index("ix_post_watches_platform", "post_watches", ["platform"])
    op.create_index("ix_post_watches_status", "post_watches", ["status"])
    op.create_index("ix_post_watches_created_at", "post_watches", ["created_at"])

    op.create_table(
        "comment_strategies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("angle", sa.String(length=40), nullable=False),
        sa.Column("tone", sa.String(length=80), nullable=False),
        sa.Column("curiosity_score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("engagement_score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "angle in ('curiosity', 'question', 'agreement', 'story', 'authority', 'contrarian', 'educational')",
            name="ck_comment_strategies_angle",
        ),
        sa.CheckConstraint(
            "curiosity_score >= 0 and curiosity_score <= 100",
            name="ck_comment_strategies_curiosity_score",
        ),
        sa.CheckConstraint(
            "engagement_score >= 0 and engagement_score <= 100",
            name="ck_comment_strategies_engagement_score",
        ),
        sa.CheckConstraint("risk_score >= 0 and risk_score <= 100", name="ck_comment_strategies_risk_score"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comment_strategies_opportunity_id", "comment_strategies", ["opportunity_id"])
    op.create_index("ix_comment_strategies_angle", "comment_strategies", ["angle"])
    op.create_index("ix_comment_strategies_risk_score", "comment_strategies", ["risk_score"])

    op.drop_constraint("ck_opportunity_results_status", "opportunity_results", type_="check")
    op.create_check_constraint(
        "ck_opportunity_results_status",
        "opportunity_results",
        "status in ('not_posted', 'posted', 'skipped', 'failed', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_opportunity_results_status", "opportunity_results", type_="check")
    op.create_check_constraint(
        "ck_opportunity_results_status",
        "opportunity_results",
        "status in ('not_posted', 'posted', 'skipped', 'failed')",
    )

    op.drop_index("ix_comment_strategies_risk_score", table_name="comment_strategies")
    op.drop_index("ix_comment_strategies_angle", table_name="comment_strategies")
    op.drop_index("ix_comment_strategies_opportunity_id", table_name="comment_strategies")
    op.drop_table("comment_strategies")

    op.drop_index("ix_post_watches_created_at", table_name="post_watches")
    op.drop_index("ix_post_watches_status", table_name="post_watches")
    op.drop_index("ix_post_watches_platform", table_name="post_watches")
    op.drop_index("ix_post_watches_account_id", table_name="post_watches")
    op.drop_index("ix_post_watches_model_brand_id", table_name="post_watches")
    op.drop_table("post_watches")

    op.drop_index("ix_creator_watches_is_active", table_name="creator_watches")
    op.drop_index("ix_creator_watches_assigned_chatter_id", table_name="creator_watches")
    op.drop_index("ix_creator_watches_assigned_team_id", table_name="creator_watches")
    op.drop_index("ix_creator_watches_assigned_model_id", table_name="creator_watches")
    op.drop_index("ix_creator_watches_priority", table_name="creator_watches")
    op.drop_index("ix_creator_watches_niche", table_name="creator_watches")
    op.drop_index("ix_creator_watches_creator_username", table_name="creator_watches")
    op.drop_index("ix_creator_watches_platform", table_name="creator_watches")
    op.drop_table("creator_watches")
