"""autonomous operations workflow layer

Revision ID: 0022_autonomous_operations
Revises: 0021_agency_activation
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_autonomous_operations"
down_revision: str | None = "0021_agency_activation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operations_workflows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_type", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'ready', 'running', 'completed', 'blocked', 'failed', 'skipped')",
            name="ck_operations_workflows_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operations_workflows_type", "operations_workflows", ["workflow_type"])
    op.create_index("ix_operations_workflows_source", "operations_workflows", ["source_type", "source_id"])
    op.create_index("ix_operations_workflows_status", "operations_workflows", ["status"])
    op.create_index("ix_operations_workflows_updated_at", "operations_workflows", ["updated_at"])

    op.create_table(
        "operations_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.String(length=40), nullable=False),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'ready', 'running', 'completed', 'blocked', 'failed', 'skipped')",
            name="ck_operations_actions_status",
        ),
        sa.CheckConstraint(
            "priority in ('low', 'normal', 'high', 'urgent')",
            name="ck_operations_actions_priority",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["operations_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operations_actions_workflow_id", "operations_actions", ["workflow_id"])
    op.create_index("ix_operations_actions_status", "operations_actions", ["status"])
    op.create_index("ix_operations_actions_priority", "operations_actions", ["priority"])
    op.create_index("ix_operations_actions_assigned_user_id", "operations_actions", ["assigned_user_id"])
    op.create_index("ix_operations_actions_created_at", "operations_actions", ["created_at"])

    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reminder_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'completed', 'blocked', 'failed', 'skipped')",
            name="ck_follow_ups_status",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_follow_ups_source", "follow_ups", ["source_type", "source_id"])
    op.create_index("ix_follow_ups_status", "follow_ups", ["status"])
    op.create_index("ix_follow_ups_due_at", "follow_ups", ["due_at"])
    op.create_index("ix_follow_ups_assigned_user_id", "follow_ups", ["assigned_user_id"])


def downgrade() -> None:
    op.drop_index("ix_follow_ups_assigned_user_id", table_name="follow_ups")
    op.drop_index("ix_follow_ups_due_at", table_name="follow_ups")
    op.drop_index("ix_follow_ups_status", table_name="follow_ups")
    op.drop_index("ix_follow_ups_source", table_name="follow_ups")
    op.drop_table("follow_ups")
    op.drop_index("ix_operations_actions_created_at", table_name="operations_actions")
    op.drop_index("ix_operations_actions_assigned_user_id", table_name="operations_actions")
    op.drop_index("ix_operations_actions_priority", table_name="operations_actions")
    op.drop_index("ix_operations_actions_status", table_name="operations_actions")
    op.drop_index("ix_operations_actions_workflow_id", table_name="operations_actions")
    op.drop_table("operations_actions")
    op.drop_index("ix_operations_workflows_updated_at", table_name="operations_workflows")
    op.drop_index("ix_operations_workflows_status", table_name="operations_workflows")
    op.drop_index("ix_operations_workflows_source", table_name="operations_workflows")
    op.drop_index("ix_operations_workflows_type", table_name="operations_workflows")
    op.drop_table("operations_workflows")
