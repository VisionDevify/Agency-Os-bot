"""team rollout human experience

Revision ID: 0017_team_rollout
Revises: 0016_learning_engine
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_team_rollout"
down_revision: str | None = "0016_learning_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_ARRAY = sa.text("'[]'::json")


def upgrade() -> None:
    op.create_table(
        "team_onboarding_checklists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("onboarded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("role_assigned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("timezone_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("availability_configured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("help_center_viewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("readiness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "readiness_score >= 0 and readiness_score <= 100",
            name="ck_team_onboarding_checklists_readiness_score",
        ),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_team_onboarding_checklists_user_id",
        "team_onboarding_checklists",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_team_onboarding_checklists_readiness_score",
        "team_onboarding_checklists",
        ["readiness_score"],
    )
    op.create_index(
        "ix_team_onboarding_checklists_onboarded",
        "team_onboarding_checklists",
        ["onboarded"],
    )

    op.create_table(
        "notification_digests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(length=80), nullable=False, server_default="operations"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=40), nullable=False, server_default="low"),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("items_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('open', 'sent', 'archived')",
            name="ck_notification_digests_status",
        ),
        sa.CheckConstraint(
            "priority in ('low', 'normal', 'critical')",
            name="ck_notification_digests_priority",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_digests_user_id", "notification_digests", ["user_id"])
    op.create_index("ix_notification_digests_purpose", "notification_digests", ["purpose"])
    op.create_index("ix_notification_digests_status", "notification_digests", ["status"])
    op.create_index("ix_notification_digests_priority", "notification_digests", ["priority"])
    op.create_index("ix_notification_digests_created_at", "notification_digests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_digests_created_at", table_name="notification_digests")
    op.drop_index("ix_notification_digests_priority", table_name="notification_digests")
    op.drop_index("ix_notification_digests_status", table_name="notification_digests")
    op.drop_index("ix_notification_digests_purpose", table_name="notification_digests")
    op.drop_index("ix_notification_digests_user_id", table_name="notification_digests")
    op.drop_table("notification_digests")
    op.drop_index("ix_team_onboarding_checklists_onboarded", table_name="team_onboarding_checklists")
    op.drop_index("ix_team_onboarding_checklists_readiness_score", table_name="team_onboarding_checklists")
    op.drop_index("ix_team_onboarding_checklists_user_id", table_name="team_onboarding_checklists")
    op.drop_table("team_onboarding_checklists")

