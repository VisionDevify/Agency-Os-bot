from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.learning import OutcomeMemory
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import (
    CREATOR_WATCH_PLATFORMS,
    CREATOR_WATCH_PRIORITIES,
    CREATOR_WATCH_STATUSES,
    OPPORTUNITY_PRIORITIES,
    POST_WATCH_PLATFORMS,
    POST_WATCH_ATTENTION_LEVELS,
    POST_WATCH_STATUSES,
    POST_WATCH_TYPES,
    CommentStrategy,
    CreatorWatch,
    OPPORTUNITY_PLATFORMS,
    OPPORTUNITY_RESULT_STATUSES,
    OPPORTUNITY_SOURCE_TYPES,
    OPPORTUNITY_STATUSES,
    Opportunity,
    OpportunityResult,
    OpportunitySource,
    PostWatch,
)
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.models.team_rollout import TeamOnboardingChecklist
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.events import emit_event
from app.services.notifications import active_targets_for_event, create_delivery_attempt
from app.services.team_operations import get_or_create_availability


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


def _require_opportunity_manage(session: Session, actor: User | None) -> None:
    if (
        user_has_permission(actor, "manage_reports")
        or user_has_permission(actor, "manage_tasks")
        or user_has_permission(actor, "manage_chatter_team")
    ):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="opportunity",
        status="denied",
        details={"permission": "manage_reports_or_manage_tasks_or_manage_chatter_team"},
    )
    raise PermissionError("Missing opportunity management permission")


def _can_view_opportunities(actor: User | None) -> bool:
    return any(
        user_has_permission(actor, permission)
        for permission in ("manage_reports", "manage_tasks", "view_dashboard", "view_chatter_dashboard")
    )


def _require_opportunity_view(session: Session, actor: User | None) -> None:
    if _can_view_opportunities(actor):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="opportunity",
        status="denied",
        details={"permission": "view_opportunity_space"},
    )
    raise PermissionError("Missing opportunity view permission")


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _identity(user: User | None) -> str:
    if user is None:
        return "Unassigned"
    return user.display_name or user.username or f"User {user.id}"


def _date_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def active_users_for_opportunity_assignment(session: Session, *, limit: int = 25) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .where(User.status == USER_STATUS_ACTIVE, User.is_active.is_(True))
            .options(selectinload(User.roles))
            .order_by(User.display_name, User.id)
            .limit(limit)
        ).all()
    )


def list_models_for_opportunity_assignment(session: Session, *, limit: int = 25) -> list[ModelBrand]:
    return list(
        session.scalars(
            select(ModelBrand)
            .where(ModelBrand.status != "archived")
            .order_by(ModelBrand.display_name, ModelBrand.id)
            .limit(limit)
        ).all()
    )


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
    priority: str = "normal",
    due_at: datetime | None = None,
    assigned_to_user_id: int | None = None,
    source_type: str | None = "manual",
    source_reference_id: int | None = None,
    reason: str | None = None,
    suggested_angle: str | None = None,
    source: OpportunitySource | None = None,
) -> Opportunity:
    _require_opportunity_access(session, actor)
    if platform not in OPPORTUNITY_PLATFORMS:
        raise ValueError(f"Invalid opportunity platform: {platform}")
    if priority not in OPPORTUNITY_PRIORITIES:
        raise ValueError(f"Invalid opportunity priority: {priority}")
    if source_type is not None and source_type not in OPPORTUNITY_SOURCE_TYPES:
        raise ValueError(f"Invalid opportunity source type: {source_type}")
    if assigned_to_user_id is not None:
        assignee = session.get(User, assigned_to_user_id)
        if assignee is None or assignee.status != USER_STATUS_ACTIVE or not assignee.is_active:
            raise PermissionError("Only active users can be assigned opportunities")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Opportunity title is required")
    opportunity = Opportunity(
        source_id=source.id if source else None,
        platform=platform,
        source_type=source_type,
        source_reference_id=source_reference_id,
        title=clean_title,
        url=url,
        niche=niche,
        model_brand_id=model_brand_id,
        score=0,
        priority=priority,
        status="discovered",
        reason=reason,
        suggested_angle=suggested_angle,
        assigned_to_user_id=assigned_to_user_id,
        assigned_at=_now() if assigned_to_user_id else None,
        due_at=due_at,
    )
    if assigned_to_user_id is not None:
        opportunity.status = "assigned"
    session.add(opportunity)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="opportunity.created",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={
            "platform": opportunity.platform,
            "priority": opportunity.priority,
            "source_type": opportunity.source_type,
            "assigned_to_user_id": opportunity.assigned_to_user_id,
            "posting": "manual_only",
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.created",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={
            "platform": opportunity.platform,
            "niche": opportunity.niche,
            "priority": opportunity.priority,
            "model_brand_id": opportunity.model_brand_id,
            "source_type": opportunity.source_type,
            "posting": "manual_only",
        },
    )
    if assigned_to_user_id is not None:
        emit_event(
            session,
            actor=actor,
            event_name="opportunity.assigned",
            resource_type="opportunity",
            resource_id=str(opportunity.id),
            payload={"assigned_to_user_id": assigned_to_user_id, "source": "intake"},
        )
    route_opportunity_notification(
        session,
        actor=actor,
        event_type="opportunity.high_priority" if priority in {"high", "critical"} else "opportunity.created",
        title="Opportunity Created",
        body=f"{opportunity.title} is ready for human review.",
        severity=priority if priority in {"high", "critical"} else None,
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
        priority="normal",
        reason="Created from Telegram for human review.",
        suggested_angle="Draft a human-approved outreach/comment angle before any posting.",
    )


