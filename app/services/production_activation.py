from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.automation import AutomationApproval, AutomationRun
from app.models.autonomous_operations import FollowUp, OperationsAction
from app.models.incident import Incident
from app.models.opportunity import Opportunity
from app.models.proxy import Proxy
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.models.task import Task
from app.models.team_rollout import DailyAutopilotSetting
from app.models.user import User
from app.services.agency_activation import (
    activation_gap_key_string,
    build_activation_report,
    set_activation_blocker_decision,
)
from app.services.audit import sanitize_details
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.automations import automation_metrics
from app.services.autonomous_operations import add_or_update_action, run_daily_autonomous_cycle
from app.services.events import emit_event
from app.services.intelligence import run_full_intelligence_scan
from app.services.recommendations import generate_recommendations
from app.services.team_experience import create_notification_digest, team_invite_packet

DAILY_AUTOPILOT_ACTIONS = [
    "Daily Readiness Scan",
    "Recommendation Refresh",
    "Intelligence Scan",
    "Follow-Up Digest",
    "Automation Health Check",
]


@dataclass(frozen=True)
class ProxyEntryStatus:
    total_proxies: int
    real_proxies: int
    accounts_missing_proxy: int
    needs_setup: bool
    guidance: str


def _now() -> datetime:
    return datetime.now(UTC)


def _timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _next_daily_run(tz_name: str, run_time_local: str, *, now: datetime | None = None) -> datetime:
    current = now or _now()
    local_now = current.astimezone(_timezone(tz_name))
    try:
        hour_text, minute_text = run_time_local.split(":", 1)
        run_time = time(hour=int(hour_text), minute=int(minute_text))
    except (TypeError, ValueError):
        run_time = time(hour=9, minute=0)
    candidate = local_now.replace(
        hour=run_time.hour,
        minute=run_time.minute,
        second=0,
        microsecond=0,
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def find_activation_blocker(session: Session, section: str, index: int) -> dict | None:
    report = build_activation_report(session)
    blockers = [blocker for blocker in report["blockers"] if blocker.get("section") == section]
    if index < 0 or index >= len(blockers):
        return None
    return blockers[index]


def decide_activation_blocker(
    session: Session,
    *,
    actor: User,
    section: str,
    index: int,
    status: str,
) -> dict | None:
    blocker = find_activation_blocker(session, section, index)
    if blocker is None:
        return None
    set_activation_blocker_decision(
        session,
        blocker,
        actor=actor,
        status=status,
        reason="Owner action from Fortuna Activation.",
    )
    return blocker


def get_or_create_daily_autopilot_setting(session: Session, owner: User | None) -> DailyAutopilotSetting:
    owner_id = owner.id if owner else None
    setting = session.scalar(
        select(DailyAutopilotSetting)
        .where(DailyAutopilotSetting.owner_user_id == owner_id)
        .limit(1)
    )
    if setting is None:
        tz_name = owner.timezone if owner and owner.timezone else "UTC"
        setting = DailyAutopilotSetting(
            owner_user_id=owner_id,
            is_enabled=True,
            timezone=tz_name,
            run_time_local="09:00",
            included_actions_json=list(DAILY_AUTOPILOT_ACTIONS),
            next_run_at=_next_daily_run(tz_name, "09:00"),
        )
        session.add(setting)
        session.flush()
        emit_event(
            session,
            actor=owner,
            event_name="daily_autopilot.configured",
            resource_type="daily_autopilot",
            resource_id=str(setting.id),
            payload={"enabled": setting.is_enabled, "timezone": setting.timezone},
        )
    return setting


def daily_autopilot_summary(session: Session, owner: User | None) -> dict:
    setting = get_or_create_daily_autopilot_setting(session, owner)
    return {
        "enabled": setting.is_enabled,
        "timezone": setting.timezone,
        "run_time_local": setting.run_time_local,
        "next_run": setting.next_run_at,
        "last_run": setting.last_run_at,
        "last_result": setting.last_result or "Not run yet",
        "included_actions": list(setting.included_actions_json or DAILY_AUTOPILOT_ACTIONS),
    }


def toggle_daily_autopilot(session: Session, *, actor: User) -> DailyAutopilotSetting:
    setting = get_or_create_daily_autopilot_setting(session, actor)
    setting.is_enabled = not setting.is_enabled
    setting.next_run_at = _next_daily_run(setting.timezone, setting.run_time_local) if setting.is_enabled else None
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="daily_autopilot.toggled",
        resource_type="daily_autopilot",
        resource_id=str(setting.id),
        details={"enabled": setting.is_enabled},
    )
    emit_event(
        session,
        actor=actor,
        event_name="daily_autopilot.toggled",
        resource_type="daily_autopilot",
        resource_id=str(setting.id),
        payload={"enabled": setting.is_enabled},
    )
    return setting


