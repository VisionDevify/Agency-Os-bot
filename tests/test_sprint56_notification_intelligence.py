from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.bot.screens import (
    render_alert_health_page,
    render_alert_routing_center_page,
    render_platform_notification_center_page,
    render_platform_notification_detail_page,
)
from app.models.button_issue import ButtonIssue
from app.models.friction import FrictionItem
from app.models.learning import LearningEvent
from app.models.platform import PlatformConnection
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.services.auth import setup_owner_if_needed
from app.services.notification_intelligence import (
    NotificationSignal,
    alert_health_summary,
    evaluate_notification_signal,
    friction_detector_summary,
    notification_learning_summary,
    record_notification_decision,
    record_notification_outcome,
    refresh_platform_status,
)
from app.services.notifications import create_delivery_attempt, create_notification_target, mark_delivery_failed, mark_delivery_sent
from app.services.platform_connections import ensure_platform_connections, platform_connection_status
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _buttons(screen) -> list[str]:
    if screen.reply_markup is None:
        return []
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _target(session, *, purpose: str = "alerts") -> NotificationTarget:
    owner = _owner(session)
    return create_notification_target(
        session,
        actor=owner,
        name="Fortuna Alerts",
        target_type="telegram_group",
        purpose=purpose,
        telegram_chat_id="-100123456789",
    )


def test_notification_priority_rules_suppress_low_and_escalate_critical() -> None:
    low = evaluate_notification_signal(
        NotificationSignal(
            signal_type="website_refresh",
            source="platform",
            priority="low",
            title="Website check completed",
            summary="Instagram website responded.",
            evidence="Public website responded.",
            recommended_action="No action needed.",
        )
    )
    medium = evaluate_notification_signal(
        NotificationSignal(
            signal_type="stats_stale",
            source="platform",
            priority="medium",
            title="Stats need review",
            summary="Instagram stats are stale.",
            evidence="Latest stats check is outside the freshness window.",
            recommended_action="Refresh stats.",
        )
    )
    high = evaluate_notification_signal(
        NotificationSignal(
            signal_type="delivery_failure",
            source="route",
            priority="high",
            title="Delivery failures",
            summary="Notification delivery failed repeatedly.",
            evidence="Three failed delivery attempts were recorded.",
            recommended_action="Open Alert Health.",
        )
    )
    critical = evaluate_notification_signal(
        NotificationSignal(
            signal_type="polling_conflict",
            source="bot",
            priority="critical",
            title="Polling conflict",
            summary="Another process is polling Telegram.",
            evidence="Telegram returned a polling conflict.",
            recommended_action="Stop duplicate poller.",
        )
    )

    assert low.suppressed is True
    assert low.show_in_today is False
    assert medium.show_in_today is True
    assert medium.alert_owner is False
    assert high.alert_owner is True
    assert critical.escalate is True


def test_medium_notification_decision_creates_today_recommendation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = evaluate_notification_signal(
            NotificationSignal(
                signal_type="route_missing",
                source="platform",
                priority="medium",
                title="Instagram route missing",
                summary="Instagram alerts do not have a target yet.",
                evidence="No Instagram alert route is configured.",
                recommended_action="Open Notification Center.",
            )
        )
        record_notification_decision(session, decision, actor=owner)

        recommendation = session.scalar(
            select(Recommendation).where(Recommendation.recommendation_type == "notification_signal_route_missing")
        )
        assert recommendation is not None
        assert recommendation.status == "open"
        assert "Notification Center" in recommendation.description


def test_refresh_platform_status_updates_timestamp_and_keeps_stats_waiting() -> None:
    with session_scope() as session:
        ensure_platform_connections(session)
        before = platform_connection_status(session, "instagram")
        refreshed = refresh_platform_status(session, "instagram")
        connection = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == "instagram"))

        assert before.connection.status != "connected"
        assert refreshed.stats.status == "waiting_for_connection"
        assert connection is not None
        assert connection.last_notification_check_at is not None


def test_stale_stats_detected_without_claiming_freshness() -> None:
    with session_scope() as session:
        ensure_platform_connections(session)
        instagram = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == "instagram"))
        assert instagram is not None
        instagram.login_connected = True
        instagram.stats_available = True
        instagram.stats_fresh = False
        instagram.last_stats_check_at = datetime.now(UTC) - timedelta(days=3)
        instagram.evidence_json = {
            "connection": {"summary": "Owner-approved connection verified."},
            "stats": {"summary": "Stats were retrieved before the freshness window."},
        }
        session.flush()

        status = platform_connection_status(session, "instagram")

        assert status.connection.status == "connected"
        assert status.stats.status == "stale"


