"""Add recovery center and prediction engine tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_recovery_prediction_engine"
down_revision: str | None = "0035_social_discovery_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_storage_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("encrypted", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "target_type in ('local_runtime', 'manual_export', 's3_compatible', 'backblaze_b2', 'google_drive')",
            name="ck_backup_storage_targets_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_storage_targets_enabled", "backup_storage_targets", ["enabled"])
    op.create_index("ix_backup_storage_targets_last_success", "backup_storage_targets", ["last_success_at"])
    op.create_index("ix_backup_storage_targets_type", "backup_storage_targets", ["target_type"])

    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("backup_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_target", sa.String(length=120), nullable=True),
        sa.Column("encrypted", sa.Boolean(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "backup_type in ('manual', 'nightly', 'pre_deploy', 'restore_test')",
            name="ck_backup_runs_type",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_backup_runs_status",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_runs_started_at", "backup_runs", ["started_at"])
    op.create_index("ix_backup_runs_status", "backup_runs", ["status"])
    op.create_index("ix_backup_runs_storage_target", "backup_runs", ["storage_target"])
    op.create_index("ix_backup_runs_type", "backup_runs", ["backup_type"])

    op.create_table(
        "restore_test_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("backup_run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'verified', 'succeeded', 'failed', 'skipped')",
            name="ck_restore_test_runs_status",
        ),
        sa.ForeignKeyConstraint(["backup_run_id"], ["backup_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_restore_test_runs_backup_run_id", "restore_test_runs", ["backup_run_id"])
    op.create_index("ix_restore_test_runs_started_at", "restore_test_runs", ["started_at"])
    op.create_index("ix_restore_test_runs_status", "restore_test_runs", ["status"])

    op.create_table(
        "team_performance_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tasks_completed", sa.Integer(), nullable=False),
        sa.Column("tasks_overdue", sa.Integer(), nullable=False),
        sa.Column("opportunities_reviewed", sa.Integer(), nullable=False),
        sa.Column("opportunities_successful", sa.Integer(), nullable=False),
        sa.Column("avg_response_minutes", sa.Integer(), nullable=True),
        sa.Column("workload_score", sa.Integer(), nullable=False),
        sa.Column("reliability_score", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("workload_score >= 0 and workload_score <= 100", name="ck_team_performance_workload"),
        sa.CheckConstraint("reliability_score >= 0 and reliability_score <= 100", name="ck_team_performance_reliability"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_performance_period", "team_performance_snapshots", ["period_start", "period_end"])
    op.create_index("ix_team_performance_role", "team_performance_snapshots", ["role"])
    op.create_index("ix_team_performance_user_id", "team_performance_snapshots", ["user_id"])

    op.create_table(
        "opportunity_predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("predicted_quality", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("recommended_angle", sa.String(length=80), nullable=True),
        sa.Column("recommended_chatter_id", sa.Integer(), nullable=True),
        sa.Column("reasoning_summary", sa.Text(), nullable=False),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("predicted_quality >= 0 and predicted_quality <= 100", name="ck_opportunity_predictions_quality"),
        sa.CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_opportunity_predictions_confidence"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recommended_chatter_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunity_predictions_chatter", "opportunity_predictions", ["recommended_chatter_id"])
    op.create_index("ix_opportunity_predictions_created_at", "opportunity_predictions", ["created_at"])
    op.create_index("ix_opportunity_predictions_opportunity_id", "opportunity_predictions", ["opportunity_id"])
    op.create_index("ix_opportunity_predictions_quality", "opportunity_predictions", ["predicted_quality"])


def downgrade() -> None:
    op.drop_index("ix_opportunity_predictions_quality", table_name="opportunity_predictions")
    op.drop_index("ix_opportunity_predictions_opportunity_id", table_name="opportunity_predictions")
    op.drop_index("ix_opportunity_predictions_created_at", table_name="opportunity_predictions")
    op.drop_index("ix_opportunity_predictions_chatter", table_name="opportunity_predictions")
    op.drop_table("opportunity_predictions")
    op.drop_index("ix_team_performance_user_id", table_name="team_performance_snapshots")
    op.drop_index("ix_team_performance_role", table_name="team_performance_snapshots")
    op.drop_index("ix_team_performance_period", table_name="team_performance_snapshots")
    op.drop_table("team_performance_snapshots")
    op.drop_index("ix_restore_test_runs_status", table_name="restore_test_runs")
    op.drop_index("ix_restore_test_runs_started_at", table_name="restore_test_runs")
    op.drop_index("ix_restore_test_runs_backup_run_id", table_name="restore_test_runs")
    op.drop_table("restore_test_runs")
    op.drop_index("ix_backup_runs_type", table_name="backup_runs")
    op.drop_index("ix_backup_runs_storage_target", table_name="backup_runs")
    op.drop_index("ix_backup_runs_status", table_name="backup_runs")
    op.drop_index("ix_backup_runs_started_at", table_name="backup_runs")
    op.drop_table("backup_runs")
    op.drop_index("ix_backup_storage_targets_type", table_name="backup_storage_targets")
    op.drop_index("ix_backup_storage_targets_last_success", table_name="backup_storage_targets")
    op.drop_index("ix_backup_storage_targets_enabled", table_name="backup_storage_targets")
    op.drop_table("backup_storage_targets")
