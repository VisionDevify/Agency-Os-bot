import asyncio
from pathlib import Path

from app.bot.runner import _cleanup_navigation_messages_on_start
from app.bot.navigation import screen_for_page
from app.bot.screens.errors import render_button_health_report_page
from app.bot.screens.settings import render_ui_self_test_page
from app.models.chat import PERSISTENT_ALERT, TEMPORARY_NAVIGATION, BotChatMessage, ChatCleanupRun
from app.services.auth import setup_owner_if_needed
from app.services.button_health import button_health_summary
from app.services.chat_cleanup import (
    chat_cleanup_metrics,
    classify_navigation_callback,
    is_stale_navigation_callback,
    reset_navigation_session,
    track_bot_message,
)
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from tests.test_sprint45_chat_cleanup import FakeBot
from tests.utils import session_scope


def test_start_cleanup_marks_old_navigation_inactive_and_records_remaining_batch() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        for index in range(5):
            track_bot_message(
                session,
                chat_id=10,
                user=owner,
                message_id=400 + index,
                message_label=TEMPORARY_NAVIGATION,
                screen="menu",
            )

        navigation_version = asyncio.run(
            _cleanup_navigation_messages_on_start(
                FakeBot(),
                session,
                user=owner,
                chat_id=10,
                cleanup_limit=2,
                time_budget_seconds=10,
            )
        )

        run = session.query(ChatCleanupRun).one()
        assert run.total_candidates == 5
        assert run.attempted_count == 2
        assert run.remaining_count == 3
        assert navigation_version > 1
        assert session.query(BotChatMessage).filter_by(chat_id=10, active_navigation=True).count() == 0


def test_inactive_old_menu_callback_is_stale_and_cannot_overwrite_active_screen() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        old = track_bot_message(session, chat_id=10, user=owner, message_id=500, screen="menu")
        new_version = reset_navigation_session(session, chat_id=10, user=owner)
        fresh = track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=501,
            screen="proxies",
            navigation_version=new_version,
        )

        state = classify_navigation_callback(session, chat_id=10, user=owner, message_id=old.message_id)

        assert state.classification == "stale_old_menu"
        assert state.active_message_id == fresh.message_id
        assert is_stale_navigation_callback(session, chat_id=10, user=owner, message_id=old.message_id) is True
        assert is_stale_navigation_callback(session, chat_id=10, user=owner, message_id=fresh.message_id) is False


def test_intelligence_quality_back_callback_is_current_active_message() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        active = track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=502,
            screen="intelligence:quality",
        )

        state = classify_navigation_callback(session, chat_id=10, user=owner, message_id=active.message_id)

        assert state.classification == "current"
        assert state.is_stale is False
        assert state.active_message_id == active.message_id


def test_intelligence_quality_back_remains_current_after_start_cleanup() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(session, chat_id=10, user=owner, message_id=503, screen="menu", navigation_version=1)
        new_version = reset_navigation_session(session, chat_id=10, user=owner)
        active = track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=504,
            screen="intelligence:quality",
            navigation_version=new_version,
        )

        state = classify_navigation_callback(session, chat_id=10, user=owner, message_id=active.message_id)

        assert state.classification == "current"
        assert state.active_navigation_version == new_version


def test_persistent_alert_callback_remains_valid_even_without_active_navigation() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        alert = track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=600,
            message_label=PERSISTENT_ALERT,
            screen="creator_alert",
        )

        state = classify_navigation_callback(session, chat_id=10, user=owner, message_id=alert.message_id)

        assert state.classification == "persistent_action"
        assert state.is_stale is False


def test_multiple_active_menus_make_button_health_need_review() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        session.add_all(
            [
                BotChatMessage(
                    chat_id=10,
                    user_id=owner.id,
                    message_id=700,
                    message_label=TEMPORARY_NAVIGATION,
                    screen="menu",
                    active_navigation=True,
                    deletion_status="active",
                    navigation_version=1,
                ),
                BotChatMessage(
                    chat_id=10,
                    user_id=owner.id,
                    message_id=701,
                    message_label=TEMPORARY_NAVIGATION,
                    screen="proxies",
                    active_navigation=True,
                    deletion_status="active",
                    navigation_version=2,
                ),
            ]
        )
        session.flush()

        health = button_health_summary(session)
        screen = render_button_health_report_page(session, owner)

        assert health.telegram_ui_status == "needs_attention"
        assert health.overall_status == "needs_attention"
        assert "Old menu cleanup needs review." in screen.text
        assert "Clean Menus" in str(screen.reply_markup.inline_keyboard)


def test_inactive_old_menus_are_reported_as_details_not_active_risk() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(session, chat_id=10, user=owner, message_id=800, screen="menu")
        reset_navigation_session(session, chat_id=10, user=owner)

        metrics = chat_cleanup_metrics(session)
        summary = production_observability_summary(session)
        selftest = render_ui_self_test_page(session, owner, details=True)

        assert metrics.status == "healthy"
        assert metrics.remaining_count >= 1
        assert not any("Telegram UI Cleanup:" in item for item in summary["observability_current_issues"])
        assert "Telegram UI Cleanup:" in selftest.text
        assert "old temporary menu" in selftest.text


def test_chat_cleanup_settings_clean_now_and_details_are_available() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        simple = screen_for_page("settings:chat_cleanup", principal, session=session, user=owner, chat_id=10)
        details = screen_for_page("settings:chat_cleanup:details", principal, session=session, user=owner, chat_id=10)

        assert "Clean Now" in str(simple.reply_markup.inline_keyboard)
        assert "Preserves:" in simple.text
        assert "Total Candidates:" in details.text


def test_latest_active_telegram_testing_docs_exist() -> None:
    doc = Path("docs/telegram_live_testing.md")
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "latest active bot message" in text
    assert "old visible menu" in text
