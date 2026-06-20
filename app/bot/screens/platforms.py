from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot.menu import callback_for, page_controls
from app.bot.screens.formatting import Screen
from app.models.user import User
from app.services.notification_intelligence import (
    alert_health_summary,
    alert_route_summaries,
    coo_briefing_foundation,
    evaluate_notification_signal,
    friction_detector_summary,
    notification_learning_summary,
    platform_notification_signal,
    refresh_all_platform_statuses,
    refresh_platform_status,
    record_notification_outcome,
)
from app.services.platform_connections import (
    PLATFORM_DEFINITIONS,
    PlatformIntegrationStatus,
    platform_connections_overview,
    platform_connections_status,
    test_platform_website,
)


def _platform_button_label(status: PlatformIntegrationStatus) -> str:
    return f"{status.emoji} {status.display_name}"


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
    rows = [
        [InlineKeyboardButton(text=_platform_button_label(item), callback_data=callback_for(f"platforms:{item.platform}"))]
        for item in statuses
    ]
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
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Instagram", callback_data=callback_for("platforms:notifications:instagram"))],
            [InlineKeyboardButton(text="𝕏 X", callback_data=callback_for("platforms:notifications:x"))],
            [InlineKeyboardButton(text="🔥 OnlyFans", callback_data=callback_for("platforms:notifications:onlyfans"))],
            [InlineKeyboardButton(text="📢 Telegram", callback_data=callback_for("platforms:notifications:telegram"))],
            [InlineKeyboardButton(text="📧 Email", callback_data=callback_for("platforms:notifications:email"))],
            [InlineKeyboardButton(text="🚨 System", callback_data=callback_for("platforms:notifications:system_alerts"))],
            [InlineKeyboardButton(text="🧠 Intelligence", callback_data=callback_for("platforms:notifications:intelligence"))],
            [InlineKeyboardButton(text="🚦 Alert Routing", callback_data=callback_for("platforms:alert_routing"))],
            [InlineKeyboardButton(text="🔔 Alert Health", callback_data=callback_for("platforms:alert_health"))],
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("platforms:notifications"))],
            *page_controls(back_to="platforms"),
        ]
    )


def render_platform_connections_page(
    session: Session,
    user: User | None = None,
    *,
    details: bool = False,
) -> Screen:
    if not details:
        refresh_all_platform_statuses(session)
    overview = platform_connections_overview(session)
    statuses = list(overview["statuses"])
    if details:
        lines = [
            "🔎 Platform Connection Details",
            "",
            "Technical values are sanitized. No credentials are shown here.",
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
        return Screen(
            "\n".join(lines),
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📋 Executive Summary", callback_data=callback_for("platforms"))], *page_controls(back_to="platforms")]
            ),
        )

    lines = [
        "🔌 Platform Connections",
        "",
        "Status:",
        f"{overview['ready']}/{overview['total']} ready for activation.",
        "",
        "What Fortuna noticed:",
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
    status = refresh_platform_status(session, platform)
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
        return Screen(
            "\n".join(lines),
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📋 Executive Summary", callback_data=callback_for(f"platforms:{platform}"))], *page_controls(back_to="platforms")]
            ),
        )

    if section == "connection":
        body = [
            f"🔐 {status.display_name} Connection Setup",
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
        "What Fortuna noticed:",
        f"• Website: {status.website.label}",
        f"• Login: {status.connection.label}",
        f"• Stats: {status.stats.label}",
        f"• Notifications: {status.notifications.label}",
        f"• Readiness: {status.readiness.label}",
        "",
        "✨ Next Best Move",
        status.next_action,
    ]
    return Screen("\n".join(lines), _platform_detail_menu(platform))


def render_platform_notification_center_page(session: Session, user: User | None = None) -> Screen:
    statuses = refresh_all_platform_statuses(session)
    health = alert_health_summary(session)
    learning = notification_learning_summary(session)
    friction = friction_detector_summary(session)
    unconfigured = [item for item in statuses if item.notifications.status == "not_configured"]
    lines = [
        "📱 Notification Center",
        "",
        "Status:",
        health.label if health.total_attempts or health.stale_route_count else "Ready for setup",
        "",
        "✨ What Fortuna noticed",
    ]
    if unconfigured:
        lines.append(f"• {len(unconfigured)} platform alert route(s) still need setup.")
    else:
        lines.append("• Platform alert routes are configured.")
    lines.append(f"• Alert health: {health.label}.")
    if learning["total"]:
        lines.append(f"• Fortuna has {learning['total']} notification learning event(s).")
    lines.append("• Notification UX needs review." if friction.status != "healthy" else "• No notification UX friction is trending.")
    lines.extend(
        [
            "",
            "🎯 Next Best Move",
            health.next_action if health.status != "healthy" else "Choose a platform alert route to configure next.",
        ]
    )
    return Screen("\n".join(lines), _notification_center_menu())


