from .formatting import *

def render_coo_dashboard_page(session: Session, user: User | None = None) -> Screen:
    priorities = top_priorities(session, actor=user, limit=5)
    messages = fortuna_messages(session, actor=user)
    lines = [
        "Fortuna COO Layer",
        "",
        "Fortuna is watching readiness, assignments, risks, and follow-ups so work gets routed instead of discovered late.",
        "",
        "What Fortuna Noticed:",
    ]
    lines.extend(f"- {message}" for message in messages)
    lines.append("")
    lines.append("Top Priorities:")
    if priorities:
        for item in priorities[:5]:
            lines.append(f"- {item.score}/100: {item.explanation.split('.')[0]} -> {item.recommended_owner}")
    else:
        lines.append("- No open priorities right now.")
    return Screen("\n".join(lines), coo_dashboard_menu())

def render_today_top5_page(session: Session, user: User | None = None) -> Screen:
    actions = todays_top_5_actions(session, actor=user)
    lines = [
        "Today's Top 5 Actions",
        "",
        "These are the highest-impact actions Fortuna recommends right now.",
        "",
    ]
    buttons: list[tuple[str, str]] = []
    if not actions:
        lines.append("No priority actions right now. Run a COO scan after new setup or team changes.")
    for index, action in enumerate(actions, start=1):
        lines.append(f"{index}. {action.title}")
        lines.append(f"   Owner: {action.owner} | Score: {action.score}/100")
        lines.append(f"   Why: {action.explanation}")
        buttons.append((f"Fix {index}: {action.title[:28]}", action.action_page))
    return Screen("\n".join(lines), top5_actions_menu(buttons))

def render_readiness_v2_page(session: Session) -> Screen:
    readiness = readiness_score_v2(session)
    blockers = readiness["biggest_blockers"][:5]
    status = "Healthy" if readiness["readiness_score"] >= 80 else "Needs Setup" if readiness["readiness_score"] >= 40 else "Blocked"
    next_action = (
        readiness["fastest_path"][0]["title"]
        if readiness["fastest_path"]
        else "No urgent setup action. Keep running the daily cycle."
    )
    lines = [
        "Readiness Score V2",
        "",
        f"Status: {status}",
        f"Agency Readiness: {readiness['readiness_score']}%",
        f"Issues Found: {len(blockers)}",
        "",
        "Recommended Action:",
        next_action,
        "",
        "Why the score is low:",
    ]
    if readiness["why_low"]:
        lines.extend(f"- {reason}" for reason in readiness["why_low"])
    else:
        lines.append("- Every readiness section is complete.")
    lines.append("")
    lines.append("Fastest path to improve:")
    buttons: list[tuple[str, str]] = []
    if readiness["fastest_path"]:
        for item in readiness["fastest_path"]:
            lines.append(f"- +{item['estimated_gain']}: {item['title']}")
            if item.get("action_page"):
                buttons.append((f"+{item['estimated_gain']} {item['title'][:24]}", item["action_page"]))
    else:
        lines.append("- Nothing urgent. Keep running the daily cycle.")
    lines.append("")
    lines.append("Biggest blockers:")
    for item in blockers:
        lines.append(f"- {item['title']} ({item['severity']})")
    return Screen("\n".join(lines), readiness_v2_menu(buttons))

def render_manager_queue_page(session: Session, user: User | None = None) -> Screen:
    queue = manager_work_queue(session, actor=user)
    lines = [
        "Manager Queue",
        "",
        "This is the work that needs assignment, approval, attention, or escalation.",
        "",
    ]
    lines.extend(_queue_lines("Needs Assignment:", queue["needs_assignment"], empty="Nothing unassigned."))
    lines.append("")
    lines.extend(_queue_lines("Needs Approval:", queue["needs_approval"], empty="No approvals waiting."))
    lines.append("")
    lines.extend(_queue_lines("Needs Attention:", queue["needs_attention"], empty="No manager/admin priorities."))
    lines.append("")
    lines.extend(_queue_lines("Overdue:", queue["overdue"], empty="No overdue work."))
    return Screen("\n".join(lines), manager_queue_menu())

