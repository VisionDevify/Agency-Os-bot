from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import CreatorWatch, Opportunity
from app.models.reporting import NotificationTarget
from app.models.task import Task
from app.models.team_rollout import ActivationBlockerDecision, AgencyActivationState
from app.models.user import User
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.events import emit_event
from app.services.recommendations import upsert_recommendation
from app.services.tasks import create_task


EXPECTED_NOTIFICATION_PURPOSES = ("owner", "operations", "incidents", "automation_logs", "testing")
ACTIVE_TASK_STATUSES = ("open", "in_progress", "blocked")
TEAM_RELATIONSHIP_TYPES = ("manager", "chatter_manager", "senior_chatter", "chatter", "va", "viewer")
CHATTER_RELATIONSHIP_TYPES = ("chatter_manager", "senior_chatter", "chatter")


@dataclass(frozen=True)
class ActivationGap:
    code: str
    title: str
    description: str
    severity: str
    section: str
    entity_type: str | None = None
    entity_id: int | None = None
    action_page: str | None = None
    task_title: str | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "section": self.section,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action_page": self.action_page,
        }


@dataclass(frozen=True)
class AccountSetupState:
    account_id: int
    platform: str
    username: str
    model_name: str
    status: str
    checklist: list[str]
    recommended_actions: list[str]


def _now() -> datetime:
    return datetime.now(UTC)


def activation_gap_key(gap: ActivationGap | dict) -> tuple[str, str, str]:
    if isinstance(gap, ActivationGap):
        code = gap.code
        entity_type = gap.entity_type or ""
        entity_id = str(gap.entity_id or "")
    else:
        code = str(gap.get("code") or "")
        entity_type = str(gap.get("entity_type") or "")
        entity_id = str(gap.get("entity_id") or "")
    return code, entity_type, entity_id


def activation_gap_key_string(gap: ActivationGap | dict) -> str:
    return "|".join(activation_gap_key(gap))


def _blocker_decisions(session: Session) -> dict[tuple[str, str, str], str]:
    rows = session.scalars(select(ActivationBlockerDecision)).all()
    return {
        (row.blocker_code, row.entity_type or "", row.entity_id or ""): row.status
        for row in rows
    }


def set_activation_blocker_decision(
    session: Session,
    blocker: ActivationGap | dict,
    *,
    actor: User,
    status: str,
    reason: str | None = None,
) -> ActivationBlockerDecision:
    if status not in {"skipped", "not_needed"}:
        raise ValueError(f"Invalid blocker decision: {status}")
    code, entity_type, entity_id = activation_gap_key(blocker)
    decision = session.scalar(
        select(ActivationBlockerDecision).where(
            ActivationBlockerDecision.blocker_code == code,
            ActivationBlockerDecision.entity_type == entity_type,
            ActivationBlockerDecision.entity_id == entity_id,
        )
    )
    if decision is None:
        decision = ActivationBlockerDecision(
            blocker_code=code,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            decided_by_user_id=actor.id,
        )
        session.add(decision)
    decision.status = status
    decision.reason = reason
    decision.decided_by_user_id = actor.id
    session.flush()
    audit_action(
        session,
        actor=actor,
        action=f"activation.blocker_{status}",
        resource_type=entity_type or "agency_activation",
        resource_id=entity_id or code,
        details={"blocker_code": code, "status": status},
    )
    emit_event(
        session,
        actor=actor,
        event_name=f"activation.blocker_{status}",
        resource_type=entity_type or "agency_activation",
        resource_id=entity_id or code,
        payload={"blocker_code": code, "status": status},
    )
    return decision


def _percent(ready: int, total: int) -> int:
    if total <= 0:
        return 0
    return round((ready / total) * 100)


def _active_models(session: Session) -> list[ModelBrand]:
    return list(
        session.scalars(
            select(ModelBrand)
            .where(ModelBrand.status != "archived", ModelBrand.is_demo.is_(False))
            .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
            .order_by(ModelBrand.id)
        ).all()
    )


def _active_accounts(session: Session) -> list[Account]:
    return list(
        session.scalars(
            select(Account)
            .where(Account.status != "archived", Account.is_demo.is_(False))
            .options(selectinload(Account.model_brand), selectinload(Account.assigned_proxy))
            .order_by(Account.id)
        ).all()
    )


def _active_creators(session: Session) -> list[CreatorWatch]:
    return list(
        session.scalars(
            select(CreatorWatch)
            .where(CreatorWatch.status != "archived", CreatorWatch.is_demo.is_(False))
            .order_by(CreatorWatch.id)
        ).all()
    )


