import re

from app.bot.screens import (
    render_automation_templates_page,
    render_automations_home,
    render_executive_mode_page,
    render_help_center_page,
    render_help_copilot_page,
    render_intelligence_home,
    render_learning_center_page,
    render_main_menu,
    render_proxies_home,
    render_recommendations_page,
    render_setup_progress_page,
)
from app.services.auth import setup_owner_if_needed
from tests.utils import session_scope


SNAKE_CASE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")
RAW_TERMS = (
    "source_type",
    "entity_id",
    "metadata_json",
    "callback",
    "renderer",
    "system_heartbeat",
    "recommendations_open",
    "status=open",
)


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _button_labels(screen) -> list[str]:
    data = screen.reply_markup.model_dump() if screen.reply_markup else {}
    labels: list[str] = []
    for row in data.get("inline_keyboard", []):
        for button in row:
            labels.append(button["text"])
    return labels


def _primary_labels(screen) -> list[str]:
    return [label for label in _button_labels(screen) if label not in {"Back", "Main Menu", "Simple Mode"}]


def _assert_calm_simple_screen(text: str) -> None:
    assert not SNAKE_CASE.search(text)
    lowered = text.lower()
    for term in RAW_TERMS:
        assert term not in lowered


def test_owner_home_is_calm_and_has_one_clear_next_action() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screen = render_main_menu(session, owner)

        assert "Fortuna Command Center" in screen.text
        assert "Agency OS Readiness" in screen.text
        assert "Fastest Gain" in screen.text
        assert "Attention Needed" in screen.text
        assert any("Today" in label for label in _button_labels(screen))
        assert "Agency Health Score" not in screen.text
        _assert_calm_simple_screen(screen.text)
        assert len(_primary_labels(screen)) <= 7


def test_primary_simple_screens_hide_raw_internal_terms() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screens = [
            render_setup_progress_page(session, owner),
            render_proxies_home(session),
            render_intelligence_home(session),
            render_learning_center_page(session),
            render_automations_home(session, owner),
            render_executive_mode_page(session, owner),
            render_recommendations_page(session, owner),
            render_help_center_page(owner),
            render_help_copilot_page(session, owner, question="next"),
        ]

        for screen in screens:
            _assert_calm_simple_screen(screen.text)


def test_more_details_paths_exist_for_power_screens() -> None:
    with session_scope() as session:
        owner = _owner(session)

        for screen in (
            render_proxies_home(session),
            render_intelligence_home(session),
            render_learning_center_page(session),
            render_automations_home(session, owner),
        ):
            labels = _button_labels(screen)
            assert "More Details" in labels or "View Proxies" in labels
            assert len(_primary_labels(screen)) <= 6


def test_proxy_vault_uses_simple_paste_assign_flow() -> None:
    with session_scope() as session:
        screen = render_proxies_home(session)

        assert "No real proxies saved yet." in screen.text
        assert "Paste your Olympix proxy string" in screen.text
        assert "What to paste" in screen.text
        assert "Host:" not in screen.text
        assert "session_" not in screen.text
        assert "Paste Proxy" in _button_labels(screen)


def test_intelligence_learning_and_hq_lead_with_guidance_not_metrics() -> None:
    with session_scope() as session:
        owner = _owner(session)
        intelligence = render_intelligence_home(session)
        learning = render_learning_center_page(session)
        hq = render_executive_mode_page(session, owner)

        assert "Fortuna Noticed" in intelligence.text
        assert "Learning Events:" not in learning.text
        assert "Readiness:" not in hq.text
        assert "Top Blockers" in hq.text


def test_automation_uses_friendly_names() -> None:
    with session_scope() as session:
        owner = _owner(session)
        home = render_automations_home(session, owner)
        templates = render_automation_templates_page(session, owner)

        assert "Daily Checkup" in home.text or "Daily Checkup" in templates.text
        assert "Daily Intelligence Scan" not in templates.text
        assert "Nudge Overdue Work" in templates.text
