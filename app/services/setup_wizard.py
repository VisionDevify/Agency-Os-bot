from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import CommentStrategy, CreatorWatch, Opportunity, OpportunityResult, PostWatch
from app.models.task import Task
from app.models.team_rollout import FirstDayChecklist, SetupWizardState
from app.models.user import User
from app.services.accounts import create_account
from app.services.auth import USER_STATUS_PENDING, audit_action, user_has_permission
from app.services.events import emit_event
from app.services.model_brands import assign_model_member, create_model_brand, update_model_brand
from app.services.opportunities import (
    comment_strategies_for_opportunity,
    create_creator_watch,
    create_manual_opportunity,
    create_opportunity_from_creator,
)
from app.services.team_experience import get_or_create_onboarding_checklist

FIRST_DAY_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("created_first_model", "Create first model", "setup:wizard"),
    ("added_accounts", "Add IG/X/OF accounts", "setup:wizard:accounts"),
    ("assigned_manager", "Assign manager", "setup:wizard:team"),
    ("assigned_team", "Assign chatters/VAs", "setup:wizard:team"),
    ("added_creators", "Add top creators to watch", "setup:wizard:creators"),
    ("created_opportunities", "Create first opportunities", "setup:wizard:opportunities"),
    ("assigned_opportunities", "Assign opportunities", "opportunities:manager"),
    ("generated_briefing", "Generate daily briefing", "reports:daily"),
    ("reviewed_activation", "Review team activation", "team_activation"),
    ("checked_production", "Check production status", "production_status"),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _require_setup_access(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_accounts") or user_has_permission(actor, "manage_users"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="setup_wizard",
        status="denied",
        details={"permission": "manage_accounts_or_manage_users"},
    )
    raise PermissionError("Setup Wizard requires Owner/Admin setup permissions")


def _score_checklist(checklist: FirstDayChecklist) -> int:
    fields = [field for field, _, _ in FIRST_DAY_ITEMS]
    completed = sum(1 for field in fields if getattr(checklist, field))
    return int(completed / len(fields) * 100)


def get_or_create_first_day_checklist(session: Session, user: User) -> FirstDayChecklist:
    checklist = session.scalar(select(FirstDayChecklist).where(FirstDayChecklist.user_id == user.id))
    if checklist is None:
        checklist = FirstDayChecklist(user_id=user.id)
        session.add(checklist)
        session.flush()
    sync_first_day_checklist(session, checklist)
    return checklist


def sync_first_day_checklist(session: Session, checklist: FirstDayChecklist) -> FirstDayChecklist:
    checklist.created_first_model = checklist.created_first_model or (
        (session.scalar(select(func.count(ModelBrand.id)).where(ModelBrand.is_demo.is_(False))) or 0) > 0
    )
    checklist.added_accounts = checklist.added_accounts or (
        (session.scalar(select(func.count(Account.id)).where(Account.is_demo.is_(False))) or 0) > 0
    )
    checklist.added_creators = checklist.added_creators or (
        (session.scalar(select(func.count(CreatorWatch.id)).where(CreatorWatch.is_demo.is_(False))) or 0) > 0
    )
    checklist.created_opportunities = checklist.created_opportunities or (
        (session.scalar(select(func.count(Opportunity.id)).where(Opportunity.is_demo.is_(False))) or 0) > 0
    )
    checklist.assigned_opportunities = checklist.assigned_opportunities or (
        (
            session.scalar(
                select(func.count(Opportunity.id)).where(
                    Opportunity.assigned_to_user_id.is_not(None),
                    Opportunity.is_demo.is_(False),
                )
            )
            or 0
        )
        > 0
    )
    checklist.assigned_manager = checklist.assigned_manager or (
        (
            session.scalar(
                select(func.count(ModelBrandMember.user_id)).where(ModelBrandMember.relationship_type == "manager")
            )
            or 0
        )
        > 0
    )
    checklist.assigned_team = checklist.assigned_team or (
        (
            session.scalar(
                select(func.count(ModelBrandMember.user_id)).where(
                    ModelBrandMember.relationship_type.in_(("chatter_manager", "senior_chatter", "chatter", "va"))
                )
            )
            or 0
        )
        > 0
    )
    checklist.completion_score = _score_checklist(checklist)
    session.flush()
    return checklist


