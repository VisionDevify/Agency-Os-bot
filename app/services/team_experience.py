from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.automation import AutomationRule, AutomationRun, AutomationSchedule
from app.models.incident import Incident
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import Opportunity, OpportunityResult
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.models.team_rollout import NotificationDigest, TeamOnboardingChecklist
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action, is_owner, user_has_permission
from app.services.automations import latest_valid_simulation, run_automation_rule
from app.services.events import emit_event
from app.services.team_operations import format_user_datetime, get_or_create_availability

ROLE_HOME_ORDER = (
    "Owner",
    "Admin",
    "Manager",
    "Chatter Manager",
    "Senior Chatter",
    "Chatter",
    "VA",
    "Model/Client",
    "Viewer",
)

HUMAN_TERMS = {
    "Intelligence Signals": "Things To Watch",
    "Signals": "Things To Watch",
    "Issue Patterns": "Recurring Problems",
    "Patterns": "Recurring Problems",
    "Outcome Memory": "What We've Learned",
    "Executive Insights": "Management Insights",
}

HELP_TOPICS: dict[str, str] = {
    "tasks": "A task is a clear piece of work with an owner, priority, and due date.",
    "incidents": "An incident is something that needs attention, investigation, or resolution.",
    "opportunities": "An opportunity is a manual, human-approved growth or outreach idea.",
    "availability": "Availability tells Fortuna OS who is on shift, away, or in quiet hours.",
    "complete_work": "Open your task, start it, add notes if needed, then mark it complete when the work is done.",
    "recommendations": "Recommendations are calm prompts from Fortuna OS about what may need attention next.",
    "get_help": "Use Help, ask your manager, or escalate a task or incident when you are blocked.",
    "notification_groups": (
        "Create the Fortuna OS Telegram groups manually, add @FortunaSolstice_Bot, open each group, "
        "then use Settings -> Notification Targets -> Register Current Chat as Fortuna Target."
    ),
    "comment_profile_leads": (
        "Comment profile leads are public profiles Fortuna noticed from approved comment data. "
        "Review them manually; Fortuna never follows, likes, or comments."
    ),
    "comment_profile_data": (
        "Add only safe public comment/profile details from manual input, approved exports, official APIs, "
        "or compliant public sources. Do not paste private content or credentials."
    ),
}

TEAM_INVITE_ROLES = ("chatter", "va", "manager")


def team_invite_message(role: str, *, bot_username: str = "@FortunaSolstice_Bot") -> str:
    normalized = role.strip().lower().replace(" ", "_")
    if normalized not in TEAM_INVITE_ROLES:
        raise ValueError(f"Unsupported invite role: {role}")
    role_label = {
        "chatter": "Chatter",
        "va": "VA",
        "manager": "Manager",
    }[normalized]
    first_area = {
        "chatter": "My Work, Opportunities, Alerts, and Help",
        "va": "Tasks, Assignments, and Help",
        "manager": "Team, Assignments, Alerts, and Help",
    }[normalized]
    return "\n".join(
        [
            f"Fortuna OS invite for {role_label}",
            f"1. Open {bot_username} in Telegram.",
            "2. Press /start.",
            "3. Choose your language, country, timezone, and 12h/24h time format.",
            "4. Wait for approval. You will see Access pending approval until an owner/admin approves you.",
            f"5. After approval, your {role_label} home will show: {first_area}.",
            "Do not send passwords or verification codes in onboarding.",
        ]
    )


def team_invite_packet(*, bot_username: str = "@FortunaSolstice_Bot") -> dict[str, str]:
    return {role: team_invite_message(role, bot_username=bot_username) for role in TEAM_INVITE_ROLES}


@dataclass(frozen=True)
class ScheduledAutomationResult:
    schedule_id: int
    rule_id: int
    rule_name: str
    status: str
    reason: str
    run_id: int | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def human_term(label: str) -> str:
    return HUMAN_TERMS.get(label, label)


def role_names(user: User | None) -> list[str]:
    if user is None:
        return []
    names = [role.name for role in user.roles]
    if user.is_owner and "Owner" not in names:
        names.append("Owner")
    return names


def primary_role(user: User | None) -> str:
    if user is None:
        return "Viewer"
    names = set(role_names(user))
    if is_owner(user):
        return "Owner"
    for role in ROLE_HOME_ORDER[1:]:
        if role in names:
            return role
    return "Viewer"


