"""Add search intelligence external evidence records.

Revision ID: 0048_search_intel
Revises: 0047_evidence_capture
Create Date: 2026-06-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0048_search_intel"
down_revision: str | None = "0047_evidence_capture"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_evidence_records_type", "evidence_records", type_="check")
    op.create_check_constraint(
        "ck_evidence_records_type",
        "evidence_records",
        "evidence_type in ('owner_note', 'owner_validation', 'system_record', 'uploaded_reference', "
        "'operational_outcome', 'external_search')",
    )
    op.create_table(
        "external_search_queries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_type", sa.String(length=60), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "query_type in ('opportunity', 'platform_signal', 'niche_research', 'competitor_research', "
            "'trend_monitoring', 'validation', 'notification_trigger', 'coo_context')",
            name="ck_external_search_queries_type",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped', 'not_configured')",
            name="ck_external_search_queries_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_search_queries_provider", "external_search_queries", ["provider"], unique=False)
    op.create_index("ix_external_search_queries_type", "external_search_queries", ["query_type"], unique=False)
    op.create_index("ix_external_search_queries_status", "external_search_queries", ["status"], unique=False)
    op.create_index("ix_external_search_queries_requested_at", "external_search_queries", ["requested_at"], unique=False)
    op.create_table(
        "external_search_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("display_url", sa.String(length=500), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source_domain", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("freshness_score", sa.Integer(), nullable=False),
        sa.Column("credibility_score", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("evidence_strength", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("used_for", sa.String(length=40), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source_type in ('website', 'news', 'social_public', 'forum_public', 'unknown')",
            name="ck_external_search_results_source_type",
        ),
        sa.CheckConstraint(
            "evidence_strength in ('weak', 'medium', 'strong')",
            name="ck_external_search_results_strength",
        ),
        sa.CheckConstraint(
            "used_for in ('opportunity', 'notification', 'coo_briefing', 'validation', 'research')",
            name="ck_external_search_results_used_for",
        ),
        sa.CheckConstraint("relevance_score >= 0 and relevance_score <= 100", name="ck_external_search_results_relevance"),
        sa.CheckConstraint("freshness_score >= 0 and freshness_score <= 100", name="ck_external_search_results_freshness"),
        sa.CheckConstraint("credibility_score >= 0 and credibility_score <= 100", name="ck_external_search_results_credibility"),
        sa.CheckConstraint("risk_score >= 0 and risk_score <= 100", name="ck_external_search_results_risk"),
        sa.ForeignKeyConstraint(["query_id"], ["external_search_queries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "result_hash", name="uq_external_search_results_provider_hash"),
    )
    op.create_index("ix_external_search_results_query", "external_search_results", ["query_id"], unique=False)
    op.create_index("ix_external_search_results_domain", "external_search_results", ["source_domain"], unique=False)
    op.create_index("ix_external_search_results_retrieved_at", "external_search_results", ["retrieved_at"], unique=False)
    op.create_index("ix_external_search_results_strength", "external_search_results", ["evidence_strength"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_external_search_results_strength", table_name="external_search_results")
    op.drop_index("ix_external_search_results_retrieved_at", table_name="external_search_results")
    op.drop_index("ix_external_search_results_domain", table_name="external_search_results")
    op.drop_index("ix_external_search_results_query", table_name="external_search_results")
    op.drop_table("external_search_results")
    op.drop_index("ix_external_search_queries_requested_at", table_name="external_search_queries")
    op.drop_index("ix_external_search_queries_status", table_name="external_search_queries")
    op.drop_index("ix_external_search_queries_type", table_name="external_search_queries")
    op.drop_index("ix_external_search_queries_provider", table_name="external_search_queries")
    op.drop_table("external_search_queries")
    op.drop_constraint("ck_evidence_records_type", "evidence_records", type_="check")
    op.create_check_constraint(
        "ck_evidence_records_type",
        "evidence_records",
        "evidence_type in ('owner_note', 'owner_validation', 'system_record', 'uploaded_reference', 'operational_outcome')",
    )
