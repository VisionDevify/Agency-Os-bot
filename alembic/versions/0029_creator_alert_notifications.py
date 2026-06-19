"""creator alert notifications

Revision ID: 0029_creator_alert_notifications
Revises: 0028_callback_error_logs
Create Date: 2026-06-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0029_creator_alert_notifications"
down_revision: str | None = "0028_callback_error_logs"
branch_labels: str | None = None
depends_on: str | None = None


ALERT_GROUPS_SQL = "('hq', 'ops', 'alerts')"
PRIORITIES_SQL = "('low', 'normal', 'high', 'critical')"
ALERT_STATUSES_SQL = "('new', 'reviewed', 'archived')"
PLATFORMS_SQL = "('x', 'instagram', 'other')"


def upgrade() -> None:
    op.add_column("creator_watches", sa.Column("alert_enabled", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("creator_watches", sa.Column("alert_priority", sa.String(length=40), server_default="normal", nullable=False))
    op.add_column("creator_watches", sa.Column("assigned_group", sa.String(length=40), server_default="alerts", nullable=False))
    op.create_check_constraint(
        "ck_creator_watches_alert_priority",
        "creator_watches",
        f"alert_priority in {PRIORITIES_SQL}",
    )
    op.create_check_constraint(
        "ck_creator_watches_assigned_group",
        "creator_watches",
        f"assigned_group in {ALERT_GROUPS_SQL}",
    )
    op.create_index("ix_creator_watches_alert_enabled", "creator_watches", ["alert_enabled"])
    op.create_index("ix_creator_watches_assigned_group", "creator_watches", ["assigned_group"])

    op.add_column("post_watches", sa.Column("priority", sa.String(length=40), server_default="normal", nullable=False))
    op.add_column("post_watches", sa.Column("alert_enabled", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("post_watches", sa.Column("assigned_group", sa.String(length=40), server_default="alerts", nullable=False))
    op.create_check_constraint("ck_post_watches_priority", "post_watches", f"priority in {PRIORITIES_SQL}")
    op.create_check_constraint("ck_post_watches_assigned_group", "post_watches", f"assigned_group in {ALERT_GROUPS_SQL}")
    op.create_index("ix_post_watches_priority", "post_watches", ["priority"])
    op.create_index("ix_post_watches_alert_enabled", "post_watches", ["alert_enabled"])
    op.create_index("ix_post_watches_assigned_group", "post_watches", ["assigned_group"])

    with op.batch_alter_table("notification_targets") as batch_op:
        batch_op.drop_constraint("ck_notification_targets_purpose", type_="check")
        batch_op.create_check_constraint(
            "ck_notification_targets_purpose",
            "purpose in ('hq', 'ops', 'alerts', 'owner', 'operations', 'incidents', 'automation_logs', 'testing')",
        )

    op.create_table(
        "creator_post_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_watch_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("post_reference", sa.String(length=500), nullable=False),
        sa.Column("priority", sa.String(length=40), server_default="normal", nullable=False),
        sa.Column("assigned_group", sa.String(length=40), server_default="alerts", nullable=False),
        sa.Column("assigned_chatter_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="new", nullable=False),
        sa.Column("suggested_angle", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"platform in {PLATFORMS_SQL}", name="ck_creator_post_alerts_platform"),
        sa.CheckConstraint(f"priority in {PRIORITIES_SQL}", name="ck_creator_post_alerts_priority"),
        sa.CheckConstraint(f"assigned_group in {ALERT_GROUPS_SQL}", name="ck_creator_post_alerts_assigned_group"),
        sa.CheckConstraint(f"status in {ALERT_STATUSES_SQL}", name="ck_creator_post_alerts_status"),
        sa.ForeignKeyConstraint(["creator_watch_id"], ["creator_watches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_chatter_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_creator_post_alerts_creator_watch_id", "creator_post_alerts", ["creator_watch_id"])
    op.create_index("ix_creator_post_alerts_opportunity_id", "creator_post_alerts", ["opportunity_id"])
    op.create_index("ix_creator_post_alerts_assigned_group", "creator_post_alerts", ["assigned_group"])
    op.create_index("ix_creator_post_alerts_priority", "creator_post_alerts", ["priority"])
    op.create_index("ix_creator_post_alerts_status", "creator_post_alerts", ["status"])
    op.create_index("ix_creator_post_alerts_created_at", "creator_post_alerts", ["created_at"])

    op.create_table(
        "own_post_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_watch_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("follow_up_task_id", sa.Integer(), nullable=True),
        sa.Column("model_brand_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("post_reference", sa.String(length=500), nullable=False),
        sa.Column("priority", sa.String(length=40), server_default="normal", nullable=False),
        sa.Column("assigned_group", sa.String(length=40), server_default="alerts", nullable=False),
        sa.Column("assigned_chatter_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="new", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"platform in {PLATFORMS_SQL}", name="ck_own_post_alerts_platform"),
        sa.CheckConstraint(f"priority in {PRIORITIES_SQL}", name="ck_own_post_alerts_priority"),
        sa.CheckConstraint(f"assigned_group in {ALERT_GROUPS_SQL}", name="ck_own_post_alerts_assigned_group"),
        sa.CheckConstraint(f"status in {ALERT_STATUSES_SQL}", name="ck_own_post_alerts_status"),
        sa.ForeignKeyConstraint(["post_watch_id"], ["post_watches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["follow_up_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_brand_id"], ["model_brands.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_chatter_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_own_post_alerts_post_watch_id", "own_post_alerts", ["post_watch_id"])
    op.create_index("ix_own_post_alerts_opportunity_id", "own_post_alerts", ["opportunity_id"])
    op.create_index("ix_own_post_alerts_follow_up_task_id", "own_post_alerts", ["follow_up_task_id"])
    op.create_index("ix_own_post_alerts_assigned_group", "own_post_alerts", ["assigned_group"])
    op.create_index("ix_own_post_alerts_priority", "own_post_alerts", ["priority"])
    op.create_index("ix_own_post_alerts_status", "own_post_alerts", ["status"])
    op.create_index("ix_own_post_alerts_created_at", "own_post_alerts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_own_post_alerts_created_at", table_name="own_post_alerts")
    op.drop_index("ix_own_post_alerts_status", table_name="own_post_alerts")
    op.drop_index("ix_own_post_alerts_priority", table_name="own_post_alerts")
    op.drop_index("ix_own_post_alerts_assigned_group", table_name="own_post_alerts")
    op.drop_index("ix_own_post_alerts_follow_up_task_id", table_name="own_post_alerts")
    op.drop_index("ix_own_post_alerts_opportunity_id", table_name="own_post_alerts")
    op.drop_index("ix_own_post_alerts_post_watch_id", table_name="own_post_alerts")
    op.drop_table("own_post_alerts")

    op.drop_index("ix_creator_post_alerts_created_at", table_name="creator_post_alerts")
    op.drop_index("ix_creator_post_alerts_status", table_name="creator_post_alerts")
    op.drop_index("ix_creator_post_alerts_priority", table_name="creator_post_alerts")
    op.drop_index("ix_creator_post_alerts_assigned_group", table_name="creator_post_alerts")
    op.drop_index("ix_creator_post_alerts_opportunity_id", table_name="creator_post_alerts")
    op.drop_index("ix_creator_post_alerts_creator_watch_id", table_name="creator_post_alerts")
    op.drop_table("creator_post_alerts")

    with op.batch_alter_table("notification_targets") as batch_op:
        batch_op.drop_constraint("ck_notification_targets_purpose", type_="check")
        batch_op.create_check_constraint(
            "ck_notification_targets_purpose",
            "purpose in ('owner', 'operations', 'incidents', 'automation_logs', 'testing')",
        )

    op.drop_index("ix_post_watches_assigned_group", table_name="post_watches")
    op.drop_index("ix_post_watches_alert_enabled", table_name="post_watches")
    op.drop_index("ix_post_watches_priority", table_name="post_watches")
    op.drop_constraint("ck_post_watches_assigned_group", "post_watches", type_="check")
    op.drop_constraint("ck_post_watches_priority", "post_watches", type_="check")
    op.drop_column("post_watches", "assigned_group")
    op.drop_column("post_watches", "alert_enabled")
    op.drop_column("post_watches", "priority")

    op.drop_index("ix_creator_watches_assigned_group", table_name="creator_watches")
    op.drop_index("ix_creator_watches_alert_enabled", table_name="creator_watches")
    op.drop_constraint("ck_creator_watches_assigned_group", "creator_watches", type_="check")
    op.drop_constraint("ck_creator_watches_alert_priority", "creator_watches", type_="check")
    op.drop_column("creator_watches", "assigned_group")
    op.drop_column("creator_watches", "alert_priority")
    op.drop_column("creator_watches", "alert_enabled")