def role_intro(role: str) -> str:
    if role in {"Owner", "Admin"}:
        return "Your home focuses on the command center, controls, and company-wide visibility."
    if role in {"Manager", "Chatter Manager"}:
        return "Here is where you manage team operations, assignments, incidents, and reports."
    if role in {"Senior Chatter", "Chatter"}:
        return "Here's what matters for your role: models, tasks, opportunities, and availability."
    if role == "VA":
        return "Here's where you'll manage accounts, tasks, availability, and upload-ready work."
    if role == "Model/Client":
        return "Your home keeps dashboards, reports, accounts, and team visibility simple."
    return "Your access is focused on the pages your team has assigned to you."


def role_home_items(user: User | None) -> list[tuple[str, str]]:
    role = primary_role(user)
    if role in {"Owner", "Admin"}:
        return [
            ("Setup Fortuna", "setup:wizard"),
            ("Fortuna HQ", "executive_mode"),
            ("Today Top 5", "coo:top5"),
            ("COO Briefing", "coo:briefing"),
            ("Fortuna Activation", "agency_activation"),
            ("Owner Daily Checklist", "owner_daily_checklist"),
            ("First Day Plan", "first_day_plan"),
            ("Fortuna Intelligence", "intelligence"),
            ("Fortuna Opportunities", "opportunities"),
            ("Models", "models"),
            ("Accounts", "accounts"),
            ("Proxies", "proxies"),
            ("Operations", "reports:operations"),
            ("Reports", "reports"),
            ("Fortuna Automation", "automations"),
            ("Settings", "settings"),
            ("Help", "help"),
        ]
    if role in {"Manager", "Chatter Manager"}:
        return [
            ("Team", "availability:team"),
            ("Assignments", "manager_queue"),
            ("Alerts", "notification_group_pilot"),
            ("Help", "help"),
        ]
    if role in {"Senior Chatter", "Chatter"}:
        return [
            ("My Work", "my_work"),
            ("Opportunities", "my_opportunities"),
            ("Alerts", "opportunities"),
            ("Help", "help"),
        ]
    if role == "VA":
        return [
            ("Tasks", "tasks:my"),
            ("Assignments", "my_work"),
            ("Help", "help"),
        ]
    if role == "Model/Client":
        return [
            ("My Dashboard", "client_dashboard"),
            ("My Accounts", "my_accounts"),
            ("My Reports", "my_reports"),
            ("My Team", "my_team"),
        ]
    return [
        ("Dashboard", "dashboard"),
        ("Availability", "availability"),
        ("Help", "help"),
    ]


def _user_timezone(user: User | None) -> ZoneInfo:
    timezone = user.timezone if user and user.timezone and user.timezone != "UTC" else "America/New_York"
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _day_window_for_user(user: User, now: datetime | None = None) -> tuple[datetime, datetime]:
    local_now = (now or _now()).astimezone(_user_timezone(user))
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def assigned_model_count(session: Session, user: User) -> int:
    return (
        session.scalar(select(func.count(ModelBrandMember.model_brand_id)).where(ModelBrandMember.user_id == user.id))
        or 0
    )


def assigned_account_count(session: Session, user: User) -> int:
    model_ids = select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
    return session.scalar(select(func.count(Account.id)).where(Account.model_brand_id.in_(model_ids))) or 0


def role_performance_snapshot(session: Session, user: User, *, now: datetime | None = None) -> dict:
    start, end = _day_window_for_user(user, now)
    completed = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.assigned_to_user_id == user.id,
                Task.status == "complete",
                Task.completed_at >= start,
                Task.completed_at < end,
            )
        )
        or 0
    )
    overdue = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.assigned_to_user_id == user.id,
                Task.status.in_(("open", "in_progress", "blocked")),
                Task.due_at.is_not(None),
                Task.due_at < (now or _now()),
            )
        )
        or 0
    )
    opportunities = (
        session.scalar(select(func.count(Opportunity.id)).where(Opportunity.assigned_to_user_id == user.id))
        or 0
    )
    posted_opportunities = (
        session.scalar(
            select(func.count(OpportunityResult.id)).where(
                OpportunityResult.posted_by_user_id == user.id,
                OpportunityResult.status == "posted",
            )
        )
        or 0
    )
    accounts = assigned_account_count(session, user)
    open_team_incidents = (
        session.scalar(
            select(func.count(Incident.id)).where(
                Incident.assigned_to_user_id == user.id,
                Incident.status.in_(("open", "investigating")),
            )
        )
        or 0
    )
    accountability_score = max(0, min(100, 80 + completed * 3 + posted_opportunities * 2 - overdue * 8))
    return {
        "tasks_completed": completed,
        "opportunities_handled": opportunities,
        "posted_opportunities": posted_opportunities,
        "accounts_maintained": accounts,
        "overdue_items": overdue,
        "open_incidents": open_team_incidents,
        "accountability_score": accountability_score,
    }