def test_alert_health_tracks_delivery_failure_and_stale_routes() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target = _target(session)
        stale_target = _target(session, purpose="hq")
        stale_target.name = "Fortuna HQ"
        stale_target.last_tested_at = None
        for _ in range(3):
            attempt = create_delivery_attempt(session, target, event_type="platform.alert", actor=owner)
            mark_delivery_failed(session, attempt, actor=owner, error_message="telegram_send_failed")

        health = alert_health_summary(session)

        assert health.failed_attempts == 3
        assert health.stale_route_count >= 1
        assert health.status in {"needs_attention", "critical"}
        assert "delivery" in health.next_action.lower() or "route" in health.next_action.lower()


def test_alert_health_reports_success_rate_when_deliveries_succeed() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target = _target(session)
        target.last_tested_at = datetime.now(UTC)
        sent = create_delivery_attempt(session, target, event_type="platform.alert", actor=owner)
        mark_delivery_sent(session, sent, actor=owner)
        failed = create_delivery_attempt(session, target, event_type="platform.alert", actor=owner)
        mark_delivery_failed(session, failed, actor=owner, error_message="temporary outage")

        health = alert_health_summary(session)

        assert health.total_attempts == 2
        assert health.success_rate == 50
        assert health.failed_attempts == 1


def test_notification_learning_tracks_ignored_and_acted_outcomes() -> None:
    with session_scope() as session:
        owner = _owner(session)
        record_notification_outcome(session, alert_key="instagram_alert", outcome="ignored", actor=owner)
        record_notification_outcome(session, alert_key="instagram_alert", outcome="acted", actor=owner)

        events = session.scalars(select(LearningEvent).where(LearningEvent.source_type == "notification")).all()
        summary = notification_learning_summary(session)

        assert {event.outcome for event in events} == {"ignored", "success"}
        assert summary["ignored"] == 1
        assert summary["acted_on"] == 1


def test_friction_detector_records_repeated_help_and_button_issues() -> None:
    with session_scope() as session:
        session.add_all(
            [
                FrictionItem(
                    screen="Notification Center",
                    issue="Owner opened Help repeatedly.",
                    severity="medium",
                    fix_recommendation="Simplify Notification Center.",
                ),
                ButtonIssue(
                    screen="Notification Center",
                    button_label="Help",
                    callback_data="help",
                    issue_type="dead_end",
                    severity="medium",
                    status="open",
                    evidence_summary="Help path loops back unexpectedly.",
                    recommended_fix="Preserve return context.",
                ),
            ]
        )
        session.flush()

        summary = friction_detector_summary(session)

        assert summary.status in {"needs_review", "needs_attention"}
        assert summary.repeated_help_count == 1
        assert summary.open_button_issue_count == 1
        assert session.scalar(select(Recommendation).where(Recommendation.recommendation_type == "notification_center_friction")) is not None


def test_notification_center_simple_screen_hides_evidence_wall_and_renders_emoji_buttons() -> None:
    with session_scope() as session:
        screen = render_platform_notification_center_page(session, _owner(session))
        buttons = _buttons(screen)

        assert "📱 Notification Center" in screen.text
        assert "✨ What Fortuna noticed" in screen.text
        assert "🎯 Next Best Move" in screen.text
        assert "Evidence:" not in screen.text
        assert "source_method" not in screen.text
        assert "not_configured" not in screen.text
        assert "📸 Instagram" in buttons
        assert "𝕏 X" in buttons
        assert "🔔 Alert Health" in buttons


def test_platform_alert_screen_supports_simulated_test_and_learning_buttons() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screen = render_platform_notification_detail_page(session, "instagram", owner)
        simulated = render_platform_notification_detail_page(session, "instagram", owner, action="test")
        details = render_platform_notification_detail_page(session, "instagram", owner, action="details")
        buttons = _buttons(screen)

        assert "Instagram Alerts" in screen.text
        assert "Fortuna can notify about" in screen.text
        assert "Evidence:" not in screen.text
        assert "not_configured" not in screen.text
        assert "🚨 Test Alert" in buttons
        assert "✅ Mark Acted On" in buttons
        assert "Simulated" in simulated.text or "simulated" in simulated.text
        assert "Alert Details" in details.text
        assert "Evidence:" in details.text
        assert "credentials" in details.text.casefold()


def test_alert_routing_and_health_screens_are_simple() -> None:
    with session_scope() as session:
        routing = render_alert_routing_center_page(session, _owner(session))
        health = render_alert_health_page(session, _owner(session))

        assert "🚦 Alert Routing Center" in routing.text
        assert "🎯 Next Best Move" in routing.text
        assert "raw" not in routing.text.lower()
        assert "🔔 Alert Health" in health.text
        assert "🎯 Next Best Move" in health.text
        assert "NotificationDeliveryAttempt" not in health.text