def list_creator_watches(
    session: Session,
    *,
    active_only: bool = True,
    assigned_chatter: User | None = None,
    limit: int = 25,
) -> list[CreatorWatch]:
    statement = (
        select(CreatorWatch)
        .options(selectinload(CreatorWatch.assigned_model), selectinload(CreatorWatch.assigned_chatter))
        .order_by(desc(CreatorWatch.priority), desc(CreatorWatch.updated_at), CreatorWatch.creator_name)
        .limit(limit)
    )
    if active_only:
        statement = statement.where(CreatorWatch.is_active.is_(True))
    if assigned_chatter is not None:
        statement = statement.where(CreatorWatch.assigned_chatter_id == assigned_chatter.id)
    return list(session.scalars(statement).all())


def get_creator_watch(session: Session, creator_id: int) -> CreatorWatch | None:
    return session.scalar(
        select(CreatorWatch)
        .where(CreatorWatch.id == creator_id)
        .options(selectinload(CreatorWatch.assigned_model), selectinload(CreatorWatch.assigned_chatter))
    )


def create_creator_watch(
    session: Session,
    *,
    actor: User | None,
    platform: str,
    creator_name: str,
    creator_username: str,
    display_name: str | None = None,
    profile_url: str | None = None,
    niche: str | None = None,
    priority: str = "normal",
    assigned_model_id: int | None = None,
    assigned_team_id: int | None = None,
    assigned_chatter_id: int | None = None,
    notes: str | None = None,
) -> CreatorWatch:
    _require_opportunity_manage(session, actor)
    if platform not in CREATOR_WATCH_PLATFORMS:
        raise ValueError(f"Invalid creator platform: {platform}")
    if priority not in CREATOR_WATCH_PRIORITIES:
        raise ValueError(f"Invalid creator priority: {priority}")
    creator = CreatorWatch(
        platform=platform,
        creator_name=creator_name.strip() or "Creator",
        display_name=(display_name or creator_name).strip() or "Creator",
        creator_username=creator_username.strip() or "unknown",
        profile_url=profile_url,
        niche=niche,
        priority=priority,
        assigned_model_id=assigned_model_id,
        assigned_team_id=assigned_team_id,
        assigned_chatter_id=assigned_chatter_id,
        notes=notes,
        status="active",
        is_active=True,
    )
    session.add(creator)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="creator_watch.created",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        details={"platform": creator.platform, "priority": creator.priority, "niche": creator.niche},
    )
    emit_event(
        session,
        actor=actor,
        event_name="creator_watch.created",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        payload={"platform": creator.platform, "priority": creator.priority, "niche": creator.niche},
    )
    audit_action(
        session,
        actor=actor,
        action="creator.created",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        details={"platform": creator.platform, "priority": creator.priority, "niche": creator.niche},
    )
    emit_event(
        session,
        actor=actor,
        event_name="creator.created",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        payload={"platform": creator.platform, "priority": creator.priority, "niche": creator.niche},
    )
    route_opportunity_notification(
        session,
        actor=actor,
        event_type="creator.created",
        title="Creator Added",
        body=f"{creator.creator_name} was added to Creator Watch.",
        severity=creator.priority if creator.priority in {"high", "critical"} else None,
    )
    return creator


def update_creator_watch(
    session: Session,
    creator: CreatorWatch,
    *,
    actor: User | None,
    platform: str | None = None,
    creator_name: str | None = None,
    display_name: str | None = None,
    creator_username: str | None = None,
    profile_url: str | None = None,
    niche: str | None = None,
    priority: str | None = None,
    notes: str | None = None,
    status: str | None = None,
) -> CreatorWatch:
    _require_opportunity_manage(session, actor)
    changed: dict[str, str | None] = {}
    if platform is not None:
        if platform not in CREATOR_WATCH_PLATFORMS:
            raise ValueError(f"Invalid creator platform: {platform}")
        creator.platform = platform
        changed["platform"] = platform
    if creator_name is not None:
        creator.creator_name = creator_name.strip() or creator.creator_name
        changed["creator_name"] = creator.creator_name
    if display_name is not None:
        creator.display_name = display_name.strip() or creator.display_name
        changed["display_name"] = creator.display_name
    if creator_username is not None:
        creator.creator_username = creator_username.strip().lstrip("@") or creator.creator_username
        changed["creator_username"] = creator.creator_username
    if profile_url is not None:
        creator.profile_url = profile_url.strip() or None
        changed["profile_url"] = "set" if creator.profile_url else None
    if niche is not None:
        creator.niche = niche.strip() or None
        changed["niche"] = creator.niche
    if priority is not None:
        if priority not in CREATOR_WATCH_PRIORITIES:
            raise ValueError(f"Invalid creator priority: {priority}")
        old_priority = creator.priority
        creator.priority = priority
        changed["priority"] = priority
        if old_priority != priority:
            emit_event(
                session,
                actor=actor,
                event_name="creator.priority_changed",
                resource_type="creator_watch",
                resource_id=str(creator.id),
                payload={"from": old_priority, "to": priority},
            )
    if notes is not None:
        creator.notes = notes.strip() or None
        changed["notes"] = "set" if creator.notes else None
    if status is not None:
        if status not in CREATOR_WATCH_STATUSES:
            raise ValueError(f"Invalid creator status: {status}")
        creator.status = status
        creator.is_active = status == "active"
        changed["status"] = status
    creator.updated_at = _now()
    session.flush()
    if changed:
        audit_action(
            session,
            actor=actor,
            action="creator.updated",
            resource_type="creator_watch",
            resource_id=str(creator.id),
            details=changed,
        )
        emit_event(
            session,
            actor=actor,
            event_name="creator.updated",
            resource_type="creator_watch",
            resource_id=str(creator.id),
            payload=changed,
        )
    return creator


def create_default_creator_watch(session: Session, *, actor: User | None) -> CreatorWatch:
    next_number = session.scalar(select(func.count(CreatorWatch.id))) or 0
    return create_creator_watch(
        session,
        actor=actor,
        platform="x",
        creator_name=f"Creator Watch {next_number + 1}",
        creator_username=f"creator_watch_{next_number + 1}",
        niche="general",
        priority="normal",
        notes="Created from Telegram for human review.",
    )


