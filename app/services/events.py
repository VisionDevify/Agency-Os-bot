from sqlalchemy.orm import Session

from app.models.audit import AuditLog
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
    """Lightweight event emission backed by audit_logs until a real event stream exists."""
    event = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=event_name,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        details=sanitize_details(payload),
    )
    session.add(event)
    session.flush()
    return event
