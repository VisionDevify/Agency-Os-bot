"""Add recovery job timeout statuses.

Revision ID: 0043_recovery_timeouts
Revises: 0042_active_cleanup
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0043_recovery_timeouts"
down_revision: str | None = "0042_active_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BACKUP_STATUSES_WITH_TIMEOUT = (
    "pending",
    "running",
    "success",
    "succeeded",
    "failed",
    "timed_out",
    "skipped",
    "manual_required",
    "not_configured",
)

BACKUP_STATUSES_WITHOUT_TIMEOUT = (
    "pending",
    "running",
    "success",
    "succeeded",
    "failed",
    "skipped",
    "manual_required",
    "not_configured",
)

RESTORE_STATUSES_WITH_TIMEOUT = (
    "pending",
    "running",
    "verified_only",
    "verified",
    "passed",
    "succeeded",
    "failed",
    "timed_out",
    "skipped",
    "not_available",
)

RESTORE_STATUSES_WITHOUT_TIMEOUT = (
    "pending",
    "running",
    "verified_only",
    "verified",
    "passed",
    "succeeded",
    "failed",
    "skipped",
    "not_available",
)


def upgrade() -> None:
    op.drop_constraint("ck_backup_runs_status", "backup_runs", type_="check")
    op.create_check_constraint(
        "ck_backup_runs_status",
        "backup_runs",
        f"status in {BACKUP_STATUSES_WITH_TIMEOUT!r}",
    )
    op.drop_constraint("ck_restore_test_runs_status", "restore_test_runs", type_="check")
    op.create_check_constraint(
        "ck_restore_test_runs_status",
        "restore_test_runs",
        f"status in {RESTORE_STATUSES_WITH_TIMEOUT!r}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_restore_test_runs_status", "restore_test_runs", type_="check")
    op.create_check_constraint(
        "ck_restore_test_runs_status",
        "restore_test_runs",
        f"status in {RESTORE_STATUSES_WITHOUT_TIMEOUT!r}",
    )
    op.drop_constraint("ck_backup_runs_status", "backup_runs", type_="check")
    op.create_check_constraint(
        "ck_backup_runs_status",
        "backup_runs",
        f"status in {BACKUP_STATUSES_WITHOUT_TIMEOUT!r}",
    )
