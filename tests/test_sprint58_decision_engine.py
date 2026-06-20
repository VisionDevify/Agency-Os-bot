from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_coo_briefing_page,
    render_decision_top_priority_page,
    render_recommendations_page,
    render_today_priorities_page,
)
from app.core.config import settings
from app.models.button_issue import ButtonIssue
from app.models.learning import LearningEvent
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.services.auth import setup_owner_if_needed
from app.services.bot_instances import record_polling_conflict
from app.services.decision_engine import (
    generate_coo_briefing,
    generate_decisions,
    record_decision_interaction,
)
from app.services.help_brain import help_brain_answer
from app.services.heartbeats import record_heartbeat
from app.services.notifications import create_delivery_attempt, create_notification_target, mark_delivery_failed
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=58, owner_telegram_id=58, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _production_env(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://:password@example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setattr(settings, "git_commit", "sprint58")


def _healthy_core_heartbeats(session) -> None:
    record_heartbeat(session, service_name="api", status="healthy", metadata={"source": "test"})
    record_heartbeat(session, service_name="db", status="healthy", metadata={"source": "test", "backend": "postgresql"})
    record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "test"})
    record_heartbeat(session, service_name="railway_deployment", status="healthy", metadata={"source": "test"})


def test_critical_recovery_outranks_platform_not_connected() -> None:
    with session_scope() as session:
        owner = _owner(session)

        decisions = generate_decisions(session, actor=owner)

        assert decisions[0].category == "recovery"
        assert decisions[0].can_wait is False
        assert decisions[0].confidence == "high"
        assert decisions[0].evidence_summary
        assert any(decision.category == "platform_connection" and decision.can_wait for decision in decisions)


def test_polling_conflict_ranks_above_informational_notification(monkeypatch) -> None:
    _production_env(monkeypatch)
    with session_scope() as session:
        owner = _owner(session)
        _healthy_core_heartbeats(session)
        record_polling_conflict(
            session,
            instance_id="worker-secret-instance",
            reason="Another process is using the same Telegram bot token.",
            source="test",
            conflict_source="railway",
            polling_lock_owner="old-worker",
        )

        decisions = generate_decisions(session, actor=owner)
        telegram = next(decision for decision in decisions if decision.category == "telegram_bot")
        notification = next(decision for decision in decisions if decision.category == "notification")

        assert telegram.priority_rank > notification.priority_rank
        assert telegram.severity == "critical"
        assert "duplicate poller" in telegram.next_best_move.lower()


def test_notification_failure_ranks_higher_than_platform_can_wait() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target: NotificationTarget = create_notification_target(
            session,
            actor=owner,
            name="Fortuna Alerts",
            target_type="telegram_group",
            purpose="alerts",
            telegram_chat_id="-100123456789",
        )
        for _ in range(3):
            attempt = create_delivery_attempt(session, target, event_type="critical.alert", actor=owner)
            mark_delivery_failed(session, attempt, actor=owner, error_message="send_failed")

        decisions = generate_decisions(session, actor=owner)
        notification = next(decision for decision in decisions if decision.category == "notification")
        platform_wait = next(decision for decision in decisions if decision.category == "platform_connection" and decision.can_wait)

        assert notification.priority_rank > platform_wait.priority_rank
        assert notification.can_wait is False


def test_decisions_require_evidence_and_stable_confidence() -> None:
    with session_scope() as session:
        owner = _owner(session)

        decisions = generate_decisions(session, actor=owner)

        assert decisions
        assert all(decision.evidence_summary for decision in decisions)
        assert all(decision.source_records for decision in decisions)
        assert all(decision.confidence in {"high", "medium", "low"} for decision in decisions)
        assert [decision.priority_rank for decision in decisions] == sorted(
            [decision.priority_rank for decision in decisions],
            reverse=True,
        )


