from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.proxy import Proxy
from app.models.task import Task
from app.models.user import User
from app.services.account_health import (
    ACCOUNT_HEALTH_CRITICAL,
    ACCOUNT_HEALTH_DISABLED,
    ACCOUNT_HEALTH_HEALTHY,
    ACCOUNT_HEALTH_WARNING,
    calculate_account_health,
)
from app.services.auth import audit_action, user_has_permission
from app.services.events import emit_event
from app.services.incidents import count_incidents
from app.services.tasks import completed_today_by_user, completed_today_count, count_tasks, overdue_tasks, record_overdue_tasks


def _now() -> datetime:
    return datetime.now(UTC)


def _require_reports(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "view_dashboard"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="report",
        status="denied",
        details={"permission": "manage_reports_or_view_dashboard"},
    )
    raise PermissionError("Missing permission: manage_reports or view_dashboard")


def _account_health_counts(session: Session) -> dict[str, int]:
    counts = {
        ACCOUNT_HEALTH_HEALTHY: 0,
        ACCOUNT_HEALTH_WARNING: 0,
        ACCOUNT_HEALTH_CRITICAL: 0,
        ACCOUNT_HEALTH_DISABLED: 0,
    }
    accounts = session.scalars(select(Account).where(Account.status != "archived")).all()
    for account in accounts:
        counts[calculate_account_health(account).status] += 1
    return counts


def _proxy_status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(Proxy.status, func.count(Proxy.id)).group_by(Proxy.status)).all()
    return {status: count for status, count in rows}


def agency_health_score(session: Session) -> int:
    account_counts = _account_health_counts(session)
    proxy_counts = _proxy_status_counts(session)
    open_incident_count = count_incidents(session, statuses=("open", "investigating"))
    critical_incident_count = count_incidents(session, statuses=("open", "investigating"), severity="critical")
    overdue_count = len(overdue_tasks(session))
    score = 100
    score -= account_counts[ACCOUNT_HEALTH_CRITICAL] * 8
    score -= account_counts[ACCOUNT_HEALTH_WARNING] * 3
    score -= proxy_counts.get("critical", 0) * 8
    score -= proxy_counts.get("warning", 0) * 3
    score -= critical_incident_count * 10
    score -= max(open_incident_count - critical_incident_count, 0) * 4
    score -= overdue_count * 3
    return max(0, min(100, score))


def executive_dashboard(session: Session) -> dict:
    account_counts = _account_health_counts(session)
    proxy_counts = _proxy_status_counts(session)
    return {
        "total_models": session.scalar(select(func.count(ModelBrand.id)).where(ModelBrand.status != "archived")) or 0,
        "total_accounts": session.scalar(select(func.count(Account.id)).where(Account.status != "archived")) or 0,
        "healthy_accounts": account_counts[ACCOUNT_HEALTH_HEALTHY],
        "warning_accounts": account_counts[ACCOUNT_HEALTH_WARNING],
        "critical_accounts": account_counts[ACCOUNT_HEALTH_CRITICAL],
        "proxy_health": proxy_counts,
        "open_tasks": count_tasks(session, statuses=("open", "in_progress", "blocked")),
        "overdue_tasks": count_tasks(session, overdue=True),
        "open_incidents": count_incidents(session, statuses=("open", "investigating")),
        "critical_incidents": count_incidents(session, statuses=("open", "investigating"), severity="critical"),
        "completed_tasks_today": completed_today_count(session),
    }


def operations_dashboard(session: Session) -> dict:
    account_counts = _account_health_counts(session)
    proxy_counts = _proxy_status_counts(session)
    return {
        "pending_tasks": count_tasks(session, statuses=("open", "in_progress")),
        "blocked_tasks": count_tasks(session, statuses=("blocked",)),
        "incidents_by_severity": {
            "info": count_incidents(session, statuses=("open", "investigating"), severity="info"),
            "warning": count_incidents(session, statuses=("open", "investigating"), severity="warning"),
            "critical": count_incidents(session, statuses=("open", "investigating"), severity="critical"),
        },
        "account_warnings": account_counts[ACCOUNT_HEALTH_WARNING] + account_counts[ACCOUNT_HEALTH_CRITICAL],
        "proxy_warnings": proxy_counts.get("warning", 0) + proxy_counts.get("critical", 0),
    }


def chatter_dashboard(session: Session, *, user: User | None = None) -> dict:
    assigned_models = 0
    if user is not None:
        assigned_models = (
            session.scalar(
                select(func.count(ModelBrandMember.model_brand_id)).where(
                    ModelBrandMember.user_id == user.id,
                    ModelBrandMember.relationship_type.in_(("chatter", "senior_chatter", "chatter_manager")),
                )
            )
            or 0
        )
    return {
        "assigned_models": assigned_models,
        "open_tasks": count_tasks(
            session,
            statuses=("open", "in_progress", "blocked"),
            assigned_to_user_id=user.id,
        )
        if user is not None
        else count_tasks(session, statuses=("open", "in_progress", "blocked")),
        "escalations": count_incidents(session, statuses=("open", "investigating")),
        "notes": "Notes placeholder ready for future chatter operations.",
    }