def mark_first_day_item(session: Session, user: User, *, item: str, actor: User) -> FirstDayChecklist:
    _require_setup_access(session, actor)
    valid = {field for field, _, _ in FIRST_DAY_ITEMS}
    if item not in valid:
        raise ValueError(f"Invalid first-day item: {item}")
    checklist = get_or_create_first_day_checklist(session, user)
    setattr(checklist, item, True)
    checklist.completion_score = _score_checklist(checklist)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="first_day.item_completed",
        resource_type="first_day_checklist",
        resource_id=str(checklist.id),
        details={"item": item, "completion_score": checklist.completion_score},
    )
    return checklist


def first_day_plan(session: Session, user: User) -> dict:
    checklist = get_or_create_first_day_checklist(session, user)
    return {
        "checklist": checklist,
        "items": [
            {
                "key": field,
                "label": label,
                "page": page,
                "done": bool(getattr(checklist, field)),
            }
            for field, label, page in FIRST_DAY_ITEMS
        ],
        "completion_score": checklist.completion_score,
    }


def latest_setup_state(session: Session, actor: User) -> SetupWizardState | None:
    return session.scalar(
        select(SetupWizardState)
        .where(SetupWizardState.owner_user_id == actor.id)
        .order_by(SetupWizardState.updated_at.desc(), SetupWizardState.id.desc())
        .limit(1)
    )


def start_setup_wizard(session: Session, *, actor: User) -> SetupWizardState:
    _require_setup_access(session, actor)
    state = SetupWizardState(
        owner_user_id=actor.id,
        status="started",
        current_step="model",
        summary_json={},
        missing_items_json=["model", "accounts", "team", "creators", "opportunities"],
    )
    session.add(state)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="setup.started",
        resource_type="setup_wizard",
        resource_id=str(state.id),
        payload={"current_step": state.current_step},
    )
    return state


def summarize_setup_state(session: Session, state: SetupWizardState | None) -> dict:
    model = state.model_brand if state and state.model_brand_id else None
    model_id = model.id if model else None
    accounts = (
        session.scalar(select(func.count(Account.id)).where(Account.model_brand_id == model_id))
        if model_id
        else 0
    ) or 0
    team = (
        session.scalar(select(func.count(ModelBrandMember.user_id)).where(ModelBrandMember.model_brand_id == model_id))
        if model_id
        else 0
    ) or 0
    creators = (
        session.scalar(select(func.count(CreatorWatch.id)).where(CreatorWatch.assigned_model_id == model_id))
        if model_id
        else 0
    ) or 0
    opportunities = (
        session.scalar(select(func.count(Opportunity.id)).where(Opportunity.model_brand_id == model_id))
        if model_id
        else 0
    ) or 0
    missing = []
    if model is None:
        missing.append("model")
    if accounts == 0:
        missing.append("accounts")
    if team == 0:
        missing.append("team")
    if creators == 0:
        missing.append("creators")
    if opportunities == 0:
        missing.append("opportunities")
    return {
        "model": model,
        "accounts": accounts,
        "team": team,
        "creators": creators,
        "opportunities": opportunities,
        "missing": missing,
    }


