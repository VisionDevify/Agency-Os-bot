from .formatting import *
from app.models.decision_memory import DecisionMemory
from app.services.decision_engine import (
    Decision,
    decision_memory_key,
    decision_memory_summary,
    generate_coo_briefing,
    generate_decisions,
    get_or_create_decision_memory,
    record_decision_interaction,
    record_decision_memory_event,
    top_decision,
)
from app.services.decision_quality import safe_decision_quality_report
from app.services.decision_trends import safe_predictive_coo_report
from app.services.evidence_capture import safe_evidence_capture_report
from app.services.reality_calibration import safe_reality_calibration_report


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


def _memory_label(memory: DecisionMemory | None) -> str:
    if memory is None:
        return "No owner feedback recorded yet."
    label = (memory.lifecycle_status or memory.outcome or "shown").replace("_", " ").title()
    return f"{label} · usefulness {memory.usefulness_score}/100"


def _top_memory(session: Session, decision: Decision | None) -> DecisionMemory | None:
    if decision is None:
        return None
    return session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)).limit(1))

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
    quality = safe_decision_quality_report(session, briefing.decisions, actor=user)
    prediction_report = safe_predictive_coo_report(session, decisions=briefing.decisions, actor=user)
    reality = safe_reality_calibration_report(session, actor=user)
    evidence = safe_evidence_capture_report(session)
    prediction = prediction_report.primary
    top = briefing.top_priority
    if details:
        lines = [
            "🔎 Decision Details",
            "",
            f"Generated: {format_user_datetime(user, briefing.generated_at)}",
            "",
            "Intelligence Quality:",
            f"Decision Quality: {quality.decision_quality_score}/100",
            f"Recommendation Accuracy: {quality.recommendation_accuracy}/100",
            f"Confidence Accuracy: {quality.confidence_accuracy}/100",
            f"Briefing Quality: {quality.briefing_quality_score}/100",
            f"Quality Status: {'Unavailable' if not quality.available else quality.status.replace('_', ' ').title()}",
            f"Prediction Status: {'Disabled' if not prediction_report.enabled else 'Unavailable' if not prediction_report.available else prediction_report.status.replace('_', ' ').title()}",
            f"Reality Check: {'Unavailable' if not reality.available else reality.status.replace('_', ' ').title()}",
            f"Evidence Records: {evidence.evidence_count if evidence.available else 'Unavailable'}",
            f"Knowledge Lessons: {evidence.knowledge_count if evidence.available else 'Unavailable'}",
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
        lines.extend(["", "Predictions:"])
        if prediction_report.predictions:
            for item in prediction_report.predictions[:4]:
                lines.extend(
                    [
                        f"- {item.prediction_title}",
                        f"  Confidence: {item.confidence.title()} | Can wait: {'Yes' if item.can_wait else 'No'}",
                        f"  Evidence: {item.evidence_summary}",
                    ]
                )
        else:
            lines.append("- No evidence-backed prediction is ready yet.")
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
    if briefing.learning_summary:
        lines.extend(["", "What Fortuna Learned"])
        lines.extend(f"- {item}" for item in briefing.learning_summary[:2])
    if evidence.available and evidence.knowledge_count:
        lines.extend(["", "📚 Evidence Lesson"])
        lines.extend(f"- {item}" for item in evidence.learned_lines[:2])
    if not quality.available:
        lines.extend(["", "Intelligence Quality", "Quality check unavailable; current evidence is still being used."])
    elif quality.status in {"needs_attention", "critical"} and quality.findings:
        lines.extend(["", "Intelligence Quality", quality.findings[0].title])
    if prediction is not None:
        lines.extend(
            [
                "",
                "🔮 Likely Next",
                prediction.prediction_title,
                "",
                "Why:",
                prediction.reason,
            ]
        )
    if reality.available and (
        reality.outcome_counts.get("proven_wrong", 0) or reality.outcome_counts.get("pending", 0)
    ):
        lines.extend(
            [
                "",
                "🧪 Reality Check",
                (
                    "A prediction was contradicted by evidence."
                    if reality.outcome_counts.get("proven_wrong", 0)
                    else "Some predictions are still waiting for evidence."
                ),
            ]
        )
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
    memory = _top_memory(session, decision)
    lines = ["🎯 Top Priority", "", *_decision_summary(decision), "", "Memory:", _memory_label(memory)]
    return Screen("\n".join(lines), decision_top_priority_menu(decision.action_page))


def render_decision_details_page(session: Session, user: User | None = None) -> Screen:
    decisions = generate_decisions(session, actor=user)
    top = next((decision for decision in decisions if not decision.can_wait), decisions[0] if decisions else None)
    memory = None
    if top is not None:
        record_decision_interaction(session, decision=top, action="opened", actor=user)
        memory = get_or_create_decision_memory(session, top)
    lines = [
        "🔎 Decision Details",
        "",
        "Fortuna ranked these using evidence, urgency, risk, and impact.",
    ]
    if not decisions:
        lines.append("")
        lines.append("Not enough evidence yet.")
    elif top is not None:
        prediction_hint = safe_predictive_coo_report(session, decisions=decisions, actor=user).primary
        lines.extend(
            [
                "",
                "Recommendation:",
                top.title,
                "",
                "Why it matters:",
                top.risk,
                "",
                "Impact:",
                top.impact,
                "",
                "Confidence:",
                top.confidence.title(),
                "",
                "Evidence:",
                top.evidence_summary,
                "",
                "Memory:",
                _memory_label(memory),
                "",
                "Next Action:",
                top.next_best_move,
            ]
        )
        if prediction_hint is not None:
            lines.extend(["", "Prediction:", prediction_hint.prediction_title])
            reality_hint = safe_reality_calibration_report(session, actor=user)
            if reality_hint.available:
                lines.extend(["Calibration:", reality_hint.status.replace("_", " ").title()])
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


def render_decision_feedback_page(session: Session, action: str, user: User | None = None) -> Screen:
    decision = top_decision(session, actor=user)
    if decision is None:
        lines = [
            "🧠 Decision Feedback",
            "",
            "There is no active decision to update right now.",
            "",
            "Next:",
            "Open COO Briefing when you want a fresh priority check.",
        ]
        return Screen("\n".join(lines), decision_details_menu())
    action_map = {
        "helpful": ("Helpful", "Fortuna will trust similar recommendations a little more when the evidence matches."),
        "not_helpful": ("Not Helpful", "Fortuna will lower similar low-risk recommendations unless fresh evidence raises them again."),
        "remind_later": ("Remind Later", "Fortuna will keep the evidence, but avoid pushing this unless it becomes more urgent."),
        "dismissed": ("Dismissed", "Fortuna will hide this unless severity increases or new evidence appears."),
        "learn_from_this": ("Learn From This", "Fortuna recorded that this decision is worth learning from."),
    }
    label, note = action_map.get(action, ("Recorded", "Fortuna recorded your feedback."))
    record_decision_memory_event(session, decision=decision, action=action, actor=user, owner_feedback=label)
    memory = _top_memory(session, decision)
    lines = [
        "🧠 Decision Feedback",
        "",
        label,
        "",
        "Decision:",
        decision.title,
        "",
        "What changed:",
        note,
        "",
        "Memory:",
        _memory_label(memory),
        "",
        "Next:",
        "Open Decision Memory to review what Fortuna has learned.",
    ]
    return Screen("\n".join(lines), decision_details_menu())


def render_decision_memory_page(
    session: Session,
    user: User | None = None,
    *,
    status_filter: str | None = None,
    details: bool = False,
) -> Screen:
    summary = decision_memory_summary(session)
    query = select(DecisionMemory).order_by(desc(DecisionMemory.updated_at), desc(DecisionMemory.id)).limit(12)
    if status_filter == "active":
        query = select(DecisionMemory).where(DecisionMemory.lifecycle_status.in_(("active", "opened", "in_progress"))).order_by(desc(DecisionMemory.updated_at), desc(DecisionMemory.id)).limit(12)
    elif status_filter == "resolved":
        query = select(DecisionMemory).where(DecisionMemory.lifecycle_status == "resolved").order_by(desc(DecisionMemory.updated_at), desc(DecisionMemory.id)).limit(12)
    elif status_filter == "waiting":
        query = select(DecisionMemory).where(DecisionMemory.lifecycle_status == "waiting_for_evidence").order_by(desc(DecisionMemory.updated_at), desc(DecisionMemory.id)).limit(12)
    elif status_filter == "dismissed":
        query = select(DecisionMemory).where(DecisionMemory.lifecycle_status == "dismissed").order_by(desc(DecisionMemory.updated_at), desc(DecisionMemory.id)).limit(12)
    memories = list(session.scalars(query).all())
    lines = [
        "🧠 Decision Memory",
        "",
        "Status:",
        "Fortuna is learning from your actions.",
        "",
        "What Fortuna noticed:",
    ]
    meaningful = tuple(summary.get("meaningful_lines") or ())
    if meaningful:
        lines.extend(f"- {item}" for item in meaningful)
    else:
        lines.append("- Not enough decision history yet.")
    lines.extend(
        [
            "",
            "Learning Signals:",
            f"Opened rate: {int(float(summary.get('opened_rate') or 0) * 100)}%",
            f"Acted-on rate: {int(float(summary.get('acted_on_rate') or 0) * 100)}%",
            f"Resolved rate: {int(float(summary.get('resolved_rate') or 0) * 100)}%",
            f"Usefulness score: {summary.get('usefulness_score') or 0}/100",
            "",
            "Recent Memory:",
        ]
    )
    if not memories:
        lines.append("- No matching decision memory yet.")
    for memory in memories[:6]:
        title = str((memory.metadata_json or {}).get("title") or memory.category.replace("_", " ").title())
        lines.append(f"- {title}: {(memory.lifecycle_status or memory.outcome).replace('_', ' ')}")
        if details:
            lines.append(f"  Evidence: {memory.evidence_summary}")
            lines.append(f"  Feedback: {memory.owner_feedback or 'None'}")
    return Screen("\n".join(lines), decision_memory_menu())

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

