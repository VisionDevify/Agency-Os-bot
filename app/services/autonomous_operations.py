from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.autonomous_operations import FollowUp, OperationsAction, OperationsWorkflow
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import CreatorWatch, Opportunity
from app.models.user import User
from app.services.agency_activation import run_activation_scan
from app.services.auth import USER_STATUS_ACTIVE, user_has_permission
from app.services.events import emit_event
from app.services.permissions import RoleName
from app.services.recommendations import generate_recommendations, upsert_recommendation
from app.services.system_truth import reconcile_stale_system_warnings

def _now() -> datetime:
    return datetime.now(UTC)


def _source_id(value: int | str) -> str:
    return str(value)


def _workflow_status(actions: list[OperationsAction]) -> str:
    if not actions:
        return "completed"
    if any(action.status in {"ready", "pending", "running"} for action in actions):
        return "ready"
    if any(action.status == "blocked" for action in actions):
        return "blocked"
    if any(action.status == "failed" for action in actions):
        return "failed"
    return "completed"


def get_or_create_workflow(
    session: Session,
    *,
    workflow_type: str,
    source_type: str,
    source_id: int | str,
    actor: User | None = None,
) -> OperationsWorkflow:
    workflow = session.scalar(
        select(OperationsWorkflow)
        .where(
            OperationsWorkflow.workflow_type == workflow_type,
            OperationsWorkflow.source_type == source_type,
            OperationsWorkflow.source_id == _source_id(source_id),
            OperationsWorkflow.status.in_(("pending", "ready", "running", "blocked")),
        )
        .options(selectinload(OperationsWorkflow.actions))
        .order_by(desc(OperationsWorkflow.updated_at), desc(OperationsWorkflow.id))
        .limit(1)
    )
    if workflow is None:
        workflow = OperationsWorkflow(
            workflow_type=workflow_type,
            source_type=source_type,
            source_id=_source_id(source_id),
            status="pending",
        )
        session.add(workflow)
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name="operations.workflow.created",
            resource_type="operations_workflow",
            resource_id=str(workflow.id),
            payload={"workflow_type": workflow_type, "source_type": source_type, "source_id": _source_id(source_id)},
        )
    return workflow


def add_or_update_action(
    session: Session,
    workflow: OperationsWorkflow,
    *,
    action_type: str,
    status: str,
    priority: str = "normal",
    assigned_user: User | None = None,
    result_summary: str | None = None,
) -> OperationsAction:
    action = session.scalar(
        select(OperationsAction)
        .where(OperationsAction.workflow_id == workflow.id, OperationsAction.action_type == action_type)
        .order_by(desc(OperationsAction.updated_at), desc(OperationsAction.id))
        .limit(1)
    )
    if action is None:
        action = OperationsAction(
            workflow_id=workflow.id,
            action_type=action_type,
            status=status,
            priority=priority,
            assigned_user_id=assigned_user.id if assigned_user else None,
            result_summary=result_summary,
        )
        session.add(action)
    elif action.status != "completed":
        action.status = status
        action.priority = priority
        action.assigned_user_id = assigned_user.id if assigned_user else action.assigned_user_id
        action.result_summary = result_summary
        action.updated_at = _now()
    session.flush()
    return action


def finalize_workflow(session: Session, workflow: OperationsWorkflow) -> OperationsWorkflow:
    actions = list(
        session.scalars(
            select(OperationsAction).where(OperationsAction.workflow_id == workflow.id).order_by(OperationsAction.id)
        ).all()
    )
    workflow.status = _workflow_status(actions)
    workflow.updated_at = _now()
    session.flush()
    return workflow


def _role_user(session: Session, role_names: tuple[str, ...]) -> User | None:
    users = list(
        session.scalars(
            select(User)
            .where(User.status == USER_STATUS_ACTIVE, User.is_active.is_(True))
            .options(selectinload(User.roles))
            .order_by(User.is_owner.desc(), User.id)
        ).all()
    )
    for user in users:
        names = {role.name for role in user.roles}
        if user.is_owner or names.intersection(role_names):
            return user
    return None


