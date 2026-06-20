"""Add platform connections.

Revision ID: 0041_platform_connections
Revises: 0040_external_backup_storage
Create Date: 2026-06-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0041_platform_connections"
down_revision: str | None = "0040_external_backup_storage"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "platform_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="ready_to_connect"),
        sa.Column("website_reachable", sa.Boolean(), nullable=True),
        sa.Column("login_connected", sa.Boolean(), nullable=True),
        sa.Column("stats_available", sa.Boolean(), nullable=True),
        sa.Column("stats_fresh", sa.Boolean(), nullable=True),
        sa.Column("notifications_configured", sa.Boolean(), nullable=True),
        sa.Column("approved_method", sa.String(length=40), nullable=False, server_default="not_configured"),
        sa.Column("last_connection_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_stats_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notification_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "platform in ('instagram', 'x', 'onlyfans', 'telegram', 'email', 'backup_storage', 'system_alerts')",
            name="ck_platform_connections_platform",
        ),
        sa.CheckConstraint(
            "status in ('not_connected', 'ready_to_connect', 'connection_configured', 'connected', 'needs_review', 'failed')",
            name="ck_platform_connections_status",
        ),
        sa.CheckConstraint(
            "approved_method in ('manual', 'official_api', 'approved_connector', 'session_based', 'not_configured')",
            name="ck_platform_connections_approved_method",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", name="uq_platform_connections_platform"),
    )
    op.create_index("ix_platform_connections_platform", "platform_connections", ["platform"])
    op.create_index("ix_platform_connections_status", "platform_connections", ["status"])
    op.create_index("ix_platform_connections_approved_method", "platform_connections", ["approved_method"])


def downgrade() -> None:
    op.drop_index("ix_platform_connections_approved_method", table_name="platform_connections")
    op.drop_index("ix_platform_connections_status", table_name="platform_connections")
    op.drop_index("ix_platform_connections_platform", table_name="platform_connections")
    op.drop_table("platform_connections")
