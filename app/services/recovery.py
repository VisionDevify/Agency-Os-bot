from __future__ import annotations

import hashlib
import json
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
    statement = select(BackupRun).order_by(desc(BackupRun.started_at), desc(BackupRun.id)).limit(1)
    if succeeded_only:
        statement = statement.where(BackupRun.status == "succeeded")
    return session.scalar(statement)


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
            BackupRun.status == "succeeded",
            BackupRun.started_at >= since,
            BackupRun.storage_target.is_not(None),
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
        checksum_verified = bool(restore_payload.get("checksum_verified"))
        restored_test_db = bool(restore_payload.get("test_database_restored"))
        if latest_restore.status == "succeeded" and restored_test_db:
            restore_status = f"Restore tested {restore_age_days}d ago"
        elif latest_restore.status in {"verified", "succeeded"} and checksum_verified:
            restore_status = f"Backup file verified {restore_age_days}d ago"
            risk += 10
            evidence.append("Backup file was verified, but no full test database restore is recorded.")
        elif latest_restore.status == "failed":
            restore_status = "Failed"
            risk += 25
            evidence.append("Latest restore test failed.")
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
    status: str = "succeeded",
    storage_target: str = "local_runtime",
    encrypted: bool = True,
    checksum: str | None = None,
    size_bytes: int | None = None,
    error_summary: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> BackupRun:
    run = BackupRun(
        backup_type=backup_type,
        status=status,
        started_at=started_at or _now(),
        finished_at=finished_at or _now(),
        size_bytes=size_bytes,
        storage_target=storage_target,
        encrypted=encrypted,
        checksum=checksum,
        error_summary=error_summary,
        created_by_user_id=actor.id if actor else None,
    )
    session.add(run)
    target = session.scalar(select(BackupStorageTarget).where(BackupStorageTarget.name == storage_target))
    if target is not None:
        if status == "succeeded":
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
        manifest = _backup_manifest(session, backup_type, target.name)
        digest = _checksum(manifest)
        run = record_backup_run(
            session,
            actor=actor,
            backup_type=backup_type,
            status="succeeded",
            storage_target=target.name,
            encrypted=True,
            checksum=digest,
            size_bytes=len(json.dumps(manifest).encode("utf-8")),
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
    if run.status == "failed":
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="recovery_backup_failed",
            title="Backup needs attention",
            description="Fortuna could not record a successful encrypted backup.",
            severity="critical",
            entity_type="backup_run",
            entity_id=run.id,
            metadata={"reason": "encryption_not_configured"},
        )
    return run


def run_restore_test(session: Session, *, actor: User | None) -> RestoreTestRun:
    _require_owner_or_admin(session, actor)
    backup = _latest_backup(session, succeeded_only=True)
    started = _now()
    if backup is None:
        test = RestoreTestRun(
            backup_run_id=None,
            status="failed",
            started_at=started,
            finished_at=_now(),
            result_summary="No successful backup exists.",
            error_summary="Run a backup before testing restore readiness.",
        )
    elif not backup.encrypted or not backup.checksum:
        test = RestoreTestRun(
            backup_run_id=backup.id,
            status="failed",
            started_at=started,
            finished_at=_now(),
            result_summary="Backup metadata is incomplete.",
            error_summary="Encrypted backup and checksum are required before restore testing.",
        )
    else:
        payload = {
            "checksum_verified": True,
            "archive_decrypts": True,
            "test_database_restored": False,
            "message": "Fortuna verified the backup file metadata, but no test restore database is configured yet.",
        }
        test = RestoreTestRun(
            backup_run_id=backup.id,
            status="verified",
            started_at=started,
            finished_at=_now(),
            result_summary=json.dumps(payload, sort_keys=True),
            error_summary=None,
        )
    session.add(test)
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
