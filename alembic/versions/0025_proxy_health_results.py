"""proxy health check results

Revision ID: 0025_proxy_health_results
Revises: 0024_fortuna_coo
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_proxy_health_results"
down_revision: str | None = "0024_fortuna_coo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proxy_health_check_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proxy_id", sa.Integer(), nullable=False),
        sa.Column("check_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("detected_ip_masked", sa.String(length=80), nullable=True),
        sa.Column("detected_country", sa.String(length=120), nullable=True),
        sa.Column("detected_state", sa.String(length=120), nullable=True),
        sa.Column("detected_city", sa.String(length=120), nullable=True),
        sa.Column("target_match", sa.Boolean(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "check_type in ('simulated', 'connectivity', 'location', 'full')",
            name="ck_proxy_health_check_results_check_type",
        ),
        sa.CheckConstraint(
            "status in ('passed', 'failed', 'warning', 'skipped')",
            name="ck_proxy_health_check_results_status",
        ),
        sa.ForeignKeyConstraint(["proxy_id"], ["proxies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proxy_health_check_results_proxy_id", "proxy_health_check_results", ["proxy_id"])
    op.create_index("ix_proxy_health_check_results_check_type", "proxy_health_check_results", ["check_type"])
    op.create_index("ix_proxy_health_check_results_status", "proxy_health_check_results", ["status"])
    op.create_index("ix_proxy_health_check_results_created_at", "proxy_health_check_results", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_proxy_health_check_results_created_at", table_name="proxy_health_check_results")
    op.drop_index("ix_proxy_health_check_results_status", table_name="proxy_health_check_results")
    op.drop_index("ix_proxy_health_check_results_check_type", table_name="proxy_health_check_results")
    op.drop_index("ix_proxy_health_check_results_proxy_id", table_name="proxy_health_check_results")
    op.drop_table("proxy_health_check_results")
