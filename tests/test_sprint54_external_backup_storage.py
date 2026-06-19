from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

import app.services.recovery as recovery_service
from app.bot.screens.recovery import (
    render_backup_run_page,
    render_backup_storage_page,
    render_recovery_center_page,
)
from app.bot.screens.settings import render_production_observability_page
from app.models.recovery import BackupRun, BackupStorageTarget, RestoreTestRun
from app.services.auth import setup_owner_if_needed
from app.services.automations import execute_action
from app.services.backup_storage import (
    ProviderOperationResult,
    decrypt_storage_config,
    mask_credential,
    upsert_storage_target,
)
from app.services.recovery import recovery_risk_assessment, record_backup_run, run_backup, run_restore_test
from tests.utils import session_scope


@dataclass
class FakeStorageProvider:
    fail_connection: bool = False
    fail_upload: bool = False
    corrupt_verify: bool = False
    store: dict[str, bytes] = field(default_factory=dict)
    target_type: str = "s3_compatible"

    def test_connection(self) -> ProviderOperationResult:
        if self.fail_connection:
            return ProviderOperationResult(
                success=False,
                status="failed",
                summary="Fortuna could not authenticate with this storage target.",
            )
        return ProviderOperationResult(
            success=True,
            status="verified",
            summary="Connection verified with write, read, and cleanup checks.",
        )

    def upload_artifact(self, *, key: str, payload: bytes, checksum: str) -> ProviderOperationResult:
        if self.fail_upload:
            return ProviderOperationResult(success=False, status="failed", summary="Upload failed safely.")
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
            return ProviderOperationResult(success=False, status="failed", summary="Artifact was not found.")
        actual = "bad" if self.corrupt_verify else hashlib.sha256(data).hexdigest()
        if actual != checksum:
            return ProviderOperationResult(success=False, status="failed", summary="Checksum verification failed.")
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
            return ProviderOperationResult(success=False, status="failed", summary="Artifact was not found.")
        return ProviderOperationResult(
            success=True,
            status="downloaded",
            summary="Artifact downloaded.",
            artifact_uri=artifact_uri,
            size_bytes=len(data),
            checksum=hashlib.sha256(data).hexdigest(),
            data=data,
        )


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=5401, owner_telegram_id=5401, display_name="Rex")


def _storage_config() -> dict[str, str]:
    return {
        "endpoint": "https://storage.example.test",
        "bucket": "fortuna-backups",
        "region": "us-east-1",
        "access_key": "ACCESSKEY1234",
        "secret_key": "super-secret-storage-key",
    }


def _active_target(session, owner, provider: FakeStorageProvider) -> BackupStorageTarget:
    return upsert_storage_target(
        session,
        actor=owner,
        name="S3-Compatible Backup Storage",
        target_type="s3_compatible",
        config=_storage_config(),
        provider=provider,
    )


def test_storage_credentials_are_encrypted_masked_and_never_rendered() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target = _active_target(session, owner, FakeStorageProvider())
        screen = render_backup_storage_page(session, owner, target_type="s3_compatible")

        assert target.enabled is True
        assert target.connection_status == "active"
        assert target.provider_available is True
        assert "super-secret-storage-key" not in (target.encrypted_config_json or "")
        assert decrypt_storage_config(target)["secret_key"] == "super-secret-storage-key"
        assert target.masked_config_json["access_key"] == "****1234"
        assert "super-secret-storage-key" not in screen.text
        assert "ACCESSKEY1234" not in screen.text
        assert "Encrypted" in screen.text
        assert mask_credential("abcd") == "****abcd"


def test_storage_connection_failure_does_not_activate_target() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target = _active_target(session, owner, FakeStorageProvider(fail_connection=True))
        screen = render_backup_storage_page(session, owner, target_type="s3_compatible")

        assert target.enabled is False
        assert target.connection_status == "failed"
        assert target.provider_available is False
        assert "Connection failed" in screen.text
        assert "super-secret-storage-key" not in screen.text