def personalized_dashboard(session: Session, user: User, *, now: datetime | None = None) -> dict:
    availability = get_or_create_availability(session, user)
    start, end = _day_window_for_user(user, now)
    due_today = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.assigned_to_user_id == user.id,
                Task.status.in_(("open", "in_progress", "blocked")),
                Task.due_at >= start,
                Task.due_at < end,
            )
        )
        or 0
    )
    overdue = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.assigned_to_user_id == user.id,
                Task.status.in_(("open", "in_progress", "blocked")),
                Task.due_at.is_not(None),
                Task.due_at < (now or _now()),
            )
        )
        or 0
    )
    open_incidents = (
        session.scalar(
            select(func.count(Incident.id)).where(
                Incident.assigned_to_user_id == user.id,
                Incident.status.in_(("open", "investigating")),
            )
        )
        or 0
    )
    recommendation = session.scalar(
        select(Recommendation)
        .where(Recommendation.status == "open")
        .order_by(desc(Recommendation.severity), desc(Recommendation.updated_at), desc(Recommendation.id))
        .limit(1)
    )
    recent = list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.actor_user_id == user.id)
            .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
            .limit(3)
        ).all()
    )
    return {
        "display_name": user.display_name or user.username or "there",
        "role": primary_role(user),
        "roles": role_names(user),
        "availability_status": availability.status,
        "tasks_due_today": due_today,
        "overdue_items": overdue,
        "open_incidents": open_incidents,
        "assigned_models": assigned_model_count(session, user),
        "recommended_action": recommendation.title if recommendation else "No urgent action right now.",
        "performance": role_performance_snapshot(session, user, now=now),
        "recent_activity": [f"{item.action} ({format_user_datetime(user, item.created_at)})" for item in recent],
    }


def daily_experience(session: Session, user: User, *, now: datetime | None = None) -> dict:
    local_now = (now or _now()).astimezone(_user_timezone(user))
    if local_now.hour < 12:
        greeting = "Good morning"
    elif local_now.hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    dashboard = personalized_dashboard(session, user, now=now)
    priorities = []
    if dashboard["overdue_items"]:
        priorities.append(f"Review {dashboard['overdue_items']} overdue item(s).")
    if dashboard["tasks_due_today"]:
        priorities.append(f"Complete {dashboard['tasks_due_today']} task(s) due today.")
    if dashboard["open_incidents"]:
        priorities.append(f"Check {dashboard['open_incidents']} assigned incident(s).")
    if not priorities:
        priorities.append("Stay available and keep your work queue clean.")
    return {
        **dashboard,
        "greeting": greeting,
        "today": local_now.strftime("%Y-%m-%d"),
        "priorities": priorities,
        "quick_actions": role_home_items(user)[:4],
    }


def help_topics_for_role(user: User | None) -> list[tuple[str, str]]:
    topics = [
        ("tasks", "What is a Task?"),
        ("incidents", "What is an Incident?"),
        ("opportunities", "What is an Opportunity?"),
        ("availability", "How does Availability work?"),
        ("complete_work", "How do I complete work?"),
        ("recommendations", "How do recommendations work?"),
        ("get_help", "How do I get help?"),
    ]
    role = primary_role(user)
    if role in {"Owner", "Admin", "Manager", "Chatter Manager"}:
        topics.append(("manager", "Manager Help"))
        topics.append(("team_invites", "Team Invite Packet"))
        topics.append(("comment_profile_leads", "What are Comment Profile Leads?"))
    if role in {"Senior Chatter", "Chatter"}:
        topics.append(("chatter", "Chatter Help"))
    if role == "VA":
        topics.append(("va", "VA Help"))
    return topics


def help_text(topic: str, user: User | None = None) -> str:
    if topic == "manager":
        return "Managers use Team, Tasks, Incidents, Reports, and Team QA to keep operations moving."
    if topic == "chatter":
        return "Chatters focus on assigned models, tasks, opportunities, availability, and clean handoffs."
    if topic == "va":
        return "VAs focus on assigned accounts, task completion, uploads, availability, and overdue cleanup."
    if topic == "team_invites":
        packet = team_invite_packet()
        return "\n\n".join(packet[role] for role in TEAM_INVITE_ROLES)
    return HELP_TOPICS.get(topic, "Fortuna OS keeps work visible, calm, and accountable.")


