from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.incident import INCIDENT_SEVERITIES, INCIDENT_SOURCE_TYPES, INCIDENT_STATUSES, Incident, IncidentTimeline
from app.models.model_brand import ModelBrand
from app.models.proxy import Proxy
from app.models.user import User
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.events import emit_event

ESCALATION_PATHS: dict[str, tuple[str, ...]] = {
    "chatter": ("Senior Chatter", "Chatter Manager", "Manager", "Owner"),
    "va": ("Manager", "Owner"),
    "proxy": ("Admin", "Manager", "Owner"),
    "system": ("Admin", "Manager", "Owner"),
    "account": ("Manager", "Owner"),
    "manual": ("Manager", "Owner"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_severity(severity: str) -> str:
    if severity == "low":
        return "info"
    if severity in {"medium", "high"}:
        return "warning"
    return severity


def _require_manage_incidents(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_incidents"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="incident",
        status="denied",
        details={"permission": "manage_incidents"},
    )
    raise PermissionError("Missing permission: manage_incidents")


def _require_resolve_incidents(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "resolve_incidents") or user_has_permission(actor, "manage_incidents"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="incident",
        status="denied",
        details={"permission": "resolve_incidents"},
    )
    raise PermissionError("Missing permission: resolve_incidents")


def _incident_payload(incident: Incident, extra: dict | None = None) -> dict:
    payload = {
        "incident_id": incident.id,
        "status": incident.status,
        "severity": incident.severity,
        "source_type": incident.source_type,
        "model_brand_id": incident.model_brand_id,
        "account_id": incident.account_id,
        "proxy_id": incident.proxy_id,
        "assigned_to_user_id": incident.assigned_to_user_id,
        "owner_user_id": incident.owner_user_id,
        "escalation_level": incident.escalation_level,
    }
    payload.update(extra or {})
    return payload


def _base_incident_query():
    return select(Incident).options(
        selectinload(Incident.model_brand),
        selectinload(Incident.account),
        selectinload(Incident.proxy),
        selectinload(Incident.owner),
        selectinload(Incident.assigned_to),
        selectinload(Incident.created_by),
        selectinload(Incident.resolved_by),
        selectinload(Incident.timeline_entries),
    )


def add_timeline_entry(
    session: Session,
    incident: Incident,
    *,
    actor: User | None,
    event_type: str,
    message: str,
    metadata: dict | None = None,
) -> IncidentTimeline:
    entry = IncidentTimeline(
        incident_id=incident.id,
        actor_user_id=actor.id if actor else None,
        event_type=event_type,
        message=message,
        metadata_json=metadata or {},
    )
    session.add(entry)
    session.flush()
    return entry


def list_incidents(session: Session, *, include_archived: bool = False) -> list[Incident]:
    statement = _base_incident_query().order_by(Incident.severity.desc(), Incident.id.desc())
    if not include_archived:
        statement = statement.where(Incident.status != "archived")
    return list(session.scalars(statement).all())


def get_incident(session: Session, incident_id: int) -> Incident | None:
    return session.scalar(_base_incident_query().where(Incident.id == incident_id))


def incidents_for_model(session: Session, model_brand_id: int, *, include_archived: bool = False) -> list[Incident]:
    statement = _base_incident_query().where(Incident.model_brand_id == model_brand_id).order_by(Incident.id.desc())
    if not include_archived:
        statement = statement.where(Incident.status != "archived")
    return list(session.scalars(statement).all())


def create_incident(
    session: Session,
    *,
    actor: User | None,
    title: str,
    description: str | None = None,
    severity: str = "warning",
    source_type: str = "manual",
    model_brand: ModelBrand | None = None,
    account: Account | None = None,
    proxy: Proxy | None = None,
    owner_user: User | None = None,
    assigned_to: User | None = None,
) -> Incident:
    if actor is not None:
        _require_manage_incidents(session, actor)
    normalized_severity = normalize_severity(severity)
    if normalized_severity not in INCIDENT_SEVERITIES:
        raise ValueError(f"Invalid incident severity: {severity}")
    if source_type not in INCIDENT_SOURCE_TYPES:
        raise ValueError(f"Invalid incident source type: {source_type}")
    if assigned_to is not None and (assigned_to.status != USER_STATUS_ACTIVE or not assigned_to.is_active):
        raise PermissionError("Only active users can be assigned incidents")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Incident title is required")
    incident = Incident(
        name=clean_title,
        title=clean_title,
        description=description,
        status="open",
        severity=normalized_severity,
        source_type=source_type,
        source_id=str(proxy.id) if proxy is not None else None,
        model_brand_id=model_brand.id if model_brand else None,
        account_id=account.id if account else None,
        proxy_id=proxy.id if proxy else None,
        owner_user_id=owner_user.id if owner_user else (actor.id if actor else None),
        assigned_to_user_id=assigned_to.id if assigned_to else None,
        assigned_user_id=assigned_to.id if assigned_to else None,
        created_by_user_id=actor.id if actor else None,
        metadata_json={"source_type": source_type},
    )
    session.add(incident)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="incident.created",
        resource_type="incident",
        resource_id=str(incident.id),
        status=incident.status,
        payload=_incident_payload(incident),
    )
    add_timeline_entry(
        session,
        incident,
        actor=actor,
        event_type="incident.created",
        message=f"Incident created: {incident.title}",
        metadata=_incident_payload(incident),
    )
    return incident


def create_default_incident(session: Session, *, actor: User) -> Incident:
    next_number = session.scalar(select(func.count(Incident.id))) or 0
    return create_incident(
        session,
        actor=actor,
        title=f"New Incident {next_number + 1}",
        description="Created from Telegram. TODO: replace with real investigation notes.",
        severity="warning",
        source_type="manual",
    )


def assign_incident(session: Session, incident: Incident, assignee: User, *, actor: User) -> Incident:
    _require_manage_incidents(session, actor)
    if assignee.status != USER_STATUS_ACTIVE or not assignee.is_active:
        raise PermissionError("Only active users can be assigned incidents")
    incident.assigned_to_user_id = assignee.id
    incident.assigned_user_id = assignee.id
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="incident.assigned",
        resource_type="incident",
        resource_id=str(incident.id),
        payload=_incident_payload(incident, {"assigned_to_user_id": assignee.id}),
    )
    add_timeline_entry(
        session,
        incident,
        actor=actor,
        event_type="incident.assigned",
        message=f"Assigned to {assignee.display_name or assignee.username or assignee.id}",
        metadata={"assigned_to_user_id": assignee.id},
    )
    return incident


