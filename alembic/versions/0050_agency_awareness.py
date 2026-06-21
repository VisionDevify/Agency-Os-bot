"""agency awareness snapshots and manual records

Revision ID: 0050_agency_awareness
Revises: 0049_ai_brain
Create Date: 2026-06-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0050_agency_awareness"
down_revision = "0049_ai_brain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agency_manual_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain_id", sa.String(length=80), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "record_type in ('activity', 'blocker', 'note', 'win', 'loss', 'plan', 'update')",
            name="ck_agency_manual_records_type",
        ),
        sa.CheckConstraint(
            "confidence in ('low', 'medium', 'high')",
            name="ck_agency_manual_records_confidence",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agency_manual_records_created_at", "agency_manual_records", ["created_at"])
    op.create_index("ix_agency_manual_records_domain", "agency_manual_records", ["domain_id"])
    op.create_index("ix_agency_manual_records_type", "agency_manual_records", ["record_type"])

    op.create_table(
        "agency_awareness_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("overall_status", sa.String(length=40), nullable=False),
        sa.Column("active_domains", sa.JSON(), nullable=False),
        sa.Column("inactive_domains", sa.JSON(), nullable=False),
        sa.Column("missing_domains", sa.JSON(), nullable=False),
        sa.Column("not_connected_domains", sa.JSON(), nullable=False),
        sa.Column("domain_records", sa.JSON(), nullable=False),
        sa.Column("visibility_score", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("top_focus_area", sa.String(length=160), nullable=False),
        sa.Column("next_best_move", sa.Text(), nullable=False),
        sa.Column("snapshot_source", sa.String(length=40), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("missing_inputs", sa.JSON(), nullable=False),
        sa.Column("degraded_mode", sa.Boolean(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "overall_status in ('healthy', 'needs_review', 'needs_attention', 'degraded', 'insufficient_data')",
            name="ck_agency_awareness_snapshots_status",
        ),
        sa.CheckConstraint(
            "visibility_score >= 0 and visibility_score <= 100",
            name="ck_agency_awareness_snapshots_visibility_score",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 100",
            name="ck_agency_awareness_snapshots_confidence_score",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agency_awareness_snapshots_generated_at", "agency_awareness_snapshots", ["generated_at"])
    op.create_index("ix_agency_awareness_snapshots_stale", "agency_awareness_snapshots", ["stale"])
    op.create_index("ix_agency_awareness_snapshots_status", "agency_awareness_snapshots", ["overall_status"])


def downgrade() -> None:
    op.drop_index("ix_agency_awareness_snapshots_status", table_name="agency_awareness_snapshots")
    op.drop_index("ix_agency_awareness_snapshots_stale", table_name="agency_awareness_snapshots")
    op.drop_index("ix_agency_awareness_snapshots_generated_at", table_name="agency_awareness_snapshots")
    op.drop_table("agency_awareness_snapshots")
    op.drop_index("ix_agency_manual_records_type", table_name="agency_manual_records")
    op.drop_index("ix_agency_manual_records_domain", table_name="agency_manual_records")
    op.drop_index("ix_agency_manual_records_created_at", table_name="agency_manual_records")
    op.drop_table("agency_manual_records")
