from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import render_coo_briefing_page, render_intelligence_quality_page
from app.core.config import settings
from app.models.button_issue import ButtonIssue
from app.models.decision_memory import DecisionMemory
from app.models.friction import FrictionItem
from app.services.auth import setup_owner_if_needed
from app.services.decision_engine import (
    Decision,
    decision_memory_key,
    generate_coo_briefing,
    generate_decisions,
    record_decision_memory_event,
)
from app.services.decision_quality import (
    DecisionQualityEngine,
    safe_decision_quality_report,
)
from app.services.help_brain import help_brain_answer
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=60, owner_telegram_id=60, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _callback_for_label(screen, label: str) -> str | None:
    for row in screen.reply_markup.inline_keyboard:
        for button in row:
            if button.text == label:
                return button.callback_data
    return None


def _thin_decision() -> Decision:
    return Decision(
        title="Check something",
        category="general",
        severity="needs_review",
        priority_rank=20,
        impact="Maybe useful.",
        risk="Unclear.",
        recommendation="Review details.",
        confidence="high",
        evidence_summary="Thin.",
        source_records=("QualityTest",),
        next_best_move="Review details.",
        can_wait=False,
        created_at=datetime.now(UTC),
        action_page="decision:details",
    )


def test_recommendation_scoring_framework_validates_required_dimensions() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decision = generate_decisions(session, actor=owner)[0]

        score = DecisionQualityEngine().score_decision_recommendation(decision)

        assert score.relevance_score > 0
        assert score.impact_score > 0
        assert score.confidence_score > 0
        assert score.evidence_score > 0
        assert score.actionability_score > 0
        assert 0 <= score.overall_recommendation_score <= 100
        assert score.recommendation_hash
        assert score.evidence_version


def test_bad_quality_score_downgrades_confidence_instead_of_inflating_it() -> None:
    score = DecisionQualityEngine().score_decision_recommendation(_thin_decision())

    assert score.adjusted_confidence == "medium"
    assert score.confidence_score < 60
    assert any("High confidence" in finding for finding in score.findings)


def test_priority_validation_keeps_recovery_above_platform_setup() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decisions = generate_decisions(session, actor=owner)

        assert decisions[0].category == "recovery"
        platform = next(decision for decision in decisions if decision.category == "platform_connection")
        assert platform.can_wait is True
        assert decisions[0].priority_rank > platform.priority_rank


def test_duplicate_stale_recommendation_suppression_requires_same_evidence_version() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decisions = generate_decisions(session, actor=owner)
        platform = next(decision for decision in decisions if decision.category == "platform_connection")

        record_decision_memory_event(session, decision=platform, action="dismissed", actor=owner)
        first_pass = DecisionQualityEngine().adjust_decisions(session, decisions, actor=owner)
        assert any(decision.category == "platform_connection" for decision in first_pass)

        second_pass = DecisionQualityEngine().adjust_decisions(session, decisions, actor=owner)
        assert not any(decision.category == "platform_connection" for decision in second_pass)


def test_critical_issue_persists_even_when_dismissed_and_duplicate() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decisions = generate_decisions(session, actor=owner)
        recovery = next(decision for decision in decisions if decision.category == "recovery")

        record_decision_memory_event(session, decision=recovery, action="dismissed", actor=owner)
        DecisionQualityEngine().adjust_decisions(session, decisions, actor=owner)
        adjusted = DecisionQualityEngine().adjust_decisions(session, decisions, actor=owner)

        assert any(decision.category == "recovery" for decision in adjusted)


def test_decision_quality_report_calculates_accuracy_and_learning_metrics() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decisions = generate_decisions(session, actor=owner)
        recovery = next(decision for decision in decisions if decision.category == "recovery")
        platform = next(decision for decision in decisions if decision.category == "platform_connection")

        record_decision_memory_event(session, decision=recovery, action="acted_on", actor=owner)
        record_decision_memory_event(session, decision=platform, action="dismissed", actor=owner)
        report = safe_decision_quality_report(session, decisions, actor=owner)

        assert report.available is True
        assert report.total_memories >= 2
        assert report.recommendation_accuracy > 0
        assert report.category_accuracy > 0
        assert report.confidence_accuracy > 0
        assert report.learning_status in {"healthy", "needs_review"}


def test_friction_severity_detects_repeated_help_back_and_button_issues() -> None:
    with session_scope() as session:
        session.add_all(
            [
                FrictionItem(screen="notification_center", issue="Repeated Help usage", severity="medium", fix_recommendation="Simplify Notification Center."),
                FrictionItem(screen="platforms", issue="Repeated Back usage loop", severity="medium", fix_recommendation="Clarify Back path."),
                ButtonIssue(
                    screen="platforms",
                    button_label="nav:platforms:raw",
                    callback_data="nav:platforms:raw",
                    issue_type="raw_internal_label",
                    severity="medium",
                    status="open",
                    evidence_summary="Raw callback label appeared on a simple screen.",
                    recommended_fix="Replace raw callback with a clear button label.",
                ),
            ]
        )
        session.flush()

        report = safe_decision_quality_report(session)

        assert report.friction.severity in {"medium", "high", "critical"}
        assert "friction signal" in report.friction.evidence