def create_setup_model(
    session: Session,
    *,
    actor: User,
    display_name: str,
    stage_name: str | None = None,
    country: str | None = None,
    timezone: str | None = None,
    primary_platform: str | None = None,
    notes: str | None = None,
    state: SetupWizardState | None = None,
    is_demo: bool = False,
) -> ModelBrand:
    _require_setup_access(session, actor)
    model = create_model_brand(
        session,
        actor=actor,
        display_name=display_name,
        stage_name=stage_name,
        country=country,
        timezone=timezone,
        primary_platform=primary_platform,
        notes=notes,
        internal_notes="Created through Setup Wizard." if not is_demo else "Demo record created by owner.",
        is_demo=is_demo,
    )
    if state is not None:
        state.model_brand_id = model.id
        state.status = "in_progress"
        state.current_step = "accounts"
        state.summary_json = {**(state.summary_json or {}), "model_id": model.id}
        state.missing_items_json = summarize_setup_state(session, state)["missing"]
    checklist = get_or_create_first_day_checklist(session, actor)
    checklist.created_first_model = True
    checklist.completion_score = _score_checklist(checklist)
    audit_action(
        session,
        actor=actor,
        action="setup.model_created",
        resource_type="model_brand",
        resource_id=str(model.id),
        details={"wizard_state_id": state.id if state else None, "is_demo": is_demo},
    )
    return model


def update_setup_model_profile(
    session: Session,
    model: ModelBrand,
    *,
    actor: User,
    display_name: str | None = None,
    stage_name: str | None = None,
    country: str | None = None,
    timezone: str | None = None,
    primary_platform: str | None = None,
    notes: str | None = None,
    status: str | None = None,
    internal_notes: str | None = None,
) -> ModelBrand:
    _require_setup_access(session, actor)
    updated = update_model_brand(
        session,
        model,
        actor=actor,
        display_name=display_name,
        stage_name=stage_name,
        country=country,
        timezone=timezone,
        primary_platform=primary_platform,
        notes=notes,
        status=status,
        internal_notes=internal_notes,
    )
    audit_action(
        session,
        actor=actor,
        action="model.profile_updated",
        resource_type="model_brand",
        resource_id=str(model.id),
        details={
            "display_name": bool(display_name is not None),
            "stage_name": bool(stage_name is not None),
            "country": bool(country is not None),
            "timezone": bool(timezone is not None),
            "primary_platform": bool(primary_platform is not None),
            "notes": bool(notes is not None),
            "status": status,
        },
    )
    return updated


def add_setup_account(
    session: Session,
    *,
    actor: User,
    model: ModelBrand,
    platform: str,
    username: str,
    display_name: str | None = None,
    account_url: str | None = None,
    notes: str | None = None,
    state: SetupWizardState | None = None,
    is_demo: bool = False,
) -> Account:
    _require_setup_access(session, actor)
    account = create_account(
        session,
        actor=actor,
        model_brand=model,
        platform=platform,
        username=username,
        display_name=display_name,
        account_url=account_url,
        notes=notes,
        is_demo=is_demo,
    )
    if state is not None:
        state.current_step = "team"
        state.summary_json = {**(state.summary_json or {}), "last_account_id": account.id}
        state.missing_items_json = summarize_setup_state(session, state)["missing"]
    checklist = get_or_create_first_day_checklist(session, actor)
    checklist.added_accounts = True
    checklist.completion_score = _score_checklist(checklist)
    audit_action(
        session,
        actor=actor,
        action="setup.account_added",
        resource_type="account",
        resource_id=str(account.id),
        details={"model_brand_id": model.id, "platform": platform, "is_demo": is_demo},
    )
    return account


def assign_setup_team_member(
    session: Session,
    *,
    actor: User,
    model: ModelBrand,
    target_user: User,
    relationship_type: str,
    state: SetupWizardState | None = None,
) -> ModelBrandMember:
    _require_setup_access(session, actor)
    member = assign_model_member(session, model, target_user, relationship_type, actor=actor)
    if state is not None:
        state.current_step = "creators"
        state.summary_json = {**(state.summary_json or {}), "last_team_user_id": target_user.id}
        state.missing_items_json = summarize_setup_state(session, state)["missing"]
    checklist = get_or_create_first_day_checklist(session, actor)
    if relationship_type == "manager":
        checklist.assigned_manager = True
    if relationship_type in {"chatter_manager", "senior_chatter", "chatter", "va"}:
        checklist.assigned_team = True
    checklist.completion_score = _score_checklist(checklist)
    audit_action(
        session,
        actor=actor,
        action="setup.team_assigned",
        resource_type="model_brand",
        resource_id=str(model.id),
        details={"target_user_id": target_user.id, "relationship_type": relationship_type},
    )
    return member


