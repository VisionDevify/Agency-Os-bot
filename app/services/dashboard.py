from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.audit import AuditLog
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.user import User
from app.services.model_health import HEALTH_CRITICAL, HEALTH_HEALTHY, HEALTH_WARNING, calculate_model_health


@dataclass(frozen=True)
class DashboardStats:
    total_users: int = 0
    active_users: int = 0
    accounts: int = 0
    healthy_proxies: int = 0
    open_tasks: int = 0
    open_incidents: int = 0
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
        healthy_proxies=0,
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
    health_counts = {HEALTH_HEALTHY: 0, HEALTH_WARNING: 0, HEALTH_CRITICAL: 0}
    model_scores: list[tuple[str, int]] = []
    for model in models:
        health = calculate_model_health(model)
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

    return DashboardStats(
        total_users=total_users,
        active_users=active_users,
        accounts=0,
        healthy_proxies=0,
        open_tasks=0,
        open_incidents=0,
        models=len(models),
        healthy_models=health_counts[HEALTH_HEALTHY],
        warning_models=health_counts[HEALTH_WARNING],
        critical_models=health_counts[HEALTH_CRITICAL],
        top_model_activity=top_model_activity,
        recent_model_events=recent_events,
    )
