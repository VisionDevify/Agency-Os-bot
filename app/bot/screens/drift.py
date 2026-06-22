from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen, format_user_datetime
from app.models.agency_drift import AgencyDriftFinding, AgencyPlan
from app.models.user import User
from app.services.agency_drift import (
    MANUAL_PLAN_TEMPLATES,
    agency_drift_report,
    create_manual_plan_from_template,
    set_plan_status,
)


def _drift_menu(*, back_to: str = "command_center:intelligence") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Active Drift", callback_data=callback_for("drift:active")),
            InlineKeyboardButton(text="Plans", callback_data=callback_for("drift:plans")),
        ],
        [
            InlineKeyboardButton(text="Add Plan", callback_data=callback_for("drift:add")),
            InlineKeyboardButton(text="Resolved", callback_data=callback_for("drift:resolved")),
        ],
        [InlineKeyboardButton(text="Details", callback_data=callback_for("drift:details"))],
    ]
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _plan_action_menu(plan: AgencyPlan) -> InlineKeyboardMarkup:
    rows = []
    if plan.status == "active":
        rows.append(
            [
                InlineKeyboardButton(text="Pause", callback_data=callback_for(f"drift:plan:{plan.id}:pause")),
                InlineKeyboardButton(text="Mark Complete", callback_data=callback_for(f"drift:plan:{plan.id}:complete")),
            ]
        )
    elif plan.status == "paused":
        rows.append([InlineKeyboardButton(text="Resume", callback_data=callback_for(f"drift:plan:{plan.id}:resume"))])
    rows.append([InlineKeyboardButton(text="Plans", callback_data=callback_for("drift:plans"))])
    rows.extend(page_controls(back_to="drift"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _finding_summary(finding: AgencyDriftFinding) -> list[str]:
    return [
        finding.domain.replace("_", " ").title(),
        "Expected:",
        finding.expected,
        "Observed:",
        finding.observed,
        "Why it matters:",
        finding.gap.replace("_", " "),
        "Confidence:",
        finding.confidence.title(),
        "Next:",
        finding.next_best_move,
    ]


def render_drift_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    report = agency_drift_report(session, persist=not details)
    if details:
        return render_drift_details_page(session, user)
    top = report.top_drift
    lines = [
        "🧭 Drift Detection",
        "",
        "Status:",
        report.status.replace("_", " ").title(),
        "",
        "What this is:",
        "Fortuna compares active plans with what the system and owner records show actually happened.",
        "",
        "What Fortuna checked:",
    ]
    lines.extend(f"- {item.replace('_', ' ').title()}" for item in report.checked[:6])
    lines.extend(
        [
            "",
            "Current Drift:",
            f"{len(report.active_findings)} active item(s)",
            "",
            "Top Drift:",
            top.gap.replace("_", " ").title() if top is not None else "No active drift right now.",
            "",
            "Next Best Move:",
            report.next_best_move,
        ]
    )
    if report.visibility_gap_count:
        lines.extend(
            [
                "",
                "Visibility note:",
                "Some gaps mean Fortuna needs more information. Missing data is not automatically failure.",
            ]
        )
    return Screen("\n".join(lines), _drift_menu())


def render_active_drift_page(session: Session, user: User | None = None) -> Screen:
    report = agency_drift_report(session, persist=False)
    lines = [
        "Active Drift",
        "",
        "What this is:",
        "Places where an active expectation and current evidence do not fully line up.",
        "",
    ]
    if not report.active_findings:
        lines.extend(["Status:", "No active drift is showing right now.", "", "Next Best Move:", "Keep plans updated."])
    else:
        for finding in report.active_findings[:6]:
            lines.extend(_finding_summary(finding))
            lines.append("")
        lines.extend(["Missing data note:", "A visibility gap means Fortuna should ask for evidence, not blame anyone."])
    return Screen("\n".join(lines), _drift_menu(back_to="drift"))


def render_drift_plans_page(session: Session, user: User | None = None) -> Screen:
    report = agency_drift_report(session, persist=False)
    lines = [
        "Plans",
        "",
        "What this is:",
        "The expectations Fortuna is allowed to compare against reality.",
        "",
    ]
    active_plans = [plan for plan in report.plans if plan.status == "active"]
    if not active_plans:
        lines.extend(["Status:", "No active plans are configured yet.", "", "Next Best Move:", "Add a structured plan."])
    else:
        for plan in active_plans[:10]:
            lines.extend(
                [
                    plan.title,
                    f"Cadence: {plan.expected_cadence}",
                    f"Status: {plan.status.title()}",
                    f"Confidence: {plan.confidence.title()}",
                    f"Next check: {plan.expected_signal}",
                    "",
                ]
            )
    rows = []
    if active_plans:
        for plan in active_plans[:4]:
            rows.append([(f"Manage {plan.title[:22]}", f"drift:plan:{plan.id}")])
    rows.append([("Add Plan", "drift:add")])
    keyboard = [[InlineKeyboardButton(text=label, callback_data=callback_for(page)) for label, page in row] for row in rows]
    keyboard.extend(page_controls(back_to="drift"))
    return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


def render_add_plan_page(session: Session, user: User | None = None) -> Screen:
    lines = [
        "Add Plan",
        "",
        "What this is:",
        "Structured templates for expectations Fortuna can track without free-form risky input.",
        "",
        "Choose a template:",
        "- Posting cadence",
        "- Creator outreach",
        "- Fan/whale tracking",
        "- Recovery/system check",
        "- Custom note placeholder",
        "",
        "Next Best Move:",
        "Start with one plan you actually want checked.",
    ]
    rows = [
        [("Posting cadence", "drift:add:posting")],
        [("Creator outreach", "drift:add:creator_outreach")],
        [("Fan/whale tracking", "drift:add:fan_whale_tracking")],
        [("Recovery/system check", "drift:add:recovery_check")],
        [("Custom placeholder", "drift:add:custom_placeholder")],
    ]
    keyboard = [[InlineKeyboardButton(text=label, callback_data=callback_for(page)) for label, page in row] for row in rows]
    keyboard.extend(page_controls(back_to="drift"))
    return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


def render_drift_plan_added_page(session: Session, template_key: str, user: User | None = None) -> Screen:
    plan = create_manual_plan_from_template(session, template_key)
    title = MANUAL_PLAN_TEMPLATES.get(template_key, MANUAL_PLAN_TEMPLATES["custom_placeholder"]).title
    lines = [
        "Plan Added",
        "",
        "Status:",
        "Tracking started.",
        "",
        "Plan:",
        title,
        "",
        "What happens next:",
        "Fortuna will compare this expectation with manual/system evidence. Missing data starts as a visibility gap, not blame.",
        "",
        "Next Best Move:",
        "Add a matching manual agency record when this work happens, or pause the plan if it is not active.",
    ]
    return Screen("\n".join(lines), _plan_action_menu(plan))


def render_drift_plan_detail_page(session: Session, plan_id: int, user: User | None = None) -> Screen:
    plan = session.get(AgencyPlan, plan_id)
    if plan is None:
        return Screen("Plan\n\nThis plan was not found.\n\nNext Best Move:\nOpen Plans.", _drift_menu(back_to="drift:plans"))
    lines = [
        "Plan",
        "",
        plan.title,
        "",
        "Status:",
        plan.status.title(),
        "",
        "Expected:",
        plan.expected_signal,
        "",
        "Cadence:",
        plan.expected_cadence,
        "",
        "Confidence:",
        plan.confidence.title(),
        "",
        "Evidence:",
        plan.evidence_summary,
    ]
    return Screen("\n".join(lines), _plan_action_menu(plan))


def render_drift_plan_status_page(session: Session, plan_id: int, status: str, user: User | None = None) -> Screen:
    canonical = {"pause": "paused", "resume": "active", "complete": "completed", "cancel": "cancelled"}.get(status, status)
    plan = set_plan_status(session, plan_id, canonical)
    if plan is None:
        return Screen("Plan Update\n\nFortuna could not update that plan safely.", _drift_menu(back_to="drift:plans"))
    lines = [
        "Plan Updated",
        "",
        "Status:",
        plan.status.title(),
        "",
        "Plan:",
        plan.title,
        "",
        "Next Best Move:",
        "Open Plans or Drift Detection to review the current state.",
    ]
    return Screen("\n".join(lines), _plan_action_menu(plan))


def render_resolved_drift_page(session: Session, user: User | None = None) -> Screen:
    report = agency_drift_report(session, persist=False)
    lines = [
        "Resolved Drift",
        "",
        "What this is:",
        "Old plan-vs-reality gaps that revalidated or closed.",
        "",
    ]
    if not report.resolved_findings:
        lines.extend(["Status:", "No resolved drift history yet.", "", "Next Best Move:", "Keep using Drift Detection."])
    else:
        for finding in report.resolved_findings[:8]:
            when = format_user_datetime(user, finding.resolved_at or finding.last_seen_at)
            lines.extend(
                [
                    finding.domain.replace("_", " ").title(),
                    f"Status: {finding.status.replace('_', ' ').title()}",
                    f"Last checked: {when}",
                    f"Evidence: {finding.observed}",
                    "",
                ]
            )
    return Screen("\n".join(lines), _drift_menu(back_to="drift"))


def render_drift_details_page(session: Session, user: User | None = None) -> Screen:
    report = agency_drift_report(session, persist=False)
    lines = [
        "Drift Details",
        "",
        "No raw private data or secrets are shown here.",
        "",
        f"Generated: {format_user_datetime(user, report.generated_at)}",
        f"Status: {report.status}",
        f"Active findings: {len(report.active_findings)}",
        f"Visibility gaps: {report.visibility_gap_count}",
        f"Plans tracked: {len(report.plans)}",
        "",
        "Evidence rule:",
        "Drift requires an expectation. Missing data without an expectation is a visibility gap.",
    ]
    if report.active_findings:
        lines.extend(["", "Current findings:"])
        for finding in report.active_findings[:8]:
            lines.append(f"- {finding.domain}: {finding.gap} ({finding.status}, {finding.confidence})")
    lines.extend(
        [
            "",
            "AI/Search boundary:",
            "AI may explain drift. Search can add context. Neither can prove internal agency activity without agency evidence.",
        ]
    )
    return Screen("\n".join(lines), _drift_menu(back_to="drift"))