def escalation_target_for(incident: Incident) -> str:
    path = ESCALATION_PATHS.get(incident.source_type or "manual", ESCALATION_PATHS["manual"])
    index = min(incident.escalation_level, len(path) - 1)
    return path[index]


def escalate_incident(session: Session, incident: Incident, *, actor: User) -> Incident:
    _require_manage_incidents(session, actor)
    previous_target = escalation_target_for(incident)
    incident.escalation_level += 1
    incident.status = "investigating"
    incident.last_escalated_at = _now()
    new_target = escalation_target_for(incident)
    history = list(incident.escalation_history or [])
    history.append(
        {
            "at": _now().isoformat(),
            "from": previous_target,
            "to": new_target,
            "actor_user_id": actor.id,
        }
    )
    incident.escalation_history = history
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="incident.escalated",
        resource_type="incident",
        resource_id=str(incident.id),
        payload=_incident_payload(incident, {"to": new_target}),
    )
    add_timeline_entry(
        session,
        incident,
        actor=actor,
        event_type="incident.escalated",
        message=f"Escalated from {previous_target} to {new_target}",
        metadata={"from": previous_target, "to": new_target, "escalation_level": incident.escalation_level},
    )
    return incident


def investigate_incident(session: Session, incident: Incident, *, actor: User) -> Incident:
    _require_manage_incidents(session, actor)
    incident.status = "investigating"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="incident.investigating",
        resource_type="incident",
        resource_id=str(incident.id),
        payload=_incident_payload(incident),
    )
    add_timeline_entry(
        session,
        incident,
        actor=actor,
        event_type="incident.investigating",
        message="Investigation started.",
        metadata=_incident_payload(incident),
    )
    return incident


def resolve_incident(
    session: Session,
    incident: Incident,
    *,
    actor: User,
    resolution_notes: str | None = None,
) -> Incident:
    _require_resolve_incidents(session, actor)
    incident.status = "resolved"
    incident.resolution_notes = resolution_notes or "Resolved from Telegram operations workflow."
    incident.resolved_by_user_id = actor.id
    incident.resolved_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="incident.resolved",
        resource_type="incident",
        resource_id=str(incident.id),
        payload=_incident_payload(incident),
    )
    add_timeline_entry(
        session,
        incident,
        actor=actor,
        event_type="incident.resolved",
        message=incident.resolution_notes or "Incident resolved.",
        metadata={"resolved_by_user_id": actor.id},
    )
    return incident


def archive_incident(session: Session, incident: Incident, *, actor: User) -> Incident:
    _require_manage_incidents(session, actor)
    incident.status = "archived"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="incident.archived",
        resource_type="incident",
        resource_id=str(incident.id),
        payload=_incident_payload(incident),
    )
    add_timeline_entry(
        session,
        incident,
        actor=actor,
        event_type="incident.archived",
        message="Incident archived.",
        metadata=_incident_payload(incident),
    )
    return incident


def incident_timeline(session: Session, incident: Incident, *, limit: int = 20) -> list[IncidentTimeline]:
    return list(
        session.scalars(
            select(IncidentTimeline)
            .where(IncidentTimeline.incident_id == incident.id)
            .order_by(IncidentTimeline.created_at.desc(), IncidentTimeline.id.desc())
            .limit(limit)
        ).all()
    )


def my_incidents(session: Session, user: User) -> list[Incident]:
    return list(
        session.scalars(
            _base_incident_query()
            .where(Incident.assigned_to_user_id == user.id, Incident.status != "archived")
            .order_by(Incident.id.desc())
        ).all()
    )


def critical_incidents(session: Session) -> list[Incident]:
    return list(
        session.scalars(
            _base_incident_query()
            .where(Incident.severity == "critical", Incident.status.in_(("open", "investigating")))
            .order_by(Incident.id.desc())
        ).all()
    )


def open_incidents(session: Session) -> list[Incident]:
    return list(
        session.scalars(
            _base_incident_query()
            .where(Incident.status.in_(("open", "investigating")))
            .order_by(Incident.id.desc())
        ).all()
    )


def count_incidents(
    session: Session,
    *,
    statuses: tuple[str, ...] | None = None,
    severity: str | None = None,
    assigned_to_user_id: int | None = None,
) -> int:
    statement = select(func.count(Incident.id))
    if statuses is not None:
        statement = statement.where(Incident.status.in_(statuses))
    if severity is not None:
        statement = statement.where(Incident.severity == severity)
    if assigned_to_user_id is not None:
        statement = statement.where(Incident.assigned_to_user_id == assigned_to_user_id)
    return session.scalar(statement) or 0


def incident_audit_logs(session: Session, incident: Incident, *, limit: int = 10) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_type == "incident", AuditLog.resource_id == str(incident.id))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
    )


def severity_label(severity: str) -> str:
    return {
        "info": "Info",
        "warning": "Warning",
        "critical": "Critical",
    }.get(severity, severity.title())
