from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.proxy import Proxy
from app.models.reporting import AccountabilitySnapshot, DailyBriefing
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
from app.services.model_health import HEALTH_CRITICAL, HEALTH_HEALTHY, HEALTH_WARNING, calculate_model_health
from app.services.tasks import completed_today_by_user, completed_today_count, count_tasks, overdue_tasks, record_overdue_tasks


def _now() -> datetime:
    return datetime.now(UTC)


def _today(current_time: datetime | None = None) -> date:
    return (current_time or _now()).date()


def _today_bounds(current_time: datetime | None = None) -> tuple[datetime, datetime]:
    now = current_time or _now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


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


def _require_any_permission(session: Session, actor: User | None, permissions: tuple[str, ...], resource_type: str) -> None:
    if actor is None or any(user_has_permission(actor, permission) for permission in permissions):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type=resource_type,
        status="denied",
        details={"permission": "_or_".join(permissions)},
    )
    raise PermissionError(f"Missing one of: {', '.join(permissions)}")


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
    counts = {"healthy": 0, "warning": 0, "critical": 0, "disabled": 0}
    rows = session.execute(select(Proxy.status, func.count(Proxy.id)).group_by(Proxy.status)).all()
    for status, count in rows:
        counts[status] = count
    return counts


def _model_health_counts(session: Session) -> dict[str, int]:
    counts = {HEALTH_HEALTHY: 0, HEALTH_WARNING: 0, HEALTH_CRITICAL: 0}
    models = session.scalars(select(ModelBrand).where(ModelBrand.status != "archived")).all()
    accounts = session.scalars(select(Account).where(Account.status != "archived")).all()
    for model in models:
        model_accounts = [account for account in accounts if account.model_brand_id == model.id]
        open_incidents = (
            session.scalar(
                select(func.count(Incident.id)).where(
                    Incident.model_brand_id == model.id,
                    Incident.status.in_(("open", "investigating")),
                )
            )
            or 0
        )
        health = calculate_model_health(
            model,
            open_incidents=open_incidents,
            disabled_accounts=sum(1 for account in model_accounts if account.status == "disabled"),
            warning_accounts=sum(
                1
                for account in model_accounts
                if account.status in {"warning", "critical"}
                or account.auth_status in {"needs_login", "needs_2fa", "expired", "locked"}
            ),
        )
        counts[health.status] += 1
    return counts


def _accounts_missing_proxy_count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count(Account.id)).where(
                Account.status != "archived",
                Account.assigned_proxy_id.is_(None),
            )
        )
        or 0
    )


def _recent_high_risk_events(session: Session, *, limit: int = 5) -> list[str]:
    risky_actions = (
        "access.denied",
        "owner.protection_triggered",
        "proxy.repair.failed",
        "proxy.rotation.failed",
        "proxy.location.mismatch",
        "incident.escalated",
        "account.auth_session.failed",
        "account.auth_session.expired",
    )
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.action.in_(risky_actions))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(limit)
    ).all()
    return [f"{log.action} on {log.resource_type}:{log.resource_id or 'n/a'} ({log.status})" for log in logs]


def _recent_failed_repairs(session: Session, *, limit: int = 5) -> list[str]:
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.action.in_(("proxy.repair.failed", "proxy.rotation.failed")))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(limit)
    ).all()
    return [f"{log.action} proxy:{log.resource_id or 'n/a'}" for log in logs]


