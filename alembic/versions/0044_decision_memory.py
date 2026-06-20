"""Add decision memory.

Revision ID: 0044_decision_memory
Revises: 0043_recovery_timeouts
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0044_decision_memory"
down_revision: str | None = "0043_recovery_timeouts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.String(length=220), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_on_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ignored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=40), nullable=False),
        sa.Column("usefulness_score", sa.Integer(), nullable=False),
        sa.Column("owner_feedback", sa.Text(), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("source_records", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "category in ('recovery', 'system_health', 'telegram_bot', 'navigation', 'notification', "
            "'platform_connection', 'opportunity', 'social_intelligence', 'team', 'learning', "
            "'friction', 'setup', 'deployment', 'security', 'general')",
            name="ck_decision_memory_category",
        ),
        sa.CheckConstraint(
            "confidence in ('high', 'medium', 'low')",
            name="ck_decision_memory_confidence",
        ),
        sa.CheckConstraint(
            "lifecycle_status in ('active', 'opened', 'in_progress', 'waiting_for_evidence', 'resolved', 'dismissed', 'stale')",
            name="ck_decision_memory_lifecycle_status",
        ),
        sa.CheckConstraint(
            "outcome in ('shown', 'opened', 'acted_on', 'ignored', 'resolved', 'failed', 'stale', 'dismissed')",
            name="ck_decision_memory_outcome",
        ),
        sa.CheckConstraint(
            "severity in ('healthy', 'needs_review', 'needs_attention', 'critical')",
            name="ck_decision_memory_severity",
        ),
        sa.CheckConstraint("usefulness_score >= 0 and usefulness_score <= 100", name="ck_decision_memory_usefulness"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_memory_decision_id", "decision_memory", ["decision_id"], unique=True)
    op.create_index("ix_decision_memory_recommendation_id", "decision_memory", ["recommendation_id"], unique=False)
    op.create_index("ix_decision_memory_category", "decision_memory", ["category"], unique=False)
    op.create_index("ix_decision_memory_outcome", "decision_memory", ["outcome"], unique=False)
    op.create_index("ix_decision_memory_lifecycle", "decision_memory", ["lifecycle_status"], unique=False)
    op.create_index("ix_decision_memory_updated_at", "decision_memory", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_decision_memory_updated_at", table_name="decision_memory")
    op.drop_index("ix_decision_memory_lifecycle", table_name="decision_memory")
    op.drop_index("ix_decision_memory_outcome", table_name="decision_memory")
    op.drop_index("ix_decision_memory_category", table_name="decision_memory")
    op.drop_index("ix_decision_memory_recommendation_id", table_name="decision_memory")
    op.drop_index("ix_decision_memory_decision_id", table_name="decision_memory")
    op.drop_table("decision_memory")
