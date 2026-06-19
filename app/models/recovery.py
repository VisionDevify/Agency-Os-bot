from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


BACKUP_RUN_TYPES = ("manual", "nightly", "pre_deploy", "restore_test")
BACKUP_RUN_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")
BACKUP_TARGET_TYPES = ("local_runtime", "manual_export", "s3_compatible", "backblaze_b2", "google_drive")
RESTORE_TEST_STATUSES = ("pending", "running", "verified", "succeeded", "failed", "skipped")


class BackupRun(TimestampMixin, Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint(
            "backup_type in ('manual', 'nightly', 'pre_deploy', 'restore_test')",
            name="ck_backup_runs_type",
        ),
        CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_backup_runs_status",
        ),
        Index("ix_backup_runs_status", "status"),
        Index("ix_backup_runs_type", "backup_type"),
        Index("ix_backup_runs_started_at", "started_at"),
        Index("ix_backup_runs_storage_target", "storage_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    backup_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    restore_tests: Mapped[list["RestoreTestRun"]] = relationship(back_populates="backup_run", lazy="selectin")


class BackupStorageTarget(TimestampMixin, Base):
    __tablename__ = "backup_storage_targets"
    __table_args__ = (
        CheckConstraint(
            "target_type in ('local_runtime', 'manual_export', 's3_compatible', 'backblaze_b2', 'google_drive')",
            name="ck_backup_storage_targets_type",
        ),
        Index("ix_backup_storage_targets_enabled", "enabled"),
        Index("ix_backup_storage_targets_type", "target_type"),
        Index("ix_backup_storage_targets_last_success", "last_success_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)


class RestoreTestRun(TimestampMixin, Base):
    __tablename__ = "restore_test_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'running', 'verified', 'succeeded', 'failed', 'skipped')",
            name="ck_restore_test_runs_status",
        ),
        Index("ix_restore_test_runs_backup_run_id", "backup_run_id"),
        Index("ix_restore_test_runs_status", "status"),
        Index("ix_restore_test_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    backup_run_id: Mapped[int | None] = mapped_column(ForeignKey("backup_runs.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)

    backup_run: Mapped[BackupRun | None] = relationship(back_populates="restore_tests", lazy="selectin")
