"""Add prediction outcome reality calibration records.

Revision ID: 0046_reality_calibration
Revises: 0045_decision_quality_trends
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0046_reality_calibration"
down_revision: str | None = "0045_decision_quality_trends"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prediction_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=False),
        sa.Column("prediction_type", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("confidence_at_prediction", sa.String(length=20), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("evidence_records", sa.JSON(), nullable=False),
        sa.Column("correction_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "outcome in ('pending', 'proven_correct', 'proven_wrong', 'unresolved', 'expired', 'not_enough_evidence')",
            name="ck_prediction_outcomes_outcome",
        ),
        sa.CheckConstraint(
            "confidence_at_prediction in ('low', 'medium', 'high')",
            name="ck_prediction_outcomes_confidence",
        ),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictive_coo_predictions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prediction_outcomes_prediction_id", "prediction_outcomes", ["prediction_id"], unique=False)
    op.create_index("ix_prediction_outcomes_prediction_type", "prediction_outcomes", ["prediction_type"], unique=False)
    op.create_index("ix_prediction_outcomes_category", "prediction_outcomes", ["category"], unique=False)
    op.create_index("ix_prediction_outcomes_outcome", "prediction_outcomes", ["outcome"], unique=False)
    op.create_index("ix_prediction_outcomes_evaluated_at", "prediction_outcomes", ["evaluated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_prediction_outcomes_evaluated_at", table_name="prediction_outcomes")
    op.drop_index("ix_prediction_outcomes_outcome", table_name="prediction_outcomes")
    op.drop_index("ix_prediction_outcomes_category", table_name="prediction_outcomes")
    op.drop_index("ix_prediction_outcomes_prediction_type", table_name="prediction_outcomes")
    op.drop_index("ix_prediction_outcomes_prediction_id", table_name="prediction_outcomes")
    op.drop_table("prediction_outcomes")