def add_setup_creator(
    session: Session,
    *,
    actor: User,
    model: ModelBrand,
    platform: str,
    username: str,
    display_name: str,
    niche: str | None = None,
    priority: str = "normal",
    assigned_chatter_id: int | None = None,
    state: SetupWizardState | None = None,
    is_demo: bool = False,
) -> CreatorWatch:
    _require_setup_access(session, actor)
    creator = create_creator_watch(
        session,
        actor=actor,
        platform=platform,
        creator_name=display_name,
        display_name=display_name,
        creator_username=username,
        niche=niche,
        priority=priority,
        assigned_model_id=model.id,
        assigned_chatter_id=assigned_chatter_id,
        notes="Starter creator from Setup Wizard." if not is_demo else "Demo creator.",
        is_demo=is_demo,
    )
    if state is not None:
        state.current_step = "opportunities"
        state.summary_json = {**(state.summary_json or {}), "last_creator_id": creator.id}
        state.missing_items_json = summarize_setup_state(session, state)["missing"]
    checklist = get_or_create_first_day_checklist(session, actor)
    checklist.added_creators = True
    checklist.completion_score = _score_checklist(checklist)
    audit_action(
        session,
        actor=actor,
        action="setup.creator_added",
        resource_type="creator_watch",
        resource_id=str(creator.id),
        details={"model_brand_id": model.id, "priority": priority, "is_demo": is_demo},
    )
    return creator


def add_setup_opportunity(
    session: Session,
    *,
    actor: User,
    model: ModelBrand,
    title: str,
    platform: str = "x",
    niche: str | None = None,
    assigned_to_user_id: int | None = None,
    creator: CreatorWatch | None = None,
    state: SetupWizardState | None = None,
    is_demo: bool = False,
) -> Opportunity:
    _require_setup_access(session, actor)
    if creator is not None:
        opportunity = create_opportunity_from_creator(session, creator, actor=actor)
        opportunity.title = title
        opportunity.model_brand_id = model.id
        opportunity.is_demo = is_demo
        if assigned_to_user_id is not None:
            opportunity.assigned_to_user_id = assigned_to_user_id
            opportunity.assigned_at = _now()
            opportunity.status = "assigned"
    else:
        opportunity = create_manual_opportunity(
            session,
            actor=actor,
            title=title,
            platform=platform,
            niche=niche,
            model_brand_id=model.id,
            assigned_to_user_id=assigned_to_user_id,
            reason="Starter opportunity from Setup Wizard.",
            suggested_angle="Review strategies and take all platform action manually.",
            is_demo=is_demo,
        )
    comment_strategies_for_opportunity(session, opportunity, actor=actor)
    if state is not None:
        state.current_step = "summary"
        state.summary_json = {**(state.summary_json or {}), "last_opportunity_id": opportunity.id}
        state.missing_items_json = summarize_setup_state(session, state)["missing"]
    checklist = get_or_create_first_day_checklist(session, actor)
    checklist.created_opportunities = True
    checklist.assigned_opportunities = checklist.assigned_opportunities or assigned_to_user_id is not None
    checklist.completion_score = _score_checklist(checklist)
    audit_action(
        session,
        actor=actor,
        action="setup.opportunity_created",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"model_brand_id": model.id, "assigned": assigned_to_user_id is not None, "is_demo": is_demo},
    )
    return opportunity