def _recent_escalations(session: Session, *, limit: int = 5) -> list[str]:
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.action == "incident.escalated")
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(limit)
    ).all()
    return [f"Incident {log.resource_id or 'n/a'} escalated" for log in logs]


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
    model_counts = _model_health_counts(session)
    total_models = session.scalar(select(func.count(ModelBrand.id)).where(ModelBrand.status != "archived")) or 0
    total_accounts = session.scalar(select(func.count(Account.id)).where(Account.status != "archived")) or 0
    total_proxies = session.scalar(select(func.count(Proxy.id))) or 0
    return {
        "agency_health_score": agency_health_score(session),
        "total_models": total_models,
        "healthy_models": model_counts[HEALTH_HEALTHY],
        "warning_models": model_counts[HEALTH_WARNING],
        "critical_models": model_counts[HEALTH_CRITICAL],
        "total_accounts": total_accounts,
        "healthy_accounts": account_counts[ACCOUNT_HEALTH_HEALTHY],
        "warning_accounts": account_counts[ACCOUNT_HEALTH_WARNING],
        "critical_accounts": account_counts[ACCOUNT_HEALTH_CRITICAL],
        "disabled_accounts": account_counts[ACCOUNT_HEALTH_DISABLED],
        "accounts_needing_login": session.scalar(
            select(func.count(Account.id)).where(Account.status != "archived", Account.auth_status == "needs_login")
        )
        or 0,
        "accounts_needing_2fa": session.scalar(
            select(func.count(Account.id)).where(Account.status != "archived", Account.auth_status == "needs_2fa")
        )
        or 0,
        "total_proxies": total_proxies,
        "healthy_proxies": proxy_counts.get("healthy", 0),
        "warning_proxies": proxy_counts.get("warning", 0),
        "critical_proxies": proxy_counts.get("critical", 0),
        "disabled_proxies": proxy_counts.get("disabled", 0),
        "accounts_missing_proxy": _accounts_missing_proxy_count(session),
        "proxy_health": proxy_counts,
        "open_tasks": count_tasks(session, statuses=("open", "in_progress", "blocked")),
        "overdue_tasks": count_tasks(session, overdue=True),
        "open_incidents": count_incidents(session, statuses=("open", "investigating")),
        "critical_incidents": count_incidents(session, statuses=("open", "investigating"), severity="critical"),
        "completed_tasks_today": completed_today_count(session),
        "recent_high_risk_events": _recent_high_risk_events(session),
    }


def operations_dashboard(session: Session) -> dict:
    account_counts = _account_health_counts(session)
    proxy_counts = _proxy_status_counts(session)
    model_counts = _model_health_counts(session)
    return {
        "pending_tasks": count_tasks(session, statuses=("open", "in_progress")),
        "blocked_tasks": count_tasks(session, statuses=("blocked",)),
        "tasks_by_status": {
            "open": count_tasks(session, statuses=("open",)),
            "in_progress": count_tasks(session, statuses=("in_progress",)),
            "blocked": count_tasks(session, statuses=("blocked",)),
            "complete": count_tasks(session, statuses=("complete",)),
            "archived": count_tasks(session, statuses=("archived",)),
        },
        "incidents_by_severity": {
            "info": count_incidents(session, statuses=("open", "investigating"), severity="info"),
            "warning": count_incidents(session, statuses=("open", "investigating"), severity="warning"),
            "critical": count_incidents(session, statuses=("open", "investigating"), severity="critical"),
        },
        "accounts_needing_attention": account_counts[ACCOUNT_HEALTH_WARNING] + account_counts[ACCOUNT_HEALTH_CRITICAL],
        "proxies_needing_attention": proxy_counts.get("warning", 0) + proxy_counts.get("critical", 0),
        "models_needing_attention": model_counts[HEALTH_WARNING] + model_counts[HEALTH_CRITICAL],
        "account_warnings": account_counts[ACCOUNT_HEALTH_WARNING] + account_counts[ACCOUNT_HEALTH_CRITICAL],
        "proxy_warnings": proxy_counts.get("warning", 0) + proxy_counts.get("critical", 0),
        "recent_escalations": _recent_escalations(session),
        "recent_failed_repairs": _recent_failed_repairs(session),
    }


def chatter_dashboard(session: Session, *, user: User | None = None) -> dict:
    _require_any_permission(
        session,
        user,
        ("view_chatter_dashboard", "manage_chatter_team"),
        "chatter_dashboard",
    )
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
        "escalations": count_incidents(session, statuses=("open", "investigating"), assigned_to_user_id=user.id)
        if user is not None
        else count_incidents(session, statuses=("open", "investigating")),
        "notes": "Notes placeholder ready for future chatter operations.",
        "future_metrics": ("conversations", "conversions", "revenue assisted", "PPV sales", "renewals"),
    }


def va_dashboard(session: Session, *, user: User | None = None) -> dict:
    _require_any_permission(session, user, ("upload_content", "manage_tasks", "view_dashboard"), "va_dashboard")
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
        "open_tasks": count_tasks(session, assigned_to_user_id=user.id, statuses=("open", "in_progress", "blocked"))
        if user
        else count_tasks(session, statuses=("open", "in_progress", "blocked")),
        "uploads": "Content/upload placeholder ready for VA operations.",
        "approvals": "Approval placeholder ready for future content workflows.",
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
    if summary["accounts_needing_login"] > 0:
        actions.append("Review accounts needing login.")
    if summary["accounts_needing_2fa"] > 0:
        actions.append("Handle accounts waiting for 2FA.")
    if not actions:
        actions.append("No urgent action. Keep monitoring dashboards.")
    return actions


