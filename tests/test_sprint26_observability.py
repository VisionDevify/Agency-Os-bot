import importlib

import pytest
from sqlalchemy import text

from app.bot.navigation import screen_for_page
from app.bot.screens import render_production_observability_page, render_proxy_detail_page, render_proxy_list_page
from app.bot.screens.proxies import render_proxy_simulation_page
from app.models.reporting import NotificationTarget
from app.services.auth import get_or_create_telegram_user, setup_owner_if_needed
from app.services.heartbeats import record_heartbeat
from app.services.observability import (
    current_alembic_revision,
    notification_target_readiness,
    production_observability_summary,
)
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_proxy
from tests.utils import session_scope


SCREEN_MODULES = (
    "accounts",
    "activation",
    "automations",
    "coo",
    "formatting",
    "help",
    "home",
    "incidents",
    "intelligence",
    "learning",
    "models",
    "opportunities",
    "proxies",
    "reports",
    "router",
    "settings",
    "tasks",
    "team",
)


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def test_split_screen_modules_import_and_core_callbacks_render() -> None:
    for module in SCREEN_MODULES:
        imported = importlib.import_module(f"app.bot.screens.{module}")
        assert imported is not None

    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)
        for page in ("menu", "settings", "production_observability", "bot_status", "proxies"):
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text
            assert "Traceback" not in screen.text


def test_production_observability_renders_safe_metadata_and_owner_gate() -> None:
    with session_scope() as session:
        owner = _owner(session)
        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={"source": "startup", "bot_started_at": "2026-06-18T00:00:00Z", "token": "secret"},
        )
        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={"source": "polling_loop", "last_polling_loop_at": "2026-06-18T00:01:00Z"},
        )
        screen = render_production_observability_page(session)
        details = render_production_observability_page(session, details=True)

        assert "Production Observability" in screen.text
        assert "Status:" in screen.text
        assert "Recommended Action:" in screen.text
        assert "App: Fortuna OS" not in screen.text
        assert "Production Observability Technical Details" in details.text
        assert "App: Fortuna OS" in details.text
        assert "Alembic:" in details.text
        assert "Bot Started: 2026-06-18T00:00:00Z" in details.text
        assert "Last Polling Loop: 2026-06-18T00:01:00Z" in details.text
        assert "Railway logs must be viewed in Railway dashboard." in details.text
        assert "TELEGRAM_BOT_TOKEN" not in details.text
        assert "DATABASE_URL" not in details.text
        assert "secret" not in details.text

        user = get_or_create_telegram_user(
            session,
            telegram_user_id=2,
            display_name="Viewer",
            owner_telegram_id=owner.telegram_id,
        )
        principal = PermissionPrincipal(telegram_id=user.telegram_id, is_owner=False, role=RoleName.VIEWER)
        with pytest.raises(PermissionError):
            screen_for_page("production_observability", principal, session=session, user=user)


def test_db_revision_and_missing_metadata_are_displayed_cleanly() -> None:
    with session_scope() as session:
        session.execute(text("create table alembic_version (version_num varchar(32) not null)"))
        session.execute(text("insert into alembic_version (version_num) values ('0024_fortuna_coo')"))
        assert current_alembic_revision(session) == "0024_fortuna_coo"

        summary = production_observability_summary(session)
        assert summary["alembic_current"] == "0024_fortuna_coo"
        assert summary["app_version"] == "Unknown"
        assert summary["git_commit"] == "Unknown"
        assert summary["deployed_at"] == "Unknown"


def test_notification_readiness_card_tracks_required_targets() -> None:
    with session_scope() as session:
        session.add(
            NotificationTarget(
                name="Fortuna OS - HQ",
                target_type="telegram_group",
                purpose="owner",
                is_active=True,
            )
        )
        readiness = notification_target_readiness(session)
        by_purpose = {item["purpose"]: item for item in readiness}

        assert by_purpose["hq"]["configured"] is True
        assert by_purpose["ops"]["configured"] is False
        assert len(readiness) == 3


def test_proxy_screens_label_simulated_health_and_hide_secrets() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="olympix",
            host="host.olympix.io",
            port=1080,
            base_username="base-user",
            password="super-secret",
            target_country="United States",
            target_state="Florida",
            target_city="Miami",
        )

        list_screen = render_proxy_list_page(session)
        detail_screen = render_proxy_detail_page(session, proxy.id)
        simulation_screen = render_proxy_simulation_page(session)

        for screen in (list_screen, detail_screen, simulation_screen):
            assert "simulated" in screen.text.lower()
            assert "super-secret" not in screen.text
            assert "encrypted_password" not in screen.text
            assert "{" not in screen.text
            assert "}" not in screen.text