def render_my_work_page(session: Session, user: User) -> Screen:
    queue = chatter_work_queue(session, user)
    lines = [
        "My Work",
        "",
        "No clutter. These are the items waiting on you.",
        "",
        f"Due Today: {len(queue['today'])}",
        f"Priority Tasks: {len(queue['priority'])}",
        f"Due Soon: {len(queue['due_soon'])}",
        f"Waiting On Me: {len(queue['waiting_on_me'])}",
        f"Opportunities: {len(queue['opportunities'])}",
        "",
        "Next Items:",
    ]
    next_items = [task.title for task in queue["today"][:3]] + [opportunity.title for opportunity in queue["opportunities"][:3]]
    if next_items:
        lines.extend(f"- {item}" for item in next_items[:5])
    else:
        lines.append("- Nothing assigned right now. Check with your manager if you expected work.")
    return Screen("\n".join(lines), my_work_menu())

def render_coo_briefing_page(session: Session, user: User | None = None) -> Screen:
    briefing = coo_briefing(session, actor=user)
    issues_found = len(briefing["needs_attention"]) + len(briefing["blocked"])
    next_action = briefing["next_actions"][0] if briefing["next_actions"] else "Nothing urgent. Run a COO scan after new changes."
    lines = [
        "Fortuna COO Briefing",
        "",
        f"Status: {'Healthy' if issues_found == 0 else 'Needs Attention'}",
        f"Readiness: {briefing['readiness_score']}%",
        f"Issues Found: {issues_found}",
        "",
        "Recommended Action:",
        next_action,
        "",
        "What changed?",
    ]
    lines.extend(f"- {item}" for item in briefing["what_changed"][:5])
    lines.append("")
    lines.append("What needs attention?")
    lines.extend(f"- {item}" for item in briefing["needs_attention"][:5]) if briefing["needs_attention"] else lines.append("- No urgent attention items.")
    lines.append("")
    lines.append("What is blocked?")
    lines.extend(f"- {item}" for item in briefing["blocked"][:5]) if briefing["blocked"] else lines.append("- No setup blockers.")
    lines.append("")
    lines.append("What should happen next?")
    lines.extend(f"- {item}" for item in briefing["next_actions"][:5]) if briefing["next_actions"] else lines.append("- Run a COO scan after new changes.")
    lines.append("")
    lines.append("Delegation:")
    lines.extend(f"- {item}" for item in briefing["delegate"][:3]) if briefing["delegate"] else lines.append("- Team load looks balanced enough for now.")
    return Screen("\n".join(lines), coo_briefing_menu())

def render_load_balancer_page(session: Session) -> Screen:
    load = team_load_balancer(session)
    lines = [
        "Team Load Balancer",
        "",
        "Fortuna only recommends reassignment here. It does not move work automatically.",
        "",
        "Overloaded:",
    ]
    if load["overloaded"]:
        for row in load["overloaded"][:5]:
            lines.append(f"- {row['name']}: score {row['workload_score']} ({row['status']})")
    else:
        lines.append("- No overloaded users detected.")
    lines.append("")
    lines.append("Idle / Available:")
    if load["idle"]:
        for row in load["idle"][:5]:
            lines.append(f"- {row['name']}: availability {row['availability']}")
    else:
        lines.append("- No idle on-shift users detected.")
    lines.append("")
    lines.append("Recommendations:")
    lines.extend(f"- {item}" for item in load["recommendations"]) if load["recommendations"] else lines.append("- No reassignment recommendation.")
    return Screen("\n".join(lines), page_menu(back_to="coo"))

def render_executive_mode_page(session: Session, user: User | None = None) -> Screen:
    summary = executive_mode_summary(session, actor=user)
    lines = [
        "Fortuna HQ",
        "",
        f"Agency Health: {summary['agency_health']}",
        f"Readiness: {summary['readiness_score']}%",
        f"Critical Issues: {summary['critical_issues']}",
        f"Open Recommendations: {summary['open_recommendations']}",
        f"Failed Automations: {summary['failed_automations']}",
        "",
        "Top Priorities:",
    ]
    if summary["top_priorities"]:
        for item in summary["top_priorities"][:5]:
            lines.append(f"- {item.score}/100: {item.explanation.split('.')[0]}")
    else:
        lines.append("- No open priorities.")
    lines.append("")
    lines.append("What Fortuna Recommends:")
    lines.extend(f"- {message}" for message in summary["messages"][:5])
    return Screen("\n".join(lines), executive_mode_menu())