def _model_member_for(session: Session, model_id: int | None, relationship_types: tuple[str, ...]) -> User | None:
    if model_id is None:
        return None
    member = session.scalar(
        select(ModelBrandMember)
        .where(
            ModelBrandMember.model_brand_id == model_id,
            ModelBrandMember.relationship_type.in_(relationship_types),
        )
        .options(selectinload(ModelBrandMember.user))
        .limit(1)
    )
    if member and member.user.status == USER_STATUS_ACTIVE and member.user.is_active:
        return member.user
    return None


def owner_attention_user(session: Session) -> User | None:
    return _role_user(session, (RoleName.OWNER.value,))


def route_operations_action(
    session: Session,
    action_type: str,
    *,
    model_brand_id: int | None = None,
    opportunity: Opportunity | None = None,
) -> User | None:
    if action_type in {"critical_incident", "owner_approval", "high_risk_proxy_action"}:
        return owner_attention_user(session)
    if action_type in {"assign_proxy", "test_proxy_health", "proxy_repair"}:
        return _role_user(session, (RoleName.ADMIN.value, RoleName.MANAGER.value))
    if action_type in {"assign_manager", "assign_chatter", "assign_team"}:
        return _role_user(session, (RoleName.MANAGER.value, RoleName.ADMIN.value))
    if action_type in {"complete_auth_setup", "review_account_health"}:
        return _model_member_for(session, model_brand_id, ("manager", "chatter_manager")) or _role_user(
            session,
            (RoleName.MANAGER.value, RoleName.ADMIN.value),
        )
    if action_type in {"opportunity_follow_up", "record_opportunity_result"} and opportunity is not None:
        if opportunity.assigned_to_user_id:
            return session.get(User, opportunity.assigned_to_user_id)
        return _model_member_for(session, opportunity.model_brand_id, ("chatter_manager", "senior_chatter", "chatter"))
    return _role_user(session, (RoleName.MANAGER.value, RoleName.ADMIN.value)) or owner_attention_user(session)


def create_follow_up(
    session: Session,
    *,
    source_type: str,
    source_id: int | str,
    due_at: datetime,
    assigned_user: User | None = None,
) -> FollowUp:
    follow_up = session.scalar(
        select(FollowUp)
        .where(
            FollowUp.source_type == source_type,
            FollowUp.source_id == _source_id(source_id),
            FollowUp.status == "pending",
        )
        .order_by(desc(FollowUp.due_at), desc(FollowUp.id))
        .limit(1)
    )
    if follow_up is None:
        follow_up = FollowUp(
            source_type=source_type,
            source_id=_source_id(source_id),
            due_at=due_at,
            assigned_user_id=assigned_user.id if assigned_user else None,
            status="pending",
        )
        session.add(follow_up)
        session.flush()
        emit_event(
            session,
            actor=assigned_user,
            event_name="follow_up.created",
            resource_type=source_type,
            resource_id=_source_id(source_id),
            payload={"due_at": due_at.isoformat(), "assigned_user_id": assigned_user.id if assigned_user else None},
        )
    return follow_up