def _build_briefing_summary(session: Session, *, actor: User | None) -> dict:
    overdue_count = record_overdue_tasks(session, actor=actor)
    account_counts = _account_health_counts(session)
    proxy_counts = _proxy_status_counts(session)
    model_counts = _model_health_counts(session)
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
        "overall_status": "healthy",
        "models_active": session.scalar(select(func.count(ModelBrand.id)).where(ModelBrand.status == "active")) or 0,
        "models_healthy": model_counts[HEALTH_HEALTHY],
        "models_warning": model_counts[HEALTH_WARNING],
        "models_critical": model_counts[HEALTH_CRITICAL],
        "accounts_healthy": account_counts[ACCOUNT_HEALTH_HEALTHY],
        "accounts_warning": account_counts[ACCOUNT_HEALTH_WARNING],
        "accounts_critical": account_counts[ACCOUNT_HEALTH_CRITICAL],
        "accounts_needing_login": session.scalar(
            select(func.count(Account.id)).where(Account.status != "archived", Account.auth_status == "needs_login")
        )
        or 0,
        "accounts_needing_2fa": session.scalar(
            select(func.count(Account.id)).where(Account.status != "archived", Account.auth_status == "needs_2fa")
        )
        or 0,
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
    if summary["agency_health_score"] < 60:
        summary["overall_status"] = "critical"
    elif summary["agency_health_score"] < 80:
        summary["overall_status"] = "warning"
    summary["recommended_actions"] = recommended_actions(summary)
    return summary


def _briefing_summary_text(summary: dict) -> str:
    return (
        f"Agency status is {summary['overall_status']} with health score "
        f"{summary['agency_health_score']}/100. "
        f"Open incidents: {summary['open_incidents']}; overdue tasks: {summary['overdue_tasks']}."
    )


def _daily_briefing_to_dict(briefing: DailyBriefing) -> dict:
    summary = dict(briefing.metrics_json or {})
    summary["briefing_id"] = briefing.id
    summary["briefing_date"] = briefing.briefing_date.isoformat()
    summary["created_at"] = briefing.created_at.isoformat() if briefing.created_at else None
    summary["summary_text"] = briefing.summary_text
    summary["recommended_actions"] = list(briefing.recommendations_json or [])
    return summary


def generate_daily_briefing(session: Session, *, actor: User | None) -> dict:
    _require_reports(session, actor)
    summary = _build_briefing_summary(session, actor=actor)
    summary_text = _briefing_summary_text(summary)
    briefing = DailyBriefing(
        briefing_date=_today(),
        generated_by_user_id=actor.id if actor else None,
        agency_health_score=summary["agency_health_score"],
        summary_text=summary_text,
        metrics_json=summary,
        recommendations_json=summary["recommended_actions"],
    )
    session.add(briefing)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="briefing.generated",
        resource_type="daily_briefing",
        resource_id=str(briefing.id),
        payload={
            "agency_health_score": summary["agency_health_score"],
            "open_incidents": summary["open_incidents"],
            "overdue_tasks": summary["overdue_tasks"],
        },
    )
    return _daily_briefing_to_dict(briefing)


def latest_daily_briefing(session: Session) -> DailyBriefing | None:
    return session.scalar(
        select(DailyBriefing).order_by(desc(DailyBriefing.created_at), desc(DailyBriefing.id)).limit(1)
    )


def view_latest_daily_briefing(session: Session, *, actor: User | None) -> dict | None:
    _require_reports(session, actor)
    briefing = latest_daily_briefing(session)
    audit_action(
        session,
        actor=actor,
        action="briefing.viewed",
        resource_type="daily_briefing",
        resource_id=str(briefing.id) if briefing else None,
        details={"status": "found" if briefing else "empty"},
    )
    return _daily_briefing_to_dict(briefing) if briefing else None


def request_briefing_send(session: Session, *, actor: User | None, target: str) -> None:
    _require_reports(session, actor)
    audit_action(
        session,
        actor=actor,
        action="briefing.send_requested",
        resource_type="daily_briefing",
        resource_id=target,
        details={"target": target, "delivery": "placeholder"},
    )


def calculate_accountability_score(
    *,
    assigned_open_tasks: int,
    completed_tasks_today: int,
    overdue_tasks_count: int,
    assigned_open_incidents: int,
    resolved_incidents_today: int,
    critical_incidents_assigned: int = 0,
) -> int:
    score = 100
    score -= overdue_tasks_count * 10
    score -= critical_incidents_assigned * 15
    score -= assigned_open_incidents * 2
    score += completed_tasks_today * 3
    score += resolved_incidents_today * 5
    return max(0, min(120, score))