def _active_opportunities(session: Session) -> list[Opportunity]:
    return list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.status != "archived", Opportunity.is_demo.is_(False))
            .order_by(Opportunity.id)
        ).all()
    )


def _section_scores(
    *,
    models: list[ModelBrand],
    accounts: list[Account],
    creators: list[CreatorWatch],
    opportunities: list[Opportunity],
    active_notification_purposes: set[str],
) -> dict[str, int]:
    model_total = len(models) * 4
    model_ready = sum(
        int(bool(model.country))
        + int(bool(model.timezone))
        + int(bool(model.primary_platform))
        + int(model.status == "active")
        for model in models
    )

    account_total = len(accounts) * 4
    account_ready = sum(
        int(bool(account.model_brand_id))
        + int(bool(account.assigned_proxy_id))
        + int(account.auth_status == "connected")
        + int(account.status == "healthy")
        for account in accounts
    )

    team_total = len(models) * 2
    team_ready = 0
    for model in models:
        relationship_types = {member.relationship_type for member in model.members}
        team_ready += int("manager" in relationship_types)
        team_ready += int(bool(relationship_types.intersection(CHATTER_RELATIONSHIP_TYPES)))

    creator_ready = _percent(
        len({creator.assigned_model_id for creator in creators if creator.assigned_model_id}),
        len(models),
    )
    opportunity_ready = _percent(
        len({opportunity.model_brand_id for opportunity in opportunities if opportunity.model_brand_id}),
        len(models),
    )
    notification_ready = _percent(
        len(active_notification_purposes.intersection(EXPECTED_NOTIFICATION_PURPOSES)),
        len(EXPECTED_NOTIFICATION_PURPOSES),
    )

    return {
        "models_ready": _percent(model_ready, model_total),
        "accounts_ready": _percent(account_ready, account_total),
        "teams_ready": _percent(team_ready, team_total),
        "creators_ready": creator_ready,
        "opportunities_ready": opportunity_ready,
        "notifications_ready": notification_ready,
    }


