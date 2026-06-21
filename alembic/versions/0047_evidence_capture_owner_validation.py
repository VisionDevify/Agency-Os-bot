"""Add evidence capture and owner validation records.

Revision ID: 0047_evidence_capture
Revises: 0046_reality_calibration
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0047_evidence_capture"
down_revision: str | None = "0046_reality_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_prediction_outcomes_outcome", "prediction_outcomes", type_="check")
    op.create_check_constraint(
        "ck_prediction_outcomes_outcome",
        "prediction_outcomes",
        "outcome in ('pending', 'partially_correct', 'proven_correct', 'proven_wrong', "
        "'unresolved', 'expired', 'not_enough_evidence')",
    )
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("linked_prediction_id", sa.Integer(), nullable=True),
        sa.Column("linked_decision_id", sa.String(length=220), nullable=True),
        sa.Column("linked_recommendation_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("evidence_strength", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "evidence_type in ('owner_note', 'owner_validation', 'system_record', 'uploaded_reference', 'operational_outcome')",
            name="ck_evidence_records_type",
        ),
        sa.CheckConstraint(
            "evidence_strength in ('weak', 'medium', 'strong')",
            name="ck_evidence_records_strength",
        ),
        sa.ForeignKeyConstraint(["linked_prediction_id"], ["predictive_coo_predictions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_recommendation_id"], ["recommendations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_records_type", "evidence_records", ["evidence_type"], unique=False)
    op.create_index("ix_evidence_records_category", "evidence_records", ["category"], unique=False)
    op.create_index("ix_evidence_records_prediction", "evidence_records", ["linked_prediction_id"], unique=False)
    op.create_index("ix_evidence_records_decision", "evidence_records", ["linked_decision_id"], unique=False)
    op.create_index("ix_evidence_records_recommendation", "evidence_records", ["linked_recommendation_id"], unique=False)
    op.create_table(
        "owner_validations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("linked_prediction_id", sa.Integer(), nullable=True),
        sa.Column("linked_decision_id", sa.String(length=220), nullable=True),
        sa.Column("linked_recommendation_id", sa.Integer(), nullable=True),
        sa.Column("evidence_record_id", sa.Integer(), nullable=True),
        sa.Column("validation_outcome", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "validation_outcome in ('correct', 'incorrect', 'partially_correct', 'too_early', 'add_evidence')",
            name="ck_owner_validations_outcome",
        ),
        sa.ForeignKeyConstraint(["evidence_record_id"], ["evidence_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_prediction_id"], ["predictive_coo_predictions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_recommendation_id"], ["recommendations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_owner_validations_prediction", "owner_validations", ["linked_prediction_id"], unique=False)
    op.create_index("ix_owner_validations_decision", "owner_validations", ["linked_decision_id"], unique=False)
    op.create_index("ix_owner_validations_recommendation", "owner_validations", ["linked_recommendation_id"], unique=False)
    op.create_index("ix_owner_validations_outcome", "owner_validations", ["validation_outcome"], unique=False)
    op.create_table(
        "knowledge_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("lesson", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("evidence_record_ids", sa.JSON(), nullable=False),
        sa.Column("source_summary", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "confidence in ('low', 'medium', 'high')",
            name="ck_knowledge_memory_confidence",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_memory_category", "knowledge_memory", ["category"], unique=False)
    op.create_index("ix_knowledge_memory_confidence", "knowledge_memory", ["confidence"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_memory_confidence", table_name="knowledge_memory")
    op.drop_index("ix_knowledge_memory_category", table_name="knowledge_memory")
    op.drop_table("knowledge_memory")
    op.drop_index("ix_owner_validations_outcome", table_name="owner_validations")
    op.drop_index("ix_owner_validations_recommendation", table_name="owner_validations")
    op.drop_index("ix_owner_validations_decision", table_name="owner_validations")
    op.drop_index("ix_owner_validations_prediction", table_name="owner_validations")
    op.drop_table("owner_validations")
    op.drop_index("ix_evidence_records_recommendation", table_name="evidence_records")
    op.drop_index("ix_evidence_records_decision", table_name="evidence_records")
    op.drop_index("ix_evidence_records_prediction", table_name="evidence_records")
    op.drop_index("ix_evidence_records_category", table_name="evidence_records")
    op.drop_index("ix_evidence_records_type", table_name="evidence_records")
    op.drop_table("evidence_records")
    op.drop_constraint("ck_prediction_outcomes_outcome", "prediction_outcomes", type_="check")
    op.create_check_constraint(
        "ck_prediction_outcomes_outcome",
        "prediction_outcomes",
        "outcome in ('pending', 'proven_correct', 'proven_wrong', 'unresolved', 'expired', 'not_enough_evidence')",
    )
