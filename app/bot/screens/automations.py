from .formatting import *

FRIENDLY_AUTOMATION_NAMES = {
    "Daily Intelligence Scan": "Daily Checkup",
    "Daily Executive Digest": "Daily Summary",
    "Overdue Task Escalation": "Nudge Overdue Work",
    "Critical Incident Escalation": "Escalate Urgent Issues",
    "Proxy Repair Assistant": "Proxy Helper",
    "Notification Failure Watch": "Notification Watch",
}


def _friendly_automation_name(name: str) -> str:
    return FRIENDLY_AUTOMATION_NAMES.get(name, name)


def render_automations_home(session: Session | None = None, user: User | None = None) -> Screen:
    lines = ["\U0001f916 Fortuna Automation", ""]
    if session is not None:
        seed_builtin_automation_templates(session, actor=user)
        metrics = automation_metrics(session)
        waiting: list[str] = []
        if metrics["pending_approvals"]:
            waiting.append("Approvals need review.")
        if metrics["failed_automations"]:
            waiting.append("Some automations need attention.")
        if not waiting:
            waiting.append("Alerts need notification groups.")
            waiting.append("Proxy repair needs real proxy data.")
        lines.extend(
            [
                "Active",
                "- Daily Checkup" if metrics["active_automations"] else "- Safe mode only",
                "",
                "Waiting",
                *[f"- {item}" for item in waiting[:2]],
                "",
                "Recommended",
                "Keep automations in safe mode until setup is complete.",
            ]
        )
    else:
        lines.extend(["Active", "- Safe mode only", "", "Recommended", "Preview before anything runs."])
    return Screen(text="\n".join(lines), reply_markup=automations_menu())

