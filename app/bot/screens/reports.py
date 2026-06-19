from datetime import datetime

from .formatting import *

def render_reports_home() -> Screen:
    return Screen(text="Reports\nBriefings, dashboards, and accountability.", reply_markup=reports_menu())


def _human_time(user: User | None, value) -> str:
    if value is None:
        return "Not set"
    if isinstance(value, datetime):
        return format_user_datetime(user, value)
    if isinstance(value, str) and "T" in value:
        try:
            return format_user_datetime(user, datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return value
    return str(value)

def render_executive_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="executive")
    generate_recommendations(session, actor=user)
    stats = executive_dashboard(session)
    lines = [
        "Executive Command Center",
        "",
        f"Status: {stats['operational_status_banner']}",
        f"Agency Health Score: {stats['agency_health_score']}/100",
        f"Models: {stats['total_models']} "
        f"({stats['healthy_models']} healthy / {stats['warning_models']} warning / {stats['critical_models']} critical)",
        f"Accounts: {stats['total_accounts']} "
        f"({stats['healthy_accounts']} healthy / {stats['warning_accounts']} warning / {stats['critical_accounts']} critical)",
        f"Auth Attention: login {stats['accounts_needing_login']} / 2FA {stats['accounts_needing_2fa']}",
        f"Proxies: {stats['total_proxies']} "
        f"({stats['healthy_proxies']} healthy / {stats['warning_proxies']} warning / {stats['critical_proxies']} critical)",
        f"Accounts Missing Proxy: {stats['accounts_missing_proxy']}",
        f"Tasks: {stats['open_tasks']} open / {stats['overdue_tasks']} overdue / {stats['completed_tasks_today']} done today",
        f"Incidents: {stats['open_incidents']} open / {stats['critical_incidents']} critical",
        "",
        "Critical Alerts:",
    ]
    lines.extend(f"- {item}" for item in stats["critical_alerts"][:5])
    if not stats["critical_alerts"]:
        lines.append("- No active critical alerts")
    lines.extend(["", "Top Recommendations:"])
    if stats["top_recommendations"]:
        for recommendation in stats["top_recommendations"]:
            marker = _status_marker(recommendation["severity"])
            lines.append(f"- {marker} {recommendation['title']}")
    else:
        lines.append("- No open recommendations")
    lines.extend(
        [
            "",
            "Production Status:",
            f"Railway: {stats['production_status']}",
            f"Last Deployment: {stats['last_deployment_status']}",
            f"Bot Heartbeat: {stats['last_bot_heartbeat']}",
            f"Last Event: {stats['last_event_logged']} at {stats['last_event_at']}",
            "",
            "Automation Status:",
            f"Active Automations: {stats['active_automations']}",
            f"Failed Automations: {stats['failed_automations']}",
            f"Pending Approvals: {stats['pending_automation_approvals']}",
            f"Last Automation Run: {stats['last_automation_run']} at {stats['last_automation_run_at']}",
            f"Automation Success Rate: {stats['automation_success_rate']}%",
            "",
            "Recent High-Risk Events:",
        ]
    )
    lines.extend(f"- {item}" for item in stats["recent_high_risk_events"][:5])
    if not stats["recent_high_risk_events"]:
        lines.append("- No high-risk events found")
    return Screen(text="\n".join(lines), reply_markup=executive_dashboard_menu())

def render_operations_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="operations")
    stats = operations_dashboard(session)
    lines = [
        "Operations Dashboard",
        "",
        f"Pending Tasks: {stats['pending_tasks']}",
        f"Blocked Tasks: {stats['blocked_tasks']}",
        f"Accounts Needing Attention: {stats['accounts_needing_attention']}",
        f"Proxies Needing Attention: {stats['proxies_needing_attention']}",
        f"Models Needing Attention: {stats['models_needing_attention']}",
        "",
        "Tasks by Status:",
    ]
    for status, count in stats["tasks_by_status"].items():
        lines.append(f"- {status}: {count}")
    lines.extend(
        [
            "",
            "Incidents by Severity:",
        ]
    )
    for severity, count in stats["incidents_by_severity"].items():
        lines.append(f"- {severity.title()}: {count}")
    lines.extend(["", "Recent Escalations:"])
    lines.extend(f"- {item}" for item in stats["recent_escalations"][:5])
    if not stats["recent_escalations"]:
        lines.append("- No recent escalations")
    lines.extend(["", "Recent Failed Repairs:"])
    lines.extend(f"- {item}" for item in stats["recent_failed_repairs"][:5])
    if not stats["recent_failed_repairs"]:
        lines.append("- No recent failed repairs")
    return Screen(text="\n".join(lines), reply_markup=operations_dashboard_menu())

