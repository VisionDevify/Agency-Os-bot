from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.help import HELP_FEEDBACK_VALUES, HelpKnowledgeBase, HelpQuestionLog, UISelfTestRun
from app.models.incident import Incident
from app.models.model_brand import ModelBrand
from app.models.opportunity import Opportunity
from app.models.proxy import Proxy, ProxyHealthCheckResult
from app.models.reporting import NotificationDeliveryAttempt, NotificationTarget
from app.models.task import Task
from app.models.user import User
from app.services.agency_activation import build_activation_report
from app.services.audit import sanitize_details
from app.services.auth import audit_action, is_owner, user_has_permission
from app.services.events import emit_event
from app.services.learning import create_learning_event
from app.services.notifications import notification_group_setup_status
from app.services.proxies import latest_proxy_health_check_results, list_proxies, proxy_check_mode


@dataclass(frozen=True)
class HelpBrainResult:
    intent: str
    role: str
    answer: str
    next_action: str
    log_id: int | None = None


HELP_KB_SEEDS: tuple[dict[str, str], ...] = (
    {
        "topic": "owner_start",
        "title": "Owner Start Guide",
        "role_scope": "owner,admin",
        "content": "Start with Start Here. Fortuna will show the next missing setup step and keep deeper tools under Advanced.",
        "related_route": "start_here",
    },
    {
        "topic": "manager_start",
        "title": "Manager Start Guide",
        "role_scope": "manager",
        "content": "Start with Manager Queue. It shows work needing assignment, approval, attention, escalation, and overdue follow-up.",
        "related_route": "manager_queue",
    },
    {
        "topic": "chatter_start",
        "title": "Chatter Start Guide",
        "role_scope": "chatter",
        "content": "Start with My Work or My Opportunities. Review assigned opportunities, use a suggested strategy, then record the human result.",
        "related_route": "my_work",
    },
    {
        "topic": "va_start",
        "title": "VA Start Guide",
        "role_scope": "va",
        "content": "Start with My Accounts and My Tasks. Keep availability updated so managers route work fairly.",
        "related_route": "my_accounts",
    },
    {
        "topic": "model_setup",
        "title": "Model Setup",
        "role_scope": "owner,admin,manager",
        "content": "Create or complete a model with country, timezone, primary platform, accounts, team, creators, and opportunities.",
        "related_route": "agency_activation:models",
    },
    {
        "topic": "account_setup",
        "title": "Account Setup",
        "role_scope": "owner,admin,manager,va",
        "content": "Accounts attach to a model. Store usernames, status, auth state, and proxy assignment only; never paste passwords.",
        "related_route": "accounts",
    },
    {
        "topic": "proxy_setup",
        "title": "Proxy Setup",
        "role_scope": "owner,admin",
        "content": "Use Proxy Vault or Real Check Pilot. Proxy passwords are encrypted and never displayed back in Telegram.",
        "related_route": "proxies:real_check_pilot",
    },
    {
        "topic": "notification_group_setup",
        "title": "Notification Group Setup",
        "role_scope": "owner,admin",
        "content": "Create the five Fortuna groups, add the bot, open each group, then register the current chat with the matching purpose.",
        "related_route": "notification_group_pilot",
    },
    {
        "topic": "opportunity_workflow",
        "title": "Opportunity Workflow",
        "role_scope": "manager,chatter",
        "content": "Opportunities are human-approved work items. Assign them, use strategies, then record posted/skipped/failed results.",
        "related_route": "opportunities:command",
    },
    {
        "topic": "tasks",
        "title": "Tasks",
        "role_scope": "all",
        "content": "Tasks are operational work. Start tasks when work begins, block them if stuck, and complete them when done.",
        "related_route": "tasks",
    },
    {
        "topic": "incidents",
        "title": "Incidents",
        "role_scope": "owner,admin,manager",
        "content": "Incidents track problems that need investigation, assignment, escalation, and resolution notes.",
        "related_route": "incidents",
    },
    {
        "topic": "readiness_score",
        "title": "Readiness Score",
        "role_scope": "owner,admin,manager",
        "content": "Readiness measures whether models, accounts, teams, creators, opportunities, notifications, and proxies are prepared.",
        "related_route": "coo:readiness",
    },
    {
        "topic": "daily_autopilot",
        "title": "Daily Autopilot",
        "role_scope": "owner,admin",
        "content": "Daily Autopilot runs safe scans and summaries. It does not perform risky actions without approval.",
        "related_route": "automations:daily_autopilot",
    },
    {
        "topic": "fortuna_hq",
        "title": "Fortuna HQ",
        "role_scope": "owner,admin",
        "content": "Fortuna HQ gives owners a concise command center: health, priorities, readiness, risks, and recommendations.",
        "related_route": "executive_mode",
    },
    {
        "topic": "what_fortuna_did",
        "title": "What Fortuna Did",
        "role_scope": "owner,admin,manager",
        "content": "What Fortuna Did lists scans, actions, recommendations, follow-ups, and automation activity.",
        "related_route": "fortuna_action_log",
    },
)