def run_daily_autopilot_now(session: Session, *, actor: User) -> DailyAutopilotSetting:
    setting = get_or_create_daily_autopilot_setting(session, actor)
    workflow = run_daily_autonomous_cycle(session, actor=actor)
    try:
        intelligence_runs = run_full_intelligence_scan(session, actor=actor)
        intelligence_summary = f"Intelligence scan completed with {len(intelligence_runs)} run(s)."
    except Exception as exc:  # pragma: no cover - defensive status capture
        intelligence_summary = f"Intelligence scan failed: {str(exc)[:160]}"
    add_or_update_action(
        session,
        workflow,
        action_type="intelligence_scan",
        status="completed" if "failed" not in intelligence_summary.lower() else "failed",
        priority="normal",
        result_summary=intelligence_summary,
    )
    digest = create_notification_digest(session, actor=actor, purpose="operations", user=actor)
    add_or_update_action(
        session,
        workflow,
        action_type="follow_up_digest",
        status="completed",
        priority="normal",
        result_summary=f"Digest prepared with {digest.item_count} update(s).",
    )
    metrics = automation_metrics(session)
    add_or_update_action(
        session,
        workflow,
        action_type="automation_health_check",
        status="completed",
        priority="normal",
        result_summary=f"Automation success rate is {metrics['automation_success_rate']}%.",
    )
    generate_recommendations(session, actor=actor)
    setting.last_run_at = _now()
    setting.last_result = "Daily autopilot completed."
    setting.next_run_at = _next_daily_run(setting.timezone, setting.run_time_local)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="daily_autopilot.ran",
        resource_type="daily_autopilot",
        resource_id=str(setting.id),
        details={"workflow_id": workflow.id, "included_actions": setting.included_actions_json},
    )
    emit_event(
        session,
        actor=actor,
        event_name="daily_autopilot.ran",
        resource_type="daily_autopilot",
        resource_id=str(setting.id),
        payload={"workflow_id": workflow.id, "result": setting.last_result},
    )
    return setting


def owner_daily_checklist(session: Session, owner: User) -> dict:
    report = build_activation_report(session)
    account_setup_needed = (
        session.scalar(
            select(func.count(Account.id)).where(
                Account.status != "archived",
                (Account.assigned_proxy_id.is_(None)) | (Account.auth_status != "connected"),
            )
        )
        or 0
    )
    opportunities_unassigned = (
        session.scalar(
            select(func.count(Opportunity.id)).where(
                Opportunity.status.in_(("discovered", "reviewing", "approved", "assigned")),
                Opportunity.assigned_to_user_id.is_(None),
            )
        )
        or 0
    )
    followups_due = (
        session.scalar(
            select(func.count(FollowUp.id)).where(FollowUp.status == "pending", FollowUp.due_at <= _now())
        )
        or 0
    )
    approvals_needed = (
        session.scalar(select(func.count(AutomationApproval.id)).where(AutomationApproval.status == "pending"))
        or 0
    )
    critical_incidents = (
        session.scalar(
            select(func.count(Incident.id)).where(
                Incident.status.in_(("open", "investigating")),
                Incident.severity == "critical",
            )
        )
        or 0
    )
    daily = daily_autopilot_summary(session, owner)
    return {
        "readiness_score": report["readiness_score"],
        "top_blockers": report["blockers"][:5],
        "approvals_needed": approvals_needed,
        "critical_incidents": critical_incidents,
        "accounts_needing_setup": account_setup_needed,
        "opportunities_needing_assignment": opportunities_unassigned,
        "followups_due": followups_due,
        "daily_autopilot_enabled": daily["enabled"],
        "daily_autopilot_next_run": daily["next_run"],
        "daily_autopilot_last_result": daily["last_result"],
    }


