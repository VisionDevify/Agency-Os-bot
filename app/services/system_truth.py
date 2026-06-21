from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.autonomous_operations import FollowUp
from app.models.callback_error import CallbackErrorLog
from app.models.coo import PriorityItem
from app.models.event_log import EventLog
from app.models.friction import FrictionItem
from app.models.intelligence import IntelligenceSignal, IssuePattern
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.models.user import User
from app.services.agency_activation import build_activation_report
from app.services.auth import audit_action
from app.services.bot_instances import bot_instance_diagnostics
from app.services.events import emit_event
from app.services.heartbeats import system_status_summary
from app.services.notifications import canonical_purpose
from app.services.persistence import storage_status
from app.services.proxies import list_placeholder_proxies, list_proxies

EXPECTED_NOTIFICATION_PURPOSES = ("hq", "ops", "alerts")

STORAGE_WARNING_TYPES = {
    "storage_not_production_ready",
    "production_persistence_degraded",
    "sqlite_fallback",
    "sqlite_fallback_active",
    "sqlite_fallback_warning",
    "sqlite_storage_warning",
}
PRODUCTION_WARNING_TYPES = {
    "production_instability",
    "production_status_degraded",
    "production_health_degraded",
}
DUPLICATE_BOT_WARNING_TYPES = {
    "duplicate_bot_polling",
    "duplicate_polling",
    "duplicate_bot_instance",
    "bot_polling_conflict",
}
PLACEHOLDER_PROXY_WARNING_TYPES = {
    "placeholder_proxy",
    "placeholder_proxies",
    "proxy_placeholder",
    "proxy_placeholders",
}


@dataclass(frozen=True)
class AlembicRevisionStatus:
    current: str
    expected_head: str
    status: str


@dataclass(frozen=True)
class SystemTruth:
    environment: str
    is_production: bool
    database_backend: str
    database_backend_label: str
    database_durable: bool | None
    database_ready: bool
    redis_status: str
    redis_healthy: bool
    bot_instance_count: int
    duplicate_bot_instance_count: int
    bot_polling_safe: bool
    migration_current: str
    migration_expected: str
    migration_status: str
    migrations_current: bool
    proxy_placeholder_count: int
    real_proxy_count: int
    notification_targets_configured_count: int
    notification_targets_missing: tuple[str, ...]
    setup_readiness_score: int
    owner_count: int
    callback_error_count: int
    production_status: str
    production_ready: bool
    current_issue_codes: tuple[str, ...]
    current_issues: tuple[str, ...]

    @property
    def status_label(self) -> str:
        return "Everything is running." if self.production_ready else "Fortuna found something that needs attention."


def _unknown(value: Any) -> str:
    if value is None:
        return "Unknown"
    text = str(value).strip()
    return text or "Unknown"


def current_alembic_revision(session: Session) -> str:
    try:
        result = session.execute(text("select version_num from alembic_version")).scalar_one_or_none()
    except SQLAlchemyError:
        return "Unknown"
    return _unknown(result)


def expected_alembic_head() -> str:
    try:
        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        return _unknown(script.get_current_head())
    except Exception:
        return "Unknown"


def alembic_revision_status(session: Session) -> AlembicRevisionStatus:
    current = current_alembic_revision(session)
    expected = expected_alembic_head()
    if current == "Unknown" or expected == "Unknown":
        status = "Unknown"
    elif current == expected:
        status = "Current"
    else:
        status = "Mismatch"
    return AlembicRevisionStatus(current=current, expected_head=expected, status=status)


