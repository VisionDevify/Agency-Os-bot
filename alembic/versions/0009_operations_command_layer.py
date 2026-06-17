"""operations command layer

Revision ID: 0009_operations_command_layer
Revises: 0008_infrastructure_intelligence
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_operations_command_layer"
down_revision: str | None = "0008_infrastructure_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("update tasks set status = 'open' where status not in ('open', 'in_progress', 'blocked', 'complete', 'archived')")
    op.alter_column("tasks", "name", existing_type=sa.String(length=160), nullable=True)
    op.alter_column("tasks", "status", existing_type=sa.String(length=40), server_default="open")
    op.add_column("tasks", sa.Column("title", sa.String(length=200), nullable=False, server_default="Task"))
    op.add_column("tasks", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("priority", sa.String(length=40), nullable=False, server_default="normal"))
    op.add_column("tasks", sa.Column("model_brand_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("account_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("assigned_to_user_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("update tasks set title = coalesce(name, title, 'Task')")
    op.create_foreign_key(
        "fk_tasks_model_brand_id_model_brands",
        "tasks",
        "model_brands",
        ["model_brand_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_account_id_accounts",
        "tasks",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_assigned_to_user_id_users",
        "tasks",
        "users",
        ["assigned_to_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_created_by_user_id_users",
        "tasks",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_tasks_status",
        "tasks",
        "status in ('open', 'in_progress', 'blocked', 'complete', 'archived')",
    )
    op.create_check_constraint(
        "ck_tasks_priority",
        "tasks",
        "priority in ('low', 'normal', 'high', 'urgent')",
    )
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_priority", "tasks", ["priority"], unique=False)
    op.create_index("ix_tasks_model_brand_id", "tasks", ["model_brand_id"], unique=False)
    op.create_index("ix_tasks_account_id", "tasks", ["account_id"], unique=False)
    op.create_index("ix_tasks_assigned_to_user_id", "tasks", ["assigned_to_user_id"], unique=False)
    op.create_index("ix_tasks_created_by_user_id", "tasks", ["created_by_user_id"], unique=False)
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"], unique=False)

    op.drop_constraint("ck_incidents_status", "incidents", type_="check")
    op.drop_constraint("ck_incidents_severity", "incidents", type_="check")
    op.execute("update incidents set status = 'investigating' where status = 'in_progress'")
    op.execute("update incidents set status = 'archived' where status = 'closed'")
    op.execute("update incidents set status = 'open' where status not in ('open', 'investigating', 'resolved', 'archived')")
    op.execute("update incidents set severity = 'info' where severity = 'low'")
    op.execute("update incidents set severity = 'warning' where severity in ('medium', 'high')")
    op.execute("update incidents set severity = 'warning' where severity not in ('info', 'warning', 'critical')")
    op.alter_column("incidents", "status", existing_type=sa.String(length=40), server_default="open")
    op.alter_column("incidents", "severity", existing_type=sa.String(length=40), server_default="warning")
    op.add_column("incidents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("model_brand_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("account_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("proxy_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("assigned_to_user_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("resolved_by_user_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "incidents",
        sa.Column("escalation_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.execute(
        "update incidents set proxy_id = source_id::integer "
        "where source_type = 'proxy' and source_id ~ '^[0-9]+$'"
    )
    op.execute("update incidents set assigned_to_user_id = assigned_user_id where assigned_user_id is not null")
    op.create_foreign_key(
        "fk_incidents_model_brand_id_model_brands",
        "incidents",
        "model_brands",
        ["model_brand_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_incidents_account_id_accounts",
        "incidents",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_incidents_proxy_id_proxies",
        "incidents",
        "proxies",
        ["proxy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_incidents_assigned_to_user_id_users",
        "incidents",
        "users",
        ["assigned_to_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_incidents_created_by_user_id_users",
        "incidents",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_incidents_resolved_by_user_id_users",
        "incidents",
        "users",
        ["resolved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_incidents_status",
        "incidents",
        "status in ('open', 'investigating', 'resolved', 'archived')",
    )
    op.create_check_constraint(
        "ck_incidents_severity",
        "incidents",
        "severity in ('info', 'warning', 'critical')",
    )
    op.create_check_constraint(
        "ck_incidents_source_type",
        "incidents",
        "source_type is null or source_type in ('manual', 'account', 'proxy', 'automation', 'system')",
    )
    op.create_index("ix_incidents_model_brand_id", "incidents", ["model_brand_id"], unique=False)
    op.create_index("ix_incidents_account_id", "incidents", ["account_id"], unique=False)
    op.create_index("ix_incidents_proxy_id", "incidents", ["proxy_id"], unique=False)
    op.create_index("ix_incidents_assigned_to_user_id", "incidents", ["assigned_to_user_id"], unique=False)
    op.create_index("ix_incidents_created_by_user_id", "incidents", ["created_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_incidents_created_by_user_id", table_name="incidents")
    op.drop_index("ix_incidents_assigned_to_user_id", table_name="incidents")
    op.drop_index("ix_incidents_proxy_id", table_name="incidents")
    op.drop_index("ix_incidents_account_id", table_name="incidents")
    op.drop_index("ix_incidents_model_brand_id", table_name="incidents")
    op.drop_constraint("ck_incidents_source_type", "incidents", type_="check")
    op.drop_constraint("ck_incidents_severity", "incidents", type_="check")
    op.drop_constraint("ck_incidents_status", "incidents", type_="check")
    op.drop_constraint("fk_incidents_resolved_by_user_id_users", "incidents", type_="foreignkey")
    op.drop_constraint("fk_incidents_created_by_user_id_users", "incidents", type_="foreignkey")
    op.drop_constraint("fk_incidents_assigned_to_user_id_users", "incidents", type_="foreignkey")
    op.drop_constraint("fk_incidents_proxy_id_proxies", "incidents", type_="foreignkey")
    op.drop_constraint("fk_incidents_account_id_accounts", "incidents", type_="foreignkey")
    op.drop_constraint("fk_incidents_model_brand_id_model_brands", "incidents", type_="foreignkey")
    op.execute("update incidents set status = 'in_progress' where status = 'investigating'")
    op.execute("update incidents set status = 'closed' where status = 'archived'")
    op.execute("update incidents set severity = 'low' where severity = 'info'")
    op.execute("update incidents set severity = 'medium' where severity = 'warning'")
    for column in [
        "escalation_history",
        "escalation_level",
        "resolved_by_user_id",
        "created_by_user_id",
        "assigned_to_user_id",
        "proxy_id",
        "account_id",
        "model_brand_id",
        "description",
    ]:
        op.drop_column("incidents", column)
    op.alter_column("incidents", "severity", existing_type=sa.String(length=40), server_default="medium")
    op.alter_column("incidents", "status", existing_type=sa.String(length=40), server_default="open")
    op.create_check_constraint(
        "ck_incidents_severity",
        "incidents",
        "severity in ('low', 'medium', 'high', 'critical')",
    )
    op.create_check_constraint(
        "ck_incidents_status",
        "incidents",
        "status in ('open', 'in_progress', 'resolved', 'closed')",
    )

    op.drop_index("ix_tasks_due_at", table_name="tasks")
    op.drop_index("ix_tasks_created_by_user_id", table_name="tasks")
    op.drop_index("ix_tasks_assigned_to_user_id", table_name="tasks")
    op.drop_index("ix_tasks_account_id", table_name="tasks")
    op.drop_index("ix_tasks_model_brand_id", table_name="tasks")
    op.drop_index("ix_tasks_priority", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_constraint("ck_tasks_priority", "tasks", type_="check")
    op.drop_constraint("ck_tasks_status", "tasks", type_="check")
    op.drop_constraint("fk_tasks_created_by_user_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_assigned_to_user_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_account_id_accounts", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_model_brand_id_model_brands", "tasks", type_="foreignkey")
    op.execute("update tasks set name = coalesce(name, title, 'Task')")
    for column in [
        "completed_at",
        "due_at",
        "created_by_user_id",
        "assigned_to_user_id",
        "account_id",
        "model_brand_id",
        "priority",
        "description",
        "title",
    ]:
        op.drop_column("tasks", column)
    op.alter_column("tasks", "status", existing_type=sa.String(length=40), server_default="draft")
    op.alter_column("tasks", "name", existing_type=sa.String(length=160), nullable=False)
