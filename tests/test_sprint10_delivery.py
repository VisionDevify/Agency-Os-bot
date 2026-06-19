import json
from pathlib import Path

from app.bot.screens import render_bot_status_page, render_notification_target_detail_page
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.services.auth import setup_owner_if_needed
from app.services.heartbeats import record_heartbeat, system_status_summary
from app.services.notifications import (
    create_delivery_attempt,
    create_notification_target,
    failed_delivery_count,
    mark_delivery_failed,
    mark_delivery_sent,
    mask_target_chat_id,
)
from tests.utils import session_scope


def _target(session):
    owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
    target = create_notification_target(
        session,
        actor=owner,
        name="Testing Sandbox",
        target_type="telegram_group",
        purpose="testing",
        telegram_chat_id="-100123456789",
    )
    return owner, target


def test_delivery_attempt_creation_and_audit() -> None:
    with session_scope() as session:
        owner, target = _target(session)

        attempt = create_delivery_attempt(
            session,
            target,
            event_type="notification.test",
            actor=owner,
            metadata={"token": "must-not-store", "source": "test"},
        )

        assert attempt.status == "pending"
        assert attempt.metadata_json["token"] == "[redacted]"
        assert session.query(NotificationDeliveryAttempt).count() == 1
        audit = session.query(AuditLog).filter_by(action="notification.delivery_attempted").one()
        assert audit.details["event_type"] == "notification.test"


def test_successful_delivery_record_emits_event() -> None:
    with session_scope() as session:
        owner, target = _target(session)
        attempt = create_delivery_attempt(session, target, event_type="briefing.generated", actor=owner)

        mark_delivery_sent(session, attempt, actor=owner)

        assert attempt.status == "sent"
        assert session.query(AuditLog).filter_by(action="notification.delivery_succeeded").count() == 1
        assert session.query(EventLog).filter_by(event_type="notification.delivery_succeeded").count() == 1


def test_failed_delivery_record_redacts_secret_like_errors() -> None:
    with session_scope() as session:
        owner, target = _target(session)
        attempt = create_delivery_attempt(session, target, event_type="briefing.generated", actor=owner)

        mark_delivery_failed(session, attempt, actor=owner, error_message="TELEGRAM_BOT_TOKEN=super-secret")

        assert attempt.status == "failed"
        assert "super-secret" not in (attempt.error_message or "")
        assert "TOKEN" not in (attempt.error_message or "")
        audit = session.query(AuditLog).filter_by(action="notification.delivery_failed").one()
        assert "super-secret" not in str(audit.details)
        assert session.query(EventLog).filter_by(event_type="notification.delivery_failed").count() == 1


def test_repeated_delivery_failures_create_recommendation() -> None:
    with session_scope() as session:
        owner, target = _target(session)
        for _ in range(3):
            attempt = create_delivery_attempt(session, target, event_type="briefing.generated", actor=owner)
            mark_delivery_failed(session, attempt, actor=owner, error_message="telegram_send_failed")

        recommendation = session.query(Recommendation).filter_by(
            recommendation_type="notification_delivery_failures",
            entity_type="notification_target",
            entity_id=str(target.id),
        ).one()

        assert recommendation.severity == "warning"
        assert recommendation.metadata_json["failed_count"] == 3


def test_notification_target_masking_and_detail_attempts() -> None:
    with session_scope() as session:
        owner, target = _target(session)
        attempt = create_delivery_attempt(session, target, event_type="notification.test", actor=owner)
        mark_delivery_sent(session, attempt, actor=owner)

        screen = render_notification_target_detail_page(session, target.id)

        assert mask_target_chat_id(target).startswith("-1")
        assert "-100123456789" not in screen.text
        assert "notification.test: sent" in screen.text


def test_production_status_screen_metrics() -> None:
    with session_scope() as session:
        owner, target = _target(session)
        record_heartbeat(session, service_name="api", status="healthy", metadata={"source": "test"})
        record_heartbeat(session, service_name="db", status="healthy", metadata={"source": "test"})
        record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "test"})
        attempt = create_delivery_attempt(session, target, event_type="notification.test", actor=owner)
        mark_delivery_failed(session, attempt, actor=owner, error_message="telegram_send_failed")

        summary = system_status_summary(session)
        screen = render_bot_status_page(session)
        details = render_bot_status_page(session, details=True)

        assert summary["failed_notification_count"] == 1
        assert failed_delivery_count(session) == 1
        assert "Status:" in screen.text
        assert "Recommended Action:" in screen.text
        assert "Environment:" in details.text
        assert "DB: healthy" in details.text
        assert "Redis: healthy" in details.text
        assert "Failed Notification Count: 1" in details.text
        assert "Last Delivery Attempt: notification.test / failed" in details.text


def test_railway_config_and_smoke_doc_presence() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "railway.json").exists()
    assert (root / "docs" / "production_smoke_test.md").exists()


def test_railway_config_does_not_override_worker_command() -> None:
    root = Path(__file__).resolve().parents[1]
    railway_config = json.loads((root / "railway.json").read_text())
    deploy_config = railway_config.get("deploy", {})

    assert "startCommand" not in deploy_config
    assert "healthcheckPath" not in deploy_config