def _now() -> datetime:
    return datetime.now(UTC)


def _role_names(user: User | None) -> set[str]:
    return {role.name for role in user.roles} if user is not None else set()


def _role_label(user: User | None) -> str:
    return ", ".join(sorted(_role_names(user))) or "Viewer"


def _adminish(user: User | None) -> bool:
    if user is None:
        return False
    return is_owner(user) or user_has_permission(user, "manage_reports") or user_has_permission(user, "manage_users")


def _safe_summary(text: str, limit: int = 500) -> str:
    blocked = ("TELEGRAM_BOT_TOKEN", "DATABASE_URL", "REDIS_URL", "APP_SECRET_KEY", "ENCRYPTION_KEY", "password", "secret")
    cleaned = text
    for marker in blocked:
        cleaned = cleaned.replace(marker, "[redacted]")
        cleaned = cleaned.replace(marker.lower(), "[redacted]")
    return cleaned[:limit]


def seed_help_knowledge_base(session: Session) -> None:
    for seed in HELP_KB_SEEDS:
        article = session.scalar(select(HelpKnowledgeBase).where(HelpKnowledgeBase.topic == seed["topic"]))
        if article is None:
            article = HelpKnowledgeBase(**seed)
            session.add(article)
        else:
            article.title = seed["title"]
            article.role_scope = seed["role_scope"]
            article.content = seed["content"]
            article.related_route = seed["related_route"]
    session.flush()


def help_article_count(session: Session) -> int:
    return session.scalar(select(func.count(HelpKnowledgeBase.id))) or 0


def detect_help_intent(question: str) -> str:
    text = question.casefold()
    if "postgres" in text or "durable" in text or "persistence" in text:
        return "postgres_explained"
    if "broken" in text or "bot down" in text or "not working" in text:
        return "system_troubleshooting"
    if "where" in text and "proxy vault" in text:
        return "proxy_where"
    if "safe" in text and ("next" in text or "do" in text):
        return "safe_next"
    if "crowded" in text or "overwhelming" in text or "too much" in text:
        return "screen_crowded"
    if "advanced mode" in text or "simple mode" in text or "switch mode" in text:
        return "advanced_mode"
    if "simulated" in text and "proxy" in text:
        return "proxy_simulated"
    if "real check" in text and ("off" in text or "disabled" in text):
        return "proxy_real_off"
    if "paste" in text and "proxy" in text:
        return "proxy_paste"
    if "session suffix" in text or ("session" in text and "proxy" in text):
        return "proxy_session_suffix"
    if "rotation" in text or ("rotate" in text and "proxy" in text):
        return "proxy_rotation"
    if "password" in text and "proxy" in text:
        return "proxy_password_hidden"
    if "assign" in text and "proxy" in text and "account" in text:
        return "proxy_assign"
    if "fix first" in text or "what should i fix" in text or "finish setup" in text:
        return "readiness_low"
    if "register" in text and ("notification" in text or "group" in text):
        return "notification_groups"
    if "proxy" in text or "assign proxy" in text:
        return "proxy_setup"
    if "readiness" in text or "stopping" in text or "ready" in text:
        return "readiness_low"
    if "what did fortuna" in text or "did today" in text:
        return "what_fortuna_did"
    if "start" in text or "where do i" in text:
        return "where_start"
    if "next" in text:
        return "next_action"
    if "can't" in text or "cant" in text or "access" in text or "why can't" in text:
        return "access_denied"
    if "model" in text:
        return "model_setup"
    if "account" in text:
        return "account_setup"
    if "task" in text:
        return "complete_task"
    if "opportun" in text:
        return "opportunity"
    if "warning" in text or "mean" in text:
        return "warning_meaning"
    if "who" in text and "help" in text:
        return "ask_person"
    return "general"


