"""Add social discovery mode tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_social_discovery_mode"
down_revision: str | None = "0034_chat_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "social_discovery_source_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("reference_url", sa.String(length=500), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("compliance_status", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_discovery_configs_platform"),
        sa.CheckConstraint(
            "source_type in ('manual', 'csv_export', 'official_api_placeholder', 'approved_public_import_placeholder')",
            name="ck_social_discovery_configs_source_type",
        ),
        sa.CheckConstraint(
            "compliance_status in ('approved', 'review_required', 'blocked')",
            name="ck_social_discovery_configs_compliance",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_discovery_configs_active", "social_discovery_source_configs", ["is_active"])
    op.create_index("ix_social_discovery_configs_platform", "social_discovery_source_configs", ["platform"])

    op.create_table(
        "social_discovery_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("source_config_id", sa.Integer(), nullable=True),
        sa.Column("started_by_user_id", sa.Integer(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "run_type in ('manual_url', 'manual_source', 'csv_import', 'official_api_placeholder', 'approved_public_import')",
            name="ck_social_discovery_runs_type",
        ),
        sa.CheckConstraint("status in ('pending', 'running', 'succeeded', 'failed')", name="ck_social_discovery_runs_status"),
        sa.ForeignKeyConstraint(["source_config_id"], ["social_discovery_source_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_discovery_runs_started_by", "social_discovery_runs", ["started_by_user_id"])
    op.create_index("ix_social_discovery_runs_status", "social_discovery_runs", ["status"])
    op.create_index("ix_social_discovery_runs_type", "social_discovery_runs", ["run_type"])

    op.create_table(
        "social_discovery_leads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("discovery_run_id", sa.Integer(), nullable=True),
        sa.Column("social_source_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("source_name", sa.String(length=180), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=True),
        sa.Column("post_reference", sa.String(length=500), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("reason_found", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("opportunity_score", sa.Integer(), nullable=False),
        sa.Column("compliance_status", sa.String(length=40), nullable=False),
        sa.Column("recommended_angle", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_social_discovery_leads_platform"),
        sa.CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_social_discovery_leads_confidence"),
        sa.CheckConstraint("opportunity_score >= 0 and opportunity_score <= 100", name="ck_social_discovery_leads_score"),
        sa.CheckConstraint(
            "compliance_status in ('approved', 'review_required', 'blocked')",
            name="ck_social_discovery_leads_compliance",
        ),
        sa.CheckConstraint(
            "status in ('new', 'reviewed', 'converted_to_opportunity', 'skipped', 'archived')",
            name="ck_social_discovery_leads_status",
        ),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["social_discovery_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["social_source_id"], ["social_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_discovery_leads_niche", "social_discovery_leads", ["niche"])
    op.create_index("ix_social_discovery_leads_platform", "social_discovery_leads", ["platform"])
    op.create_index("ix_social_discovery_leads_run_id", "social_discovery_leads", ["discovery_run_id"])
    op.create_index("ix_social_discovery_leads_score", "social_discovery_leads", ["opportunity_score"])
    op.create_index("ix_social_discovery_leads_status", "social_discovery_leads", ["status"])


def downgrade() -> None:
    op.drop_index("ix_social_discovery_leads_status", table_name="social_discovery_leads")
    op.drop_index("ix_social_discovery_leads_score", table_name="social_discovery_leads")
    op.drop_index("ix_social_discovery_leads_run_id", table_name="social_discovery_leads")
    op.drop_index("ix_social_discovery_leads_platform", table_name="social_discovery_leads")
    op.drop_index("ix_social_discovery_leads_niche", table_name="social_discovery_leads")
    op.drop_table("social_discovery_leads")
    op.drop_index("ix_social_discovery_runs_type", table_name="social_discovery_runs")
    op.drop_index("ix_social_discovery_runs_status", table_name="social_discovery_runs")
    op.drop_index("ix_social_discovery_runs_started_by", table_name="social_discovery_runs")
    op.drop_table("social_discovery_runs")
    op.drop_index("ix_social_discovery_configs_platform", table_name="social_discovery_source_configs")
    op.drop_index("ix_social_discovery_configs_active", table_name="social_discovery_source_configs")
    op.drop_table("social_discovery_source_configs")
