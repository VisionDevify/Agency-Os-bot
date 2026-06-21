from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_ai_brain_page,
    render_ai_critic_status_page,
    render_ai_evidence_summary_page,
    render_ai_settings_page,
)
from app.models.ai import AIAuditLog
from app.models.evidence import EvidenceRecord
from app.models.recovery import BackupRun, RestoreTestRun
from app.services.ai import (
    AIGroundedOutput,
    FortunaAIBrain,
    FortunaAICritic,
    ai_configuration_status,
    ai_observability_summary,
    generate_ai_search_summary,
)
from app.services.ai.providers import AIProviderOptions, AIProviderResponse, AIProviderStatus, AIProviderTimeout
from app.services.auth import setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


@dataclass
class FakeAIProvider:
    response_text: str | None = None
    error: Exception | None = None

    def get_provider_status(self) -> AIProviderStatus:
        return AIProviderStatus(
            provider="openai",
            enabled=True,
            configured=True,
            status="configured",
            reason="Fake provider configured.",
            next_action="Use AI Brain.",
            model="gpt-5.4-mini",
        )

    validate_configuration = get_provider_status

    def generate_reasoning(self, prompt: str, context: dict, options: AIProviderOptions) -> AIProviderResponse:
        if self.error is not None:
            raise self.error
        text = self.response_text or (
            '{"conclusion":"Recovery still needs full restore evidence.",'
            '"evidence_used":["unit-test"],'
            '"reasoning_summary":"The supplied evidence shows verified backup context but not full restore proof.",'
            '"confidence":"medium",'
            '"limitations":["Evidence remains the source of truth."],'
            '"next_best_move":"Review Recovery Center.",'
            '"safety_flags":[]}'
        )
        return AIProviderResponse(text=text, model=options.model, usage={"input_tokens": 10, "output_tokens": 10})

    summarize_evidence = generate_reasoning
    critique_output = generate_reasoning


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=65, owner_telegram_id=65, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _context() -> dict:
    return {
        "use_case": "decision_details",
        "recovery": {"status": "needs_review"},
        "bot_status": {"polling_conflict_active": False},
        "evidence_records": [{"source": "unit-test", "summary": "Verified backup exists; full restore is missing."}],
        "decisions": [],
        "recommendations": [],
        "search_results": [],
    }


