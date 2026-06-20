from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.bot.screens import (
    render_platform_connections_page,
    render_platform_detail_page,
    render_platform_notification_center_page,
    render_production_observability_page,
)
from app.models.platform import PLATFORM_IDENTIFIERS, PlatformConnection
from app.services.auth import setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from app.services.platform_connections import (
    PlatformLayerState,
    ensure_platform_connections,
    platform_connection_status,
    platform_connections_overview,
    sanitize_platform_payload,
    test_platform_website as run_platform_website_check,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _button_texts(screen) -> list[str]:
    markup = screen.reply_markup
    if markup is None:
        return []
    return [button.text for row in markup.inline_keyboard for button in row]


def test_default_platform_connections_are_setup_states_not_failures() -> None:
    with session_scope() as session:
        ensure_platform_connections(session)
        rows = session.scalars(select(PlatformConnection)).all()

        assert {row.platform for row in rows} == set(PLATFORM_IDENTIFIERS)
        assert all(row.status in {"ready_to_connect", "not_connected"} for row in rows)
        assert all(row.status != "failed" for row in rows)

        overview = platform_connections_overview(session)
        assert overview["needs_attention"] == 0
        assert overview["waiting"] >= 1


def test_website_reachability_does_not_imply_login_connection(monkeypatch) -> None:
    with session_scope() as session:
        def fake_reachability(url: str, *, timeout_seconds: int = 5) -> PlatformLayerState:
            return PlatformLayerState(
                status="reachable",
                label="Reachable",
                evidence="Public website responded with HTTP 200.",
                checked_at=datetime.now(UTC),
                next_action="Connection setup is still required for account access.",
            )

        monkeypatch.setattr("app.services.platform_connections._safe_http_reachability", fake_reachability)
        result = run_platform_website_check(session, "instagram")
        status = platform_connection_status(session, "instagram")

        assert result.status == "reachable"
        assert status.website.status == "reachable"
        assert status.connection.status != "connected"
        assert status.stats.status == "waiting_for_connection"


def test_login_connection_does_not_imply_fresh_stats_without_evidence() -> None:
    with session_scope() as session:
        ensure_platform_connections(session)
        instagram = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == "instagram"))
        assert instagram is not None
        instagram.status = "connected"
        instagram.login_connected = True
        instagram.stats_available = True
        instagram.stats_fresh = True
        instagram.last_stats_check_at = None
        instagram.evidence_json = {"connection": {"summary": "Owner-approved session verified."}}
        session.flush()

        status = platform_connection_status(session, "instagram")

        assert status.connection.status == "connected"
        assert status.stats.status == "stale"
        assert "timestamp evidence" in status.stats.evidence


def test_fresh_stats_require_timestamp_and_evidence() -> None:
    with session_scope() as session:
        ensure_platform_connections(session)
        instagram = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == "instagram"))
        assert instagram is not None
        checked_at = datetime.now(UTC)
        instagram.status = "connected"
        instagram.login_connected = True
        instagram.stats_available = True
        instagram.stats_fresh = True
        instagram.last_stats_check_at = checked_at
        instagram.evidence_json = {
            "connection": {"summary": "Owner-approved API verified."},
            "stats": {"summary": "Stats retrieval succeeded.", "checked_at": checked_at.isoformat()},
        }
        session.flush()

        status = platform_connection_status(session, "instagram")

        assert status.stats.status == "fresh"
        assert status.stats.checked_at == checked_at


def test_platform_screens_hide_secrets_and_primary_screen_hides_status_codes() -> None:
    with session_scope() as session:
        ensure_platform_connections(session)
        instagram = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == "instagram"))
        assert instagram is not None
        instagram.status = "failed"
        instagram.evidence_summary = "api_secret=super-secret-token failed"
        instagram.evidence_json = {"connection": {"summary": "session_token=secret-value"}}
        session.flush()

        simple = render_platform_connections_page(session, _owner(session))
        detail = render_platform_detail_page(session, "instagram", _owner(session), details=True)

        combined = f"{simple.text}\n{detail.text}".casefold()
        assert "super-secret-token" not in combined
        assert "secret-value" not in combined
        assert "api_secret" not in combined
        assert "ready_to_connect" not in simple.text
        assert "not_configured" not in simple.text


def test_notification_routes_report_unconfigured_without_fake_success() -> None:
    with session_scope() as session:
        screen = render_platform_notification_center_page(session, _owner(session))
        status = platform_connection_status(session, "x")

        assert "Notification Center" in screen.text
        assert status.notifications.status == "not_configured"
        assert "not configured" in status.notifications.label.casefold()


def test_activation_readiness_renders_clear_next_action() -> None:
    with session_scope() as session:
        screen = render_platform_detail_page(session, "onlyfans", _owner(session))

        assert "OnlyFans" in screen.text
        assert "Website" in screen.text
        assert "Login" in screen.text
        assert "Stats" in screen.text
        assert "Notifications" in screen.text
        assert "Readiness" in screen.text
        assert "Next Best Move" in screen.text


def test_connection_setup_rejects_normal_chat_credentials() -> None:
    with session_scope() as session:
        screen = render_platform_detail_page(session, "instagram", _owner(session), section="connection")

        assert "Secure credential flow not active yet" in screen.text
        assert "normal chat" not in screen.text.casefold()


def test_emoji_buttons_render_on_platform_screens() -> None:
    with session_scope() as session:
        screen = render_platform_connections_page(session, _owner(session))
        buttons = _button_texts(screen)

        assert any(text.startswith("📸") for text in buttons)
        assert any(text.startswith("𝕏") for text in buttons)
        assert any(text.startswith("🔥") for text in buttons)
        assert any(text.startswith("🔔") for text in buttons)


def test_observability_sanitizes_platform_connection_evidence() -> None:
    with session_scope() as session:
        ensure_platform_connections(session)
        instagram = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == "instagram"))
        assert instagram is not None
        instagram.status = "failed"
        instagram.evidence_summary = "password=do-not-show"
        session.flush()

        screen = render_production_observability_page(session, _owner(session), details=True)

        assert "do-not-show" not in screen.text
        assert "password=" not in screen.text.casefold()
        assert "Platform Connections" in screen.text


def test_sanitize_platform_payload_redacts_secret_values() -> None:
    payload = {
        "public": "ok",
        "nested": {"token": "abc123"},
        "list": ["safe", "secret=hidden"],
    }

    sanitized = sanitize_platform_payload(payload)

    assert "abc123" not in str(sanitized)
    assert "hidden" not in str(sanitized)


def test_help_brain_platform_connection_answers() -> None:
    with session_scope() as session:
        owner = _owner(session)

        reachable = help_brain_answer(session, owner, question="Why does Instagram say reachable but not connected?")
        stats = help_brain_answer(session, owner, question="What does stats waiting for connection mean?")
        auto = help_brain_answer(session, owner, question="Does Fortuna auto-like/comment/follow?")

        assert "Reachable only means Fortuna can access the public website" in reachable.answer
        assert "Connected means" in reachable.answer
        assert "not verified an approved platform connection" in stats.answer
        assert "does not auto-post" in auto.answer
        assert "auto-comment" in auto.answer
        assert "like" in auto.answer
        assert "follow" in auto.answer