def render_automation_rules_page(session: Session, user: User | None = None) -> Screen:
    seed_builtin_automation_templates(session, actor=user)
    rules = list_automation_rules(session)
    lines = ["Automation Rules", ""]
    buttons: list[tuple[str, str]] = []
    if not rules:
        lines.append("No automation rules yet.")
    for rule in rules[:20]:
        lines.append(f"{rule.id}. {rule.name}")
        lines.append(f"   {_automation_status_line(rule)}")
        buttons.append((f"{rule.id}. {rule.name[:36]}", f"nav:automation:{rule.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_rules_menu(buttons))

def render_automation_templates_page(session: Session, user: User | None = None) -> Screen:
    rules = seed_builtin_automation_templates(session, actor=user)
    by_type = {rule.automation_type: rule for rule in rules}
    lines = ["Built-In Automation Templates", ""]
    buttons: list[tuple[str, str]] = []
    for template in BUILTIN_AUTOMATION_TEMPLATES:
        rule = by_type.get(template.automation_type)
        status = rule.status if rule else "not seeded"
        lines.append(f"- {_friendly_automation_name(template.name)}")
        lines.append(f"  Risk: {template.risk_level} | Status: {status}")
        lines.append(f"  What starts it: {template.trigger_type}")
        if rule:
            buttons.append((_friendly_automation_name(template.name)[:40], f"nav:automation:{rule.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_templates_menu(buttons))

def render_automation_rule_detail_page(session: Session, rule_id: int) -> Screen:
    rule = get_automation_rule(session, rule_id)
    if rule is None:
        return Screen(text="Automation rule not found.", reply_markup=page_menu(back_to="automations:rules"))
    latest_approval = latest_rule_approval(session, rule)
    rollback = rollback_plan_for_rule(rule)
    lines = [
        "Automation Rule",
        "",
        f"Name: {rule.name}",
        f"Status: {rule.status}",
        f"Category: {rule.category}",
        f"Risk: {_status_marker(rule.risk_level)} {rule.risk_level}",
        f"Owner Approval Required: {'yes' if rule.requires_owner_approval else 'no'}",
        f"Latest Approval: {latest_approval.status if latest_approval else 'none'}",
        f"Last Simulated: {format_user_datetime(None, rule.last_simulated_at) if rule.last_simulated_at else 'never'}",
        f"Last Run: {format_user_datetime(None, rule.last_run_at) if rule.last_run_at else 'never'}",
        "",
        "What starts it:",
        f"- {rule.trigger_type}",
    ]
    lines.extend(_json_lines("Checks before running:", rule.conditions_json))
    lines.extend(_json_lines("What it will do:", rule.actions_json))
    lines.extend(_json_lines("How to undo it:", rollback.get("steps", [])))
    if rollback.get("limitations"):
        lines.extend(_json_lines("Rollback limitations:", rollback["limitations"], limit=4))
    return Screen(text="\n".join(lines), reply_markup=automation_rule_detail_menu(rule.id, rule.status))

def render_automation_rule_simulations_page(session: Session, rule_id: int) -> Screen:
    rule = get_automation_rule(session, rule_id)
    if rule is None:
        return Screen(text="Automation rule not found.", reply_markup=page_menu(back_to="automations:rules"))
    runs = [
        run
        for run in list_simulation_runs(session, limit=50)
        if run.automation_rule_id == rule.id
    ]
    lines = ["Simulation Results", "", f"Rule: {rule.name}", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No simulations for this rule yet.")
    for run in runs[:10]:
        lines.append(f"{run.id}. {run.status} | Risk: {run.risk_level}")
        lines.append(f"   Would trigger: {run.would_trigger_count} | Fail: {run.would_fail_count}")
        buttons.append((f"{run.id}. {run.status}", f"nav:simulation:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=simulation_runs_menu(buttons))

def render_automation_rollback_page(session: Session, rule_id: int) -> Screen:
    rule = get_automation_rule(session, rule_id)
    if rule is None:
        return Screen(text="Automation rule not found.", reply_markup=page_menu(back_to="automations:rules"))
    plan = rollback_plan_for_rule(rule)
    lines = ["Rollback Plan", "", f"Rule: {rule.name}", f"Rollback Available: {'yes' if plan.get('available') else 'no'}", ""]
    lines.extend(_json_lines("Rollback steps:", plan.get("steps", [])))
    lines.extend(_json_lines("Limitations:", plan.get("limitations", [])))
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"automation:{rule.id}"))

def render_automation_approvals_page(session: Session) -> Screen:
    approvals = pending_approvals(session)
    lines = ["Pending Automation Approvals", ""]
    buttons: list[tuple[str, str]] = []
    if not approvals:
        lines.append("No pending approvals.")
    for approval in approvals:
        rule_name = approval.rule.name if approval.rule else f"Rule {approval.automation_rule_id}"
        lines.append(f"{approval.id}. {rule_name}")
        lines.append(f"   Status: {approval.status} | Expires: {format_user_datetime(None, approval.expires_at) if approval.expires_at else 'not set'}")
        buttons.append((f"{approval.id}. {rule_name[:34]}", f"nav:approval:{approval.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_approvals_menu(buttons))

def render_automation_approval_detail_page(session: Session, approval_id: int) -> Screen:
    approval = session.get(AutomationApproval, approval_id)
    if approval is None:
        return Screen(text="Approval not found.", reply_markup=page_menu(back_to="automations:approvals"))
    rule = approval.rule
    lines = [
        "Automation Approval",
        "",
        f"Rule: {rule.name if rule else approval.automation_rule_id}",
        f"Status: {approval.status}",
        f"Risk: {rule.risk_level if rule else 'unknown'}",
        f"Requested By: {approval.requested_by_user_id}",
        f"Approved By: {approval.approved_by_user_id or 'pending'}",
        f"Expires: {format_user_datetime(None, approval.expires_at) if approval.expires_at else 'not set'}",
        f"Reason: {approval.approval_reason or 'None'}",
    ]
    return Screen(text="\n".join(lines), reply_markup=automation_approval_detail_menu(approval.id, approval.automation_rule_id))

def render_automation_runs_page(session: Session, *, rule_id: int | None = None) -> Screen:
    runs = latest_automation_runs(session, limit=30)
    if rule_id is not None:
        runs = [run for run in runs if run.automation_rule_id == rule_id]
    lines = ["Automation Run History", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No automation runs yet.")
    for run in runs[:15]:
        rule_name = run.rule.name if run.rule else f"Rule {run.automation_rule_id}"
        lines.append(f"{run.id}. {rule_name}")
        lines.append(f"   Status: {run.status} | Rollback: {run.rollback_status}")
        lines.append(f"   Started: {format_user_datetime(None, run.started_at) if run.started_at else 'not started'}")
        buttons.append((f"{run.id}. {rule_name[:34]}", f"nav:automation_run:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_runs_menu(buttons))

def render_automation_run_detail_page(session: Session, run_id: int) -> Screen:
    run = get_automation_run(session, run_id)
    if run is None:
        return Screen(text="Automation run not found.", reply_markup=page_menu(back_to="automations:runs"))
    lines = [
        "Automation Run",
        "",
        f"Rule: {run.rule.name if run.rule else run.automation_rule_id}",
        f"Status: {run.status}",
        f"Rollback Available: {'yes' if run.rollback_available else 'no'}",
        f"Rollback Status: {run.rollback_status}",
        f"Started: {format_user_datetime(None, run.started_at) if run.started_at else 'not started'}",
        f"Finished: {format_user_datetime(None, run.finished_at) if run.finished_at else 'not finished'}",
        f"Error: {run.error_message or 'None'}",
        "",
        "Steps:",
    ]
    buttons: list[tuple[str, str]] = []
    if not run.steps:
        lines.append("- No step records yet.")
    for step in sorted(run.steps, key=lambda item: item.step_order):
        lines.append(f"- {step.step_order}. {step.action_type}: {step.status}")
        buttons.append((f"{step.step_order}. {step.action_type[:32]}", f"nav:automation_step:{step.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_run_detail_menu(run.id, buttons))

def render_automation_step_detail_page(session: Session, step_id: int) -> Screen:
    step = get_automation_step(session, step_id)
    if step is None:
        return Screen(text="Automation step not found.", reply_markup=page_menu(back_to="automations:runs"))
    lines = [
        "Automation Step",
        "",
        f"Action: {step.action_type}",
        f"Status: {step.status}",
        f"Entity: {step.entity_type or 'n/a'}:{step.entity_id or 'n/a'}",
        f"Started: {format_user_datetime(None, step.started_at) if step.started_at else 'not started'}",
        f"Finished: {format_user_datetime(None, step.finished_at) if step.finished_at else 'not finished'}",
        f"Error: {step.error_message or 'None'}",
    ]
    lines.extend(_json_lines("Input:", step.input_json, limit=6))
    lines.extend(_json_lines("Output:", step.output_json, limit=6))
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"automation_run:{step.automation_run_id}"))

def render_automation_health_page(session: Session) -> Screen:
    metrics = automation_metrics(session)
    issues = metrics["failed_automations"] + metrics["pending_approvals"]
    if metrics["failed_automations"]:
        status = "Needs Attention"
        next_action = "Review failed automations before enabling anything new."
    elif metrics["pending_approvals"]:
        status = "Waiting on Approval"
        next_action = "Review pending approvals."
    else:
        status = "Healthy"
        next_action = "No action needed."
    lines = [
        "Automation Health",
        "",
        f"Status: {status}",
        f"Issues Found: {issues}",
        "",
        "Recommended Action:",
        next_action,
        "",
        "Technical Details:",
        f"Total Rules: {metrics['total_rules']}",
        f"Active: {metrics['active_automations']}",
        f"Failed: {metrics['failed_automations']}",
        f"Pending Approvals: {metrics['pending_approvals']}",
        f"Total Simulations: {metrics['total_simulations']}",
        f"Total Runs: {metrics['total_runs']}",
        f"Success Count: {metrics['success_count']}",
        f"Failure Count: {metrics['failure_count']}",
        f"Skipped Count: {metrics['skipped_count']}",
        f"Rollback Count: {metrics['rollback_count']}",
        f"Last Run: {metrics['last_automation_run']} ({metrics['last_run_status']})",
        f"Average Duration: {metrics['average_duration_seconds']}s",
        f"Affected Entities: {metrics['affected_entities_count']}",
        f"Success Rate: {metrics['automation_success_rate']}%",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="automations"))

def render_simulation_runs_page(session: Session) -> Screen:
    runs = list_simulation_runs(session)
    lines = ["Automation Simulation Runs", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No simulation runs yet.")
    for run in runs[:15]:
        created = format_user_datetime(None, run.created_at) if run.created_at else "pending timestamp"
        lines.append(f"{run.id}. {run.automation_name}")
        lines.append(
            f"   Status: {run.status} | Risk: {run.risk_level} | Would Trigger: {run.would_trigger_count}"
        )
        lines.append(f"   Created: {created}")
        buttons.append((f"{run.id}. {run.automation_name}", f"nav:simulation:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=simulation_runs_menu(buttons))

def render_simulation_run_detail_page(session: Session, run_id: int) -> Screen:
    run = session.get(AutomationSimulationRun, run_id)
    if run is None:
        return Screen(text="Simulation run not found.", reply_markup=page_menu(back_to="automations:simulations"))
    expires = format_user_datetime(None, run.expires_at) if run.expires_at else "not set"
    impact = run.impact_summary_json or {}
    lines = [
        "Simulation Impact Preview",
        "",
        f"Automation: {run.automation_name}",
        f"Type: {run.automation_type}",
        f"Rule: {run.automation_rule_id or 'legacy/manual'}",
        f"Status: {run.status}",
        f"Risk: {_status_marker(run.risk_level)} {run.risk_level}",
        f"Target Scope: {run.target_scope}",
        f"Would Trigger: {run.would_trigger_count}",
        f"Would Succeed: {run.would_succeed_count}",
        f"Would Fail: {run.would_fail_count}",
        f"Expires: {expires}",
        "",
        "Impact Summary:",
    ]
    for key, value in sorted(impact.items()):
        lines.append(f"- {key}: {value}")
    if not impact:
        lines.append("- No impact details recorded")
    if run.affected_entities_json:
        lines.extend(["", "What could be affected:"])
        for item in run.affected_entities_json[:8]:
            if isinstance(item, dict):
                lines.append("- " + ", ".join(f"{key}: {value}" for key, value in item.items()))
            else:
                lines.append(f"- {item}")
    if run.warnings_json:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in run.warnings_json[:6])
    lines.extend(["", "No production changes are applied by simulation runs."])
    return Screen(text="\n".join(lines), reply_markup=simulation_run_detail_menu(run.id))

