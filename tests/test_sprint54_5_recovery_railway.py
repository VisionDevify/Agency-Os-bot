from __future__ import annotations

from datetime import UTC, datetime

from pydantic import SecretStr

from app.bot.screens.recovery import render_backup_storage_page
from app.core.config import settings
from app.models.recovery import BackupRun, BackupStorageTarget, RestoreTestRun
from app.services.auth import setup_owner_if_needed
from app.services.backup_storage import ProviderOperationResult, backup_s3_environment_state
from app.services.recovery import recovery_risk_assessment, record_backup_run
from scripts.verify_railway import CommandResult, build_report
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=5451, owner_telegram_id=5451, display_name="Rex")


def test_backup_s3_environment_state_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "backup_s3_endpoint", None)
    monkeypatch.setattr(settings, "backup_s3_bucket", None)
    monkeypatch.setattr(settings, "backup_s3_region", None)
    monkeypatch.setattr(settings, "backup_s3_access_key", SecretStr(""))
    monkeypatch.setattr(settings, "backup_s3_secret_key", SecretStr(""))

    state = backup_s3_environment_state()

    assert state["configured"] is False
    assert "BACKUP_S3_ENDPOINT" in state["missing"]
    assert state["access_key_masked"] == "Not set"
    assert state["secret_key_status"] == "Missing"


def test_backup_s3_environment_state_configured_masks_values(monkeypatch) -> None:
    monkeypatch.setattr(settings, "backup_s3_endpoint", "https://storage.example.test")
    monkeypatch.setattr(settings, "backup_s3_bucket", "fortuna")
    monkeypatch.setattr(settings, "backup_s3_region", "us-east-1")
    monkeypatch.setattr(settings, "backup_s3_access_key", SecretStr("ACCESSKEY1234"))
    monkeypatch.setattr(settings, "backup_s3_secret_key", SecretStr("do-not-render"))

    state = backup_s3_environment_state()

    assert state["configured"] is True
    assert state["missing"] == []
    assert state["access_key_masked"] == "****1234"
    assert state["secret_key_status"] == "Configured"
    assert "ACCESSKEY1234" not in str(state)
    assert "do-not-render" not in str(state)


def test_backup_storage_screen_owner_guidance_and_backblaze_s3_note(monkeypatch) -> None:
    monkeypatch.setattr(settings, "backup_s3_endpoint", None)
    monkeypatch.setattr(settings, "backup_s3_bucket", None)
    monkeypatch.setattr(settings, "backup_s3_access_key", SecretStr(""))
    monkeypatch.setattr(settings, "backup_s3_secret_key", SecretStr(""))
    with session_scope() as session:
        owner = _owner(session)
        storage = render_backup_storage_page(session, owner)
        s3 = render_backup_storage_page(session, owner, target_type="s3_compatible")
        b2 = render_backup_storage_page(session, owner, target_type="backblaze_b2")

        combined = f"{storage.text}\n{s3.text}\n{b2.text}"
        assert "Add your backup storage variables in Railway" in storage.text
        assert "BACKUP_S3_* variables" in s3.text
        assert "Endpoint: Missing" in s3.text
        assert "Access Key: Not set" in s3.text
        assert "Use Backblaze's S3-compatible endpoint" in combined
        assert "do-not-render" not in combined


def test_fake_success_without_artifact_does_not_create_protected_state() -> None:
    with session_scope() as session:
        owner = _owner(session)
        run = record_backup_run(
            session,
            actor=owner,
            status="succeeded",
            encrypted=True,
            checksum=None,
            artifact_uri=None,
            artifact_verified=False,
            external_storage_used=False,
        )
        assessment = recovery_risk_assessment(session, now=datetime.now(UTC))

        assert run.status == "manual_required"
        assert assessment.status == "critical"
        assert assessment.protection_status != "Protected by recent verified backups"


