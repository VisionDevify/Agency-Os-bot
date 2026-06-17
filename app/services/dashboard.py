from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.task import Task
from app.models.user import User
from app.services.account_health import ACCOUNT_HEALTH_CRITICAL, calculate_account_health
from app.services.model_health import HEALTH_CRITICAL, HEALTH_HEALTHY, HEALTH_WARNING, calculate_model_health
from app.services.proxies import infrastructure_stats


@dataclass(frozen=True)
class DashboardStats:
    total_users: int = 0
    active_users: int = 0
    accounts: int = 0
    instagram_accounts: int = 0
    x_accounts: int = 0
    onlyfans_accounts: int = 0
    accounts_needing_login: int = 0
    accounts_needing_2fa: int = 0
    critical_accounts: int = 0
    healthy_proxies: int = 0
    warning_proxies: int = 0
    critical_proxies: int = 0
    total_proxies: int = 0
    accounts_assigned_proxy: int = 0
    accounts_missing_proxy: int = 0
    recent_proxy_rotations: tuple[str, ...] = ()
    recent_proxy_failures: tuple[str, ...] = ()
    recent_proxy_incidents: tuple[str, ...] = ()
    average_proxy_health_score: int = 0
    open_tasks: int = 0
    open_incidents: int = 0
    overdue_tasks: int = 0
    blocked_tasks: int = 0
    completed_tasks_today: int = 0
    critical_incidents: int = 0
    models: int = 0
    healthy_models: int = 0
    warning_models: int = 0
    critical_models: int = 0
    top_model_activity: tuple[str, ...] = ()
    recent_model_events: tuple[str, ...] = ()


def placeholder_dashboard_stats() -> DashboardStats:
    return DashboardStats(
        total_users=1,
        active_users=1,
        accounts=0,
        instagram_accounts=0,
        x_accounts=0,
        onlyfans_accounts=0,
        accounts_needing_login=0,
        accounts_needing_2fa=0,
        critical_accounts=0,
        healthy_proxies=0,
        warning_proxies=0,
        critical_proxies=0,
        total_proxies=0,
        accounts_assigned_proxy=0,
        accounts_missing_proxy=0,
        average_proxy_health_score=0,
        open_tasks=0,
        open_incidents=0,
        models=0,
        healthy_models=0,
        warning_models=0,
        critical_models=0,
    )


def dashboard_stats(session: Session) -> DashboardStats:
    total_users = session.scalar(select(func.count(User.id))) or 0
    active_users = (
        session.scalar(select(func.count(User.id)).where(User.status == "active", User.is_active.is_(True)))
        or 0
    )
    models = list(
        session.scalars(
            select(ModelBrand)
            .where(ModelBrand.status != "archived")
            .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
            .order_by(ModelBrand.id)
        ).all()
    )
    accounts = list(
        session.scalars(
            select(Account)
            .where(Account.status != "archived")
            .options(selectinload(Account.model_brand))
            .order_by(Account.id)
        ).all()
    )
    health_counts = {HEALTH_HEALTHY: 0, HEALTH_WARNING: 0, HEALTH_CRITICAL: 0}
    model_scores: list[tuple[str, int]] = []
    for model in models:
        model_accounts = [account for account in accounts if account.model_brand_id == model.id]
        health = calculate_model_health(
            model,
            disabled_accounts=sum(1 for account in model_accounts if account.status == "disabled"),
            warning_accounts=sum(
                1
                for account in model_accounts
                if account.status == "warning" or account.auth_status in {"needs_login", "needs_2fa"}
            ),
        )
        health_counts[health.status] += 1
        model_scores.append((model.display_name, health.score))

    activity_rows = session.execute(
        select(AuditLog.resource_id, func.count(AuditLog.id))
        .where(AuditLog.resource_type == "model_brand", AuditLog.resource_id.is_not(None))
        .group_by(AuditLog.resource_id)
        .order_by(func.count(AuditLog.id).desc())
        .limit(5)
    ).all()
    model_names = {str(model.id): model.display_name for model in models}
    top_model_activity = tuple(
        f"{model_names.get(str(resource_id), 'Model ' + str(resource_id))}: {count} events"
        for resource_id, count in activity_rows
    )
    if not top_model_activity:
        top_model_activity = tuple(
            f"{name}: {score}/100" for name, score in sorted(model_scores, key=lambda item: item[1])[:5]
        )

    recent_events = tuple(
        f"{log.action} -> {model_names.get(str(log.resource_id), 'Model ' + str(log.resource_id))}"
        for log in session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_type == "model_brand")
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(5)
        ).all()
    )
    platform_counts = {
        "instagram": sum(1 for account in accounts if account.platform == "instagram"),
        "x": sum(1 for account in accounts if account.platform == "x"),
        "onlyfans": sum(1 for account in accounts if account.platform == "onlyfans"),
    }
    critical_accounts = sum(
        1 for account in accounts if calculate_account_health(account).status == ACCOUNT_HEALTH_CRITICAL
    )
    infrastructure = infrastructure_stats(session)
    open_tasks = (
        session.scalar(select(func.count(Task.id)).where(Task.status.in_(("open", "in_progress", "blocked"))))
        or 0
    )
    overdue_tasks = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.due_at.is_not(None),
                Task.due_at < func.now(),
                Task.status.in_(("open", "in_progress", "blocked")),
            )
        )
        or 0
    )
    blocked_tasks = session.scalar(select(func.count(Task.id)).where(Task.status == "blocked")) or 0
    completed_tasks_today = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.status == "complete",
                Task.completed_at.is_not(None),
                func.date(Task.completed_at) == func.current_date(),
            )
        )
        or 0
    )
    open_incidents = (
        session.scalar(select(func.count(Incident.id)).where(Incident.status.in_(("open", "investigating"))))
        or 0
    )
    critical_incidents = (
        session.scalar(
            select(func.count(Incident.id)).where(
                Incident.status.in_(("open", "investigating")),
                Incident.severity == "critical",
            )
        )
        or 0
    )

    return DashboardStats(
        total_users=total_users,
        active_users=active_users,
        accounts=len(accounts),
        instagram_accounts=platform_counts["instagram"],
        x_accounts=platform_counts["x"],
        onlyfans_accounts=platform_counts["onlyfans"],
        accounts_needing_login=sum(1 for account in accounts if account.auth_status == "needs_login"),
        accounts_needing_2fa=sum(1 for account in accounts if account.auth_status == "needs_2fa"),
        critical_accounts=critical_accounts,
        healthy_proxies=infrastructure.healthy_proxies,
        warning_proxies=infrastructure.warning_proxies,
        critical_proxies=infrastructure.critical_proxies,
        total_proxies=infrastructure.total_proxies,
        accounts_assigned_proxy=infrastructure.accounts_assigned_proxy,
        accounts_missing_proxy=infrastructure.accounts_missing_proxy,
        recent_proxy_rotations=infrastructure.recent_rotations,
        recent_proxy_failures=infrastructure.recent_failures,
        recent_proxy_incidents=infrastructure.recent_incidents,
        average_proxy_health_score=infrastructure.average_health_score,
        open_tasks=open_tasks,
        open_incidents=open_incidents,
        overdue_tasks=overdue_tasks,
        blocked_tasks=blocked_tasks,
        completed_tasks_today=completed_tasks_today,
        critical_incidents=critical_incidents,
        models=len(models),
        healthy_models=health_counts[HEALTH_HEALTHY],
        warning_models=health_counts[HEALTH_WARNING],
        critical_models=health_counts[HEALTH_CRITICAL],
        top_model_activity=top_model_activity,
        recent_model_events=recent_events,
    )
