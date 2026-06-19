from __future__ import annotations

from typing import Any

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
from app.services.build_metadata import safe_build_metadata, safe_metadata_value
from app.services.button_health import button_health_summary
from app.services.chat_cleanup import chat_cleanup_metrics
from app.services.help_brain import help_questions_today, notification_pilot_status, proxy_pilot_status
from app.services.heartbeats import list_heartbeats, system_status_summary
from app.services.bot_instances import bot_instance_diagnostics
from app.services.persistence import storage_status
from app.services.notifications import notification_routing_mode_summary, purpose_aliases
from app.services.recovery import recovery_risk_assessment
from app.services.shared_status import StatusCondition, compute_shared_status
from app.services.system_truth import (
    AlembicRevisionStatus,
    alembic_revision_status,
    current_alembic_revision,
    expected_alembic_head,
    system_truth,
)

REQUIRED_NOTIFICATION_PURPOSES: tuple[tuple[str, str], ...] = (
    ("hq", "Fortuna HQ"),
    ("ops", "Fortuna Ops"),
    ("alerts", "Fortuna Alerts"),
)


def _unknown(value: Any) -> str:
    if value is None:
        return "Unknown"
    text = str(value).strip()
    return text or "Unknown"


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
    build_metadata = safe_build_metadata(environment=storage.environment, alembic_revision=revision.current.lower())
    status = system_status_summary(session)
    truth = system_truth(session)
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
    recovery = recovery_risk_assessment(session)
    buttons = button_health_summary(session)
    cleanup = chat_cleanup_metrics(session)
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
    if truth.database_ready and truth.redis_healthy:
        production_risk = "ready"
    elif storage.risk == "unsafe":
        production_risk = "unsafe"
    else:
        production_risk = "degraded"
    operations_issue_count = len(truth.current_issues)
    operations_status = "healthy" if truth.production_ready else ("critical" if production_risk == "unsafe" else "needs_attention")
    recovery_status = recovery.status
    recovery_issue_count = len(recovery.alerts) or (0 if recovery_status == "healthy" else 1)
    shared_status = compute_shared_status(
        [
            StatusCondition(
                "operations",
                operations_status,
                "Operations are checked through SystemTruth.",
                operations_issue_count,
                "Open Production Observability details." if operations_issue_count else None,
            ),
            StatusCondition(
                "recovery",
                recovery_status,
                recovery.next_best_move,
                recovery_issue_count,
                recovery.next_best_move if recovery_status != "healthy" else None,
            ),
            StatusCondition(
                "button_health",
                buttons.overall_status,
                "Button and navigation scan results.",
                buttons.open_issue_count,
                "Open Button Health." if buttons.open_issue_count else None,
            ),
            StatusCondition(
                "chat_cleanup",
                "needs_review" if cleanup.failed_count >= 3 else "healthy",
                "Chat cleanup protects Telegram menu history.",
                cleanup.failed_count if cleanup.failed_count >= 3 else 0,
                "Open Chat Cleanup settings." if cleanup.failed_count >= 3 else None,
            ),
        ]
    )
    observability_issues = list(truth.current_issues)
    if recovery_status != "healthy":
        observability_issues.append(f"Recovery: {recovery.next_best_move}")
    if buttons.open_issue_count:
        observability_issues.append(f"Navigation/Button Health: {buttons.open_issue_count} open issue(s).")
    if cleanup.failed_count >= 3:
        observability_issues.append(f"Chat Cleanup: {cleanup.failed_count} recent deletion failure(s).")

    return {
        "app_display_name": build_metadata["app_name"],
        "app_name": build_metadata["app_name"],
        "app_version": build_metadata["build_version"],
        "build_version": build_metadata["build_version"],
        "git_commit": build_metadata["git_commit"],
        "deployed_at": build_metadata["deployed_at"],
        "railway_deployment_id": safe_metadata_value(settings.railway_deployment_id, default="unknown"),
        "environment": status["environment"],
        "build_environment": build_metadata["environment"],
        "build_alembic_revision": build_metadata["alembic_revision"],
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
        "storage_risk_label": "Production Ready" if production_risk == "ready" else production_risk.title(),
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
        "system_truth_status": truth.production_status,
        "system_truth_ready": truth.production_ready,
        "system_truth_current_issues": list(truth.current_issues),
        "observability_current_issues": observability_issues,
        "shared_status": shared_status.status,
        "shared_status_label": shared_status.label,
        "shared_status_icon": shared_status.icon,
        "active_issue_count": shared_status.issue_count,
        "recommended_action": shared_status.recommended_action,
        "system_truth_current_issue_codes": list(truth.current_issue_codes),
        "system_truth_readiness_score": truth.setup_readiness_score,
        "system_truth_placeholder_proxy_count": truth.proxy_placeholder_count,
        "system_truth_real_proxy_count": truth.real_proxy_count,
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
        "recovery_last_backup": recovery.last_backup_status,
        "recovery_backup_health": recovery.protection_status,
        "recovery_external_storage_configured": recovery.external_storage_configured,
        "recovery_restore_test_status": recovery.restore_test_status,
        "recovery_confidence": recovery.recovery_confidence,
        "recovery_risk_score": recovery.risk_score,
        "recovery_risk_level": recovery.risk_level,
        "recovery_alerts": list(recovery.alerts),
        "recovery_evidence": list(recovery.evidence),
        "recovery_next_best_move": recovery.next_best_move,
        "recovery_status": recovery_status,
        "recovery_issue_count": recovery_issue_count,
        "button_health_status": buttons.overall_status,
        "button_health_open_issue_count": buttons.open_issue_count,
        "button_health_technical_issue_count": buttons.technical_issue_count,
        "button_health_navigation_issue_count": buttons.navigation_issue_count,
        "button_health_ux_issue_count": buttons.ux_issue_count,
        "button_health_last_scan_at": buttons.last_scan_at,
        "chat_cleanup_latest_at": cleanup.latest_cleanup_at,
        "chat_cleanup_attempted_count": cleanup.attempted_count,
        "chat_cleanup_deleted_count": cleanup.deleted_count,
        "chat_cleanup_preserved_count": cleanup.preserved_count,
        "chat_cleanup_failed_count": cleanup.failed_count,
        "chat_cleanup_reuse_count": cleanup.concurrency_reuse_count,
        "chat_cleanup_stale_count": cleanup.stale_callback_count,
    }
