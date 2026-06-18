from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.model_brand import ModelBrand
from app.models.proxy import Proxy
from app.models.recommendation import RECOMMENDATION_SEVERITIES, RECOMMENDATION_STATUSES, Recommendation
from app.models.task import Task
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action, user_has_permission
from app.services.events import emit_event


def _now() -> datetime:
    return datetime.now(UTC)


def _require_reports(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "view_dashboard"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="recommendation",
        status="denied",
        details={"permission": "manage_reports_or_view_dashboard"},
    )
    raise PermissionError("Missing permission: manage_reports or view_dashboard")


def _find_open_recommendation(
    session: Session,
    *,
    recommendation_type: str,
    entity_type: str | None,
    entity_id: str | None,
) -> Recommendation | None:
    return session.scalar(
        select(Recommendation).where(
            Recommendation.recommendation_type == recommendation_type,
            Recommendation.entity_type == entity_type,
            Recommendation.entity_id == entity_id,
            Recommendation.status == "open",
        )
    )


def _upsert_recommendation(
    session: Session,
    *,
    actor: User | None,
    recommendation_type: str,
    title: str,
    description: str,
    severity: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    metadata: dict | None = None,
) -> Recommendation:
    if severity not in RECOMMENDATION_SEVERITIES:
        raise ValueError(f"Invalid recommendation severity: {severity}")
    entity_id_text = str(entity_id) if entity_id is not None else None
    recommendation = _find_open_recommendation(
        session,
        recommendation_type=recommendation_type,
        entity_type=entity_type,
        entity_id=entity_id_text,
    )
    created = recommendation is None
    if recommendation is None:
        recommendation = Recommendation(
            recommendation_type=recommendation_type,
            title=title,
            description=description,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id_text,
            status="open",
            metadata_json=sanitize_details(metadata),
        )
        session.add(recommendation)
    else:
        recommendation.title = title
        recommendation.description = description
        recommendation.severity = severity
        recommendation.metadata_json = sanitize_details(metadata)
        recommendation.updated_at = _now()
    session.flush()
    if created:
        emit_event(
            session,
            actor=actor,
            event_name="recommendation.generated",
            resource_type="recommendation",
            resource_id=str(recommendation.id),
            payload={
                "recommendation_type": recommendation_type,
                "severity": severity,
                "entity_type": entity_type,
                "entity_id": entity_id_text,
            },
        )
    return recommendation


def upsert_recommendation(
    session: Session,
    *,
    actor: User | None,
    recommendation_type: str,
    title: str,
    description: str,
    severity: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    metadata: dict | None = None,
) -> Recommendation:
    return _upsert_recommendation(
        session,
        actor=actor,
        recommendation_type=recommendation_type,
        title=title,
        description=description,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata,
    )