def va_dashboard(session: Session, *, user: User | None = None) -> dict:
    assigned_models = 0
    if user is not None:
        assigned_models = (
            session.scalar(
                select(func.count(ModelBrandMember.model_brand_id)).where(
                    ModelBrandMember.user_id == user.id,
                    ModelBrandMember.relationship_type == "va",
                )
            )
            or 0
        )
    return {
        "assigned_models": assigned_models,
        "assigned_accounts": session.scalar(select(func.count(Account.id)).where(Account.status != "archived")) or 0,
        "uploads": "Uploads placeholder ready for content operations.",
        "overdue_items": count_tasks(session, assigned_to_user_id=user.id, overdue=True) if user else count_tasks(session, overdue=True),
    }


def recent_audit_highlights(session: Session, *, limit: int = 5) -> list[str]:
    logs = session.scalars(
        select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(limit)
    ).all()
    return [f"{log.action} on {log.resource_type}:{log.resource_id or 'n/a'} ({log.status})" for log in logs]


def recommended_actions(summary: dict) -> list[str]:
    actions: list[str] = []
    if summary["critical_incidents"] > 0:
        actions.append("Review and resolve critical incidents.")
    if summary["overdue_tasks"] > 0:
        actions.append("Reassign or complete overdue tasks.")
    if summary["accounts_critical"] > 0:
        actions.append("Check critical accounts needing login, 2FA, or recovery.")
    if summary["proxies_critical"] > 0:
        actions.append("Run proxy repair simulation for critical proxies.")
    if not actions:
        actions.append("No urgent action. Keep monitoring dashboards.")
    return actions


def generate_daily_briefing(session: Session, *, actor: User | None) -> dict:
    _require_reports(session, actor)
    overdue_count = record_overdue_tasks(session, actor=actor)
    account_counts = _account_health_counts(session)
    proxy_counts = _proxy_status_counts(session)
    top_users = [
        {
            "user_id": user.id,
            "display_name": user.display_name or user.username or f"User {user.id}",
            "completed_tasks": count,
        }
        for user, count in completed_today_by_user(session)
    ]
    summary = {
        "agency_health_score": agency_health_score(session),
        "models_active": session.scalar(select(func.count(ModelBrand.id)).where(ModelBrand.status == "active")) or 0,
        "accounts_healthy": account_counts[ACCOUNT_HEALTH_HEALTHY],
        "accounts_warning": account_counts[ACCOUNT_HEALTH_WARNING],
        "accounts_critical": account_counts[ACCOUNT_HEALTH_CRITICAL],
        "proxies_healthy": proxy_counts.get("healthy", 0),
        "proxies_warning": proxy_counts.get("warning", 0),
        "proxies_critical": proxy_counts.get("critical", 0),
        "open_incidents": count_incidents(session, statuses=("open", "investigating")),
        "critical_incidents": count_incidents(session, statuses=("open", "investigating"), severity="critical"),
        "tasks_completed_today": completed_today_count(session),
        "overdue_tasks": overdue_count,
        "top_active_users": top_users,
        "recent_audit_highlights": recent_audit_highlights(session),
    }
    summary["recommended_actions"] = recommended_actions(summary)
    emit_event(
        session,
        actor=actor,
        event_name="briefing.generated",
        resource_type="report",
        resource_id="daily_company_briefing",
        payload={
            "agency_health_score": summary["agency_health_score"],
            "open_incidents": summary["open_incidents"],
            "overdue_tasks": summary["overdue_tasks"],
        },
    )
    return summary


def generate_accountability_report(session: Session, *, actor: User | None) -> dict:
    _require_reports(session, actor)
    current_time = _now()
    start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    users = session.scalars(select(User).options(selectinload(User.roles)).order_by(User.id)).all()
    rows: list[dict] = []
    for user in users:
        rows.append(
            {
                "user_id": user.id,
                "display_name": user.display_name or user.username or f"User {user.id}",
                "assigned_open_tasks": count_tasks(
                    session,
                    statuses=("open", "in_progress", "blocked"),
                    assigned_to_user_id=user.id,
                ),
                "completed_today": session.scalar(
                    select(func.count(Task.id)).where(
                        Task.assigned_to_user_id == user.id,
                        Task.status == "complete",
                        Task.completed_at.is_not(None),
                        Task.completed_at >= start,
                        Task.completed_at < end,
                    )
                )
                or 0,
                "overdue_tasks": count_tasks(session, assigned_to_user_id=user.id, overdue=True),
                "open_incidents_assigned": count_incidents(
                    session,
                    statuses=("open", "investigating"),
                    assigned_to_user_id=user.id,
                ),
                "last_seen": user.last_seen.isoformat() if user.last_seen else "Not seen yet",
                "roles": [role.name for role in user.roles],
            }
        )
    report = {"generated_at": current_time.isoformat(), "users": rows}
    emit_event(
        session,
        actor=actor,
        event_name="accountability.generated",
        resource_type="report",
        resource_id="team_accountability",
        payload={"users": len(rows)},
    )
    return report