def _build_model_gaps(
    models: list[ModelBrand],
    accounts: list[Account],
    creators: list[CreatorWatch],
    opportunities: list[Opportunity],
) -> list[ActivationGap]:
    gaps: list[ActivationGap] = []
    accounts_by_model = {model.id: 0 for model in models}
    creators_by_model = {model.id: 0 for model in models}
    opportunities_by_model = {model.id: 0 for model in models}
    for account in accounts:
        if account.model_brand_id in accounts_by_model:
            accounts_by_model[account.model_brand_id] += 1
    for creator in creators:
        if creator.assigned_model_id in creators_by_model:
            creators_by_model[creator.assigned_model_id] += 1
    for opportunity in opportunities:
        if opportunity.model_brand_id in opportunities_by_model:
            opportunities_by_model[opportunity.model_brand_id] += 1

    if not models:
        return [
            ActivationGap(
                code="model.none",
                title="Create your first model/brand",
                description="Fortuna OS needs one model or brand before accounts, creators, and opportunities can connect.",
                severity="critical",
                section="models",
                action_page="setup:wizard:model",
                task_title="Create first model/brand",
            )
        ]

    for model in models:
        label = model.display_name
        model_page = f"model:{model.id}:complete"
        if not model.country:
            gaps.append(
                ActivationGap(
                    code="model.missing_country",
                    title=f"{label}: country missing",
                    description="Add the model country so schedules, reporting, and team context make sense.",
                    severity="warning",
                    section="models",
                    entity_type="model",
                    entity_id=model.id,
                    action_page=model_page,
                    task_title=f"Configure country for {label}",
                )
            )
        if not model.timezone:
            gaps.append(
                ActivationGap(
                    code="model.missing_timezone",
                    title=f"{label}: timezone missing",
                    description="Add the model timezone so task timing and daily operations are clear.",
                    severity="warning",
                    section="models",
                    entity_type="model",
                    entity_id=model.id,
                    action_page=model_page,
                    task_title=f"Configure timezone for {label}",
                )
            )
        if not model.primary_platform:
            gaps.append(
                ActivationGap(
                    code="model.missing_platform",
                    title=f"{label}: primary platform missing",
                    description="Set the primary platform so the team knows where to focus first.",
                    severity="warning",
                    section="models",
                    entity_type="model",
                    entity_id=model.id,
                    action_page=model_page,
                    task_title=f"Set primary platform for {label}",
                )
            )
        if accounts_by_model.get(model.id, 0) == 0:
            gaps.append(
                ActivationGap(
                    code="model.missing_accounts",
                    title=f"{label}: no accounts attached",
                    description="Add Instagram, X, OnlyFans, Email, or Other account records to this model.",
                    severity="critical",
                    section="accounts",
                    entity_type="model",
                    entity_id=model.id,
                    action_page=f"model:{model.id}:accounts",
                    task_title=f"Add accounts to {label}",
                )
            )
        relationship_types = {member.relationship_type for member in model.members}
        if not relationship_types:
            gaps.append(
                ActivationGap(
                    code="model.missing_team",
                    title=f"{label}: no team assigned",
                    description="Assign a manager, chatter team, or VA so work has an owner.",
                    severity="critical",
                    section="team",
                    entity_type="model",
                    entity_id=model.id,
                    action_page=f"model:{model.id}:team",
                    task_title=f"Assign team to {label}",
                )
            )
        elif "manager" not in relationship_types:
            gaps.append(
                ActivationGap(
                    code="team.missing_manager",
                    title=f"{label}: manager missing",
                    description="Assign a manager so operations have a clear owner.",
                    severity="warning",
                    section="team",
                    entity_type="model",
                    entity_id=model.id,
                    action_page=f"model:{model.id}:team",
                    task_title=f"Assign manager to {label}",
                )
            )
        if not relationship_types.intersection(CHATTER_RELATIONSHIP_TYPES):
            gaps.append(
                ActivationGap(
                    code="team.missing_chatter",
                    title=f"{label}: chatter team missing",
                    description="Assign a chatter manager, senior chatter, or chatter before opportunity work starts.",
                    severity="warning",
                    section="team",
                    entity_type="model",
                    entity_id=model.id,
                    action_page=f"model:{model.id}:team",
                    task_title=f"Assign chatter team to {label}",
                )
            )
        if creators_by_model.get(model.id, 0) == 0:
            gaps.append(
                ActivationGap(
                    code="model.missing_creators",
                    title=f"{label}: no creators watched",
                    description="Add creators to watch so the team can spot opportunities.",
                    severity="warning",
                    section="creators",
                    entity_type="model",
                    entity_id=model.id,
                    action_page="opportunities:creators",
                    task_title=f"Add creators to watch for {label}",
                )
            )
        if opportunities_by_model.get(model.id, 0) == 0:
            gaps.append(
                ActivationGap(
                    code="model.missing_opportunities",
                    title=f"{label}: no linked opportunities",
                    description="Create or link opportunities so chatters know where to focus.",
                    severity="warning",
                    section="opportunities",
                    entity_type="model",
                    entity_id=model.id,
                    action_page="opportunities:command",
                    task_title=f"Create first opportunities for {label}",
                )
            )
    return gaps


def _build_account_gaps(accounts: list[Account]) -> list[ActivationGap]:
    gaps: list[ActivationGap] = []
    for account in accounts:
        label = f"{account.platform.title()} @{account.username}"
        if account.assigned_proxy_id is None:
            gaps.append(
                ActivationGap(
                    code="account.missing_proxy",
                    title=f"{label}: proxy missing",
                    description="Assign a proxy before this account is considered operationally ready.",
                    severity="warning",
                    section="accounts",
                    entity_type="account",
                    entity_id=account.id,
                    action_page=f"account:{account.id}",
                    task_title=f"Assign proxy to {label}",
                )
            )
        if account.auth_status != "connected":
            gaps.append(
                ActivationGap(
                    code="account.missing_auth",
                    title=f"{label}: auth setup not connected",
                    description="Keep credentials as references only, then mark the account connected when it is ready.",
                    severity="warning",
                    section="accounts",
                    entity_type="account",
                    entity_id=account.id,
                    action_page=f"account:{account.id}",
                    task_title=f"Finish auth setup for {label}",
                )
            )
    return gaps


def _build_notification_gaps(active_purposes: set[str]) -> list[ActivationGap]:
    missing = [purpose for purpose in EXPECTED_NOTIFICATION_PURPOSES if purpose not in active_purposes]
    if not missing:
        return []
    return [
        ActivationGap(
            code="notifications.missing_targets",
            title="Notification targets missing",
            description="Add Fortuna HQ, Fortuna Operations, Incidents, Automation Logs, and Testing targets when the groups are ready.",
            severity="warning",
            section="notifications",
            action_page="notification_targets",
            task_title="Register Fortuna OS notification targets",
        )
    ]


