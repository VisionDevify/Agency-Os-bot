"""agency operations activation

Revision ID: 0013_ops_activation
Revises: 0012_delivery_attempts
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_ops_activation"
down_revision: str | None = "0012_delivery_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("language", sa.String(length=40), nullable=False, server_default="English"))
    op.add_column("users", sa.Column("country", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"))
    op.add_column("users", sa.Column("time_format", sa.String(length=8), nullable=False, server_default="12h"))
    op.create_check_constraint("ck_users_time_format", "users", "time_format in ('12h', '24h')")
    op.create_index("ix_users_language", "users", ["language"])
    op.create_index("ix_users_country", "users", ["country"])
    op.create_index("ix_users_timezone", "users", ["timezone"])

    op.create_table(
        "user_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="off_shift"),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"),
        sa.Column("shift_start_local", sa.Time(), nullable=True),
        sa.Column("shift_end_local", sa.Time(), nullable=True),
        sa.Column("quiet_hours_start_local", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end_local", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('on_shift', 'off_shift', 'away', 'vacation', 'unavailable')",
            name="ck_user_availability_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_availability_user_id", "user_availability", ["user_id"])
    op.create_index("ix_user_availability_status", "user_availability", ["status"])
    op.create_index("ix_user_availability_timezone", "user_availability", ["timezone"])

    op.add_column("tasks", sa.Column("proxy_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("last_escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_tasks_proxy_id_proxies", "tasks", "proxies", ["proxy_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(
        "fk_tasks_owner_user_id_users",
        "tasks",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tasks_proxy_id", "tasks", ["proxy_id"])
    op.create_index("ix_tasks_owner_user_id", "tasks", ["owner_user_id"])
    op.create_index("ix_tasks_escalation_level", "tasks", ["escalation_level"])

    op.add_column("incidents", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("last_escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_incidents_owner_user_id_users",
        "incidents",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_incidents_owner_user_id", "incidents", ["owner_user_id"])
    op.create_index("ix_incidents_escalation_level", "incidents", ["escalation_level"])

    op.create_table(
        "incident_timeline",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_timeline_incident_id", "incident_timeline", ["incident_id"])
    op.create_index("ix_incident_timeline_actor_user_id", "incident_timeline", ["actor_user_id"])
    op.create_index("ix_incident_timeline_event_type", "incident_timeline", ["event_type"])
    op.create_index("ix_incident_timeline_created_at", "incident_timeline", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_incident_timeline_created_at", table_name="incident_timeline")
    op.drop_index("ix_incident_timeline_event_type", table_name="incident_timeline")
    op.drop_index("ix_incident_timeline_actor_user_id", table_name="incident_timeline")
    op.drop_index("ix_incident_timeline_incident_id", table_name="incident_timeline")
    op.drop_table("incident_timeline")

    op.drop_index("ix_incidents_escalation_level", table_name="incidents")
    op.drop_index("ix_incidents_owner_user_id", table_name="incidents")
    op.drop_constraint("fk_incidents_owner_user_id_users", "incidents", type_="foreignkey")
    op.drop_column("incidents", "last_escalated_at")
    op.drop_column("incidents", "owner_user_id")

    op.drop_index("ix_tasks_escalation_level", table_name="tasks")
    op.drop_index("ix_tasks_owner_user_id", table_name="tasks")
    op.drop_index("ix_tasks_proxy_id", table_name="tasks")
    op.drop_constraint("fk_tasks_owner_user_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_proxy_id_proxies", "tasks", type_="foreignkey")
    op.drop_column("tasks", "last_escalated_at")
    op.drop_column("tasks", "escalation_level")
    op.drop_column("tasks", "blocked_reason")
    op.drop_column("tasks", "started_at")
    op.drop_column("tasks", "owner_user_id")
    op.drop_column("tasks", "proxy_id")

    op.drop_index("ix_user_availability_timezone", table_name="user_availability")
    op.drop_index("ix_user_availability_status", table_name="user_availability")
    op.drop_index("ix_user_availability_user_id", table_name="user_availability")
    op.drop_table("user_availability")

    op.drop_index("ix_users_timezone", table_name="users")
    op.drop_index("ix_users_country", table_name="users")
    op.drop_index("ix_users_language", table_name="users")
    op.drop_constraint("ck_users_time_format", "users", type_="check")
    op.drop_column("users", "time_format")
    op.drop_column("users", "timezone")
    op.drop_column("users", "country")
    op.drop_column("users", "language")
