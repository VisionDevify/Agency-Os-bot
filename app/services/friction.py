from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.friction import FRICTION_SEVERITIES, FrictionItem


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
