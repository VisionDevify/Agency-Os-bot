"""constrain user status values

Revision ID: 0005_user_status_check
Revises: 0004_user_admin_metadata
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_user_status_check"
down_revision: str | None = "0004_user_admin_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status in ('pending', 'active', 'disabled', 'denied')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_status", "users", type_="check")
