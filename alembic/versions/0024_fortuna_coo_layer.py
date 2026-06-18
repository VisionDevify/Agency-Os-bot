"""fortuna coo layer

Revision ID: 0024_fortuna_coo
Revises: 0023_activation_autopilot
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_fortuna_coo"
down_revision: str | None = "0023_activation_autopilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "priority_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="info"),
        sa.Column("urgency", sa.String(length=40), nullable=False, server_default="normal"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("business_impact", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_owner", sa.String(length=80), nullable=False, server_default="Manager"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_priority_items_severity",
        ),
        sa.CheckConstraint(
            "urgency in ('low', 'normal', 'high', 'urgent')",
            name="ck_priority_items_urgency",
        ),
        sa.CheckConstraint("confidence >= 0 and confidence <= 100", name="ck_priority_items_confidence"),
        sa.CheckConstraint("business_impact >= 0 and business_impact <= 100", name="ck_priority_items_business_impact"),
        sa.CheckConstraint("score >= 0 and score <= 100", name="ck_priority_items_score"),
        sa.CheckConstraint(
            "status in ('open', 'routed', 'acknowledged', 'resolved', 'dismissed')",
            name="ck_priority_items_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "category",
            name="uq_priority_items_source_category",
        ),
    )
    op.create_index("ix_priority_items_source", "priority_items", ["source_type", "source_id"])
    op.create_index("ix_priority_items_category", "priority_items", ["category"])
    op.create_index("ix_priority_items_status", "priority_items", ["status"])
    op.create_index("ix_priority_items_score", "priority_items", ["score"])
    op.create_index("ix_priority_items_recommended_owner", "priority_items", ["recommended_owner"])
    op.create_index("ix_priority_items_updated_at", "priority_items", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_priority_items_updated_at", table_name="priority_items")
    op.drop_index("ix_priority_items_recommended_owner", table_name="priority_items")
    op.drop_index("ix_priority_items_score", table_name="priority_items")
    op.drop_index("ix_priority_items_status", table_name="priority_items")
    op.drop_index("ix_priority_items_category", table_name="priority_items")
    op.drop_index("ix_priority_items_source", table_name="priority_items")
    op.drop_table("priority_items")
