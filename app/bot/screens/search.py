from __future__ import annotations

from .formatting import *
from app.services.search_intelligence import (
    attach_latest_search_result_as_evidence,
    create_notification_watch_from_latest_search_result,
    create_opportunity_from_latest_search_result,
    ignore_latest_search_result,
    latest_search_results,
    list_search_history,
    run_guided_search,
    run_search,
    search_configuration_status,
    search_observability_summary,
    SearchOptions,
)


def _search_status_label(status: str) -> str:
    return {
        "configured": "Configured",
        "not_configured": "Not configured yet",
        "disabled": "Disabled",
        "failed": "Needs review",
        "skipped": "Skipped",
        "succeeded": "Succeeded",
    }.get(status, status.replace("_", " ").title())


def _strength_label(strength: str) -> str:
    return {"weak": "Weak", "medium": "Medium", "strong": "Strong"}.get(strength, "Weak")


def render_search_center_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    status = search_configuration_status(session)
    label = _search_status_label(str(status["status"]))
    lines = [
        "🔎 Search Intelligence",
        "",
        "Status:",
        label,
        "",
        "What Fortuna can do:",
        "- Research public trends",
        "- Validate opportunities",
        "- Monitor public signals",
        "- Attach external evidence",
        "",
        "✨ Next Best Move",
        str(status["next_action"]),
    ]
    if not status["configured"]:
        lines.extend(
            [
                "",
                "Why:",
                "Tavily is the approved search provider, but the API key is not active yet.",
            ]
        )
    if details:
        env_vars = status.get("env_vars", {})
        lines.extend(
            [
                "",
                "Details:",
                f"Provider: {status['provider']}",
                f"Enabled: {'Yes' if status['enabled'] else 'No'}",
                f"Daily searches: {status['daily_count']}/{status['daily_limit']}",
                f"Latest query status: {_search_status_label(str(status['latest_query_status']))}",
                "",
                "Railway variables by name:",
            ]
        )
        for name in (
            "SEARCH_PROVIDER",
            "SEARCH_ENABLED",
            "TAVILY_API_KEY",
            "SEARCH_DAILY_LIMIT",
            "SEARCH_TIMEOUT_SECONDS",
            "SEARCH_DEFAULT_RECENCY_DAYS",
        ):
            lines.append(f"- {name}: {'present' if env_vars.get(name) else 'missing'}")
        if status.get("latest_error"):
            lines.extend(["", "Latest safe error:", str(status["latest_error"])[:180]])
    return Screen("\n".join(lines), search_center_menu(configured=bool(status["configured"])))


def render_search_guided_page(session: Session, workflow: str, user: User | None = None) -> Screen:
    labels = {
        "run": "Run Search",
        "opportunity": "Opportunity Research",
        "platform_signals": "Platform Signals",
        "coo_context": "COO Context",
    }
    if workflow == "run":
        status = search_configuration_status(session)
        lines = [
            "🔍 Run Search",
            "",
            "Status:",
            _search_status_label(str(status["status"])),
            "",
            "What Fortuna noticed:",
            "Free-form search input is not active yet because credentials and queries need a secure workflow.",
            "",
            "✨ Next Best Move",
            "Use a guided search preset or add TAVILY_API_KEY in Railway if search is not configured.",
        ]
        return Screen("\n".join(lines), search_center_menu(configured=bool(status["configured"])))
    report = run_guided_search(session, workflow, actor=user)
    label = labels.get(workflow, "COO Context")
    lines = [
        f"🔎 {label}",
        "",
        "Status:",
        _search_status_label(report.status),
        "",
        "What Fortuna noticed:",
    ]
    if report.status == "succeeded":
        if report.cached:
            lines.append("Fortuna reused cached public results for this query.")
        else:
            lines.append(f"Fortuna stored {len(report.results)} public result(s) as external evidence candidates.")
    elif report.compliance and not report.compliance.allowed:
        lines.append(report.compliance.public_reason)
    elif report.query and report.query.safe_error_summary:
        lines.append(report.query.safe_error_summary)
    else:
        lines.append(report.provider_status.reason)
    lines.extend(["", "✨ Next Best Move", report.next_action])
    if report.results:
        top = report.results[0]
        lines.extend(
            [
                "",
                "Top Evidence:",
                top.title,
                f"Source: {top.source_domain}",
                f"Strength: {_strength_label(top.evidence_strength)}",
            ]
        )
    return Screen("\n".join(lines), search_results_menu() if report.results else search_center_menu(configured=report.provider_status.configured))


