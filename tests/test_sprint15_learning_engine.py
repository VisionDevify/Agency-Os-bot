from datetime import UTC, datetime, timedelta

from app.bot.navigation import screen_for_page
from app.models.automation import AutomationRun
from app.models.learning import ConfidenceRecord, LearningEvent, OutcomeMemory, Playbook, PlaybookRun
from app.models.recommendation import Recommendation
from app.services.auth import setup_owner_if_needed
from app.services.automations import create_automation_rule
from app.services.incidents import create_incident, resolve_incident
from app.services.learning import (
    automation_learning_summary,
    capture_automation_run,
    capture_proxy_outcome,
    create_playbook_run,
    create_learning_event,
    executive_memory_briefing,
    finish_playbook_run,
    learning_center_metrics,
    record_feedback,
    recommend_playbooks,
    seed_default_playbooks,
)
from app.services.notifications import create_delivery_attempt, create_notification_target, mark_delivery_failed
from app.services.opportunities import create_manual_opportunity, record_opportunity_result, score_opportunity
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_proxy
from app.services.tasks import complete_task, create_task, record_overdue_tasks
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def test_learning_event_creation_redacts_sensitive_metadata_and_updates_memory() -> None:
    with session_scope() as session:
        owner = _owner(session)

        event = create_learning_event(
            session,
            actor=owner,
            event_type="system.test",
            source_type="system",
            outcome="success",
            severity="info",
            summary="Safe learning event.",
            details={"token": "secret", "safe": "visible"},
        )

        memory = session.query(OutcomeMemory).filter_by(memory_key="system_health:system.test").one()
        assert event.details_json["token"] == "[redacted]"
        assert event.details_json["safe"] == "visible"
        assert memory.occurrences == 1
        assert memory.success_rate == 100


def test_learning_capture_from_task_completed_and_overdue() -> None:
    with session_scope() as session:
        owner = _owner(session)
        task = create_task(session, actor=owner, title="Finish report")
        overdue = create_task(
            session,
            actor=owner,
            title="Overdue report",
            due_at=datetime.now(UTC) - timedelta(hours=2),
        )

        complete_task(session, task, actor=owner)
        record_overdue_tasks(session, actor=owner)

        assert session.query(LearningEvent).filter_by(event_type="task.completed").count() == 1
        assert session.query(LearningEvent).filter_by(event_type="task.overdue_detected").count() == 1
        memory = session.query(OutcomeMemory).filter_by(memory_key=f"task_overdue:task:{overdue.id}").one()
        assert memory.failure_count == 1


def test_learning_capture_from_incident_resolved() -> None:
    with session_scope() as session:
        owner = _owner(session)
        incident = create_incident(session, actor=owner, title="Critical repair", severity="critical")

        resolve_incident(session, incident, actor=owner, resolution_notes="Recovered.")

        event = session.query(LearningEvent).filter_by(event_type="incident.resolved").one()
        assert event.outcome == "success"
        assert session.query(OutcomeMemory).filter_by(memory_key=f"incident_pattern:incident:{incident.id}").count() == 1


def test_learning_capture_from_proxy_repair_success_and_failure() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.learning.local",
            port=8111,
            base_username="base",
            password="secret",
        )

        capture_proxy_outcome(session, proxy, actor=owner, event_type="proxy.repair.succeeded", succeeded=True)
        capture_proxy_outcome(session, proxy, actor=owner, event_type="proxy.repair.failed", succeeded=False)

        memory = session.query(OutcomeMemory).filter_by(memory_key=f"proxy_failure:proxy:{proxy.id}").one()
        assert memory.occurrences == 2
        assert memory.success_count == 1
        assert memory.failure_count == 1


def test_playbook_seeding_recommendation_run_and_confidence_change() -> None:
    with session_scope() as session:
        owner = _owner(session)

        playbooks = seed_default_playbooks(session, actor=owner)
        recommended = recommend_playbooks(session, source_type="proxy", event_type="proxy.repair.failed", severity="critical")
        run = create_playbook_run(session, playbooks[0], actor=owner, status="running", source_type="proxy", source_id="1")
        finish_playbook_run(
            session,
            run,
            actor=owner,
            status="succeeded",
            result_summary="Recovered with playbook.",
        )

        assert len(playbooks) == 7
        assert recommended[0][0].category == "proxy"
        assert run.status == "succeeded"
        assert session.query(ConfidenceRecord).filter_by(subject_type="playbook").count() >= 1


