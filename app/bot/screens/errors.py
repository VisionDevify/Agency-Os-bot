from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen
from app.models.user import User
from app.services.callbacks import latest_callback_error, run_callback_health_smoke_test
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
            "Fortuna saved this button issue for review. You can safely return Home or retry later."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Home", callback_data=callback_for("menu"))],
                [InlineKeyboardButton(text="Button Health Report", callback_data=callback_for("button_health"))],
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


def render_button_health_report_page(session: Session, user: User | None = None, *, run_now: bool = False) -> Screen:
    if user is None:
        return Screen(text="Button Health Report\n\nOwner access required.", reply_markup=page_controls_markup("settings"))
    report = run_callback_health_smoke_test(session, actor=user)
    lines = [
        "Button Health Report",
        "",
        "Automatic callback smoke test for non-destructive screen renderers.",
        "",
        f"Health Score: {report.score}%",
        f"Working: {len(report.working)}",
        f"Failing: {len(report.failing)}",
        f"Untested: {len(report.untested)}",
    ]
    if report.failing:
        lines.extend(["", "Failing Buttons:"])
        for failure in report.failing[:8]:
            lines.append(f"- {failure.page}: {failure.exception_type}")
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
                [InlineKeyboardButton(text="Last Error", callback_data=callback_for("debug_last_error"))],
                *page_controls(back_to="settings"),
            ]
        ),
    )


def page_controls_markup(back_to: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=page_controls(back_to=back_to))
