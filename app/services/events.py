from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.user import User
from app.services.audit import sanitize_details


def emit_event(
    session: Session,
    *,
    actor: User | None,
    event_name: str,
    resource_type: str,
    resource_id: str | None = None,
    status: str = "success",
    payload: dict | None = None,
) -> AuditLog:
    """Emit a safe event to both the audit trail and lightweight event log."""
    safe_payload = sanitize_details(payload)
    event = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=event_name,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        details=safe_payload,
    )
    event_log = EventLog(
        event_type=event_name,
        actor_user_id=actor.id if actor else None,
        entity_type=resource_type,
        entity_id=resource_id,
        metadata_json=safe_payload,
    )
    session.add(event)
    session.add(event_log)
    session.flush()
    return event
