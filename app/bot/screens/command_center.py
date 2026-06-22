from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen
from app.models.user import User
from app.services.live_scores import ROLE_HOME_FOUNDATION, SCORE_ORDER, LiveScore, build_command_center_report


PRIMARY_SCORE_KEYS = ("agency_os", "intelligence", "team_readiness", "revenue_intelligence")
SCORE_ICONS = {
    "agency_os": "🚀",
    "intelligence": "🧠",
    "team_readiness": "👥",
    "revenue_intelligence": "🐋",
    "recovery_safety": "🛡",
    "reliability": "⚡",
    "agency_visibility": "🧭",
}


def _score_line(score: LiveScore) -> str:
    arrow = {"up": "▲", "down": "▼", "flat": "↔"}.get(score.movement, "↔")
    delta = f"{arrow} {score.delta_since_last:+d} this {score.delta_period}" if score.delta_since_last else f"{arrow} steady"
    return f"{SCORE_ICONS.get(score.score_name, '•')} {score.label}\n{score.score_percent}%  {delta}"


def _confidence_label(value: str) -> str:
    return {"high": "High", "medium": "Medium", "low": "Low"}.get(value, value.title())


def _command_center_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Today", callback_data=callback_for("today_priorities"))],
            [
                InlineKeyboardButton(text="🧠 Intelligence", callback_data=callback_for("command_center:intelligence")),
                InlineKeyboardButton(text="🎯 Operations", callback_data=callback_for("command_center:operations")),
            ],
            [
                InlineKeyboardButton(text="🛡 Systems", callback_data=callback_for("command_center:systems")),
                InlineKeyboardButton(text="⚙️ Admin", callback_data=callback_for("command_center:admin")),
            ],
            [
                InlineKeyboardButton(text="📈 Scores", callback_data=callback_for("command_center:scores")),
                InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("command_center")),
            ],
        ]
    )


def _hub_menu(rows: list[list[tuple[str, str]]], *, back_to: str = "command_center") -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        keyboard.append([InlineKeyboardButton(text=label, callback_data=callback_for(page)) for label, page in row])
    keyboard.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _scores_menu() -> InlineKeyboardMarkup:
    rows = [
        [(f"{SCORE_ICONS.get(name, '•')} {label}", f"command_center:score:{name}")]
        for name, label in (
            ("agency_os", "Agency OS"),
            ("intelligence", "Intelligence"),
            ("team_readiness", "Team Readiness"),
            ("revenue_intelligence", "Revenue Intelligence"),
            ("recovery_safety", "Recovery Safety"),
            ("reliability", "Reliability"),
            ("agency_visibility", "Agency Visibility"),
        )
    ]
    return _hub_menu(rows, back_to="command_center")


def render_command_center_home(session: Session, user: User | None = None) -> Screen:
    report = build_command_center_report(session, persist=True)
    lines = ["🚀 Fortuna Command Center", "Fortuna OS for the agency.", ""]
    for key in PRIMARY_SCORE_KEYS:
        lines.extend([_score_line(report.scores[key]), ""])
    if report.active_job_summary:
        lines.extend(["Current Active Job", report.active_job_summary, ""])
    fastest = report.fastest_gain
    lines.extend(
        [
            "🎯 Fastest Gain",
            fastest.title if fastest else "Add the next small piece of evidence.",
            fastest.required_action if fastest else "Use Today to choose the next move.",
            "",
            "✨ Next Best Move",
            fastest.required_action if fastest else "Open Today.",
            "",
            "⚠ Attention Needed",
        ]
    )
    if report.attention_items:
        lines.extend(report.attention_items[:3])
    else:
        lines.append("No urgent item is active right now.")
    return Screen("\n".join(lines), _command_center_menu())


def render_intelligence_hub_page(session: Session, user: User | None = None) -> Screen:
    report = build_command_center_report(session)
    score = report.scores["intelligence"]
    lines = [
        "🧠 Intelligence",
        "",
        "Status",
        f"{score.score_percent}% readiness, confidence {_confidence_label(score.confidence)}.",
        "",
        "Why it matters",
        "This is where Fortuna explains what matters, what it learned, and what may happen next.",
        "",
        "Next Best Move",
        score.fastest_gain,
    ]
    rows = [
        [("👑 COO Briefing", "coo:briefing"), ("🧭 What Fortuna Can See", "agency_awareness")],
        [("🌅 Today", "today_priorities"), ("🧠 AI Brain", "ai_brain")],
        [("📚 What Fortuna Remembers", "decision:memory"), ("🧪 How Accurate Is Fortuna?", "reality:check")],
        [("📈 Recommendation Quality", "intelligence:quality"), ("🔮 Predictions", "prediction:preview")],
    ]
    return Screen("\n".join(lines), _hub_menu(rows))


