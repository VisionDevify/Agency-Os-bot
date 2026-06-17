"""setup wizard and ui clarity persistence

Revision ID: 0020_setup_wizard
Revises: 0019_opportunity_intake
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_setup_wizard"
down_revision: str | None = "0019_opportunity_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_brands", sa.Column("country", sa.String(length=120), nullable=True))
    op.add_column("model_brands", sa.Column("timezone", sa.String(length=120), nullable=True))
    op.add_column("model_brands", sa.Column("language_preference", sa.String(length=80), nullable=True))
    op.add_column("model_brands", sa.Column("primary_platform", sa.String(length=40), nullable=True))
    op.add_column("model_brands", sa.Column("internal_notes", sa.Text(), nullable=True))
    op.add_column(
        "model_brands",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_model_brands_country", "model_brands", ["country"])
    op.create_index("ix_model_brands_timezone", "model_brands", ["timezone"])
    op.create_index("ix_model_brands_is_demo", "model_brands", ["is_demo"])

    op.add_column("accounts", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_accounts_is_demo", "accounts", ["is_demo"])

    op.add_column("creator_watches", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_creator_watches_is_demo", "creator_watches", ["is_demo"])

    op.add_column("opportunities", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_opportunities_is_demo", "opportunities", ["is_demo"])

    op.add_column("post_watches", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_post_watches_is_demo", "post_watches", ["is_demo"])

    op.create_table(
        "setup_wizard_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("model_brand_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="started"),
        sa.Column("current_step", sa.String(length=80), nullable=False, server_default="model"),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("missing_items_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('started', 'in_progress', 'completed', 'abandoned')",
            name="ck_setup_wizard_states_status",
        ),
        sa.ForeignKeyConstraint(["model_brand_id"], ["model_brands.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_setup_wizard_states_owner_user_id", "setup_wizard_states", ["owner_user_id"])
    op.create_index("ix_setup_wizard_states_model_brand_id", "setup_wizard_states", ["model_brand_id"])
    op.create_index("ix_setup_wizard_states_status", "setup_wizard_states", ["status"])

    op.create_table(
        "first_day_checklists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_first_model", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_accounts", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_manager", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_team", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_creators", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_opportunities", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_opportunities", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generated_briefing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reviewed_activation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checked_production", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completion_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "completion_score >= 0 and completion_score <= 100",
            name="ck_first_day_checklists_completion_score",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_first_day_checklists_user_id", "first_day_checklists", ["user_id"], unique=True)
    op.create_index("ix_first_day_checklists_completion_score", "first_day_checklists", ["completion_score"])


def downgrade() -> None:
    op.drop_index("ix_first_day_checklists_completion_score", table_name="first_day_checklists")
    op.drop_index("ix_first_day_checklists_user_id", table_name="first_day_checklists")
    op.drop_table("first_day_checklists")

    op.drop_index("ix_setup_wizard_states_status", table_name="setup_wizard_states")
    op.drop_index("ix_setup_wizard_states_model_brand_id", table_name="setup_wizard_states")
    op.drop_index("ix_setup_wizard_states_owner_user_id", table_name="setup_wizard_states")
    op.drop_table("setup_wizard_states")

    op.drop_index("ix_post_watches_is_demo", table_name="post_watches")
    op.drop_column("post_watches", "is_demo")
    op.drop_index("ix_opportunities_is_demo", table_name="opportunities")
    op.drop_column("opportunities", "is_demo")
    op.drop_index("ix_creator_watches_is_demo", table_name="creator_watches")
    op.drop_column("creator_watches", "is_demo")
    op.drop_index("ix_accounts_is_demo", table_name="accounts")
    op.drop_column("accounts", "is_demo")

    op.drop_index("ix_model_brands_is_demo", table_name="model_brands")
    op.drop_index("ix_model_brands_timezone", table_name="model_brands")
    op.drop_index("ix_model_brands_country", table_name="model_brands")
    op.drop_column("model_brands", "is_demo")
    op.drop_column("model_brands", "internal_notes")
    op.drop_column("model_brands", "primary_platform")
    op.drop_column("model_brands", "language_preference")
    op.drop_column("model_brands", "timezone")
    op.drop_column("model_brands", "country")