def complete_setup_wizard(session: Session, state: SetupWizardState, *, actor: User) -> SetupWizardState:
    _require_setup_access(session, actor)
    summary = summarize_setup_state(session, state)
    state.status = "completed"
    state.current_step = "complete"
    state.summary_json = {
        "model_id": summary["model"].id if summary["model"] else None,
        "accounts": summary["accounts"],
        "team": summary["team"],
        "creators": summary["creators"],
        "opportunities": summary["opportunities"],
    }
    state.missing_items_json = summary["missing"]
    state.completed_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="setup.completed",
        resource_type="setup_wizard",
        resource_id=str(state.id),
        payload={"missing": state.missing_items_json, **state.summary_json},
    )
    return state


def manager_setup_qa(session: Session) -> dict:
    models = list(
        session.scalars(
            select(ModelBrand)
            .where(ModelBrand.status != "archived")
            .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
            .order_by(ModelBrand.id)
        ).all()
    )
    models_without_manager = []
    models_without_chatters = []
    for model in models:
        relationships = {member.relationship_type for member in model.members}
        if "manager" not in relationships:
            models_without_manager.append(model)
        if not relationships.intersection({"chatter_manager", "senior_chatter", "chatter"}):
            models_without_chatters.append(model)
    users = list(session.scalars(select(User).options(selectinload(User.roles), selectinload(User.availability))).all())
    users_without_timezone = [user for user in users if not user.timezone or user.timezone == "UTC"]
    users_without_role = [user for user in users if not user.roles]
    users_pending = [user for user in users if user.status == USER_STATUS_PENDING]
    users_not_onboarded = []
    for user in users:
        checklist = get_or_create_onboarding_checklist(session, user)
        if not checklist.onboarded:
            users_not_onboarded.append(user)
    return {
        "models_without_manager": models_without_manager,
        "models_without_chatters": models_without_chatters,
        "accounts_without_model": list(session.scalars(select(Account).where(Account.model_brand_id.is_(None))).all()),
        "opportunities_without_assignee": list(
            session.scalars(
                select(Opportunity)
                .where(Opportunity.assigned_to_user_id.is_(None), Opportunity.status != "archived")
                .order_by(Opportunity.priority.desc(), Opportunity.id)
            ).all()
        ),
        "tasks_without_owner": list(
            session.scalars(
                select(Task).where(Task.owner_user_id.is_(None), Task.status != "archived").order_by(Task.id)
            ).all()
        ),
        "users_pending": users_pending,
        "users_without_timezone": users_without_timezone,
        "users_without_role": users_without_role,
        "users_not_onboarded": users_not_onboarded,
    }


def placeholder_cleanup_summary(session: Session) -> dict:
    placeholder_models = list(
        session.scalars(
            select(ModelBrand)
            .where(
                ModelBrand.is_demo.is_(False),
                ModelBrand.status != "archived",
                ModelBrand.display_name.in_(("New Model 1", "Untitled Model", "Default Model")),
            )
            .order_by(ModelBrand.id)
        ).all()
    )
    placeholder_opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(
                Opportunity.is_demo.is_(False),
                Opportunity.status != "archived",
                Opportunity.model_brand_id.is_(None),
                Opportunity.title.in_(("Manual Opportunity 1", "Untitled Opportunity", "Default Opportunity")),
            )
            .order_by(Opportunity.id)
        ).all()
    )
    demo_counts = {
        "models": session.query(ModelBrand).filter(ModelBrand.is_demo.is_(True)).count(),
        "accounts": session.query(Account).filter(Account.is_demo.is_(True)).count(),
        "creators": session.query(CreatorWatch).filter(CreatorWatch.is_demo.is_(True)).count(),
        "opportunities": session.query(Opportunity).filter(Opportunity.is_demo.is_(True)).count(),
        "posts": session.query(PostWatch).filter(PostWatch.is_demo.is_(True)).count(),
    }
    return {
        "placeholder_models": placeholder_models,
        "placeholder_opportunities": placeholder_opportunities,
        "demo_counts": demo_counts,
        "has_placeholders": bool(placeholder_models or placeholder_opportunities),
        "has_demo": any(demo_counts.values()),
    }


