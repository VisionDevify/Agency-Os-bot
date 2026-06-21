from datetime import UTC, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen
from app.models.user import User
from app.services.button_health import button_health_summary, run_button_issue_scan
from app.services.callbacks import callback_failure_review, latest_callback_error, run_callback_health_smoke_test
from app.services.team_ux import team_ux_readiness
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
    team_ux = team_ux_readiness(session)
    if not details:
        total_issues = health.open_issue_count + health.telegram_ui_issue_count
        title = "🟢 Button Health" if health.overall_status == "healthy" else "🟡 Button Health"
        technical = "✅ No crashes found." if health.technical_issue_count == 0 else f"⚠ {health.technical_issue_count} technical issue(s)."
        if health.telegram_ui_status != "healthy":
            navigation = "⚠ Old menu cleanup needs review."
        elif health.navigation_issue_count == 0:
            navigation = "✅ Navigation looks clear."
        else:
            navigation = f"⚠ {health.navigation_issue_count} path(s) need review."
        ux = "✅ Button labels look clear." if health.ux_issue_count == 0 else f"⚠ {health.ux_issue_count} confusing button(s) found."
        recommended_action = (
            "Run Chat Cleanup."
            if health.telegram_ui_status != "healthy"
            else "No action needed."
            if total_issues == 0
            else "Review button issues."
        )
        if team_ux.meaningful and health.telegram_ui_status == "healthy":
            recommended_action = team_ux.next_action
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
                    "Team UX:",
                    f"{team_ux.label} - {team_ux.evidence}",
                    "",
                    f"Issues Found: {total_issues}",
                    f"Last Check: {last_check}",
                    "",
                    "Recommended Action:",
                    recommended_action,
                ]
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🧹 Clean Menus", callback_data=callback_for("settings:chat_cleanup:clean"))],
                    [InlineKeyboardButton(text="🔄 Run Check", callback_data=callback_for("button_health:run"))],
                    [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("button_health:details"))],
                    *page_controls(back_to="settings"),
                ]
            ),
        )
    report = run_callback_health_smoke_test(session, actor=user)
    revalidated_at = datetime.now(UTC)
    review = callback_failure_review(
        session,
        limit=10,
        working_pages=report.working,
        failing_pages=[failure.page for failure in report.failing],
        revalidated_at=revalidated_at,
    )
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
        "Telegram UI Cleanup:",
        f"Status: {health.telegram_ui_status}",
        f"Evidence: {health.telegram_ui_evidence}",
        f"Next: {health.telegram_ui_next_action}",
        "",
        "Team UX:",
        f"Status: {team_ux.label}",
        f"Score: {team_ux.score}/100",
        f"Navigation Clarity: {team_ux.navigation_clarity}",
        f"Screen Clarity: {team_ux.screen_clarity}",
        f"Stale Menu Safety: {team_ux.stale_menu_safety}",
        f"Callback Reliability: {team_ux.callback_reliability}",
        f"Onboarding Friendliness: {team_ux.onboarding_friendliness}",
        f"Next Action Clarity: {team_ux.next_action_clarity}",
        f"Evidence: {team_ux.evidence}",
        f"Next: {team_ux.next_action}",
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
            f"Callback errors: {len(review.active_items) + len(review.validating_items) + len(review.historical_items)} total",
            f"Active callback errors: {len(review.active_items)}",
            f"Validating callback errors: {len(review.validating_items)}",
            f"Historical fixed callback errors: {len(review.historical_items)}",
            f"Friction items: {review.friction_count}",
            f"Callback recommendations: {review.recommendation_count} total",
            f"Active callback recommendations: {review.active_recommendation_count}",
            f"Resolved callback recommendations: {review.resolved_recommendation_count}",
            f"Callback audit rows: {review.audit_count}",
            f"Callback event rows: {review.event_count}",
        ]
    )
    if report.failing:
        lines.extend(["", "Failing Buttons:"])
        for failure in report.failing[:8]:
            lines.append(f"- {failure.page}: {failure.exception_type}")
    if review.active_items:
        lines.extend(["", "Active Logged Failures:"])
        for item in review.active_items[:3]:
            when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
            lines.append(f"- {item.page}: {item.exception_type} at {when}")
    elif review.validating_items:
        lines.extend(["", "Validating Logged Failures:"])
        for item in review.validating_items[:3]:
            when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
            lines.append(f"- {item.page}: {item.exception_type} at {when}")
            lines.append(f"  Evidence: {item.evidence_summary}")
    elif review.historical_items:
        lines.extend(["", "Historical Fixed Issues:"])
        for item in review.historical_items[:3]:
            when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
            lines.append(f"- {item.page}: {item.exception_type} at {when}")
            lines.append(f"  Evidence: {item.evidence_summary}")
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
    review = callback_failure_review(session, limit=20)
    lines = [
        "Callback Failure Review",
        "",
        "Fortuna checked callback errors, friction items, callback recommendations, audit logs, and event logs.",
        "",
        f"Callback errors: {len(review.active_items)} active",
        "",
        "Active Failures:",
        f"{len(review.active_items)} active / {len(review.new_since_deploy_items)} new since latest validation",
        "",
        "Validating:",
        f"{len(review.validating_items)} waiting for targeted recheck",
        "",
        "Resolved / Historical:",
        f"{len(review.historical_items)} fixed historical issue(s)",
        "",
        f"Friction items: {review.friction_count}",
        f"Active callback recommendations: {review.active_recommendation_count}",
        f"Resolved callback recommendations: {review.resolved_recommendation_count}",
        f"Callback audit rows: {review.audit_count}",
        f"Callback event rows: {review.event_count}",
    ]
    if not review.active_items and not review.validating_items:
        lines.extend(
            [
                "",
                "No callback failures are currently logged in this database."
                if not review.historical_items
                else "✅ No new callback failures since latest deployment.",
                "Old failures are retained as historical records for audit and learning."
                if review.historical_items
                else "No historical callback failures need review.",
                "Next best move: keep Button Health available during mobile QA.",
            ]
        )
    else:
        if review.active_items:
            lines.extend(["", "Active Failures:"])
        for item in review.active_items:
            when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
            lines.extend(
                [
                    f"- {item.page}",
                    f"  Exception: {item.exception_type}",
                    f"  Time: {when}",
                    f"  Status: {item.lifecycle_status}",
                    f"  Evidence: {item.evidence_summary}",
                    f"  Root cause: {item.root_cause}",
                    f"  Fix: {item.recommended_fix}",
                ]
            )
        if review.validating_items:
            lines.extend(["", "Validating:"])
            for item in review.validating_items[:8]:
                when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
                lines.extend(
                    [
                        f"- {item.page}",
                        f"  Exception: {item.exception_type}",
                        f"  Time: {when}",
                        f"  Evidence: {item.evidence_summary}",
                        f"  Root cause: {item.root_cause}",
                        f"  Fix: {item.recommended_fix}",
                        f"  Next: {item.next_action}",
                    ]
                )
    if review.historical_items:
        lines.extend(["", "Historical Fixed Issues:"])
        for item in review.historical_items[:8]:
            when = format_user_datetime(user, item.created_at) if item.created_at else "Unknown"
            fixed_by = item.fixed_by_commit or "current validated build"
            lines.extend(
                [
                    f"- {item.page}",
                    f"  Exception: {item.exception_type}",
                    f"  First seen: {when}",
                    f"  Status: historical",
                    f"  Fixed by: {fixed_by}",
                    f"  Evidence: {item.evidence_summary}",
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
