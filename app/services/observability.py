from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import desc, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.automation import AutomationRun
from app.models.event_log import EventLog
from app.models.help import UISelfTestRun
from app.models.intelligence import IntelligenceRun
from app.models.proxy import ProxyHealthCheckResult
from app.models.permissions import Role
from app.models.reporting import NotificationTarget
from app.models.user import User
from app.services.help_brain import help_questions_today, notification_pilot_status, proxy_pilot_status
from app.services.heartbeats import list_heartbeats, system_status_summary
from app.services.bot_instances import bot_instance_diagnostics
from app.services.persistence import storage_status
from app.services.notifications import notification_routing_mode_summary, purpose_aliases

REQUIRED_NOTIFICATION_PURPOSES: tuple[tuple[str, str], ...] = (
    ("hq", "Fortuna HQ"),
    ("ops", "Fortuna Ops"),
    ("alerts", "Fortuna Alerts"),
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
        for purpose in active_by_purpose:
            if target.purpose in purpose_aliases(purpose):
                active_by_purpose[purpose] += 1
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
    storage = storage_status()
    status = system_status_summary(session)
    heartbeats = {heartbeat.service_name: heartbeat for heartbeat in list_heartbeats(session)}
    bot_heartbeat = heartbeats.get("bot")
    redis_heartbeat = heartbeats.get("redis")
    bot_metadata = bot_heartbeat.metadata_json if bot_heartbeat else {}
    latest_audit = _latest(session, AuditLog, desc(AuditLog.created_at), desc(AuditLog.id))
    latest_event = _latest(session, EventLog, desc(EventLog.created_at), desc(EventLog.id))
    latest_automation_run = _latest(session, AutomationRun, desc(AutomationRun.started_at), desc(AutomationRun.id))
    latest_intelligence_run = _latest(session, IntelligenceRun, desc(IntelligenceRun.started_at), desc(IntelligenceRun.id))
    latest_real_proxy_check = session.scalar(
        select(ProxyHealthCheckResult)
        .where(ProxyHealthCheckResult.check_type.in_(("connectivity", "location", "full")))
        .order_by(desc(ProxyHealthCheckResult.created_at), desc(ProxyHealthCheckResult.id))
        .limit(1)
    )
    recent_proxy_failures = (
        session.scalar(
            select(ProxyHealthCheckResult.id)
            .where(ProxyHealthCheckResult.status.in_(("failed", "warning")))
            .order_by(desc(ProxyHealthCheckResult.created_at), desc(ProxyHealthCheckResult.id))
            .limit(1)
        )
        is not None
    )
    configured_notification_targets = (
        session.scalar(select(func.count(NotificationTarget.id)).where(NotificationTarget.is_active.is_(True))) or 0
    )
    help_total, help_confused = help_questions_today(session)
    notification_pilot = notification_pilot_status(session)
    routing_mode = notification_routing_mode_summary(session)
    proxy_pilot = proxy_pilot_status(session)
    bot_diagnostics = bot_instance_diagnostics(session)
    latest_self_test = _latest(session, UISelfTestRun, desc(UISelfTestRun.created_at), desc(UISelfTestRun.id))
    owner_count = session.scalar(select(func.count(User.id)).where(User.is_owner.is_(True))) or 0
    role_count = session.scalar(select(func.count(Role.id))) or 0
    audit_count = session.scalar(select(func.count(AuditLog.id))) or 0
    event_count = session.scalar(select(func.count(EventLog.id))) or 0
    latest_db_write = None
    if latest_audit and latest_event:
        latest_db_write = max(latest_audit.created_at, latest_event.created_at)
    elif latest_audit:
        latest_db_write = latest_audit.created_at
    elif latest_event:
        latest_db_write = latest_event.created_at
    redis_connected = status["redis_status"] == "healthy"
    polling_guard_active = bot_metadata.get("polling_guard") == "redis_lock" and bot_metadata.get("redis_lock_status") == "held"
    if storage.risk == "ready" and redis_connected:
        production_risk = "Production Ready"
    elif storage.risk == "unsafe":
        production_risk = "Unsafe"
    else:
        production_risk = "Degraded"

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
        "storage_backend": storage.display_backend,
        "storage_backend_key": storage.backend,
        "storage_driver": storage.scheme,
        "storage_durable": storage.durable,
        "storage_risk": production_risk,
        "storage_warning": storage.warning or "None",
        "sqlite_fallback_allowed": storage.sqlite_fallback_allowed,
        "sqlite_file_location": storage.file_location,
        "last_db_write_at": latest_db_write,
        "owner_count": owner_count,
        "role_count": role_count,
        "audit_count": audit_count,
        "event_count": event_count,
        "redis_connected": redis_connected,
        "polling_guard_active": polling_guard_active,
        "last_redis_ping_at": redis_heartbeat.last_seen_at if redis_heartbeat else None,
        "alembic_current": revision.current,
        "alembic_expected": revision.expected_head,
        "alembic_status": revision.status,
        "bot_last_seen_at": status["bot_last_seen_at"],
        "bot_started_at": bot_metadata.get("bot_started_at", "Unknown"),
        "last_polling_loop_at": bot_metadata.get("last_polling_loop_at", "Unknown"),
        "last_telegram_update_at": bot_metadata.get("last_telegram_update_at", "Unknown"),
        "polling_guard": bot_metadata.get("polling_guard", "Unknown"),
        "redis_lock_status": bot_metadata.get("redis_lock_status", "Unknown"),
        "bot_instance_id": bot_diagnostics["instance_id_masked"],
        "bot_primary_polling_enabled": bot_diagnostics["primary_polling_enabled"],
        "bot_polling_allowed": bot_diagnostics["preflight_allowed"],
        "bot_polling_warning": bot_diagnostics["preflight_reason"] if not bot_diagnostics["preflight_allowed"] else "None",
        "active_bot_instance_count": bot_diagnostics["active_instance_count"],
        "duplicate_bot_instance_count": bot_diagnostics["duplicate_instance_count"],
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
        "notification_routing_mode": routing_mode.mode,
        "notification_routing_label": routing_mode.label,
        "notification_hq_configured": routing_mode.hq_configured,
        "notification_ops_configured": routing_mode.ops_configured,
        "notification_alerts_configured": routing_mode.alerts_configured,
        "notification_ops_alerts_combined": routing_mode.combined_ops_alerts,
        "notification_targets_configured_count": configured_notification_targets,
        "help_questions_today": help_total,
        "help_confused_count": help_confused,
        "proxy_real_health_checks_enabled": settings.proxy_real_health_checks_enabled,
        "proxy_real_location_checks_enabled": settings.proxy_real_location_checks_enabled,
        "last_real_proxy_check_status": latest_real_proxy_check.status if latest_real_proxy_check else "None",
        "last_real_proxy_check_at": latest_real_proxy_check.created_at if latest_real_proxy_check else None,
        "recent_proxy_health_failures": recent_proxy_failures,
        "notification_pilot_status": f"{notification_pilot['configured']}/{notification_pilot['required']} configured",
        "proxy_pilot_status": f"{proxy_pilot['enabled']}/{proxy_pilot['total']} proxies enabled",
        "last_ui_self_test_status": latest_self_test.status if latest_self_test else "None",
        "last_ui_self_test_at": latest_self_test.created_at if latest_self_test else None,
    }
