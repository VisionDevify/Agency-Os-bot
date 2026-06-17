"""user admin metadata

Revision ID: 0004_user_admin_metadata
Revises: 0003_add_missing_timestamps
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_user_admin_metadata"
down_revision: str | None = "0003_add_missing_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=160), nullable=True))
    op.add_column("users", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_seen")
    op.drop_column("users", "display_name")
