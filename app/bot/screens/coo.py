from .formatting import *
from app.services.decision_engine import (
    Decision,
    generate_coo_briefing,
    generate_decisions,
    record_decision_interaction,
    top_decision,
)


def _decision_status_icon(status: str) -> str:
    return {
        "healthy": "🟢",
        "needs_review": "🟡",
        "needs_attention": "🟠",
        "critical": "🔴",
    }.get(status, "🟡")


def _decision_summary(decision: Decision) -> list[str]:
    return [
        decision.title,
        "",
        "Why:",
        decision.risk,
        "",
        "Impact:",
        decision.impact,
        "",
        "Confidence:",
        decision.confidence.title(),
        "",
        "Evidence:",
        decision.evidence_summary,
        "",
        "Next:",
        decision.next_best_move,
    ]

def render_coo_dashboard_page(session: Session, user: User | None = None) -> Screen:
    priorities = top_priorities(session, actor=user, limit=5)
    messages = fortuna_messages(session, actor=user)
    lines = [
        "Fortuna Operations",
        "",
        "Fortuna is quietly watching readiness, assignments, risks, and follow-ups.",
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

def render_coo_briefing_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    briefing = generate_coo_briefing(session, actor=user)
    top = briefing.top_priority
    if details:
        lines = [
            "🔎 Decision Details",
            "",
            f"Generated: {format_user_datetime(user, briefing.generated_at)}",
            "",
            "Ranked decisions:",
        ]
        if not briefing.decisions:
            lines.append("- No evidence-backed decisions yet.")
        for index, decision in enumerate(briefing.decisions[:8], start=1):
            lines.extend(
                [
                    "",
                    f"{index}. {decision.severity_icon} {decision.title}",
                    f"Category: {decision.category_label}",
                    f"Priority: {decision.priority_rank}/100",
                    f"Confidence: {decision.confidence.title()}",
                    f"Can wait: {'Yes' if decision.can_wait else 'No'}",
                    f"Impact: {decision.impact}",
                    f"Risk: {decision.risk}",
                    f"Evidence: {decision.evidence_summary}",
                    f"Sources: {', '.join(decision.source_records)}",
                ]
            )
        return Screen("\n".join(lines), decision_details_menu())

    lines = [
        "👑 COO Briefing",
        "",
        "Status:",
        f"{_decision_status_icon(briefing.overall_status)} {briefing.overall_label}",
        "",
        "What changed:",
        *[f"• {item}" for item in briefing.what_changed],
        "",
        "🎯 Top Priority",
    ]
    if top is None:
        lines.extend(["Nothing urgent here.", "", "Why:", "Fortuna has enough evidence to stay quiet right now."])
    else:
        lines.extend(
            [
                top.title,
                "",
                "Why:",
                top.risk,
            ]
        )
    lines.extend(["", "Risks:"])
    if briefing.risks:
        lines.extend(f"• {decision.title}" for decision in briefing.risks[:3])
    else:
        lines.append("• No active high-risk blocker found.")
    lines.extend(["", "Opportunities:"])
    if briefing.opportunities:
        lines.extend(f"• {decision.title}" for decision in briefing.opportunities[:3])
    else:
        lines.append("• No urgent opportunity needs attention.")
    lines.extend(["", "🧘 Can Wait"])
    if briefing.can_wait:
        lines.extend(f"• {decision.title}" for decision in briefing.can_wait[:3])
    else:
        lines.append("• Nothing optional is competing for attention.")
    lines.extend(
        [
            "",
            "✨ Next Best Move",
            briefing.next_best_move,
            "",
            "Fortuna recommends what matters first. Humans still decide.",
        ]
    )
    return Screen("\n".join(lines), coo_briefing_menu())


def render_decision_top_priority_page(session: Session, user: User | None = None) -> Screen:
    decision = top_decision(session, actor=user)
    if decision is None:
        lines = [
            "🎯 Top Priority",
            "",
            "Nothing urgent here.",
            "",
            "Why:",
            "Fortuna did not find an evidence-backed blocker that should interrupt you.",
            "",
            "✨ Next Best Move",
            "Keep operating from Today.",
        ]
        return Screen("\n".join(lines), decision_top_priority_menu("today_priorities"))
    record_decision_interaction(session, decision=decision, action="opened", actor=user)
    lines = ["🎯 Top Priority", "", *_decision_summary(decision)]
    return Screen("\n".join(lines), decision_top_priority_menu(decision.action_page))


def render_decision_details_page(session: Session, user: User | None = None) -> Screen:
    decisions = generate_decisions(session, actor=user)
    lines = [
        "🔎 Decision Details",
        "",
        "Fortuna ranked these using evidence, urgency, risk, and impact.",
    ]
    if not decisions:
        lines.append("")
        lines.append("Not enough evidence yet.")
    for index, decision in enumerate(decisions[:8], start=1):
        lines.extend(
            [
                "",
                f"{index}. {decision.severity_icon} {decision.title}",
                f"Priority: {decision.priority_rank}/100",
                f"Category: {decision.category_label}",
                f"Confidence: {decision.confidence.title()}",
                f"Next: {decision.next_best_move}",
                f"Evidence: {decision.evidence_summary}",
            ]
        )
    return Screen("\n".join(lines), decision_details_menu())

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
    blockers = [item.explanation.split(".")[0] for item in summary["top_priorities"][:3]]
    blocker_lines = [f"- {item}" for item in blockers] if blockers else ["- Nothing urgent here."]
    lines = [
        "\U0001f3f0 Fortuna HQ",
        "",
        "Agency Health",
        "Needs setup." if summary["readiness_score"] < 80 else "Looks steady.",
        "",
        "Fortuna Recommends",
        summary["messages"][0] if summary["messages"] else "Finish model setup first.",
        "",
        "Top Blockers",
        *blocker_lines,
        "",
        "What Fortuna Did",
        f"Prepared {len(summary['messages'])} action{'s' if len(summary['messages']) != 1 else ''} today.",
    ]
    return Screen("\n".join(lines), executive_mode_menu())

