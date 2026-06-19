from pathlib import Path

from app.bot.screens import (
    render_help_copilot_page,
    render_notification_group_pilot_page,
    render_production_observability_page,
    render_proxy_real_check_pilot_page,
    render_ui_self_test_page,
)
from app.models.help import HelpKnowledgeBase, HelpQuestionLog, UISelfTestRun
from app.models.learning import LearningEvent
from app.models.proxy import ProxyHealthCheckResult
from app.models.reporting import NotificationDeliveryAttempt
from app.services.auth import get_or_create_telegram_user, setup_owner_if_needed
from app.services.help_brain import (
    help_brain_answer,
    help_article_count,
    notification_pilot_status,
    record_help_feedback,
    seed_help_knowledge_base,
)
from app.services.notifications import create_notification_target, run_notification_routing_smoke_test
from app.services.proxy_adapters import ProxyAdapterResult, ProxyProviderAdapter
from app.services.proxies import create_proxy, run_real_proxy_check, set_proxy_real_check_flags
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


def test_help_brain_seeds_kb_answers_readiness_and_logs_question() -> None:
    with session_scope() as session:
        owner = _owner(session)

        result = help_brain_answer(session, owner, question="Why is readiness low?")
        screen = render_help_copilot_page(session, owner, question="readiness_low")

        assert help_article_count(session) >= 15
        assert session.query(HelpKnowledgeBase).filter_by(topic="notification_group_setup").count() == 1
        assert result.intent == "readiness_low"
        assert "Readiness" in result.answer
        assert session.query(HelpQuestionLog).count() == 2
        assert "Ask Fortuna" in screen.text
        assert "TELEGRAM_BOT_TOKEN" not in screen.text


def test_help_brain_permission_safe_for_non_admin_proxy_question() -> None:
    with session_scope() as session:
        owner = _owner(session)
        viewer = get_or_create_telegram_user(session, telegram_user_id=2, display_name="Viewer", owner_telegram_id=owner.telegram_id)
        viewer.status = "active"

        result = help_brain_answer(session, viewer, question="How do I assign a proxy?")

        assert "restricted" in result.answer.lower()
        assert "super-secret" not in result.answer
        assert "encrypted_password" not in result.answer


def test_help_feedback_creates_learning_event() -> None:
    with session_scope() as session:
        owner = _owner(session)
        result = help_brain_answer(session, owner, question="Where do I start?")

        record_help_feedback(session, log_id=result.log_id, feedback="still_confused", actor=owner)

        log = session.get(HelpQuestionLog, result.log_id)
        assert log.feedback == "still_confused"
        assert session.query(LearningEvent).filter_by(event_type="help.feedback.still_confused").count() == 1


def test_notification_group_pilot_checklist_and_routing_test() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna OS - Testing Sandbox",
            target_type="telegram_group",
            purpose="testing",
            telegram_chat_id="-100123456789",
        )

        status = notification_pilot_status(session)
        result = run_notification_routing_smoke_test(session, actor=owner)
        screen = render_notification_group_pilot_page(session)

        assert status["configured"] == 1
        assert "Fortuna HQ" in result.actual_sends
        assert session.query(NotificationDeliveryAttempt).count() == 1
        assert "register the three Fortuna Telegram spaces" in screen.text
        assert "-100123456789" not in screen.text


def test_proxy_real_check_pilot_uses_mocked_adapter_and_hides_secret() -> None:
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
                    latency_ms=88,
                    detected_ip_masked="203.0.x.55",
                    detected_country="United States",
                    detected_state="Florida",
                    detected_city="Miami",
                )
            ),
        )
        screen = render_proxy_real_check_pilot_page(session)

        assert result.status == "passed"
        assert session.query(ProxyHealthCheckResult).count() == 1
        assert "Real Check Pilot" in screen.text
        assert "super-secret" not in screen.text
        assert "encrypted_password" not in screen.text


def test_ui_self_test_and_observability_surface_help_and_pilot_status() -> None:
    with session_scope() as session:
        owner = _owner(session)
        seed_help_knowledge_base(session)
        help_brain_answer(session, owner, question="How do I register notification groups?")

        selftest = render_ui_self_test_page(session, owner, run_now=True)
        selftest_details = render_ui_self_test_page(session, owner, details=True)
        observability = render_production_observability_page(session, details=True)

        assert session.query(UISelfTestRun).count() == 1
        assert "Fortuna Self-Test" in selftest.text
        assert "Recommended Action:" in selftest.text
        assert "UI Self-Test Technical Details" in selftest_details.text
        assert "Help Questions Today:" in observability.text
        assert "Notification Pilot:" in observability.text
        assert "Proxy Pilot:" in observability.text
        assert "TELEGRAM_BOT_TOKEN" not in selftest.text


def test_bot_worker_runner_does_not_run_migrations_on_startup() -> None:
    runner_source = Path("app/bot/runner.py").read_text()

    assert "run_migrations" not in runner_source
