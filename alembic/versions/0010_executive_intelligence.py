"""executive intelligence persistence

Revision ID: 0010_executive_intelligence
Revises: 0009_operations_command_layer
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_executive_intelligence"
down_revision: str | None = "0009_operations_command_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_logs_event_type", "event_logs", ["event_type"])
    op.create_index("ix_event_logs_actor_user_id", "event_logs", ["actor_user_id"])
    op.create_index("ix_event_logs_entity", "event_logs", ["entity_type", "entity_id"])
    op.create_index("ix_event_logs_created_at", "event_logs", ["created_at"])

    op.create_table(
        "daily_briefings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("generated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("agency_health_score", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("recommendations_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_briefings_briefing_date", "daily_briefings", ["briefing_date"])
    op.create_index("ix_daily_briefings_generated_by_user_id", "daily_briefings", ["generated_by_user_id"])
    op.create_index("ix_daily_briefings_created_at", "daily_briefings", ["created_at"])

    op.create_table(
        "accountability_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("roles_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("assigned_open_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_tasks_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assigned_open_incidents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_incidents_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accountability_snapshots_snapshot_date", "accountability_snapshots", ["snapshot_date"])
    op.create_index("ix_accountability_snapshots_user_id", "accountability_snapshots", ["user_id"])
    op.create_index(
        "ix_accountability_snapshots_date_user",
        "accountability_snapshots",
        ["snapshot_date", "user_id"],
    )
    op.create_index("ix_accountability_snapshots_created_at", "accountability_snapshots", ["created_at"])

    op.create_table(
        "notification_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("telegram_chat_id", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "target_type in ('telegram_user', 'telegram_group', 'telegram_channel')",
            name="ck_notification_targets_target_type",
        ),
        sa.CheckConstraint(
            "purpose in ('owner', 'operations', 'incidents', 'automation_logs', 'testing')",
            name="ck_notification_targets_purpose",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_targets_name", "notification_targets", ["name"])
    op.create_index("ix_notification_targets_target_type", "notification_targets", ["target_type"])
    op.create_index("ix_notification_targets_purpose", "notification_targets", ["purpose"])
    op.create_index("ix_notification_targets_is_active", "notification_targets", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_notification_targets_is_active", table_name="notification_targets")
    op.drop_index("ix_notification_targets_purpose", table_name="notification_targets")
    op.drop_index("ix_notification_targets_target_type", table_name="notification_targets")
    op.drop_index("ix_notification_targets_name", table_name="notification_targets")
    op.drop_table("notification_targets")

    op.drop_index("ix_accountability_snapshots_created_at", table_name="accountability_snapshots")
    op.drop_index("ix_accountability_snapshots_date_user", table_name="accountability_snapshots")
    op.drop_index("ix_accountability_snapshots_user_id", table_name="accountability_snapshots")
    op.drop_index("ix_accountability_snapshots_snapshot_date", table_name="accountability_snapshots")
    op.drop_table("accountability_snapshots")

    op.drop_index("ix_daily_briefings_created_at", table_name="daily_briefings")
    op.drop_index("ix_daily_briefings_generated_by_user_id", table_name="daily_briefings")
    op.drop_index("ix_daily_briefings_briefing_date", table_name="daily_briefings")
    op.drop_table("daily_briefings")

    op.drop_index("ix_event_logs_created_at", table_name="event_logs")
    op.drop_index("ix_event_logs_entity", table_name="event_logs")
    op.drop_index("ix_event_logs_actor_user_id", table_name="event_logs")
    op.drop_index("ix_event_logs_event_type", table_name="event_logs")
    op.drop_table("event_logs")
