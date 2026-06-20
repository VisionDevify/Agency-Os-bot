from .formatting import *
from app.services.decision_engine import generate_decisions
from app.services.decision_quality import safe_decision_quality_report


def _quality_status_label(status: str, *, available: bool = True) -> str:
    if not available:
        return "🟡 Quality check unavailable"
    return {
        "healthy": "🟢 Healthy",
        "needs_review": "🟡 Needs review",
        "needs_attention": "🟠 Needs attention",
        "critical": "🔴 Critical",
    }.get(status, "🟡 Needs review")


def _quality_percent(value: float) -> str:
    return f"{int(round(value * 100))}%"

def render_intelligence_home(session: Session | None = None) -> Screen:
    lines = ["\U0001f9e0 Fortuna Insights", ""]
    if session is None:
        lines.extend(["Status", "Watching quietly.", "", "Next Best Move", "Ask Fortuna what to check next."])
    else:
        status = command_center_intelligence_status(session)
        noticed: list[str] = []
        if status["open_signals"]:
            noticed.append("There are things to watch.")
        if status["active_patterns"]:
            noticed.append("Fortuna found recurring problems.")
        if status["negative_trends"]:
            noticed.append("Some trends need attention.")
        if status["overloaded_users"]:
            noticed.append("Someone may be overloaded.")
        if not noticed:
            noticed.append("No urgent risks.")
        lines.extend(
            [
                "Status",
                "Watching quietly.",
                "",
                "Fortuna Noticed",
                *[f"- {item}" for item in noticed[:3]],
                "",
                "Next Best Move",
                "Finish setup before adding more automation." if noticed == ["No urgent risks."] else "Review priorities first.",
            ]
        )
    return Screen(text="\n".join(lines), reply_markup=intelligence_menu())


def render_intelligence_details_page(session: Session) -> Screen:
    status = command_center_intelligence_status(session)
    learning = learning_center_metrics(session)
    lines = [
        "Fortuna Insights - More Details",
        "",
        f"Status: {status['status']}",
        f"Things To Watch: {status['open_signals']}",
        f"Critical Watch Items: {status['critical_signals']}",
        f"Recurring Problems: {status['active_patterns']}",
        f"Negative Trends: {status['negative_trends']}",
        f"Overloaded Users: {status['overloaded_users']}",
        f"Management Insights: {status['open_executive_insights']}",
        f"Learning Events: {learning['total_learning_events']}",
        f"Active Playbooks: {learning['active_playbooks']}",
        "",
        "Technical analysis tools live here.",
    ]
    return Screen(text="\n".join(lines), reply_markup=intelligence_details_menu())


def render_intelligence_quality_page(
    session: Session,
    user: User | None = None,
    *,
    details: bool = False,
) -> Screen:
    decisions = generate_decisions(session, actor=user)
    report = safe_decision_quality_report(session, decisions, actor=user)
    findings = list(report.findings)
    if not report.available:
        noticed = ["Intelligence quality check unavailable."]
        next_move = "Use COO Briefing from current evidence and try again later."
    elif findings:
        noticed = [finding.title for finding in findings[:3]]
        next_move = findings[0].recommendation
    else:
        noticed = ["Fortuna found no decision-quality issue that should interrupt you."]
        next_move = "Keep using COO Briefing and record feedback when recommendations help."

    lines = [
        "🧠 Intelligence Quality",
        "",
        "Status:",
        _quality_status_label(report.status, available=report.available),
        "",
        "Decision Quality:",
        f"{report.decision_quality_score}/100",
        "",
        "Recommendation Accuracy:",
        f"{report.recommendation_accuracy}/100",
        "",
        "Confidence Accuracy:",
        f"{report.confidence_accuracy}/100",
        "",
        "Briefing Quality:",
        f"{report.briefing_quality_score}/100",
        "",
        "Learning Status:",
        report.learning_status.replace("_", " ").title(),
        "",
        "What Fortuna noticed:",
        *[f"- {item}" for item in noticed],
        "",
        "Next Best Move:",
        next_move,
    ]
    if details:
        lines.extend(
            [
                "",
                "Quality Details:",
                f"Decision memories reviewed: {report.total_memories}",
                f"Acted-on rate: {_quality_percent(report.acted_on_rate)}",
                f"Resolved rate: {_quality_percent(report.resolved_rate)}",
                f"Ignored rate: {_quality_percent(report.ignored_rate)}",
                f"Dismissal rate: {_quality_percent(report.dismissal_rate)}",
                f"Usefulness score: {report.usefulness_score}/100",
                f"Duplicate suppression: {report.duplicate_suppression_status.replace('_', ' ')}",
                "",
                "Friction:",
                report.friction.evidence,
                f"Next: {report.friction.recommendation}",
                "",
                "Findings:",
            ]
        )
        if findings:
            for finding in findings[:8]:
                lines.append(f"- {finding.title}: {finding.evidence}")
        else:
            lines.append("- No material quality findings.")
        if report.unavailable_reason:
            lines.extend(["", "Unavailable Reason:", report.unavailable_reason])
    return Screen(text="\n".join(lines), reply_markup=intelligence_quality_menu())

