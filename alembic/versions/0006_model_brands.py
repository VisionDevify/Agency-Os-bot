"""model brands command center

Revision ID: 0006_model_brands
Revises: 0005_user_status_check
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_model_brands"
down_revision: str | None = "0005_user_status_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_brands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("stage_name", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('active', 'warning', 'disabled', 'archived')",
            name="ck_model_brands_status",
        ),
    )
    op.create_index("ix_model_brands_display_name", "model_brands", ["display_name"], unique=False)
    op.create_index("ix_model_brands_stage_name", "model_brands", ["stage_name"], unique=False)
    op.create_index("ix_model_brands_status", "model_brands", ["status"], unique=False)

    op.create_table(
        "model_brand_members",
        sa.Column("model_brand_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("relationship_type", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "relationship_type in "
            "('manager', 'chatter_manager', 'senior_chatter', 'chatter', 'va', 'viewer')",
            name="ck_model_brand_members_relationship_type",
        ),
        sa.ForeignKeyConstraint(["model_brand_id"], ["model_brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model_brand_id", "user_id", "relationship_type"),
        sa.UniqueConstraint(
            "model_brand_id",
            "user_id",
            "relationship_type",
            name="uq_model_brand_members_model_user_type",
        ),
    )
    op.create_index(
        "ix_model_brand_members_model_brand_id",
        "model_brand_members",
        ["model_brand_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_brand_members_user_id",
        "model_brand_members",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_brand_members_relationship_type",
        "model_brand_members",
        ["relationship_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_brand_members_relationship_type", table_name="model_brand_members")
    op.drop_index("ix_model_brand_members_user_id", table_name="model_brand_members")
    op.drop_index("ix_model_brand_members_model_brand_id", table_name="model_brand_members")
    op.drop_table("model_brand_members")
    op.drop_index("ix_model_brands_status", table_name="model_brands")
    op.drop_index("ix_model_brands_stage_name", table_name="model_brands")
    op.drop_index("ix_model_brands_display_name", table_name="model_brands")
    op.drop_table("model_brands")