def assign_creator_watch(
    session: Session,
    creator: CreatorWatch,
    *,
    actor: User | None,
    chatter: User | None = None,
    model_brand: ModelBrand | None = None,
    team_id: int | None = None,
) -> CreatorWatch:
    _require_opportunity_manage(session, actor)
    if chatter is not None:
        creator.assigned_chatter_id = chatter.id
    if model_brand is not None:
        creator.assigned_model_id = model_brand.id
    if team_id is not None:
        creator.assigned_team_id = team_id
    creator.updated_at = _now()
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="creator.assigned",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        details={
            "assigned_chatter_id": creator.assigned_chatter_id,
            "assigned_model_id": creator.assigned_model_id,
            "assigned_team_id": creator.assigned_team_id,
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name="creator.assigned",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        payload={"assigned_chatter_id": creator.assigned_chatter_id, "assigned_model_id": creator.assigned_model_id},
    )
    route_opportunity_notification(
        session,
        actor=actor,
        event_type="creator.assigned",
        title="Creator Assigned",
        body=f"{creator.creator_name} assignment changed.",
        severity=creator.priority if creator.priority in {"high", "critical"} else None,
    )
    return creator


def set_creator_watch_active(
    session: Session,
    creator: CreatorWatch,
    *,
    actor: User | None,
    is_active: bool,
    action: str = "creator_watch.disabled",
) -> CreatorWatch:
    _require_opportunity_manage(session, actor)
    creator.is_active = is_active
    if action.endswith("archived"):
        creator.status = "archived"
    elif is_active:
        creator.status = "active"
    else:
        creator.status = "disabled"
    creator.updated_at = _now()
    session.flush()
    audit_action(
        session,
        actor=actor,
        action=action,
        resource_type="creator_watch",
        resource_id=str(creator.id),
        details={"is_active": is_active},
    )
    emit_event(
        session,
        actor=actor,
        event_name=action,
        resource_type="creator_watch",
        resource_id=str(creator.id),
        payload={"is_active": is_active},
    )
    return creator


def list_post_watches(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 25,
) -> list[PostWatch]:
    statement = (
        select(PostWatch)
        .options(selectinload(PostWatch.model_brand), selectinload(PostWatch.account))
        .order_by(desc(PostWatch.created_at), desc(PostWatch.id))
        .limit(limit)
    )
    if status is not None:
        statement = statement.where(PostWatch.status == status)
    return list(session.scalars(statement).all())


def get_post_watch(session: Session, post_id: int) -> PostWatch | None:
    return session.scalar(
        select(PostWatch)
        .where(PostWatch.id == post_id)
        .options(selectinload(PostWatch.model_brand), selectinload(PostWatch.account))
    )


def create_post_watch(
    session: Session,
    *,
    actor: User | None,
    model_brand: ModelBrand,
    platform: str,
    post_reference: str,
    post_type: str = "other",
    account_id: int | None = None,
    status: str = "recent",
    attention_level: str = "monitor",
    assigned_chatter_id: int | None = None,
    assigned_team_id: int | None = None,
    notes: str | None = None,
) -> PostWatch:
    _require_opportunity_manage(session, actor)
    if platform not in POST_WATCH_PLATFORMS:
        raise ValueError(f"Invalid post watch platform: {platform}")
    if status not in POST_WATCH_STATUSES:
        raise ValueError(f"Invalid post watch status: {status}")
    if post_type not in POST_WATCH_TYPES:
        raise ValueError(f"Invalid post watch type: {post_type}")
    if attention_level not in POST_WATCH_ATTENTION_LEVELS:
        raise ValueError(f"Invalid post attention level: {attention_level}")
    if assigned_chatter_id is not None:
        assignee = session.get(User, assigned_chatter_id)
        if assignee is None or assignee.status != USER_STATUS_ACTIVE or not assignee.is_active:
            raise PermissionError("Only active users can be assigned post watches")
    post = PostWatch(
        model_brand_id=model_brand.id,
        platform=platform,
        account_id=account_id,
        post_reference=post_reference.strip() or "manual-post-reference",
        post_type=post_type.strip() or "other",
        status=status,
        attention_level=attention_level,
        assigned_chatter_id=assigned_chatter_id,
        assigned_team_id=assigned_team_id,
        notes=notes,
    )
    session.add(post)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="post_watch.created",
        resource_type="post_watch",
        resource_id=str(post.id),
        details={"platform": post.platform, "status": post.status, "model_brand_id": post.model_brand_id},
    )
    emit_event(
        session,
        actor=actor,
        event_name="post_watch.created",
        resource_type="post_watch",
        resource_id=str(post.id),
        payload={
            "platform": post.platform,
            "status": post.status,
            "attention_level": post.attention_level,
            "model_brand_id": post.model_brand_id,
        },
    )
    route_opportunity_notification(
        session,
        actor=actor,
        event_type="post_watch.created",
        title="Own Post Added",
        body=f"{post.post_reference} is now being watched.",
        severity="warning" if post.attention_level == "urgent" else None,
    )
    return post


def assign_post_watch(
    session: Session,
    post: PostWatch,
    *,
    actor: User | None,
    chatter: User | None = None,
    team_id: int | None = None,
) -> PostWatch:
    _require_opportunity_manage(session, actor)
    if chatter is not None:
        if chatter.status != USER_STATUS_ACTIVE or not chatter.is_active:
            raise PermissionError("Only active users can be assigned post watches")
        post.assigned_chatter_id = chatter.id
    if team_id is not None:
        post.assigned_team_id = team_id
    post.status = "assigned" if post.assigned_chatter_id or post.assigned_team_id else post.status
    post.updated_at = _now()
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="post_watch.assigned",
        resource_type="post_watch",
        resource_id=str(post.id),
        details={"assigned_chatter_id": post.assigned_chatter_id, "assigned_team_id": post.assigned_team_id},
    )
    emit_event(
        session,
        actor=actor,
        event_name="post_watch.assigned",
        resource_type="post_watch",
        resource_id=str(post.id),
        payload={"assigned_chatter_id": post.assigned_chatter_id, "assigned_team_id": post.assigned_team_id},
    )
    return post