def generate_recommendations(session: Session, *, actor: User | None) -> list[Recommendation]:
    _require_reports(session, actor)
    generated: list[Recommendation] = []

    accounts_missing_proxy = session.scalar(
        select(func.count(Account.id)).where(Account.status != "archived", Account.assigned_proxy_id.is_(None))
    ) or 0
    if accounts_missing_proxy:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="accounts_missing_proxy",
                title="Accounts Missing Proxy",
                description=f"{accounts_missing_proxy} active accounts do not have a proxy assigned.",
                severity="warning",
                metadata={"count": accounts_missing_proxy},
            )
        )

    accounts_needing_login = session.scalar(
        select(func.count(Account.id)).where(
            Account.status != "archived",
            Account.auth_status.in_(("needs_login", "needs_2fa", "expired", "locked")),
        )
    ) or 0
    if accounts_needing_login:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="accounts_needing_login",
                title="Accounts Need Auth Attention",
                description=f"{accounts_needing_login} accounts need login, 2FA, or recovery attention.",
                severity="critical" if accounts_needing_login > 3 else "warning",
                metadata={"count": accounts_needing_login},
            )
        )

    overdue_task_count = session.scalar(
        select(func.count(Task.id)).where(
            Task.due_at.is_not(None),
            Task.due_at < func.now(),
            Task.status.in_(("open", "in_progress", "blocked")),
        )
    ) or 0
    if overdue_task_count:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="overdue_tasks",
                title="Overdue Tasks",
                description=f"{overdue_task_count} tasks are overdue and need review.",
                severity="warning",
                metadata={"count": overdue_task_count},
            )
        )

    critical_incidents = list(
        session.scalars(
            select(Incident).where(
                Incident.status.in_(("open", "investigating")),
                Incident.severity == "critical",
            )
        ).all()
    )
    for incident in critical_incidents[:10]:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="critical_incident_open",
                title="Critical Incident Open",
                description=incident.title,
                severity="critical",
                entity_type="incident",
                entity_id=incident.id,
                metadata={"severity": incident.severity, "status": incident.status},
            )
        )

    proxies = list(session.scalars(select(Proxy).where(Proxy.status.in_(("warning", "critical")))).all())
    if proxies:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="proxies_warning_critical",
                title="Proxy Vault Needs Attention",
                description=f"{len(proxies)} proxies are warning or critical.",
                severity="critical" if any(proxy.status == "critical" for proxy in proxies) else "warning",
                metadata={"proxy_ids": [proxy.id for proxy in proxies[:25]]},
            )
        )

    mismatch_proxies = [
        proxy
        for proxy in session.scalars(select(Proxy)).all()
        if (
            proxy.target_country
            and proxy.detected_country
            and proxy.target_country.casefold() != proxy.detected_country.casefold()
        )
        or (
            proxy.target_state
            and proxy.detected_state
            and proxy.target_state.casefold() != proxy.detected_state.casefold()
        )
        or (
            proxy.target_city
            and proxy.detected_city
            and proxy.target_city.casefold() != proxy.detected_city.casefold()
        )
    ]
    if mismatch_proxies:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="proxy_location_mismatch",
                title="Proxy Location Mismatch",
                description=f"{len(mismatch_proxies)} proxies do not match their target location.",
                severity="warning",
                metadata={"proxy_ids": [proxy.id for proxy in mismatch_proxies[:25]]},
            )
        )

    failed_repairs = list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "proxy.repair.failed")
            .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
            .limit(10)
        ).all()
    )
    if failed_repairs:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="failed_repair_attempts",
                title="Failed Repair Attempts",
                description=f"{len(failed_repairs)} recent proxy repair attempts failed.",
                severity="critical",
                metadata={"count": len(failed_repairs)},
            )
        )

    models = list(
        session.scalars(
            select(ModelBrand)
            .where(ModelBrand.status == "active")
            .options(selectinload(ModelBrand.members))
        ).all()
    )
    without_manager = [
        model for model in models if not any(member.relationship_type == "manager" for member in model.members)
    ]
    if without_manager:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="models_without_manager",
                title="Models Without Manager",
                description=f"{len(without_manager)} active models do not have an assigned manager.",
                severity="warning",
                metadata={"model_ids": [model.id for model in without_manager[:25]]},
            )
        )
    without_chatter = [
        model
        for model in models
        if not any(member.relationship_type in {"chatter", "senior_chatter", "chatter_manager"} for member in model.members)
    ]
    if without_chatter:
        generated.append(
            _upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="models_without_chatter_team",
                title="Models Without Chatter Team",
                description=f"{len(without_chatter)} active models do not have a chatter team assigned.",
                severity="warning",
                metadata={"model_ids": [model.id for model in without_chatter[:25]]},
            )
        )

    return generated


def list_recommendations(
    session: Session,
    *,
    status: str | None = "open",
    limit: int = 20,
) -> list[Recommendation]:
    statement = select(Recommendation).order_by(
        desc(Recommendation.severity == "critical"),
        desc(Recommendation.created_at),
        desc(Recommendation.id),
    )
    if status is not None:
        statement = statement.where(Recommendation.status == status)
    return list(session.scalars(statement.limit(limit)).all())


def get_recommendation(session: Session, recommendation_id: int) -> Recommendation | None:
    return session.get(Recommendation, recommendation_id)


def update_recommendation_status(
    session: Session,
    recommendation: Recommendation,
    *,
    actor: User,
    status: str,
) -> Recommendation:
    _require_reports(session, actor)
    if status not in RECOMMENDATION_STATUSES:
        raise ValueError(f"Invalid recommendation status: {status}")
    old_status = recommendation.status
    recommendation.status = status
    recommendation.updated_at = _now()
    session.flush()
    action = {
        "acknowledged": "recommendation.acknowledged",
        "dismissed": "recommendation.dismissed",
        "resolved": "recommendation.resolved",
    }.get(status, "recommendation.status_changed")
    audit_action(
        session,
        actor=actor,
        action=action,
        resource_type="recommendation",
        resource_id=str(recommendation.id),
        details={"from": old_status, "to": status, "recommendation_type": recommendation.recommendation_type},
    )
    emit_event(
        session,
        actor=actor,
        event_name="recommendation.status_changed",
        resource_type="recommendation",
        resource_id=str(recommendation.id),
        payload={"from": old_status, "to": status, "recommendation_type": recommendation.recommendation_type},
    )
    from app.services.learning import capture_recommendation_status

    capture_recommendation_status(session, recommendation, actor=actor, status=status)
    return recommendation
