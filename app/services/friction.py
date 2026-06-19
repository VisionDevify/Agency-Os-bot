from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.friction import FRICTION_SEVERITIES, FrictionItem
from app.models.user import User
from app.services.auth import audit_action
from app.services.events import emit_event


def create_friction_item(
    session: Session,
    *,
    screen: str,
    issue: str,
    severity: str,
    fix_recommendation: str,
) -> FrictionItem:
    normalized = severity.strip().casefold()
    if normalized not in FRICTION_SEVERITIES:
        raise ValueError("Unsupported friction severity.")
    item = FrictionItem(
        screen=screen.strip()[:120] or "Unknown",
        issue=issue.strip(),
        severity=normalized,
        fix_recommendation=fix_recommendation.strip(),
    )
    session.add(item)
    session.flush()
    return item


def report_problem(
    session: Session,
    *,
    actor: User | None,
    screen: str,
    issue: str,
    severity: str = "medium",
    notes: str | None = None,
    callback_error_log_id: int | None = None,
) -> FrictionItem:
    details: list[str] = [issue.strip() or "Owner reported a product issue."]
    if notes:
        details.append(f"Notes: {notes.strip()}")
    if callback_error_log_id is not None:
        details.append(f"CallbackErrorLog: {callback_error_log_id}")
    item = create_friction_item(
        session,
        screen=screen,
        issue=" | ".join(details),
        severity=severity,
        fix_recommendation="Review this owner-reported mobile QA issue and add a regression test after fixing it.",
    )
    audit_action(
        session,
        actor=actor,
        action="friction.reported",
        resource_type="friction_item",
        resource_id=str(item.id),
        details={
            "screen": item.screen,
            "severity": item.severity,
            "callback_error_log_id": callback_error_log_id,
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name="friction.reported",
        resource_type="friction_item",
        resource_id=str(item.id),
        payload={
            "screen": item.screen,
            "severity": item.severity,
            "callback_error_log_id": callback_error_log_id,
        },
    )
    return item
