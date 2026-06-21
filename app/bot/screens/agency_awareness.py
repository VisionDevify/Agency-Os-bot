from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen, format_user_datetime
from app.models.user import User
from app.services.agency_awareness import AgencyAwarenessReport, agency_awareness_report


STATUS_LABELS = {
    "healthy": "Healthy",
    "needs_review": "Needs Review",
    "needs_attention": "Needs Attention",
    "degraded": "Limited Visibility",
    "insufficient_data": "Needs More Information",
}

STATUS_ICONS = {
    "healthy": "🟢",
    "needs_review": "🟡",
    "needs_attention": "🟠",
    "degraded": "🟡",
    "insufficient_data": "⚪",
}


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def _status_icon(status: str) -> str:
    return STATUS_ICONS.get(status, "⚪")


def _freshness(report: AgencyAwarenessReport, user: User | None) -> str:
    label = "live" if report.snapshot_source == "live" and not report.stale else "fallback"
    return f"{label} snapshot · {format_user_datetime(user, report.generated_at)}"


def _domain_line(domain) -> str:
    stale = " · older evidence" if domain.stale else ""
    unavailable = " · temporarily unavailable" if domain.unavailable else ""
    return f"- {domain.display_name}: {domain.status.replace('_', ' ').title()} ({domain.confidence} confidence){stale}{unavailable}"


def _domain_summary(domain) -> list[str]:
    return [
        f"{domain.display_name}",
        f"Status: {domain.status.replace('_', ' ').title()}",
        f"Why: {domain.evidence_summary}",
        f"Confidence: {domain.confidence.title()}",
        f"Next: {domain.next_best_move}",
    ]


def _awareness_menu(*, back_to: str = "owner_advanced", include_refresh: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if include_refresh:
        rows.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("agency_awareness"))])
    rows.extend(
        [
            [InlineKeyboardButton(text="✅ Active Areas", callback_data=callback_for("agency_awareness:active"))],
            [InlineKeyboardButton(text="🕳 Missing / Inactive", callback_data=callback_for("agency_awareness:missing"))],
            [InlineKeyboardButton(text="🔌 Not Connected", callback_data=callback_for("agency_awareness:not_connected"))],
            [
                InlineKeyboardButton(text="🧾 Evidence", callback_data=callback_for("agency_awareness:evidence")),
                InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("agency_awareness:details")),
            ],
        ]
    )
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_agency_awareness_page(
    session: Session,
    user: User | None = None,
    *,
    details: bool = False,
) -> Screen:
    report = agency_awareness_report(session, persist=not details)
    if details:
        return render_agency_awareness_details_page(session, user, report=report)

    visible = list(report.active_domains[:5])
    limited = list(report.missing_domains[:3]) + list(report.not_connected_domains[:3])
    lines = [
        "🧭 Agency Awareness",
        "",
        "Status:",
        f"{_status_icon(report.overall_status)} {_status_label(report.overall_status)}",
        "",
        "What this is:",
        "Fortuna's current map of what the agency is doing and where visibility is still missing.",
        "",
        "What Fortuna can see:",
    ]
    if visible:
        lines.extend(_domain_line(domain) for domain in visible)
    else:
        lines.append("- Not enough live agency activity is visible yet.")
    lines.extend(["", "What Fortuna cannot see:"])
    if limited:
        lines.extend(_domain_line(domain) for domain in limited[:6])
    else:
        lines.append("- No major visibility gaps are showing right now.")
    if report.fallback_notice:
        lines.extend(["", "Limited visibility:", report.fallback_notice])
    if report.missing_inputs:
        lines.extend(["", "Unavailable source:", ", ".join(report.missing_inputs[:4])])
    lines.extend(
        [
            "",
            "Top Focus Area:",
            report.top_focus_area,
            "",
            "✨ Next Best Move",
            report.next_best_move,
            "",
            _freshness(report, user),
        ]
    )
    return Screen("\n".join(lines), _awareness_menu())


def render_agency_active_areas_page(session: Session, user: User | None = None) -> Screen:
    report = agency_awareness_report(session, persist=False)
    lines = [
        "✅ Active Areas",
        "",
        "What this is:",
        "Agency areas where Fortuna has current or useful evidence.",
        "",
        "Why it matters:",
        "Active areas can be used for COO Briefing, Today, and recommendations.",
        "",
    ]
    if not report.active_domains:
        lines.extend(
            [
                "Status:",
                "Fortuna does not have enough evidence to call any agency area active yet.",
                "",
                "✨ Next Best Move",
                "Add manual agency records or connect approved sources when work begins.",
            ]
        )
    else:
        for domain in report.active_domains[:8]:
            lines.extend(_domain_summary(domain))
            lines.append("")
        lines.extend(["✨ Next Best Move", "Use these active areas to decide what matters today."])
    return Screen("\n".join(lines), _awareness_menu(back_to="agency_awareness", include_refresh=False))


