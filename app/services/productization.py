from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.autonomous_operations import FollowUp
from app.models.friction import FrictionItem
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import CreatorWatch, Opportunity
from app.models.proxy import Proxy
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.models.task import Task
from app.models.user import User
from app.services.agency_activation import build_activation_report
from app.services.auth import is_owner
from app.services.coo import todays_top_5_actions
from app.services.team_experience import primary_role

ACTIVE_TASK_STATUSES = ("open", "in_progress", "blocked")
ACTIVE_OPPORTUNITY_STATUSES = ("discovered", "reviewing", "approved", "assigned")


@dataclass(frozen=True)
class ProductNextAction:
    title: str
    reason: str
    action_page: str
    estimated_time: str
    audience: str
    severity: str = "normal"


@dataclass(frozen=True)
class ProductSetupStep:
    number: int
    label: str
    status: str
    why: str
    action_label: str
    action_page: str
    complete: bool
    optional: bool = False


def _is_demo_proxy(proxy: Proxy) -> bool:
    metadata = proxy.metadata_json or {}
    host = (proxy.host or "").casefold()
    provider = (proxy.provider or "").casefold()
    name = (proxy.name or "").casefold()
    return bool(
        metadata.get("is_demo")
        or metadata.get("placeholder")
        or "placeholder" in host
        or host.endswith(".local")
        or "demo" in provider
        or "fake" in provider
        or "test" in provider
        or "placeholder" in name
    )


def real_proxy_count(session: Session) -> int:
    proxies = list(session.scalars(select(Proxy).where(Proxy.status != "disabled")).all())
    return sum(1 for proxy in proxies if not _is_demo_proxy(proxy))


def setup_steps(session: Session) -> list[ProductSetupStep]:
    report = build_activation_report(session)
    blockers = report.get("blockers", [])
    codes = {str(blocker.get("code") or "") for blocker in blockers}
    model_count = session.scalar(select(func.count(ModelBrand.id)).where(ModelBrand.status != "archived")) or 0
    account_count = session.scalar(select(func.count(Account.id)).where(Account.status != "archived")) or 0
    team_count = session.scalar(select(func.count(ModelBrandMember.user_id))) or 0
    creator_count = session.scalar(select(func.count(CreatorWatch.id)).where(CreatorWatch.is_active.is_(True))) or 0
    opportunity_count = session.scalar(select(func.count(Opportunity.id)).where(Opportunity.status != "archived")) or 0
    notification_count = (
        session.scalar(select(func.count(NotificationTarget.id)).where(NotificationTarget.is_active.is_(True))) or 0
    )
    proxy_count = real_proxy_count(session)
    daily_ready = bool(
        session.scalar(
            select(func.count(FollowUp.id)).where(FollowUp.status.in_(("pending", "ready", "completed")))
        )
    )

    def state(done: bool, waiting: bool = False, optional: bool = False) -> str:
        if done:
            return "Complete"
        if optional:
            return "Optional for now"
        if waiting:
            return "Waiting"
        return "Needs attention"

    model_complete = bool(model_count) and not any(code.startswith("model.missing") for code in codes)
    account_complete = bool(account_count) and "model.missing_accounts" not in codes
    team_complete = bool(team_count) and not any(code in {"model.missing_team", "team.missing_manager", "team.missing_chatter"} for code in codes)
    creator_complete = bool(creator_count) and "model.missing_creators" not in codes
    opportunity_complete = bool(opportunity_count) and "model.missing_opportunities" not in codes
    alerts_complete = bool(notification_count) and "notifications.missing_targets" not in codes

    return [
        ProductSetupStep(
            1,
            "Model",
            state(model_complete),
            "This is the profile Fortuna uses to organize accounts, creators, and team work.",
            "Continue Model Setup",
            "agency_activation:models",
            model_complete,
        ),
        ProductSetupStep(
            2,
            "Account",
            state(account_complete, waiting=not model_count),
            "Accounts connect the model to daily work without storing platform passwords.",
            "Add Account",
            "setup:wizard:accounts",
            account_complete,
        ),
        ProductSetupStep(
            3,
            "Proxy",
            state(bool(proxy_count)),
            "A proxy gives accounts a clean operating setup when you are ready to use one.",
            "Paste Proxy",
            "proxies",
            bool(proxy_count),
        ),
        ProductSetupStep(
            4,
            "Team",
            state(team_complete, waiting=not model_count, optional=True),
            "Team assignment lets Fortuna route work to the right person.",
            "Assign Team",
            "setup:wizard:team",
            team_complete,
            optional=True,
        ),
        ProductSetupStep(
            5,
            "Creators",
            state(creator_complete, waiting=not model_count),
            "Creators give chatters a focused place to find manual opportunities.",
            "Add Creator",
            "setup:wizard:creators",
            creator_complete,
        ),
        ProductSetupStep(
            6,
            "Opportunities",
            state(opportunity_complete, waiting=not model_count),
            "Opportunities turn creator and post ideas into trackable work.",
            "Create Opportunity",
            "setup:wizard:opportunities",
            opportunity_complete,
        ),
        ProductSetupStep(
            7,
            "Alerts",
            state(alerts_complete, optional=True),
            "Alerts route important work to HQ, Ops, or Alerts when groups are registered.",
            "Set Up Alerts",
            "notification_group_pilot",
            alerts_complete,
            optional=True,
        ),
        ProductSetupStep(
            8,
            "Daily Cycle",
            state(daily_ready, waiting=not opportunity_complete, optional=True),
            "The daily cycle refreshes priorities, follow-ups, and summaries.",
            "Run Daily Cycle",
            "automations:daily_autopilot:run",
            daily_ready,
            optional=True,
        ),
    ]


