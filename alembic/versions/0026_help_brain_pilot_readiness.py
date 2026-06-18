"""help brain pilot readiness

Revision ID: 0026_help_brain_pilot_readiness
Revises: 0025_proxy_health_results
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_help_brain_pilot_readiness"
down_revision: str | None = "0025_proxy_health_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "help_knowledge_base",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("role_scope", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("related_route", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic"),
    )
    op.create_index("ix_help_knowledge_base_topic", "help_knowledge_base", ["topic"], unique=True)
    op.create_index("ix_help_knowledge_base_role_scope", "help_knowledge_base", ["role_scope"])
    op.create_index("ix_help_knowledge_base_related_route", "help_knowledge_base", ["related_route"])

    op.create_table(
        "help_question_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("detected_intent", sa.String(length=120), nullable=False),
        sa.Column("answer_summary", sa.Text(), nullable=False),
        sa.Column("feedback", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "feedback is null or feedback in ('helpful', 'not_helpful', 'still_confused')",
            name="ck_help_question_logs_feedback",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_help_question_logs_user_id", "help_question_logs", ["user_id"])
    op.create_index("ix_help_question_logs_detected_intent", "help_question_logs", ["detected_intent"])
    op.create_index("ix_help_question_logs_feedback", "help_question_logs", ["feedback"])
    op.create_index("ix_help_question_logs_created_at", "help_question_logs", ["created_at"])

    op.create_table(
        "ui_self_test_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("screens_checked", sa.Integer(), nullable=False),
        sa.Column("failures_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('passed', 'warning', 'failed')", name="ck_ui_self_test_runs_status"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ui_self_test_runs_status", "ui_self_test_runs", ["status"])
    op.create_index("ix_ui_self_test_runs_requested_by_user_id", "ui_self_test_runs", ["requested_by_user_id"])
    op.create_index("ix_ui_self_test_runs_created_at", "ui_self_test_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ui_self_test_runs_created_at", table_name="ui_self_test_runs")
    op.drop_index("ix_ui_self_test_runs_requested_by_user_id", table_name="ui_self_test_runs")
    op.drop_index("ix_ui_self_test_runs_status", table_name="ui_self_test_runs")
    op.drop_table("ui_self_test_runs")

    op.drop_index("ix_help_question_logs_created_at", table_name="help_question_logs")
    op.drop_index("ix_help_question_logs_feedback", table_name="help_question_logs")
    op.drop_index("ix_help_question_logs_detected_intent", table_name="help_question_logs")
    op.drop_index("ix_help_question_logs_user_id", table_name="help_question_logs")
    op.drop_table("help_question_logs")

    op.drop_index("ix_help_knowledge_base_related_route", table_name="help_knowledge_base")
    op.drop_index("ix_help_knowledge_base_role_scope", table_name="help_knowledge_base")
    op.drop_index("ix_help_knowledge_base_topic", table_name="help_knowledge_base")
    op.drop_table("help_knowledge_base")
