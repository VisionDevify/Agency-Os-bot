from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account
from app.models.automation import AutomationRule
from app.models.learning import LearningEvent, OutcomeMemory, Playbook
from app.models.model_brand import ModelBrand
from app.models.opportunity import CreatorWatch, Opportunity, PostWatch
from app.models.permissions import Role
from app.models.proxy import Proxy
from app.models.recovery import BackupRun, BackupStorageTarget, RestoreTestRun
from app.models.reporting import NotificationTarget
from app.models.social import SocialDiscoveryLead, SocialSource
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action, user_has_permission
from app.services.events import emit_event
from app.services.recommendations import upsert_recommendation

BACKUP_FRESHNESS_TARGET_HOURS = 24
RESTORE_TEST_STALE_DAYS = 30
BACKUP_FAILURE_LOOKBACK_DAYS = 7
BACKUP_COPY_LOOKBACK_DAYS = 7
SUCCESS_BACKUP_STATUSES = {"success", "succeeded"}
TERMINAL_BACKUP_STATUSES = {"success", "succeeded", "failed", "skipped", "manual_required", "not_configured"}
TERMINAL_RESTORE_STATUSES = {"verified_only", "verified", "passed", "succeeded", "failed", "skipped", "not_available"}


@dataclass(frozen=True)
class RecoveryAssessment:
    protection_status: str
    last_backup_status: str
    restore_test_status: str
    backup_copies_count: int
    recovery_confidence: str
    risk_score: int
    risk_level: str
    evidence: tuple[str, ...]
    alerts: tuple[str, ...]
    next_best_move: str
    latest_backup: BackupRun | None
    latest_restore_test: RestoreTestRun | None
    external_storage_configured: bool
    encryption_status: str
    checksum_status: str
    recent_failure_count: int


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _new_run_identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _backup_is_verified_success(run: BackupRun | None) -> bool:
    return bool(
        run
        and run.status in SUCCESS_BACKUP_STATUSES
        and run.artifact_uri
        and run.artifact_verified
        and run.checksum
        and run.encrypted
    )


def _backup_is_terminal(run: BackupRun | None) -> bool:
    return bool(run and run.status in TERMINAL_BACKUP_STATUSES)


def _restore_is_terminal(run: RestoreTestRun | None) -> bool:
    return bool(run and run.status in TERMINAL_RESTORE_STATUSES)


def _require_owner_or_admin(session: Session, actor: User | None) -> None:
    if actor is not None and (actor.is_owner or user_has_permission(actor, "manage_roles")):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="recovery_center",
        status="denied",
        details={"permission": "owner_or_admin"},
    )
    raise PermissionError("Recovery Center is owner/admin only.")


def _latest_backup(session: Session, *, succeeded_only: bool = False) -> BackupRun | None:
    statement = select(BackupRun).order_by(desc(BackupRun.started_at), desc(BackupRun.id))
    if succeeded_only:
        statement = statement.where(
            BackupRun.status.in_(tuple(SUCCESS_BACKUP_STATUSES)),
            BackupRun.artifact_uri.is_not(None),
            BackupRun.artifact_verified.is_(True),
            BackupRun.checksum.is_not(None),
            BackupRun.encrypted.is_(True),
        )
    return session.scalar(statement.limit(1))


def _latest_restore_test(session: Session) -> RestoreTestRun | None:
    return session.scalar(select(RestoreTestRun).order_by(desc(RestoreTestRun.started_at), desc(RestoreTestRun.id)).limit(1))


def _enabled_storage_targets(session: Session) -> list[BackupStorageTarget]:
    return list(
        session.scalars(
            select(BackupStorageTarget)
            .where(BackupStorageTarget.enabled.is_(True))
            .order_by(BackupStorageTarget.name)
        ).all()
    )