def next_incomplete_setup_step(session: Session) -> ProductSetupStep | None:
    for step in setup_steps(session):
        if not step.complete and not step.optional and step.status != "Waiting":
            return step
    for step in setup_steps(session):
        if not step.complete and step.status != "Waiting":
            return step
    return None


def best_next_action(session: Session, user: User | None) -> ProductNextAction:
    role = primary_role(user)
    if role in {"Owner", "Admin"} or (user is not None and is_owner(user)):
        step = next_incomplete_setup_step(session)
        if step is not None:
            return ProductNextAction(
                title=step.action_label,
                reason=step.why,
                action_page=step.action_page,
                estimated_time="2-5 min",
                audience="Owner",
                severity="setup",
            )
        actions = todays_top_5_actions(session, actor=user, limit=1)
        if actions:
            action = actions[0]
            return ProductNextAction(
                title=action.title,
                reason=action.explanation,
                action_page=action.action_page,
                estimated_time="5 min",
                audience=action.owner,
                severity="attention",
            )
        return ProductNextAction(
            title="Review Today's Priorities",
            reason="Fortuna does not see a setup blocker right now. A quick daily review is enough.",
            action_page="today_priorities",
            estimated_time="2 min",
            audience="Owner",
            severity="calm",
        )

    if role in {"Manager", "Chatter Manager"}:
        actions = todays_top_5_actions(session, actor=user, limit=1)
        if actions:
            action = actions[0]
            return ProductNextAction(
                title="Open Assignments",
                reason=action.explanation,
                action_page="manager_queue",
                estimated_time="5 min",
                audience="Manager",
                severity="attention",
            )
        return ProductNextAction(
            title="Check Team Assignments",
            reason="No urgent priority is waiting. A quick queue review keeps the team moving.",
            action_page="manager_queue",
            estimated_time="2 min",
            audience="Manager",
            severity="calm",
        )

    if role in {"Senior Chatter", "Chatter"} and user is not None:
        opportunities = (
            session.scalar(
                select(func.count(Opportunity.id)).where(
                    Opportunity.assigned_to_user_id == user.id,
                    Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
                )
            )
            or 0
        )
        tasks = (
            session.scalar(
                select(func.count(Task.id)).where(
                    Task.assigned_to_user_id == user.id,
                    Task.status.in_(ACTIVE_TASK_STATUSES),
                )
            )
            or 0
        )
        if opportunities:
            return ProductNextAction(
                title="Review My Opportunities",
                reason=f"You have {opportunities} opportunity item(s) waiting for manual review.",
                action_page="my_opportunities",
                estimated_time="5 min",
                audience="Chatter",
                severity="attention",
            )
        if tasks:
            return ProductNextAction(
                title="Open My Work",
                reason=f"You have {tasks} task(s) waiting on you.",
                action_page="my_work",
                estimated_time="5 min",
                audience="Chatter",
                severity="attention",
            )
        return ProductNextAction(
            title="Check My Work",
            reason="Nothing urgent is assigned yet. Keep availability current and check your workspace.",
            action_page="my_work",
            estimated_time="1 min",
            audience="Chatter",
            severity="calm",
        )

    if role == "VA" and user is not None:
        tasks = (
            session.scalar(
                select(func.count(Task.id)).where(
                    Task.assigned_to_user_id == user.id,
                    Task.status.in_(ACTIVE_TASK_STATUSES),
                )
            )
            or 0
        )
        return ProductNextAction(
            title="Open Tasks" if tasks else "Check Assignments",
            reason=f"You have {tasks} task(s) assigned." if tasks else "No task is waiting. Check assignments or availability.",
            action_page="tasks:my" if tasks else "my_work",
            estimated_time="2 min",
            audience="VA",
            severity="attention" if tasks else "calm",
        )

    return ProductNextAction(
        title="Open Help",
        reason="Fortuna will show the screens available for your role.",
        action_page="help",
        estimated_time="1 min",
        audience=role,
        severity="calm",
    )


def friction_burndown(session: Session) -> dict[str, list[FrictionItem]]:
    items = list(
        session.scalars(
            select(FrictionItem).order_by(desc(FrictionItem.discovered_at), desc(FrictionItem.id)).limit(100)
        ).all()
    )
    grouped = {"high": [], "medium": [], "low": []}
    for item in items:
        if item.severity in {"critical", "high"}:
            grouped["high"].append(item)
        elif item.severity == "medium":
            grouped["medium"].append(item)
        else:
            grouped["low"].append(item)
    return grouped


def visible_button_count(labels: list[str]) -> int:
    navigation = {"Back", "Main Menu", "More", "More Details", "Technical Details", "Advanced", "Simple Mode"}
    return sum(1 for label in labels if label not in navigation)