def system_truth(session: Session) -> SystemTruth:
    storage = storage_status()
    status = system_status_summary(session)
    revision = alembic_revision_status(session)
    bot = bot_instance_diagnostics(session)
    placeholder_count = len(list_placeholder_proxies(session, include_archived=False))
    real_proxy_count = len(list_proxies(session, include_disabled=False))
    active_notification_purposes = {
        canonical_purpose(purpose)
        for purpose in session.scalars(select(NotificationTarget.purpose).where(NotificationTarget.is_active.is_(True))).all()
    }
    missing_notification_targets = tuple(
        purpose for purpose in EXPECTED_NOTIFICATION_PURPOSES if purpose not in active_notification_purposes
    )
    try:
        readiness = int(build_activation_report(session)["readiness_score"])
    except Exception:
        readiness = 0
    owner_count = int(session.scalar(select(func.count(User.id)).where(User.is_owner.is_(True))) or 0)
    callback_error_count = int(session.scalar(select(func.count(CallbackErrorLog.id))) or 0)

    database_ready = storage.backend == "postgresql" and storage.durable is True
    redis_healthy = status["redis_status"] == "healthy"
    migrations_current = revision.status == "Current"
    polling_issue = _bot_polling_issue(storage.is_production, bot)
    bot_polling_safe = polling_issue is None

    issue_codes: list[str] = []
    issues: list[str] = []
    if storage.is_production and not database_ready:
        issue_codes.append("storage")
        issues.append("Storage is not production-ready.")
    if storage.is_production and not redis_healthy:
        issue_codes.append("redis")
        issues.append("Redis is not healthy.")
    if storage.is_production and not migrations_current:
        issue_codes.append("migrations")
        issues.append("Database migrations need attention.")
    if storage.is_production and not bot_polling_safe:
        issue_codes.append("bot_polling")
        issues.append(polling_issue or "Bot polling safety needs review.")
    if placeholder_count:
        issue_codes.append("proxy_placeholders")
        issues.append("Placeholder proxies are still visible to normal operations.")

    production_ready = not issue_codes
    return SystemTruth(
        environment=storage.environment,
        is_production=storage.is_production,
        database_backend=storage.backend,
        database_backend_label=storage.display_backend,
        database_durable=storage.durable,
        database_ready=database_ready,
        redis_status=status["redis_status"],
        redis_healthy=redis_healthy,
        bot_instance_count=int(bot["active_instance_count"]),
        duplicate_bot_instance_count=int(bot["duplicate_instance_count"]),
        bot_polling_safe=bot_polling_safe,
        migration_current=revision.current,
        migration_expected=revision.expected_head,
        migration_status=revision.status,
        migrations_current=migrations_current,
        proxy_placeholder_count=placeholder_count,
        real_proxy_count=real_proxy_count,
        notification_targets_configured_count=len(active_notification_purposes),
        notification_targets_missing=missing_notification_targets,
        setup_readiness_score=readiness,
        owner_count=owner_count,
        callback_error_count=callback_error_count,
        production_status="ready" if production_ready else "needs_attention",
        production_ready=production_ready,
        current_issue_codes=tuple(issue_codes),
        current_issues=tuple(issues),
    )


def _bot_polling_issue(is_production: bool, diagnostics: dict[str, object]) -> str | None:
    if not is_production:
        return None
    if bool(diagnostics.get("polling_conflict_active")):
        return "Polling conflict detected: another process is using the same Telegram bot token."
    if bool(diagnostics.get("webhook_delivery_active")):
        return None
    if not bool(diagnostics.get("preflight_allowed")):
        reason = str(diagnostics.get("preflight_reason") or "").strip()
        if "BOT_PRIMARY_INSTANCE" in reason:
            return "Current bot process is not marked as the primary polling instance."
        if "Redis is required" in reason:
            return "Redis polling lock is missing."
        return reason or "Bot polling preflight did not pass."
    active_count = int(diagnostics.get("active_instance_count") or 0)
    duplicate_count = int(diagnostics.get("duplicate_instance_count") or 0)
    if active_count <= 0:
        return "No active bot polling heartbeat was found."
    if duplicate_count > 0 or active_count > 1:
        return "More than one bot instance appears active."
    if not bool(diagnostics.get("redis_configured")):
        return "Redis polling lock is missing."
    redis_lock = str(diagnostics.get("redis_lock_status") or "").strip().lower()
    polling_guard = str(diagnostics.get("polling_guard") or "").strip().lower()
    if polling_guard != "redis_lock" or redis_lock != "held":
        return "Redis polling lock needs confirmation."
    return None


def _text_for(record: object, *fields: str) -> str:
    values: list[str] = []
    for field in fields:
        value = getattr(record, field, None)
        if value:
            values.append(str(value))
    metadata = getattr(record, "metadata_json", None)
    if metadata:
        values.append(str(metadata))
    return " ".join(values).casefold()


def _is_storage_warning(record: object) -> bool:
    text = _text_for(
        record,
        "recommendation_type",
        "title",
        "description",
        "signal_type",
        "pattern_type",
        "category",
        "source_type",
        "action_type",
        "result_summary",
        "explanation",
        "issue",
    )
    return any(
        token in text
        for token in (
            *STORAGE_WARNING_TYPES,
            "storage is not production-ready",
            "sqlite",
            "persistence degraded",
            "redis missing",
            "redis_unavailable",
            "redis url is not configured",
        )
    )


def _is_production_warning(record: object) -> bool:
    text = _text_for(
        record,
        "recommendation_type",
        "title",
        "description",
        "signal_type",
        "pattern_type",
        "category",
        "source_type",
        "action_type",
        "result_summary",
        "explanation",
        "issue",
    )
    return any(token in text for token in (*PRODUCTION_WARNING_TYPES, "production instability", "production degraded"))