def _build_team_gaps(session: Session) -> list[ActivationGap]:
    active_non_owner_count = session.scalar(
        select(func.count(User.id)).where(
            User.status == USER_STATUS_ACTIVE,
            User.is_active.is_(True),
            User.is_owner.is_(False),
        )
    ) or 0
    if active_non_owner_count:
        return []
    return [
        ActivationGap(
            code="team.no_real_users",
            title="No real team users onboarded",
            description="Invite team members to press /start, complete onboarding, then approve and assign roles.",
            severity="warning",
            section="team",
            action_page="users:pending",
            task_title="Invite and approve first team users",
        )
    ]


def build_activation_report(session: Session) -> dict:
    models = _active_models(session)
    accounts = _active_accounts(session)
    creators = _active_creators(session)
    opportunities = _active_opportunities(session)
    active_notification_purposes = set(
        session.scalars(select(NotificationTarget.purpose).where(NotificationTarget.is_active.is_(True))).all()
    )

    raw_gaps = [
        *_build_model_gaps(models, accounts, creators, opportunities),
        *_build_account_gaps(accounts),
        *_build_notification_gaps(active_notification_purposes),
        *_build_team_gaps(session),
    ]
    unlinked_opportunities = [
        opportunity
        for opportunity in opportunities
        if opportunity.model_brand_id is None and opportunity.status != "archived"
    ]
    if unlinked_opportunities:
        raw_gaps.append(
            ActivationGap(
                code="opportunity.unlinked",
                title="Opportunities not linked to a model",
                description=f"{len(unlinked_opportunities)} opportunities are floating without a model/brand.",
                severity="warning",
                section="opportunities",
                action_page="opportunities:command",
                task_title="Link opportunities to models",
            )
        )

    decisions = _blocker_decisions(session)
    skipped_keys = {key for key, status in decisions.items() if status == "skipped"}
    not_needed_keys = {key for key, status in decisions.items() if status == "not_needed"}
    suppressed_keys = skipped_keys | not_needed_keys
    gaps = [gap for gap in raw_gaps if activation_gap_key(gap) not in suppressed_keys]

    scores = _section_scores(
        models=models,
        accounts=accounts,
        creators=creators,
        opportunities=opportunities,
        active_notification_purposes=active_notification_purposes,
    )
    score_key_by_section = {
        "models": "models_ready",
        "accounts": "accounts_ready",
        "team": "teams_ready",
        "creators": "creators_ready",
        "opportunities": "opportunities_ready",
        "notifications": "notifications_ready",
    }
    for section, score_key in score_key_by_section.items():
        raw_section = [gap for gap in raw_gaps if gap.section == section]
        open_section = [gap for gap in raw_section if activation_gap_key(gap) not in not_needed_keys]
        if raw_section and not open_section:
            scores[score_key] = 100
    readiness_score = round(sum(scores.values()) / len(scores)) if scores else 0
    recommendations = [
        {
            "title": gap.title,
            "next_step": gap.description,
            "action_page": gap.action_page,
            "severity": gap.severity,
            "key": activation_gap_key_string(gap),
        }
        for gap in gaps[:10]
    ]
    return {
        **scores,
        "readiness_score": readiness_score,
        "blockers": [gap.as_dict() for gap in gaps],
        "skipped_blockers": len(skipped_keys),
        "not_needed_blockers": len(not_needed_keys),
        "recommendations": recommendations,
        "counts": {
            "models": len(models),
            "accounts": len(accounts),
            "creators": len(creators),
            "opportunities": len(opportunities),
            "notification_targets": len(active_notification_purposes),
        },
    }


def latest_activation_state(session: Session) -> AgencyActivationState | None:
    return session.scalar(select(AgencyActivationState).order_by(AgencyActivationState.updated_at.desc()))


def persist_activation_state(session: Session, report: dict) -> AgencyActivationState:
    state = latest_activation_state(session)
    if state is None:
        state = AgencyActivationState()
        session.add(state)
    state.models_ready = int(report["models_ready"])
    state.accounts_ready = int(report["accounts_ready"])
    state.teams_ready = int(report["teams_ready"])
    state.creators_ready = int(report["creators_ready"])
    state.opportunities_ready = int(report["opportunities_ready"])
    state.notifications_ready = int(report["notifications_ready"])
    state.readiness_score = int(report["readiness_score"])
    state.blockers_json = report["blockers"]
    state.recommendations_json = report["recommendations"]
    state.updated_at = _now()
    session.flush()
    return state


def _task_exists(session: Session, title: str) -> bool:
    return (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.title == title,
                Task.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
        or 0
    ) > 0


