from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


BACKUP_RUN_TYPES = ("manual", "nightly", "pre_deploy", "restore_test")
BACKUP_RUN_STATUSES = (
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
BACKUP_TARGET_TYPES = (
    "local_runtime",
    "manual_export",
    "s3_compatible",
    "backblaze_b2",
    "google_drive",
    "cloudflare_r2",
    "azure_blob",
)
RESTORE_TEST_STATUSES = (
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


class BackupRun(TimestampMixin, Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint(
            "backup_type in ('manual', 'nightly', 'pre_deploy', 'restore_test')",
            name="ck_backup_runs_type",
        ),
        CheckConstraint(
            "status in ('pending', 'running', 'success', 'succeeded', 'failed', 'timed_out', 'skipped', 'manual_required', 'not_configured')",
            name="ck_backup_runs_status",
        ),
        Index("ix_backup_runs_run_identifier", "run_identifier", unique=True),
        Index("ix_backup_runs_status", "status"),
        Index("ix_backup_runs_type", "backup_type"),
        Index("ix_backup_runs_started_at", "started_at"),
        Index("ix_backup_runs_storage_target", "storage_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_identifier: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    backup_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifact_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    external_storage_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    restore_tests: Mapped[list["RestoreTestRun"]] = relationship(back_populates="backup_run", lazy="selectin")


class BackupStorageTarget(TimestampMixin, Base):
    __tablename__ = "backup_storage_targets"
    __table_args__ = (
        CheckConstraint(
            "target_type in ('local_runtime', 'manual_export', 's3_compatible', 'backblaze_b2', 'google_drive', 'cloudflare_r2', 'azure_blob')",
            name="ck_backup_storage_targets_type",
        ),
        CheckConstraint(
            "connection_status in ('not_configured', 'pending', 'active', 'failed', 'disabled')",
            name="ck_backup_storage_targets_connection_status",
        ),
        Index("ix_backup_storage_targets_enabled", "enabled"),
        Index("ix_backup_storage_targets_type", "target_type"),
        Index("ix_backup_storage_targets_last_success", "last_success_at"),
        Index("ix_backup_storage_targets_connection_status", "connection_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encrypted_config_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    masked_config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    connection_status: Mapped[str] = mapped_column(String(40), default="not_configured", nullable=False)
    provider_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_test_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)


class RestoreTestRun(TimestampMixin, Base):
    __tablename__ = "restore_test_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'running', 'verified_only', 'verified', 'passed', 'succeeded', 'failed', 'timed_out', 'skipped', 'not_available')",
            name="ck_restore_test_runs_status",
        ),
        Index("ix_restore_test_runs_run_identifier", "run_identifier", unique=True),
        Index("ix_restore_test_runs_backup_run_id", "backup_run_id"),
        Index("ix_restore_test_runs_status", "status"),
        Index("ix_restore_test_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_identifier: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    backup_run_id: Mapped[int | None] = mapped_column(ForeignKey("backup_runs.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    checksum_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    decrypt_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    full_restore_performed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    backup_run: Mapped[BackupRun | None] = relationship(back_populates="restore_tests", lazy="selectin")
