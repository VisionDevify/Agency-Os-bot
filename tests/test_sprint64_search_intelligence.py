from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_coo_briefing_page,
    render_search_center_page,
    render_search_history_page,
    render_search_results_page,
    render_search_settings_page,
)
from app.models.evidence import EvidenceRecord
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation
from app.models.search import ExternalSearchQuery, ExternalSearchResult
from app.services.auth import setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.search_intelligence import (
    ProviderSearchResult,
    ProviderStatus,
    SearchOptions,
    attach_latest_search_result_as_evidence,
    create_notification_watch_from_latest_search_result,
    create_opportunity_from_latest_search_result,
    run_search,
    search_compliance_check,
)
from tests.utils import session_scope


class FakeSearchProvider:
    provider_name = "tavily"

    def __init__(self, results: tuple[ProviderSearchResult, ...] = (), *, fail: Exception | None = None) -> None:
        self.results = results
        self.fail = fail
        self.calls = 0

    def get_provider_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider="tavily",
            enabled=True,
            configured=True,
            status="configured",
            reason="Fake provider configured.",
            next_action="Run a safe public search.",
        )

    validate_api_key = get_provider_status

    def search(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return self.results

    def search_news_or_recent(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        return self.search(query, options)

    def normalize_results(self, payload: dict) -> tuple[ProviderSearchResult, ...]:
        return self.results


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=64, owner_telegram_id=64, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _result(
    *,
    title: str = "Official creator platform update",
    url: str = "https://instagram.com/blog/creator-update",
    snippet: str = "Instagram announced a public creator update for businesses.",
    score: float = 0.88,
    published_at: datetime | None = None,
) -> ProviderSearchResult:
    return ProviderSearchResult(
        title=title,
        url=url,
        snippet=snippet,
        score=score,
        published_at=published_at or datetime.now(UTC),
    )


def test_missing_tavily_key_returns_not_configured(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_ENABLED", "true")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with session_scope() as session:
        owner = _owner(session)
        report = run_search(session, "public creator economy trends", actor=owner)

        assert report.status == "not_configured"
        assert report.query is not None
        assert report.query.status == "not_configured"
        assert "TAVILY_API_KEY" in report.next_action


def test_provider_success_stores_query_results_and_external_evidence(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_DAILY_LIMIT", "25")
    provider = FakeSearchProvider(
        (
            _result(),
            _result(),
            _result(title="Forum chatter", url="https://reddit.com/r/creators/post", snippet="A public forum thread.", score=0.45),
        )
    )
    with session_scope() as session:
        owner = _owner(session)
        report = run_search(
            session,
            "public creator economy trends",
            actor=owner,
            options=SearchOptions(query_type="opportunity", used_for="opportunity"),
            provider=provider,
        )

        assert report.status == "succeeded"
        assert provider.calls == 1
        assert session.query(ExternalSearchQuery).count() == 1
        assert session.query(ExternalSearchResult).count() == 2
        assert session.query(EvidenceRecord).filter(EvidenceRecord.evidence_type == "external_search").count() == 2
        assert report.query is not None
        assert report.query.result_count == 2


def test_provider_failure_and_timeout_are_safe_handled() -> None:
    provider = FakeSearchProvider(fail=TimeoutError("network timeout for test"))
    with session_scope() as session:
        owner = _owner(session)
        report = run_search(session, "public platform changes", actor=owner, provider=provider)

        assert report.status == "failed"
        assert report.query is not None
        assert report.query.status == "failed"
        assert "timeout" in (report.query.safe_error_summary or "").casefold()


def test_compliance_blocks_private_or_login_queries_without_provider_call() -> None:
    provider = FakeSearchProvider((_result(),))
    blocked = search_compliance_check("scrape private Instagram followers behind login", query_type="opportunity")
    with session_scope() as session:
        owner = _owner(session)
        report = run_search(session, "scrape private Instagram followers behind login", actor=owner, provider=provider)

        assert not blocked.allowed
        assert report.status == "skipped"
        assert provider.calls == 0
        assert report.query is not None
        assert "private" in (report.query.safe_error_summary or "").casefold()


def test_public_opportunity_query_allowed() -> None:
    allowed = search_compliance_check("public creator economy trend research", query_type="opportunity")
    blocked = search_compliance_check("login required private profile search", query_type="opportunity")

    assert allowed.allowed
    assert not blocked.allowed


def test_scoring_credibility_freshness_and_weak_opportunity_behavior() -> None:
    old = datetime.now(UTC) - timedelta(days=400)
    provider = FakeSearchProvider(
        (
            _result(title="Official update", url="https://instagram.com/blog/public-update", score=0.9),
            _result(title="Random forum rumor", url="https://random-forum.example/post", snippet="rumor private leak", score=0.2, published_at=old),
        )
    )
    with session_scope() as session:
        owner = _owner(session)
        run_search(
            session,
            "latest creator trend",
            actor=owner,
            options=SearchOptions(query_type="trend_monitoring", used_for="opportunity"),
            provider=provider,
        )
        results = session.query(ExternalSearchResult).order_by(ExternalSearchResult.credibility_score.desc()).all()
        assert results[0].source_domain == "instagram.com"
        assert results[0].credibility_score > results[1].credibility_score
        assert results[1].freshness_score < results[0].freshness_score

    weak_provider = FakeSearchProvider(
        (_result(title="Unknown weak signal", url="https://unknown-example.test/post", snippet="vague chatter", score=0.1, published_at=old),)
    )
    with session_scope() as session:
        owner = _owner(session)
        run_search(
            session,
            "vague public trend",
            actor=owner,
            options=SearchOptions(query_type="opportunity", used_for="opportunity"),
            provider=weak_provider,
        )
        opportunity = create_opportunity_from_latest_search_result(session, actor=owner)
        recommendation = session.query(Recommendation).filter(Recommendation.recommendation_type == "external_opportunity_evidence_review").one()
        assert opportunity is not None
        assert opportunity.priority == "low"
        assert recommendation.severity == "info"


def test_attach_evidence_opportunity_and_notification_thresholds() -> None:
    strong_provider = FakeSearchProvider((_result(score=0.95),))
    with session_scope() as session:
        owner = _owner(session)
        run_search(
            session,
            "public platform signal",
            actor=owner,
            options=SearchOptions(query_type="notification_trigger", used_for="notification"),
            provider=strong_provider,
        )
        evidence = attach_latest_search_result_as_evidence(session, actor=owner)
        opportunity = create_opportunity_from_latest_search_result(session, actor=owner)
        notification = create_notification_watch_from_latest_search_result(session, actor=owner)

        assert evidence is not None
        assert evidence.evidence_type == "external_search"
        assert opportunity is not None
        assert session.query(Opportunity).count() == 1
        assert notification is True


def test_rate_limit_blocks_excessive_searches(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_DAILY_LIMIT", "1")
    provider = FakeSearchProvider((_result(),))
    with session_scope() as session:
        owner = _owner(session)
        first = run_search(session, "public trend one", actor=owner, provider=provider)
        second = run_search(session, "public trend two", actor=owner, provider=provider)

        assert first.status == "succeeded"
        assert second.status == "skipped"
        assert second.query is not None
        assert "limit" in (second.query.safe_error_summary or "").casefold()


def test_search_center_history_results_and_settings_render_without_key_leak(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret-test-value")
    provider = FakeSearchProvider((_result(),))
    with session_scope() as session:
        owner = _owner(session)
        run_search(session, "public creator trends", actor=owner, provider=provider)

        center = render_search_center_page(session, owner, details=True)
        history = render_search_history_page(session, owner)
        results = render_search_results_page(session, owner)
        settings = render_search_settings_page(session, owner)
        coo_details = render_coo_briefing_page(session, owner, details=True)
        combined = "\n".join([center.text, history.text, results.text, settings.text, coo_details.text])

        assert "Search Intelligence" in center.text
        assert "Search History" in history.text
        assert "Search Results" in results.text
        assert "TAVILY_API_KEY: present" in settings.text
        assert "tvly-secret-test-value" not in combined
        assert "External Evidence" in coo_details.text
        assert "Back" in _buttons(results)
        assert "Main Menu" in _buttons(results)


def test_search_routes_help_brain_and_observability(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_ENABLED", "true")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        search_screen = screen_for_page("search", principal, session=session, user=owner)
        settings_screen = screen_for_page("search:settings", principal, session=session, user=owner)
        summary = production_observability_summary(session)
        search_answer = help_brain_answer(session, owner, question="What is Search Intelligence?")
        private_answer = help_brain_answer(session, owner, question="Can Fortuna search private profiles?")

        assert "Not configured" in search_screen.text
        assert "TAVILY_API_KEY: missing" in settings_screen.text
        assert summary["search_intelligence_label"] == "Not configured yet"
        assert "approved search APIs" in search_answer.answer
        assert "public web evidence only" in private_answer.answer