def team_onboarding_activation(session: Session) -> dict:
    active_team = (
        session.scalar(
            select(func.count(User.id)).where(
                User.status == USER_STATUS_ACTIVE,
                User.is_active.is_(True),
                User.is_owner.is_(False),
            )
        )
        or 0
    )
    pending = session.scalars(
        select(User)
        .where(User.status == "pending", User.is_active.is_(True))
        .order_by(User.created_at, User.id)
    ).all()
    missing_localization = (
        session.scalar(
            select(func.count(User.id)).where(
                User.status == USER_STATUS_ACTIVE,
                User.is_owner.is_(False),
                (User.timezone == "UTC") | (User.country.is_(None)),
            )
        )
        or 0
    )
    return {
        "active_team_count": active_team,
        "pending_users": list(pending),
        "missing_localization": missing_localization,
        "invite_packet": team_invite_packet(),
    }


def proxy_entry_status(session: Session) -> ProxyEntryStatus:
    from app.services.proxies import list_proxies

    real_proxies = list_proxies(session, include_disabled=False)
    total = len(real_proxies)
    real = len(real_proxies)
    missing = (
        session.scalar(
            select(func.count(Account.id)).where(
                Account.status != "archived",
                Account.assigned_proxy_id.is_(None),
            )
        )
        or 0
    )
    if real == 0:
        guidance = "No encrypted proxy is saved yet. Use the Olympix wizard, enter credentials only in the bot flow, and Fortuna OS will store the password encrypted."
    elif missing:
        guidance = f"{missing} account(s) still need a proxy assignment."
    else:
        guidance = "Proxy setup is ready. You can run a health check or assign new accounts as they are added."
    return ProxyEntryStatus(total, real, missing, real == 0, guidance)


def autonomous_action_log(session: Session, *, window: str = "today") -> dict:
    current = _now()
    if window == "7d":
        start = current - timedelta(days=7)
    elif window == "all":
        start = None
    else:
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)

    def _count(model, *criteria) -> int:
        statement = select(func.count(model.id))
        if start is not None and hasattr(model, "created_at"):
            statement = statement.where(model.created_at >= start)
        for criterion in criteria:
            statement = statement.where(criterion)
        return session.scalar(statement) or 0

    action_statement = select(OperationsAction).order_by(desc(OperationsAction.updated_at), desc(OperationsAction.id)).limit(12)
    if start is not None:
        action_statement = action_statement.where(OperationsAction.updated_at >= start)
    recent_actions = list(session.scalars(action_statement).all())
    errors = _count(OperationsAction, OperationsAction.status.in_(("failed", "blocked")))
    return {
        "window": window,
        "actions_created": _count(OperationsAction),
        "tasks_created": _count(Task),
        "recommendations_created": _count(Recommendation),
        "followups_created": _count(FollowUp),
        "automations_run": _count(AutomationRun),
        "errors_detected": errors,
        "recent_actions": [
            sanitize_details(
                {
                    "type": action.action_type.replace("_", " "),
                    "status": action.status,
                    "priority": action.priority,
                    "summary": action.result_summary,
                }
            )
            for action in recent_actions
        ],
    }
