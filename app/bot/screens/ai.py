from __future__ import annotations

from sqlalchemy import desc, func, select

from .formatting import *
from app.models.ai import AIAuditLog
from app.models.opportunity import Opportunity
from app.services.ai import (
    FortunaAIBrain,
    ai_configuration_status,
    generate_ai_decision_explanation,
    generate_ai_evidence_summary,
    generate_ai_search_summary,
)
from app.services.decision_engine import generate_decisions


def _ai_status_label(status: str) -> str:
    return {
        "configured": "Configured",
        "not_configured": "Not configured yet",
        "disabled": "Disabled",
        "failed": "Needs review",
        "rate_limited": "Rate limited",
        "timeout": "Timed out",
    }.get(status, status.replace("_", " ").title())


def _render_grounded_result(title: str, result, *, fallback_hint: str | None = None) -> Screen:
    output = result.output
    lines = [
        title,
        "",
        "Status:",
        _ai_status_label(result.status),
        "",
        "Conclusion:",
        output.conclusion,
        "",
        "Reasoning:",
        output.reasoning_summary,
        "",
        "Confidence:",
        output.confidence.title(),
        "",
        "Limitations:",
    ]
    lines.extend(f"- {item}" for item in output.limitations[:3])
    lines.extend(["", "Next Best Move", output.next_best_move])
    if result.fallback_used and fallback_hint:
        lines.extend(["", "Fallback:", fallback_hint])
    if output.evidence_used:
        lines.extend(["", "Evidence Used:"])
        lines.extend(f"- {item}" for item in output.evidence_used[:5])
    if output.safety_flags:
        lines.extend(["", "Safety Flags:"])
        lines.extend(f"- {item.replace('_', ' ').title()}" for item in output.safety_flags[:5])
    return Screen("\n".join(lines), ai_brain_menu(configured=result.provider_status.configured))


def render_ai_brain_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    status = ai_configuration_status(session)
    lines = [
        "🧠 AI Brain",
        "",
        "Status:",
        _ai_status_label(str(status["status"])),
        "",
        "What Fortuna can use AI for:",
        "- Explain decisions",
        "- Summarize evidence",
        "- Compare options",
        "- Summarize search results",
        "- Improve COO Briefing language",
        "",
        "✨ Next Best Move",
        str(status["next_action"]),
    ]
    if not status["configured"]:
        lines.extend(
            [
                "",
                "Why:",
                "Fortuna needs an OpenAI API key in Railway before AI Brain can run. ChatGPT Pro does not automatically power production API calls.",
            ]
        )
    if details:
        audit_count = session.scalar(select(func.count(AIAuditLog.id))) or 0
        critic_blocks = (
            session.scalar(select(func.count(AIAuditLog.id)).where(AIAuditLog.status == "blocked_by_critic")) or 0
        )
        env_vars = status.get("env_vars", {})
        lines.extend(
            [
                "",
                "Details:",
                f"Provider: {status['provider']}",
                f"Enabled: {'Yes' if status['enabled'] else 'No'}",
                f"Model: {status['model']}",
                f"Critic: {'Enabled' if status['critic_enabled'] else 'Disabled'}",
                f"Daily AI calls: {status['daily_count']}/{status['daily_limit']}",
                f"Audit records: {audit_count}",
                f"Critic blocks: {critic_blocks}",
                "",
                "Railway variables by name:",
            ]
        )
        for name in (
            "AI_PROVIDER",
            "AI_ENABLED",
            "OPENAI_API_KEY",
            "AI_MODEL",
            "AI_TIMEOUT_SECONDS",
            "AI_DAILY_LIMIT",
            "AI_MAX_CONTEXT_RECORDS",
            "AI_CRITIC_ENABLED",
        ):
            lines.append(f"- {name}: {'present' if env_vars.get(name) else 'missing'}")
        if status.get("latest_failure"):
            lines.extend(["", "Latest safe failure:", str(status["latest_failure"])[:180]])
    return Screen("\n".join(lines), ai_brain_menu(configured=bool(status["configured"])))