def render_manager_command_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="manager_command")
    metrics = manager_command_metrics(session)
    lines = [
        "Manager Command View",
        "",
        f"People On Shift: {len(metrics['on_shift'])}",
        f"People Off Shift: {len(metrics['off_shift'])}",
        f"Open Tasks: {metrics['open_tasks']}",
        f"Overdue Tasks: {metrics['overdue_tasks']}",
        f"Open Incidents: {metrics['open_incidents']}",
        f"Unresolved Critical Incidents: {metrics['unresolved_critical_incidents']}",
        f"Owner/Admin Recommendations: {metrics['owner_admin_recommendations']}",
        f"Notification Delivery Failures: {metrics['notification_delivery_failures']}",
        "",
        "On Shift:",
    ]
    if metrics["on_shift"]:
        lines.extend(f"- {_identity(person)}" for person in metrics["on_shift"][:10])
    else:
        lines.append("- Nobody marked on shift")
    lines.extend(["", "Open Tasks by Assignee:"])
    if metrics["open_tasks_by_assignee"]:
        for user_id, count in sorted(metrics["open_tasks_by_assignee"].items(), key=lambda item: str(item[0])):
            assignee = session.get(User, user_id) if user_id is not None else None
            lines.append(f"- {_identity(assignee)}: {count}")
    else:
        lines.append("- None")
    lines.extend(["", "Open Incidents by Assignee:"])
    if metrics["open_incidents_by_assignee"]:
        for user_id, count in sorted(metrics["open_incidents_by_assignee"].items(), key=lambda item: str(item[0])):
            assignee = session.get(User, user_id) if user_id is not None else None
            lines.append(f"- {_identity(assignee)}: {count}")
    else:
        lines.append("- None")
    return Screen(text="\n".join(lines), reply_markup=manager_command_menu())

def render_chatter_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="chatter")
    stats = chatter_dashboard(session, user=user)
    lines = [
        "Chatter Dashboard",
        "",
        f"Assigned Models: {stats['assigned_models']}",
        f"Open Tasks: {stats['open_tasks']}",
        f"Escalations: {stats['escalations']}",
        f"Notes: {stats['notes']}",
        "",
        "Future Metrics:",
    ]
    lines.extend(f"- {item}" for item in stats["future_metrics"])
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))

def render_va_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="va")
    stats = va_dashboard(session, user=user)
    lines = [
        "VA Dashboard",
        "",
        f"Assigned Models: {stats['assigned_models']}",
        f"Assigned Accounts: {stats['assigned_accounts']}",
        f"Open Tasks: {stats['open_tasks']}",
        f"Overdue Tasks: {stats['overdue_items']}",
        f"Content/Upload: {stats['uploads']}",
        f"Approvals: {stats['approvals']}",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))

def render_daily_briefing_page(
    session: Session,
    user: User | None = None,
    *,
    mode: str = "generate",
) -> Screen:
    if mode == "latest":
        summary = view_latest_daily_briefing(session, actor=user)
        if summary is None:
            return Screen(
                text="Daily Company Briefing\n\nNo briefing has been generated yet.",
                reply_markup=briefing_menu(),
            )
    else:
        summary = generate_daily_briefing(session, actor=user)
    record_report_view(session, actor=user, report_name="daily_briefing")
    lines = [
        "Daily Company Briefing",
        "",
        f"Briefing ID: {summary.get('briefing_id', 'pending')}",
        f"Summary: {summary['summary_text']}",
        f"Overall Status: {summary['overall_status']}",
        f"Agency Health Score: {summary['agency_health_score']}",
        f"Active Models: {summary['models_active']}",
        f"Models Healthy/Warning/Critical: "
        f"{summary['models_healthy']}/{summary['models_warning']}/{summary['models_critical']}",
        f"Accounts Healthy/Warning/Critical: "
        f"{summary['accounts_healthy']}/{summary['accounts_warning']}/{summary['accounts_critical']}",
        f"Accounts Needing Login/2FA: {summary['accounts_needing_login']}/{summary['accounts_needing_2fa']}",
        f"Proxies Healthy/Warning/Critical: "
        f"{summary['proxies_healthy']}/{summary['proxies_warning']}/{summary['proxies_critical']}",
        f"Open Incidents: {summary['open_incidents']}",
        f"Critical Incidents: {summary['critical_incidents']}",
        f"Tasks Completed Today: {summary['tasks_completed_today']}",
        f"Overdue Tasks: {summary['overdue_tasks']}",
        "",
        "Top Active Users:",
    ]
    if summary["top_active_users"]:
        for row in summary["top_active_users"]:
            lines.append(f"- {row['display_name']}: {row['completed_tasks']}")
    else:
        lines.append("- No completed tasks yet today")
    lines.extend(["", "Recent Audit Highlights:"])
    lines.extend(f"- {item}" for item in summary["recent_audit_highlights"])
    lines.extend(["", "Recommended Actions:"])
    lines.extend(f"- {item}" for item in summary["recommended_actions"])
    return Screen(text="\n".join(lines), reply_markup=briefing_menu())

