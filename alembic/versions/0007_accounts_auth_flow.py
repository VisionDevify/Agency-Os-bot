"""accounts foundation and secure auth flow

Revision ID: 0007_accounts_auth_flow
Revises: 0006_model_brands
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_accounts_auth_flow"
down_revision: str | None = "0006_model_brands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("update accounts set status = 'warning' where status not in ('healthy', 'warning', 'critical', 'disabled', 'archived')")
    op.alter_column("accounts", "name", existing_type=sa.String(length=160), nullable=True)
    op.alter_column("accounts", "status", existing_type=sa.String(length=40), server_default="healthy")

    op.add_column("accounts", sa.Column("model_brand_id", sa.Integer(), nullable=True))
    op.add_column("accounts", sa.Column("platform", sa.String(length=40), nullable=False, server_default="other"))
    op.add_column("accounts", sa.Column("username", sa.String(length=160), nullable=False, server_default="unknown"))
    op.add_column("accounts", sa.Column("display_name", sa.String(length=160), nullable=False, server_default="Unknown"))
    op.add_column("accounts", sa.Column("account_url", sa.String(length=500), nullable=True))
    op.add_column(
        "accounts",
        sa.Column("auth_status", sa.String(length=40), nullable=False, server_default="not_connected"),
    )
    op.add_column("accounts", sa.Column("credential_ref", sa.String(length=255), nullable=True))
    op.add_column("accounts", sa.Column("connected_email_ref", sa.String(length=255), nullable=True))
    op.add_column("accounts", sa.Column("connected_phone_mask", sa.String(length=80), nullable=True))
    op.add_column("accounts", sa.Column("assigned_proxy_id", sa.Integer(), nullable=True))
    op.add_column("accounts", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        "fk_accounts_model_brand_id_model_brands",
        "accounts",
        "model_brands",
        ["model_brand_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_accounts_assigned_proxy_id_proxies",
        "accounts",
        "proxies",
        ["assigned_proxy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_accounts_platform",
        "accounts",
        "platform in ('instagram', 'x', 'onlyfans', 'email', 'other')",
    )
    op.create_check_constraint(
        "ck_accounts_status",
        "accounts",
        "status in ('healthy', 'warning', 'critical', 'disabled', 'archived')",
    )
    op.create_check_constraint(
        "ck_accounts_auth_status",
        "accounts",
        "auth_status in ('not_connected', 'connected', 'needs_login', 'needs_2fa', 'expired', 'locked')",
    )
    op.create_index("ix_accounts_model_brand_id", "accounts", ["model_brand_id"], unique=False)
    op.create_index("ix_accounts_platform", "accounts", ["platform"], unique=False)
    op.create_index("ix_accounts_status", "accounts", ["status"], unique=False)
    op.create_index("ix_accounts_auth_status", "accounts", ["auth_status"], unique=False)
    op.create_index("ix_accounts_username", "accounts", ["username"], unique=False)

    op.create_table(
        "account_auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("handled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'waiting_for_code', 'submitted', 'success', 'failed', 'expired', 'cancelled')",
            name="ck_account_auth_sessions_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["handled_by_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_account_auth_sessions_account_id",
        "account_auth_sessions",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_account_auth_sessions_status",
        "account_auth_sessions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_account_auth_sessions_expires_at",
        "account_auth_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_account_auth_sessions_requested_by_user_id",
        "account_auth_sessions",
        ["requested_by_user_id"],
        unique=False,
    )

    op.create_table(
        "account_verification_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("auth_session_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("code_type", sa.String(length=40), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "code_type in ('email', 'sms', 'authenticator', 'backup_code')",
            name="ck_account_verification_codes_code_type",
        ),
        sa.ForeignKeyConstraint(["auth_session_id"], ["account_auth_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_account_verification_codes_auth_session_id",
        "account_verification_codes",
        ["auth_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_account_verification_codes_expires_at",
        "account_verification_codes",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_account_verification_codes_expires_at", table_name="account_verification_codes")
    op.drop_index("ix_account_verification_codes_auth_session_id", table_name="account_verification_codes")
    op.drop_table("account_verification_codes")
    op.drop_index("ix_account_auth_sessions_requested_by_user_id", table_name="account_auth_sessions")
    op.drop_index("ix_account_auth_sessions_expires_at", table_name="account_auth_sessions")
    op.drop_index("ix_account_auth_sessions_status", table_name="account_auth_sessions")
    op.drop_index("ix_account_auth_sessions_account_id", table_name="account_auth_sessions")
    op.drop_table("account_auth_sessions")

    op.drop_index("ix_accounts_username", table_name="accounts")
    op.drop_index("ix_accounts_auth_status", table_name="accounts")
    op.drop_index("ix_accounts_status", table_name="accounts")
    op.drop_index("ix_accounts_platform", table_name="accounts")
    op.drop_index("ix_accounts_model_brand_id", table_name="accounts")
    op.drop_constraint("ck_accounts_auth_status", "accounts", type_="check")
    op.drop_constraint("ck_accounts_status", "accounts", type_="check")
    op.drop_constraint("ck_accounts_platform", "accounts", type_="check")
    op.drop_constraint("fk_accounts_assigned_proxy_id_proxies", "accounts", type_="foreignkey")
    op.drop_constraint("fk_accounts_model_brand_id_model_brands", "accounts", type_="foreignkey")

    for column in [
        "last_checked_at",
        "notes",
        "assigned_proxy_id",
        "connected_phone_mask",
        "connected_email_ref",
        "credential_ref",
        "auth_status",
        "account_url",
        "display_name",
        "username",
        "platform",
        "model_brand_id",
    ]:
        op.drop_column("accounts", column)
    op.alter_column("accounts", "status", existing_type=sa.String(length=40), server_default="draft")
    op.alter_column("accounts", "name", existing_type=sa.String(length=160), nullable=False)
