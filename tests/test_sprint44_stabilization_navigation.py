import re
from datetime import UTC, datetime

import pytest

from app.bot.navigation import screen_for_page
from app.bot.navigation_stack import parent_page_for, root_page_for
from app.models.proxy import ProxySessionMemory
from app.services.auth import setup_owner_if_needed
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import (
    create_proxy,
    list_proxies,
    remember_proxy_session,
    rotate_olympix_session,
)
from tests.utils import session_scope


SNAKE_CASE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")


def _callbacks(screen) -> list[str]:
    return [
        button.callback_data
        for row in screen.reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def _owner_context(session):
    owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")
    principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)
    return owner, principal


def test_navigation_parent_map_matches_core_owner_flows() -> None:
    assert parent_page_for("intelligence") == "owner_advanced"
    assert parent_page_for("intelligence:trends") == "intelligence"
    assert parent_page_for("proxy:12:manage") == "proxy:12"
    assert parent_page_for("setup:wizard:model") == "setup_progress"
    assert root_page_for("proxy:12:manage") == "proxies"
    assert root_page_for("intelligence:trends") == "owner_advanced"


def test_more_children_and_proxy_manage_back_buttons_are_predictable() -> None:
    with session_scope() as session:
        owner, principal = _owner_context(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="Olympix",
            host="host.olympix.io",
            port=1080,
            base_username="user_demo,type_mobile",
            password="secret",
            session_suffix="abcd1111",
            proxy_type="SOCKS5 Mobile",
        )

        more = screen_for_page("owner_advanced", principal, session=session, user=owner)
        intelligence = screen_for_page("intelligence", principal, session=session, user=owner)
        automations = screen_for_page("automations", principal, session=session, user=owner)
        reports = screen_for_page("reports", principal, session=session, user=owner)
        settings = screen_for_page("settings", principal, session=session, user=owner)
        observability = screen_for_page("production_observability", principal, session=session, user=owner)
        proxy_manage = screen_for_page(f"proxy:{proxy.id}:manage", principal, session=session, user=owner)

        assert "🌙 More" in more.text
        assert "nav:menu" in _callbacks(more)
        assert "nav:owner_advanced" in _callbacks(intelligence)
        assert "nav:owner_advanced" in _callbacks(automations)
        assert "nav:owner_advanced" in _callbacks(reports)
        assert "nav:owner_advanced" in _callbacks(settings)
        assert "nav:owner_advanced" in _callbacks(observability)
        assert f"nav:proxy:{proxy.id}" in _callbacks(proxy_manage)


def test_integrity_and_observability_lead_with_summary_not_database_rows() -> None:
    with session_scope() as session:
        owner, principal = _owner_context(session)

        integrity = screen_for_page("integrity", principal, session=session, user=owner)
        integrity_details = screen_for_page("integrity:details", principal, session=session, user=owner)
        observability = screen_for_page("production_observability", principal, session=session, user=owner)

        assert "Production Check" in integrity.text
        assert "Fortuna checked:" in integrity.text
        assert "Recommended action:" in integrity.text
        assert "Alembic" not in integrity.text
        assert "audit row" not in integrity.text.casefold()
        assert "Production Check Technical Details" in integrity_details.text
        assert "Checks:" in integrity_details.text
        assert "Production Observability" in observability.text
        assert "Alembic" not in observability.text
        assert "Audit Rows" not in observability.text


def test_simple_screens_do_not_leak_snake_case_or_internal_rows() -> None:
    with session_scope() as session:
        owner, principal = _owner_context(session)
        pages = ["menu", "owner_advanced", "proxies", "integrity", "production_observability"]

        for page in pages:
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert not SNAKE_CASE.search(screen.text), page
            for raw in ("metadata_json", "entity_id", "source_type", "status=open"):
                assert raw not in screen.text.casefold()


def test_proxy_vault_hides_placeholder_records_and_uses_simple_empty_state() -> None:
    with session_scope() as session:
        owner, principal = _owner_context(session)
        create_proxy(
            session,
            actor=owner,
            provider="placeholder",
            host="placeholder-proxy-1.local",
            port=8000,
            base_username="missing",
            password="secret",
        ).metadata_json = {"is_placeholder": True, "archived": True}
        session.flush()

        assert list_proxies(session) == []
        screen = screen_for_page("proxies", principal, session=session, user=owner)

        assert "No real proxies saved yet." in screen.text
        assert "placeholder-proxy" not in screen.text
        assert "Healthy 100" not in screen.text
        assert "nav:proxies:olympix:paste" in _callbacks(screen)


def test_proxy_rotation_does_not_reuse_recent_session_suffix(monkeypatch) -> None:
    with session_scope() as session:
        owner, _principal = _owner_context(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="Olympix",
            host="host.olympix.io",
            port=1080,
            base_username="user_demo,type_mobile",
            password="secret",
            session_suffix="abcd1111",
            proxy_type="SOCKS5 Mobile",
        )
        remember_proxy_session(session, proxy, "used2222", source="rotated", used_at=datetime.now(UTC))
        session.flush()

        candidates = iter(["abcd1111", "used2222", "new3333"])
        monkeypatch.setattr("app.services.proxies.generate_olympix_session_suffix", lambda length=8: next(candidates))

        history = rotate_olympix_session(session, proxy, actor=owner)

        assert history.new_session_suffix == "new3333"
        assert proxy.session_suffix == "new3333"
        memory = session.query(ProxySessionMemory).filter_by(proxy_id=proxy.id).all()
        assert len(memory) >= 3
        assert all(item.session_suffix_masked != "new3333" for item in memory)


def test_proxy_rotation_fails_safely_when_unique_suffix_unavailable(monkeypatch) -> None:
    with session_scope() as session:
        owner, _principal = _owner_context(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="Olympix",
            host="host.olympix.io",
            port=1080,
            base_username="user_demo,type_mobile",
            password="secret",
            session_suffix="abcd1111",
            proxy_type="SOCKS5 Mobile",
        )
        session.flush()
        monkeypatch.setattr("app.services.proxies.generate_olympix_session_suffix", lambda length=8: "abcd1111")

        with pytest.raises(RuntimeError):
            rotate_olympix_session(session, proxy, actor=owner)

        assert proxy.session_suffix == "abcd1111"