def backup_copy_count(session: Session, *, now: datetime | None = None) -> int:
    current = now or _now()
    since = current - timedelta(days=BACKUP_COPY_LOOKBACK_DAYS)
    targets = session.scalars(
        select(BackupRun.storage_target)
        .where(
            BackupRun.status.in_(tuple(SUCCESS_BACKUP_STATUSES)),
            BackupRun.started_at >= since,
            BackupRun.storage_target.is_not(None),
            BackupRun.artifact_uri.is_not(None),
            BackupRun.artifact_verified.is_(True),
            BackupRun.checksum.is_not(None),
            BackupRun.encrypted.is_(True),
        )
        .distinct()
    ).all()
    return len([target for target in targets if target])


def _backup_age_hours(backup: BackupRun | None, *, now: datetime) -> int | None:
    if backup is None:
        return None
    return max(0, round((_aware(now) - _aware(backup.started_at)).total_seconds() / 3600))


def _risk_level(score: int) -> str:
    if score <= 24:
        return "Low"
    if score <= 49:
        return "Moderate"
    if score <= 74:
        return "High"
    return "Critical"


def _confidence_for(score: int, latest_backup: BackupRun | None, latest_restore: RestoreTestRun | None) -> str:
    if latest_backup is None:
        return "Not set up yet"
    if latest_restore is None:
        return "Not tested yet"
    if score <= 24:
        return "High"
    if score <= 49:
        return "Moderate"
    if score <= 74:
        return "Low"
    return "Very low"