def render_ai_settings_page(session: Session, user: User | None = None) -> Screen:
    status = ai_configuration_status(session)
    env_vars = status.get("env_vars", {})
    lines = [
        "⚙️ AI Settings",
        "",
        "AI enabled:",
        "Yes" if status["enabled"] else "No",
        "",
        "Provider:",
        str(status["provider"]).title(),
        "",
        "Model:",
        str(status["model"]),
        "",
        "Critic:",
        "Enabled" if status["critic_enabled"] else "Disabled",
        "",
        "Daily limit:",
        str(status["daily_limit"]),
        "",
        "Last call:",
        str(status["latest_status"]),
        "",
        "Railway variables by name:",
    ]
    for name in (
        "AI_PROVIDER",
        "AI_ENABLED",
        "OPENAI_API_KEY",
        "AI_MODEL",
        "AI_TIMEOUT_SECONDS",
        "AI_DAILY_LIMIT",
        "AI_MAX_CONTEXT_RECORDS",
        "AI_CRITIC_ENABLED",
    ):
        lines.append(f"- {name}: {'present' if env_vars.get(name) else 'missing'}")
    lines.extend(
        [
            "",
            "Safety:",
            "Fortuna never renders API keys, sends backup credentials to AI, or lets AI override Recovery, Bot Status, or compliance truth.",
            "",
            "✨ Next Best Move",
            str(status["next_action"]),
        ]
    )
    return Screen("\n".join(lines), ai_settings_menu())


def render_ai_critic_status_page(session: Session, user: User | None = None) -> Screen:
    status = ai_configuration_status(session)
    latest_blocks = list(
        session.scalars(
            select(AIAuditLog)
            .where(AIAuditLog.status == "blocked_by_critic")
            .order_by(desc(AIAuditLog.created_at), desc(AIAuditLog.id))
            .limit(3)
        ).all()
    )
    lines = [
        "🧪 AI Critic Status",
        "",
        "Status:",
        "Enabled" if status["critic_enabled"] else "Disabled",
        "",
        "What the critic blocks:",
        "- Unsupported claims",
        "- Exaggerated confidence",
        "- Invented health or recovery status",
        "- Raw secret leaks",
        "- Compliance violations",
        "- Auto-post/comment/like/follow suggestions",
    ]
    if latest_blocks:
        lines.extend(["", "Recent Blocks:"])
        for block in latest_blocks:
            lines.append(f"- {block.use_case}: {block.safe_error_summary or 'Blocked safely.'}")
    else:
        lines.extend(["", "Recent Blocks:", "- None recorded."])
    lines.extend(["", "✨ Next Best Move", "Keep AI Critic enabled in production."])
    return Screen("\n".join(lines), ai_critic_menu())


def render_ai_evidence_summary_page(session: Session, user: User | None = None) -> Screen:
    result = generate_ai_evidence_summary(session, actor=user)
    return _render_grounded_result(
        "🔎 AI Evidence Summary",
        result,
        fallback_hint="Fortuna used deterministic evidence wording because AI was unavailable or blocked.",
    )


def render_ai_search_summary_page(session: Session, user: User | None = None) -> Screen:
    result = generate_ai_search_summary(session, actor=user)
    return _render_grounded_result(
        "🔎 AI Search Summary",
        result,
        fallback_hint="Tavily results and OpenAI must both be configured before AI can summarize external evidence.",
    )


def render_ai_coo_briefing_page(session: Session, user: User | None = None) -> Screen:
    decisions = generate_decisions(session, actor=user)
    top = next((decision for decision in decisions if not decision.can_wait), decisions[0] if decisions else None)
    result = generate_ai_decision_explanation(session, actor=user)
    return _render_grounded_result(
        "👑 AI COO Briefing",
        result,
        fallback_hint="The normal COO Briefing remains available and evidence-backed.",
    )


def render_ai_opportunity_explanation_page(session: Session, user: User | None = None) -> Screen:
    latest_opportunity = session.scalar(
        select(Opportunity).order_by(desc(Opportunity.created_at), desc(Opportunity.id)).limit(1)
    )
    if latest_opportunity is None:
        lines = [
            "🎯 AI Opportunity Explanation",
            "",
            "Status:",
            "Waiting for evidence",
            "",
            "What Fortuna noticed:",
            "No opportunity record is available for AI to explain yet.",
            "",
            "✨ Next Best Move",
            "Create or review an opportunity first.",
        ]
        return Screen("\n".join(lines), ai_brain_menu(configured=bool(ai_configuration_status(session)["configured"])))
    result = FortunaAIBrain().reason(
        session,
        use_case="opportunity_explanation",
        prompt=(
            "Explain why the latest opportunity might matter. Use only supplied opportunity, search, "
            "decision, and evidence records. Include limitations and keep it concise."
        ),
        actor=user,
    )
    return _render_grounded_result(
        "🎯 AI Opportunity Explanation",
        result,
        fallback_hint="Fortuna did not use AI unless a grounded explanation passed critic checks.",
    )
