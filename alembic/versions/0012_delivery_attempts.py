"""notification delivery attempts

Revision ID: 0012_delivery_attempts
Revises: 0011_production_intelligence
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_delivery_attempts"
down_revision: str | None = "0011_production_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notification_target_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.ForeignKeyConstraint(["notification_target_id"], ["notification_targets.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status in ('pending', 'sent', 'failed', 'skipped')",
            name="ck_notification_delivery_attempts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_delivery_attempts_target_id",
        "notification_delivery_attempts",
        ["notification_target_id"],
    )
    op.create_index(
        "ix_notification_delivery_attempts_event_type",
        "notification_delivery_attempts",
        ["event_type"],
    )
    op.create_index("ix_notification_delivery_attempts_status", "notification_delivery_attempts", ["status"])
    op.create_index(
        "ix_notification_delivery_attempts_attempted_at",
        "notification_delivery_attempts",
        ["attempted_at"],
    )
    op.create_index("ix_notification_delivery_attempts_created_at", "notification_delivery_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_delivery_attempts_created_at", table_name="notification_delivery_attempts")
    op.drop_index("ix_notification_delivery_attempts_attempted_at", table_name="notification_delivery_attempts")
    op.drop_index("ix_notification_delivery_attempts_status", table_name="notification_delivery_attempts")
    op.drop_index("ix_notification_delivery_attempts_event_type", table_name="notification_delivery_attempts")
    op.drop_index("ix_notification_delivery_attempts_target_id", table_name="notification_delivery_attempts")
    op.drop_table("notification_delivery_attempts")