def render_daily_digest_page(
    session: Session,
    user: User | None = None,
    *,
    mode: str = "home",
    purpose: str | None = None,
) -> Screen:
    if mode == "generate":
        summary = generate_daily_digest(session, actor=user)
        title = "Daily Digest Generated"
    elif mode == "preview":
        summary = preview_daily_digest(session, actor=user)
        title = "Daily Digest Preview"
        if summary is None:
            return Screen(
                text="Daily Digest\n\nNo digest has been generated yet.",
                reply_markup=daily_digest_menu(),
            )
    elif mode == "send":
        target_purpose = purpose or "operations"
        attempts = request_digest_send(session, actor=user, purpose=target_purpose)
        latest = preview_daily_digest(session, actor=user) or generate_daily_digest(session, actor=user)
        lines = [
            "Daily Digest Send Requested",
            "",
            f"Purpose: {target_purpose}",
            f"Delivery Attempts Created: {attempts}",
            "",
            latest["summary_text"],
        ]
        return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())
    elif mode == "history":
        attempts = daily_digest_delivery_history(session)
        lines = ["Daily Digest Delivery History", ""]
        if not attempts:
            lines.append("No delivery attempts yet.")
        for attempt in attempts:
            when = format_user_datetime(user, attempt.attempted_at) if attempt.attempted_at else "unknown time"
            lines.append(f"{when} | {attempt.event_type} | {attempt.status}")
        return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())
    elif mode == "schedule":
        return Screen(
            text="Daily Digest Schedule\n\nScheduling is prepared as a placeholder. Use Generate/Preview/Send today.",
            reply_markup=daily_digest_menu(),
        )
    else:
        summary = preview_daily_digest(session, actor=user)
        if summary is None:
            lines = [
                "Daily Digest",
                "",
                "No digest generated yet.",
                "Use Generate Digest to create today's operational summary.",
            ]
            return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())
        title = "Daily Digest"
    record_report_view(session, actor=user, report_name="daily_digest")
    lines = [
        title,
        "",
        f"Summary: {summary['summary_text']}",
        f"Agency Health Score: {summary['agency_health_score']}",
        f"Critical Incidents: {summary['critical_incidents']}",
        f"Overdue Tasks: {summary['overdue_tasks']}",
        f"Accounts Needing Login/2FA: {summary['accounts_needing_login']}/{summary['accounts_needing_2fa']}",
        f"Proxies Warning/Critical: {summary['proxies_warning']}/{summary['proxies_critical']}",
        "",
        "Top Recommendations:",
    ]
    for item in summary["recommended_actions"][:5]:
        lines.append(f"- {item}")
    if not summary["recommended_actions"]:
        lines.append("- No recommendations right now")
    return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())