def test_missing_openai_key_returns_not_configured(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with session_scope() as session:
        status = ai_configuration_status(session)
        owner = _owner(session)
        screen = render_ai_brain_page(session, owner, details=True)

        assert status["status"] == "not_configured"
        assert "OPENAI_API_KEY" in screen.text
        assert "Not configured" in screen.text
        assert "sk-" not in screen.text


def test_ai_provider_success_creates_grounded_audit(monkeypatch) -> None:
    monkeypatch.setenv("AI_DAILY_LIMIT", "25")
    with session_scope() as session:
        owner = _owner(session)
        result = FortunaAIBrain(provider=FakeAIProvider()).reason(
            session,
            use_case="decision_details",
            prompt="Explain the decision.",
            actor=owner,
            context=_context(),
        )

        audit = session.get(AIAuditLog, result.audit_log_id)
        assert result.status == "succeeded"
        assert result.fallback_used is False
        assert result.output.confidence == "medium"
        assert audit is not None
        assert audit.status == "succeeded"
        assert audit.evidence_count >= 1


def test_provider_timeout_falls_back_safely(monkeypatch) -> None:
    monkeypatch.setenv("AI_DAILY_LIMIT", "25")
    with session_scope() as session:
        result = FortunaAIBrain(provider=FakeAIProvider(error=AIProviderTimeout("timeout"))).reason(
            session,
            use_case="coo_briefing",
            prompt="Explain.",
            context=_context(),
        )

        assert result.status == "timeout"
        assert result.fallback_used is True
        assert "timeout" in result.output.limitations[0].casefold()


def test_empty_context_blocks_decision_ai() -> None:
    with session_scope() as session:
        result = FortunaAIBrain(provider=FakeAIProvider()).reason(
            session,
            use_case="decision_details",
            prompt="Explain.",
            context={"decisions": [], "evidence_records": [], "search_results": [], "recommendations": []},
        )

        assert result.status == "fallback_used"
        assert result.safe_error_summary == "No evidence context."


def test_critic_blocks_secret_leak_compliance_and_fake_health() -> None:
    critic = FortunaAICritic()
    base = _context()
    outputs = [
        AIGroundedOutput("Use sk-secret-token-value", ("unit-test",), "Secret leaked.", "medium", ("Bad.",), "Stop."),
        AIGroundedOutput("Auto-follow creators.", ("unit-test",), "Auto-follow them.", "medium", ("Bad.",), "Auto-follow."),
        AIGroundedOutput("Recovery is healthy.", ("unit-test",), "Recovery is protected.", "medium", ("Bad.",), "Relax."),
        AIGroundedOutput("Good idea.", ("made-up-source",), "Unsupported.", "medium", ("Bad.",), "Trust it."),
    ]

    for output in outputs:
        status, flags, _ = critic.critique(output, base)
        assert status == "blocked"
        assert flags


def test_critic_downgrades_exaggerated_confidence() -> None:
    output = AIGroundedOutput(
        "Review recovery.",
        ("unit-test",),
        "One evidence record supports this.",
        "high",
        ("Limited evidence.",),
        "Open Recovery Center.",
    )

    status, flags, corrected = FortunaAICritic().critique(output, _context())

    assert status == "downgraded"
    assert "exaggerated_confidence" in flags
    assert corrected.confidence == "medium"


def test_ai_screens_render_without_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-not-real")
    with session_scope() as session:
        owner = _owner(session)
        for screen in (
            render_ai_brain_page(session, owner),
            render_ai_settings_page(session, owner),
            render_ai_critic_status_page(session, owner),
        ):
            assert "sk-test-secret-not-real" not in screen.text
        assert any("AI COO Briefing" in label for label in _buttons(render_ai_brain_page(session, owner)))
        assert "Refresh" in " ".join(_buttons(render_ai_settings_page(session, owner)))


def test_ai_routes_back_home_and_owner_access(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with session_scope() as session:
        owner = _owner(session)
        screen = screen_for_page("ai_brain:settings", _principal(owner), session=session, user=owner)
        buttons = _buttons(screen)

        assert "Main Menu" in buttons
        assert "Back" in buttons
        assert "OPENAI_API_KEY" in screen.text


def test_ai_observability_summary_reflects_blocks(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with session_scope() as session:
        session.add(AIAuditLog(use_case="coo", provider="openai", model="gpt-5.4-mini", status="blocked_by_critic"))
        summary = ai_observability_summary(session)

        assert summary["critic_blocks"] == 1
        assert summary["meaningful"] is True
        assert summary["health"] == "needs_review"


def test_search_summary_falls_back_without_results(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-not-real")
    with session_scope() as session:
        result = generate_ai_search_summary(session)

        assert result.status == "fallback_used"
        assert "search evidence" in result.output.conclusion.casefold() or result.fallback_used


def test_ai_help_brain_answers_boundaries(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        answer = help_brain_answer(session, owner, question="What is AI Brain?")
        critic = help_brain_answer(session, owner, question="What does AI Critic do?")
        api_key = help_brain_answer(session, owner, question="Does ChatGPT Pro power Fortuna?")

        assert "may not mark systems healthy" in answer.answer
        assert "unsupported claims" in critic.answer
        assert "OPENAI_API_KEY" in api_key.answer


def test_ai_cannot_override_recovery_truth_with_verified_only_restore(monkeypatch) -> None:
    monkeypatch.setenv("AI_DAILY_LIMIT", "25")
    with session_scope() as session:
        session.add(
            BackupRun(
                run_identifier="ai-brain-backup",
                backup_type="manual",
                status="succeeded",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                encrypted=True,
                checksum="abc123",
                artifact_verified=True,
                external_storage_used=True,
            )
        )
        session.add(
            RestoreTestRun(
                run_identifier="ai-brain-restore",
                status="verified_only",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                checksum_verified=True,
                decrypt_verified=True,
                full_restore_performed=False,
            )
        )
        response = (
            '{"conclusion":"Recovery is healthy and protected.",'
            '"evidence_used":["unit-test"],'
            '"reasoning_summary":"Recovery is fixed.",'
            '"confidence":"high",'
            '"limitations":["None"],'
            '"next_best_move":"Relax.",'
            '"safety_flags":[]}'
        )
        result = FortunaAIBrain(provider=FakeAIProvider(response_text=response)).reason(
            session,
            use_case="coo_briefing",
            prompt="Explain.",
            context=_context(),
        )

        assert result.status == "blocked_by_critic"
        assert result.fallback_used is True
        assert "AI critic blocked output" in result.safe_error_summary
