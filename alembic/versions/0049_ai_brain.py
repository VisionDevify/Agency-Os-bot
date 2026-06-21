"""ai brain audit logs

Revision ID: 0049_ai_brain
Revises: 0048_search_intel
Create Date: 2026-06-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_ai_brain"
down_revision = "0048_search_intel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("use_case", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("estimated_input_chars", sa.Integer(), nullable=False),
        sa.Column("estimated_output_chars", sa.Integer(), nullable=False),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('succeeded', 'failed', 'blocked_by_critic', 'fallback_used', 'not_configured', 'rate_limited', 'timeout')",
            name="ck_ai_audit_logs_status",
        ),
        sa.CheckConstraint("evidence_count >= 0", name="ck_ai_audit_logs_evidence_count"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_audit_logs_created_at", "ai_audit_logs", ["created_at"])
    op.create_index("ix_ai_audit_logs_status", "ai_audit_logs", ["status"])
    op.create_index("ix_ai_audit_logs_use_case", "ai_audit_logs", ["use_case"])


def downgrade() -> None:
    op.drop_index("ix_ai_audit_logs_use_case", table_name="ai_audit_logs")
    op.drop_index("ix_ai_audit_logs_status", table_name="ai_audit_logs")
    op.drop_index("ix_ai_audit_logs_created_at", table_name="ai_audit_logs")
    op.drop_table("ai_audit_logs")
