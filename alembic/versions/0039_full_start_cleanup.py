"""Canonical chat cleanup tracking and navigation sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_full_start_cleanup"
down_revision: str | None = "0038_recovery_button_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MESSAGE_LABELS = (
    "temporary_navigation",
    "temporary_help",
    "temporary_status",
    "temporary_error",
    "persistent_alert",
    "persistent_report",
    "persistent_export",
    "persistent_approval",
    "persistent_incident",
    "persistent_delivery",
    "unknown_preserve",
)

DELETION_STATUSES = (
    "active",
    "cleanup_started",
    "deleted",
    "already_missing",
    "forbidden",
    "too_old",
    "failed",
    "preserved",
)


def _in_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "chat_cleanup_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cleanup_run_id", sa.String(length=80), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preserved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("concurrency_reuse_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed', 'reused')",
            name="ck_chat_cleanup_runs_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_cleanup_runs_chat", "chat_cleanup_runs", ["chat_id", "started_at"])
    op.create_index("ix_chat_cleanup_runs_run_id", "chat_cleanup_runs", ["cleanup_run_id"], unique=True)

    op.add_column("bot_chat_messages", sa.Column("message_label", sa.String(length=40), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("screen", sa.String(length=160), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("active_navigation", sa.Boolean(), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("deletion_status", sa.String(length=40), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("cleanup_batch_id", sa.String(length=80), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("cleanup_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("cleanup_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("cleanup_run_id", sa.String(length=80), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("navigation_version", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE bot_chat_messages
        SET
            message_label = CASE
                WHEN message_type = 'error_fallback' THEN 'temporary_error'
                WHEN message_type IN (
                    'temporary_navigation',
                    'persistent_alert',
                    'persistent_report',
                    'persistent_export',
                    'persistent_approval'
                ) THEN message_type
                ELSE 'unknown_preserve'
            END,
            screen = page,
            active_navigation = CASE
                WHEN is_active = true
                    AND deleted_at IS NULL
                    AND message_type = 'temporary_navigation'
                THEN true
                ELSE false
            END,
            deletion_status = CASE
                WHEN deleted_at IS NOT NULL THEN 'deleted'
                WHEN delete_error IS NOT NULL THEN 'failed'
                WHEN message_type LIKE 'persistent_%' THEN 'preserved'
                ELSE 'active'
            END,
            cleanup_started_at = delete_attempted_at,
            cleanup_completed_at = deleted_at,
            navigation_version = 1
        """
    )

    op.alter_column("bot_chat_messages", "message_label", nullable=False)
    op.alter_column("bot_chat_messages", "active_navigation", nullable=False)
    op.alter_column("bot_chat_messages", "deletion_status", nullable=False)
    op.alter_column("bot_chat_messages", "navigation_version", nullable=False)
    op.create_check_constraint(
        "ck_bot_chat_messages_label",
        "bot_chat_messages",
        f"message_label in ({_in_values(MESSAGE_LABELS)})",
    )
    op.create_check_constraint(
        "ck_bot_chat_messages_deletion_status",
        "bot_chat_messages",
        f"deletion_status in ({_in_values(DELETION_STATUSES)})",
    )
    op.create_index("ix_bot_chat_messages_label_cleanup", "bot_chat_messages", ["message_label", "deletion_status"])
    op.create_index(
        "ix_bot_chat_messages_active_nav",
        "bot_chat_messages",
        ["chat_id", "user_id", "active_navigation"],
    )
    op.create_index("ix_bot_chat_messages_cleanup_run", "bot_chat_messages", ["cleanup_run_id"])

    op.drop_index("ix_bot_chat_messages_type_active", table_name="bot_chat_messages")
    op.drop_constraint("ck_bot_chat_messages_type", "bot_chat_messages", type_="check")
    op.drop_column("bot_chat_messages", "delete_error")
    op.drop_column("bot_chat_messages", "deleted_at")
    op.drop_column("bot_chat_messages", "delete_attempted_at")
    op.drop_column("bot_chat_messages", "is_active")
    op.drop_column("bot_chat_messages", "page")
    op.drop_column("bot_chat_messages", "message_type")


def downgrade() -> None:
    op.add_column("bot_chat_messages", sa.Column("message_type", sa.String(length=40), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("page", sa.String(length=160), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("delete_attempted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bot_chat_messages", sa.Column("delete_error", sa.String(length=160), nullable=True))

    op.execute(
        """
        UPDATE bot_chat_messages
        SET
            message_type = CASE
                WHEN message_label = 'temporary_error' THEN 'error_fallback'
                WHEN message_label IN (
                    'temporary_navigation',
                    'persistent_alert',
                    'persistent_report',
                    'persistent_export',
                    'persistent_approval'
                ) THEN message_label
                ELSE 'persistent_report'
            END,
            page = screen,
            is_active = active_navigation,
            delete_attempted_at = cleanup_started_at,
            deleted_at = CASE WHEN deletion_status = 'deleted' THEN cleanup_completed_at ELSE NULL END,
            delete_error = CASE
                WHEN deletion_status IN ('failed', 'forbidden', 'too_old') THEN deletion_status
                ELSE NULL
            END
        """
    )

    op.alter_column("bot_chat_messages", "message_type", nullable=False)
    op.alter_column("bot_chat_messages", "is_active", nullable=False)
    op.create_check_constraint(
        "ck_bot_chat_messages_type",
        "bot_chat_messages",
        "message_type in ("
        "'temporary_navigation',"
        "'persistent_alert',"
        "'persistent_report',"
        "'persistent_approval',"
        "'persistent_export',"
        "'error_fallback'"
        ")",
    )
    op.create_index("ix_bot_chat_messages_type_active", "bot_chat_messages", ["message_type", "is_active"])

    op.drop_index("ix_bot_chat_messages_cleanup_run", table_name="bot_chat_messages")
    op.drop_index("ix_bot_chat_messages_active_nav", table_name="bot_chat_messages")
    op.drop_index("ix_bot_chat_messages_label_cleanup", table_name="bot_chat_messages")
    op.drop_constraint("ck_bot_chat_messages_deletion_status", "bot_chat_messages", type_="check")
    op.drop_constraint("ck_bot_chat_messages_label", "bot_chat_messages", type_="check")
    op.drop_column("bot_chat_messages", "navigation_version")
    op.drop_column("bot_chat_messages", "cleanup_run_id")
    op.drop_column("bot_chat_messages", "cleanup_completed_at")
    op.drop_column("bot_chat_messages", "cleanup_started_at")
    op.drop_column("bot_chat_messages", "cleanup_batch_id")
    op.drop_column("bot_chat_messages", "deletion_status")
    op.drop_column("bot_chat_messages", "active_navigation")
    op.drop_column("bot_chat_messages", "screen")
    op.drop_column("bot_chat_messages", "message_label")

    op.drop_index("ix_chat_cleanup_runs_run_id", table_name="chat_cleanup_runs")
    op.drop_index("ix_chat_cleanup_runs_chat", table_name="chat_cleanup_runs")
    op.drop_table("chat_cleanup_runs")
