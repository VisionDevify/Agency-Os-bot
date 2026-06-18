"""friction items

Revision ID: 0027_friction_items
Revises: 0026_help_brain_pilot_readiness
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_friction_items"
down_revision: str | None = "0026_help_brain_pilot_readiness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "friction_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("screen", sa.String(length=120), nullable=False),
        sa.Column("issue", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="medium"),
        sa.Column("fix_recommendation", sa.Text(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_friction_items_severity",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_friction_items_screen", "friction_items", ["screen"])
    op.create_index("ix_friction_items_severity", "friction_items", ["severity"])
    op.create_index("ix_friction_items_discovered_at", "friction_items", ["discovered_at"])


def downgrade() -> None:
    op.drop_index("ix_friction_items_discovered_at", table_name="friction_items")
    op.drop_index("ix_friction_items_severity", table_name="friction_items")
    op.drop_index("ix_friction_items_screen", table_name="friction_items")
    op.drop_table("friction_items")
