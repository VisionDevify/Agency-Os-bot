import pytest

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_notification_group_setup_page,
    render_notification_routing_test_page,
    render_production_observability_page,
    render_proxy_check_history_page,
    render_proxy_detail_page,
)
from app.models.coo import PriorityItem
from app.models.learning import LearningEvent
from app.models.proxy import ProxyHealthCheckResult
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.notifications import (
    add_current_chat_as_target,
    create_notification_target,
    mask_target_chat_id,
    notification_group_setup_status,
    run_notification_routing_smoke_test,
)
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxy_adapters import ProxyAdapterResult, ProxyProviderAdapter
from app.services.proxies import (
    create_proxy,
    run_real_proxy_check,
    run_simulated_proxy_check,
    set_proxy_real_check_flags,
)
from tests.utils import session_scope


class FakeAdapter(ProxyProviderAdapter):
    def __init__(self, result: ProxyAdapterResult) -> None:
        self.result = result
        self.called = False

    def check(self, proxy, *, include_location: bool, timeout_seconds: int) -> ProxyAdapterResult:
        self.called = True
        return self.result


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _proxy(session, owner):
    return create_proxy(
        session,
        actor=owner,
        provider="Olympix Mobile SOCKS5",
        host="host.olympix.io",
        port=1080,
        base_username="base-user",
        password="super-secret",
        target_country="United States",
        target_state="Florida",
        target_city="Miami",
    )


def test_register_current_chat_target_masks_chat_id_and_maps_purpose() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target = add_current_chat_as_target(
            session,
            actor=owner,
            chat_id=-100123456789,
            chat_title="Fortuna OS - Testing Sandbox",
            target_type="telegram_group",
            purpose="testing",
        )
        screen = render_notification_group_setup_page(session)

        assert target.purpose == "testing"
        assert target.target_type == "telegram_group"
        assert mask_target_chat_id(target).startswith("-1")
        assert "-100123456789" not in screen.text
        assert "Testing Sandbox: Configured" in screen.text


def test_notification_routing_smoke_test_records_sandbox_and_simulated_routes() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna OS - Testing Sandbox",
            target_type="telegram_group",
            purpose="testing",
            telegram_chat_id="-100111222333",
        )
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna OS - Operations",
            target_type="telegram_group",
            purpose="operations",
            telegram_chat_id="-100444555666",
        )

        result = run_notification_routing_smoke_test(session, actor=owner, send_testing=True)
        screen = render_notification_routing_test_page(session)

        attempts = session.query(NotificationDeliveryAttempt).order_by(NotificationDeliveryAttempt.id).all()
        assert "Testing Sandbox" in result.actual_sends
        assert any("Operations: simulated only" == item for item in result.skipped)
        assert sorted(attempt.status for attempt in attempts) == ["pending", "skipped"]
        assert "HQ" in screen.text
        assert "Raw chat IDs are never shown" in screen.text


def test_proxy_adapter_disabled_by_default_and_owner_enable_required() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = _proxy(session, owner)
        fake = FakeAdapter(ProxyAdapterResult(success=True, latency_ms=10))

        skipped = run_real_proxy_check(session, proxy, actor=owner, adapter=fake)
        assert skipped.status == "skipped"
        assert fake.called is False

        viewer = get_or_create_telegram_user(session, telegram_user_id=2, display_name="Viewer", owner_telegram_id=1)
        viewer.status = USER_STATUS_ACTIVE
        viewer.is_active = True
        assign_role_to_user(session, viewer, RoleName.ADMIN, actor=owner)
        with pytest.raises(PermissionError):
            set_proxy_real_check_flags(session, proxy, actor=viewer, health_enabled=True, location_enabled=True)


def test_proxy_real_health_check_stores_result_and_hides_secret_in_ui() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = _proxy(session, owner)
        set_proxy_real_check_flags(session, proxy, actor=owner, health_enabled=True, location_enabled=True)
        result = run_real_proxy_check(
            session,
            proxy,
            actor=owner,
            adapter=FakeAdapter(
                ProxyAdapterResult(
                    success=True,
                    latency_ms=123,
                    detected_ip_masked="203.0.x.10",
                    detected_country="United States",
                    detected_state="Florida",
                    detected_city="Miami",
                    location_confidence="provider_reported",
                )
            ),
        )
        detail = render_proxy_detail_page(session, proxy.id)
        history = render_proxy_check_history_page(session, proxy.id)

        assert result.status == "passed"
        assert session.query(ProxyHealthCheckResult).count() == 1
        assert "Real Checks: enabled" in detail.text
        assert "Latest Check:" in detail.text
        assert "203.0.x.10" in detail.text
        assert "super-secret" not in detail.text
        assert "encrypted_password" not in history.text


def test_failed_proxy_real_check_creates_learning_recommendation_and_priority() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = _proxy(session, owner)
        set_proxy_real_check_flags(session, proxy, actor=owner, health_enabled=True, location_enabled=True)

        result = run_real_proxy_check(
            session,
            proxy,
            actor=owner,
            adapter=FakeAdapter(
                ProxyAdapterResult(
                    success=False,
                    failure_reason="password bad: super-secret",
                )
            ),
        )

        assert result.status == "failed"
        assert "super-secret" not in (result.error_message or "")
        assert session.query(LearningEvent).filter_by(source_type="proxy").count() == 1
        assert session.query(Recommendation).filter_by(recommendation_type="proxy_real_check_failed").count() == 1
        assert session.query(PriorityItem).filter_by(category="proxy_health_failure").count() == 1


def test_observability_shows_notification_and_proxy_status() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna OS - HQ",
            target_type="telegram_group",
            purpose="owner",
            telegram_chat_id="-100123123123",
        )
        proxy = _proxy(session, owner)
        run_simulated_proxy_check(session, proxy, actor=owner)
        screen = render_production_observability_page(session)

        assert "Notification Targets Configured: 1" in screen.text
        assert "Proxy Health Reality:" in screen.text
        assert "Real Health Checks: no" in screen.text


def test_notification_group_setup_callback_renders_for_owner() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)
        screen = screen_for_page("notification_group_setup", principal, session=session, user=owner)

        assert "Notification Group Setup" in screen.text
        assert "Fortuna OS - HQ" in screen.text
        assert notification_group_setup_status(session)[0].label == "HQ"