def _restore_result_json(restore: RestoreTestRun | None) -> dict[str, Any]:
    if restore is None or not restore.result_summary:
        return {}
    try:
        payload = json.loads(restore.result_summary)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def recovery_risk_assessment(session: Session, *, now: datetime | None = None) -> RecoveryAssessment:
    current = now or _now()
    latest_any = _latest_backup(session)
    latest_success = _latest_backup(session, succeeded_only=True)
    latest_restore = _latest_restore_test(session)
    enabled_targets = _enabled_storage_targets(session)
    external_storage_configured = any(target.target_type not in {"local_runtime", "manual_export"} for target in enabled_targets)
    copies = backup_copy_count(session, now=current)
    failure_since = current - timedelta(days=BACKUP_FAILURE_LOOKBACK_DAYS)
    recent_failure_count = session.scalar(
        select(func.count(BackupRun.id)).where(BackupRun.status == "failed", BackupRun.started_at >= failure_since)
    ) or 0

    risk = 0
    evidence: list[str] = []

    if latest_success is None:
        risk += 35
        evidence.append("No successful backup has been recorded.")
        last_backup_status = "Not set up yet"
    else:
        age_hours = _backup_age_hours(latest_success, now=current) or 0
        last_backup_status = f"{latest_success.status.title()} {age_hours}h ago"
        evidence.append(f"Latest successful backup is {age_hours} hours old.")
        if age_hours > BACKUP_FRESHNESS_TARGET_HOURS:
            risk += 15
            evidence.append("Backup is older than the freshness target.")
        if age_hours > 72:
            risk += 15
            evidence.append("Backup is more than 72 hours old.")

    if latest_any is not None and latest_any.status == "failed":
        evidence.append("The most recent backup attempt failed.")
        risk += 10

    if recent_failure_count:
        added = min(20, recent_failure_count * 5)
        risk += added
        evidence.append(f"{recent_failure_count} backup failure(s) in the last {BACKUP_FAILURE_LOOKBACK_DAYS} days.")

    if copies == 0:
        risk += 25
        evidence.append("No verified backup copies were found in the recent window.")
    elif copies == 1:
        risk += 15
        evidence.append("Only one recent backup copy is verified.")
    else:
        evidence.append(f"{copies} recent backup copies are verified.")

    if not external_storage_configured:
        risk += 10
        evidence.append("No external storage target is enabled yet.")
    else:
        evidence.append("At least one external storage target is enabled.")

    encrypted = bool(latest_success and latest_success.encrypted)
    checksum_present = bool(latest_success and latest_success.checksum)
    encryption_status = "Encrypted" if encrypted else "Not set up yet"
    checksum_status = "Recorded" if checksum_present else "Not set up yet"
    if not encrypted:
        risk += 20
        evidence.append("Latest successful backup is not recorded as encrypted.")
    else:
        evidence.append("Latest successful backup is recorded as encrypted.")
    if not checksum_present:
        risk += 15
        evidence.append("Latest successful backup has no checksum recorded.")
    else:
        evidence.append("Latest successful backup has a checksum recorded.")

    restore_payload = _restore_result_json(latest_restore)
    if latest_restore is None:
        risk += 25
        restore_status = "Not tested yet"
        evidence.append("No restore test has been recorded.")
    else:
        restore_age_days = max(0, round((_aware(current) - _aware(latest_restore.started_at)).total_seconds() / 86400))
        checksum_verified = bool(latest_restore.checksum_verified or restore_payload.get("checksum_verified"))
        restored_test_db = bool(latest_restore.full_restore_performed or restore_payload.get("test_database_restored"))
        if latest_restore.status in {"passed", "succeeded"} and restored_test_db:
            restore_status = f"Restore tested {restore_age_days}d ago"
        elif latest_restore.status in {"verified_only", "verified"} and checksum_verified:
            restore_status = f"Backup file verified {restore_age_days}d ago"
            risk += 10
            evidence.append("Backup file was verified, but no full test database restore is recorded.")
        elif latest_restore.status == "failed":
            restore_status = "Failed"
            risk += 25
            evidence.append("Latest restore test failed.")
        elif latest_restore.status == "not_available":
            restore_status = "Not available"
            risk += 20
            evidence.append("Restore testing could not run because no verified backup artifact was available.")
        else:
            restore_status = latest_restore.status.title()
            risk += 15
            evidence.append("Latest restore test is incomplete.")
        if restore_age_days > RESTORE_TEST_STALE_DAYS:
            risk += 15
            evidence.append("Restore test is stale.")

    score = _clamp_score(risk)
    level = _risk_level(score)
    confidence = _confidence_for(score, latest_success, latest_restore)
    if latest_success is None:
        protection_status = "Not set up yet"
        next_move = "Run your first backup and configure backup storage."
    elif latest_restore is None:
        protection_status = "Backup recorded, restore not tested"
        next_move = "Run a restore test so Fortuna can verify the backup."
    elif copies < 2 or not external_storage_configured:
        protection_status = "Needs external redundancy"
        next_move = "Configure an external backup target."
    elif score <= 24:
        protection_status = "Protected by recent verified backups"
        next_move = "Nothing urgent. Keep nightly backups enabled."
    else:
        protection_status = "Needs attention"
        next_move = evidence[0] if evidence else "Review Recovery Center details."

    alerts: list[str] = []
    if level != "Low":
        alerts.append(f"Recovery Alert - {level} Risk")

    return RecoveryAssessment(
        protection_status=protection_status,
        last_backup_status=last_backup_status,
        restore_test_status=restore_status,
        backup_copies_count=copies,
        recovery_confidence=confidence,
        risk_score=score,
        risk_level=level,
        evidence=tuple(evidence),
        alerts=tuple(alerts),
        next_best_move=next_move,
        latest_backup=latest_success,
        latest_restore_test=latest_restore,
        external_storage_configured=external_storage_configured,
        encryption_status=encryption_status,
        checksum_status=checksum_status,
        recent_failure_count=int(recent_failure_count),
    )


def _table_counts(session: Session) -> dict[str, int]:
    models = {
        "users": User,
        "roles": Role,
        "models": ModelBrand,
        "accounts": Account,
        "proxy_metadata": Proxy,
        "opportunities": Opportunity,
        "creators": CreatorWatch,
        "own_posts": PostWatch,
        "social_sources": SocialSource,
        "social_leads": SocialDiscoveryLead,
        "learning_events": LearningEvent,
        "outcome_memory": OutcomeMemory,
        "notification_targets": NotificationTarget,
        "automation_rules": AutomationRule,
        "playbooks": Playbook,
    }
    counts: dict[str, int] = {}
    for name, model in models.items():
        counts[name] = int(session.scalar(select(func.count(model.id))) or 0)
    return counts


