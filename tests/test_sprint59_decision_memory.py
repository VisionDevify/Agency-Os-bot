from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_coo_briefing_page,
    render_decision_details_page,
    render_decision_feedback_page,
    render_decision_memory_page,
    render_today_priorities_page,
)
from app.models.decision_memory import DecisionMemory
from app.models.event_log import EventLog
from app.models.learning import LearningEvent
from app.models.recovery import BackupRun, RestoreTestRun
from app.services.auth import setup_owner_if_needed
from app.services.bot_instances import record_polling_conflict
from app.services.decision_engine import (
    apply_decision_resolvers,
    decision_memory_key,
    generate_coo_briefing,
    generate_decisions,
    record_decision_interaction,
    record_decision_memory_event,
)
from app.services.help_brain import help_brain_answer
from app.services.heartbeats import record_heartbeat
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=59, owner_telegram_id=59, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def test_decision_shown_creates_memory() -> None:
    with session_scope() as session:
        owner = _owner(session)

        briefing = generate_coo_briefing(session, actor=owner)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.category == "recovery"))

        assert briefing.top_priority is not None
        assert memory is not None
        assert memory.outcome == "shown"
        assert memory.shown_at is not None
        assert memory.evidence_summary


def test_opening_decision_updates_opened_at_and_event() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]

        record_decision_interaction(session, decision=decision, action="opened", actor=owner)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)))
        event = session.scalar(select(EventLog).where(EventLog.event_type == "decision.opened"))

        assert memory is not None
        assert memory.opened_at is not None
        assert memory.lifecycle_status == "opened"
        assert event is not None


def test_feedback_buttons_record_helpful_dismiss_and_remind_later() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]

        record_decision_memory_event(session, decision=decision, action="helpful", actor=owner)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)))
        assert memory is not None
        assert memory.usefulness_score > 50
        assert memory.owner_feedback == "Marked helpful."

        record_decision_memory_event(session, decision=decision, action="remind_later", actor=owner)
        assert memory.lifecycle_status == "waiting_for_evidence"

        record_decision_memory_event(session, decision=decision, action="dismissed", actor=owner)
        assert memory.outcome == "dismissed"
        assert memory.lifecycle_status == "dismissed"


def test_ignored_does_not_equal_failed() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]

        record_decision_interaction(session, decision=decision, action="ignored", actor=owner)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)))

        assert memory is not None
        assert memory.outcome == "ignored"
        assert memory.outcome != "failed"
        assert memory.lifecycle_status == "active"


def test_resolved_requires_evidence_for_recovery() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]
        record_decision_interaction(session, decision=decision, action="opened", actor=owner)

        apply_decision_resolvers(session)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)))

        assert memory is not None
        assert memory.lifecycle_status != "resolved"


def test_acted_on_recovery_evidence_improves_usefulness_but_waits_for_restore() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]
        record_decision_interaction(session, decision=decision, action="opened", actor=owner)
        backup = BackupRun(
            run_identifier="s59-backup",
            backup_type="manual",
            status="succeeded",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            encrypted=True,
            checksum="abc123",
            artifact_verified=True,
            external_storage_used=True,
            storage_target="backblaze_b2",
        )
        session.add(backup)
        session.flush()
        session.add(
            RestoreTestRun(
                run_identifier="s59-restore",
                backup_run_id=backup.id,
                status="verified_only",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                checksum_verified=True,
                decrypt_verified=True,
                full_restore_performed=False,
            )
        )
        session.flush()

        apply_decision_resolvers(session)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)))

        assert memory is not None
        assert memory.outcome == "acted_on"
        assert memory.lifecycle_status == "waiting_for_evidence"
        assert memory.usefulness_score > 50


def test_dismissed_platform_login_lowers_urgency_but_critical_recovery_stays_visible() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decisions = generate_decisions(session, actor=owner)
        platform = next(decision for decision in decisions if decision.category == "platform_connection")
        recovery = next(decision for decision in decisions if decision.category == "recovery")

        record_decision_memory_event(session, decision=platform, action="dismissed", actor=owner)
        record_decision_memory_event(session, decision=recovery, action="dismissed", actor=owner)
        refreshed = generate_decisions(session, actor=owner)

        assert refreshed[0].category == "recovery"
        assert any(decision.category == "platform_connection" and decision.can_wait for decision in refreshed)


def test_resolved_polling_conflict_hides_from_primary_briefing_when_evidence_clears() -> None:
    with session_scope() as session:
        owner = _owner(session)
        record_polling_conflict(
            session,
            instance_id="worker-a",
            reason="Another process is using the same Telegram bot token.",
            source="test",
            conflict_source="railway",
        )
        conflict = next(decision for decision in generate_decisions(session, actor=owner) if decision.category == "telegram_bot")
        record_decision_interaction(session, decision=conflict, action="opened", actor=owner)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(conflict)))
        assert memory is not None

        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={"polling_conflict_active": "false", "latest_polling_conflict_reason": "None"},
        )
        apply_decision_resolvers(session)
        session.flush()
        screen = render_coo_briefing_page(session, owner)

        assert "Telegram polling conflict is active" not in screen.text


def test_waiting_for_evidence_appears_when_action_unverified() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]

        record_decision_memory_event(session, decision=decision, action="remind_later", actor=owner)
        screen = render_decision_memory_page(session, owner, status_filter="waiting")

        assert "waiting for evidence" in screen.text.lower()
        assert "Recovery is not fully protected yet" in screen.text


def test_coo_and_today_use_decision_memory() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]
        record_decision_memory_event(session, decision=decision, action="acted_on", actor=owner)

        coo = render_coo_briefing_page(session, owner)
        today = render_today_priorities_page(session, owner)

        assert "What Fortuna Learned" in coo.text
        assert "What Fortuna Learned" in today.text
        assert "Recovery recommendations were acted on" in coo.text


def test_decision_details_and_memory_screens_render_without_raw_ids() -> None:
    with session_scope() as session:
        owner = _owner(session)

        details = render_decision_details_page(session, owner)
        feedback = render_decision_feedback_page(session, "helpful", owner)
        memory = render_decision_memory_page(session, owner)
        buttons = _buttons(details)

        assert "Decision Details" in details.text
        assert "Memory:" in details.text
        assert "Decision Feedback" in feedback.text
        assert "Decision Memory" in memory.text
        assert "decision_id" not in details.text
        assert "source_records" not in details.text
        assert any("Helpful" in button for button in buttons)
        assert "Back" in buttons
        assert "Main Menu" in buttons


def test_decision_memory_routes_have_back_home() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        screen = screen_for_page("decision:memory", principal, session=session, user=owner)
        buttons = _buttons(screen)

        assert "Decision Memory" in screen.text
        assert "Back" in buttons
        assert "Main Menu" in buttons


def test_help_brain_explains_decision_memory_feedback_and_safety() -> None:
    with session_scope() as session:
        owner = _owner(session)

        memory = help_brain_answer(session, owner, question="What is Decision Memory?")
        helpful = help_brain_answer(session, owner, question="What does Helpful do?")
        dismiss = help_brain_answer(session, owner, question="What does Dismiss do?")

        assert "shown, opened, acted on" in memory.answer
        assert "feedback signals" in helpful.answer
        assert "never hide critical safety issues" in dismiss.answer