def _article(session: Session, topic: str) -> HelpKnowledgeBase | None:
    return session.scalar(select(HelpKnowledgeBase).where(HelpKnowledgeBase.topic == topic))


def _readiness_answer(session: Session, user: User | None) -> tuple[str, str]:
    if not _adminish(user):
        return (
            "Readiness is managed by owners and managers. Ask your manager to open Fortuna Activation, or use My Work for your assigned items.",
            "my_work",
        )
    report = build_activation_report(session)
    blockers = list(report.get("blockers", []))[:5]
    score = int(report.get("readiness_score", 0))
    if not blockers:
        return (
            f"Readiness is {score}%. Fortuna does not see major setup blockers right now.",
            "agency_activation",
        )
    lines = [f"Readiness is {score}%. The top blockers are:"]
    for blocker in blockers:
        title = blocker.get("title") or blocker.get("label") or "Setup item"
        lines.append(f"- {title}")
    lines.append("Use Fortuna Activation -> Fix Top Blocker to move through them one at a time.")
    return "\n".join(lines), "agency_activation"


def _user_work_answer(session: Session, user: User | None) -> tuple[str, str]:
    if user is None:
        return "Open /start and complete onboarding first.", "menu"
    if _adminish(user):
        report = build_activation_report(session)
        blockers = report.get("blockers", [])
        if blockers:
            first = blockers[0]
            return (
                f"Your safest next move is: {first['title']}. {first['description']} "
                "Open Start Here and fix one item at a time.",
                first.get("action_page") or "start_here",
            )
    open_tasks = session.scalar(
        select(func.count(Task.id)).where(Task.assigned_to_user_id == user.id, Task.status.in_(("open", "in_progress", "blocked")))
    ) or 0
    open_opportunities = session.scalar(
        select(func.count(Opportunity.id)).where(
            Opportunity.assigned_to_user_id == user.id,
            Opportunity.status.in_(("discovered", "reviewing", "assigned")),
        )
    ) or 0
    open_incidents = session.scalar(
        select(func.count(Incident.id)).where(
            Incident.assigned_to_user_id == user.id,
            Incident.status.in_(("open", "investigating")),
        )
    ) or 0
    if open_tasks or open_opportunities or open_incidents:
        return (
            f"Today, start with your assigned work: {open_tasks} task(s), {open_opportunities} opportunity item(s), and {open_incidents} incident(s).",
            "my_work",
        )
    if _adminish(user):
        return "No direct work is assigned to you. Open Fortuna HQ or Manager Queue to clear setup and routing gaps.", "executive_mode"
    return "No direct work is assigned yet. Keep Availability updated and ask your manager if you should be assigned to a model.", "availability"


def _notification_answer(session: Session, user: User | None) -> tuple[str, str]:
    if not _adminish(user):
        return "Notification groups are managed by Owner/Admin. Ask them to register the group from inside the Telegram group.", "help"
    statuses = notification_group_setup_status(session)
    missing = [status.label for status in statuses if not status.configured]
    if missing:
        missing_text = ", ".join(missing)
        answer = (
            "To register notification groups, create the Fortuna groups, add @FortunaSolstice_Bot, open each group, "
            "then tap Register This Chat. Missing right now: "
            f"{missing_text}."
        )
    else:
        answer = "All notification purposes have an active target. Use Test Sandbox before sending real group alerts."
    return answer, "notification_group_pilot"


