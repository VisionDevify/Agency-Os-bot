from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import desc, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.automation import AutomationRun
from app.models.event_log import EventLog
from app.models.intelligence import IntelligenceRun
from app.models.reporting import NotificationTarget
from app.services.heartbeats import list_heartbeats, system_status_summary

REQUIRED_NOTIFICATION_PURPOSES: tuple[tuple[str, str], ...] = (
    ("owner", "HQ"),
    ("operations", "Operations"),
    ("incidents", "Incidents"),
    ("automation_logs", "Automation Logs"),
    ("testing", "Testing Sandbox"),
)


@dataclass(frozen=True)
class AlembicRevisionStatus:
    current: str
    expected_head: str
    status: str


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


def notification_target_readiness(session: Session) -> list[dict[str, object]]:
    active_targets = session.scalars(select(NotificationTarget).where(NotificationTarget.is_active.is_(True))).all()
    active_by_purpose = {purpose: 0 for purpose, _label in REQUIRED_NOTIFICATION_PURPOSES}
    for target in active_targets:
        if target.purpose in active_by_purpose:
            active_by_purpose[target.purpose] += 1
    return [
        {
            "purpose": purpose,
            "label": label,
            "configured": active_by_purpose[purpose] > 0,
            "active_count": active_by_purpose[purpose],
        }
        for purpose, label in REQUIRED_NOTIFICATION_PURPOSES
    ]


def _latest(session: Session, model, *order_columns):
    return session.scalar(select(model).order_by(*order_columns).limit(1))


def production_observability_summary(session: Session) -> dict[str, object]:
    revision = alembic_revision_status(session)
    status = system_status_summary(session)
    heartbeats = {heartbeat.service_name: heartbeat for heartbeat in list_heartbeats(session)}
    bot_heartbeat = heartbeats.get("bot")
    bot_metadata = bot_heartbeat.metadata_json if bot_heartbeat else {}
    latest_audit = _latest(session, AuditLog, desc(AuditLog.created_at), desc(AuditLog.id))
    latest_event = _latest(session, EventLog, desc(EventLog.created_at), desc(EventLog.id))
    latest_automation_run = _latest(session, AutomationRun, desc(AutomationRun.started_at), desc(AutomationRun.id))
    latest_intelligence_run = _latest(session, IntelligenceRun, desc(IntelligenceRun.started_at), desc(IntelligenceRun.id))

    return {
        "app_display_name": settings.app_display_name,
        "app_version": _unknown(settings.app_version),
        "git_commit": _unknown(settings.git_commit),
        "deployed_at": _unknown(settings.deployed_at),
        "railway_deployment_id": _unknown(settings.railway_deployment_id),
        "environment": status["environment"],
        "api_status": status["api_status"],
        "bot_status": status["bot_status"],
        "postgres_status": status["db_status"],
        "redis_status": status["redis_status"],
        "railway_status": status["railway_deployment_status"],
        "railway_note": "Railway logs must be viewed in Railway dashboard.",
        "alembic_current": revision.current,
        "alembic_expected": revision.expected_head,
        "alembic_status": revision.status,
        "bot_last_seen_at": status["bot_last_seen_at"],
        "bot_started_at": bot_metadata.get("bot_started_at", "Unknown"),
        "last_polling_loop_at": bot_metadata.get("last_polling_loop_at", "Unknown"),
        "last_telegram_update_at": bot_metadata.get("last_telegram_update_at", "Unknown"),
        "polling_guard": bot_metadata.get("polling_guard", "Unknown"),
        "redis_lock_status": bot_metadata.get("redis_lock_status", "Unknown"),
        "last_audit_action": latest_audit.action if latest_audit else "None",
        "last_audit_at": latest_audit.created_at if latest_audit else None,
        "last_event_type": latest_event.event_type if latest_event else "None",
        "last_event_at": latest_event.created_at if latest_event else None,
        "last_automation_run": latest_automation_run.status if latest_automation_run else "None",
        "last_automation_run_at": latest_automation_run.started_at if latest_automation_run else None,
        "last_intelligence_run": latest_intelligence_run.status if latest_intelligence_run else "None",
        "last_intelligence_run_at": latest_intelligence_run.started_at if latest_intelligence_run else None,
        "last_delivery_status": status["last_delivery_status"],
        "failed_notification_count": status["failed_notification_count"],
        "notification_readiness": notification_target_readiness(session),
    }
