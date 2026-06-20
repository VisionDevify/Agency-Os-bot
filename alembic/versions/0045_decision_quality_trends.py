"""Add decision quality trends and predictive COO records.

Revision ID: 0045_decision_quality_trends
Revises: 0044_decision_memory
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0045_decision_quality_trends"
down_revision: str | None = "0044_decision_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_quality_trends",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("time_window", sa.String(length=20), nullable=False),
        sa.Column("decisions_shown", sa.Integer(), nullable=False),
        sa.Column("decisions_opened", sa.Integer(), nullable=False),
        sa.Column("decisions_acted_on", sa.Integer(), nullable=False),
        sa.Column("decisions_resolved", sa.Integer(), nullable=False),
        sa.Column("decisions_ignored", sa.Integer(), nullable=False),
        sa.Column("usefulness_score_avg", sa.Integer(), nullable=False),
        sa.Column("confidence_accuracy_avg", sa.Integer(), nullable=False),
        sa.Column("recommendation_score_avg", sa.Integer(), nullable=False),
        sa.Column("trend_direction", sa.String(length=40), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("time_window in ('daily', 'weekly', 'monthly')", name="ck_decision_quality_trends_window"),
        sa.CheckConstraint(
            "trend_direction in ('improving', 'stable', 'declining', 'insufficient_data')",
            name="ck_decision_quality_trends_direction",
        ),
        sa.CheckConstraint("decisions_shown >= 0", name="ck_decision_quality_trends_shown"),
        sa.CheckConstraint("decisions_opened >= 0", name="ck_decision_quality_trends_opened"),
        sa.CheckConstraint("decisions_acted_on >= 0", name="ck_decision_quality_trends_acted"),
        sa.CheckConstraint("decisions_resolved >= 0", name="ck_decision_quality_trends_resolved"),
        sa.CheckConstraint("decisions_ignored >= 0", name="ck_decision_quality_trends_ignored"),
        sa.CheckConstraint("usefulness_score_avg >= 0 and usefulness_score_avg <= 100", name="ck_decision_quality_trends_usefulness"),
        sa.CheckConstraint("confidence_accuracy_avg >= 0 and confidence_accuracy_avg <= 100", name="ck_decision_quality_trends_confidence"),
        sa.CheckConstraint("recommendation_score_avg >= 0 and recommendation_score_avg <= 100", name="ck_decision_quality_trends_recommendation"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category", "time_window", name="uq_decision_quality_trends_category_window"),
    )
    op.create_index("ix_decision_quality_trends_category", "decision_quality_trends", ["category"], unique=False)
    op.create_index("ix_decision_quality_trends_direction", "decision_quality_trends", ["trend_direction"], unique=False)
    op.create_index("ix_decision_quality_trends_window", "decision_quality_trends", ["time_window"], unique=False)

    op.create_table(
        "predictive_coo_predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prediction_title", sa.String(length=220), nullable=False),
        sa.Column("prediction_type", sa.String(length=60), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("recommended_next_action", sa.Text(), nullable=False),
        sa.Column("can_wait", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_on_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_key", sa.String(length=220), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "prediction_type in ('likely_next_priority', 'recurring_risk', 'likely_blocker', "
            "'upcoming_setup_need', 'stale_decision_warning', 'repeated_friction_warning')",
            name="ck_predictive_coo_predictions_type",
        ),
        sa.CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_predictive_coo_predictions_confidence"),
        sa.CheckConstraint(
            "status in ('shown', 'opened', 'helpful', 'not_helpful', 'remind_later', 'dismissed', "
            "'acted_on', 'proven_correct', 'proven_wrong')",
            name="ck_predictive_coo_predictions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictive_coo_predictions_type", "predictive_coo_predictions", ["prediction_type"], unique=False)
    op.create_index("ix_predictive_coo_predictions_status", "predictive_coo_predictions", ["status"], unique=False)
    op.create_index("ix_predictive_coo_predictions_created_at", "predictive_coo_predictions", ["created_at"], unique=False)
    op.create_index("ix_predictive_coo_predictions_evidence_key", "predictive_coo_predictions", ["evidence_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_predictive_coo_predictions_evidence_key", table_name="predictive_coo_predictions")
    op.drop_index("ix_predictive_coo_predictions_created_at", table_name="predictive_coo_predictions")
    op.drop_index("ix_predictive_coo_predictions_status", table_name="predictive_coo_predictions")
    op.drop_index("ix_predictive_coo_predictions_type", table_name="predictive_coo_predictions")
    op.drop_table("predictive_coo_predictions")
    op.drop_index("ix_decision_quality_trends_window", table_name="decision_quality_trends")
    op.drop_index("ix_decision_quality_trends_direction", table_name="decision_quality_trends")
    op.drop_index("ix_decision_quality_trends_category", table_name="decision_quality_trends")
    op.drop_table("decision_quality_trends")