def _readiness_score(checklist: TeamOnboardingChecklist) -> int:
    fields = (
        checklist.role_assigned,
        checklist.timezone_confirmed,
        checklist.availability_configured,
        checklist.help_center_viewed,
        checklist.onboarded,
    )
    return int(sum(1 for value in fields if value) / len(fields) * 100)


def get_or_create_onboarding_checklist(session: Session, user: User) -> TeamOnboardingChecklist:
    checklist = session.scalar(
        select(TeamOnboardingChecklist).where(TeamOnboardingChecklist.user_id == user.id)
    )
    if checklist is None:
        checklist = TeamOnboardingChecklist(
            user_id=user.id,
            role_assigned=bool(user.roles),
            timezone_confirmed=bool(user.timezone and user.timezone != "UTC"),
            availability_configured=user.availability is not None,
            help_center_viewed=False,
            onboarded=False,
        )
        checklist.readiness_score = _readiness_score(checklist)
        session.add(checklist)
        session.flush()
    return checklist


def update_onboarding_checklist(
    session: Session,
    target_user: User,
    *,
    actor: User,
    field: str,
    value: bool = True,
) -> TeamOnboardingChecklist:
    if not user_has_permission(actor, "manage_users"):
        audit_action(
            session,
            actor=actor,
            action="access.denied",
            resource_type="team_onboarding_checklist",
            resource_id=str(target_user.id),
            status="denied",
            details={"permission": "manage_users"},
        )
        raise PermissionError("Missing permission: manage_users")
    if field not in {
        "onboarded",
        "role_assigned",
        "timezone_confirmed",
        "availability_configured",
        "help_center_viewed",
    }:
        raise ValueError(f"Invalid checklist field: {field}")
    checklist = get_or_create_onboarding_checklist(session, target_user)
    setattr(checklist, field, value)
    checklist.updated_by_user_id = actor.id
    checklist.readiness_score = _readiness_score(checklist)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="team.onboarding_checklist_updated",
        resource_type="user",
        resource_id=str(target_user.id),
        details={"field": field, "value": value, "readiness_score": checklist.readiness_score},
    )
    return checklist


def list_onboarding_checklists(session: Session) -> list[TeamOnboardingChecklist]:
    users = list(session.scalars(select(User).options(selectinload(User.roles), selectinload(User.availability))).all())
    for user in users:
        checklist = get_or_create_onboarding_checklist(session, user)
        checklist.role_assigned = checklist.role_assigned or bool(user.roles)
        checklist.timezone_confirmed = checklist.timezone_confirmed or bool(user.timezone and user.timezone != "UTC")
        checklist.availability_configured = checklist.availability_configured or user.availability is not None
        checklist.readiness_score = _readiness_score(checklist)
    session.flush()
    return list(
        session.scalars(
            select(TeamOnboardingChecklist)
            .options(selectinload(TeamOnboardingChecklist.user), selectinload(TeamOnboardingChecklist.updated_by))
            .order_by(TeamOnboardingChecklist.readiness_score, TeamOnboardingChecklist.user_id)
        ).all()
    )


def create_notification_digest(
    session: Session,
    *,
    actor: User | None,
    purpose: str = "operations",
    user: User | None = None,
    limit: int = 10,
) -> NotificationDigest:
    attempts = list(
        session.scalars(
            select(NotificationDeliveryAttempt)
            .where(NotificationDeliveryAttempt.status.in_(("pending", "skipped", "failed")))
            .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
            .limit(limit)
        ).all()
    )
    items = [
        {
            "event_type": attempt.event_type,
            "status": attempt.status,
            "target_id": attempt.notification_target_id,
            "attempted_at": attempt.attempted_at.isoformat() if attempt.attempted_at else None,
        }
        for attempt in attempts
    ]
    title = "Notification Digest"
    summary = f"You have {len(items)} update(s)." if items else "No low-priority updates are waiting."
    digest = NotificationDigest(
        user_id=user.id if user else None,
        purpose=purpose,
        status="open",
        priority="low",
        title=title,
        summary=summary,
        items_json=[sanitize_details(item) for item in items],
        item_count=len(items),
    )
    session.add(digest)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="notification.digest_created",
        resource_type="notification_digest",
        resource_id=str(digest.id),
        details={"purpose": purpose, "item_count": digest.item_count},
    )
    emit_event(
        session,
        actor=actor,
        event_name="notification.digest_created",
        resource_type="notification_digest",
        resource_id=str(digest.id),
        payload={"purpose": purpose, "item_count": digest.item_count},
    )
    return digest


