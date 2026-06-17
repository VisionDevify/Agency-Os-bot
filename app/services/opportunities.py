from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.learning import OutcomeMemory
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import (
    CREATOR_WATCH_PLATFORMS,
    CREATOR_WATCH_PRIORITIES,
    POST_WATCH_PLATFORMS,
    POST_WATCH_STATUSES,
    CommentStrategy,
    CreatorWatch,
    OPPORTUNITY_PLATFORMS,
    OPPORTUNITY_RESULT_STATUSES,
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
from app.services.auth import audit_action, user_has_permission
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
        creator_username=creator_username.strip() or "unknown",
        profile_url=profile_url,
        niche=niche,
        priority=priority,
        assigned_model_id=assigned_model_id,
        assigned_team_id=assigned_team_id,
        assigned_chatter_id=assigned_chatter_id,
        notes=notes,
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
        action="creator_watch.assigned",
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
        event_name="creator_watch.assigned",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        payload={"assigned_chatter_id": creator.assigned_chatter_id, "assigned_model_id": creator.assigned_model_id},
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
    post_type: str = "post",
    account_id: int | None = None,
    status: str = "recent",
    notes: str | None = None,
) -> PostWatch:
    _require_opportunity_manage(session, actor)
    if platform not in POST_WATCH_PLATFORMS:
        raise ValueError(f"Invalid post watch platform: {platform}")
    if status not in POST_WATCH_STATUSES:
        raise ValueError(f"Invalid post watch status: {status}")
    post = PostWatch(
        model_brand_id=model_brand.id,
        platform=platform,
        account_id=account_id,
        post_reference=post_reference.strip() or "manual-post-reference",
        post_type=post_type.strip() or "post",
        status=status,
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
        payload={"platform": post.platform, "status": post.status, "model_brand_id": post.model_brand_id},
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
        post_type="post",
        status="recent",
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
    return [
        {
            "angle": "curiosity",
            "tone": "warm curiosity",
            "curiosity_score": 86,
            "engagement_score": _clamp_score(62 + opportunity.score // 5),
            "risk_score": _clamp_score(base_risk),
            "reasoning": f"Ask a simple, relevant question about {niche} to invite a human reply.",
        },
        {
            "angle": "agreement",
            "tone": "friendly agreement",
            "curiosity_score": 58,
            "engagement_score": _clamp_score(55 + opportunity.score // 6),
            "risk_score": _clamp_score(base_risk - 4),
            "reasoning": "Affirm a specific point first, then add one short human observation.",
        },
        {
            "angle": "educational",
            "tone": "helpful and concise",
            "curiosity_score": 64,
            "engagement_score": _clamp_score(50 + opportunity.score // 4),
            "risk_score": _clamp_score(base_risk + 2),
            "reasoning": "Share one useful idea without pitching, pushing, or automating engagement.",
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
            .where(Opportunity.score >= 70, Opportunity.status.not_in(("completed", "archived", "rejected")))
            .order_by(desc(Opportunity.score), desc(Opportunity.updated_at))
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
    return {
        **queue,
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
        "first_task_completed": first_task_completed,
        "first_opportunity_reviewed": first_opportunity_reviewed,
        "help_center_viewed": bool(checklist and checklist.help_center_viewed),
    }
    score = round((sum(1 for value in checks.values() if value) / len(checks)) * 100)
    return {"user": user, "score": score, "checks": checks}


def team_activation_summary(session: Session) -> list[dict]:
    users = list(session.scalars(select(User).options(selectinload(User.roles)).where(User.status == "active").order_by(User.display_name)).all())
    return sorted((activation_score(session, user) for user in users), key=lambda item: (item["score"], _identity(item["user"])))


def help_copilot_answer(
    session: Session,
    user: User | None,
    *,
    question: str,
    current_page: str | None = None,
) -> dict:
    role_names = {role.name for role in user.roles} if user is not None else set()
    question_text = question.lower()
    if "opportun" in question_text:
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
    elif status == "rejected":
        opportunity.status = "rejected"
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