def test_verified_backup_without_restore_is_needs_review() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            BackupStorageTarget(
                name="S3-Compatible Backup Storage",
                target_type="s3_compatible",
                enabled=True,
                encrypted=True,
                connection_status="active",
                provider_available=True,
            )
        )
        record_backup_run(
            session,
            actor=owner,
            status="succeeded",
            storage_target="S3-Compatible Backup Storage",
            encrypted=True,
            checksum="a" * 64,
            artifact_uri="s3://bucket/backup.enc",
            artifact_verified=True,
            external_storage_used=True,
        )

        assert recovery_risk_assessment(session, now=datetime.now(UTC)).status == "needs_review"


def test_failed_restore_validation_prevents_healthy_status() -> None:
    with session_scope() as session:
        owner = _owner(session)
        backup = BackupRun(
            run_identifier="backup-restore-fail",
            backup_type="manual",
            status="succeeded",
            storage_target="S3-Compatible Backup Storage",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            encrypted=True,
            checksum="b" * 64,
            artifact_uri="s3://bucket/backup.enc",
            artifact_verified=True,
            external_storage_used=True,
        )
        session.add_all(
            [
                BackupStorageTarget(
                    name="S3-Compatible Backup Storage",
                    target_type="s3_compatible",
                    enabled=True,
                    encrypted=True,
                    connection_status="active",
                    provider_available=True,
                ),
                backup,
            ]
        )
        session.flush()
        session.add(
            RestoreTestRun(
                run_identifier="restore-failed",
                backup_run_id=backup.id,
                status="failed",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                checksum_verified=False,
                decrypt_verified=False,
                full_restore_performed=False,
                error_summary="Checksum validation failed.",
            )
        )

        assert recovery_risk_assessment(session, now=datetime.now(UTC)).status == "needs_attention"


def test_railway_verification_script_handles_cli_missing() -> None:
    report = build_report(railway_command=[], runner=lambda _cmd, _timeout: CommandResult(127, "", "missing"))

    assert report["railway_cli"]["status"] == "unavailable"
    assert report["auth"]["status"] == "unavailable"
    assert report["services"]["api"]["status"] == "unavailable"
    assert report["services"]["worker"]["status"] == "unavailable"
    assert report["services"]["postgres"]["status"] == "unavailable"
    assert report["services"]["redis"]["status"] == "unavailable"


def test_railway_verification_script_handles_auth_missing() -> None:
    def runner(command: list[str], _timeout: int) -> CommandResult:
        if "--version" in command:
            return CommandResult(0, "railway 5.15.0", "")
        if "whoami" in command:
            return CommandResult(1, "", "Unauthorized. Please login with `railway login`")
        return CommandResult(1, "", "not reached")

    report = build_report(railway_command=["railway"], runner=runner)

    assert report["railway_cli"]["status"] == "pass"
    assert report["auth"]["status"] == "unavailable"
    assert report["auth"]["severity"] == "blocking"
    assert report["services"]["api"]["status"] == "unavailable"


def test_railway_verification_script_service_discovery_success() -> None:
    def runner(command: list[str], _timeout: int) -> CommandResult:
        if "--version" in command:
            return CommandResult(0, "railway 5.15.0", "")
        if "whoami" in command:
            return CommandResult(0, "VisionDevify", "")
        if "status" in command:
            return CommandResult(
                0,
                '{"project":"Fortuna","services":["Agency-Os-bot API","sparkling-cat worker","Postgres","Redis"]}',
                "",
            )
        return CommandResult(0, "", "")

    report = build_report(railway_command=["railway"], runner=runner)

    assert report["railway_cli"]["status"] == "pass"
    assert report["auth"]["status"] == "pass"
    assert report["project"]["status"] == "pass"
    assert report["services"]["api"]["status"] == "pass"
    assert report["services"]["worker"]["status"] == "pass"
    assert report["services"]["postgres"]["status"] == "pass"
    assert report["services"]["redis"]["status"] == "pass"


def test_connection_result_statuses_remain_explicit() -> None:
    result = ProviderOperationResult(success=False, status="not_configured", summary="Missing storage setting.")

    assert result.status == "not_configured"
    assert result.success is False