def _resolved_incidents_today(session: Session, user_id: int, *, now: datetime | None = None) -> int:
    start, end = _today_bounds(now)
    return (
        session.scalar(
            select(func.count(Incident.id)).where(
                Incident.resolved_by_user_id == user_id,
                Incident.resolved_at.is_not(None),
                Incident.resolved_at >= start,
                Incident.resolved_at < end,
            )
        )
        or 0
    )


def generate_accountability_report(session: Session, *, actor: User | None) -> dict:
    _require_reports(session, actor)
    current_time = _now()
    start, end = _today_bounds(current_time)
    users = session.scalars(select(User).options(selectinload(User.roles)).order_by(User.id)).all()
    rows: list[dict] = []
    for user in users:
        roles = [role.name for role in user.roles]
        assigned_open = count_tasks(
            session,
            statuses=("open", "in_progress", "blocked"),
            assigned_to_user_id=user.id,
        )
        completed_today = (
            session.scalar(
                select(func.count(Task.id)).where(
                    Task.assigned_to_user_id == user.id,
                    Task.status == "complete",
                    Task.completed_at.is_not(None),
                    Task.completed_at >= start,
                    Task.completed_at < end,
                )
            )
            or 0
        )
        user_overdue_tasks = count_tasks(session, assigned_to_user_id=user.id, overdue=True)
        open_incidents_assigned = count_incidents(
            session,
            statuses=("open", "investigating"),
            assigned_to_user_id=user.id,
        )
        critical_incidents_assigned = count_incidents(
            session,
            statuses=("open", "investigating"),
            severity="critical",
            assigned_to_user_id=user.id,
        )
        resolved_today = _resolved_incidents_today(session, user.id, now=current_time)
        score = calculate_accountability_score(
            assigned_open_tasks=assigned_open,
            completed_tasks_today=completed_today,
            overdue_tasks_count=user_overdue_tasks,
            assigned_open_incidents=open_incidents_assigned,
            resolved_incidents_today=resolved_today,
            critical_incidents_assigned=critical_incidents_assigned,
        )
        snapshot = AccountabilitySnapshot(
            snapshot_date=_today(current_time),
            user_id=user.id,
            roles_json=roles,
            assigned_open_tasks=assigned_open,
            completed_tasks_today=completed_today,
            overdue_tasks=user_overdue_tasks,
            assigned_open_incidents=open_incidents_assigned,
            resolved_incidents_today=resolved_today,
            last_seen_at=user.last_seen,
            score=score,
        )
        session.add(snapshot)
        session.flush()
        rows.append(
            {
                "snapshot_id": snapshot.id,
                "user_id": user.id,
                "display_name": user.display_name or user.username or f"User {user.id}",
                "assigned_open_tasks": assigned_open,
                "completed_today": completed_today,
                "completed_tasks_today": completed_today,
                "overdue_tasks": user_overdue_tasks,
                "open_incidents_assigned": open_incidents_assigned,
                "assigned_open_incidents": open_incidents_assigned,
                "resolved_incidents_today": resolved_today,
                "last_seen": user.last_seen.isoformat() if user.last_seen else "Not seen yet",
                "roles": roles,
                "score": score,
            }
        )
    report = {"generated_at": current_time.isoformat(), "snapshot_date": _today(current_time).isoformat(), "users": rows}
    emit_event(
        session,
        actor=actor,
        event_name="accountability.generated",
        resource_type="accountability_report",
        resource_id=report["snapshot_date"],
        payload={"users": len(rows)},
    )
    return report


def view_accountability_report(session: Session, *, actor: User | None) -> None:
    _require_reports(session, actor)
    audit_action(
        session,
        actor=actor,
        action="accountability.viewed",
        resource_type="accountability_report",
        resource_id=_today().isoformat(),
    )


def latest_accountability_snapshots(session: Session, *, snapshot_date: date | None = None) -> list[AccountabilitySnapshot]:
    current_date = snapshot_date or _today()
    return list(
        session.scalars(
            select(AccountabilitySnapshot)
            .where(AccountabilitySnapshot.snapshot_date == current_date)
            .order_by(desc(AccountabilitySnapshot.created_at), AccountabilitySnapshot.user_id)
        ).all()
    )


def record_dashboard_view(session: Session, *, actor: User | None, dashboard_name: str) -> None:
    emit_event(
        session,
        actor=actor,
        event_name="dashboard.viewed",
        resource_type="dashboard",
        resource_id=dashboard_name,
        payload={"dashboard": dashboard_name},
    )


def record_report_view(session: Session, *, actor: User | None, report_name: str) -> None:
    emit_event(
        session,
        actor=actor,
        event_name="report.viewed",
        resource_type="report",
        resource_id=report_name,
        payload={"report": report_name},
    )
