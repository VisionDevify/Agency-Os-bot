from datetime import UTC, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen
from app.models.user import User
from app.services.button_health import button_health_summary, run_button_issue_scan
from app.services.callbacks import callback_failure_review, latest_callback_error, run_callback_health_smoke_test
from app.services.team_operations import format_user_datetime


def render_callback_error_page(page: str, *, error_id: int | None = None) -> Screen:
    report_page = f"callback_error:report:{error_id}" if error_id else "callback_error:report"
    return Screen(
        text=(
            "Fortuna encountered a problem loading this screen.\n\n"
            "The issue was logged so it can be fixed. The bot is still running."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Home", callback_data=callback_for("menu")),
                    InlineKeyboardButton(text="Retry", callback_data=callback_for(page or "menu")),
                ],
                [InlineKeyboardButton(text="Report Problem", callback_data=callback_for(report_page))],
            ]
        ),
    )


def render_callback_problem_reported_page() -> Screen:
    return Screen(
        text=(
            "Problem Reported\n\n"
            "Fortuna saved this button issue for review. You can safely return Home or retry later.\n\n"
            "Optional: reply with a short note about what you expected to happen."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Home", callback_data=callback_for("menu"))],
                [InlineKeyboardButton(text="Button Health Report", callback_data=callback_for("button_health"))],
                [InlineKeyboardButton(text="Callback Failure Review", callback_data=callback_for("callback_failure_review"))],
            ]
        ),
    )


def render_report_problem_page(*, started: bool = False) -> Screen:
    if started:
        text = "\n".join(
            [
                "Report a Problem",
                "",
                "Send one message in this format:",
                "Screen | what happened | severity | notes",
                "",
                "Severity can be low, medium, high, or critical.",
                "",
                "Example:",
                "Proxy Vault | Add Proxy button did nothing | high | happened on mobile",
            ]
        )
    else:
        text = "\n".join(
            [
                "Report a Problem",
                "",
                "Use this during mobile QA when something feels broken or confusing.",
                "",
                "Fortuna will save the report as a FrictionItem with audit and event records.",
            ]
        )
    return Screen(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Start Report", callback_data=callback_for("settings:report_problem:start"))],
                [InlineKeyboardButton(text="Button Health Report", callback_data=callback_for("button_health"))],
                *page_controls(back_to="settings"),
            ]
        ),
    )


def render_problem_report_saved_page() -> Screen:
    return Screen(
        text="Problem Report Saved\n\nFortuna logged this for review. Thank you.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Report Another Problem", callback_data=callback_for("settings:report_problem:start"))],
                [InlineKeyboardButton(text="Button Health Report", callback_data=callback_for("button_health"))],
                *page_controls(back_to="settings"),
            ]
        ),
    )


def render_debug_last_error_page(session: Session, user: User | None = None) -> Screen:
    error = latest_callback_error(session)
    if error is None:
        text = "Last Button Error\n\nNo callback errors have been logged yet."
    else:
        when = format_user_datetime(user, error.created_at) if error.created_at else "Unknown"
        text = "\n".join(
            [
                "Last Button Error",
                "",
                f"Callback: {error.callback_data or 'Unknown'}",
                f"Screen: {error.affected_screen or error.page or 'Unknown'}",
                f"Exception: {error.exception_type}",
                f"Time: {when}",
                "",
                "No secrets, tokens, proxy passwords, or raw environment values are shown here.",
            ]
        )
    return Screen(text=text, reply_markup=page_controls_markup("settings"))


