"""agency intelligence brain v1

Revision ID: 0014_intel_brain_v1
Revises: 0013_ops_activation
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_intel_brain_v1"
down_revision: str | None = "0013_ops_activation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "intelligence_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("signal_type", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=40), server_default="info", nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), server_default="80", nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="open", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("severity in ('info', 'warning', 'critical')", name="ck_intelligence_signals_severity"),
        sa.CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_intelligence_signals_confidence"),
        sa.CheckConstraint("occurrence_count >= 0", name="ck_intelligence_signals_occurrence_count"),
        sa.CheckConstraint("status in ('open', 'acknowledged', 'resolved', 'dismissed')", name="ck_intelligence_signals_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intelligence_signals_type", "intelligence_signals", ["signal_type"])
    op.create_index("ix_intelligence_signals_severity", "intelligence_signals", ["severity"])
    op.create_index("ix_intelligence_signals_entity", "intelligence_signals", ["entity_type", "entity_id"])
    op.create_index("ix_intelligence_signals_status", "intelligence_signals", ["status"])
    op.create_index("ix_intelligence_signals_last_seen_at", "intelligence_signals", ["last_seen_at"])

    op.create_table(
        "issue_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern_type", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("severity", sa.String(length=40), server_default="warning", nullable=False),
        sa.Column("confidence_score", sa.Integer(), server_default="80", nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("related_event_ids_json", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("severity in ('info', 'warning', 'critical')", name="ck_issue_patterns_severity"),
        sa.CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_issue_patterns_confidence"),
        sa.CheckConstraint("occurrence_count >= 0", name="ck_issue_patterns_occurrence_count"),
        sa.CheckConstraint("status in ('active', 'acknowledged', 'resolved', 'dismissed')", name="ck_issue_patterns_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issue_patterns_type", "issue_patterns", ["pattern_type"])
    op.create_index("ix_issue_patterns_severity", "issue_patterns", ["severity"])
    op.create_index("ix_issue_patterns_entity", "issue_patterns", ["entity_type", "entity_id"])
    op.create_index("ix_issue_patterns_status", "issue_patterns", ["status"])
    op.create_index("ix_issue_patterns_last_seen_at", "issue_patterns", ["last_seen_at"])

    op.create_table(
        "trend_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("value_numeric", sa.Integer(), nullable=False),
        sa.Column("comparison_window", sa.String(length=40), server_default="daily", nullable=False),
        sa.Column("trend_direction", sa.String(length=40), server_default="flat", nullable=False),
        sa.Column("percent_change", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("comparison_window in ('daily', 'weekly', 'monthly')", name="ck_trend_snapshots_window"),
        sa.CheckConstraint("trend_direction in ('up', 'down', 'flat', 'volatile')", name="ck_trend_snapshots_direction"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trend_snapshots_snapshot_date", "trend_snapshots", ["snapshot_date"])
    op.create_index("ix_trend_snapshots_metric", "trend_snapshots", ["metric_name"])
    op.create_index("ix_trend_snapshots_entity", "trend_snapshots", ["entity_type", "entity_id"])
    op.create_index("ix_trend_snapshots_window", "trend_snapshots", ["comparison_window"])
    op.create_index("ix_trend_snapshots_direction", "trend_snapshots", ["trend_direction"])
    op.create_index("ix_trend_snapshots_created_at", "trend_snapshots", ["created_at"])

    op.create_table(
        "workload_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("open_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("overdue_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("open_incidents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("critical_incidents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_tasks_24h", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolved_incidents_24h", sa.Integer(), server_default="0", nullable=False),
        sa.Column("availability_status", sa.String(length=40), server_default="off_shift", nullable=False),
        sa.Column("workload_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("overload_status", sa.String(length=40), server_default="normal", nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("overload_status in ('normal', 'elevated', 'overloaded', 'critical')", name="ck_workload_snapshots_overload_status"),
        sa.CheckConstraint("workload_score >= 0", name="ck_workload_snapshots_score"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workload_snapshots_snapshot_date", "workload_snapshots", ["snapshot_date"])
    op.create_index("ix_workload_snapshots_user_id", "workload_snapshots", ["user_id"])
    op.create_index("ix_workload_snapshots_overload_status", "workload_snapshots", ["overload_status"])
    op.create_index("ix_workload_snapshots_created_at", "workload_snapshots", ["created_at"])

    op.create_table(
        "executive_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("insight_type", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), server_default="info", nullable=False),
        sa.Column("confidence_score", sa.Integer(), server_default="80", nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("source_signal_ids_json", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="open", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("severity in ('info', 'warning', 'critical')", name="ck_executive_insights_severity"),
        sa.CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_executive_insights_confidence"),
        sa.CheckConstraint("status in ('open', 'acknowledged', 'resolved', 'dismissed')", name="ck_executive_insights_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_executive_insights_type", "executive_insights", ["insight_type"])
    op.create_index("ix_executive_insights_severity", "executive_insights", ["severity"])
    op.create_index("ix_executive_insights_status", "executive_insights", ["status"])
    op.create_index("ix_executive_insights_created_at", "executive_insights", ["created_at"])

    op.create_table(
        "opportunity_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_opportunity_sources_platform"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunity_sources_platform", "opportunity_sources", ["platform"])
    op.create_index("ix_opportunity_sources_name", "opportunity_sources", ["name"])
    op.create_index("ix_opportunity_sources_niche", "opportunity_sources", ["niche"])
    op.create_index("ix_opportunity_sources_is_active", "opportunity_sources", ["is_active"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("niche", sa.String(length=120), nullable=True),
        sa.Column("model_brand_id", sa.Integer(), nullable=True),
        sa.Column("score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="discovered", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("suggested_angle", sa.Text(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("platform in ('x', 'instagram', 'reddit', 'other')", name="ck_opportunities_platform"),
        sa.CheckConstraint("score >= 0 and score <= 100", name="ck_opportunities_score"),
        sa.CheckConstraint(
            "status in ('discovered', 'reviewing', 'approved', 'assigned', 'completed', 'rejected', 'archived')",
            name="ck_opportunities_status",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_brand_id"], ["model_brands.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunities_source_id", "opportunities", ["source_id"])
    op.create_index("ix_opportunities_platform", "opportunities", ["platform"])
    op.create_index("ix_opportunities_model_brand_id", "opportunities", ["model_brand_id"])
    op.create_index("ix_opportunities_assigned_to_user_id", "opportunities", ["assigned_to_user_id"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])
    op.create_index("ix_opportunities_score", "opportunities", ["score"])
    op.create_index("ix_opportunities_niche", "opportunities", ["niche"])

    op.create_table(
        "opportunity_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("posted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="not_posted", nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=True),
        sa.Column("conversions", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status in ('not_posted', 'posted', 'skipped', 'failed')", name="ck_opportunity_results_status"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunity_results_opportunity_id", "opportunity_results", ["opportunity_id"])
    op.create_index("ix_opportunity_results_posted_by_user_id", "opportunity_results", ["posted_by_user_id"])
    op.create_index("ix_opportunity_results_status", "opportunity_results", ["status"])

    op.create_table(
        "intelligence_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("started_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "run_type in ('pattern_detection', 'trend_analysis', 'workload_analysis', "
            "'recommendation_generation', 'executive_briefing', 'opportunity_scoring')",
            name="ck_intelligence_runs_type",
        ),
        sa.CheckConstraint("status in ('pending', 'running', 'succeeded', 'failed')", name="ck_intelligence_runs_status"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intelligence_runs_type", "intelligence_runs", ["run_type"])
    op.create_index("ix_intelligence_runs_status", "intelligence_runs", ["status"])
    op.create_index("ix_intelligence_runs_started_by", "intelligence_runs", ["started_by_user_id"])
    op.create_index("ix_intelligence_runs_started_at", "intelligence_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_runs_started_at", table_name="intelligence_runs")
    op.drop_index("ix_intelligence_runs_started_by", table_name="intelligence_runs")
    op.drop_index("ix_intelligence_runs_status", table_name="intelligence_runs")
    op.drop_index("ix_intelligence_runs_type", table_name="intelligence_runs")
    op.drop_table("intelligence_runs")

    op.drop_index("ix_opportunity_results_status", table_name="opportunity_results")
    op.drop_index("ix_opportunity_results_posted_by_user_id", table_name="opportunity_results")
    op.drop_index("ix_opportunity_results_opportunity_id", table_name="opportunity_results")
    op.drop_table("opportunity_results")

    op.drop_index("ix_opportunities_niche", table_name="opportunities")
    op.drop_index("ix_opportunities_score", table_name="opportunities")
    op.drop_index("ix_opportunities_status", table_name="opportunities")
    op.drop_index("ix_opportunities_assigned_to_user_id", table_name="opportunities")
    op.drop_index("ix_opportunities_model_brand_id", table_name="opportunities")
    op.drop_index("ix_opportunities_platform", table_name="opportunities")
    op.drop_index("ix_opportunities_source_id", table_name="opportunities")
    op.drop_table("opportunities")

    op.drop_index("ix_opportunity_sources_is_active", table_name="opportunity_sources")
    op.drop_index("ix_opportunity_sources_niche", table_name="opportunity_sources")
    op.drop_index("ix_opportunity_sources_name", table_name="opportunity_sources")
    op.drop_index("ix_opportunity_sources_platform", table_name="opportunity_sources")
    op.drop_table("opportunity_sources")

    op.drop_index("ix_executive_insights_created_at", table_name="executive_insights")
    op.drop_index("ix_executive_insights_status", table_name="executive_insights")
    op.drop_index("ix_executive_insights_severity", table_name="executive_insights")
    op.drop_index("ix_executive_insights_type", table_name="executive_insights")
    op.drop_table("executive_insights")

    op.drop_index("ix_workload_snapshots_created_at", table_name="workload_snapshots")
    op.drop_index("ix_workload_snapshots_overload_status", table_name="workload_snapshots")
    op.drop_index("ix_workload_snapshots_user_id", table_name="workload_snapshots")
    op.drop_index("ix_workload_snapshots_snapshot_date", table_name="workload_snapshots")
    op.drop_table("workload_snapshots")

    op.drop_index("ix_trend_snapshots_created_at", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_direction", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_window", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_entity", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_metric", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_snapshot_date", table_name="trend_snapshots")
    op.drop_table("trend_snapshots")

    op.drop_index("ix_issue_patterns_last_seen_at", table_name="issue_patterns")
    op.drop_index("ix_issue_patterns_status", table_name="issue_patterns")
    op.drop_index("ix_issue_patterns_entity", table_name="issue_patterns")
    op.drop_index("ix_issue_patterns_severity", table_name="issue_patterns")
    op.drop_index("ix_issue_patterns_type", table_name="issue_patterns")
    op.drop_table("issue_patterns")

    op.drop_index("ix_intelligence_signals_last_seen_at", table_name="intelligence_signals")
    op.drop_index("ix_intelligence_signals_status", table_name="intelligence_signals")
    op.drop_index("ix_intelligence_signals_entity", table_name="intelligence_signals")
    op.drop_index("ix_intelligence_signals_severity", table_name="intelligence_signals")
    op.drop_index("ix_intelligence_signals_type", table_name="intelligence_signals")
    op.drop_table("intelligence_signals")