def archive_placeholder_records(session: Session, *, actor: User) -> dict:
    _require_setup_access(session, actor)
    summary = placeholder_cleanup_summary(session)
    for model in summary["placeholder_models"]:
        model.status = "archived"
    for opportunity in summary["placeholder_opportunities"]:
        opportunity.status = "archived"
    counts = {
        "models_archived": len(summary["placeholder_models"]),
        "opportunities_archived": len(summary["placeholder_opportunities"]),
    }
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="placeholder.archived",
        resource_type="setup_cleanup",
        details=counts,
    )
    emit_event(
        session,
        actor=actor,
        event_name="placeholder.archived",
        resource_type="setup_cleanup",
        payload=counts,
    )
    return counts


def create_demo_seed(session: Session, *, actor: User) -> dict:
    _require_setup_access(session, actor)
    model = create_setup_model(
        session,
        actor=actor,
        display_name="Demo Model",
        stage_name="Demo Stage",
        country="United States",
        timezone="America/New_York",
        notes="Demo data for learning the UI.",
        is_demo=True,
    )
    account = add_setup_account(
        session,
        actor=actor,
        model=model,
        platform="instagram",
        username="demo_model",
        display_name="Demo Model IG",
        notes="Demo account. Do not use for production.",
        is_demo=True,
    )
    creator = add_setup_creator(
        session,
        actor=actor,
        model=model,
        platform="x",
        username="demo_creator",
        display_name="Demo Creator",
        niche="lifestyle",
        priority="normal",
        is_demo=True,
    )
    opportunity = add_setup_opportunity(
        session,
        actor=actor,
        model=model,
        title="Demo opportunity for guided workflow testing",
        platform="x",
        niche="lifestyle",
        creator=creator,
        is_demo=True,
    )
    audit_action(
        session,
        actor=actor,
        action="demo.created",
        resource_type="demo_seed",
        details={
            "model_id": model.id,
            "account_id": account.id,
            "creator_id": creator.id,
            "opportunity_id": opportunity.id,
        },
    )
    return {"model": model, "account": account, "creator": creator, "opportunity": opportunity}


def clear_demo_data(session: Session, *, actor: User) -> dict:
    _require_setup_access(session, actor)
    demo_opportunity_ids = select(Opportunity.id).where(Opportunity.is_demo.is_(True))
    demo_model_ids = select(ModelBrand.id).where(ModelBrand.is_demo.is_(True))
    counts = {
        "strategies": session.query(CommentStrategy).filter(CommentStrategy.opportunity_id.in_(demo_opportunity_ids)).count(),
        "results": session.query(OpportunityResult).filter(OpportunityResult.opportunity_id.in_(demo_opportunity_ids)).count(),
        "opportunities": session.query(Opportunity).filter(Opportunity.is_demo.is_(True)).count(),
        "posts": session.query(PostWatch).filter(PostWatch.is_demo.is_(True)).count(),
        "creators": session.query(CreatorWatch).filter(CreatorWatch.is_demo.is_(True)).count(),
        "accounts": session.query(Account).filter(Account.is_demo.is_(True)).count(),
        "models": session.query(ModelBrand).filter(ModelBrand.is_demo.is_(True)).count(),
    }
    session.execute(delete(CommentStrategy).where(CommentStrategy.opportunity_id.in_(demo_opportunity_ids)))
    session.execute(delete(OpportunityResult).where(OpportunityResult.opportunity_id.in_(demo_opportunity_ids)))
    session.execute(delete(Opportunity).where(Opportunity.is_demo.is_(True)))
    session.execute(delete(PostWatch).where(PostWatch.is_demo.is_(True)))
    session.execute(delete(CreatorWatch).where(CreatorWatch.is_demo.is_(True)))
    session.execute(delete(Account).where(Account.is_demo.is_(True)))
    session.execute(delete(ModelBrandMember).where(ModelBrandMember.model_brand_id.in_(demo_model_ids)))
    session.execute(delete(ModelBrand).where(ModelBrand.is_demo.is_(True)))
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="demo.cleared",
        resource_type="demo_seed",
        details=counts,
    )
    return counts