def _is_duplicate_warning(record: object) -> bool:
    text = _text_for(
        record,
        "recommendation_type",
        "title",
        "description",
        "signal_type",
        "pattern_type",
        "category",
        "source_type",
        "action_type",
        "result_summary",
        "explanation",
        "issue",
    )
    return any(token in text for token in (*DUPLICATE_BOT_WARNING_TYPES, "duplicate polling", "duplicate bot"))


def _is_placeholder_proxy_warning(record: object) -> bool:
    text = _text_for(
        record,
        "recommendation_type",
        "title",
        "description",
        "signal_type",
        "pattern_type",
        "category",
        "source_type",
        "action_type",
        "result_summary",
        "explanation",
        "issue",
    )
    return any(token in text for token in (*PLACEHOLDER_PROXY_WARNING_TYPES, "placeholder proxy", "placeholder proxies"))


def _matches_resolved_truth(record: object, truth: SystemTruth) -> bool:
    if truth.database_ready and truth.redis_healthy and _is_storage_warning(record):
        return True
    if truth.production_ready and _is_production_warning(record):
        return True
    if truth.duplicate_bot_instance_count == 0 and truth.bot_polling_safe and _is_duplicate_warning(record):
        return True
    if truth.proxy_placeholder_count == 0 and _is_placeholder_proxy_warning(record):
        return True
    return False


def _safe_note(metadata: dict | None, *, reason: str, resolved_at: datetime) -> dict:
    data = dict(metadata or {})
    data["reconciled_by"] = "system_truth"
    data["resolved_reason"] = reason
    data["resolved_at"] = resolved_at.isoformat()
    return data


def reconcile_stale_system_warnings(session: Session, *, actor: User | None = None) -> dict[str, int]:
    truth = system_truth(session)
    now = datetime.now(UTC)
    resolved_counts = {
        "recommendations": 0,
        "priority_items": 0,
        "intelligence_signals": 0,
        "issue_patterns": 0,
        "follow_ups": 0,
        "friction_items_preserved": 0,
    }

    for recommendation in session.scalars(select(Recommendation).where(Recommendation.status.in_(("open", "acknowledged")))).all():
        if _matches_resolved_truth(recommendation, truth):
            recommendation.status = "resolved"
            recommendation.metadata_json = _safe_note(
                recommendation.metadata_json,
                reason="live_system_truth_no_longer_matches_warning",
                resolved_at=now,
            )
            recommendation.updated_at = now
            resolved_counts["recommendations"] += 1

    for item in session.scalars(select(PriorityItem).where(PriorityItem.status.in_(("open", "routed", "acknowledged")))).all():
        if _matches_resolved_truth(item, truth):
            item.status = "resolved"
            item.updated_at = now
            resolved_counts["priority_items"] += 1

    for signal in session.scalars(select(IntelligenceSignal).where(IntelligenceSignal.status.in_(("open", "acknowledged")))).all():
        if _matches_resolved_truth(signal, truth):
            signal.status = "resolved"
            signal.metadata_json = _safe_note(
                signal.metadata_json,
                reason="historical_issue_resolved_by_live_truth",
                resolved_at=now,
            )
            signal.updated_at = now
            resolved_counts["intelligence_signals"] += 1

    for pattern in session.scalars(select(IssuePattern).where(IssuePattern.status.in_(("active", "acknowledged")))).all():
        if _matches_resolved_truth(pattern, truth):
            pattern.status = "resolved"
            pattern.updated_at = now
            resolved_counts["issue_patterns"] += 1

    for follow_up in session.scalars(select(FollowUp).where(FollowUp.status.in_(("pending", "blocked", "failed")))).all():
        if _matches_resolved_truth(follow_up, truth):
            follow_up.status = "completed"
            follow_up.updated_at = now
            resolved_counts["follow_ups"] += 1

    # Friction items are immutable UX records in the current schema. We preserve them as history.
    for friction in session.scalars(select(FrictionItem)).all():
        if _matches_resolved_truth(friction, truth):
            resolved_counts["friction_items_preserved"] += 1

    changed = sum(value for key, value in resolved_counts.items() if key != "friction_items_preserved")
    if changed:
        audit_action(
            session,
            actor=actor,
            action="stale_warning.resolved",
            resource_type="system_truth",
            details={"resolved": resolved_counts, "current_issue_codes": list(truth.current_issue_codes)},
        )
        emit_event(
            session,
            actor=actor,
            event_name="stale_warning.resolved",
            resource_type="system_truth",
            payload={"resolved": resolved_counts, "current_issue_codes": list(truth.current_issue_codes)},
        )
    session.flush()
    return resolved_counts