def list_notification_digests(session: Session, *, limit: int = 10) -> list[NotificationDigest]:
    return list(
        session.scalars(
            select(NotificationDigest)
            .order_by(desc(NotificationDigest.created_at), desc(NotificationDigest.id))
            .limit(limit)
        ).all()
    )


def _next_scheduled_time(schedule: AutomationSchedule, now: datetime) -> datetime | None:
    if schedule.schedule_type == "hourly":
        return now + timedelta(hours=1)
    if schedule.schedule_type == "daily":
        return now + timedelta(days=1)
    if schedule.schedule_type == "weekly":
        return now + timedelta(days=7)
    return None


def set_schedule_next_run(
    session: Session,
    schedule: AutomationSchedule,
    *,
    next_run_at: datetime | None,
    actor: User | None = None,
) -> AutomationSchedule:
    schedule.next_run_at = next_run_at
    schedule.is_active = next_run_at is not None and schedule.schedule_type in {"hourly", "daily", "weekly"}
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="automation.schedule_updated",
        resource_type="automation_schedule",
        resource_id=str(schedule.id),
        details={"schedule_type": schedule.schedule_type, "is_active": schedule.is_active},
    )
    return schedule


def _scheduled_skip_run(
    session: Session,
    schedule: AutomationSchedule,
    *,
    actor: User | None,
    reason: str,
    now: datetime,
) -> AutomationRun:
    run = AutomationRun(
        automation_rule_id=schedule.automation_rule_id,
        status="skipped",
        started_by_user_id=actor.id if actor else None,
        started_at=now,
        finished_at=now,
        result_summary_json={"scheduled": True, "skipped": True, "reason": reason},
        rollback_available=False,
        rollback_status="not_needed",
    )
    session.add(run)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.scheduled_run.skipped",
        resource_type="automation_schedule",
        resource_id=str(schedule.id),
        payload={"automation_rule_id": schedule.automation_rule_id, "reason": reason},
    )
    return run


def run_due_scheduled_automations(
    session: Session,
    *,
    actor: User | None,
    now: datetime | None = None,
    limit: int = 10,
) -> list[ScheduledAutomationResult]:
    current = now or _now()
    schedules = list(
        session.scalars(
            select(AutomationSchedule)
            .options(selectinload(AutomationSchedule.rule))
            .where(
                AutomationSchedule.is_active.is_(True),
                AutomationSchedule.next_run_at.is_not(None),
                AutomationSchedule.next_run_at <= current,
            )
            .order_by(AutomationSchedule.next_run_at, AutomationSchedule.id)
            .limit(limit)
        ).all()
    )
    results: list[ScheduledAutomationResult] = []
    for schedule in schedules:
        rule = schedule.rule
        run: AutomationRun | None = None
        reason = "ran"
        if rule.risk_level != "low" or rule.requires_owner_approval:
            reason = "Only low-risk automations auto-run initially."
            run = _scheduled_skip_run(session, schedule, actor=actor, reason=reason, now=current)
        elif rule.status != "active":
            reason = f"Automation is {rule.status}, not active."
            run = _scheduled_skip_run(session, schedule, actor=actor, reason=reason, now=current)
        elif latest_valid_simulation(session, rule) is None:
            reason = "A fresh simulation is required before scheduled execution."
            run = _scheduled_skip_run(session, schedule, actor=actor, reason=reason, now=current)
        else:
            run = run_automation_rule(session, rule, actor=actor)
            reason = "Scheduled automation ran safely."
        schedule.last_run_at = current
        schedule.next_run_at = _next_scheduled_time(schedule, current)
        if schedule.next_run_at is None:
            schedule.is_active = False
        session.flush()
        results.append(
            ScheduledAutomationResult(
                schedule_id=schedule.id,
                rule_id=rule.id,
                rule_name=rule.name,
                status=run.status if run else "skipped",
                reason=reason,
                run_id=run.id if run else None,
            )
        )
    if results:
        audit_action(
            session,
            actor=actor,
            action="automation.scheduled_runs_processed",
            resource_type="automation_schedule",
            details={"count": len(results)},
        )
    return results


def scheduled_automation_summary(session: Session) -> dict:
    total = session.scalar(select(func.count(AutomationSchedule.id))) or 0
    active = session.scalar(select(func.count(AutomationSchedule.id)).where(AutomationSchedule.is_active.is_(True))) or 0
    successful = session.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "succeeded")) or 0
    failed = session.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "failed")) or 0
    skipped = session.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "skipped")) or 0
    return {"total": total, "active": active, "successful": successful, "failed": failed, "skipped": skipped}
