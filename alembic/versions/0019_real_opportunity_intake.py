"""real opportunity intake workflows

Revision ID: 0019_opportunity_intake
Revises: 0018_creator_watch
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_opportunity_intake"
down_revision: str | None = "0018_creator_watch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("creator_watches", sa.Column("display_name", sa.String(length=180), nullable=True))
    op.add_column(
        "creator_watches",
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
    )
    op.execute("update creator_watches set display_name = creator_name where display_name is null")
    op.create_check_constraint(
        "ck_creator_watches_status",
        "creator_watches",
        "status in ('active', 'disabled', 'archived')",
    )
    op.create_index("ix_creator_watches_status", "creator_watches", ["status"])

    op.add_column("opportunities", sa.Column("source_type", sa.String(length=40), nullable=True))
    op.add_column("opportunities", sa.Column("source_reference_id", sa.Integer(), nullable=True))
    op.add_column(
        "opportunities",
        sa.Column("priority", sa.String(length=40), nullable=False, server_default="normal"),
    )
    op.add_column("opportunities", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("opportunities", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("opportunities", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_opportunities_priority",
        "opportunities",
        "priority in ('low', 'normal', 'high', 'critical')",
    )
    op.create_check_constraint(
        "ck_opportunities_source_type",
        "opportunities",
        "source_type is null or source_type in ('manual', 'creator_watch', 'own_post')",
    )
    op.create_index("ix_opportunities_source_ref", "opportunities", ["source_type", "source_reference_id"])
    op.create_index("ix_opportunities_priority", "opportunities", ["priority"])
    op.create_index("ix_opportunities_due_at", "opportunities", ["due_at"])

    op.add_column("opportunity_results", sa.Column("reason", sa.Text(), nullable=True))

    op.execute("update post_watches set post_type = 'other' where post_type = 'post'")
    op.add_column(
        "post_watches",
        sa.Column("attention_level", sa.String(length=40), nullable=False, server_default="monitor"),
    )
    op.add_column("post_watches", sa.Column("assigned_chatter_id", sa.Integer(), nullable=True))
    op.add_column("post_watches", sa.Column("assigned_team_id", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_post_watches_post_type",
        "post_watches",
        "post_type in ('image', 'video', 'text', 'thread', 'story', 'reel', 'other')",
    )
    op.create_check_constraint(
        "ck_post_watches_attention_level",
        "post_watches",
        "attention_level in ('monitor', 'engage', 'urgent')",
    )
    op.create_foreign_key(
        "fk_post_watches_assigned_chatter_id_users",
        "post_watches",
        "users",
        ["assigned_chatter_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_post_watches_attention_level", "post_watches", ["attention_level"])
    op.create_index("ix_post_watches_assigned_chatter_id", "post_watches", ["assigned_chatter_id"])
    op.create_index("ix_post_watches_assigned_team_id", "post_watches", ["assigned_team_id"])

    op.add_column("comment_strategies", sa.Column("sample_comment", sa.Text(), nullable=True))
    op.add_column("comment_strategies", sa.Column("why_it_might_work", sa.Text(), nullable=True))
    op.add_column("comment_strategies", sa.Column("suggested_use_case", sa.Text(), nullable=True))
    op.drop_constraint("ck_comment_strategies_angle", "comment_strategies", type_="check")
    op.create_check_constraint(
        "ck_comment_strategies_angle",
        "comment_strategies",
        "angle in ('curiosity', 'question', 'agreement', 'relatable', 'story', 'authority', "
        "'contrarian', 'soft_cta', 'humor', 'educational', 'supportive')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_comment_strategies_angle", "comment_strategies", type_="check")
    op.create_check_constraint(
        "ck_comment_strategies_angle",
        "comment_strategies",
        "angle in ('curiosity', 'question', 'agreement', 'story', 'authority', 'contrarian', 'educational')",
    )
    op.drop_column("comment_strategies", "suggested_use_case")
    op.drop_column("comment_strategies", "why_it_might_work")
    op.drop_column("comment_strategies", "sample_comment")

    op.drop_index("ix_post_watches_assigned_team_id", table_name="post_watches")
    op.drop_index("ix_post_watches_assigned_chatter_id", table_name="post_watches")
    op.drop_index("ix_post_watches_attention_level", table_name="post_watches")
    op.drop_constraint("fk_post_watches_assigned_chatter_id_users", "post_watches", type_="foreignkey")
    op.drop_constraint("ck_post_watches_attention_level", "post_watches", type_="check")
    op.drop_constraint("ck_post_watches_post_type", "post_watches", type_="check")
    op.drop_column("post_watches", "assigned_team_id")
    op.drop_column("post_watches", "assigned_chatter_id")
    op.drop_column("post_watches", "attention_level")

    op.drop_column("opportunity_results", "reason")

    op.drop_index("ix_opportunities_due_at", table_name="opportunities")
    op.drop_index("ix_opportunities_priority", table_name="opportunities")
    op.drop_index("ix_opportunities_source_ref", table_name="opportunities")
    op.drop_constraint("ck_opportunities_source_type", "opportunities", type_="check")
    op.drop_constraint("ck_opportunities_priority", "opportunities", type_="check")
    op.drop_column("opportunities", "completed_at")
    op.drop_column("opportunities", "assigned_at")
    op.drop_column("opportunities", "due_at")
    op.drop_column("opportunities", "priority")
    op.drop_column("opportunities", "source_reference_id")
    op.drop_column("opportunities", "source_type")

    op.drop_index("ix_creator_watches_status", table_name="creator_watches")
    op.drop_constraint("ck_creator_watches_status", "creator_watches", type_="check")
    op.drop_column("creator_watches", "status")
    op.drop_column("creator_watches", "display_name")