def update_post_watch_status(
    session: Session,
    post: PostWatch,
    *,
    actor: User | None,
    status: str,
) -> PostWatch:
    _require_opportunity_manage(session, actor)
    if status not in POST_WATCH_STATUSES:
        raise ValueError(f"Invalid post watch status: {status}")
    old_status = post.status
    post.status = status
    post.updated_at = _now()
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="post_watch.status_changed",
        resource_type="post_watch",
        resource_id=str(post.id),
        details={"from": old_status, "to": status},
    )
    emit_event(
        session,
        actor=actor,
        event_name="post_watch.status_changed",
        resource_type="post_watch",
        resource_id=str(post.id),
        payload={"from": old_status, "to": status},
    )
    return post


def create_default_post_watch(session: Session, *, actor: User | None) -> PostWatch:
    _require_opportunity_manage(session, actor)
    model = session.scalar(select(ModelBrand).order_by(ModelBrand.id).limit(1))
    if model is None:
        model = ModelBrand(display_name="Default Model", stage_name="Default", status="active")
        session.add(model)
        session.flush()
    next_number = session.scalar(select(func.count(PostWatch.id))) or 0
    return create_post_watch(
        session,
        actor=actor,
        model_brand=model,
        platform="instagram",
        post_reference=f"manual-post-{next_number + 1}",
        post_type="other",
        status="recent",
        attention_level="monitor",
        notes="Created from Telegram for human tracking.",
    )