def _proxy_answer(session: Session, user: User | None) -> tuple[str, str]:
    if not (user_has_permission(user, "manage_proxies") or is_owner(user)):
        return "Proxy setup is restricted. Ask an Owner/Admin to assign or check proxies; you can continue with your visible tasks.", "help"
    proxy_count = session.scalar(select(func.count(Proxy.id))) or 0
    if not proxy_count:
        return "No proxies are saved yet. Open Proxy Vault -> Add Proxy -> Paste Full Proxy String. Paste host:port:username:password only in the bot flow.", "proxies:add"
    enabled = 0
    for proxy in list_proxies(session):
        if proxy_check_mode(proxy).real_health_enabled:
            enabled += 1
    return (
        f"{proxy_count} proxy record(s) exist. {enabled} have real checks enabled. Use Real Check Pilot to pick one proxy and run a safe test.",
        "proxies",
    )


def _admin_status_answer(session: Session, user: User | None) -> tuple[str, str]:
    if not _adminish(user):
        return "Production status is owner/admin-only. If something feels broken, ask a manager to check Settings -> Production Observability.", "help"
    latest_audit = session.scalar(select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(1))
    latest_event = session.scalar(select(EventLog).order_by(desc(EventLog.created_at), desc(EventLog.id)).limit(1))
    answer = (
        "Production status is checked from Settings -> Production Observability. "
        f"Latest audit: {latest_audit.action if latest_audit else 'none'}. "
        f"Latest event: {latest_event.event_type if latest_event else 'none'}."
    )
    return answer, "production_observability"