def create_activation_tasks(session: Session, *, actor: User, report: dict) -> list[Task]:
    if not user_has_permission(actor, "manage_tasks"):
        return []
    created: list[Task] = []
    for blocker in report["blockers"]:
        title = blocker.get("title")
        if not title:
            continue
        task_title = f"Setup: {title}"
        if _task_exists(session, task_title):
            continue
        priority = "high" if blocker.get("severity") == "critical" else "normal"
        task = create_task(
            session,
            actor=actor,
            title=task_title,
            description=blocker.get("description"),
            priority=priority,
        )
        created.append(task)
    return created


def generate_activation_recommendations(session: Session, *, actor: User | None, report: dict) -> None:
    for blocker in report["blockers"]:
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type=f"activation_{blocker['code'].replace('.', '_')}",
            title=blocker["title"],
            description=blocker["description"],
            severity=blocker["severity"],
            entity_type=blocker.get("entity_type"),
            entity_id=blocker.get("entity_id"),
            metadata={
                "section": blocker.get("section"),
                "action_page": blocker.get("action_page"),
            },
        )


def run_activation_scan(session: Session, *, actor: User, create_tasks: bool = True) -> AgencyActivationState:
    if not (user_has_permission(actor, "manage_accounts") or user_has_permission(actor, "manage_users")):
        audit_action(
            session,
            actor=actor,
            action="access.denied",
            resource_type="agency_activation",
            status="denied",
            details={"permission": "manage_accounts_or_manage_users"},
        )
        raise PermissionError("Missing permission: manage_accounts or manage_users")
    report = build_activation_report(session)
    state = persist_activation_state(session, report)
    generate_activation_recommendations(session, actor=actor, report=report)
    created_tasks = create_activation_tasks(session, actor=actor, report=report) if create_tasks else []
    emit_event(
        session,
        actor=actor,
        event_name="agency_activation.scanned",
        resource_type="agency_activation",
        resource_id=str(state.id),
        payload={
            "readiness_score": state.readiness_score,
            "blocker_count": len(report["blockers"]),
            "tasks_created": len(created_tasks),
        },
    )
    return state


def account_setup_states(session: Session) -> list[AccountSetupState]:
    states: list[AccountSetupState] = []
    for account in _active_accounts(session):
        checklist: list[str] = []
        recommended_actions: list[str] = []
        if account.model_brand_id:
            checklist.append("Model linked")
        else:
            checklist.append("Needs model")
            recommended_actions.append("Link this account to a model/brand.")
        if account.assigned_proxy_id:
            checklist.append("Proxy assigned")
        else:
            checklist.append("Needs proxy")
            recommended_actions.append("Assign the best available proxy.")
        if account.auth_status == "connected":
            checklist.append("Auth connected")
        else:
            checklist.append(f"Auth: {account.auth_status.replace('_', ' ')}")
            recommended_actions.append("Finish secure auth setup; never paste passwords into chat.")
        if account.status == "healthy":
            checklist.append("Health healthy")
        else:
            checklist.append(f"Health: {account.status}")
            recommended_actions.append("Review account health before active work.")
        if account.status == "disabled":
            status = "Blocked"
        elif not account.model_brand_id:
            status = "Needs Team"
        elif not account.assigned_proxy_id:
            status = "Needs Proxy"
        elif account.auth_status != "connected":
            status = "Needs Auth"
        else:
            status = "Ready"
        states.append(
            AccountSetupState(
                account_id=account.id,
                platform=account.platform,
                username=account.username,
                model_name=account.model_brand.display_name if account.model_brand else "No model",
                status=status,
                checklist=checklist,
                recommended_actions=recommended_actions,
            )
        )
    return states


def activation_answer(session: Session, question: str) -> str:
    report = build_activation_report(session)
    blockers = report["blockers"]
    top_blockers = blockers[:3]
    if not blockers:
        return "Fortuna OS setup looks ready. Next best step: generate a daily briefing and start assigning real work."
    blocker_lines = "\n".join(f"- {blocker['title']}" for blocker in top_blockers)
    score = report["readiness_score"]
    q = question.lower()
    if "unhealthy" in q and "model" in q:
        model_blockers = [blocker for blocker in blockers if blocker.get("entity_type") == "model"][:3]
        if model_blockers:
            return "The model is unhealthy because setup is incomplete:\n" + "\n".join(
                f"- {blocker['title']}" for blocker in model_blockers
            )
    if "next" in q or "finish" in q:
        first = blockers[0]
        return f"Readiness is {score}%. Start here: {first['title']}. {first['description']}"
    return f"Fortuna readiness is {score}%. The main blockers are:\n{blocker_lines}\nUse Owner Home -> Fortuna Activation to fix them in order."
