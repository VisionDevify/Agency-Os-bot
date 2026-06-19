"""Track temporary bot navigation messages for chat cleanup."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_chat_cleanup"
down_revision: str | None = "0033_proxy_session_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("message_type", sa.String(length=40), nullable=False),
        sa.Column("page", sa.String(length=160), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("delete_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_error", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "message_type in ("
            "'temporary_navigation',"
            "'persistent_alert',"
            "'persistent_report',"
            "'persistent_approval',"
            "'persistent_export',"
            "'error_fallback'"
            ")",
            name="ck_bot_chat_messages_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bot_chat_messages_chat_user", "bot_chat_messages", ["chat_id", "user_id"])
    op.create_index(
        "ix_bot_chat_messages_message",
        "bot_chat_messages",
        ["chat_id", "message_id"],
    )
    op.create_index(
        "ix_bot_chat_messages_type_active",
        "bot_chat_messages",
        ["message_type", "is_active"],
    )

    op.create_table(
        "chat_cleanup_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("clean_on_start", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_cleanup_preferences_chat_user",
        "chat_cleanup_preferences",
        ["chat_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_cleanup_preferences_chat_user", table_name="chat_cleanup_preferences")
    op.drop_table("chat_cleanup_preferences")
    op.drop_index("ix_bot_chat_messages_type_active", table_name="bot_chat_messages")
    op.drop_index("ix_bot_chat_messages_message", table_name="bot_chat_messages")
    op.drop_index("ix_bot_chat_messages_chat_user", table_name="bot_chat_messages")
    op.drop_table("bot_chat_messages")