def render_search_history_page(session: Session, user: User | None = None, *, rerun: bool = False) -> Screen:
    rerun_report = None
    history = list_search_history(session)
    if rerun and history:
        latest = history[0]
        rerun_report = run_search(
            session,
            latest.query_text,
            actor=user,
            options=SearchOptions(query_type=latest.query_type, used_for="research", force_refresh=True),
        )
        history = list_search_history(session)
    lines = [
        "📚 Search History",
        "",
        "Search results are timestamped external evidence, not truth by themselves.",
    ]
    if rerun_report is not None:
        lines.extend(["", "Re-run:", _search_status_label(rerun_report.status)])
        if rerun_report.query and rerun_report.query.safe_error_summary:
            lines.append(rerun_report.query.safe_error_summary)
    lines.extend(["", "Recent Searches:"])
    if not history:
        lines.append("- No searches recorded yet.")
    for query in history[:6]:
        when = format_user_datetime(user, query.requested_at)
        lines.append(f"- {_search_status_label(query.status)} · {query.query_type.replace('_', ' ')} · {query.result_count} result(s) · {when}")
    return Screen("\n".join(lines), search_history_menu())


def render_search_results_page(session: Session, user: User | None = None, *, action: str | None = None) -> Screen:
    action_message: str | None = None
    if action == "attach":
        evidence = attach_latest_search_result_as_evidence(session, actor=user)
        action_message = "Evidence attached." if evidence is not None else "No search result is available to attach."
    elif action == "opportunity":
        opportunity = create_opportunity_from_latest_search_result(session, actor=user)
        action_message = "Opportunity created for human review." if opportunity is not None else "No result is available to turn into an opportunity."
    elif action == "notification":
        created = create_notification_watch_from_latest_search_result(session, actor=user)
        action_message = (
            "Notification watch recommendation created for review."
            if created
            else "Latest result is not strong enough for an alert watch yet."
        )
    elif action == "ignore":
        ignored = ignore_latest_search_result(session, actor=user)
        action_message = "Result ignored for learning." if ignored else "No result is available to ignore."
    results = latest_search_results(session)
    lines = [
        "🔎 Search Results",
        "",
        "Search result ≠ truth. Fortuna treats it as external evidence.",
    ]
    if action_message:
        lines.extend(["", "Action:", action_message])
    if not results:
        lines.extend(["", "What Fortuna noticed:", "No search results are stored yet.", "", "✨ Next Best Move", "Run a guided public search."])
        return Screen("\n".join(lines), search_center_menu(configured=bool(search_configuration_status(session)["configured"])))
    top = results[0]
    lines.extend(
        [
            "",
            "Top Result:",
            top.title,
            "",
            "Source:",
            top.source_domain,
            "",
            "Snippet:",
            top.snippet,
            "",
            "Freshness:",
            f"{top.freshness_score}/100",
            "Credibility:",
            f"{top.credibility_score}/100",
            "Evidence Strength:",
            _strength_label(top.evidence_strength),
            "",
            "Why Fortuna thinks it matters:",
            "The result matched the public query and was scored for relevance, freshness, credibility, and risk.",
        ]
    )
    return Screen("\n".join(lines), search_results_menu())


def render_search_settings_page(session: Session, user: User | None = None) -> Screen:
    status = search_configuration_status(session)
    env_vars = status.get("env_vars", {})
    lines = [
        "⚙️ Search Settings",
        "",
        "Provider:",
        str(status["provider"]).title(),
        "",
        "Status:",
        _search_status_label(str(status["status"])),
        "",
        "Railway variables by name:",
    ]
    for name in (
        "SEARCH_PROVIDER",
        "SEARCH_ENABLED",
        "TAVILY_API_KEY",
        "SEARCH_DAILY_LIMIT",
        "SEARCH_TIMEOUT_SECONDS",
        "SEARCH_DEFAULT_RECENCY_DAYS",
    ):
        lines.append(f"- {name}: {'present' if env_vars.get(name) else 'missing'}")
    lines.extend(
        [
            "",
            "Safety:",
            "Fortuna uses approved public search APIs only. It does not scrape Google directly, search private profiles, or treat results as proof.",
            "",
            "✨ Next Best Move",
            str(status["next_action"]),
        ]
    )
    return Screen("\n".join(lines), search_settings_menu())


def render_search_observability_detail(session: Session, user: User | None = None) -> Screen:
    summary = search_observability_summary(session)
    lines = [
        "🔎 Search Details",
        "",
        f"Status: {summary['label']}",
        f"Provider: {summary['provider']}",
        f"Enabled: {'Yes' if summary['enabled'] else 'No'}",
        f"Configured: {'Yes' if summary['configured'] else 'No'}",
        f"Daily searches: {summary['daily_count']}/{summary['daily_limit']}",
        f"Latest query status: {_search_status_label(str(summary['latest_query_status']))}",
        f"Failed/skipped count: {summary['failed_or_skipped_count']}",
        "",
        "Next:",
        str(summary["next_action"]),
    ]
    return Screen("\n".join(lines), search_center_menu(configured=bool(summary["configured"])))
