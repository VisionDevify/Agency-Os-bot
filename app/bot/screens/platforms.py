from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen
from app.models.platform import PLATFORM_IDENTIFIERS
from app.models.user import User
from app.services.platform_connections import (
    PLATFORM_DEFINITIONS,
    PlatformIntegrationStatus,
    platform_connection_status,
    platform_connections_overview,
    platform_connections_status,
    test_platform_website,
)


def _platform_button_label(status: PlatformIntegrationStatus) -> str:
    return f"{status.emoji} {status.display_name}"


def _status_line(label: str, status: str, evidence: str) -> str:
    return f"{label}: {status}\nEvidence: {evidence}"


def _unknown_platform_screen() -> Screen:
    return Screen(
        "\n".join(
            [
                "🔌 Platform Connections",
                "",
                "Status:",
                "That platform is not available yet.",
                "",
                "✨ Next Best Move",
                "Open Platform Connections and choose one of the supported platforms.",
            ]
        ),
        InlineKeyboardMarkup(inline_keyboard=page_controls(back_to="platforms")),
    )


def _platform_connections_menu(statuses: list[PlatformIntegrationStatus]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=_platform_button_label(item), callback_data=callback_for(f"platforms:{item.platform}"))] for item in statuses]
    rows.extend(
        [
            [InlineKeyboardButton(text="🔔 Notification Center", callback_data=callback_for("platforms:notifications"))],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("platforms:details"))],
            [InlineKeyboardButton(text="❓ Help", callback_data=callback_for("help_copilot:platform_connections"))],
            *page_controls(back_to="owner_advanced"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _platform_detail_menu(platform: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Test Website", callback_data=callback_for(f"platforms:{platform}:test_website"))],
            [InlineKeyboardButton(text="🔐 Connection Setup", callback_data=callback_for(f"platforms:{platform}:connection"))],
            [InlineKeyboardButton(text="📊 Stats Check", callback_data=callback_for(f"platforms:{platform}:stats"))],
            [InlineKeyboardButton(text="🔔 Notifications", callback_data=callback_for(f"platforms:notifications:{platform}"))],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for(f"platforms:{platform}:details"))],
            [InlineKeyboardButton(text="❓ Help", callback_data=callback_for("help_copilot:platform_connections"))],
            *page_controls(back_to="platforms"),
        ]
    )