def _strategy_templates_for(opportunity: Opportunity) -> list[dict]:
    base_risk = 20
    if opportunity.url:
        base_risk += 5
    if opportunity.score >= 80:
        base_risk -= 5
    if opportunity.platform == "instagram":
        base_risk += 3
    niche = opportunity.niche or "this niche"
    title = opportunity.title[:80]
    return [
        {
            "angle": "curiosity",
            "tone": "warm curiosity",
            "sample_comment": f"This is interesting. What made you focus on {niche} right now?",
            "curiosity_score": 86,
            "engagement_score": _clamp_score(62 + opportunity.score // 5),
            "risk_score": _clamp_score(base_risk),
            "reasoning": f"Ask a simple, relevant question about {niche} to invite a human reply.",
            "why_it_might_work": "Questions invite a reply without sounding like a pitch.",
            "suggested_use_case": "Use when the creator post already has a clear topic or opinion.",
        },
        {
            "angle": "relatable",
            "tone": "friendly and grounded",
            "sample_comment": f"That part about {niche} feels very real. A lot of people miss that detail.",
            "curiosity_score": 54,
            "engagement_score": _clamp_score(60 + opportunity.score // 6),
            "risk_score": _clamp_score(base_risk - 5),
            "reasoning": "Connect to a specific point without pushing for anything.",
            "why_it_might_work": "Relatable comments feel natural and reduce spam risk.",
            "suggested_use_case": "Use when the creator shared a personal or observational post.",
        },
        {
            "angle": "question",
            "tone": "clear question",
            "sample_comment": f"Do you think {niche} is changing because of timing, audience taste, or both?",
            "curiosity_score": 78,
            "engagement_score": _clamp_score(58 + opportunity.score // 5),
            "risk_score": _clamp_score(base_risk + 1),
            "reasoning": "A direct question gives the creator an easy path to respond.",
            "why_it_might_work": "Specific questions outperform generic praise.",
            "suggested_use_case": "Use when you want a clean conversation starter.",
        },
        {
            "angle": "authority",
            "tone": "confident but not pushy",
            "sample_comment": f"The strongest {niche} posts usually make one point this clearly. This one does that well.",
            "curiosity_score": 45,
            "engagement_score": _clamp_score(56 + opportunity.score // 5),
            "risk_score": _clamp_score(base_risk + 7),
            "reasoning": "Offer one expert-style observation without pretending to have private data.",
            "why_it_might_work": "Authority can earn attention when it is specific and modest.",
            "suggested_use_case": "Use only when the comment can be genuinely specific.",
        },
        {
            "angle": "contrarian",
            "tone": "respectfully different",
            "sample_comment": f"I might see this slightly differently: the underrated part is the audience timing, not just {niche}.",
            "curiosity_score": 72,
            "engagement_score": _clamp_score(63 + opportunity.score // 5),
            "risk_score": _clamp_score(base_risk + 14),
            "reasoning": "A respectful counterpoint can create discussion, but should stay polite.",
            "why_it_might_work": "Contrarian angles stand out when they add substance.",
            "suggested_use_case": "Use sparingly on high-quality discussion posts.",
        },
        {
            "angle": "soft_cta",
            "tone": "gentle next step",
            "sample_comment": f"This could be a great thread on what people misunderstand about {niche}.",
            "curiosity_score": 57,
            "engagement_score": _clamp_score(59 + opportunity.score // 6),
            "risk_score": _clamp_score(base_risk + 10),
            "reasoning": "Suggest a next content idea without asking for a click or sale.",
            "why_it_might_work": "Soft calls to action help without feeling promotional.",
            "suggested_use_case": "Use when a creator seems open to expanding a topic.",
        },
        {
            "angle": "story",
            "tone": "short story",
            "sample_comment": f"This reminds me of when people first notice {niche}; the small details usually matter most.",
            "curiosity_score": 67,
            "engagement_score": _clamp_score(61 + opportunity.score // 5),
            "risk_score": _clamp_score(base_risk + 4),
            "reasoning": "A small story makes the comment feel human instead of templated.",
            "why_it_might_work": "Story-driven replies are easier to remember.",
            "suggested_use_case": "Use when the chatter can personalize it honestly.",
        },
        {
            "angle": "humor",
            "tone": "light humor",
            "sample_comment": f"The {niche} detail is doing more heavy lifting here than it gets credit for.",
            "curiosity_score": 52,
            "engagement_score": _clamp_score(64 + opportunity.score // 6),
            "risk_score": _clamp_score(base_risk + 8),
            "reasoning": "Light humor can be memorable when it stays safe and context-aware.",
            "why_it_might_work": "Playful wording can invite likes/replies without being aggressive.",
            "suggested_use_case": "Use only when the post tone is already casual.",
        },
        {
            "angle": "educational",
            "tone": "helpful and concise",
            "sample_comment": f"One reason {title or niche} works: it gives people a clear point to react to.",
            "curiosity_score": 64,
            "engagement_score": _clamp_score(50 + opportunity.score // 4),
            "risk_score": _clamp_score(base_risk + 2),
            "reasoning": "Share one useful idea without pitching, pushing, or automating engagement.",
            "why_it_might_work": "Useful context can position the team as thoughtful.",
            "suggested_use_case": "Use when the creator post is educational or analytical.",
        },
        {
            "angle": "supportive",
            "tone": "supportive",
            "sample_comment": f"This is a strong point. The {niche} angle feels especially clear here.",
            "curiosity_score": 48,
            "engagement_score": _clamp_score(53 + opportunity.score // 7),
            "risk_score": _clamp_score(base_risk - 6),
            "reasoning": "Supportive comments are safest when they name one concrete reason.",
            "why_it_might_work": "Low-risk support keeps the interaction natural.",
            "suggested_use_case": "Use for low-risk relationship building.",
        },
    ]


def comment_strategies_for_opportunity(
    session: Session,
    opportunity: Opportunity,
    *,
    actor: User | None = None,
    create_if_missing: bool = True,
) -> list[CommentStrategy]:
    strategies = list(
        session.scalars(
            select(CommentStrategy)
            .where(CommentStrategy.opportunity_id == opportunity.id)
            .order_by(CommentStrategy.risk_score, desc(CommentStrategy.engagement_score), CommentStrategy.id)
        ).all()
    )
    if strategies or not create_if_missing:
        return strategies
    for item in _strategy_templates_for(opportunity):
        session.add(CommentStrategy(opportunity_id=opportunity.id, **item))
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="comment_strategy.generated",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={"strategy_count": 3, "posting": "manual_only"},
    )
    return list(
        session.scalars(
            select(CommentStrategy)
            .where(CommentStrategy.opportunity_id == opportunity.id)
            .order_by(CommentStrategy.risk_score, desc(CommentStrategy.engagement_score), CommentStrategy.id)
        ).all()
    )


def regenerate_comment_strategies(
    session: Session,
    opportunity: Opportunity,
    *,
    actor: User | None,
) -> list[CommentStrategy]:
    _require_opportunity_view(session, actor)
    session.execute(delete(CommentStrategy).where(CommentStrategy.opportunity_id == opportunity.id))
    session.flush()
    strategies = comment_strategies_for_opportunity(session, opportunity, actor=actor, create_if_missing=True)
    audit_action(
        session,
        actor=actor,
        action="opportunity.strategy_generated",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"strategy_count": len(strategies), "posting": "manual_only"},
    )
    return strategies


def opportunity_queue_summary(session: Session, *, user: User | None = None) -> dict:
    statuses = ("discovered", "reviewing", "assigned", "completed", "rejected", "archived")
    counts = {
        status: session.scalar(select(func.count(Opportunity.id)).where(Opportunity.status == status)) or 0
        for status in statuses
    }
    top = list_opportunities(session, limit=5)
    assigned_query = select(Opportunity).where(Opportunity.status == "assigned")
    if user is not None and user_has_permission(user, "view_chatter_dashboard") and not user_has_permission(user, "manage_reports"):
        assigned_query = assigned_query.where(Opportunity.assigned_to_user_id == user.id)
    assigned = list(
        session.scalars(assigned_query.order_by(desc(Opportunity.score), desc(Opportunity.updated_at)).limit(5)).all()
    )
    unassigned = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.assigned_to_user_id.is_(None), Opportunity.status.in_(("discovered", "reviewing", "approved")))
            .order_by(desc(Opportunity.score), desc(Opportunity.updated_at))
            .limit(5)
        ).all()
    )
    high_priority = list(
        session.scalars(
            select(Opportunity)
            .where(
                (Opportunity.score >= 70) | (Opportunity.priority.in_(("high", "critical"))),
                Opportunity.status.not_in(("completed", "archived", "rejected")),
            )
            .order_by(desc(Opportunity.priority), desc(Opportunity.score), desc(Opportunity.updated_at))
            .limit(5)
        ).all()
    )
    recent_results = opportunity_results(session, limit=5)
    return {
        "counts": counts,
        "top": top,
        "assigned": assigned,
        "unassigned": unassigned,
        "high_priority": high_priority,
        "recent_results": recent_results,
    }


def chatter_workspace(session: Session, user: User) -> dict:
    assigned_opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.assigned_to_user_id == user.id)
            .order_by(desc(Opportunity.score), desc(Opportunity.updated_at))
            .limit(5)
        ).all()
    )
    assigned_tasks = list(
        session.scalars(
            select(Task)
            .where(Task.assigned_to_user_id == user.id, Task.status.in_(("open", "in_progress", "blocked")))
            .order_by(Task.due_at.is_(None), Task.due_at, desc(Task.priority))
            .limit(5)
        ).all()
    )
    assigned_model_ids = select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
    assigned_models = list(
        session.scalars(select(ModelBrand).where(ModelBrand.id.in_(assigned_model_ids)).order_by(ModelBrand.display_name).limit(5)).all()
    )
    recent_results = list(
        session.scalars(
            select(OpportunityResult)
            .where(OpportunityResult.posted_by_user_id == user.id)
            .order_by(desc(OpportunityResult.created_at), desc(OpportunityResult.id))
            .limit(5)
        ).all()
    )
    if assigned_opportunities:
        next_action = f"Review {assigned_opportunities[0].title} and choose a human-approved strategy."
    elif assigned_tasks:
        next_action = f"Work on task: {assigned_tasks[0].title}"
    else:
        next_action = "Check availability and wait for manager-assigned opportunities."
    return {
        "today_opportunities": assigned_opportunities[:3],
        "assigned_opportunities": assigned_opportunities,
        "opportunity_tabs": {
            "new": [item for item in assigned_opportunities if item.status == "assigned"],
            "in_progress": [item for item in assigned_opportunities if item.status == "reviewing"],
            "posted": [item for item in assigned_opportunities if item.status == "completed"],
            "needs_result": [item for item in assigned_opportunities if item.status in {"assigned", "reviewing"}],
            "completed": [item for item in assigned_opportunities if item.status == "completed"],
        },
        "assigned_models": assigned_models,
        "assigned_tasks": assigned_tasks,
        "recent_results": recent_results,
        "recommended_next_action": next_action,
    }


def manager_opportunity_view(session: Session) -> dict:
    queue = opportunity_queue_summary(session)
    results = opportunity_results(session, limit=20)
    angle_counts: dict[str, int] = {}
    chatter_counts: dict[str, int] = {}
    for result in results:
        opportunity = result.opportunity or session.get(Opportunity, result.opportunity_id)
        if opportunity is not None:
            angle = (opportunity.suggested_angle or "unknown")[:80]
            angle_counts[angle] = angle_counts.get(angle, 0) + (1 if result.status == "posted" else 0)
        if result.posted_by_user_id:
            user = session.get(User, result.posted_by_user_id)
            label = _identity(user)
            chatter_counts[label] = chatter_counts.get(label, 0) + 1
    now = _now()
    overdue = list(
        session.scalars(
            select(Opportunity)
            .where(
                Opportunity.due_at.is_not(None),
                Opportunity.due_at < now,
                Opportunity.status.not_in(("completed", "archived", "rejected")),
            )
            .order_by(Opportunity.due_at, desc(Opportunity.priority))
            .limit(10)
        ).all()
    )
    completed_today = list(
        session.scalars(
            select(Opportunity)
            .where(
                Opportunity.completed_at.is_not(None),
                Opportunity.completed_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
            )
            .order_by(desc(Opportunity.completed_at), desc(Opportunity.id))
            .limit(10)
        ).all()
    )
    by_model: dict[str, int] = {}
    by_niche: dict[str, int] = {}
    for opportunity in list_opportunities(session, include_archived=True, limit=200):
        model = session.get(ModelBrand, opportunity.model_brand_id) if opportunity.model_brand_id else None
        by_model[model.display_name if model else "Unassigned"] = by_model.get(model.display_name if model else "Unassigned", 0) + 1
        by_niche[opportunity.niche or "unknown"] = by_niche.get(opportunity.niche or "unknown", 0) + 1
    return {
        **queue,
        "overdue": overdue,
        "completed_today": completed_today,
        "by_model": sorted(by_model.items(), key=lambda item: item[1], reverse=True)[:5],
        "by_niche": sorted(by_niche.items(), key=lambda item: item[1], reverse=True)[:5],
        "top_angles": sorted(angle_counts.items(), key=lambda item: item[1], reverse=True)[:5],
        "most_active_chatters": sorted(chatter_counts.items(), key=lambda item: item[1], reverse=True)[:5],
    }


def opportunity_learning_overview(session: Session) -> dict:
    from app.services.learning import opportunity_learning_summary

    summary = opportunity_learning_summary(session)
    team_counts: dict[str, int] = {}
    results = opportunity_results(session, limit=200)
    for result in results:
        if result.status != "posted" or not result.posted_by_user_id:
            continue
        user = session.get(User, result.posted_by_user_id)
        team_counts[_identity(user)] = team_counts.get(_identity(user), 0) + 1
    return {**summary, "most_successful_teams": sorted(team_counts.items(), key=lambda item: item[1], reverse=True)[:5]}


def create_opportunity_from_creator(
    session: Session,
    creator: CreatorWatch,
    *,
    actor: User | None,
    title: str | None = None,
    url: str | None = None,
    assigned_to_user_id: int | None = None,
) -> Opportunity:
    opportunity = create_manual_opportunity(
        session,
        actor=actor,
        title=title or f"Engage with @{creator.creator_username}",
        platform=creator.platform,
        url=url or creator.profile_url,
        niche=creator.niche,
        model_brand_id=creator.assigned_model_id,
        priority=creator.priority,
        assigned_to_user_id=assigned_to_user_id or creator.assigned_chatter_id,
        source_type="creator_watch",
        source_reference_id=creator.id,
        reason=f"Created from creator watch: {creator.creator_name}",
        suggested_angle="Review creator context and choose a human-approved comment strategy.",
    )
    audit_action(
        session,
        actor=actor,
        action="opportunity.created_from_creator",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"creator_watch_id": creator.id},
    )
    return opportunity


def create_opportunity_from_post(
    session: Session,
    post: PostWatch,
    *,
    actor: User | None,
    title: str | None = None,
    assigned_to_user_id: int | None = None,
) -> Opportunity:
    priority = "critical" if post.attention_level == "urgent" else "high" if post.attention_level == "engage" else "normal"
    opportunity = create_manual_opportunity(
        session,
        actor=actor,
        title=title or f"Review own post: {post.post_reference[:80]}",
        platform=post.platform,
        url=post.post_reference if post.post_reference.startswith(("http://", "https://")) else None,
        niche=post.model_brand.stage_name or post.model_brand.display_name,
        model_brand_id=post.model_brand_id,
        priority=priority,
        assigned_to_user_id=assigned_to_user_id or post.assigned_chatter_id,
        source_type="own_post",
        source_reference_id=post.id,
        reason=f"Created from own post watch: {post.post_type}",
        suggested_angle="Review post context and decide whether human engagement is useful.",
    )
    audit_action(
        session,
        actor=actor,
        action="opportunity.created_from_post",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"post_watch_id": post.id},
    )
    return opportunity


