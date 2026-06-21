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
from app.services.audit import sanitize_details, sanitize_value
from app.services.auth import audit_action, is_owner, user_has_permission
from app.services.events import emit_event
from app.services.learning import create_learning_event
from app.services.notifications import notification_group_setup_status
from app.services.productization import best_next_action
from app.services.proxies import latest_proxy_health_check_results, list_proxies, proxy_check_mode
from app.services.recovery import recovery_risk_assessment


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
        "content": "Use three simple targets: Fortuna HQ for owner alerts, Fortuna Ops for team operations, and Fortuna Alerts for creator/own-post action alerts.",
        "related_route": "notification_group_pilot",
    },
    {
        "topic": "creator_alerts",
        "title": "Creator Alerts",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Creator alerts are manually entered post references. Fortuna creates an opportunity, suggests comment strategies, and routes the alert for human review only.",
        "related_route": "opportunities:creators",
    },
    {
        "topic": "opportunity_workflow",
        "title": "Opportunity Workflow",
        "role_scope": "manager,chatter",
        "content": "Opportunities are human-approved work items. Assign them, use strategies, then record posted/skipped/failed results.",
        "related_route": "opportunities:command",
    },
    {
        "topic": "social_opportunity_intelligence",
        "title": "Social Opportunity Intelligence",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Use manual URLs, official APIs, approved exports, or approved captures only. Fortuna scores public opportunities and suggests angles; humans approve and post manually.",
        "related_route": "opportunities:score",
    },
    {
        "topic": "social_discovery_mode",
        "title": "Discovery Mode",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Discovery Mode helps Fortuna turn approved manual sources, public post URLs, official APIs, or approved exports into leads for human review. It does not scrape private data or post for you.",
        "related_route": "opportunities:discovery",
    },
    {
        "topic": "social_comment_angles",
        "title": "Comment Angles",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Comment angles are safe idea starters like curiosity, relatable, playful, question, or soft CTA. A human reviews the idea and decides what to write manually.",
        "related_route": "opportunities:discovery",
    },
    {
        "topic": "comment_profile_leads",
        "title": "Comment Profile Leads",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Comment profile leads are public profiles Fortuna noticed in approved comment data. They are suggestions for manual review only; Fortuna never follows, likes, or comments for you.",
        "related_route": "opportunities:profiles",
    },
    {
        "topic": "comment_section_review",
        "title": "Comment Section Review",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Comment Section Review looks at manually entered or approved public comment data and points you to profiles worth checking by hand.",
        "related_route": "opportunities:comments",
    },
    {
        "topic": "safe_social_data",
        "title": "Safe Social Data",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Safe social data is manually entered, officially provided, approved export data, or compliant public-source data. Do not enter private data, secrets, scraped private content, or anything from rate-limit evasion.",
        "related_route": "opportunities:discovery",
    },
    {
        "topic": "social_learning",
        "title": "Social Learning",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Fortuna learns from manual results: reviewed, skipped, converted, clicks, replies, profile visits, conversions, and notes. That improves source, niche, timing, angle, and chatter recommendations.",
        "related_route": "intelligence:learning",
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
    {
        "topic": "recovery_center",
        "title": "Recovery Center",
        "role_scope": "owner,admin",
        "content": "Recovery Center shows whether backups and restore tests are actually recorded. If evidence is missing, Fortuna says not set up or not tested yet.",
        "related_route": "recovery_center",
    },
    {
        "topic": "disaster_recovery",
        "title": "Disaster Recovery",
        "role_scope": "owner,admin",
        "content": "If Railway breaks, rebuild Fortuna from the repo, environment secrets, Postgres, Redis, and the latest encrypted backup.",
        "related_route": "recovery:disaster_plan",
    },
    {
        "topic": "restore_test",
        "title": "Restore Tests",
        "role_scope": "owner,admin",
        "content": "A restore test proves a backup can be verified or restored. Verification alone is useful, but a full test database restore is stronger evidence.",
        "related_route": "recovery:restore:test",
    },
    {
        "topic": "platform_connections",
        "title": "Platform Connections",
        "role_scope": "owner,admin,manager",
        "content": "Platform Connections shows public website reachability, approved login/API/session connection, stats access, notification routing, and activation readiness as separate evidence-backed states.",
        "related_route": "platforms",
    },
    {
        "topic": "platform_reachable_vs_connected",
        "title": "Reachable Versus Connected",
        "role_scope": "owner,admin,manager",
        "content": "Reachable only means Fortuna can access the public website. Connected means you have approved a login/API/session method and Fortuna verified it.",
        "related_route": "platforms",
    },
    {
        "topic": "platform_stats_waiting",
        "title": "Platform Stats Waiting",
        "role_scope": "owner,admin,manager",
        "content": "Stats wait for connection because follower, reach, engagement, and account metrics require a verified owner-approved connection. Fortuna does not fabricate placeholder metrics.",
        "related_route": "platforms",
    },
    {
        "topic": "platform_notifications",
        "title": "Platform Notifications",
        "role_scope": "owner,admin,manager",
        "content": "Platform notifications route approved alerts to Fortuna HQ, Ops, or Alerts targets. Missing targets are setup items, not failures.",
        "related_route": "platforms:notifications",
    },
    {
        "topic": "opportunity_prediction",
        "title": "Opportunity Prediction",
        "role_scope": "owner,admin,manager,chatter",
        "content": "Fortuna ranks opportunities from source history, niche fit, timing, angle performance, team workload, and manual results. It never auto-posts.",
        "related_route": "opportunities:best",
    },
    {
        "topic": "team_performance_intelligence",
        "title": "Team Performance Intelligence",
        "role_scope": "owner,admin,manager",
        "content": "Team Intelligence uses task and opportunity outcomes to suggest who is available, overloaded, or a good fit for new work.",
        "related_route": "team_intelligence",
    },
    {
        "topic": "coo_briefing",
        "title": "COO Briefing",
        "role_scope": "owner,admin,manager",
        "content": "COO Briefing turns system truth, recovery, notifications, platforms, opportunities, and recent activity into one top priority and one next best move.",
        "related_route": "coo:briefing",
    },
    {
        "topic": "decision_priorities",
        "title": "Decision Priorities",
        "role_scope": "owner,admin,manager",
        "content": "Fortuna ranks decisions using evidence, urgency, risk, reversibility, business impact, and whether owner action is required. It recommends what matters first, but humans still decide.",
        "related_route": "coo:briefing",
    },
    {
        "topic": "decision_confidence",
        "title": "Decision Confidence",
        "role_scope": "owner,admin,manager",
        "content": "Confidence tells you how strong the evidence is. High confidence comes from current checks or recent records. Low confidence means Fortuna needs more proof or owner review.",
        "related_route": "decision:details",
    },
    {
        "topic": "decision_can_wait",
        "title": "Can Wait",
        "role_scope": "owner,admin,manager",
        "content": "Can Wait means the item is prepared or useful later, but it should not distract from the current top priority.",
        "related_route": "coo:briefing",
    },
    {
        "topic": "decision_memory",
        "title": "Decision Memory",
        "role_scope": "owner,admin,manager",
        "content": "Decision Memory records which recommendations were shown, opened, acted on, dismissed, and resolved. It learns from evidence and owner feedback without hiding critical safety issues.",
        "related_route": "decision:memory",
    },
    {
        "topic": "decision_feedback",
        "title": "Decision Feedback",
        "role_scope": "owner,admin,manager",
        "content": "Helpful, Not Helpful, Remind Later, and Dismiss adjust future ranking gradually. They do not automatically resolve the underlying issue.",
        "related_route": "decision:details",
    },
    {
        "topic": "decision_quality",
        "title": "Decision Quality",
        "role_scope": "owner,admin,manager",
        "content": "Decision Quality checks whether Fortuna's recommendations are evidence-backed, specific, useful, and correctly prioritized. If the check is unavailable, COO Briefing still uses current evidence.",
        "related_route": "intelligence:quality",
    },
    {
        "topic": "recommendation_accuracy",
        "title": "Recommendation Accuracy",
        "role_scope": "owner,admin,manager",
        "content": "Recommendation Accuracy compares what Fortuna suggested with later evidence from Decision Memory and system records. It does not invent outcomes.",
        "related_route": "intelligence:quality",
    },
    {
        "topic": "confidence_accuracy",
        "title": "Confidence Accuracy",
        "role_scope": "owner,admin,manager",
        "content": "Confidence Accuracy checks whether high, medium, and low confidence matched the strength of evidence and later outcomes. Weak evidence should never inflate confidence.",
        "related_route": "intelligence:quality",
    },
    {
        "topic": "decision_quality_trends",
        "title": "Decision Quality Trends",
        "role_scope": "owner,admin,manager",
        "content": "Decision Quality Trends compare Decision Memory outcomes by category over time. Improving means recommendations are being acted on or resolved with evidence; insufficient data means Fortuna does not have enough records yet.",
        "related_route": "intelligence:quality:trends",
    },
    {
        "topic": "predictive_coo",
        "title": "Predictive COO",
        "role_scope": "owner,admin,manager",
        "content": "Predictive COO makes conservative, evidence-backed guesses about what may matter next. Predictions are not facts and never replace current verified status.",
        "related_route": "prediction:preview",
    },
    {
        "topic": "reality_check",
        "title": "Reality Check",
        "role_scope": "owner,admin,manager",
        "content": "Reality Check compares predictions against later evidence. Fortuna can be wrong, and calibration exists so it can improve instead of sounding certain without proof.",
        "related_route": "reality:check",
    },
    {
        "topic": "prediction_outcomes",
        "title": "Prediction Outcomes",
        "role_scope": "owner,admin,manager",
        "content": "Prediction outcomes stay pending until later evidence proves them correct, proves them wrong, or shows there is not enough evidence.",
        "related_route": "reality:outcomes",
    },
    {
        "topic": "confidence_calibration",
        "title": "Confidence Calibration",
        "role_scope": "owner,admin,manager",
        "content": "Confidence Calibration checks whether low, medium, and high confidence predictions matched real outcomes. It can reduce future confidence wording when Fortuna is overconfident.",
        "related_route": "reality:calibration",
    },
    {
        "topic": "evidence_capture",
        "title": "Evidence",
        "role_scope": "owner,admin,manager",
        "content": "Evidence is a traceable note, validation, system record, reference, or operational outcome that helps Fortuna compare predictions with reality.",
        "related_route": "evidence:notes",
    },
    {
        "topic": "owner_validation",
        "title": "Owner Validation",
        "role_scope": "owner,admin,manager",
        "content": "Owner Validation records whether a prediction looked correct, incorrect, partially correct, or too early to tell. It helps Fortuna learn, but it does not override system truth by itself.",
        "related_route": "decision:review",
    },
    {
        "topic": "knowledge_memory",
        "title": "Knowledge Memory",
        "role_scope": "owner,admin,manager",
        "content": "Knowledge Memory stores durable lessons that came from evidence, such as recovery setup lessons or notification rollout notes.",
        "related_route": "knowledge:memory",
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
    if "coo briefing" in text or ("briefing" in text and "coo" in text):
        return "coo_briefing"
    if "decide priorities" in text or "decides priorities" in text or "rank decisions" in text or "decide priority" in text:
        return "decision_priorities"
    if "why" in text and "recovery" in text and "top priority" in text:
        return "decision_recovery_priority"
    if "why" in text and "platform" in text and "wait" in text:
        return "decision_platforms_wait"
    if "decision quality trend" in text or ("trend" in text and "decision" in text):
        return "decision_quality_trends"
    if "decision quality" in text or "is fortuna right" in text:
        return "decision_quality"
    if "insufficient data" in text:
        return "trend_insufficient_data"
    if "improving" in text and ("trend" in text or "mean" in text):
        return "trend_improving"
    if "predictive coo" in text or ("prediction" in text and "coo" in text):
        return "predictive_coo"
    if "reality check" in text or "can fortuna be wrong" in text:
        return "reality_check"
    if "proven correct" in text:
        return "prediction_proven_correct"
    if "proven wrong" in text:
        return "prediction_proven_wrong"
    if "not enough evidence" in text:
        return "prediction_not_enough_evidence"
    if "prediction" in text and "pending" in text:
        return "prediction_pending"
    if "owner feedback" in text and "prove" in text:
        return "owner_feedback_prediction_proof"
    if "confidence calibration" in text or ("calibration" in text and "confidence" in text):
        return "confidence_calibration"
    if "owner validation" in text or ("validate" in text and "owner" in text):
        return "owner_validation"
    if "partially correct" in text or "partial correct" in text:
        return "partially_correct"
    if "knowledge memory" in text or "institutional knowledge" in text:
        return "knowledge_memory"
    if "what is evidence" in text or ("evidence" in text and "learn" in text):
        return "evidence_capture"
    if "feedback" in text and ("override" in text or "system record" in text or "system truth" in text):
        return "feedback_override"
    if "predictions facts" in text or ("are predictions" in text and "facts" in text):
        return "prediction_not_facts"
    if "restore testing" in text and ("likely next" in text or "prediction" in text):
        return "prediction_restore_testing"
    if "train" in text and "prediction" in text:
        return "prediction_training"
    if "recommendation accuracy" in text or ("accuracy" in text and "recommendation" in text):
        return "recommendation_accuracy"
    if "confidence accuracy" in text or ("accuracy" in text and "confidence" in text):
        return "confidence_accuracy"
    if "confidence" in text and ("mean" in text or "decision" in text):
        return "decision_confidence"
    if "can wait" in text:
        return "decision_can_wait"
    if "learn" in text and "decision" in text:
        return "decision_learning"
    if "decision memory" in text or ("memory" in text and "recommendation" in text):
        return "decision_memory"
    if "helpful" in text or "not helpful" in text or "dismiss" in text or "remind later" in text:
        return "decision_feedback"
    if "act automatically" in text or ("fortuna" in text and "automatically" in text and ("decision" in text or "prediction" in text)):
        return "decision_human_approval"
    if "platform connection" in text or "platform connections" in text:
        return "platform_connections"
    if "reachable" in text and "connected" in text:
        return "platform_reachable_vs_connected"
    if "instagram" in text and ("reachable" in text or "connected" in text):
        return "platform_reachable_vs_connected"
    if "stats waiting" in text or "waiting for connection" in text or ("access" in text and "account stats" in text):
        return "platform_stats_waiting"
    if "when" in text and "connect platforms" in text:
        return "platform_activation_readiness"
    if "notification" in text and "platform" in text:
        return "platform_notifications"
    if "activation readiness" in text:
        return "platform_activation_readiness"
    if "comment profile" in text or "profile lead" in text or ("why" in text and "profile" in text and "suggest" in text):
        return "comment_profile_leads"
    if "comment section" in text:
        return "comment_section_review"
    if "safe data" in text or "data is safe" in text or "safe to enter" in text or "compliant public data" in text:
        return "safe_social_data"
    if "follow" in text and ("automatic" in text or "automatically" in text or "fortuna" in text):
        return "no_auto_posting"
    if "discovery mode" in text or ("discover" in text and ("opportun" in text or "lead" in text)):
        return "social_discovery_mode"
    if "recovery risk" in text or "recovery alert" in text:
        return "recovery_risk"
    if "recovery center" in text or "backup" in text or "backups" in text:
        return "recovery_center"
    if "railway breaks" in text or "rebuild fortuna" in text or "disaster" in text:
        return "disaster_recovery"
    if "restore test" in text:
        return "restore_test"
    if "choose best opportun" in text or "best opportun" in text or "opportunity prediction" in text:
        return "opportunity_prediction"
    if "chatter performs" in text or "best chatter" in text or "team intelligence" in text:
        return "team_performance"
    if "find opportunities" in text or "finds opportunities" in text or "find opportunity" in text:
        return "social_discovery_sources"
    if "public post" in text or ("add" in text and "post" in text and "opportun" in text):
        return "social_public_post"
    if "record result" in text or ("record" in text and "result" in text):
        return "social_record_results"
    if "comment angle" in text or "comment ideas" in text or "angle" in text:
        return "social_comment_angles"
    if "fortuna learn" in text or ("how" in text and "learn" in text):
        return "social_learning"
    if "compliant" in text or "compliance" in text or ("safe" in text and ("social" in text or "opportun" in text)):
        return "social_compliance"
    if "where am i" in text or "what screen" in text:
        return "where_am_i"
    if "what does back" in text or ("back" in text and "do" in text):
        return "back_navigation"
    if "get home" in text or "main menu" in text or "go home" in text:
        return "home_navigation"
    if "creator alert" in text or ("creator" in text and "alert" in text):
        return "creator_alerts"
    if "social" in text and ("opportunity" in text or "intelligence" in text):
        return "social_opportunity_intelligence"
    if "auto" in text and ("post" in text or "comment" in text):
        return "no_auto_posting"
    if "explain this screen" in text or "what is this screen" in text:
        return "explain_screen"
    if "availability" in text:
        return "availability"
    if "own post" in text and "alert" in text:
        return "own_post_alerts"
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
    next_action = best_next_action(session, user)
    if next_action.title:
        return (
            f"Your next best move is {next_action.title}. It is the safest next move because {next_action.reason} "
            f"Estimated time: {next_action.estimated_time}.",
            next_action.action_page,
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
            "To register notification groups, create Fortuna HQ, Fortuna Ops, and Fortuna Alerts, add @FortunaSolstice_Bot, open each group, "
            "then tap Register This Chat. Missing right now: "
            f"{missing_text}."
        )
    else:
        answer = "HQ, Ops, and Alerts are configured. Use routing simulation before sending real group alerts beyond the approved target."
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

    if intent == "coo_briefing":
        answer = (
            "COO Briefing shows what matters, why it matters, and what should happen next.\n\n"
            "Why: it compares recovery, bot health, notifications, platform readiness, opportunities, and recent activity so the owner sees one top priority instead of a dashboard wall.\n\n"
            "Next button to press: COO Briefing."
        )
        next_action = "coo:briefing" if _adminish(user) else "help"
    elif intent == "decision_priorities":
        answer = (
            "Fortuna ranks decisions using evidence, urgency, risk, impact, reversibility, and whether owner action is required.\n\n"
            "Why: the highest-risk item should be handled before optional setup.\n\n"
            "Next button to press: Top Priority."
        )
        next_action = "decision:top" if _adminish(user) else "help"
    elif intent == "decision_recovery_priority":
        recovery = recovery_risk_assessment(session) if _adminish(user) else None
        answer = (
            "Recovery becomes top priority when backup or restore evidence is missing.\n\n"
            f"Why: {recovery.next_best_move if recovery else 'Data-loss risk matters before optional setup.'}\n\n"
            "Next button to press: Recovery Center."
        )
        next_action = "recovery_center" if _adminish(user) else "help"
    elif intent == "decision_platforms_wait":
        answer = (
            "Platform connections can wait when credentials are intentionally planned for later and no active workflow depends on them yet.\n\n"
            "Why: Not connected yet is a setup state, not a production failure.\n\n"
            "Next button to press: Platform Connections."
        )
        next_action = "platforms" if _adminish(user) else "help"
    elif intent == "decision_confidence":
        answer = (
            "Confidence tells you how strong Fortuna's evidence is.\n\n"
            "Why: current checks and recent records create high confidence; partial or older evidence creates medium or low confidence.\n\n"
            "Next button to press: Decision Details."
        )
        next_action = "decision:details" if _adminish(user) else "help"
    elif intent == "decision_can_wait":
        answer = (
            "Can Wait means Fortuna sees the item, but it should not distract from the top priority.\n\n"
            "Why: optional setup like final platform logins can be prepared without interrupting recovery or bot-health work.\n\n"
            "Next button to press: COO Briefing."
        )
        next_action = "coo:briefing" if _adminish(user) else "help"
    elif intent == "decision_learning":
        answer = (
            "Fortuna records whether decisions were shown, opened, ignored, acted on, or resolved.\n\n"
            "Why: over time, that helps Fortuna learn which recommendations actually matter.\n\n"
            "Next button to press: COO Briefing."
        )
        next_action = "coo:briefing" if _adminish(user) else "help"
    elif intent == "decision_memory":
        answer = (
            "Decision Memory shows what Fortuna learned after recommendations were shown.\n\n"
            "Why: it separates shown, opened, acted on, dismissed, waiting, and resolved decisions so future briefings get quieter and smarter.\n\n"
            "Next button to press: Decision Memory."
        )
        next_action = "decision:memory" if _adminish(user) else "help"
    elif intent == "decision_feedback":
        answer = (
            "Helpful, Not Helpful, Remind Later, and Dismiss are feedback signals.\n\n"
            "Why: they tune low-risk recommendations gradually, but they never hide critical safety issues without evidence that the issue was resolved.\n\n"
            "Next button to press: Decision Details."
        )
        next_action = "decision:details" if _adminish(user) else "help"
    elif intent == "decision_quality":
        answer = (
            "Decision Quality checks whether Fortuna's recommendations are specific, evidence-backed, correctly prioritized, and useful.\n\n"
            "Why: Fortuna should answer whether it is right, not just produce more recommendations.\n\n"
            "Next button to press: Intelligence Quality."
        )
        next_action = "intelligence:quality" if _adminish(user) else "help"
    elif intent == "recommendation_accuracy":
        answer = (
            "Recommendation Accuracy compares what Fortuna recommended with later evidence from Decision Memory and system records.\n\n"
            "Why: Fortuna should not assume a recommendation worked unless an action or resolution was actually observed.\n\n"
            "Next button to press: Intelligence Quality."
        )
        next_action = "intelligence:quality" if _adminish(user) else "help"
    elif intent == "confidence_accuracy":
        answer = (
            "Confidence Accuracy checks whether Fortuna's confidence matched the evidence and later outcome.\n\n"
            "Why: weak evidence should lower confidence, and scoring problems should never make Fortuna sound more certain.\n\n"
            "Next button to press: Intelligence Quality."
        )
        next_action = "intelligence:quality" if _adminish(user) else "help"
    elif intent == "decision_quality_trends":
        answer = (
            "Decision Quality Trends show whether Fortuna's recommendations are improving, stable, declining, or still missing enough outcome data.\n\n"
            "Why: trends use Decision Memory and real outcomes. Fortuna does not invent improvement when records are thin.\n\n"
            "Next button to press: Decision Trends."
        )
        next_action = "intelligence:quality:trends" if _adminish(user) else "help"
    elif intent == "trend_improving":
        answer = (
            "Improving means recommendations in that category are being opened, acted on, or resolved with evidence.\n\n"
            "Why: Fortuna needs real Decision Memory records before it can say a category is getting better.\n\n"
            "Next button to press: Category Trends."
        )
        next_action = "intelligence:quality:categories" if _adminish(user) else "help"
    elif intent == "trend_insufficient_data":
        answer = (
            "Insufficient data means Fortuna does not have enough decision outcomes to call a real trend yet.\n\n"
            "Why: low data should stay honest instead of becoming fake confidence.\n\n"
            "Next button to press: Decision Trends."
        )
        next_action = "intelligence:quality:trends" if _adminish(user) else "help"
    elif intent == "predictive_coo":
        answer = (
            "Predictive COO uses current evidence plus decision trends to suggest what may matter next.\n\n"
            "Why: predictions are evidence-backed guesses about what may matter next. They do not replace current verified status.\n\n"
            "Next button to press: Prediction Preview."
        )
        next_action = "prediction:preview" if _adminish(user) else "help"
    elif intent == "reality_check":
        answer = (
            "Reality Check compares Fortuna's predictions against later evidence.\n\n"
            "Why: Fortuna can be wrong. Reality Check exists so it can compare predictions against later evidence and improve.\n\n"
            "Next button to press: Reality Check."
        )
        next_action = "reality:check" if _adminish(user) else "help"
    elif intent == "prediction_proven_correct":
        answer = (
            "Proven correct means later evidence supported the prediction.\n\n"
            "Why: Fortuna cannot mark a prediction correct just because it sounded useful or no one complained.\n\n"
            "Next button to press: Prediction Outcomes."
        )
        next_action = "reality:outcomes" if _adminish(user) else "help"
    elif intent == "prediction_proven_wrong":
        answer = (
            "Proven wrong means later evidence contradicted the prediction.\n\n"
            "Why: wrong predictions stay visible in calibration so Fortuna can reduce overconfidence instead of hiding misses.\n\n"
            "Next button to press: Prediction Outcomes."
        )
        next_action = "reality:outcomes" if _adminish(user) else "help"
    elif intent == "prediction_not_enough_evidence":
        answer = (
            "Not enough evidence means Reality Check ran, but Fortuna could not prove or disprove the prediction.\n\n"
            "Why: missing evidence should stay honest instead of becoming fake accuracy.\n\n"
            "Next button to press: Reality Check."
        )
        next_action = "reality:check" if _adminish(user) else "help"
    elif intent == "prediction_pending":
        answer = (
            "A pending prediction is still waiting for later evidence.\n\n"
            "Why: ignored or unresolved predictions are not automatically wrong, and silence is not proof.\n\n"
            "Next button to press: Prediction Outcomes."
        )
        next_action = "reality:outcomes" if _adminish(user) else "help"
    elif intent == "owner_feedback_prediction_proof":
        answer = (
            "Owner feedback can say a prediction was helpful or looked wrong, but feedback alone does not prove correctness.\n\n"
            "Why: proven correct needs supporting evidence, and proven wrong needs contradicting evidence.\n\n"
            "Next button to press: Reality Check."
        )
        next_action = "reality:check" if _adminish(user) else "help"
    elif intent == "confidence_calibration":
        answer = (
            "Confidence Calibration checks whether Fortuna's low, medium, and high confidence predictions matched real outcomes.\n\n"
            "Why: if Fortuna is overconfident, future predictions should use more cautious wording until evidence improves.\n\n"
            "Next button to press: Calibration."
        )
        next_action = "reality:calibration" if _adminish(user) else "help"
    elif intent == "evidence_capture":
        answer = (
            "Evidence is a traceable record of what happened in reality.\n\n"
            "Why: owner notes, validations, system records, references, and operational outcomes help Fortuna learn without guessing.\n\n"
            "Next button to press: Evidence Notes."
        )
        next_action = "evidence:notes" if _adminish(user) else "help"
    elif intent == "owner_validation":
        answer = (
            "Owner Validation lets you mark a prediction correct, incorrect, partially correct, too early, or add evidence.\n\n"
            "Why: owner feedback helps Fortuna learn, but evidence still matters.\n\n"
            "Next button to press: Decision Review."
        )
        next_action = "decision:review" if _adminish(user) else "help"
    elif intent == "partially_correct":
        answer = (
            "Partially Correct means some evidence supported the prediction, but uncertainty or disagreement remains.\n\n"
            "Why: Fortuna should not force messy real-world outcomes into only right or wrong.\n\n"
            "Next button to press: Prediction Outcomes."
        )
        next_action = "reality:outcomes" if _adminish(user) else "help"
    elif intent == "knowledge_memory":
        answer = (
            "Knowledge Memory stores durable lessons that came from evidence.\n\n"
            "Why: lessons such as recovery setup notes or rollout blockers should be reusable later, not buried in one chat screen.\n\n"
            "Next button to press: Knowledge Memory."
        )
        next_action = "knowledge:memory" if _adminish(user) else "help"
    elif intent == "feedback_override":
        answer = (
            "No. Owner feedback cannot override system records by itself.\n\n"
            "Why: owner feedback helps Fortuna learn, but contradictory system evidence stays visible until reviewed.\n\n"
            "Next button to press: Reality Check."
        )
        next_action = "reality:check" if _adminish(user) else "help"
    elif intent == "prediction_not_facts":
        answer = (
            "No. Predictions are not facts.\n\n"
            "Why: they are conservative forecasts from current evidence and trends, while verified status still comes from live records and checks.\n\n"
            "Next button to press: Prediction Preview."
        )
        next_action = "prediction:preview" if _adminish(user) else "help"
    elif intent == "prediction_restore_testing":
        answer = (
            "Fortuna predicts restore testing as a likely next blocker when backups are verified but full restore validation is still missing.\n\n"
            "Why: backup evidence improves recovery, but full protection still needs restore-test evidence.\n\n"
            "Next button to press: Prediction Preview."
        )
        next_action = "prediction:preview" if _adminish(user) else "help"
    elif intent == "prediction_training":
        answer = (
            "Train predictions by using Helpful, Not Helpful, Remind Later, and Dismiss after reviewing a prediction.\n\n"
            "Why: ignored does not mean wrong, and proven-correct predictions require later evidence.\n\n"
            "Next button to press: Prediction Preview."
        )
        next_action = "prediction:preview" if _adminish(user) else "help"
    elif intent == "decision_human_approval":
        answer = (
            "No. Fortuna recommends decisions, but humans still decide and execute.\n\n"
            "Why: Fortuna should not auto-execute business decisions, post, comment, like, follow, or bypass platform rules.\n\n"
            "Next button to press: COO Briefing."
        )
        next_action = "coo:briefing" if _adminish(user) else "help"
    elif intent == "platform_connections":
        answer = (
            "Platform Connections shows each platform in layers: public website, verified login/API/session, stats access, notifications, and activation readiness.\n\n"
            "Why: reachable is not the same as connected, and missing credentials are setup items, not failures.\n\n"
            "Next button to press: Platform Connections."
        )
        next_action = "platforms" if _adminish(user) else "help"
    elif intent == "platform_reachable_vs_connected":
        answer = (
            "Reachable only means Fortuna can access the public website. Connected means you have approved a login/API/session method and Fortuna verified it.\n\n"
            "Why: a public website check cannot prove account access or stats access.\n\n"
            "Next button to press: Connection Setup."
        )
        next_action = "platforms"
    elif intent == "platform_stats_waiting":
        answer = (
            "Stats waiting for connection means Fortuna has not verified an approved platform connection yet.\n\n"
            "Why: followers, reach, engagement, and account metrics require official/API, approved connector, session-based, or manual evidence. Fortuna will not invent stats.\n\n"
            "Next button to press: Connection Setup."
        )
        next_action = "platforms"
    elif intent == "platform_notifications":
        answer = (
            "Platform notifications send approved alerts to Fortuna HQ, Ops, or Alerts targets when those targets are registered.\n\n"
            "Why: missing targets are setup items, not delivery failures.\n\n"
            "Next button to press: Notification Center."
        )
        next_action = "platforms:notifications"
    elif intent == "platform_activation_readiness":
        answer = (
            "Activation readiness means Fortuna has checked the setup pieces needed before a platform becomes useful: website check, connection method, secure credential readiness, stats layer, notification route, and compliance rules.\n\n"
            "Why: Fortuna should say what is prepared without pretending credentials or stats already exist.\n\n"
            "Next button to press: Platform Connections."
        )
        next_action = "platforms"
    elif intent == "readiness_low":
        answer, next_action = _readiness_answer(session, user)
    elif intent == "recovery_center":
        if not _adminish(user):
            answer = "Recovery Center is owner/admin-only. Ask an owner to confirm backups before entering critical data."
            next_action = "help"
        else:
            recovery = recovery_risk_assessment(session)
            answer = (
                "Recovery Center checks real backup and restore records. "
                f"Current status: {recovery.protection_status}. "
                f"Risk: {recovery.risk_score}/100 ({recovery.risk_level}). "
                f"Next: {recovery.next_best_move}"
            )
            next_action = "recovery_center"
    elif intent == "recovery_risk":
        if not _adminish(user):
            answer = "Recovery risk is owner/admin-only. The short version: backups and restore tests lower risk; missing evidence raises it."
            next_action = "help"
        else:
            recovery = recovery_risk_assessment(session)
            drivers = "; ".join(recovery.evidence[:3]) or "No evidence has been recorded yet."
            answer = (
                f"Recovery Risk is {recovery.risk_score}/100 ({recovery.risk_level}). "
                "Fortuna calculates it from backup age, recent failures, storage redundancy, encryption, checksum records, and restore-test evidence. "
                f"Main drivers: {drivers}"
            )
            next_action = "recovery_center"
    elif intent == "disaster_recovery":
        answer = (
            "If Railway breaks, rebuild Fortuna from the code repo, safe environment secrets, Postgres, Redis, and the latest encrypted backup. "
            "Recovery Center -> Disaster Plan shows the steps."
        )
        next_action = "recovery:disaster_plan" if _adminish(user) else "help"
    elif intent == "restore_test":
        answer = (
            "A restore test checks whether a backup can be verified or restored. "
            "If no test database is configured, Fortuna can verify checksum/decryption readiness but will not call that a full restore pass."
        )
        next_action = "recovery:restore:test" if _adminish(user) else "help"
    elif intent == "opportunity_prediction":
        answer = (
            "Fortuna chooses the best opportunity from score, source history, niche fit, timing assumptions, angle performance, and team workload. "
            "It only recommends. A human reviews and posts manually."
        )
        next_action = "opportunities:best"
    elif intent == "team_performance":
        answer = (
            "Team Intelligence looks at completed tasks, overdue work, opportunity outcomes, and workload balance. "
            "It suggests who may be a good fit for new work, but it does not reassign automatically."
        )
        next_action = "team_intelligence" if _adminish(user) else "my_work"
    elif intent == "where_am_i":
        page = (current_page or "this screen").replace("_", " ").replace(":", " -> ")
        answer = f"You are on {page}. The top of the screen tells you what matters, and the main button is the safest next step."
        next_action = current_page or "menu"
    elif intent == "back_navigation":
        answer = "Back returns to the section that opened the current screen. Main Menu always takes you home and clears the path."
        next_action = current_page or "menu"
    elif intent == "home_navigation":
        answer = "Tap Main Menu from any screen to return home. If you feel lost, use What Should I Do Next from Home or Help."
        next_action = "menu"
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
    elif intent == "explain_screen":
        answer = (
            "This screen starts with what matters, then the recommended action, then deeper details only if you ask for them. "
            "Use What Should I Do Next if you want Fortuna to choose one path."
        )
        next_action = current_page or "assistant_next"
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
    elif intent == "availability":
        answer = (
            "Availability tells Fortuna whether you are on shift, away, or unavailable. "
            "Keep it current so work is routed to the right person without extra noise."
        )
        next_action = "availability"
    elif intent == "notification_groups":
        answer, next_action = _notification_answer(session, user)
    elif intent == "creator_alerts":
        article = _article(session, "creator_alerts")
        answer = article.content if article else "Open Creator Watchlist, choose a creator, then tap New Post Alert. Fortuna creates an opportunity and human review strategies; it never posts automatically."
        next_action = "opportunities:creators"
    elif intent == "own_post_alerts":
        answer = "Open Own Post Watch, choose or add a post, then tap New Own Post Alert. Fortuna routes it to Ops or Alerts, creates a follow-up task, and keeps all platform action manual."
        next_action = "opportunities:posts"
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
    elif intent == "social_opportunity_intelligence":
        article = _article(session, "social_opportunity_intelligence")
        answer = article.content if article else "Use compliant data only. Fortuna scores opportunities for human review and never posts automatically."
        next_action = "opportunities:score"
    elif intent == "social_discovery_mode":
        article = _article(session, "social_discovery_mode")
        answer = article.content if article else (
            "Discovery Mode turns approved manual sources or public post references into opportunity leads for human review. "
            "It does not scrape private data, bypass platform limits, or post automatically."
        )
        next_action = "opportunities:discovery"
    elif intent == "social_discovery_sources":
        answer = (
            "Fortuna can use manual URLs, manually entered creators/pages, approved exports, and future official API connectors. "
            "Private data, prohibited scraping, and auto-engagement are not supported."
        )
        next_action = "opportunities:discovery"
    elif intent == "social_public_post":
        answer = (
            "Open Opportunities -> Discovery Mode -> Paste Public Post. Add the public URL or reference, niche, and why it may matter. "
            "Fortuna will score it and keep the next step manual."
        )
        next_action = "opportunities:discovery:paste_post"
    elif intent == "social_record_results":
        answer = (
            "Open the opportunity or discovery lead, then record reviewed, skipped, converted, clicks, replies, profile visits, conversions, and notes. "
            "Those manual results teach Fortuna what works."
        )
        next_action = "opportunities:command"
    elif intent == "social_comment_angles":
        article = _article(session, "social_comment_angles")
        answer = article.content if article else (
            "Comment angles are human-reviewed ideas like curiosity, relatable, playful, question, or soft CTA. "
            "Fortuna drafts direction, but you decide and post manually."
        )
        next_action = "opportunities:discovery"
    elif intent == "comment_profile_leads":
        article = _article(session, "comment_profile_leads")
        answer = article.content if article else (
            "Comment profile leads are public profiles Fortuna noticed in approved comment data. "
            "Review them manually; Fortuna never follows, likes, or comments."
        )
        next_action = "opportunities:profiles"
    elif intent == "comment_section_review":
        article = _article(session, "comment_section_review")
        answer = article.content if article else (
            "Comment Section Review summarizes approved public comment evidence and points you to the best profile lead to inspect by hand."
        )
        next_action = "opportunities:comments"
    elif intent == "safe_social_data":
        article = _article(session, "safe_social_data")
        answer = article.content if article else (
            "Safe data means manual public input, approved exports, official APIs, compliant public sources, or approved future connectors. "
            "Do not enter private data, passwords, or anything collected through evasion."
        )
        next_action = "opportunities:discovery"
    elif intent == "social_learning":
        article = _article(session, "social_learning")
        answer = article.content if article else (
            "Fortuna learns from manual outcomes: which sources, niches, angles, timing windows, and team members produce better results."
        )
        next_action = "intelligence:learning"
    elif intent == "social_compliance":
        answer = (
            "Safe social work means public or approved inputs, human review, no private data, no scraping against platform rules, "
            "no rate-limit evasion, and no automatic posting, liking, following, or commenting."
        )
        next_action = "opportunities:discovery"
    elif intent == "no_auto_posting":
        answer = "Fortuna does not auto-post, auto-comment, like, follow, evade limits, or scrape private data. It only prepares advisory work for human review."
        next_action = "opportunities:score"
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
        failures_json=sanitize_value(failures),
        warnings_json=sanitize_value(warnings),
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