def _backup_manifest(session: Session, backup_type: str, storage_target: str) -> dict[str, Any]:
    return sanitize_details(
        {
            "backup_type": backup_type,
            "storage_target": storage_target,
            "created_at": _now().isoformat(),
            "tables": _table_counts(session),
            "contents": "metadata_manifest_only",
            "proxy_passwords": "excluded_plaintext",
        }
    )


def _checksum(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ensure_local_storage_target(session: Session) -> BackupStorageTarget:
    target = session.scalar(select(BackupStorageTarget).where(BackupStorageTarget.name == "Railway Local Runtime"))
    if target is None:
        target = BackupStorageTarget(
            name="Railway Local Runtime",
            target_type="local_runtime",
            enabled=True,
            encrypted=True,
            notes="Runtime-local metadata target. External storage is still recommended.",
        )
        session.add(target)
        session.flush()
    return target


def record_backup_run(
    session: Session,
    *,
    actor: User | None,
    backup_type: str = "manual",
    status: str = "manual_required",
    run_identifier: str | None = None,
    storage_target: str = "local_runtime",
    encrypted: bool = True,
    checksum: str | None = None,
    artifact_uri: str | None = None,
    artifact_verified: bool = False,
    external_storage_used: bool = False,
    size_bytes: int | None = None,
    result_summary: str | None = None,
    error_summary: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> BackupRun:
    identifier = run_identifier or _new_run_identifier("backup")
    existing = session.scalar(select(BackupRun).where(BackupRun.run_identifier == identifier))
    if _backup_is_terminal(existing):
        return existing

    if status in SUCCESS_BACKUP_STATUSES and not (
        artifact_uri and artifact_verified and checksum and encrypted
    ):
        status = "manual_required"
        result_summary = result_summary or "Backup execution needs a verified artifact before it can count as successful."
        error_summary = error_summary or "No verified backup artifact was recorded."

    if existing is None:
        run = BackupRun(
            run_identifier=identifier,
            backup_type=backup_type,
            status=status,
            started_at=started_at or _now(),
            finished_at=finished_at or _now(),
            size_bytes=size_bytes,
            storage_target=storage_target,
            encrypted=encrypted,
            checksum=checksum,
            artifact_uri=artifact_uri,
            artifact_verified=artifact_verified,
            external_storage_used=external_storage_used,
            result_summary=result_summary,
            error_summary=error_summary,
            created_by_user_id=actor.id if actor else None,
        )
        session.add(run)
    else:
        run = existing
        run.status = status
        run.finished_at = finished_at or _now()
        run.size_bytes = size_bytes
        run.storage_target = storage_target
        run.encrypted = encrypted
        run.checksum = checksum
        run.artifact_uri = artifact_uri
        run.artifact_verified = artifact_verified
        run.external_storage_used = external_storage_used
        run.result_summary = result_summary
        run.error_summary = error_summary
    target = session.scalar(select(BackupStorageTarget).where(BackupStorageTarget.name == storage_target))
    if target is not None:
        if status in SUCCESS_BACKUP_STATUSES:
            target.last_success_at = run.finished_at
        elif status == "failed":
            target.last_failure_at = run.finished_at
    session.flush()
    return run


def run_backup(session: Session, *, actor: User | None, backup_type: str = "manual") -> BackupRun:
    _require_owner_or_admin(session, actor)
    target = ensure_local_storage_target(session)
    started = _now()
    encrypted = bool(settings.encryption_key.get_secret_value())
    if not encrypted:
        run = record_backup_run(
            session,
            actor=actor,
            backup_type=backup_type,
            status="failed",
            storage_target=target.name,
            encrypted=False,
            error_summary="Encryption key is not configured.",
            started_at=started,
            finished_at=_now(),
        )
    else:
        run = record_backup_run(
            session,
            actor=actor,
            backup_type=backup_type,
            status="manual_required",
            storage_target=target.name,
            encrypted=True,
            result_summary=(
                "Automated Postgres export is not configured in this runtime. "
                "Use Manual Export or configure external backup storage before Fortuna can count backups as protected."
            ),
            error_summary="Manual backup export or external storage configuration is required.",
            started_at=started,
            finished_at=_now(),
        )
    audit_action(
        session,
        actor=actor,
        action="backup.run_completed",
        resource_type="backup_run",
        resource_id=str(run.id),
        status=run.status,
        details={"backup_type": backup_type, "storage_target": target.target_type, "encrypted": run.encrypted},
    )
    emit_event(
        session,
        actor=actor,
        event_name="backup.run_completed",
        resource_type="backup_run",
        resource_id=str(run.id),
        status=run.status,
        payload={"backup_type": backup_type, "encrypted": run.encrypted},
    )
    if run.status in {"failed", "manual_required", "not_configured"}:
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="recovery_backup_failed",
            title="Backup needs attention",
            description=run.error_summary or "Fortuna could not record a verified backup artifact.",
            severity="critical" if run.status == "failed" else "warning",
            entity_type="backup_run",
            entity_id=run.id,
            metadata={"reason": run.status, "run_identifier": run.run_identifier},
        )
    return run


def run_restore_test(session: Session, *, actor: User | None, run_identifier: str | None = None) -> RestoreTestRun:
    _require_owner_or_admin(session, actor)
    identifier = run_identifier or _new_run_identifier("restore")
    existing = session.scalar(select(RestoreTestRun).where(RestoreTestRun.run_identifier == identifier))
    if _restore_is_terminal(existing):
        return existing

    backup = _latest_backup(session, succeeded_only=True)
    started = _now()
    if backup is None:
        payload = {
            "backup_run_id": None,
            "status": "not_available",
            "result_summary": "No verified backup artifact is available yet.",
            "error_summary": "Run a backup that produces a verified artifact before testing restore readiness.",
            "checksum_verified": False,
            "decrypt_verified": False,
            "full_restore_performed": False,
        }
    elif not _backup_is_verified_success(backup):
        payload = {
            "backup_run_id": backup.id,
            "status": "failed",
            "result_summary": "Backup metadata is incomplete.",
            "error_summary": "A verified encrypted backup artifact and checksum are required before restore testing.",
            "checksum_verified": False,
            "decrypt_verified": False,
            "full_restore_performed": False,
        }
    else:
        summary_payload = {
            "checksum_verified": True,
            "archive_decrypts": True,
            "test_database_restored": False,
            "message": "Fortuna verified the backup file metadata, but no test restore database is configured yet.",
        }
        payload = {
            "backup_run_id": backup.id,
            "status": "verified_only",
            "result_summary": json.dumps(summary_payload, sort_keys=True),
            "error_summary": None,
            "checksum_verified": True,
            "decrypt_verified": True,
            "full_restore_performed": False,
        }
    if existing is None:
        test = RestoreTestRun(
            run_identifier=identifier,
            started_at=started,
            finished_at=_now(),
            **payload,
        )
        session.add(test)
    else:
        test = existing
        test.backup_run_id = payload["backup_run_id"]
        test.status = payload["status"]
        test.finished_at = _now()
        test.result_summary = payload["result_summary"]
        test.error_summary = payload["error_summary"]
        test.checksum_verified = payload["checksum_verified"]
        test.decrypt_verified = payload["decrypt_verified"]
        test.full_restore_performed = payload["full_restore_performed"]
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="restore_test.completed",
        resource_type="restore_test_run",
        resource_id=str(test.id),
        status=test.status,
        details={"backup_run_id": test.backup_run_id},
    )
    emit_event(
        session,
        actor=actor,
        event_name="restore_test.completed",
        resource_type="restore_test_run",
        resource_id=str(test.id),
        status=test.status,
        payload={"backup_run_id": test.backup_run_id},
    )
    return test


def backup_history(session: Session, *, limit: int = 10) -> list[BackupRun]:
    return list(session.scalars(select(BackupRun).order_by(desc(BackupRun.started_at), desc(BackupRun.id)).limit(limit)).all())