def test_backup_upload_success_requires_verified_encrypted_artifact(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        provider = FakeStorageProvider()
        _active_target(session, owner, provider)
        monkeypatch.setattr(recovery_service.settings, "encryption_key", SecretStr("test-encryption-key"))
        monkeypatch.setattr(recovery_service, "provider_for_target", lambda target: provider)

        run = run_backup(session, actor=owner)
        screen = render_backup_run_page(session, owner)

        assert run.status == "succeeded"
        assert run.artifact_uri
        assert run.artifact_verified is True
        assert run.external_storage_used is True
        assert run.encrypted is True
        assert run.checksum
        assert session.query(BackupRun).filter_by(run_identifier=run.run_identifier).count() == 1
        assert "super-secret-storage-key" not in screen.text


def test_backup_upload_failure_is_not_reported_as_success(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        provider = FakeStorageProvider(fail_upload=True)
        _active_target(session, owner, provider)
        monkeypatch.setattr(recovery_service.settings, "encryption_key", SecretStr("test-encryption-key"))
        monkeypatch.setattr(recovery_service, "provider_for_target", lambda target: provider)

        run = run_backup(session, actor=owner)

        assert run.status == "failed"
        assert run.artifact_verified is False
        assert run.artifact_uri is None
        assert run.external_storage_used is False


def test_restore_validation_downloads_verifies_and_decrypts_artifact(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        provider = FakeStorageProvider()
        _active_target(session, owner, provider)
        monkeypatch.setattr(recovery_service.settings, "encryption_key", SecretStr("test-encryption-key"))
        monkeypatch.setattr(recovery_service, "provider_for_target", lambda target: provider)

        backup = run_backup(session, actor=owner)
        restore = run_restore_test(session, actor=owner)

        assert backup.status == "succeeded"
        assert restore.status == "verified_only"
        assert restore.checksum_verified is True
        assert restore.decrypt_verified is True
        assert restore.full_restore_performed is False
        assert session.query(RestoreTestRun).filter_by(run_identifier=restore.run_identifier).count() == 1


def test_recovery_status_transitions_use_canonical_evidence(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        now = datetime.now(UTC)

        assert recovery_risk_assessment(session, now=now).status == "critical"

        provider = FakeStorageProvider()
        _active_target(session, owner, provider)
        assert recovery_risk_assessment(session, now=now).status == "needs_attention"

        backup = record_backup_run(
            session,
            actor=owner,
            status="succeeded",
            storage_target="S3-Compatible Backup Storage",
            encrypted=True,
            checksum="c" * 64,
            artifact_uri="s3://fortuna-test/backup.enc",
            artifact_verified=True,
            external_storage_used=True,
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1),
        )
        assert recovery_risk_assessment(session, now=now).status == "needs_review"

        session.add(
            RestoreTestRun(
                run_identifier="restore-healthy",
                backup_run_id=backup.id,
                status="passed",
                started_at=now,
                finished_at=now,
                result_summary='{"checksum_verified": true, "archive_decrypts": true, "test_database_restored": true}',
                checksum_verified=True,
                decrypt_verified=True,
                full_restore_performed=True,
            )
        )
        session.flush()

        assessment = recovery_risk_assessment(session, now=now)
        assert assessment.status == "healthy"
        assert assessment.protection_status == "Verified backup; add redundancy when ready"


def test_observability_and_recovery_screens_share_recovery_status_without_secrets() -> None:
    with session_scope() as session:
        owner = _owner(session)
        provider = FakeStorageProvider()
        _active_target(session, owner, provider)

        observability = render_production_observability_page(session, owner)
        recovery = render_recovery_center_page(session, owner)
        combined = f"{observability.text}\n{recovery.text}"

        assert "Recovery" in combined
        assert "super-secret-storage-key" not in combined
        assert "ACCESSKEY1234" not in combined
        assert "Backup needs setup" not in combined
        assert "Run your first backup" in combined or "Run a backup" in combined


def test_scheduled_recovery_backup_action_uses_honest_backup_path() -> None:
    with session_scope() as session:
        owner = _owner(session)

        result = execute_action(
            session,
            {"type": "run_recovery_backup", "backup_type": "nightly"},
            actor=owner,
        )

        assert result["status"] == "not_configured"
        assert result["artifact_verified"] is False
        assert result["external_storage_used"] is False
        run = session.get(BackupRun, result["backup_run_id"])
        assert run is not None
        assert run.backup_type == "nightly"
