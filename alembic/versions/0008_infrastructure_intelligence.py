"""infrastructure intelligence layer

Revision ID: 0008_infrastructure_intelligence
Revises: 0007_accounts_auth_flow
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_infrastructure_intelligence"
down_revision: str | None = "0007_accounts_auth_flow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "update proxies set status = 'warning' "
        "where status not in ('healthy', 'warning', 'critical', 'disabled')"
    )
    op.alter_column("proxies", "name", existing_type=sa.String(length=160), nullable=True)
    op.alter_column("proxies", "status", existing_type=sa.String(length=40), server_default="healthy")
    op.add_column("proxies", sa.Column("provider", sa.String(length=120), nullable=False, server_default="unknown"))
    op.add_column("proxies", sa.Column("host", sa.String(length=255), nullable=False, server_default="localhost"))
    op.add_column("proxies", sa.Column("port", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "proxies",
        sa.Column("base_username", sa.String(length=160), nullable=False, server_default="proxy_user"),
    )
    op.add_column(
        "proxies",
        sa.Column("session_suffix", sa.String(length=80), nullable=False, server_default="session_initial"),
    )
    op.add_column("proxies", sa.Column("previous_session_suffix", sa.String(length=80), nullable=True))
    op.add_column(
        "proxies",
        sa.Column("encrypted_password", sa.Text(), nullable=False, server_default="enc:v1:placeholder"),
    )
    op.add_column(
        "proxies",
        sa.Column(
            "generated_username",
            sa.String(length=255),
            nullable=False,
            server_default="proxy_user-session_initial",
        ),
    )
    op.add_column("proxies", sa.Column("health_score", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("proxies", sa.Column("target_country", sa.String(length=120), nullable=True))
    op.add_column("proxies", sa.Column("target_state", sa.String(length=120), nullable=True))
    op.add_column("proxies", sa.Column("target_city", sa.String(length=120), nullable=True))
    op.add_column("proxies", sa.Column("detected_country", sa.String(length=120), nullable=True))
    op.add_column("proxies", sa.Column("detected_state", sa.String(length=120), nullable=True))
    op.add_column("proxies", sa.Column("detected_city", sa.String(length=120), nullable=True))
    op.add_column("proxies", sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proxies", sa.Column("last_rotation", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proxies", sa.Column("last_successful_rotation", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proxies", sa.Column("rotation_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("proxies", sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("proxies", sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("proxies", sa.Column("connection_test_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("proxies", sa.Column("location_mismatch_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("proxies", sa.Column("rotation_success_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("proxies", sa.Column("rotation_failure_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("proxies", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_proxies_status",
        "proxies",
        "status in ('healthy', 'warning', 'critical', 'disabled')",
    )
    op.create_check_constraint("ck_proxies_health_score", "proxies", "health_score >= 0 and health_score <= 100")
    op.create_check_constraint("ck_proxies_port", "proxies", "port >= 0 and port <= 65535")
    op.create_index("ix_proxies_provider", "proxies", ["provider"], unique=False)
    op.create_index("ix_proxies_status", "proxies", ["status"], unique=False)
    op.create_index("ix_proxies_health_score", "proxies", ["health_score"], unique=False)
    op.create_index(
        "ix_proxies_target_location",
        "proxies",
        ["target_country", "target_state", "target_city"],
        unique=False,
    )

    op.create_table(
        "proxy_rotation_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("proxy_id", sa.Integer(), nullable=False),
        sa.Column("previous_session_suffix", sa.String(length=80), nullable=True),
        sa.Column("new_session_suffix", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("detected_country", sa.String(length=120), nullable=True),
        sa.Column("detected_state", sa.String(length=120), nullable=True),
        sa.Column("detected_city", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('started', 'succeeded', 'failed', 'rolled_back')",
            name="ck_proxy_rotation_history_status",
        ),
        sa.ForeignKeyConstraint(["proxy_id"], ["proxies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_proxy_rotation_history_proxy_id", "proxy_rotation_history", ["proxy_id"], unique=False)
    op.create_index("ix_proxy_rotation_history_status", "proxy_rotation_history", ["status"], unique=False)
    op.create_index("ix_proxy_rotation_history_created_at", "proxy_rotation_history", ["created_at"], unique=False)

    op.execute(
        "update incidents set status = 'open' "
        "where status not in ('open', 'in_progress', 'resolved', 'closed')"
    )
    op.alter_column("incidents", "name", existing_type=sa.String(length=160), nullable=True)
    op.alter_column("incidents", "status", existing_type=sa.String(length=40), server_default="open")
    op.add_column(
        "incidents",
        sa.Column("title", sa.String(length=200), nullable=False, server_default="Infrastructure incident"),
    )
    op.add_column("incidents", sa.Column("severity", sa.String(length=40), nullable=False, server_default="medium"))
    op.add_column("incidents", sa.Column("source_type", sa.String(length=80), nullable=True))
    op.add_column("incidents", sa.Column("source_id", sa.String(length=80), nullable=True))
    op.add_column("incidents", sa.Column("assigned_user_id", sa.Integer(), nullable=True))
    op.add_column("incidents", sa.Column("resolution_notes", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_incidents_assigned_user_id_users",
        "incidents",
        "users",
        ["assigned_user_id"],
        ["id"],
    )
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
    op.create_index("ix_incidents_status", "incidents", ["status"], unique=False)
    op.create_index("ix_incidents_severity", "incidents", ["severity"], unique=False)
    op.create_index("ix_incidents_source", "incidents", ["source_type", "source_id"], unique=False)
    op.create_index("ix_incidents_assigned_user_id", "incidents", ["assigned_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_incidents_assigned_user_id", table_name="incidents")
    op.drop_index("ix_incidents_source", table_name="incidents")
    op.drop_index("ix_incidents_severity", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_constraint("ck_incidents_status", "incidents", type_="check")
    op.drop_constraint("ck_incidents_severity", "incidents", type_="check")
    op.drop_constraint("fk_incidents_assigned_user_id_users", "incidents", type_="foreignkey")
    for column in ["resolved_at", "resolution_notes", "assigned_user_id", "source_id", "source_type", "severity", "title"]:
        op.drop_column("incidents", column)
    op.alter_column("incidents", "status", existing_type=sa.String(length=40), server_default="draft")
    op.alter_column("incidents", "name", existing_type=sa.String(length=160), nullable=False)

    op.drop_index("ix_proxy_rotation_history_created_at", table_name="proxy_rotation_history")
    op.drop_index("ix_proxy_rotation_history_status", table_name="proxy_rotation_history")
    op.drop_index("ix_proxy_rotation_history_proxy_id", table_name="proxy_rotation_history")
    op.drop_table("proxy_rotation_history")

    op.drop_index("ix_proxies_target_location", table_name="proxies")
    op.drop_index("ix_proxies_health_score", table_name="proxies")
    op.drop_index("ix_proxies_status", table_name="proxies")
    op.drop_index("ix_proxies_provider", table_name="proxies")
    op.drop_constraint("ck_proxies_port", "proxies", type_="check")
    op.drop_constraint("ck_proxies_health_score", "proxies", type_="check")
    op.drop_constraint("ck_proxies_status", "proxies", type_="check")
    for column in [
        "latency_ms",
        "rotation_failure_count",
        "rotation_success_count",
        "location_mismatch_count",
        "connection_test_count",
        "failure_count",
        "success_count",
        "rotation_count",
        "last_successful_rotation",
        "last_rotation",
        "last_health_check",
        "detected_city",
        "detected_state",
        "detected_country",
        "target_city",
        "target_state",
        "target_country",
        "health_score",
        "generated_username",
        "encrypted_password",
        "previous_session_suffix",
        "session_suffix",
        "base_username",
        "port",
        "host",
        "provider",
    ]:
        op.drop_column("proxies", column)
    op.alter_column("proxies", "status", existing_type=sa.String(length=40), server_default="draft")
    op.alter_column("proxies", "name", existing_type=sa.String(length=160), nullable=False)
