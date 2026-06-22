"""agency drift detection

Revision ID: 0053_agency_drift_detection
Revises: 0052_command_center_scores
Create Date: 2026-06-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0053_agency_drift_detection"
down_revision = "0052_command_center_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agency_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("owner_role", sa.String(length=60), nullable=False),
        sa.Column("expected_cadence", sa.String(length=80), nullable=False),
        sa.Column("expected_signal", sa.String(length=180), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('active', 'paused', 'completed', 'cancelled')", name="ck_agency_plans_status"),
        sa.CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_agency_plans_confidence"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agency_plans_domain", "agency_plans", ["domain"])
    op.create_index("ix_agency_plans_status", "agency_plans", ["status"])
    op.create_index("ix_agency_plans_start_at", "agency_plans", ["start_at"])

    op.create_table(
        "agency_expectations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("expected_cadence", sa.String(length=80), nullable=False),
        sa.Column("expected_signal", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('active', 'paused', 'completed', 'cancelled')", name="ck_agency_expectations_status"),
        sa.CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_agency_expectations_confidence"),
        sa.ForeignKeyConstraint(["plan_id"], ["agency_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agency_expectations_plan_id", "agency_expectations", ["plan_id"])
    op.create_index("ix_agency_expectations_domain", "agency_expectations", ["domain"])
    op.create_index("ix_agency_expectations_status", "agency_expectations", ["status"])
    op.create_index("ix_agency_expectations_next_check_at", "agency_expectations", ["next_check_at"])

    op.create_table(
        "agency_drift_findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("expected", sa.Text(), nullable=False),
        sa.Column("observed", sa.Text(), nullable=False),
        sa.Column("gap", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("next_best_move", sa.Text(), nullable=False),
        sa.Column("evidence_records", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("severity in ('low', 'medium', 'high')", name="ck_agency_drift_findings_severity"),
        sa.CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_agency_drift_findings_confidence"),
        sa.CheckConstraint(
            "status in ('active', 'needs_review', 'resolved', 'historical', 'reappeared')",
            name="ck_agency_drift_findings_status",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["agency_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agency_drift_findings_plan_id", "agency_drift_findings", ["plan_id"])
    op.create_index("ix_agency_drift_findings_domain", "agency_drift_findings", ["domain"])
    op.create_index("ix_agency_drift_findings_status", "agency_drift_findings", ["status"])
    op.create_index("ix_agency_drift_findings_severity", "agency_drift_findings", ["severity"])
    op.create_index("ix_agency_drift_findings_last_seen_at", "agency_drift_findings", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_agency_drift_findings_last_seen_at", table_name="agency_drift_findings")
    op.drop_index("ix_agency_drift_findings_severity", table_name="agency_drift_findings")
    op.drop_index("ix_agency_drift_findings_status", table_name="agency_drift_findings")
    op.drop_index("ix_agency_drift_findings_domain", table_name="agency_drift_findings")
    op.drop_index("ix_agency_drift_findings_plan_id", table_name="agency_drift_findings")
    op.drop_table("agency_drift_findings")
    op.drop_index("ix_agency_expectations_next_check_at", table_name="agency_expectations")
    op.drop_index("ix_agency_expectations_status", table_name="agency_expectations")
    op.drop_index("ix_agency_expectations_domain", table_name="agency_expectations")
    op.drop_index("ix_agency_expectations_plan_id", table_name="agency_expectations")
    op.drop_table("agency_expectations")
    op.drop_index("ix_agency_plans_start_at", table_name="agency_plans")
    op.drop_index("ix_agency_plans_status", table_name="agency_plans")
    op.drop_index("ix_agency_plans_domain", table_name="agency_plans")
    op.drop_table("agency_plans")
