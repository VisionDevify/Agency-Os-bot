from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

import app.services.recovery as recovery_service
from app.bot.screens.recovery import render_backup_run_page, render_restore_test_page
from app.bot.screens.settings import render_botstatus_page, render_production_observability_page, render_ui_self_test_page
from app.models.recovery import BackupRun, BackupStorageTarget, RestoreTestRun
from app.services.auth import setup_owner_if_needed
from app.services.backup_storage import ProviderOperationResult, upsert_storage_target
from app.services.observability import production_observability_summary
from app.services.recovery import mark_stale_recovery_jobs, run_backup, start_backup_job, start_restore_job
from tests.utils import session_scope


@dataclass
class FakeStorageProvider:
    store: dict[str, bytes] = field(default_factory=dict)
    target_type: str = "s3_compatible"

    def test_connection(self) -> ProviderOperationResult:
        return ProviderOperationResult(success=True, status="verified", summary="Connection verified.")

    def upload_artifact(self, *, key: str, payload: bytes, checksum: str) -> ProviderOperationResult:
        self.store[key] = payload
        return ProviderOperationResult(
            success=True,
            status="uploaded",
            summary="Artifact uploaded.",
            artifact_uri=f"s3://fortuna-test/{key}",
            size_bytes=len(payload),
            checksum=checksum,
        )

    def verify_artifact(self, *, artifact_uri: str, checksum: str) -> ProviderOperationResult:
        data = self.store.get(artifact_uri.removeprefix("s3://fortuna-test/"))
        if data is None:
            return ProviderOperationResult(success=False, status="failed", summary="Artifact missing.")
        if hashlib.sha256(data).hexdigest() != checksum:
            return ProviderOperationResult(success=False, status="failed", summary="Checksum mismatch.")
        return ProviderOperationResult(
            success=True,
            status="verified",
            summary="Artifact verified.",
            artifact_uri=artifact_uri,
            size_bytes=len(data),
            checksum=checksum,
            data=data,
        )

    def download_artifact(self, *, artifact_uri: str) -> ProviderOperationResult:
        data = self.store.get(artifact_uri.removeprefix("s3://fortuna-test/"))
        if data is None:
            return ProviderOperationResult(success=False, status="failed", summary="Artifact missing.")
        return ProviderOperationResult(success=True, status="downloaded", summary="Downloaded.", data=data)


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=5806, owner_telegram_id=5806, display_name="Rex")


def _active_target(session, owner, provider: FakeStorageProvider) -> BackupStorageTarget:
    return upsert_storage_target(
        session,
        actor=owner,
        name="S3-Compatible Backup Storage",
        target_type="s3_compatible",
        config={
            "endpoint": "https://storage.example.test",
            "bucket": "fortuna-backups",
            "region": "us-east-1",
            "access_key": "ACCESSKEY1234",
            "secret_key": "super-secret-storage-key",
        },
        provider=provider,
    )


def test_recovery_renderers_are_side_effect_free() -> None:
    with session_scope() as session:
        owner = _owner(session)

        backup_screen = render_backup_run_page(session, owner)
        restore_screen = render_restore_test_page(session, owner)

        assert "No backup has started yet" in backup_screen.text
        assert "No restore validation has started yet" in restore_screen.text
        assert session.query(BackupRun).count() == 0
        assert session.query(RestoreTestRun).count() == 0


def test_backup_job_start_reuses_active_job_and_finishes_by_identifier(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        provider = FakeStorageProvider()
        _active_target(session, owner, provider)
        monkeypatch.setattr(recovery_service.settings, "encryption_key", SecretStr("test-encryption-key"))
        monkeypatch.setattr(recovery_service, "provider_for_target", lambda target: provider)

        run, started = start_backup_job(session, actor=owner)
        again, again_started = start_backup_job(session, actor=owner)

        assert started is True
        assert again_started is False
        assert again.id == run.id
        assert run.status == "running"

        finished = run_backup(session, actor=owner, run_identifier=run.run_identifier)

        assert finished.id == run.id
        assert finished.status == "succeeded"
        assert finished.artifact_verified is True
        assert session.query(BackupRun).filter_by(run_identifier=run.run_identifier).count() == 1


def test_stale_recovery_jobs_mark_timed_out_and_surface_in_status() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            BackupRun(
                run_identifier="backup-stale",
                backup_type="manual",
                status="running",
                started_at=datetime.now(UTC) - timedelta(minutes=30),
                storage_target="S3-Compatible Backup Storage",
                encrypted=False,
                created_by_user_id=owner.id,
            )
        )
        session.add(
            RestoreTestRun(
                run_identifier="restore-stale",
                status="running",
                started_at=datetime.now(UTC) - timedelta(minutes=30),
            )
        )
        session.flush()

        backup_count, restore_count = mark_stale_recovery_jobs(session)
        botstatus = render_botstatus_page(session, owner, details=True)
        observability = render_production_observability_page(session, owner, details=True)
        selftest = render_ui_self_test_page(session, owner, run_now=True, details=True)

        assert backup_count == 1
        assert restore_count == 1
        assert session.query(BackupRun).filter_by(status="timed_out").count() == 1
        assert session.query(RestoreTestRun).filter_by(status="timed_out").count() == 1
        assert "Recovery Timed Out Marked" in botstatus.text
        assert "Timed Out Jobs Marked" in observability.text
        assert "Timed Out Jobs Marked" in selftest.text


def test_running_recovery_job_appears_in_observability_without_being_critical() -> None:
    with session_scope() as session:
        owner = _owner(session)
        run, started = start_backup_job(session, actor=owner)
        summary = production_observability_summary(session)
        screen = render_backup_run_page(session, owner)

        assert started is True
        assert run.status == "running"
        assert summary["recovery_job_active"] is True
        assert summary["recovery_job_active_type"] == "backup"
        assert "Backup running" in screen.text


def test_restore_job_start_reuses_active_job() -> None:
    with session_scope() as session:
        owner = _owner(session)
        run, started = start_restore_job(session, actor=owner)
        again, again_started = start_restore_job(session, actor=owner)

        assert started is True
        assert again_started is False
        assert again.id == run.id
        assert run.status == "running"
