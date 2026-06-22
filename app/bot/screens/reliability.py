from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.models.reliability import CallbackLatencyRecord, ReliabilityJob
from app.models.user import User
from app.services.reliability import reliability_summary, run_command_verification_harness

from .formatting import Screen, format_user_datetime


def _status_title(status: str) -> str:
    return "🛡 Reliability Center" if status == "healthy" else "🟡 Reliability Center"


def _reliability_menu(*, details: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("reliability"))],
        [
            InlineKeyboardButton(text="🐢 Slow Buttons", callback_data=callback_for("reliability:slow")),
            InlineKeyboardButton(text="⚠️ Active Failures", callback_data=callback_for("callback_failure_review")),
        ],
        [
            InlineKeyboardButton(text="📜 Historical Issues", callback_data=callback_for("reliability:history")),
            InlineKeyboardButton(text="🧰 Job Status", callback_data=callback_for("reliability:jobs")),
        ],
        [InlineKeyboardButton(text="✅ Verify Navigation", callback_data=callback_for("reliability:verify"))],
    ]
    if not details:
        rows.append([InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("reliability:details"))])
    rows.extend(page_controls(back_to="reliability" if details else "owner_advanced"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_reliability_center_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    summary = reliability_summary(session)
    status = str(summary["status"]).replace("_", " ").title()
    avg_ms = int(summary["average_response_ms"])
    avg_seconds = f"{avg_ms / 1000:.1f}s"
    active_jobs = summary["active_jobs"]
    failed_jobs = summary.get("failed_jobs") or []
    job_line = "No long-running jobs are active."
    if active_jobs:
        job = active_jobs[0]
        job_line = f"{job.job_type.replace('_', ' ').title()}: {job.status.replace('_', ' ').title()}"
    elif failed_jobs:
        job = failed_jobs[0]
        job_line = f"Recent {job.job_type.replace('_', ' ').title()}: {job.status.replace('_', ' ').title()}"

    if not details:
        lines = [
            _status_title(str(summary["status"])),
            "",
            "Status:",
            status,
            "",
            "Button Reliability:",
            f"{summary['button_reliability']}%",
            "",
            "Average Response:",
            avg_seconds,
            "",
            "Slowest Area:",
            str(summary["slowest_area"]),
            "",
            "Active Issues:",
            str(summary["active_issue_count"]),
            "",
            "Long-Running Jobs:",
            job_line,
            "",
            "Latest Check:",
            format_user_datetime(user, summary["latest_check"]),
            "",
            "Next Best Move:",
            "Nothing urgent." if summary["status"] == "healthy" else "Open Slow Buttons or Active Failures.",
        ]
        return Screen("\n".join(lines), _reliability_menu())

    slow_lines = [
        f"- {record.callback_route}: {record.latency_label} ({record.total_latency_ms or 0}ms)"
        for record in summary["slow_records"]
    ] or ["- None in the last 24 hours."]
    job_lines = [_job_line(job, user) for job in summary["latest_jobs"]] or ["- No jobs recorded yet."]
    lines = [
        "🔎 Reliability Details",
        "",
        f"Status: {status}",
        f"Reliability: {summary['button_reliability']}%",
        f"Average Response: {avg_seconds}",
        f"Webhook: {summary['webhook_status']}",
        f"Active Issues: {summary['active_issue_count']}",
        f"Historical Failures: {summary['historical_failure_count']}",
        f"Timed Out Jobs: {summary['timed_out_jobs']}",
        "",
        "Slow Routes:",
        *slow_lines,
        "",
        "Recent Jobs:",
        *job_lines,
        "",
        "Historical records stay available for learning, but only active issues count against reliability.",
    ]
    return Screen("\n".join(lines), _reliability_menu(details=True))


def _job_line(job: ReliabilityJob, user: User | None) -> str:
    when = format_user_datetime(user, job.updated_at)
    summary = job.result_summary or job.safe_error_summary or job.current_step
    return f"- {job.job_type}: {job.status} at {when} — {summary}"


def render_reliability_slow_page(session: Session, user: User | None = None) -> Screen:
    summary = reliability_summary(session)
    records: list[CallbackLatencyRecord] = list(summary["slow_records"])
    lines = ["🐢 Slow Buttons", ""]
    if not records:
        lines.extend(["No slow button routes were recorded in the last 24 hours.", "", "Next Best Move:", "Nothing urgent."])
    else:
        lines.extend(["Fortuna found routes that may feel slow.", ""])
        for record in records:
            lines.append(f"- {record.callback_route}: {record.latency_label} ({record.total_latency_ms or 0}ms)")
        lines.extend(["", "Next Best Move:", "Review the slowest route first."])
    return Screen("\n".join(lines), _reliability_menu(details=True))


def render_reliability_jobs_page(session: Session, user: User | None = None) -> Screen:
    summary = reliability_summary(session)
    jobs: list[ReliabilityJob] = list(summary["latest_jobs"])
    lines = ["🧰 Job Status", ""]
    if not jobs:
        lines.extend(["No long-running jobs are recorded yet.", "", "Next Best Move:", "Nothing urgent."])
    else:
        for job in jobs:
            lines.append(_job_line(job, user))
        lines.extend(["", "Next Best Move:", "Timed-out or failed jobs should be reviewed."])
    return Screen("\n".join(lines), _reliability_menu(details=True))


def render_reliability_history_page(session: Session, user: User | None = None) -> Screen:
    summary = reliability_summary(session)
    lines = [
        "📜 Historical Issues",
        "",
        f"Historical callback failures: {summary['historical_failure_count']}",
        "",
        "Historical issues are kept for audit and learning.",
        "They do not count as active reliability problems after fresh checks pass.",
        "",
        "Next Best Move:",
        "Use Active Failures for current problems.",
    ]
    return Screen("\n".join(lines), _reliability_menu(details=True))


def render_reliability_verify_page(session: Session, user: User | None = None) -> Screen:
    if user is None:
        return Screen("✅ Navigation Verification\n\nOwner context is unavailable.", _reliability_menu(details=True))
    try:
        result = run_command_verification_harness(session, actor=user)
    except Exception as exc:
        lines = [
            "âœ… Navigation Verification",
            "",
            "Passed Routes: unavailable",
            "Failed Routes: unavailable",
            "Slow Routes: unavailable",
            "Callback Issue Count: unavailable",
            "Stale Menu Issues: unavailable",
            "",
            "Failures:",
            f"- Verification harness could not finish safely ({type(exc).__name__}).",
            "",
            "Next Best Move:",
            "Open /reliability and retry after the current issue is fixed.",
        ]
        return Screen("\n".join(lines), _reliability_menu(details=True))
    failed = [f"- /{item.command}: {item.safe_error_summary or 'failed'}" for item in result.failed]
    slow = [f"- /{item.command}: {item.latency_ms}ms" for item in result.slow]
    lines = [
        "✅ Navigation Verification",
        "",
        f"Passed Routes: {len(result.passed)}",
        f"Failed Routes: {len(result.failed)}",
        f"Slow Routes: {len(result.slow)}",
        f"Callback Issue Count: {result.callback_issue_count}",
        f"Stale Menu Issues: {result.stale_menu_issue_count}",
        "",
        "Failures:",
        *(failed or ["- None"]),
        "",
        "Slow:",
        *(slow or ["- None"]),
        "",
        "This verifies command-rendered screens without relying on Telegram Desktop inline button labels.",
    ]
    return Screen("\n".join(lines), _reliability_menu(details=True))
