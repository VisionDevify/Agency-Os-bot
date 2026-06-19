"""Add recovery run evidence and button issues."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_recovery_button_health"
down_revision: str | None = "0037_social_comment_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("backup_runs", sa.Column("run_identifier", sa.String(length=80), nullable=True))
    op.execute("update backup_runs set run_identifier = 'legacy-backup-' || id where run_identifier is null")
    op.alter_column("backup_runs", "run_identifier", nullable=False)
    op.add_column("backup_runs", sa.Column("artifact_uri", sa.String(length=500), nullable=True))
    op.add_column("backup_runs", sa.Column("artifact_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("backup_runs", sa.Column("external_storage_used", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("backup_runs", sa.Column("result_summary", sa.Text(), nullable=True))
    op.create_index("ix_backup_runs_run_identifier", "backup_runs", ["run_identifier"], unique=True)
    op.drop_constraint("ck_backup_runs_status", "backup_runs", type_="check")
    op.create_check_constraint(
        "ck_backup_runs_status",
        "backup_runs",
        "status in ('pending', 'running', 'success', 'succeeded', 'failed', 'skipped', 'manual_required', 'not_configured')",
    )

    op.add_column("restore_test_runs", sa.Column("run_identifier", sa.String(length=80), nullable=True))
    op.execute("update restore_test_runs set run_identifier = 'legacy-restore-' || id where run_identifier is null")
    op.alter_column("restore_test_runs", "run_identifier", nullable=False)
    op.add_column("restore_test_runs", sa.Column("checksum_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("restore_test_runs", sa.Column("decrypt_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("restore_test_runs", sa.Column("full_restore_performed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute(
        "update restore_test_runs set checksum_verified = true, decrypt_verified = true "
        "where status in ('verified', 'succeeded')"
    )
    op.execute("update restore_test_runs set full_restore_performed = true where status = 'succeeded'")
    op.create_index("ix_restore_test_runs_run_identifier", "restore_test_runs", ["run_identifier"], unique=True)
    op.drop_constraint("ck_restore_test_runs_status", "restore_test_runs", type_="check")
    op.create_check_constraint(
        "ck_restore_test_runs_status",
        "restore_test_runs",
        "status in ('pending', 'running', 'verified_only', 'verified', 'passed', 'succeeded', 'failed', 'skipped', 'not_available')",
    )

    op.create_table(
        "button_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("screen", sa.String(length=160), nullable=False),
        sa.Column("button_label", sa.String(length=160), nullable=True),
        sa.Column("callback_data", sa.String(length=260), nullable=True),
        sa.Column("issue_type", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("recommended_fix", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "issue_type in ('missing_handler', 'renderer_error', 'bad_back_target', 'missing_back', "
            "'missing_home', 'confusing_label', 'dead_end', 'raw_internal_label')",
            name="ck_button_issues_type",
        ),
        sa.CheckConstraint("severity in ('low', 'medium', 'high', 'critical')", name="ck_button_issues_severity"),
        sa.CheckConstraint("status in ('open', 'resolved', 'ignored')", name="ck_button_issues_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_button_issues_detected_at", "button_issues", ["detected_at"])
    op.create_index("ix_button_issues_lookup", "button_issues", ["screen", "button_label", "callback_data", "issue_type"])
    op.create_index("ix_button_issues_screen", "button_issues", ["screen"])
    op.create_index("ix_button_issues_severity", "button_issues", ["severity"])
    op.create_index("ix_button_issues_status", "button_issues", ["status"])


def downgrade() -> None:
    op.drop_index("ix_button_issues_status", table_name="button_issues")
    op.drop_index("ix_button_issues_severity", table_name="button_issues")
    op.drop_index("ix_button_issues_screen", table_name="button_issues")
    op.drop_index("ix_button_issues_lookup", table_name="button_issues")
    op.drop_index("ix_button_issues_detected_at", table_name="button_issues")
    op.drop_table("button_issues")

    op.drop_constraint("ck_restore_test_runs_status", "restore_test_runs", type_="check")
    op.create_check_constraint(
        "ck_restore_test_runs_status",
        "restore_test_runs",
        "status in ('pending', 'running', 'verified', 'succeeded', 'failed', 'skipped')",
    )
    op.drop_index("ix_restore_test_runs_run_identifier", table_name="restore_test_runs")
    op.drop_column("restore_test_runs", "full_restore_performed")
    op.drop_column("restore_test_runs", "decrypt_verified")
    op.drop_column("restore_test_runs", "checksum_verified")
    op.drop_column("restore_test_runs", "run_identifier")

    op.drop_constraint("ck_backup_runs_status", "backup_runs", type_="check")
    op.create_check_constraint(
        "ck_backup_runs_status",
        "backup_runs",
        "status in ('pending', 'running', 'succeeded', 'failed', 'skipped')",
    )
    op.drop_index("ix_backup_runs_run_identifier", table_name="backup_runs")
    op.drop_column("backup_runs", "result_summary")
    op.drop_column("backup_runs", "external_storage_used")
    op.drop_column("backup_runs", "artifact_verified")
    op.drop_column("backup_runs", "artifact_uri")
    op.drop_column("backup_runs", "run_identifier")