def test_automation_outcome_learning_creates_memory_and_review_recommendation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        rule = create_automation_rule(
            session,
            actor=owner,
            name="Learning Rule",
            automation_type="learning_rule",
            actions=[{"type": "write_event_log"}],
        )
        run = AutomationRun(
            automation_rule_id=rule.id,
            status="failed",
            started_by_user_id=owner.id,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            error_message="safe failure",
            rollback_available=False,
            rollback_status="not_needed",
        )
        session.add(run)
        session.flush()

        capture_automation_run(session, run, actor=owner)

        assert session.query(OutcomeMemory).filter_by(memory_key=f"automation_result:automation_rule:{rule.id}").count() == 1
        assert session.query(Recommendation).filter_by(recommendation_type="automation_learning_pause_review").count() == 1
        assert automation_learning_summary(session)["failed_runs"] == 1


def test_opportunity_result_learning_adjusts_score() -> None:
    with session_scope() as session:
        owner = _owner(session)
        opportunity = create_manual_opportunity(
            session,
            actor=owner,
            title="Manual learning opportunity",
            niche="fitness",
            suggested_angle="human approved angle",
        )
        score_opportunity(session, opportunity, actor=owner)
        previous_score = opportunity.score

        record_opportunity_result(session, opportunity, actor=owner, status="posted", clicks=20, conversions=2)

        assert opportunity.score > previous_score
        assert session.query(OutcomeMemory).filter_by(memory_key=f"opportunity_result:opportunity:{opportunity.id}").count() == 1


def test_recommendation_feedback_creates_learning_and_confidence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        recommendation = Recommendation(
            recommendation_type="manual_review",
            title="Review something",
            description="Operator feedback test.",
            severity="warning",
            status="open",
            metadata_json={"confidence_score": 70},
        )
        session.add(recommendation)
        session.flush()

        record_feedback(session, actor=owner, subject_type="recommendation", subject_id=recommendation.id, feedback="useful")
        record_feedback(session, actor=owner, subject_type="recommendation", subject_id=recommendation.id, feedback="not_useful")

        assert session.query(LearningEvent).filter(LearningEvent.event_type.like("recommendation.feedback.%")).count() == 2
        assert session.query(ConfidenceRecord).filter_by(subject_type="recommendation").count() == 2
        assert recommendation.metadata_json["last_feedback"] == "not_useful"


def test_notification_failure_learning_records_safe_memory() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target = create_notification_target(
            session,
            actor=owner,
            name="Testing Sandbox",
            target_type="telegram_group",
            purpose="testing",
            telegram_chat_id="-100123456789",
        )
        attempt = create_delivery_attempt(session, target, event_type="digest.sent", actor=owner)

        mark_delivery_failed(session, attempt, actor=owner, error_message="token=secret")

        event = session.query(LearningEvent).filter_by(event_type="notification.delivery_failed").one()
        assert "secret" not in str(event.details_json)
        assert session.query(OutcomeMemory).filter_by(memory_key=f"notification_failure:notification_target:{target.id}").count() == 1


def test_executive_memory_briefing_and_learning_center_counts() -> None:
    with session_scope() as session:
        owner = _owner(session)
        seed_default_playbooks(session, actor=owner)
        create_learning_event(
            session,
            actor=owner,
            event_type="proxy.repair.succeeded",
            source_type="proxy",
            source_id="1",
            entity_type="proxy",
            entity_id="1",
            outcome="success",
            summary="Proxy recovered.",
        )

        metrics = learning_center_metrics(session)
        briefing = executive_memory_briefing(session)

        assert metrics["total_learning_events"] == 1
        assert metrics["active_playbooks"] == 7
        assert "confidence" in briefing["summary"]


def test_learning_center_telegram_callbacks_do_not_crash() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=1, is_owner=True, role=RoleName.OWNER)

        for page in (
            "intelligence:learning",
            "intelligence:learning:playbooks",
            "intelligence:learning:outcome_memory",
            "intelligence:learning:confidence",
            "intelligence:learning:automation",
            "intelligence:learning:opportunity",
            "intelligence:learning:briefing",
        ):
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text

        playbook = session.query(Playbook).first()
        assert playbook is not None
        detail = screen_for_page(f"playbook:{playbook.id}", principal, session=session, user=owner)
        assert "Playbook" in detail.text