def render_platform_notification_detail_page(
    session: Session,
    platform: str,
    user: User | None = None,
    *,
    action: str | None = None,
) -> Screen:
    if platform == "intelligence":
        lines = [
            "🧠 Intelligence Alerts",
            "",
            "Status:",
            "Ready for setup",
            "",
            "Fortuna can notify about:",
            "• important opportunities",
            "• repeated failures",
            "• production risks",
            "",
            "🎯 Next Best Move",
            "Register Fortuna HQ before enabling intelligence alerts.",
        ]
        return Screen(
            "\n".join(lines),
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚦 Alert Routing", callback_data=callback_for("platforms:alert_routing"))], *page_controls(back_to="platforms:notifications")]),
        )
    if platform not in PLATFORM_DEFINITIONS:
        return _unknown_platform_screen()
    status = refresh_platform_status(session, platform)
    signal = platform_notification_signal(status)
    decision = evaluate_notification_signal(signal)
    if action == "learn_ignored":
        record_notification_outcome(session, alert_key=signal.signal_type, outcome="ignored", actor=user)
    elif action == "learn_acted":
        record_notification_outcome(session, alert_key=signal.signal_type, outcome="success", actor=user)
    test_line = "Fortuna simulated the alert route. No live alert was sent." if action == "test" else None
    can_notify_about = {
        "instagram": ("opportunity discoveries", "creator changes", "connection failures", "stale stats"),
        "x": ("opportunity discoveries", "creator changes", "connection failures", "stale stats"),
        "onlyfans": ("opportunity discoveries", "creator/model changes", "connection failures", "stale stats"),
        "telegram": ("production status", "delivery failures", "registered group health"),
        "email": ("future email summaries", "delivery failures", "owner reports"),
        "system_alerts": ("polling conflicts", "backup verification failures", "restore failures", "broken notification routes"),
        "backup_storage": ("backup warnings", "restore validation issues", "storage target failures"),
    }.get(platform, ("important changes", "delivery failures"))
    if action == "details":
        lines = [
            f"🔎 {status.display_name} Alert Details",
            "",
            "Safe technical details. No credentials are shown here.",
            "",
            f"Notification Status: {status.notifications.status}",
            f"Route: {decision.route or 'not routed'}",
            f"Priority: {signal.priority}",
            f"Show in Today: {'yes' if decision.show_in_today else 'no'}",
            f"Alert Owner: {'yes' if decision.alert_owner else 'no'}",
            f"Escalate: {'yes' if decision.escalate else 'no'}",
            "",
            "Evidence:",
            f"- {status.notifications.evidence}",
            f"- {signal.evidence}",
            "",
            "What this means:",
            decision.reason,
            "",
            "Next Action:",
            signal.recommended_action,
        ]
        return Screen(
            "\n".join(lines),
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Summary", callback_data=callback_for(f"platforms:notifications:{platform}"))],
                    *page_controls(back_to="platforms:notifications"),
                ]
            ),
        )
    lines = [
        f"{status.emoji} {status.display_name} Alerts",
        "",
        "Status:",
        status.notifications.label,
        "",
        "Fortuna can notify about:",
        *(f"• {item}" for item in can_notify_about),
        "",
        "What Fortuna noticed:",
        f"• Priority: {signal.priority.title()}",
        f"• {decision.reason}",
        *( [f"• {test_line}"] if test_line else [] ),
        "",
        "🎯 Next Best Move",
        status.notifications.next_action or "Open Notification Routing.",
    ]
    buttons = [
        [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for(f"platforms:notifications:{platform}"))],
        [InlineKeyboardButton(text="🚨 Test Alert", callback_data=callback_for(f"platforms:notifications:{platform}:test"))],
        [InlineKeyboardButton(text="⚙️ Configure", callback_data=callback_for("notification_routing"))],
        [InlineKeyboardButton(text="✅ Mark Acted On", callback_data=callback_for(f"platforms:notifications:{platform}:learn_acted"))],
        [InlineKeyboardButton(text="❌ Mark Ignored", callback_data=callback_for(f"platforms:notifications:{platform}:learn_ignored"))],
        [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for(f"platforms:notifications:{platform}:details"))],
        *page_controls(back_to="platforms:notifications"),
    ]
    return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons))


def render_alert_routing_center_page(session: Session, user: User | None = None) -> Screen:
    routes = alert_route_summaries(session)
    lines = [
        "🚦 Alert Routing Center",
        "",
        "Status:",
        "Fortuna checked where alerts should go.",
        "",
        "Routes:",
    ]
    for route in routes:
        lines.append(f"• {route.source_label} → {route.route_label}")
    lines.extend(["", "🎯 Next Best Move", "Register missing HQ/Ops/Alerts targets before real alert delivery."])
    return Screen(
        "\n".join(lines),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔔 Alert Health", callback_data=callback_for("platforms:alert_health"))],
                [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("platforms:alert_routing"))],
                *page_controls(back_to="platforms:notifications"),
            ]
        ),
    )


def render_alert_health_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    health = alert_health_summary(session)
    friction = friction_detector_summary(session)
    coo = coo_briefing_foundation(session)
    if details:
        lines = [
            "🔎 Alert Health Details",
            "",
            f"Status: {health.status}",
            f"Success Rate: {health.success_rate if health.success_rate is not None else 'Not enough data'}",
            f"Attempts: {health.total_attempts}",
            f"Failed: {health.failed_attempts}",
            f"Stale Routes: {health.stale_route_count}",
            f"Disabled Routes: {health.disabled_route_count}",
            f"Friction: {friction.status}",
            "",
            "COO Briefing Foundation:",
            f"System: {coo.system_health_summary}",
            *(f"• {item}" for item in coo.top_blockers),
        ]
        return Screen(
            "\n".join(lines),
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Summary", callback_data=callback_for("platforms:alert_health"))], *page_controls(back_to="platforms:notifications")]),
        )
    lines = [
        "🔔 Alert Health",
        "",
        "Status:",
        health.label,
        "",
        "What Fortuna noticed:",
        f"• {health.evidence}",
        f"• Friction: {friction.evidence}",
        "",
        "🎯 Next Best Move",
        health.next_action,
    ]
    return Screen(
        "\n".join(lines),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("platforms:alert_health"))],
                [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("platforms:alert_health:details"))],
                *page_controls(back_to="platforms:notifications"),
            ]
        ),
    )
