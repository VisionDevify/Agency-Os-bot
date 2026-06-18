"""callback error logs

Revision ID: 0028_callback_error_logs
Revises: 0027_friction_items
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0028_callback_error_logs"
down_revision: str | None = "0027_friction_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "callback_error_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("callback_data", sa.String(length=260), nullable=True),
        sa.Column("page", sa.String(length=220), nullable=True),
        sa.Column("affected_screen", sa.String(length=220), nullable=True),
        sa.Column("exception_type", sa.String(length=120), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_callback_error_logs_created_at", "callback_error_logs", ["created_at"])
    op.create_index("ix_callback_error_logs_exception_type", "callback_error_logs", ["exception_type"])
    op.create_index("ix_callback_error_logs_page", "callback_error_logs", ["page"])
    op.create_index("ix_callback_error_logs_user_id", "callback_error_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_callback_error_logs_user_id", table_name="callback_error_logs")
    op.drop_index("ix_callback_error_logs_page", table_name="callback_error_logs")
    op.drop_index("ix_callback_error_logs_exception_type", table_name="callback_error_logs")
    op.drop_index("ix_callback_error_logs_created_at", table_name="callback_error_logs")
    op.drop_table("callback_error_logs")
