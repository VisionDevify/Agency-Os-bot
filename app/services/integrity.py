from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.automation import AutomationRule
from app.models.event_log import EventLog
from app.models.learning import LearningEvent
from app.models.permissions import Role
from app.models.proxy import Proxy
from app.models.user import User
from app.services.auth import audit_action
from app.services.bot_instances import active_bot_instance_heartbeats
from app.services.events import emit_event
from app.services.observability import alembic_revision_status
from app.services.persistence import storage_status


@dataclass(frozen=True)
class IntegrityCheck:
    name: str
    status: str
    detail: str


def _count(session: Session, model) -> int:
    return int(session.scalar(select(func.count(model.id))) or 0)


def _redis_ping() -> IntegrityCheck:
    if not settings.redis_url:
        return IntegrityCheck("Redis ping", "warning", "Redis URL is not configured; polling guard is not durable.")
    try:
        from redis import Redis

        client = Redis.from_url(settings.redis_url)
        client.ping()
    except Exception:
        return IntegrityCheck("Redis ping", "fail", "Redis ping failed.")
    return IntegrityCheck("Redis ping", "pass", "Redis responded to ping.")


def _table_access_check(session: Session, label: str, model) -> IntegrityCheck:
    try:
        total = _count(session, model)
    except SQLAlchemyError:
        return IntegrityCheck(label, "fail", "Table is not accessible.")
    return IntegrityCheck(label, "pass", f"Table accessible ({total} rows).")


def run_integrity_check(session: Session, *, actor: User | None = None) -> dict[str, Any]:
    storage = storage_status()
    checks: list[IntegrityCheck] = []

    try:
        session.execute(text("select 1"))
        db_status = "pass"
        db_detail = f"Connected using {storage.display_backend}."
    except SQLAlchemyError:
        db_status = "fail"
        db_detail = "Database connection failed."
    if storage.backend == "sqlite_fallback" and storage.is_production:
        db_status = "warning" if db_status == "pass" else db_status
        db_detail += " Emergency SQLite is not production-durable."
    checks.append(IntegrityCheck("DB backend", db_status, db_detail))

    revision = alembic_revision_status(session)
    revision_status = "pass" if revision.status == "Current" else "warning"
    checks.append(
        IntegrityCheck(
            "Alembic revision",
            revision_status,
            f"{revision.current} / expected {revision.expected_head} ({revision.status}).",
        )
    )

    owner_total = int(session.scalar(select(func.count(User.id)).where(User.is_owner.is_(True))) or 0)
    checks.append(
        IntegrityCheck(
            "Owner account",
            "pass" if owner_total > 0 else "fail",
            f"{owner_total} owner user(s) found.",
        )
    )

    role_total = _count(session, Role)
    checks.append(IntegrityCheck("Roles", "pass" if role_total > 0 else "fail", f"{role_total} role(s) found."))

    try:
        audit = audit_action(
            session,
            actor=actor,
            action="integrity.audit_write_test",
            resource_type="integrity_check",
            details={"backend": storage.backend},
        )
        checks.append(IntegrityCheck("Audit write", "pass", f"Audit row {audit.id} written."))
    except Exception:
        checks.append(IntegrityCheck("Audit write", "fail", "Audit write failed."))

    try:
        event = emit_event(
            session,
            actor=actor,
            event_name="integrity.event_write_test",
            resource_type="integrity_check",
            payload={"backend": storage.backend},
        )
        checks.append(IntegrityCheck("Event write", "pass", f"Event/audit row {event.id} written."))
    except Exception:
        checks.append(IntegrityCheck("Event write", "fail", "Event write failed."))

    checks.extend(
        [
            _table_access_check(session, "Learning tables", LearningEvent),
            _table_access_check(session, "Automation tables", AutomationRule),
            _table_access_check(session, "Proxy tables", Proxy),
            _redis_ping(),
        ]
    )

    if settings.redis_url:
        guard_status = "Redis polling guard can be active."
        guard_check = "pass"
    else:
        guard_status = "Redis missing; duplicate polling guard is not durable."
        guard_check = "warning"
    checks.append(IntegrityCheck("Polling guard", guard_check, guard_status))

    active_instances = active_bot_instance_heartbeats(session)
    instance_status = "pass" if len(active_instances) <= 1 else "warning"
    checks.append(
        IntegrityCheck(
            "Bot instances",
            instance_status,
            f"{len(active_instances)} active bot instance heartbeat(s) detected.",
        )
    )

    fail_count = sum(1 for check in checks if check.status == "fail")
    warning_count = sum(1 for check in checks if check.status == "warning")
    overall = "fail" if fail_count else "warning" if warning_count else "pass"

    return {
        "overall": overall,
        "checks": checks,
        "fail_count": fail_count,
        "warning_count": warning_count,
        "storage_backend": storage.backend,
        "storage_display_backend": storage.display_backend,
        "storage_durable": storage.durable,
        "storage_warning": storage.warning,
        "redis_configured": bool(settings.redis_url),
        "active_bot_instances": len(active_instances),
    }
