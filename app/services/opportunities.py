from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.opportunity import (
    OPPORTUNITY_PLATFORMS,
    OPPORTUNITY_RESULT_STATUSES,
    OPPORTUNITY_STATUSES,
    Opportunity,
    OpportunityResult,
    OpportunitySource,
)
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action, user_has_permission
from app.services.events import emit_event


def _now() -> datetime:
    return datetime.now(UTC)


def _require_opportunity_access(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "manage_tasks"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="opportunity",
        status="denied",
        details={"permission": "manage_reports_or_manage_tasks"},
    )
    raise PermissionError("Missing permission: manage_reports or manage_tasks")


def list_opportunity_sources(session: Session, *, active_only: bool = True) -> list[OpportunitySource]:
    statement = select(OpportunitySource).order_by(OpportunitySource.platform, OpportunitySource.name)
    if active_only:
        statement = statement.where(OpportunitySource.is_active.is_(True))
    return list(session.scalars(statement).all())


def create_opportunity_source(
    session: Session,
    *,
    actor: User | None,
    platform: str,
    name: str,
    url: str | None = None,
    niche: str | None = None,
) -> OpportunitySource:
    _require_opportunity_access(session, actor)
    if platform not in OPPORTUNITY_PLATFORMS:
        raise ValueError(f"Invalid opportunity platform: {platform}")
    source = OpportunitySource(
        platform=platform,
        name=name.strip() or "Manual Source",
        url=url,
        niche=niche,
        is_active=True,
    )
    session.add(source)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="opportunity_source.created",
        resource_type="opportunity_source",
        resource_id=str(source.id),
        payload={"platform": source.platform, "niche": source.niche},
    )
    return source


def list_opportunities(session: Session, *, include_archived: bool = False, limit: int = 25) -> list[Opportunity]:
    statement = (
        select(Opportunity)
        .options(selectinload(Opportunity.source))
        .order_by(desc(Opportunity.score), desc(Opportunity.created_at), desc(Opportunity.id))
        .limit(limit)
    )
    if not include_archived:
        statement = statement.where(Opportunity.status != "archived")
    return list(session.scalars(statement).all())


def get_opportunity(session: Session, opportunity_id: int) -> Opportunity | None:
    return session.scalar(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id)
        .options(selectinload(Opportunity.source))
    )


def create_manual_opportunity(
    session: Session,
    *,
    actor: User | None,
    title: str,
    platform: str = "x",
    url: str | None = None,
    niche: str | None = None,
    model_brand_id: int | None = None,
    reason: str | None = None,
    suggested_angle: str | None = None,
    source: OpportunitySource | None = None,
) -> Opportunity:
    _require_opportunity_access(session, actor)
    if platform not in OPPORTUNITY_PLATFORMS:
        raise ValueError(f"Invalid opportunity platform: {platform}")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Opportunity title is required")
    opportunity = Opportunity(
        source_id=source.id if source else None,
        platform=platform,
        title=clean_title,
        url=url,
        niche=niche,
        model_brand_id=model_brand_id,
        score=0,
        status="discovered",
        reason=reason,
        suggested_angle=suggested_angle,
    )
    session.add(opportunity)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.created",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={
            "platform": opportunity.platform,
            "niche": opportunity.niche,
            "model_brand_id": opportunity.model_brand_id,
            "posting": "manual_only",
        },
    )
    return opportunity


def create_default_opportunity(session: Session, *, actor: User | None) -> Opportunity:
    next_number = len(list_opportunities(session, include_archived=True, limit=500)) + 1
    return create_manual_opportunity(
        session,
        actor=actor,
        title=f"Manual Opportunity {next_number}",
        platform="x",
        niche="general",
        reason="Created from Telegram for human review.",
        suggested_angle="Draft a human-approved outreach/comment angle before any posting.",
    )


def score_opportunity(
    session: Session,
    opportunity: Opportunity,
    *,
    actor: User | None,
    score: int | None = None,
) -> Opportunity:
    _require_opportunity_access(session, actor)
    if score is None:
        score = 35
        if opportunity.model_brand_id is not None:
            score += 20
        if opportunity.niche:
            score += 15
        if opportunity.url:
            score += 10
        if opportunity.reason:
            score += 10
        if opportunity.suggested_angle:
            score += 10
    opportunity.score = max(0, min(100, score))
    if opportunity.status == "discovered":
        opportunity.status = "reviewing"
    opportunity.updated_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.scored",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={"score": opportunity.score, "status": opportunity.status},
    )
    return opportunity


def assign_opportunity(
    session: Session,
    opportunity: Opportunity,
    assignee: User,
    *,
    actor: User | None,
) -> Opportunity:
    _require_opportunity_access(session, actor)
    opportunity.assigned_to_user_id = assignee.id
    opportunity.status = "assigned"
    opportunity.updated_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.assigned",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={"assigned_to_user_id": assignee.id},
    )
    return opportunity


def update_opportunity_status(
    session: Session,
    opportunity: Opportunity,
    *,
    actor: User | None,
    status: str,
) -> Opportunity:
    _require_opportunity_access(session, actor)
    if status not in OPPORTUNITY_STATUSES:
        raise ValueError(f"Invalid opportunity status: {status}")
    old_status = opportunity.status
    opportunity.status = status
    opportunity.updated_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.status_changed",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={"from": old_status, "to": status},
    )
    return opportunity


def record_opportunity_result(
    session: Session,
    opportunity: Opportunity,
    *,
    actor: User | None,
    status: str = "posted",
    clicks: int | None = None,
    conversions: int | None = None,
    notes: str | None = None,
) -> OpportunityResult:
    if actor is None or opportunity.assigned_to_user_id != actor.id:
        _require_opportunity_access(session, actor)
    if status not in OPPORTUNITY_RESULT_STATUSES:
        raise ValueError(f"Invalid opportunity result status: {status}")
    result = OpportunityResult(
        opportunity_id=opportunity.id,
        posted_by_user_id=actor.id if actor else None,
        status=status,
        clicks=clicks,
        conversions=conversions,
        notes=notes,
    )
    session.add(result)
    if status == "posted":
        opportunity.status = "completed"
    elif status in {"skipped", "failed"}:
        opportunity.status = "reviewing"
    opportunity.updated_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.result_recorded",
        resource_type="opportunity_result",
        resource_id=str(result.id),
        payload=sanitize_details(
            {
                "opportunity_id": opportunity.id,
                "status": result.status,
                "clicks": clicks,
                "conversions": conversions,
                "posting": "manual_record_only",
            }
        ),
    )
    return result


def opportunity_results(session: Session, opportunity: Opportunity | None = None, *, limit: int = 20) -> list[OpportunityResult]:
    statement = select(OpportunityResult).order_by(desc(OpportunityResult.created_at), desc(OpportunityResult.id)).limit(limit)
    if opportunity is not None:
        statement = statement.where(OpportunityResult.opportunity_id == opportunity.id)
    return list(session.scalars(statement).all())


def run_opportunity_scoring(session: Session, *, actor: User | None) -> int:
    _require_opportunity_access(session, actor)
    opportunities = list(
        session.scalars(
            select(Opportunity).where(Opportunity.status.in_(("discovered", "reviewing"))).order_by(Opportunity.id)
        ).all()
    )
    for opportunity in opportunities:
        score_opportunity(session, opportunity, actor=actor)
    emit_event(
        session,
        actor=actor,
        event_name="opportunity_scoring.completed",
        resource_type="opportunity",
        payload={"scored": len(opportunities), "mode": "deterministic_no_scraping"},
    )
    return len(opportunities)
