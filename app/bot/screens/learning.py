from .formatting import *

def render_learning_center_page(session: Session) -> Screen:
    metrics = learning_center_metrics(session)
    repeated_failures = metrics["repeated_failures"][:3]
    status = "Learning quietly" if metrics["total_learning_events"] else "Still learning"
    if repeated_failures:
        status = "Needs attention"
    next_action = (
        "Review the repeated failures first."
        if repeated_failures
        else "Run real alerts so Fortuna can learn what works."
    )
    lines = [
        "\U0001f9e0 What Fortuna Learned",
        "",
        "Fortuna is still learning from your workflow.",
        "",
        f"Status: {status}",
        "",
        "Recent Lessons",
    ]
    for memory in repeated_failures:
        lines.append(f"- {memory.summary}")
    if not repeated_failures:
        lines.append("- No repeated failures yet.")
        lines.append("- Notifications still need setup." if not metrics["recent_events"] else "- Fortuna has new workflow history.")
    lines.extend(["", "Best Next Lesson", next_action])
    return Screen(text="\n".join(lines), reply_markup=learning_center_menu())


def render_learning_details_page(session: Session) -> Screen:
    metrics = learning_center_metrics(session)
    repeated_failures = metrics["repeated_failures"][:3]
    lines = [
        "Learning Center - More Details",
        "",
        f"Total Learning Events: {metrics['total_learning_events']}",
        f"Active Playbooks: {metrics['active_playbooks']}",
        f"Outcome Memories: {metrics['outcome_memories']}",
        "",
        "Highest Confidence Playbooks:",
    ]
    for playbook in metrics["highest_confidence_playbooks"][:3]:
        lines.append(f"- {playbook.name}: {playbook.confidence_score}%")
    if not metrics["highest_confidence_playbooks"]:
        lines.append("- None yet")
    lines.extend(["", "Repeated Failures:"])
    for memory in repeated_failures:
        lines.append(f"- {memory.summary}")
    if not repeated_failures:
        lines.append("- None recorded")
    lines.extend(["", "Recent Learning Events:"])
    for event in metrics["recent_events"][:5]:
        lines.append(f"- {event.event_type}: {event.outcome}")
    if not metrics["recent_events"]:
        lines.append("- Learning events will appear as operations complete.")
    return Screen(text="\n".join(lines), reply_markup=learning_details_menu())

def render_playbooks_page(session: Session, *, recommended: bool = False) -> Screen:
    if recommended:
        pairs = recommend_playbooks(session, source_type="system", event_type="current_operations", limit=7)
        playbooks = [playbook for playbook, _reason in pairs]
        reasons = {playbook.id: reason for playbook, reason in pairs}
        title = "Recommended Playbooks"
    else:
        playbooks = list_playbooks(session)
        reasons = {}
        title = "Playbooks"
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not playbooks:
        lines.append("No playbooks yet.")
    for playbook in playbooks:
        reason = reasons.get(playbook.id)
        lines.append(f"{playbook.id}. {playbook.name}")
        lines.append(
            f"   Category: {playbook.category} | Risk: {playbook.risk_level} | Confidence: {playbook.confidence_score}%"
        )
        if reason:
            lines.append(f"   Why: {reason}")
        buttons.append((f"{playbook.id}. {playbook.name[:34]}", f"nav:playbook:{playbook.id}"))
    back_to = "intelligence:learning" if not recommended else "intelligence:learning"
    return Screen(text="\n".join(lines), reply_markup=learning_playbooks_menu(buttons, back_to=back_to))

def render_playbook_detail_page(session: Session, playbook_id: int) -> Screen:
    playbook = get_playbook(session, playbook_id)
    if playbook is None:
        return Screen(text="Playbook not found.", reply_markup=page_menu(back_to="intelligence:learning:playbooks"))
    lines = [
        "Playbook",
        "",
        f"Name: {playbook.name}",
        f"Category: {playbook.category}",
        f"Status: {playbook.status}",
        f"Risk: {_status_marker(playbook.risk_level)} {playbook.risk_level}",
        f"Confidence: {playbook.confidence_score}%",
        f"Successes: {playbook.success_count}",
        f"Failures: {playbook.failure_count}",
        "",
        "Trigger:",
        playbook.trigger_summary,
        "",
        "Diagnosis Steps:",
    ]
    lines.extend(f"- {step}" for step in (playbook.diagnosis_steps_json or [])[:6])
    lines.extend(["", "Resolution Steps:"])
    lines.extend(f"- {step}" for step in (playbook.resolution_steps_json or [])[:6])
    lines.extend(["", "Verification Steps:"])
    lines.extend(f"- {step}" for step in (playbook.verification_steps_json or [])[:6])
    if playbook.rollback_steps_json:
        lines.extend(["", "Rollback Limitations / Steps:"])
        lines.extend(f"- {step}" for step in playbook.rollback_steps_json[:5])
    return Screen(text="\n".join(lines), reply_markup=playbook_detail_menu(playbook.id))

