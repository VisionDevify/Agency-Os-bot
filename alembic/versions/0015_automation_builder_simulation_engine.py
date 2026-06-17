"""automation builder simulation engine

Revision ID: 0015_automation_builder
Revises: 0014_intel_brain_v1
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_automation_builder"
down_revision: str | None = "0014_intel_brain_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSON_OBJECT = sa.text("'{}'::json")
JSON_ARRAY = sa.text("'[]'::json")


def upgrade() -> None:
    op.drop_constraint("ck_automation_rules_status", "automation_rules", type_="check")
    op.add_column("automation_rules", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "automation_rules",
        sa.Column("category", sa.String(length=40), nullable=False, server_default="system"),
    )
    op.add_column(
        "automation_rules",
        sa.Column("trigger_type", sa.String(length=120), nullable=False, server_default="manual"),
    )
    op.add_column(
        "automation_rules",
        sa.Column("trigger_config_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
    )
    op.add_column(
        "automation_rules",
        sa.Column("conditions_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
    )
    op.add_column(
        "automation_rules",
        sa.Column("actions_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
    )
    op.add_column(
        "automation_rules",
        sa.Column("rollback_plan_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
    )
    op.add_column(
        "automation_rules",
        sa.Column("risk_level", sa.String(length=40), nullable=False, server_default="low"),
    )
    op.add_column(
        "automation_rules",
        sa.Column("requires_owner_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("automation_rules", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.add_column("automation_rules", sa.Column("approved_by_user_id", sa.Integer(), nullable=True))
    op.add_column("automation_rules", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rules", sa.Column("last_simulated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_rules", sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_automation_rules_created_by_user_id_users",
        "automation_rules",
        "users",
        ["created_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_automation_rules_approved_by_user_id_users",
        "automation_rules",
        "users",
        ["approved_by_user_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_automation_rules_category",
        "automation_rules",
        "category in ('infrastructure', 'operations', 'notifications', 'reports', "
        "'intelligence', 'opportunities', 'system')",
    )
    op.create_check_constraint(
        "ck_automation_rules_status",
        "automation_rules",
        "status in ('draft', 'simulated', 'pending_approval', 'approved', 'active', "
        "'paused', 'retired', 'failed', 'disabled', 'archived')",
    )
    op.create_check_constraint(
        "ck_automation_rules_risk_level",
        "automation_rules",
        "risk_level in ('low', 'medium', 'high', 'critical')",
    )
    op.create_index("ix_automation_rules_category", "automation_rules", ["category"])
    op.create_index("ix_automation_rules_trigger_type", "automation_rules", ["trigger_type"])
    op.create_index("ix_automation_rules_risk_level", "automation_rules", ["risk_level"])
    op.create_index("ix_automation_rules_created_by_user_id", "automation_rules", ["created_by_user_id"])
    op.create_index("ix_automation_rules_approved_by_user_id", "automation_rules", ["approved_by_user_id"])

    op.drop_constraint("ck_automation_simulation_runs_status", "automation_simulation_runs", type_="check")
    op.add_column("automation_simulation_runs", sa.Column("automation_rule_id", sa.Integer(), nullable=True))
    op.add_column(
        "automation_simulation_runs",
        sa.Column("affected_entities_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
    )
    op.add_column(
        "automation_simulation_runs",
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
    )
    op.add_column("automation_simulation_runs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_automation_simulation_runs_rule_id_rules",
        "automation_simulation_runs",
        "automation_rules",
        ["automation_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_automation_simulation_runs_status",
        "automation_simulation_runs",
        "status in ('pending', 'running', 'succeeded', 'failed', 'expired', "
        "'draft', 'simulated', 'approved', 'rejected')",
    )
    op.create_index("ix_automation_simulation_runs_rule_id", "automation_simulation_runs", ["automation_rule_id"])
    op.create_index("ix_automation_simulation_runs_finished_at", "automation_simulation_runs", ["finished_at"])

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_rule_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("started_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_event_id", sa.Integer(), nullable=True),
        sa.Column("affected_entities_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
        sa.Column("result_summary_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rollback_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rollback_status", sa.String(length=40), nullable=False, server_default="not_needed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["automation_rule_id"], ["automation_rules.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["trigger_event_id"], ["event_logs.id"]),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped', 'rolled_back')",
            name="ck_automation_runs_status",
        ),
        sa.CheckConstraint(
            "rollback_status in ('not_needed', 'available', 'completed', 'failed')",
            name="ck_automation_runs_rollback_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_runs_rule_id", "automation_runs", ["automation_rule_id"])
    op.create_index("ix_automation_runs_status", "automation_runs", ["status"])
    op.create_index("ix_automation_runs_started_by_user_id", "automation_runs", ["started_by_user_id"])
    op.create_index("ix_automation_runs_started_at", "automation_runs", ["started_at"])
    op.create_index("ix_automation_runs_finished_at", "automation_runs", ["finished_at"])
    op.create_index("ix_automation_runs_trigger_event_id", "automation_runs", ["trigger_event_id"])

    op.create_table(
        "automation_run_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_run_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
        sa.Column("output_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["automation_run_id"], ["automation_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped', 'rolled_back')",
            name="ck_automation_run_steps_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_run_steps_run_id", "automation_run_steps", ["automation_run_id"])
    op.create_index("ix_automation_run_steps_action_type", "automation_run_steps", ["action_type"])
    op.create_index("ix_automation_run_steps_status", "automation_run_steps", ["status"])
    op.create_index("ix_automation_run_steps_entity", "automation_run_steps", ["entity_type", "entity_id"])
    op.create_index("ix_automation_run_steps_created_at", "automation_run_steps", ["created_at"])

    op.create_table(
        "automation_approvals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_rule_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["automation_rule_id"], ["automation_rules.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'expired')",
            name="ck_automation_approvals_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_approvals_rule_id", "automation_approvals", ["automation_rule_id"])
    op.create_index("ix_automation_approvals_requested_by_user_id", "automation_approvals", ["requested_by_user_id"])
    op.create_index("ix_automation_approvals_approved_by_user_id", "automation_approvals", ["approved_by_user_id"])
    op.create_index("ix_automation_approvals_status", "automation_approvals", ["status"])
    op.create_index("ix_automation_approvals_created_at", "automation_approvals", ["created_at"])
    op.create_index("ix_automation_approvals_expires_at", "automation_approvals", ["expires_at"])

    op.create_table(
        "automation_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_rule_id", sa.Integer(), nullable=False),
        sa.Column("schedule_type", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"),
        sa.Column("time_of_day_local", sa.String(length=10), nullable=True),
        sa.Column("day_of_week", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["automation_rule_id"], ["automation_rules.id"]),
        sa.CheckConstraint(
            "schedule_type in ('manual', 'hourly', 'daily', 'weekly', 'event_based')",
            name="ck_automation_schedules_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_schedules_rule_id", "automation_schedules", ["automation_rule_id"])
    op.create_index("ix_automation_schedules_type", "automation_schedules", ["schedule_type"])
    op.create_index("ix_automation_schedules_is_active", "automation_schedules", ["is_active"])
    op.create_index("ix_automation_schedules_next_run_at", "automation_schedules", ["next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_automation_schedules_next_run_at", table_name="automation_schedules")
    op.drop_index("ix_automation_schedules_is_active", table_name="automation_schedules")
    op.drop_index("ix_automation_schedules_type", table_name="automation_schedules")
    op.drop_index("ix_automation_schedules_rule_id", table_name="automation_schedules")
    op.drop_table("automation_schedules")

    op.drop_index("ix_automation_approvals_expires_at", table_name="automation_approvals")
    op.drop_index("ix_automation_approvals_created_at", table_name="automation_approvals")
    op.drop_index("ix_automation_approvals_status", table_name="automation_approvals")
    op.drop_index("ix_automation_approvals_approved_by_user_id", table_name="automation_approvals")
    op.drop_index("ix_automation_approvals_requested_by_user_id", table_name="automation_approvals")
    op.drop_index("ix_automation_approvals_rule_id", table_name="automation_approvals")
    op.drop_table("automation_approvals")

    op.drop_index("ix_automation_run_steps_created_at", table_name="automation_run_steps")
    op.drop_index("ix_automation_run_steps_entity", table_name="automation_run_steps")
    op.drop_index("ix_automation_run_steps_status", table_name="automation_run_steps")
    op.drop_index("ix_automation_run_steps_action_type", table_name="automation_run_steps")
    op.drop_index("ix_automation_run_steps_run_id", table_name="automation_run_steps")
    op.drop_table("automation_run_steps")

    op.drop_index("ix_automation_runs_trigger_event_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_finished_at", table_name="automation_runs")
    op.drop_index("ix_automation_runs_started_at", table_name="automation_runs")
    op.drop_index("ix_automation_runs_started_by_user_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_status", table_name="automation_runs")
    op.drop_index("ix_automation_runs_rule_id", table_name="automation_runs")
    op.drop_table("automation_runs")

    op.drop_index("ix_automation_simulation_runs_finished_at", table_name="automation_simulation_runs")
    op.drop_index("ix_automation_simulation_runs_rule_id", table_name="automation_simulation_runs")
    op.drop_constraint("ck_automation_simulation_runs_status", "automation_simulation_runs", type_="check")
    op.drop_constraint("fk_automation_simulation_runs_rule_id_rules", "automation_simulation_runs", type_="foreignkey")
    op.drop_column("automation_simulation_runs", "finished_at")
    op.drop_column("automation_simulation_runs", "warnings_json")
    op.drop_column("automation_simulation_runs", "affected_entities_json")
    op.drop_column("automation_simulation_runs", "automation_rule_id")
    op.create_check_constraint(
        "ck_automation_simulation_runs_status",
        "automation_simulation_runs",
        "status in ('draft', 'simulated', 'approved', 'rejected', 'expired')",
    )

    op.drop_index("ix_automation_rules_approved_by_user_id", table_name="automation_rules")
    op.drop_index("ix_automation_rules_created_by_user_id", table_name="automation_rules")
    op.drop_index("ix_automation_rules_risk_level", table_name="automation_rules")
    op.drop_index("ix_automation_rules_trigger_type", table_name="automation_rules")
    op.drop_index("ix_automation_rules_category", table_name="automation_rules")
    op.drop_constraint("ck_automation_rules_risk_level", "automation_rules", type_="check")
    op.drop_constraint("ck_automation_rules_status", "automation_rules", type_="check")
    op.drop_constraint("ck_automation_rules_category", "automation_rules", type_="check")
    op.drop_constraint("fk_automation_rules_approved_by_user_id_users", "automation_rules", type_="foreignkey")
    op.drop_constraint("fk_automation_rules_created_by_user_id_users", "automation_rules", type_="foreignkey")
    op.drop_column("automation_rules", "last_run_at")
    op.drop_column("automation_rules", "last_simulated_at")
    op.drop_column("automation_rules", "approved_at")
    op.drop_column("automation_rules", "approved_by_user_id")
    op.drop_column("automation_rules", "created_by_user_id")
    op.drop_column("automation_rules", "requires_owner_approval")
    op.drop_column("automation_rules", "risk_level")
    op.drop_column("automation_rules", "rollback_plan_json")
    op.drop_column("automation_rules", "actions_json")
    op.drop_column("automation_rules", "conditions_json")
    op.drop_column("automation_rules", "trigger_config_json")
    op.drop_column("automation_rules", "trigger_type")
    op.drop_column("automation_rules", "category")
    op.drop_column("automation_rules", "description")
    op.create_check_constraint(
        "ck_automation_rules_status",
        "automation_rules",
        "status in ('draft', 'active', 'disabled', 'archived')",
    )
