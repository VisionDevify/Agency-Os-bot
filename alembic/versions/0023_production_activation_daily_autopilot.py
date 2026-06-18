"""production activation daily autopilot

Revision ID: 0023_activation_autopilot
Revises: 0022_autonomous_operations
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_activation_autopilot"
down_revision: str | None = "0022_autonomous_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activation_blocker_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_code", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("entity_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('skipped', 'not_needed')",
            name="ck_activation_blocker_decisions_status",
        ),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "blocker_code",
            "entity_type",
            "entity_id",
            name="uq_activation_blocker_decisions_key",
        ),
    )
    op.create_index(
        "ix_activation_blocker_decisions_blocker_code",
        "activation_blocker_decisions",
        ["blocker_code"],
    )
    op.create_index(
        "ix_activation_blocker_decisions_decided_by",
        "activation_blocker_decisions",
        ["decided_by_user_id"],
    )
    op.create_index(
        "ix_activation_blocker_decisions_status",
        "activation_blocker_decisions",
        ["status"],
    )

    op.create_table(
        "daily_autopilot_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"),
        sa.Column("run_time_local", sa.String(length=10), nullable=False, server_default="09:00"),
        sa.Column("included_actions_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_daily_autopilot_settings_is_enabled",
        "daily_autopilot_settings",
        ["is_enabled"],
    )
    op.create_index(
        "ix_daily_autopilot_settings_next_run_at",
        "daily_autopilot_settings",
        ["next_run_at"],
    )
    op.create_index(
        "ix_daily_autopilot_settings_owner_user_id",
        "daily_autopilot_settings",
        ["owner_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_autopilot_settings_owner_user_id", table_name="daily_autopilot_settings")
    op.drop_index("ix_daily_autopilot_settings_next_run_at", table_name="daily_autopilot_settings")
    op.drop_index("ix_daily_autopilot_settings_is_enabled", table_name="daily_autopilot_settings")
    op.drop_table("daily_autopilot_settings")
    op.drop_index("ix_activation_blocker_decisions_status", table_name="activation_blocker_decisions")
    op.drop_index("ix_activation_blocker_decisions_decided_by", table_name="activation_blocker_decisions")
    op.drop_index("ix_activation_blocker_decisions_blocker_code", table_name="activation_blocker_decisions")
    op.drop_table("activation_blocker_decisions")