def render_accountability_page(session: Session, user: User | None = None) -> Screen:
    view_accountability_report(session, actor=user)
    report = generate_accountability_report(session, actor=user)
    record_report_view(session, actor=user, report_name="team_accountability")
    generated = report.get("generated_at")
    generated_text = _human_time(user, generated)
    lines = ["Team Accountability", "", f"Generated: {generated_text}", ""]
    if not report["users"]:
        lines.append("No users yet.")
    for row in report["users"][:15]:
        roles = ", ".join(row["roles"]) or "No roles"
        lines.append(f"{row['display_name']}")
        lines.append(f"   Open Tasks: {row['assigned_open_tasks']} | Completed Today: {row['completed_today']}")
        lines.append(
            f"   Overdue: {row['overdue_tasks']} | Open Incidents: {row['open_incidents_assigned']}"
        )
        lines.append(f"   Resolved Today: {row['resolved_incidents_today']} | Score: {row['score']}")
        lines.append(f"   Last Seen: {row['last_seen']} | Roles: {roles}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))


def _recommendation_group(recommendation: Recommendation) -> tuple[str, str]:
    rec_type = recommendation.recommendation_type
    title = recommendation.title.lower()
    if recommendation.severity == "critical" or "critical" in title:
        return "\U0001f534 Urgent", "Fix Now"
    if "notification" in title or "notification" in rec_type:
        return "\U0001f535 System", "Fix Now"
    if rec_type.startswith("activation_") or "missing" in title or "setup" in title or "model" in title or "account" in title:
        return "\U0001f7e1 Needs Setup", "Fix Now"
    if "creator" in title or "opportun" in title:
        return "\U0001f7e1 Growth", "Fix Now"
    if "production" in title or "automation" in title or "proxy" in title:
        return "\u2699 System", "Review"
    return "\U0001f535 Recommended Next Moves", "Review"


def _friendly_recommendation_title(recommendation: Recommendation) -> str:
    raw = recommendation.title.strip()
    replacements = {
        "Models Missing Manager": "Model needs a manager",
        "Models Missing Chatter Team": "Model needs a chatter team",
        "Accounts Missing Proxy": "Account needs a proxy",
        "Notification Targets Missing": "Notification groups are not registered",
    }
    if raw in replacements:
        return replacements[raw]
    return raw.replace("_", " ").strip().capitalize()


def render_recommendations_page(session: Session, user: User | None = None) -> Screen:
    generate_recommendations(session, actor=user)
    recommendations = list_recommendations(session, status="open", limit=20)
    record_report_view(session, actor=user, report_name="recommendations")
    lines = ["\U0001f534 Start Here", ""]
    buttons: list[tuple[str, str]] = []
    if not recommendations:
        lines.extend(["Nothing urgent here.", "", "Fortuna will keep watching for blockers.", "", "Ready when you are."])
    else:
        top = recommendations[0]
        top_title = _friendly_recommendation_title(top)
        lines.extend(
            [
                top_title,
                "",
                "Why",
                top.description,
                "",
                "Next",
                "Fix This",
                "",
                "\U0001f7e1 Later",
            ]
        )
        buttons.append((f"Fix This: {top_title[:32]}", f"nav:recommendation:{top.id}"))
        grouped: dict[str, list[Recommendation]] = {}
        for recommendation in recommendations:
            group, _ = _recommendation_group(recommendation)
            grouped.setdefault(group, []).append(recommendation)
        later_count = 0
        for group in (
            "\U0001f7e1 Needs Setup",
            "\U0001f7e1 Growth",
            "\U0001f535 System",
            "\u2699 System",
            "\U0001f535 Recommended Next Moves",
        ):
            group_items = grouped.get(group, [])
            if not group_items:
                continue
            for recommendation in group_items:
                if recommendation.id == top.id:
                    continue
                lines.append(f"- {_friendly_recommendation_title(recommendation)}")
                later_count += 1
                if later_count >= 4:
                    break
            if later_count >= 4:
                break
        if later_count == 0:
            lines.append("- Nothing else urgent.")
    return Screen(text="\n".join(lines), reply_markup=recommendations_menu(buttons))

def render_recommendation_detail_page(session: Session, recommendation_id: int) -> Screen:
    recommendation = session.get(Recommendation, recommendation_id)
    if recommendation is None:
        return Screen(
            text="Recommendation not found.",
            reply_markup=page_menu(back_to="reports:executive:recommendations"),
        )
    target = (
        f"{recommendation.entity_type}:{recommendation.entity_id}"
        if recommendation.entity_type and recommendation.entity_id
        else "General"
    )
    lines = [
        "Recommendation",
        "",
        f"Title: {recommendation.title}",
        f"Severity: {_status_marker(recommendation.severity)} {recommendation.severity}",
        f"Status: {recommendation.status}",
        f"Target: {target}",
        "",
        "Why this matters:",
        recommendation.description,
        "",
        "Jump opens the closest related Fortuna OS page when available.",
    ]
    return Screen(text="\n".join(lines), reply_markup=recommendation_detail_menu(recommendation.id))

def render_recommendation_why_page(session: Session, recommendation_id: int) -> Screen:
    recommendation = session.get(Recommendation, recommendation_id)
    if recommendation is None:
        return Screen(text="Recommendation not found.", reply_markup=page_menu(back_to="reports:executive:recommendations"))
    why = recommendation_why(recommendation)
    source_signals = ", ".join(str(signal_id) for signal_id in why["source_signal_ids"]) or "None"
    lines = [
        "Why This Recommendation",
        "",
        f"Title: {recommendation.title}",
        f"Reason: {why['reason']}",
        f"Confidence: {why['confidence_score'] if why['confidence_score'] is not None else 'Not scored'}",
        f"Related Entity: {why['related_entity']}",
        f"Source Signals: {source_signals}",
        f"Source Pattern: {why['source_pattern_id'] or 'None'}",
        "",
        "Suggested Next Action:",
        why["suggested_action"],
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"recommendation:{recommendation.id}"))