def run_account_autopilot(session: Session, account: Account, *, actor: User | None) -> OperationsWorkflow:
    workflow = get_or_create_workflow(
        session,
        workflow_type="account_autopilot",
        source_type="account",
        source_id=account.id,
        actor=actor,
    )
    model = account.model_brand if account.model_brand_id else None
    add_or_update_action(
        session,
        workflow,
        action_type="check_model_assignment",
        status="completed" if account.model_brand_id else "ready",
        priority="high" if not account.model_brand_id else "normal",
        result_summary="Model assignment checked.",
    )
    proxy_assignee = route_operations_action(session, "assign_proxy", model_brand_id=account.model_brand_id)
    proxy_missing = account.assigned_proxy_id is None
    add_or_update_action(
        session,
        workflow,
        action_type="assign_proxy",
        status="ready" if proxy_missing else "completed",
        priority="high" if proxy_missing else "normal",
        assigned_user=proxy_assignee,
        result_summary="Proxy assignment needed." if proxy_missing else "Proxy already assigned.",
    )
    if proxy_missing:
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="account_missing_proxy_autopilot",
            title=f"Assign proxy to {account.platform.title()} @{account.username}",
            description="This account cannot be considered ready until a proxy is assigned.",
            severity="warning",
            entity_type="account",
            entity_id=account.id,
            metadata={"source": "account_autopilot"},
        )
    auth_assignee = route_operations_action(session, "complete_auth_setup", model_brand_id=account.model_brand_id)
    auth_incomplete = account.auth_status != "connected"
    add_or_update_action(
        session,
        workflow,
        action_type="complete_auth_setup",
        status="ready" if auth_incomplete else "completed",
        priority="high" if auth_incomplete else "normal",
        assigned_user=auth_assignee,
        result_summary="Secure auth setup is still incomplete." if auth_incomplete else "Auth status is connected.",
    )
    manager_missing = bool(model and not any(member.relationship_type == "manager" for member in model.members))
    va_missing = bool(model and not any(member.relationship_type == "va" for member in model.members))
    add_or_update_action(
        session,
        workflow,
        action_type="check_manager_assignment",
        status="ready" if manager_missing else "completed",
        priority="normal",
        assigned_user=route_operations_action(session, "assign_manager", model_brand_id=account.model_brand_id),
        result_summary="Manager assignment needed." if manager_missing else "Manager check passed.",
    )
    add_or_update_action(
        session,
        workflow,
        action_type="check_va_assignment",
        status="ready" if va_missing else "completed",
        priority="low",
        assigned_user=route_operations_action(session, "assign_team", model_brand_id=account.model_brand_id),
        result_summary="VA assignment may be useful." if va_missing else "VA check passed.",
    )
    ready = bool(account.model_brand_id and not proxy_missing and not auth_incomplete and account.status == "healthy")
    add_or_update_action(
        session,
        workflow,
        action_type="confirm_account_readiness",
        status="completed" if ready else "blocked",
        priority="normal",
        result_summary="Account ready." if ready else "Account has setup blockers.",
    )
    if not ready:
        create_follow_up(
            session,
            source_type="account",
            source_id=account.id,
            due_at=_now() + timedelta(days=1),
            assigned_user=auth_assignee or proxy_assignee,
        )
    emit_event(
        session,
        actor=actor,
        event_name="autopilot.account_analyzed",
        resource_type="account",
        resource_id=str(account.id),
        payload={"ready": ready, "workflow_id": workflow.id},
    )
    return finalize_workflow(session, workflow)


def run_model_autopilot(session: Session, model: ModelBrand, *, actor: User | None) -> OperationsWorkflow:
    workflow = get_or_create_workflow(
        session,
        workflow_type="model_autopilot",
        source_type="model_brand",
        source_id=model.id,
        actor=actor,
    )
    checks = {
        "set_country": bool(model.country),
        "set_timezone": bool(model.timezone),
        "set_primary_platform": bool(model.primary_platform),
        "assign_manager": any(member.relationship_type == "manager" for member in model.members),
        "assign_chatter_team": any(
            member.relationship_type in {"chatter_manager", "senior_chatter", "chatter"} for member in model.members
        ),
    }
    for action_type, passed in checks.items():
        add_or_update_action(
            session,
            workflow,
            action_type=action_type,
            status="completed" if passed else "ready",
            priority="high" if action_type in {"assign_manager", "assign_chatter_team"} and not passed else "normal",
            assigned_user=route_operations_action(session, action_type, model_brand_id=model.id),
            result_summary="Ready." if passed else "Missing setup item.",
        )
    if not all(checks.values()):
        create_follow_up(
            session,
            source_type="model_brand",
            source_id=model.id,
            due_at=_now() + timedelta(days=1),
            assigned_user=route_operations_action(session, "assign_manager", model_brand_id=model.id),
        )
    if actor is not None and (user_has_permission(actor, "manage_accounts") or user_has_permission(actor, "manage_users")):
        run_activation_scan(session, actor=actor, create_tasks=False)
    emit_event(
        session,
        actor=actor,
        event_name="autopilot.model_analyzed",
        resource_type="model_brand",
        resource_id=str(model.id),
        payload={"workflow_id": workflow.id, "missing_count": sum(1 for passed in checks.values() if not passed)},
    )
    return finalize_workflow(session, workflow)


