from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.bot.navigation import screen_for_page
from app.bot.screens import render_main_menu, render_proxy_detail_page
from app.core.config import settings
from app.main import app
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.incident import IncidentTimeline
from app.models.intelligence import IntelligenceRun, IntelligenceSignal, IssuePattern, TrendSnapshot, WorkloadSnapshot
from app.models.learning import ConfidenceRecord, LearningEvent, OutcomeMemory
from app.models.recommendation import Recommendation
from app.services.audit import sanitize_details
from app.services.auth import setup_owner_if_needed
from app.services.events import emit_event
from app.services.heartbeats import record_heartbeat
from app.services.incidents import add_timeline_entry, create_incident
from app.services.intelligence import run_full_intelligence_scan
from app.services.learning import record_feedback
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_proxy
from app.services.recommendations import upsert_recommendation
from app.services.tasks import complete_task, create_task
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def test_recursive_sanitization_redacts_nested_secret_and_chat_metadata() -> None:
    sanitized = sanitize_details(
        {
            "safe": "ok",
            "token": "secret-token",
            "nested": {
                "password": "secret-password",
                "telegram_chat_id": "-100123456789",
                "items": [{"owner_telegram_id": "12345"}, {"safe": True}],
            },
        }
    )

    assert sanitized["safe"] == "ok"
    assert sanitized["token"] == "[redacted]"
    assert sanitized["nested"]["password"] == "[redacted]"
    assert sanitized["nested"]["telegram_chat_id"] == "[redacted]"
    assert sanitized["nested"]["items"][0]["owner_telegram_id"] == "[redacted]"
    assert sanitized["nested"]["items"][1]["safe"] is True


def test_metadata_sinks_redact_nested_sensitive_values() -> None:
    with session_scope() as session:
        owner = _owner(session)
        emit_event(
            session,
            actor=owner,
            event_name="audit.safety_probe",
            resource_type="system",
            payload={"nested": {"token": "secret-token", "chat_id": "-100123"}},
        )
        recommendation = upsert_recommendation(
            session,
            actor=owner,
            recommendation_type="safety_probe",
            title="Safety Probe",
            description="Checks recursive metadata redaction.",
            severity="info",
            metadata={"nested": {"password": "secret-password", "owner_telegram_id": "12345"}},
        )
        record_heartbeat(
            session,
            service_name="api",
            status="healthy",
            metadata={"nested": {"telegram_chat_id": "-100123456789"}},
            actor=owner,
        )
        incident = create_incident(
            session,
            actor=owner,
            title="Timeline Safety Probe",
            severity="info",
            source_type="manual",
        )
        add_timeline_entry(
            session,
            incident,
            actor=owner,
            event_type="incident.note",
            message="Safe timeline note.",
            metadata={"nested": {"token": "secret-token"}},
        )

        audit = session.query(AuditLog).filter_by(action="audit.safety_probe").one()
        event = session.query(EventLog).filter_by(event_type="audit.safety_probe").one()
        timeline = session.query(IncidentTimeline).filter_by(event_type="incident.note").one()

        assert audit.details["nested"]["token"] == "[redacted]"
        assert event.metadata_json["nested"]["chat_id"] == "[redacted]"
        assert recommendation.metadata_json["nested"]["password"] == "[redacted]"
        assert recommendation.metadata_json["nested"]["owner_telegram_id"] == "[redacted]"
        assert timeline.metadata_json["nested"]["token"] == "[redacted]"


def test_fortuna_branding_is_used_for_app_and_core_user_facing_docs() -> None:
    assert settings.app_display_name == "Fortuna OS"
    assert app.title == "Fortuna OS"
    assert render_main_menu().text.startswith("Fortuna OS")

    production_doc = Path("docs/production_operations.md").read_text(encoding="utf-8")
    invite_doc = Path("docs/team_invite_packet.md").read_text(encoding="utf-8")

    assert "Fortuna OS - HQ" in production_doc
    assert "Fortuna OS invite for Chatter" in invite_doc
    legacy_brand = "Agency" + " OS"
    assert f"{legacy_brand} - HQ" not in production_doc
    assert f"{legacy_brand} invite" not in invite_doc


def test_task_completion_data_flow_reaches_event_learning_memory_and_confidence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        task = create_task(
            session,
            actor=owner,
            title="Verify data flow",
            assigned_to=owner,
            due_at=datetime.now(UTC) + timedelta(days=1),
        )
        complete_task(session, task, actor=owner)
        recommendation = upsert_recommendation(
            session,
            actor=owner,
            recommendation_type="audit_flow_probe",
            title="Audit Flow Probe",
            description="Confirms recommendation feedback reaches learning.",
            severity="info",
        )
        record_feedback(
            session,
            actor=owner,
            subject_type="recommendation",
            subject_id=recommendation.id,
            feedback="useful",
        )

        assert session.query(AuditLog).filter_by(action="task.completed", resource_id=str(task.id)).count() == 1
        assert session.query(EventLog).filter_by(event_type="task.completed", entity_id=str(task.id)).count() == 1
        assert session.query(LearningEvent).filter_by(event_type="task.completed").count() == 1
        assert session.query(OutcomeMemory).filter_by(memory_key=f"task_overdue:task:{task.id}").count() == 1
        assert session.query(ConfidenceRecord).filter_by(subject_type="recommendation").count() == 1


def test_full_intelligence_scan_persists_results_from_live_operational_records() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="audit-provider",
            host="audit-proxy.local",
            port=1080,
            base_username="audit-user",
            password="secret",
        )
        for index in range(3):
            emit_event(
                session,
                actor=owner,
                event_name="proxy.repair.failed",
                resource_type="proxy",
                resource_id=str(proxy.id),
                status="failed",
                payload={"failure_index": index, "password": "must-redact"},
            )

        runs = run_full_intelligence_scan(session, actor=owner)

        assert len(runs) >= 5
        assert session.query(IntelligenceRun).count() == len(runs)
        assert session.query(IntelligenceSignal).filter_by(signal_type="recurring_proxy_failures").count() == 1
        assert session.query(IssuePattern).filter_by(pattern_type="recurring_proxy_failures").count() == 1
        assert session.query(TrendSnapshot).count() > 0
        assert session.query(WorkloadSnapshot).count() > 0
        assert session.query(Recommendation).filter_by(recommendation_type="replace_rotate_proxy").count() == 1
        assert session.query(EventLog).filter_by(event_type="intelligence_run.succeeded").count() == len(runs)
        assert "must-redact" not in str(session.query(EventLog).all())


def test_proxy_screen_and_core_callbacks_are_clean_and_do_not_show_raw_output() -> None:
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
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        proxy_screen = render_proxy_detail_page(session, proxy.id)
        assert "super-secret" not in proxy_screen.text
        assert "encrypted_password" not in proxy_screen.text
        assert "{" not in proxy_screen.text
        assert "}" not in proxy_screen.text

        for page in (
            "coo:top5",
            "coo:briefing",
            "coo:readiness",
            "manager_queue",
            "my_work",
            "intelligence:learning",
            "automations:health",
            "agency_activation",
            "fortuna_action_log",
        ):
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text
            assert "Traceback" not in screen.text
            assert "encrypted_password" not in screen.text
            assert "super-secret" not in screen.text
