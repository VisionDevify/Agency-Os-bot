from datetime import UTC, datetime

from app.bot.navigation_stack import parent_page_for
from app.models.button_issue import ButtonIssue
from app.models.callback_error import CallbackErrorLog
from app.services.auth import setup_owner_if_needed
from app.services.chat_cleanup import STALE_MENU_RESPONSE, chat_cleanup_metrics, reset_navigation_session, track_bot_message
from app.services.help_brain import detect_help_intent, help_brain_answer
from app.services.observability import production_observability_summary
from app.services.team_ux import (
    ai_readability_check,
    all_screen_audience_metadata,
    all_team_role_metadata,
    record_user_trust_signal,
    team_ux_readiness,
    trust_signal_summary,
)
from tests.utils import session_scope


def test_major_team_navigation_paths_have_back_parent() -> None:
    expected = {
        "menu": "menu",
        "owner_advanced": "menu",
        "coo:briefing": "owner_advanced",
        "ai_brain": "owner_advanced",
        "search": "owner_advanced",
        "recovery_center": "owner_advanced",
        "agency_activation": "menu",
        "decision:memory": "coo:briefing",
        "reality:check": "intelligence:quality",
        "intelligence:quality": "coo:briefing",
        "platforms": "owner_advanced",
        "platforms:notifications": "platforms",
    }

    for page, parent in expected.items():
        assert parent_page_for(page) == parent


def test_team_role_and_screen_metadata_exist_for_future_modes() -> None:
    roles = {metadata.role: metadata for metadata in all_team_role_metadata()}
    screens = {metadata.screen: metadata for metadata in all_screen_audience_metadata()}

    assert set(roles) == {"owner", "manager", "chatter", "va"}
    assert roles["owner"].owner_only is True
    assert roles["chatter"].future_chatter_screen is True
    assert roles["va"].future_va_screen is True
    assert screens["coo:briefing"].owner_only is True
    assert screens["platforms"].manager_capable is True


def test_team_ux_ready_when_active_screen_is_clean() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(session, chat_id=10, user=owner, message_id=100, screen="menu")

        readiness = team_ux_readiness(session)

        assert readiness.status == "ready"
        assert readiness.score >= 90
        assert "Active screen" in readiness.evidence


def test_old_menu_risk_creates_team_ux_needs_review_and_observability_signal() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(session, chat_id=10, user=owner, message_id=100, screen="menu")
        reset_navigation_session(session, chat_id=10, user=owner)

        cleanup = chat_cleanup_metrics(session)
        readiness = team_ux_readiness(session)
        summary = production_observability_summary(session)

        assert cleanup.status == "needs_review"
        assert readiness.status == "needs_review"
        assert summary["team_ux_meaningful"] is True
        assert any("Team UX:" in issue for issue in summary["observability_current_issues"])


def test_callback_failures_and_trust_signals_make_team_ux_not_ready() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        session.add(
            CallbackErrorLog(
                telegram_user_id=owner.telegram_id,
                user_id=owner.id,
                callback_data="nav:coo:briefing",
                page="coo:briefing",
                affected_screen="COO Briefing",
                exception_type="IntegrityError",
                error_message="database consistency issue",
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            ButtonIssue(
                screen="coo:briefing",
                button_label="Back",
                callback_data="nav:owner_advanced",
                issue_type="bad_back_target",
                severity="high",
                status="open",
                evidence_summary="Back path failed during navigation audit.",
                recommended_fix="Return to More.",
            )
        )
        record_user_trust_signal(
            session,
            screen="coo:briefing",
            signal_type="repeat Back usage",
            evidence="Owner repeatedly used Back after opening COO Briefing.",
        )
        session.flush()

        trust = trust_signal_summary(session)
        readiness = team_ux_readiness(session)

        assert trust.callback_failures == 1
        assert trust.navigation_failures == 1
        assert trust.repeated_back_usage >= 1
        assert readiness.status == "not_ready"
        assert readiness.callback_reliability < 100


def test_ai_readability_flags_developer_language_and_suggests_plain_words() -> None:
    result = ai_readability_check(
        "Calibration metadata_json says insufficient data. callback_id failed.",
        intended_audience="chatter",
    )

    assert result.status != "ready"
    assert "Uses developer language." in result.issues
    assert "Fortuna needs more information here" in result.simplified_suggestion
    assert "Next:" in result.simplified_suggestion


def test_help_brain_answers_old_menu_active_screen_and_cleanup_questions() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)

        old_menu = help_brain_answer(session, owner, question="Why does Fortuna say a menu is old?")
        active_screen = help_brain_answer(session, owner, question="What is the active screen?")
        cleanup = help_brain_answer(session, owner, question="How does chat cleanup work?")

        assert detect_help_intent("Why does Fortuna say a menu is old?") == "old_menu"
        assert "previous Fortuna screen" in old_menu.answer
        assert "newest Fortuna menu" in active_screen.answer
        assert "Reports, alerts, exports" in cleanup.answer


def test_stale_menu_response_uses_team_safe_redirect_language() -> None:
    assert STALE_MENU_RESPONSE == "That menu is no longer active. Opening the latest screen..."