def run_opportunity_autopilot(session: Session, opportunity: Opportunity, *, actor: User | None) -> OperationsWorkflow:
    from app.services.opportunities import comment_strategies_for_opportunity, score_opportunity

    workflow = get_or_create_workflow(
        session,
        workflow_type="opportunity_autopilot",
        source_type="opportunity",
        source_id=opportunity.id,
        actor=actor,
    )
    if actor is not None:
        try:
            score_opportunity(session, opportunity, actor=actor)
            strategies = comment_strategies_for_opportunity(session, opportunity, actor=actor)
            generated_summary = f"Generated score {opportunity.score} and {len(strategies)} strategy options."
            generated_status = "completed"
        except PermissionError:
            generated_summary = "Strategy generation skipped due to permissions."
            generated_status = "skipped"
    else:
        generated_summary = "Strategy generation skipped because no actor was available."
        generated_status = "skipped"
    add_or_update_action(
        session,
        workflow,
        action_type="generate_strategy_and_score",
        status=generated_status,
        priority="normal",
        result_summary=generated_summary,
    )
    assignee = route_operations_action(session, "opportunity_follow_up", opportunity=opportunity)
    add_or_update_action(
        session,
        workflow,
        action_type="recommend_assignee",
        status="completed" if opportunity.assigned_to_user_id else "ready",
        priority="high" if opportunity.priority in {"high", "critical"} else "normal",
        assigned_user=assignee,
        result_summary="Opportunity has an assignee." if opportunity.assigned_to_user_id else "Assignee recommendation prepared.",
    )
    add_or_update_action(
        session,
        workflow,
        action_type="track_result",
        status="ready" if opportunity.status not in {"completed", "rejected", "archived"} else "completed",
        priority="normal",
        assigned_user=assignee,
        result_summary="Follow up until a human result is recorded.",
    )
    if opportunity.status not in {"completed", "rejected", "archived"}:
        create_follow_up(
            session,
            source_type="opportunity",
            source_id=opportunity.id,
            due_at=opportunity.due_at or _now() + timedelta(days=1),
            assigned_user=assignee,
        )
    emit_event(
        session,
        actor=actor,
        event_name="autopilot.opportunity_analyzed",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload={"workflow_id": workflow.id, "score": opportunity.score},
    )
    return finalize_workflow(session, workflow)


def run_creator_autopilot(session: Session, creator: CreatorWatch, *, actor: User | None) -> OperationsWorkflow:
    workflow = get_or_create_workflow(
        session,
        workflow_type="creator_autopilot",
        source_type="creator_watch",
        source_id=creator.id,
        actor=actor,
    )
    assignee = (
        session.get(User, creator.assigned_chatter_id)
        if creator.assigned_chatter_id
        else route_operations_action(session, "opportunity_follow_up", model_brand_id=creator.assigned_model_id)
    )
    checks = [
        ("build_watch_profile", bool(creator.creator_username and creator.niche), "Create a clean creator profile."),
        ("validate_niche", bool(creator.niche), "Confirm niche so opportunity scoring has context."),
        ("suggest_assignee", bool(creator.assigned_chatter_id), "Suggest a chatter or manager owner."),
        ("suggest_opportunity_bucket", bool(creator.assigned_model_id), "Connect this creator to a model/brand."),
        ("suggest_strategy_category", True, "Start with low-risk human-approved strategy categories."),
    ]
    for action_type, passed, summary in checks:
        add_or_update_action(
            session,
            workflow,
            action_type=action_type,
            status="completed" if passed else "ready",
            priority="high" if creator.priority in {"high", "critical"} and not passed else "normal",
            assigned_user=assignee,
            result_summary=summary,
        )
    upsert_recommendation(
        session,
        actor=actor,
        recommendation_type="creator_watch_autopilot",
        title=f"Review creator watch profile for {creator.creator_name}",
        description="Fortuna OS prepared the next setup actions for this creator watch item.",
        severity="warning" if creator.priority in {"high", "critical"} else "info",
        entity_type="creator_watch",
        entity_id=creator.id,
        metadata={"source": "creator_autopilot", "priority": creator.priority},
    )
    emit_event(
        session,
        actor=actor,
        event_name="autopilot.creator_analyzed",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        payload={"workflow_id": workflow.id},
    )
    return finalize_workflow(session, workflow)