def create_task_from_opportunity(
    session: Session,
    opportunity: Opportunity,
    *,
    actor: User,
    assignee: User | None = None,
) -> Task:
    from app.services.tasks import create_task

    model = session.get(ModelBrand, opportunity.model_brand_id) if opportunity.model_brand_id else None
    account: Account | None = None
    task = create_task(
        session,
        actor=actor,
        title=f"Work opportunity: {opportunity.title[:120]}",
        description=(
            "Review the opportunity, pick a human-approved strategy, perform any platform action manually, "
            "then record the result in Agency OS."
        ),
        priority="high" if opportunity.priority == "critical" else opportunity.priority,
        model_brand=model,
        account=account,
        assigned_to=assignee or opportunity.assigned_to,
        due_at=opportunity.due_at,
    )
    audit_action(
        session,
        actor=actor,
        action="opportunity.task_created",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"task_id": task.id},
    )
    return task


def activation_score(session: Session, user: User) -> dict:
    checklist = session.scalar(select(TeamOnboardingChecklist).where(TeamOnboardingChecklist.user_id == user.id))
    availability = get_or_create_availability(session, user)
    first_task_completed = (
        session.scalar(select(func.count(Task.id)).where(Task.assigned_to_user_id == user.id, Task.status == "complete")) or 0
    ) > 0
    first_opportunity_reviewed = (
        session.scalar(select(func.count(OpportunityResult.id)).where(OpportunityResult.posted_by_user_id == user.id)) or 0
    ) > 0
    checks = {
        "onboarding_complete": bool(checklist and checklist.onboarded),
        "availability_set": availability.status != "off_shift",
        "role_assigned": bool(user.roles),
        "timezone_confirmed": bool(user.timezone and user.timezone != "UTC"),
        "first_task_completed": first_task_completed,
        "first_opportunity_reviewed": first_opportunity_reviewed,
        "help_center_viewed": bool(checklist and checklist.help_center_viewed),
    }
    score = round((sum(1 for value in checks.values() if value) / len(checks)) * 100)
    return {"user": user, "score": score, "checks": checks}


