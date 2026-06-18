from .formatting import *

def render_intelligence_home(session: Session | None = None) -> Screen:
    lines = ["Intelligence Command Center", ""]
    if session is None:
        lines.append("Things to watch, recurring problems, trends, and workload intelligence.")
    else:
        status = command_center_intelligence_status(session)
        learning = learning_center_metrics(session)
        lines.extend(
            [
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
                "Run analysis or drill into watch items, recurring problems, trends, and workload.",
            ]
        )
    return Screen(text="\n".join(lines), reply_markup=intelligence_menu())

def render_intelligence_runs_page(session: Session) -> Screen:
    runs = list_intelligence_runs(session, limit=10)
    lines = ["Intelligence Runs", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No intelligence runs yet.")
    for run in runs:
        finished = run.finished_at.isoformat() if run.finished_at else "running"
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
        f"Started: {run.started_at.isoformat() if run.started_at else 'unknown'}",
        f"Finished: {run.finished_at.isoformat() if run.finished_at else 'not finished'}",
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
        lines.append(f"   Seen: {signal.occurrence_count} | Last: {signal.last_seen_at.isoformat() if signal.last_seen_at else 'unknown'}")
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
    lines = ["Trend Analysis", ""]
    if not trends:
        lines.append("No trend snapshots yet.")
    for trend in trends:
        change = f"{trend.percent_change}%" if trend.percent_change is not None else "baseline"
        lines.append(f"{trend.id}. {trend.metric_name}: {trend.value_numeric}")
        lines.append(f"   Direction: {trend.trend_direction} | Change: {change}")
        lines.append(f"   Window: {trend.comparison_window} | Date: {trend.snapshot_date.isoformat()}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence"))

