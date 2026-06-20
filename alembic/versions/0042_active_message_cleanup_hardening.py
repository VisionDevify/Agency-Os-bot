"""Add cleanup batch evidence fields.

Revision ID: 0042_active_cleanup
Revises: 0041_platform_connections
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0042_active_cleanup"
down_revision: str | None = "0041_platform_connections"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("chat_cleanup_runs", sa.Column("total_candidates", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("chat_cleanup_runs", sa.Column("remaining_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("chat_cleanup_runs", "remaining_count")
    op.drop_column("chat_cleanup_runs", "total_candidates")