def help_brain_answer(
    session: Session,
    user: User | None,
    *,
    question: str,
    current_page: str | None = None,
) -> HelpBrainResult:
    seed_help_knowledge_base(session)
    intent = detect_help_intent(question)
    role = _role_label(user)
    next_action = current_page or "help"

    if intent == "readiness_low":
        answer, next_action = _readiness_answer(session, user)
    elif intent == "postgres_explained":
        answer = (
            "Postgres is Fortuna's durable production database. It keeps users, setup, audit logs, proxies, "
            "recommendations, and learning records safe across Railway deploys and restarts. SQLite fallback is emergency-only."
        )
        next_action = "production_observability" if _adminish(user) else "help"
    elif intent == "system_troubleshooting":
        if _adminish(user):
            answer = (
                "If something feels broken, check Settings -> Production Observability first. "
                "Then run /integrity and /botstatus to confirm durable storage, Redis, and duplicate polling."
            )
            next_action = "production_observability"
        else:
            answer = "Tell a manager which button or screen failed. Production diagnostics are owner/admin-only."
            next_action = "help"
    elif intent == "proxy_where":
        answer = "Proxy Vault is on Owner Home. Tap Proxy Vault, then Paste Olympix Proxy String or Add Proxy."
        next_action = "proxies"
    elif intent == "safe_next":
        answer, next_action = _user_work_answer(session, user)
    elif intent == "screen_crowded":
        answer = (
            "Fortuna now starts in Simple Mode so the daily view stays calm. "
            "Open Advanced only when you need deeper controls like Intelligence, Automations, Proxy Vault, Reports, or Observability."
        )
        next_action = "menu"
    elif intent == "advanced_mode":
        answer = "Use Owner Home -> Advanced to open deeper controls. Tap Simple Mode from Advanced to return to the calmer daily home."
        next_action = "owner_advanced"
    elif intent == "proxy_simulated":
        answer = (
            "Simulated proxy checks are safe placeholders. They do not contact the provider. "
            "Real checks stay off until an owner enables them for a saved proxy."
        )
        next_action = "proxies"
    elif intent == "proxy_real_off":
        answer = (
            "Real checks are off by default so Fortuna never contacts an external proxy provider without owner approval. "
            "Open Proxy Detail -> Advanced -> Enable Real Checks when you are ready to test a saved proxy."
        )
        next_action = "proxies"
    elif intent == "proxy_paste":
        answer = (
            "Yes. Open Proxy Vault -> Add Proxy -> Paste Full Proxy String, then paste host:port:username:password. "
            "Fortuna extracts the Olympix session suffix after session_, encrypts the password, and only shows masked details."
        )
        next_action = "proxies:olympix:paste"
    elif intent == "proxy_session_suffix":
        answer = (
            "The session suffix is the part after session_ in your Olympix username. "
            "That suffix controls the active proxy session/IP. Fortuna stores it separately so rotation is simple."
        )
        next_action = "proxies"
    elif intent == "proxy_rotation":
        answer = (
            "Rotation changes only the session suffix after session_. Olympix should treat the new suffix as a fresh session/IP. "
            "Fortuna saves the previous suffix so you can roll back."
        )
        next_action = "proxies"
    elif intent == "proxy_password_hidden":
        answer = (
            "Fortuna hides proxy passwords by design. The password is encrypted after you paste it and is never shown again in Telegram, logs, audits, or help screens."
        )
        next_action = "proxies"
    elif intent == "proxy_assign":
        answer = (
            "Open the account, then choose Assign Best Proxy or Choose Proxy. If no proxy exists yet, tap Add Proxy First and use the one-paste Olympix flow."
        )
        next_action = "accounts:attention"
    elif intent == "notification_groups":
        answer, next_action = _notification_answer(session, user)
    elif intent == "proxy_setup":
        answer, next_action = _proxy_answer(session, user)
    elif intent == "what_fortuna_did":
        if _adminish(user):
            answer = "Open What Fortuna Did to review scans, recommendations, follow-ups, automations, and errors Fortuna recorded today."
            next_action = "fortuna_action_log"
        else:
            answer = "You can see your own work from My Work. Fortuna's full action log is for managers and owners."
            next_action = "my_work"
    elif intent == "next_action":
        answer, next_action = _user_work_answer(session, user)
    elif intent == "where_start":
        if is_owner(user) or user_has_permission(user, "manage_accounts"):
            article = _article(session, "owner_start")
            answer = article.content if article else "Start with Fortuna HQ and Fortuna Activation."
            next_action = "executive_mode"
        elif "Manager" in _role_names(user):
            article = _article(session, "manager_start")
            answer = article.content if article else "Start with Manager Queue."
            next_action = "manager_queue"
        elif "VA" in _role_names(user):
            article = _article(session, "va_start")
            answer = article.content if article else "Start with My Accounts and My Tasks."
            next_action = "my_accounts"
        else:
            article = _article(session, "chatter_start")
            answer = article.content if article else "Start with My Work."
            next_action = "my_work"
    elif intent == "model_setup":
        if "edit" in question.casefold():
            answer = (
                "Open Models -> View Models -> choose the model -> Edit Model. "
                "Use Edit Name, Edit Stage Name, Edit Country, Edit Timezone, or Edit Notes."
            )
            next_action = "models:view"
        elif "first" in question.casefold() or "create" in question.casefold():
            answer = "Open Setup Fortuna -> Create First Model. Send display name, stage name, country, timezone, and optional notes."
            next_action = "setup:wizard:model"
        else:
            article = _article(session, "model_setup")
            answer = article.content if article else "Complete the model profile from Fortuna Activation."
            next_action = "agency_activation:models"
    elif intent == "account_setup":
        article = _article(session, "account_setup")
        answer = article.content if article else "Add accounts from Setup Fortuna or Account pages."
        next_action = "accounts"
    elif intent == "opportunity":
        article = _article(session, "opportunity_workflow")
        answer = article.content if article else "Use opportunities from your role workspace and record the result."
        next_action = "my_opportunities" if "Chatter" in _role_names(user) else "opportunities:command"
    elif intent == "complete_task":
        article = _article(session, "tasks")
        answer = article.content if article else "Open My Tasks, start the task, then complete it when done."
        next_action = "tasks:my"
    elif intent == "access_denied":
        answer = "If you cannot see a page, your role may not include that permission yet. Complete onboarding, then ask a manager to approve you or assign the correct role."
        next_action = "help"
    elif "production" in question.casefold() or "bot down" in question.casefold():
        answer, next_action = _admin_status_answer(session, user)
    elif intent == "warning_meaning":
        answer = "A warning means Fortuna sees something that should be reviewed, but it is not always an emergency. Open the related detail page and follow the recommended next action."
        next_action = current_page or "help"
    elif intent == "ask_person":
        answer = "Ask your manager first. If it involves owner approvals, production status, or high-risk proxy actions, your manager should route it to Owner/Admin."
        next_action = "help"
    else:
        answer = "Fortuna can help with setup, tasks, opportunities, proxies, notifications, and readiness. Ask a simple question like: What should I do next?"
        next_action = current_page or "help"

    log = HelpQuestionLog(
        user_id=user.id if user else None,
        question=_safe_summary(question, 1000),
        detected_intent=intent,
        answer_summary=_safe_summary(answer),
    )
    session.add(log)
    session.flush()
    audit_action(
        session,
        actor=user,
        action="help_brain.answered",
        resource_type="help_question_log",
        resource_id=str(log.id),
        details={"intent": intent, "next_action": next_action},
    )
    emit_event(
        session,
        actor=user,
        event_name="help_brain.answered",
        resource_type="help_question_log",
        resource_id=str(log.id),
        payload={"intent": intent, "next_action": next_action},
    )
    return HelpBrainResult(intent=intent, role=role, answer=answer, next_action=next_action, log_id=log.id)