def team_activation_summary(session: Session) -> list[dict]:
    users = list(session.scalars(select(User).options(selectinload(User.roles)).where(User.status == "active").order_by(User.display_name)).all())
    return sorted((activation_score(session, user) for user in users), key=lambda item: (item["score"], _identity(item["user"])))


def team_activation_qa(session: Session) -> list[dict]:
    users = list(
        session.scalars(
            select(User)
            .options(selectinload(User.roles), selectinload(User.availability))
            .order_by(User.status, User.display_name, User.id)
        ).all()
    )
    rows: list[dict] = []
    for user in users:
        role_names = {role.name for role in user.roles}
        assigned_tasks_count = session.scalar(
            select(func.count(Task.id)).where(Task.assigned_to_user_id == user.id, Task.status.in_(("open", "in_progress", "blocked")))
        ) or 0
        assigned_opportunities_count = session.scalar(
            select(func.count(Opportunity.id)).where(
                Opportunity.assigned_to_user_id == user.id,
                Opportunity.status.not_in(("completed", "archived", "rejected")),
            )
        ) or 0
        assigned_models_count = session.scalar(
            select(func.count(ModelBrandMember.model_brand_id)).where(ModelBrandMember.user_id == user.id)
        ) or 0
        flags: list[str] = []
        if user.status == "pending":
            flags.append("pending approval")
        if not user.roles:
            flags.append("needs role")
        if not user.timezone or user.timezone == "UTC":
            flags.append("needs timezone")
        if user.availability is None:
            flags.append("needs availability")
        if assigned_tasks_count == 0 and assigned_opportunities_count == 0:
            flags.append("no assigned work")
        if role_names.intersection({"Chatter", "Senior Chatter", "Chatter Manager"}):
            if assigned_models_count == 0:
                flags.append("chatter needs model")
            if assigned_opportunities_count == 0:
                flags.append("chatter needs opportunity")
        score = activation_score(session, user)["score"] if user.status == USER_STATUS_ACTIVE else 0
        rows.append(
            {
                "user": user,
                "score": score,
                "flags": flags,
                "assigned_tasks": assigned_tasks_count,
                "assigned_opportunities": assigned_opportunities_count,
                "assigned_models": assigned_models_count,
            }
        )
    return sorted(rows, key=lambda item: (item["score"], _identity(item["user"])))