def run_readiness_autopilot(session: Session, *, actor: User) -> OperationsWorkflow:
    workflow = get_or_create_workflow(
        session,
        workflow_type="readiness_autopilot",
        source_type="agency_activation",
        source_id="global",
        actor=actor,
    )
    state = run_activation_scan(session, actor=actor, create_tasks=True)
    add_or_update_action(
        session,
        workflow,
        action_type="update_readiness_score",
        status="completed",
        priority="normal",
        result_summary=f"Readiness is {state.readiness_score}%.",
    )
    add_or_update_action(
        session,
        workflow,
        action_type="route_setup_gaps",
        status="ready" if state.readiness_score < 85 else "completed",
        priority="high" if state.readiness_score < 60 else "normal",
        assigned_user=owner_attention_user(session) if state.readiness_score < 60 else route_operations_action(session, "assign_team"),
        result_summary="Setup blockers routed to the right owner.",
    )
    emit_event(
        session,
        actor=actor,
        event_name="autopilot.readiness_analyzed",
        resource_type="agency_activation",
        resource_id=str(state.id),
        payload={"readiness_score": state.readiness_score, "workflow_id": workflow.id},
    )
    return finalize_workflow(session, workflow)


def run_daily_autonomous_cycle(session: Session, *, actor: User) -> OperationsWorkflow:
    workflow = get_or_create_workflow(
        session,
        workflow_type="daily_autonomous_cycle",
        source_type="system",
        source_id=_now().date().isoformat(),
        actor=actor,
    )
    steps = [
        ("truth_reconciliation", lambda: reconcile_stale_system_warnings(session, actor=actor)),
        ("readiness_scan", lambda: run_readiness_autopilot(session, actor=actor)),
        ("recommendation_refresh", lambda: generate_recommendations(session, actor=actor)),
    ]
    for action_type, fn in steps:
        try:
            fn()
            status = "completed"
            summary = f"{action_type.replace('_', ' ').title()} completed."
        except Exception as exc:  # pragma: no cover - defensive status capture
            status = "failed"
            summary = str(exc)[:240]
        add_or_update_action(
            session,
            workflow,
            action_type=action_type,
            status=status,
            priority="normal",
            assigned_user=owner_attention_user(session) if status == "failed" else None,
            result_summary=summary,
        )
    emit_event(
        session,
        actor=actor,
        event_name="autopilot.daily_cycle.completed",
        resource_type="operations_workflow",
        resource_id=str(workflow.id),
        payload={"workflow_id": workflow.id},
    )
    return finalize_workflow(session, workflow)


def recent_operations_activity(session: Session, *, limit: int = 5) -> list[str]:
    actions = list(
        session.scalars(
            select(OperationsAction)
            .options(selectinload(OperationsAction.workflow))
            .order_by(desc(OperationsAction.updated_at), desc(OperationsAction.id))
            .limit(limit)
        ).all()
    )
    return [
        f"Fortuna OS {action.status}: {action.action_type.replace('_', ' ')}"
        for action in actions
    ]


def outstanding_blockers(session: Session, *, limit: int = 5) -> list[str]:
    actions = list(
        session.scalars(
            select(OperationsAction)
            .where(OperationsAction.status.in_(("ready", "blocked", "failed")))
            .order_by(desc(OperationsAction.priority), desc(OperationsAction.updated_at))
            .limit(limit)
        ).all()
    )
    return [
        f"{action.priority.title()}: {action.action_type.replace('_', ' ')}"
        for action in actions
    ]