def render_agency_missing_page(session: Session, user: User | None = None) -> Screen:
    report = agency_awareness_report(session, persist=False)
    domains = list(report.missing_domains) + list(report.inactive_domains)
    lines = [
        "🕳 Missing / Inactive",
        "",
        "What this is:",
        "Areas where Fortuna needs more information or has only weak/stale visibility.",
        "",
        "Why it matters:",
        "Missing data is not failure. It means Fortuna should not pretend to understand that work yet.",
        "",
    ]
    if not domains:
        lines.extend(["Status:", "No missing or inactive agency areas are currently flagged."])
    else:
        for domain in domains[:10]:
            lines.extend(
                [
                    domain.display_name,
                    "Fortuna needs more information here.",
                    f"Why: {domain.evidence_summary}",
                    f"Next: {domain.next_best_move}",
                    "",
                ]
            )
    lines.extend(["✨ Next Best Move", report.next_best_move])
    return Screen("\n".join(lines), _awareness_menu(back_to="agency_awareness", include_refresh=False))


def render_agency_not_connected_page(session: Session, user: User | None = None) -> Screen:
    report = agency_awareness_report(session, persist=False)
    domains = list(report.not_connected_domains)
    lines = [
        "🔌 Not Connected",
        "",
        "What this is:",
        "External platforms and data sources that are not connected yet, ready to connect, or temporarily unavailable.",
        "",
        "Why it matters:",
        "Not connected is setup status. It does not mean broken.",
        "",
    ]
    if not domains:
        lines.extend(["Status:", "No disconnected platform areas are currently flagged."])
    else:
        for domain in domains[:10]:
            state = domain.connection_state or domain.status
            lines.extend(
                [
                    domain.display_name,
                    f"State: {state.replace('_', ' ').title()}",
                    f"Why it matters: {domain.why_it_matters}",
                    f"What it unlocks: {domain.data_unlocked}",
                    f"When to connect: {domain.recommended_timing}",
                    f"Next: {domain.next_best_move}",
                    "",
                ]
            )
    lines.extend(["✨ Next Best Move", "Connect only when an active workflow needs that source."])
    return Screen("\n".join(lines), _awareness_menu(back_to="agency_awareness", include_refresh=False))


def render_agency_evidence_page(session: Session, user: User | None = None) -> Screen:
    report = agency_awareness_report(session, persist=False)
    lines = [
        "🧾 Agency Awareness Evidence",
        "",
        "Status:",
        f"{_status_icon(report.overall_status)} {_status_label(report.overall_status)}",
        "",
        "Visibility:",
        f"{report.visibility_level.title()} ({report.visibility_score}/100)",
        "",
        "Confidence:",
        f"{report.confidence_score}/100",
        "",
        "What Fortuna used:",
        report.evidence_summary,
    ]
    if report.missing_inputs:
        lines.extend(["", "Unavailable inputs:", *[f"- {item}" for item in report.missing_inputs[:8]]])
    lines.extend(["", "Snapshot:", _freshness(report, user), "", "✨ Next Best Move", report.next_best_move])
    return Screen("\n".join(lines), _awareness_menu(back_to="agency_awareness", include_refresh=False))


def render_agency_awareness_details_page(
    session: Session,
    user: User | None = None,
    *,
    report: AgencyAwarenessReport | None = None,
) -> Screen:
    report = report or agency_awareness_report(session, persist=False)
    lines = [
        "🔎 Agency Awareness Details",
        "",
        "No secrets or raw IDs are shown here.",
        "",
        f"Snapshot: {_freshness(report, user)}",
        f"Status: {_status_label(report.overall_status)}",
        f"Visibility: {report.visibility_level.title()} ({report.visibility_score}/100)",
        f"Confidence: {report.confidence_score}/100",
        f"Degraded mode: {'Yes' if report.degraded_mode else 'No'}",
        "",
        "Domains:",
    ]
    for domain in report.domains:
        lines.append(
            f"- {domain.display_name}: {domain.status.replace('_', ' ').title()} | {domain.confidence} | {domain.source}"
        )
    if report.missing_inputs:
        lines.extend(["", "Missing inputs:", *[f"- {item}" for item in report.missing_inputs]])
    lines.extend(["", "Top focus:", report.top_focus_area, "", "Next:", report.next_best_move])
    return Screen("\n".join(lines), _awareness_menu(back_to="agency_awareness", include_refresh=False))
