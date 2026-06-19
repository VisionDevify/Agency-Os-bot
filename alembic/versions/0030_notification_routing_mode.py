"""Add notification routing mode config.

Revision ID: 0030_notification_routing_mode
Revises: 0029_creator_alert_notifications
Create Date: 2026-06-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0030_notification_routing_mode"
down_revision: str | None = "0029_creator_alert_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_routing_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mode in ('2_group', '3_group')", name="ck_notification_routing_configs_mode"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_routing_configs_mode", "notification_routing_configs", ["mode"])
    op.execute(
        "insert into notification_routing_configs (mode, notes) "
        "values ('3_group', 'Default Fortuna HQ/Ops/Alerts routing.')"
    )


def downgrade() -> None:
    op.drop_index("ix_notification_routing_configs_mode", table_name="notification_routing_configs")
    op.drop_table("notification_routing_configs")