def render_button_health_report_page(
    session: Session,
    user: User | None = None,
    *,
    run_now: bool = False,
    details: bool = False,
) -> Screen:
    if user is None:
        return Screen(text="Button Health Report\n\nOwner access required.", reply_markup=page_controls_markup("settings"))
    health = run_button_issue_scan(session, actor=user) if run_now or not details else button_health_summary(session)
    review = callback_failure_review(session, limit=3)
    if not details:
        title = "🟢 Button Health" if health.open_issue_count == 0 else "🟡 Button Health"
        technical = "✅ No crashes found." if health.technical_issue_count == 0 else f"⚠ {health.technical_issue_count} technical issue(s)."
        navigation = "✅ Navigation looks clear." if health.navigation_issue_count == 0 else f"⚠ {health.navigation_issue_count} path(s) need review."
        ux = "✅ Button labels look clear." if health.ux_issue_count == 0 else f"⚠ {health.ux_issue_count} confusing button(s) found."
        recommended_action = "No action needed." if health.open_issue_count == 0 else "Review button issues."
        last_check = format_user_datetime(user, datetime.now(UTC))
        return Screen(
            text="\n".join(
                [
                    title,
                    "",
                    "Technical:",
                    technical,
                    "",
                    "Navigation:",
                    navigation,
                    "",
                    "UX:",
                    ux,
                    "",
                    f"Issues Found: {health.open_issue_count}",
                    f"Last Check: {last_check}",
                    "",
                    "Recommended Action:",
                    recommended_action,
                ]
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Run Again", callback_data=callback_for("button_health:run"))],
                    [InlineKeyboardButton(text="View Issues", callback_data=callback_for("button_health:details"))],
                    [InlineKeyboardButton(text="Technical Details", callback_data=callback_for("button_health:details"))],
                    *page_controls(back_to="settings"),
                ]
            ),
        )
    report = run_callback_health_smoke_test(session, actor=user)
    health = button_health_summary(session)
    lines = [
        "Fortuna Self-Test Technical Details",
        "",
        "Automatic callback smoke test for non-destructive screen renderers.",
        "",
        f"Overall Button Status: {health.overall_label}",
        f"Open Button Issues: {health.open_issue_count}",
        f"Technical Issues: {health.technical_issue_count}",
        f"Navigation Issues: {health.navigation_issue_count}",
        f"UX Issues: {health.ux_issue_count}",
        "",
        f"Health Score: {report.score}%",
        f"Working: {len(report.working)}",
        f"Failing: {len(report.failing)}",
        f"Untested: {len(report.untested)}",
    ]
    if health.issues:
        lines.extend(["", "Open Button Issues:"])
        for issue in health.issues[:8]:
            lines.append(f"- {issue.screen}: {issue.issue_type} ({issue.severity})")
            lines.append(f"  Evidence: {issue.evidence_summary}")
    lines.extend(
        [
            "",
            "Recent Production Failure Logs:",
            f"Callback errors: {len(review.items)}",
            f"Friction items: {review.friction_count}",
            f"Callback recommendations: {review.recommendation_count}",
            f"Callback audit rows: {review.audit_count}",
            f"Callback event rows: {review.event_count}",
        ]
    )
    if report.failing:
        lines.extend(["", "Failing Buttons:"])
        for failure in report.failing[:8]:
            lines.append(f"- {failure.page}: {failure.exception_type}")
    if review.items:
        lines.extend(["", "Latest Logged Failures:"])
        for item in review.items[:3]:
            when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
            lines.append(f"- {item.page}: {item.exception_type} at {when}")
    if report.untested:
        lines.extend(["", "Skipped For Safety:"])
        for page in report.untested[:8]:
            lines.append(f"- {page}")
    if not report.failing:
        lines.extend(["", "Fortuna did not find renderer crashes in the safe smoke set."])
    return Screen(
        text="\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Run Again", callback_data=callback_for("button_health:run"))],
                [InlineKeyboardButton(text="Executive Summary", callback_data=callback_for("button_health"))],
                [InlineKeyboardButton(text="Callback Failure Review", callback_data=callback_for("callback_failure_review"))],
                [InlineKeyboardButton(text="Last Error", callback_data=callback_for("debug_last_error"))],
                *page_controls(back_to="settings"),
            ]
        ),
    )


def render_callback_failure_review_page(session: Session, user: User | None = None) -> Screen:
    review = callback_failure_review(session, limit=10)
    lines = [
        "Callback Failure Review",
        "",
        "Fortuna checked callback errors, friction items, callback recommendations, audit logs, and event logs.",
        "",
        f"Callback errors: {len(review.items)}",
        f"Friction items: {review.friction_count}",
        f"Callback recommendations: {review.recommendation_count}",
        f"Callback audit rows: {review.audit_count}",
        f"Callback event rows: {review.event_count}",
    ]
    if not review.items:
        lines.extend(
            [
                "",
                "No callback failures are currently logged in this database.",
                "Next best move: keep Button Health Report available during mobile QA.",
            ]
        )
    else:
        lines.extend(["", "Logged Failures:"])
        for item in review.items:
            when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
            lines.extend(
                [
                    f"- {item.page}",
                    f"  Exception: {item.exception_type}",
                    f"  Time: {when}",
                    f"  Root cause: {item.root_cause}",
                    f"  Fix: {item.recommended_fix}",
                ]
            )
    return Screen(
        text="\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Run Button Health", callback_data=callback_for("button_health:run"))],
                [InlineKeyboardButton(text="Last Error", callback_data=callback_for("debug_last_error"))],
                *page_controls(back_to="settings"),
            ]
        ),
    )


def page_controls_markup(back_to: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=page_controls(back_to=back_to))