def record_help_feedback(session: Session, *, log_id: int, feedback: str, actor: User | None) -> HelpQuestionLog:
    if feedback not in HELP_FEEDBACK_VALUES:
        raise ValueError(f"Invalid help feedback: {feedback}")
    log = session.get(HelpQuestionLog, log_id)
    if log is None:
        raise ValueError("Help question log not found")
    log.feedback = feedback
    outcome = "success" if feedback == "helpful" else "partial" if feedback == "still_confused" else "failure"
    create_learning_event(
        session,
        actor=actor,
        event_type=f"help.feedback.{feedback}",
        source_type="system",
        source_id=log.id,
        entity_type="help_question_log",
        entity_id=log.id,
        outcome=outcome,
        severity="warning" if feedback != "helpful" else "info",
        summary=f"Help Brain feedback recorded: {feedback}.",
        details={"intent": log.detected_intent, "feedback": feedback},
        confidence_score=82 if feedback == "helpful" else 55,
    )
    audit_action(
        session,
        actor=actor,
        action="help.feedback_recorded",
        resource_type="help_question_log",
        resource_id=str(log.id),
        details={"feedback": feedback, "intent": log.detected_intent},
    )
    return log


def help_questions_today(session: Session) -> tuple[int, int]:
    start = _now() - timedelta(hours=24)
    total = session.scalar(select(func.count(HelpQuestionLog.id)).where(HelpQuestionLog.created_at >= start)) or 0
    confused = (
        session.scalar(
            select(func.count(HelpQuestionLog.id)).where(
                HelpQuestionLog.created_at >= start,
                HelpQuestionLog.feedback.in_(("not_helpful", "still_confused")),
            )
        )
        or 0
    )
    return total, confused


def notification_pilot_status(session: Session) -> dict:
    statuses = notification_group_setup_status(session)
    configured = sum(1 for status in statuses if status.configured)
    latest = session.scalar(
        select(NotificationDeliveryAttempt)
        .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
        .limit(1)
    )
    return {
        "configured": configured,
        "required": len(statuses),
        "ready": configured == len(statuses),
        "statuses": statuses,
        "latest_status": latest.status if latest else "none",
        "latest_at": latest.attempted_at if latest else None,
    }