def render_intelligence_briefing_page(
    session: Session,
    user: User | None = None,
    *,
    mode: str = "generate",
) -> Screen:
    if mode == "latest":
        latest = list_executive_insights(session, limit=1)
        if not latest:
            return Screen(
                text="Executive Intelligence Briefing\n\nNo intelligence briefing has been generated yet.",
                reply_markup=intelligence_briefing_menu(),
            )
        insight = latest[0]
        lines = [
            "Executive Intelligence Briefing",
            "",
            f"Insight ID: {insight.id}",
            f"Severity: {_status_marker(insight.severity)} {insight.severity}",
            f"Confidence: {insight.confidence_score}",
            f"Summary: {insight.body}",
            "",
            "Recommended Action:",
            insight.recommended_action,
        ]
        return Screen(text="\n".join(lines), reply_markup=intelligence_briefing_menu())
    if mode == "send_hq":
        lines = [
            "Executive Intelligence Briefing",
            "",
            "Send to HQ is a safe placeholder until notification targets are explicitly approved.",
        ]
        return Screen(text="\n".join(lines), reply_markup=intelligence_briefing_menu())
    briefing = generate_executive_intelligence_briefing(session, actor=user)
    lines = [
        "Executive Intelligence Briefing",
        "",
        f"Insight ID: {briefing['insight_id']}",
        f"Agency Health Score: {briefing['agency_health_score']}/100",
        f"Summary: {briefing['summary_text']}",
        "",
        "Top Risks:",
    ]
    lines.extend(f"- {item}" for item in briefing["top_risks"][:3])
    if not briefing["top_risks"]:
        lines.append("- No top risks detected")
    lines.extend(["", "Top Improvements:"])
    lines.extend(f"- {item}" for item in briefing["top_improvements"][:3])
    if not briefing["top_improvements"]:
        lines.append("- No improvement recommendations yet")
    lines.extend(["", "Patterns Detected:"])
    lines.extend(f"- {item}" for item in briefing["patterns_detected"][:5])
    if not briefing["patterns_detected"]:
        lines.append("- No active patterns")
    lines.extend(["", "Negative Trends:"])
    lines.extend(f"- {item}" for item in briefing["negative_trends"][:5])
    if not briefing["negative_trends"]:
        lines.append("- No significant negative trends")
    lines.extend(["", "Overloaded Users:"])
    lines.extend(f"- {item}" for item in briefing["overloaded_users"][:5])
    if not briefing["overloaded_users"]:
        lines.append("- None")
    lines.extend(
        [
            "",
            "What the system is learning:",
            briefing.get("learning_summary", "Learning memory is still warming up."),
            f"Top Recurring Problem: {briefing.get('top_recurring_problem', 'Not enough data')}",
            f"Best Playbook: {briefing.get('best_playbook') or 'Not enough data'}",
            f"Lowest Confidence Playbook: {briefing.get('lowest_confidence_playbook') or 'Not enough data'}",
        ]
    )
    lines.extend(["", "Confidence Notes:", briefing["confidence_notes"]])
    return Screen(text="\n".join(lines), reply_markup=intelligence_briefing_menu())

def render_workload_intelligence_page(session: Session, user: User | None = None) -> Screen:
    snapshots = list_workload_snapshots(session, limit=30)
    if not snapshots:
        from app.services.intelligence import analyze_workload

        snapshots = analyze_workload(session, actor=user)
    lines = ["Workload Intelligence", ""]
    overloaded = [snapshot for snapshot in snapshots if snapshot.overload_status in {"overloaded", "critical"}]
    off_shift = [snapshot for snapshot in snapshots if snapshot.availability_status != "on_shift"]
    overdue = [snapshot for snapshot in snapshots if snapshot.overdue_tasks > 0]
    critical = [snapshot for snapshot in snapshots if snapshot.critical_incidents > 0]
    lines.extend(
        [
            f"Overloaded Users: {len(overloaded)}",
            f"Users Off Shift: {len(off_shift)}",
            f"Users With Overdue Tasks: {len(overdue)}",
            f"Users With Critical Incidents: {len(critical)}",
            "",
            "Suggested Reassignments:",
        ]
    )
    if not overloaded and not overdue:
        lines.append("- None right now")
    for snapshot in (overloaded + overdue)[:10]:
        user_obj = session.get(User, snapshot.user_id)
        lines.append(
            f"- {_identity(user_obj)}: {snapshot.overload_status}, score {snapshot.workload_score}, "
            f"overdue {snapshot.overdue_tasks}"
        )
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))

