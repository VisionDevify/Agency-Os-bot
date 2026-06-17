"""add missing timestamp columns

Revision ID: 0003_add_missing_timestamps
Revises: 0002_persistent_auth_audit
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_missing_timestamps"
down_revision: str | None = "0002_persistent_auth_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "audit_logs",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "updated_at")
    op.drop_column("users", "updated_at")