def render_intelligence_runs_page(session: Session) -> Screen:
    runs = list_intelligence_runs(session, limit=10)
    lines = ["Intelligence Runs", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No intelligence runs yet.")
    for run in runs:
        finished = format_user_datetime(None, run.finished_at) if run.finished_at else "running"
        lines.append(f"{run.id}. {run.run_type}")
        lines.append(f"   Status: {run.status} | Finished: {finished}")
        buttons.append((f"{run.id}. {run.run_type}", f"nav:intelligence:run_detail:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=intelligence_run_menu(buttons))

def render_intelligence_run_detail_page(session: Session, run_id: int) -> Screen:
    run = session.get(IntelligenceRun, run_id)
    if run is None:
        return Screen(text="Intelligence run not found.", reply_markup=page_menu(back_to="intelligence:runs"))
    lines = [
        "Intelligence Run",
        "",
        f"ID: {run.id}",
        f"Type: {run.run_type}",
        f"Status: {run.status}",
        f"Started: {format_user_datetime(None, run.started_at) if run.started_at else 'unknown'}",
        f"Finished: {format_user_datetime(None, run.finished_at) if run.finished_at else 'not finished'}",
        f"Error: {run.error_message or 'None'}",
        "",
        "Summary:",
    ]
    for key, value in sorted((run.summary_json or {}).items()):
        lines.append(f"- {key}: {value}")
    if not run.summary_json:
        lines.append("- Empty")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:runs"))

def render_intelligence_signals_page(session: Session) -> Screen:
    signals = list_signals(session, status="open", limit=20)
    lines = ["Intelligence Signals", ""]
    if not signals:
        lines.append("No open intelligence signals.")
    for signal in signals:
        lines.append(f"{signal.id}. {_status_marker(signal.severity)} {signal.title}")
        lines.append(f"   Type: {signal.signal_type} | Confidence: {signal.confidence_score}")
        lines.append(f"   Entity: {signal.entity_type or 'general'}:{signal.entity_id or 'n/a'}")
        lines.append(f"   Seen: {signal.occurrence_count} | Last: {format_user_datetime(None, signal.last_seen_at) if signal.last_seen_at else 'unknown'}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence"))

def render_intelligence_patterns_page(session: Session) -> Screen:
    patterns = list_patterns(session, status="active", limit=20)
    lines = ["Issue Patterns", ""]
    if not patterns:
        lines.append("No active issue patterns.")
    for pattern in patterns:
        lines.append(f"{pattern.id}. {_status_marker(pattern.severity)} {pattern.title}")
        lines.append(f"   Type: {pattern.pattern_type} | Confidence: {pattern.confidence_score}")
        lines.append(f"   Entity: {pattern.entity_type or 'general'}:{pattern.entity_id or 'n/a'}")
        lines.append(f"   Occurrences: {pattern.occurrence_count}")
        lines.append(f"   Action: {pattern.suggested_action}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence"))

def render_intelligence_trends_page(session: Session) -> Screen:
    trends = list_trends(session, limit=20)
    lines = ["\U0001f4c8 Trends", "", "Fortuna checked today\u2019s trends.", ""]
    if not trends:
        lines.extend(["What Changed", "- No trend snapshots yet.", "", "What It Means", "Nothing urgent here.", "", "Next", "Run analysis after setup has real data."])
        return Screen(text="\n".join(lines), reply_markup=trends_menu())
    negative = [trend for trend in trends if trend.trend_direction in {"down", "volatile"}][:3]
    calm = [trend for trend in trends if trend.trend_direction in {"flat", "up"}][:2]
    lines.append("What Changed")
    if negative:
        for trend in negative:
            friendly = trend.metric_name.replace("_", " ")
            lines.append(f"- {friendly.title()} moved {trend.trend_direction}.")
    else:
        lines.append("- No task issues.")
        lines.append("- No incident spike.")
    for trend in calm:
        friendly = trend.metric_name.replace("_", " ")
        lines.append(f"- {friendly.title()} looks steady.")
    lines.extend(["", "What It Means", "Setup still needs attention, but nothing is urgent.", "", "Next", "Clear setup recommendations."])
    return Screen(text="\n".join(lines), reply_markup=trends_menu())


def render_intelligence_trend_details_page(session: Session) -> Screen:
    trends = list_trends(session, limit=20)
    lines = ["Trends - More Details", ""]
    if not trends:
        lines.append("No trend snapshots yet.")
    for trend in trends:
        change = f"{trend.percent_change}%" if trend.percent_change is not None else "baseline"
        lines.append(f"{trend.id}. {trend.metric_name.replace('_', ' ')}: {trend.value_numeric}")
        lines.append(f"   Direction: {trend.trend_direction} | Change: {change}")
        lines.append(f"   Window: {trend.comparison_window} | Date: {trend.snapshot_date.strftime('%b')} {trend.snapshot_date.day}, {trend.snapshot_date.year}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence"))