def help_copilot_answer(
    session: Session,
    user: User | None,
    *,
    question: str,
    current_page: str | None = None,
) -> dict:
    role_names = {role.name for role in user.roles} if user is not None else set()
    question_text = question.lower()
    if "add" in question_text and "creator" in question_text:
        answer = "Open Opportunities -> Creator Watchlist -> Add Creator, then follow the guided steps for platform, username, niche, priority, and assignment."
        next_action = "opportunities:creators:add"
    elif "assign" in question_text and "opportun" in question_text:
        answer = "Open Opportunity Detail, tap Assign Chatter, choose the teammate, and Agency OS will make it visible in their workspace."
        next_action = "opportunities:command"
    elif "where" in question_text and "opportun" in question_text:
        answer = "Chatters use My Opportunities. Managers use Opportunities -> Command Center or Manager View."
        next_action = "my_opportunities" if "Chatter" in role_names or "Senior Chatter" in role_names else "opportunities:command"
    elif "access" in question_text or "can't" in question_text or "cant" in question_text:
        answer = "Access depends on your role and permissions. Ask a manager to check Team Activation, role assignment, and whether your account is approved."
        next_action = "help"
    elif "what should i do next" in question_text or "next" in question_text:
        if "Chatter" in role_names or "Senior Chatter" in role_names:
            answer = "Start with Chatter Workspace, review assigned opportunities, then choose a suggested strategy and record the result after manual action."
            next_action = "chatter_workspace"
        else:
            answer = "Start with the Command Center, clear high-priority unassigned opportunities, then check Team Activation."
            next_action = "opportunities:command"
    elif "record" in question_text and "result" in question_text:
        answer = "Open the opportunity, tap Record Result, choose Posted, Skipped, Rejected, or Failed, then add safe notes and optional clicks/conversions."
        next_action = "my_opportunities"
    elif "opportun" in question_text:
        if "Chatter" in role_names or "Senior Chatter" in role_names:
            answer = "Open My Opportunities, pick the assigned item, review the suggested strategies, then record the human result."
            next_action = "my_opportunities"
        else:
            answer = "Use Opportunities Command Center to review, assign, and track opportunities. Posting stays human-approved."
            next_action = "opportunities:command"
    elif "task" in question_text:
        answer = "Open My Tasks, start the task when you begin, and mark it complete when the work is done."
        next_action = "tasks:my"
    elif "availability" in question_text or "shift" in question_text:
        answer = "Use Availability to show whether you are on shift, away, or unavailable so routing stays fair."
        next_action = "availability"
    elif "where" in question_text:
        answer = "Use your home screen first. It only shows the areas that matter for your role."
        next_action = "menu"
    else:
        answer = "Tell Agency OS what you are trying to do, then use the suggested next action. Managers can use Team Activation to see who needs help."
        next_action = current_page or "help"
    audit_action(
        session,
        actor=user,
        action="help_copilot.answered",
        resource_type="help",
        details={"question": question[:120], "next_action": next_action},
    )
    return {"answer": answer, "next_action": next_action, "role": ", ".join(sorted(role_names)) or "Viewer"}


def route_opportunity_notification(
    session: Session,
    *,
    actor: User | None,
    event_type: str,
    title: str,
    body: str,
    severity: str | None = None,
) -> list[NotificationDeliveryAttempt]:
    targets = active_targets_for_event(session, event_type, severity=severity)
    attempts: list[NotificationDeliveryAttempt] = []
    for target in targets:
        attempts.append(
            create_delivery_attempt(
                session,
                target,
                event_type=event_type,
                actor=actor,
                status="pending",
                metadata=sanitize_details({"title": title, "body": body, "severity": severity}),
            )
        )
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.notification_routed",
        resource_type="notification",
        resource_id=event_type,
        payload={"target_count": len(attempts), "event_type": event_type},
    )
    return attempts


def _opportunity_memory_adjustment(session: Session, opportunity: Opportunity) -> int:
    terms = [
        term
        for term in (
            opportunity.niche,
            opportunity.suggested_angle,
            str(opportunity.source_id) if opportunity.source_id else None,
        )
        if term
    ]
    if not terms:
        return 0
    memories = list(
        session.scalars(
            select(OutcomeMemory).where(OutcomeMemory.memory_type == "opportunity_result").order_by(desc(OutcomeMemory.last_seen_at))
        ).all()
    )
    adjustment = 0
    for memory in memories:
        haystack = " ".join(
            str(value)
            for value in (
                memory.memory_key,
                memory.summary,
                (memory.metadata_json or {}).get("last_summary"),
                (memory.metadata_json or {}).get("last_event_type"),
            )
            if value
        ).lower()
        if any(term.lower() in haystack for term in terms):
            if memory.success_rate >= 70:
                adjustment += 5
            elif memory.failure_count > memory.success_count:
                adjustment -= 5
    return max(-10, min(10, adjustment))


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
        score += _opportunity_memory_adjustment(session, opportunity)
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
    opportunity.assigned_at = _now()
    opportunity.updated_at = _now()
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="opportunity.assigned",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"assigned_to_user_id": assignee.id},
    )
    emit_event(
        session,
        actor=actor,
        event_name="opportunity.assigned",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={"assigned_to_user_id": assignee.id},
    )
    route_opportunity_notification(
        session,
        actor=actor,
        event_type="opportunity.assigned",
        title="Opportunity Assigned",
        body=f"{opportunity.title} assigned to {_identity(assignee)}.",
        severity=opportunity.priority if opportunity.priority in {"high", "critical"} else None,
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
    if status == "completed":
        opportunity.completed_at = _now()
    opportunity.updated_at = _now()
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="opportunity.status_changed",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"from": old_status, "to": status},
    )
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
    reason: str | None = None,
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
        reason=reason,
        notes=notes,
    )
    session.add(result)
    if status == "posted":
        opportunity.status = "completed"
        opportunity.completed_at = _now()
    elif status == "rejected":
        opportunity.status = "rejected"
    elif status in {"skipped", "failed"}:
        opportunity.status = "reviewing"
    opportunity.updated_at = _now()
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="opportunity.result_recorded",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details=sanitize_details(
            {
                "result_id": result.id,
                "status": result.status,
                "clicks": clicks,
                "conversions": conversions,
                "reason": reason,
                "posting": "manual_record_only",
            }
        ),
    )
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
                "reason": reason,
                "posting": "manual_record_only",
            }
        ),
    )
    if status == "posted":
        emit_event(
            session,
            actor=actor,
            event_name="opportunity.completed",
            resource_type="opportunity",
            resource_id=str(opportunity.id),
            payload={"result_id": result.id, "posting": "manual_record_only"},
        )
    route_opportunity_notification(
        session,
        actor=actor,
        event_type="opportunity.result_recorded",
        title="Opportunity Result Recorded",
        body=f"{opportunity.title}: {status}",
        severity="warning" if status == "failed" else None,
    )
    from app.services.learning import capture_opportunity_result

    capture_opportunity_result(session, result, actor=actor)
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