def _notification_center_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📸 Instagram Alerts", callback_data=callback_for("platforms:notifications:instagram"))],
        [InlineKeyboardButton(text="𝕏 X Alerts", callback_data=callback_for("platforms:notifications:x"))],
        [InlineKeyboardButton(text="🔥 OnlyFans Alerts", callback_data=callback_for("platforms:notifications:onlyfans"))],
        [InlineKeyboardButton(text="📢 Telegram Alerts", callback_data=callback_for("platforms:notifications:telegram"))],
        [InlineKeyboardButton(text="📧 Email Alerts", callback_data=callback_for("platforms:notifications:email"))],
        [InlineKeyboardButton(text="🚨 System Alerts", callback_data=callback_for("platforms:notifications:system_alerts"))],
        [InlineKeyboardButton(text="🧠 Intelligence Alerts", callback_data=callback_for("notification_routing"))],
        *page_controls(back_to="platforms"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_platform_connections_page(
    session: Session,
    user: User | None = None,
    *,
    details: bool = False,
) -> Screen:
    overview = platform_connections_overview(session)
    statuses = list(overview["statuses"])
    if details:
        lines = [
            "🔎 Platform Connection Details",
            "",
            "Technical values are still sanitized. No credentials are shown here.",
            "",
        ]
        for item in statuses:
            lines.extend(
                [
                    f"{item.emoji} {item.display_name}",
                    f"- Website: {item.website.status}",
                    f"- Login: {item.connection.status}",
                    f"- Stats: {item.stats.status}",
                    f"- Notifications: {item.notifications.status}",
                    f"- Readiness: {item.readiness.status}",
                    f"- Methods: {', '.join(method.replace('_', ' ') for method in item.supported_connection_methods)}",
                    f"- Evidence: {item.evidence_summary}",
                    "",
                ]
            )
        return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Executive Summary", callback_data=callback_for("platforms"))], *page_controls(back_to="platforms")]))

    lines = [
        "🔌 Platform Connections",
        "",
        "Status:",
        f"{overview['ready']}/{overview['total']} ready for activation.",
        "",
        "What Fortuna checked:",
        "• Website reachability is separate from login access.",
        "• Stats wait for a verified owner-approved connection.",
        "• Missing credentials are setup items, not failures.",
        "",
        "Platforms:",
    ]
    for item in statuses:
        lines.append(f"• {item.emoji} {item.display_name}: {item.connection.label} / Stats {item.stats.label}")
    lines.extend(["", "✨ Next Best Move", str(overview["next_action"])])
    return Screen("\n".join(lines), _platform_connections_menu(statuses))


def render_platform_detail_page(
    session: Session,
    platform: str,
    user: User | None = None,
    *,
    details: bool = False,
    run_website_check: bool = False,
    section: str | None = None,
) -> Screen:
    if platform not in PLATFORM_DEFINITIONS:
        return _unknown_platform_screen()
    if run_website_check:
        test_platform_website(session, platform)
    status = platform_connection_status(session, platform)
    if details:
        lines = [
            f"🔎 {status.display_name} Details",
            "",
            "Compliance:",
            "Fortuna may observe, summarize, and recommend. Humans execute.",
            "No auto-posting, auto-commenting, auto-liking, auto-following, scraping, or evasion.",
            "",
            f"Supported Methods: {', '.join(method.replace('_', ' ') for method in status.supported_connection_methods)}",
            f"Website Status: {status.website.status}",
            f"Login Status: {status.connection.status}",
            f"Stats Status: {status.stats.status}",
            f"Notification Status: {status.notifications.status}",
            f"Readiness Status: {status.readiness.status}",
            "",
            "Evidence:",
            status.evidence_summary,
            "",
            "Credentials:",
            "Secure credential flow not active yet. Do not paste credentials into normal chat.",
        ]
        return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Executive Summary", callback_data=callback_for(f"platforms:{platform}"))], *page_controls(back_to="platforms")]))

    if section == "connection":
        title = f"🔐 {status.display_name} Connection Setup"
        body = [
            title,
            "",
            "Status:",
            status.connection.label,
            "",
            "What this means:",
            "Connected means you approved a login/API/session method and Fortuna verified it.",
            "Secure credential flow not active yet.",
            "",
            "✨ Next Best Move",
            status.connection.next_action or "Wait for secure credential setup.",
        ]
        return Screen("\n".join(body), _platform_detail_menu(platform))
    if section == "stats":
        body = [
            f"📊 {status.display_name} Stats",
            "",
            "Status:",
            status.stats.label,
            "",
            "Why:",
            status.stats.evidence,
            "",
            "✨ Next Best Move",
            status.stats.next_action or "Complete connection setup first.",
        ]
        return Screen("\n".join(body), _platform_detail_menu(platform))

    lines = [
        f"{status.emoji} {status.display_name}",
        "",
        "Status:",
        status.readiness.label,
        "",
        _status_line("🌐 Website", status.website.label, status.website.evidence),
        "",
        _status_line("🔐 Login", status.connection.label, status.connection.evidence),
        "",
        _status_line("📊 Stats", status.stats.label, status.stats.evidence),
        "",
        _status_line("🔔 Notifications", status.notifications.label, status.notifications.evidence),
        "",
        _status_line("🧩 Readiness", status.readiness.label, status.readiness.evidence),
        "",
        "✨ Next Best Move",
        status.next_action,
    ]
    return Screen("\n".join(lines), _platform_detail_menu(platform))


def render_platform_notification_center_page(session: Session, user: User | None = None) -> Screen:
    statuses = platform_connections_status(session)
    lines = [
        "🔔 Notification Center",
        "",
        "Status:",
        "Notification routes are checked per platform.",
        "",
        "What Fortuna checked:",
    ]
    for item in statuses:
        lines.append(f"• {item.emoji} {item.display_name}: {item.notifications.label}")
    lines.extend(
        [
            "",
            "✨ Next Best Move",
            "Register Fortuna Alerts/HQ targets before sending real platform alerts.",
        ]
    )
    return Screen("\n".join(lines), _notification_center_menu())


def render_platform_notification_detail_page(session: Session, platform: str, user: User | None = None) -> Screen:
    if platform not in PLATFORM_DEFINITIONS:
        return _unknown_platform_screen()
    status = platform_connection_status(session, platform)
    lines = [
        f"🔔 {status.display_name} Alerts",
        "",
        "What happened:",
        status.notifications.label,
        "",
        "Why it matters:",
        status.notifications.evidence,
        "",
        "What to do next:",
        status.notifications.next_action or "Open Notification Routing.",
    ]
    return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Notification Routing", callback_data=callback_for("notification_routing"))], *page_controls(back_to="platforms:notifications")]))