def test_coo_briefing_is_decision_first_and_not_false_healthy() -> None:
    with session_scope() as session:
        owner = _owner(session)

        briefing = generate_coo_briefing(session, actor=owner)
        screen = render_coo_briefing_page(session, owner)

        assert briefing.top_priority is not None
        assert briefing.top_priority.category == "recovery"
        assert briefing.overall_status == "critical"
        assert "Top Priority" in screen.text
        assert "Recovery is not fully protected yet" in screen.text
        assert "Can Wait" in screen.text
        assert "Everything is running" not in screen.text
        assert "source_records" not in screen.text


def test_coo_briefing_refresh_fallback_is_honest(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        generate_coo_briefing(session, actor=owner)

        def fail_refresh(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("app.services.decision_engine.generate_decisions", fail_refresh)

        fallback = generate_coo_briefing(session, actor=owner)

        assert fallback.overall_status == "needs_review"
        assert fallback.top_priority is not None
        assert "may be stale" in fallback.top_priority.risk
        assert "last known briefing" in fallback.top_priority.evidence_summary.lower()


def test_today_view_uses_one_next_move_and_suppresses_noise() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            ButtonIssue(
                screen="Notification Center",
                button_label="Help",
                callback_data="nav:help",
                issue_type="dead_end",
                severity="medium",
                status="open",
                detected_at=datetime.now(UTC),
                evidence_summary="Help path loops.",
                recommended_fix="Preserve return context.",
            )
        )
        session.flush()

        screen = render_today_priorities_page(session, owner)

        assert "What Matters Today" in screen.text
        assert "Recommended Next Action" in screen.text
        assert screen.text.count("Recommended Next Action") == 1
        assert "Button Health" in screen.text
        assert "Platform logins can wait" in screen.text
        assert "not_connected" not in screen.text


def test_recommendations_include_impact_confidence_and_evidence() -> None:
    with session_scope() as session:
        owner = _owner(session)

        screen = render_recommendations_page(session, owner)

        assert "Impact" in screen.text
        assert "Confidence" in screen.text
        assert "Evidence" in screen.text
        assert "No verified backup" in screen.text
        assert session.scalar(select(Recommendation).where(Recommendation.recommendation_type == "decision_recovery")) is not None


def test_decision_learning_events_are_created_when_opened_and_recorded() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screen = render_decision_top_priority_page(session, owner)
        decision = generate_decisions(session, actor=owner)[0]
        record_decision_interaction(session, decision=decision, action="ignored", actor=owner)
        record_decision_interaction(session, decision=decision, action="acted_on", actor=owner)

        events = session.scalars(select(LearningEvent).where(LearningEvent.source_type == "system")).all()

        assert "Top Priority" in screen.text
        assert any(event.event_type == "decision.opened" for event in events)
        assert any(event.event_type == "decision.ignored" for event in events)
        assert any(event.event_type == "decision.acted_on" for event in events)


def test_decision_routes_have_back_home_and_emoji_buttons() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        top = screen_for_page("decision:top", principal, session=session, user=owner)
        details = screen_for_page("decision:details", principal, session=session, user=owner)
        buttons = _buttons(top)

        assert "🎯 Top Priority" in top.text
        assert "Decision Details" in details.text
        assert "🔎 Decision Details" in buttons
        assert "Back" in buttons
        assert "Main Menu" in buttons


def test_help_brain_explains_coo_decisions() -> None:
    with session_scope() as session:
        owner = _owner(session)

        briefing = help_brain_answer(session, owner, question="What is COO Briefing?")
        priorities = help_brain_answer(session, owner, question="How does Fortuna decide priorities?")
        recovery = help_brain_answer(session, owner, question="Why is Recovery top priority?")
        wait = help_brain_answer(session, owner, question="Why can platform connections wait?")
        confidence = help_brain_answer(session, owner, question="What does confidence mean?")
        automatic = help_brain_answer(session, owner, question="Can Fortuna act automatically?")

        assert "one top priority" in briefing.answer
        assert "evidence, urgency, risk" in priorities.answer
        assert "backup or restore evidence" in recovery.answer
        assert "Not connected yet is a setup state" in wait.answer
        assert "how strong Fortuna's evidence is" in confidence.answer
        assert "humans still decide" in automatic.answer