def render_operations_hub_page(session: Session, user: User | None = None) -> Screen:
    report = build_command_center_report(session)
    score = report.scores["revenue_intelligence"]
    lines = [
        "🎯 Operations",
        "",
        "Status",
        f"{score.score_percent}% revenue visibility, confidence {_confidence_label(score.confidence)}.",
        "",
        "Why it matters",
        "Operations will hold creators, content, traffic, fans, whales, chatters, and tasks as those workflows come online.",
        "",
        "Next Best Move",
        score.fastest_gain,
        "",
        "Coming Soon / Needs Data",
        "Fans, whales, source quality, and chatter revenue loops need first records before Fortuna can score them highly.",
    ]
    rows = [
        [("🎯 Opportunities", "opportunities"), ("👤 Creators", "opportunities:creators")],
        [("📝 Content", "opportunities:posts"), ("📈 Traffic", "command_center:score:agency_visibility")],
        [("🐋 Fans / Whales", "command_center:score:revenue_intelligence"), ("✅ Tasks", "tasks")],
        [("🧾 Manual Records", "agency_awareness:evidence")],
    ]
    return Screen("\n".join(lines), _hub_menu(rows))


def render_systems_hub_page(session: Session, user: User | None = None) -> Screen:
    report = build_command_center_report(session)
    reliability = report.scores["reliability"]
    recovery = report.scores["recovery_safety"]
    lines = [
        "🛡 Systems",
        "",
        "Status",
        f"Reliability {reliability.score_percent}% · Recovery {recovery.score_percent}%.",
        "",
        "Why it matters",
        "Systems keeps the bot, backups, AI, search, social accounts, and alerts working safely.",
        "",
        "Next Best Move",
        recovery.fastest_gain if recovery.score_percent < reliability.score_percent else reliability.fastest_gain,
    ]
    rows = [
        [("🛡 Backups & Safety", "recovery_center"), ("⚡ Reliability Center", "reliability")],
        [("🧠 AI Settings", "ai_brain:settings"), ("🔎 Search Intelligence", "search")],
        [("📱 Social Accounts", "platforms"), ("🔔 Notifications", "platforms:notifications")],
        [("🔭 System Watch", "production_observability"), ("💾 Backup Storage", "recovery:storage")],
    ]
    return Screen("\n".join(lines), _hub_menu(rows))


def render_admin_hub_page(session: Session, user: User | None = None) -> Screen:
    roles = ", ".join(label.title() for label in ROLE_HOME_FOUNDATION)
    lines = [
        "⚙️ Admin",
        "",
        "Status",
        "Owner mode is active.",
        "",
        "Why it matters",
        "Admin keeps commands, settings, history, integrations, role modes, and deeper details out of the main team flow.",
        "",
        "Next Best Move",
        "Use Commands when testing or onboarding a teammate.",
        "",
        "Role Mode Foundation",
        f"Prepared roles: {roles}. Permissions stay owner-only until they are ready.",
    ]
    rows = [
        [("⚙️ Settings", "settings"), ("❓ Help", "help")],
        [("⌨️ Commands", "help:commands"), ("📜 Audit / History", "audit_logs")],
        [("🔌 Integrations", "platforms"), ("🧰 Developer Details", "owner_advanced")],
        [("🧪 Self-Test", "ui_self_test"), ("🚨 Callback History", "callback_failure_review")],
    ]
    return Screen("\n".join(lines), _hub_menu(rows))


def render_scores_page(session: Session, user: User | None = None) -> Screen:
    report = build_command_center_report(session)
    lines = [
        "📈 Scores",
        "",
        "Status",
        "Scores are deterministic and evidence-backed.",
        "",
        "Why it matters",
        "They show where Fortuna is ready, where confidence is low, and what would raise readiness fastest.",
        "",
    ]
    for key in SCORE_ORDER:
        score = report.scores[key]
        lines.append(f"{SCORE_ICONS.get(key, '•')} {score.label}: {score.score_percent}% · {_confidence_label(score.confidence)} confidence")
        lines.append(f"Fastest gain: {score.fastest_gain}")
    return Screen("\n".join(lines), _scores_menu())


def render_score_detail_page(session: Session, score_name: str, user: User | None = None) -> Screen:
    report = build_command_center_report(session)
    score = report.scores.get(score_name) or report.scores["agency_os"]
    lines = [
        f"{SCORE_ICONS.get(score.score_name, '📈')} {score.label}",
        "",
        f"Score: {score.score_percent}%",
        f"Confidence: {_confidence_label(score.confidence)}",
        "",
        "Why it moved",
        score.reason_for_change,
        "",
        "What would raise it",
        score.fastest_gain,
        "",
        "What is missing",
    ]
    lines.extend(score.weak_spots or ("No major gap found in the current evidence.",))
    lines.extend(["", "Evidence used"])
    lines.append(score.evidence_summary)
    lines.extend(["", "Breakdown"])
    for item in score.score_breakdown:
        lines.append(f"{item.label}: {item.earned}/{item.weight}")
        lines.append(item.evidence)
    return Screen("\n".join(lines), _hub_menu([], back_to="command_center:scores"))