def render_playbook_history_page(session: Session, playbook_id: int) -> Screen:
    playbook = get_playbook(session, playbook_id)
    if playbook is None:
        return Screen(text="Playbook not found.", reply_markup=page_menu(back_to="intelligence:learning:playbooks"))
    runs = sorted(playbook.runs or [], key=lambda run: run.created_at, reverse=True)[:15]
    lines = ["Playbook History", "", playbook.name, ""]
    if not runs:
        lines.append("No runs or suggestions recorded yet.")
    for run in runs:
        lines.append(f"{run.id}. {run.status}")
        lines.append(f"   Source: {run.source_type or 'general'}:{run.source_id or 'n/a'}")
        lines.append(f"   Result: {run.result_summary or 'pending'}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"playbook:{playbook.id}"))

def render_outcome_memory_page(session: Session) -> Screen:
    memories = list_outcome_memories(session, limit=25)
    lines = ["Outcome Memory", ""]
    if not memories:
        lines.append("No outcome memories yet.")
    for memory in memories:
        lines.append(f"{memory.id}. {memory.memory_type}")
        lines.append(
            f"   Seen: {memory.occurrences} | Success Rate: {memory.success_rate}% | Last: {memory.last_outcome}"
        )
        lines.append(f"   {memory.summary}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))

def render_confidence_changes_page(session: Session) -> Screen:
    records = list_confidence_records(session, limit=25)
    lines = ["Confidence Changes", ""]
    if not records:
        lines.append("No confidence changes yet.")
    for record in records:
        previous = record.previous_score if record.previous_score is not None else "baseline"
        lines.append(f"{record.id}. {record.subject_type}:{record.subject_id}")
        lines.append(f"   {previous} -> {record.new_score} | {record.reason}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))

def render_automation_learning_page(session: Session) -> Screen:
    summary = automation_learning_summary(session)
    lines = [
        "Automation Learning",
        "",
        f"Success Rate: {summary['success_rate']}%",
        f"Succeeded Runs: {summary['succeeded_runs']}",
        f"Failed Runs: {summary['failed_runs']}",
        f"Skipped Runs: {summary['skipped_runs']}",
        "",
        "Automation Memories:",
    ]
    for memory in summary["memories"][:10]:
        lines.append(f"- {memory.summary}")
    if not summary["memories"]:
        lines.append("- No automation outcome memory yet.")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))

def render_opportunity_learning_page(session: Session) -> Screen:
    summary = opportunity_learning_summary(session)
    lines = ["Opportunity Learning", "", "Best Niches:"]
    for niche, stats in summary["best_niches"][:5]:
        lines.append(f"- {niche}: {stats['success']}/{stats['total']} positive")
    if not summary["best_niches"]:
        lines.append("- No opportunity outcomes yet.")
    lines.extend(["", "Best Angles:"])
    for angle, stats in summary["best_angles"][:5]:
        lines.append(f"- {angle}: {stats['success']}/{stats['total']} positive")
    if not summary["best_angles"]:
        lines.append("- No angle memory yet.")
    lines.extend(["", "Weak Sources:"])
    for source, stats in summary["weak_sources"][:5]:
        lines.append(f"- {source}: {stats['success']}/{stats['total']} positive")
    if not summary["weak_sources"]:
        lines.append("- No weak sources identified.")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))

def render_executive_memory_briefing_page(session: Session) -> Screen:
    briefing = executive_memory_briefing(session)
    best = briefing["best_playbook"]
    lowest = briefing["lowest_confidence_playbook"]
    weakest_source = briefing["weakest_opportunity_source"]
    lines = [
        "Executive Memory Briefing",
        "",
        "What the system is learning:",
        briefing["summary"],
        "",
        f"Top Recurring Problem: {briefing['top_recurring_problem']}",
        f"Best Playbook: {best.name if best else 'Not enough data'}",
        f"Lowest Confidence Playbook: {lowest.name if lowest else 'Not enough data'}",
        f"Automation Success Rate: {briefing['automation_success_rate']}%",
        f"Weakest Opportunity Source: {weakest_source[0] if weakest_source else 'Not enough data'}",
        "",
        "Recent Confidence Changes:",
    ]
    for record in briefing["recent_confidence_changes"][:5]:
        lines.append(f"- {record.subject_type}:{record.subject_id} -> {record.new_score} ({record.reason})")
    if not briefing["recent_confidence_changes"]:
        lines.append("- None yet")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))