def proxy_pilot_status(session: Session) -> dict:
    proxies = list_proxies(session)
    enabled = [proxy for proxy in proxies if proxy_check_mode(proxy).real_health_enabled]
    latest_real = session.scalar(
        select(ProxyHealthCheckResult)
        .where(ProxyHealthCheckResult.check_type.in_(("connectivity", "location", "full")))
        .order_by(desc(ProxyHealthCheckResult.created_at), desc(ProxyHealthCheckResult.id))
        .limit(1)
    )
    return {
        "total": len(proxies),
        "enabled": len(enabled),
        "ready": bool(enabled),
        "latest_status": latest_real.status if latest_real else "none",
        "latest_at": latest_real.created_at if latest_real else None,
    }


def _screen_is_safe(text: str) -> list[str]:
    lowered = text.casefold()
    warnings: list[str] = []
    forbidden = (
        "telegram_bot_token",
        "app_secret_key",
        "encryption_key",
        "database_url",
        "redis_url",
        "encrypted_password",
        "traceback",
        "secret",
        "password: super",
        "super-secret",
    )
    for marker in forbidden:
        if marker in lowered:
            warnings.append(f"forbidden text: {marker}")
    if "{" in text or "}" in text:
        warnings.append("possible raw JSON/dict output")
    return warnings


def run_ui_self_test(session: Session, *, actor: User | None) -> UISelfTestRun:
    if not is_owner(actor):
        audit_action(
            session,
            actor=actor,
            action="access.denied",
            resource_type="ui_self_test",
            status="denied",
            details={"permission": "owner"},
        )
        raise PermissionError("UI Self-Test is owner-only")

    from app.bot.navigation import screen_for_page
    from app.services.permissions import PermissionPrincipal, RoleName

    principal = PermissionPrincipal(
        telegram_id=actor.telegram_id,
        is_owner=True,
        role=RoleName.OWNER,
    )
    pages = (
        "menu",
        "start_here",
        "first_workspace",
        "executive_mode",
        "agency_activation",
        "models",
        "accounts",
        "proxies",
        "proxies:real_check_pilot",
        "notification_group_pilot",
        "help",
        "help_copilot",
        "settings",
        "production_observability",
    )
    failures: list[str] = []
    warnings: list[str] = []
    checked = 0
    for page in pages:
        try:
            screen = screen_for_page(page, principal, session=session, user=actor)
            checked += 1
            if not screen.text.strip():
                failures.append(f"{page}: empty text")
            if screen.reply_markup is None:
                warnings.append(f"{page}: no buttons")
            for warning in _screen_is_safe(screen.text):
                warnings.append(f"{page}: {warning}")
        except Exception as exc:
            failures.append(f"{page}: {type(exc).__name__}")

    status = "failed" if failures else "warning" if warnings else "passed"
    run = UISelfTestRun(
        requested_by_user_id=actor.id,
        status=status,
        screens_checked=checked,
        failures_json=sanitize_details(failures),
        warnings_json=sanitize_details(warnings),
        created_at=_now(),
    )
    session.add(run)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="ui_self_test.run",
        resource_type="ui_self_test_run",
        resource_id=str(run.id),
        status=status,
        details={"screens_checked": checked, "failure_count": len(failures), "warning_count": len(warnings)},
    )
    emit_event(
        session,
        actor=actor,
        event_name="ui_self_test.run",
        resource_type="ui_self_test_run",
        resource_id=str(run.id),
        status=status,
        payload={"screens_checked": checked, "failure_count": len(failures), "warning_count": len(warnings)},
    )
    return run


def latest_ui_self_test_run(session: Session) -> UISelfTestRun | None:
    return session.scalar(select(UISelfTestRun).order_by(desc(UISelfTestRun.created_at), desc(UISelfTestRun.id)).limit(1))


def recent_help_questions(session: Session, *, limit: int = 5) -> list[HelpQuestionLog]:
    return list(
        session.scalars(
            select(HelpQuestionLog).order_by(desc(HelpQuestionLog.created_at), desc(HelpQuestionLog.id)).limit(limit)
        ).all()
    )


def latest_proxy_pilot_result(session: Session, proxy: Proxy) -> ProxyHealthCheckResult | None:
    results = latest_proxy_health_check_results(session, proxy, limit=1)
    return results[0] if results else None
