from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.social import SOCIAL_EVENT_CATEGORIES, SOCIAL_EVENT_SEVERITIES, SOCIAL_EVENT_STATUSES, SocialEvent
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.events import emit_event


def _now() -> datetime:
    return datetime.now(UTC)


def create_social_event(
    session: Session,
    *,
    event_type: str,
    event_category: str,
    source_module: str,
    entity_type: str,
    entity_id: int | str | None,
    actor_type: str = "user",
    actor_id: int | str | None = None,
    actor: User | None = None,
    status: str = "success",
    severity: str = "info",
    summary: str,
    details: dict | None = None,
    evidence: dict | None = None,
) -> SocialEvent:
    if event_category not in SOCIAL_EVENT_CATEGORIES:
        raise ValueError(f"Invalid social event category: {event_category}")
    if status not in SOCIAL_EVENT_STATUSES:
        raise ValueError(f"Invalid social event status: {status}")
    if severity not in SOCIAL_EVENT_SEVERITIES:
        raise ValueError(f"Invalid social event severity: {severity}")
    social_event = SocialEvent(
        event_type=event_type,
        event_category=event_category,
        source_module=source_module,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        actor_type=actor_type,
        actor_id=str(actor_id if actor_id is not None else actor.id if actor is not None else "") or None,
        status=status,
        severity=severity,
        summary=summary,
        details_json=sanitize_details(details or {}),
        evidence_json=sanitize_details(evidence or {}),
        created_at=_now(),
    )
    session.add(social_event)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=event_type,
        resource_type=entity_type,
        resource_id=str(entity_id) if entity_id is not None else None,
        status="success" if status in {"success", "resolved"} else status,
        payload={
            "social_event_id": social_event.id,
            "event_category": event_category,
            "source_module": source_module,
            "summary": summary,
        },
    )
    return social_event