def test_decision_quality_engine_exception_falls_back_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("quality offline")

    monkeypatch.setattr(DecisionQualityEngine, "adjust_decisions", boom)
    with session_scope() as session:
        owner = _owner(session)

        decisions = generate_decisions(session, actor=owner)

        assert decisions
        assert decisions[0].category == "recovery"


def test_safe_quality_report_handles_audit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("audit offline")

    monkeypatch.setattr(DecisionQualityEngine, "audit", boom)
    with session_scope() as session:
        report = safe_decision_quality_report(session)

        assert report.available is False
        assert report.status == "needs_review"
        assert "unavailable" in report.findings[0].title.casefold()


def test_memory_lookup_failure_does_not_crash_briefing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("memory offline")

    monkeypatch.setattr("app.services.decision_engine.decision_memory_summary", boom)
    with session_scope() as session:
        owner = _owner(session)

        briefing = generate_coo_briefing(session, actor=owner)

        assert briefing.top_priority is not None
        assert any("unavailable" in line.casefold() for line in briefing.learning_summary)


def test_feature_flag_disables_quality_adjustments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "decision_quality_enabled", False)
    with session_scope() as session:
        owner = _owner(session)

        decisions = generate_decisions(session, actor=owner)

        assert decisions
        assert "recommendation_quality" not in (decisions[0].details or {})


def test_intelligence_quality_screen_and_routes_render_cleanly() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        screen = render_intelligence_quality_page(session, owner)
        routed = screen_for_page("intelligence:quality", principal, session=session, user=owner)
        details = screen_for_page("intelligence:quality:details", principal, session=session, user=owner)
        buttons = _buttons(screen)

        assert "Intelligence Quality" in screen.text
        assert "Decision Quality:" in screen.text
        assert "source_records" not in screen.text
        assert "decision_id" not in screen.text
        assert "Intelligence Quality" in routed.text
        assert "Quality Details:" in details.text
        assert any("Refresh" in button for button in buttons)
        assert "Back" in buttons
        assert "Main Menu" in buttons
        assert _callback_for_label(screen, "Back") == "nav:coo:briefing"
        assert _callback_for_label(screen, "Main Menu") == "nav:menu"


def test_intelligence_quality_back_returns_to_coo_parent() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        screen = screen_for_page("intelligence:quality", principal, session=session, user=owner)
        back_target = (_callback_for_label(screen, "Back") or "").removeprefix("nav:")
        parent = screen_for_page(back_target, principal, session=session, user=owner)

        assert back_target == "coo:briefing"
        assert "COO Briefing" in parent.text


def test_intelligence_quality_main_menu_still_returns_home() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        screen = screen_for_page("intelligence:quality", principal, session=session, user=owner)
        main_target = (_callback_for_label(screen, "Main Menu") or "").removeprefix("nav:")
        home = screen_for_page(main_target, principal, session=session, user=owner)

        assert main_target == "menu"
        assert "Fortuna OS" in home.text


def test_coo_briefing_details_include_quality_scores() -> None:
    with session_scope() as session:
        owner = _owner(session)

        details = render_coo_briefing_page(session, owner, details=True)

        assert "Intelligence Quality:" in details.text
        assert "Recommendation Accuracy:" in details.text


def test_observability_includes_intelligence_quality_without_secret_leakage() -> None:
    with session_scope() as session:
        _owner(session)

        summary = production_observability_summary(session)

        assert "decision_quality_status" in summary
        assert "decision_quality_score" in summary
        rendered = str(summary)
        assert "SECRET" not in rendered.upper()
        assert "TOKEN" not in rendered.upper()


def test_help_brain_explains_decision_quality_accuracy_and_confidence() -> None:
    with session_scope() as session:
        owner = _owner(session)

        quality = help_brain_answer(session, owner, question="What is Decision Quality?")
        recommendation = help_brain_answer(session, owner, question="What is Recommendation Accuracy?")
        confidence = help_brain_answer(session, owner, question="What is Confidence Accuracy?")

        assert "specific, evidence-backed" in quality.answer
        assert "later evidence" in recommendation.answer
        assert "weak evidence" in confidence.answer
        assert quality.next_action == "intelligence:quality"


def test_duplicate_suppression_failure_does_not_hide_critical_recommendation(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("suppression unavailable")

    monkeypatch.setattr(DecisionQualityEngine, "should_suppress_duplicate", boom)
    with session_scope() as session:
        owner = _owner(session)

        decisions = generate_decisions(session, actor=owner)

        assert decisions
        assert any(decision.category == "recovery" for decision in decisions)


def test_stale_recommendation_state_is_stored_as_quality_metadata() -> None:
    with session_scope() as session:
        owner = _owner(session)
        decisions = generate_decisions(session, actor=owner)
        decision = decisions[0]

        record_decision_memory_event(session, decision=decision, action="ignored", actor=owner)
        DecisionQualityEngine().adjust_decisions(session, decisions, actor=owner)
        memory = session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)))

        assert memory is not None
        assert memory.metadata_json.get("quality_evidence_version")
        assert memory.metadata_json.get("recommendation_hash")
