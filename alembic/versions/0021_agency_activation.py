"""agency activation state

Revision ID: 0021_agency_activation
Revises: 0020_setup_wizard
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_agency_activation"
down_revision: str | None = "0020_setup_wizard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agency_activation_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("models_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("teams_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creators_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opportunities_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notifications_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("readiness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blockers_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("recommendations_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "readiness_score >= 0 and readiness_score <= 100",
            name="ck_agency_activation_readiness_score",
        ),
        sa.CheckConstraint("models_ready >= 0 and models_ready <= 100", name="ck_agency_activation_models_ready"),
        sa.CheckConstraint("accounts_ready >= 0 and accounts_ready <= 100", name="ck_agency_activation_accounts_ready"),
        sa.CheckConstraint("teams_ready >= 0 and teams_ready <= 100", name="ck_agency_activation_teams_ready"),
        sa.CheckConstraint("creators_ready >= 0 and creators_ready <= 100", name="ck_agency_activation_creators_ready"),
        sa.CheckConstraint(
            "opportunities_ready >= 0 and opportunities_ready <= 100",
            name="ck_agency_activation_opportunities_ready",
        ),
        sa.CheckConstraint(
            "notifications_ready >= 0 and notifications_ready <= 100",
            name="ck_agency_activation_notifications_ready",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agency_activation_states_updated_at", "agency_activation_states", ["updated_at"])
    op.create_index("ix_agency_activation_states_readiness_score", "agency_activation_states", ["readiness_score"])


def downgrade() -> None:
    op.drop_index("ix_agency_activation_states_readiness_score", table_name="agency_activation_states")
    op.drop_index("ix_agency_activation_states_updated_at", table_name="agency_activation_states")
    op.drop_table("agency_activation_states")
