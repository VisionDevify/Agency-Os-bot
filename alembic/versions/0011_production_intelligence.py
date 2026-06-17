"""production intelligence layer

Revision ID: 0011_production_intelligence
Revises: 0010_executive_intelligence
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_production_intelligence"
down_revision: str | None = "0010_executive_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notification_targets", sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("automation_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('draft', 'active', 'disabled', 'archived')",
            name="ck_automation_rules_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_rules_name", "automation_rules", ["name"])
    op.create_index("ix_automation_rules_automation_type", "automation_rules", ["automation_type"])
    op.create_index("ix_automation_rules_status", "automation_rules", ["status"])

    op.create_table(
        "automation_simulation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_name", sa.String(length=160), nullable=False),
        sa.Column("automation_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="simulated"),
        sa.Column("simulated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("target_scope", sa.String(length=160), nullable=False),
        sa.Column("would_trigger_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("would_succeed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("would_fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impact_summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("risk_level", sa.String(length=40), nullable=False, server_default="low"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["simulated_by_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "status in ('draft', 'simulated', 'approved', 'rejected', 'expired')",
            name="ck_automation_simulation_runs_status",
        ),
        sa.CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_automation_simulation_runs_risk_level",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_automation_simulation_runs_automation_type",
        "automation_simulation_runs",
        ["automation_type"],
    )
    op.create_index("ix_automation_simulation_runs_status", "automation_simulation_runs", ["status"])
    op.create_index("ix_automation_simulation_runs_risk_level", "automation_simulation_runs", ["risk_level"])
    op.create_index(
        "ix_automation_simulation_runs_simulated_by_user_id",
        "automation_simulation_runs",
        ["simulated_by_user_id"],
    )
    op.create_index("ix_automation_simulation_runs_created_at", "automation_simulation_runs", ["created_at"])
    op.create_index("ix_automation_simulation_runs_expires_at", "automation_simulation_runs", ["expires_at"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="info"),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("generated_from_event_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generated_from_event_id"], ["event_logs.id"]),
        sa.CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_recommendations_severity",
        ),
        sa.CheckConstraint(
            "status in ('open', 'acknowledged', 'dismissed', 'resolved')",
            name="ck_recommendations_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendations_type", "recommendations", ["recommendation_type"])
    op.create_index("ix_recommendations_severity", "recommendations", ["severity"])
    op.create_index("ix_recommendations_status", "recommendations", ["status"])
    op.create_index("ix_recommendations_entity", "recommendations", ["entity_type", "entity_id"])
    op.create_index("ix_recommendations_generated_from_event_id", "recommendations", ["generated_from_event_id"])
    op.create_index("ix_recommendations_created_at", "recommendations", ["created_at"])

    op.create_table(
        "system_heartbeats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_name"),
    )
    op.create_index("ix_system_heartbeats_service_name", "system_heartbeats", ["service_name"], unique=True)
    op.create_index("ix_system_heartbeats_status", "system_heartbeats", ["status"])
    op.create_index("ix_system_heartbeats_last_seen_at", "system_heartbeats", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_system_heartbeats_last_seen_at", table_name="system_heartbeats")
    op.drop_index("ix_system_heartbeats_status", table_name="system_heartbeats")
    op.drop_index("ix_system_heartbeats_service_name", table_name="system_heartbeats")
    op.drop_table("system_heartbeats")

    op.drop_index("ix_recommendations_created_at", table_name="recommendations")
    op.drop_index("ix_recommendations_generated_from_event_id", table_name="recommendations")
    op.drop_index("ix_recommendations_entity", table_name="recommendations")
    op.drop_index("ix_recommendations_status", table_name="recommendations")
    op.drop_index("ix_recommendations_severity", table_name="recommendations")
    op.drop_index("ix_recommendations_type", table_name="recommendations")
    op.drop_table("recommendations")

    op.drop_index("ix_automation_simulation_runs_expires_at", table_name="automation_simulation_runs")
    op.drop_index("ix_automation_simulation_runs_created_at", table_name="automation_simulation_runs")
    op.drop_index("ix_automation_simulation_runs_simulated_by_user_id", table_name="automation_simulation_runs")
    op.drop_index("ix_automation_simulation_runs_risk_level", table_name="automation_simulation_runs")
    op.drop_index("ix_automation_simulation_runs_status", table_name="automation_simulation_runs")
    op.drop_index("ix_automation_simulation_runs_automation_type", table_name="automation_simulation_runs")
    op.drop_table("automation_simulation_runs")

    op.drop_index("ix_automation_rules_status", table_name="automation_rules")
    op.drop_index("ix_automation_rules_automation_type", table_name="automation_rules")
    op.drop_index("ix_automation_rules_name", table_name="automation_rules")
    op.drop_table("automation_rules")

    op.drop_column("notification_targets", "last_tested_at")
