from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse

from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceRecord
from app.models.opportunity import Opportunity
from app.models.search import ExternalSearchQuery, ExternalSearchResult
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.evidence_capture import create_evidence_record
from app.services.events import emit_event
from app.services.recommendations import upsert_recommendation


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_DAILY_LIMIT = 25
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_MAX_RESULTS = 5
MAX_SNIPPET_CHARS = 420

BLOCKED_QUERY_MARKERS = (
    "private profile",
    "private instagram",
    "private onlyfans",
    "login required",
    "behind login",
    "password",
    "session cookie",
    "auth cookie",
    "bypass",
    "bot detection",
    "dox",
    "doxx",
    "home address",
    "phone number",
    "ssn",
    "social security",
    "email list",
    "leaked",
    "token",
    "scrape private",
    "scrape followers",
)

SOCIAL_PUBLIC_DOMAINS = ("instagram.com", "x.com", "twitter.com", "onlyfans.com", "t.me", "telegram.org")
FORUM_DOMAINS = ("reddit.com", "quora.com", "forum", "community")
REPUTABLE_DOMAINS = (
    "gov",
    "edu",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "theverge.com",
    "techcrunch.com",
    "wired.com",
    "forbes.com",
    "businessinsider.com",
)
OFFICIAL_DOMAINS = (
    "instagram.com",
    "x.com",
    "twitter.com",
    "onlyfans.com",
    "telegram.org",
    "tavily.com",
    "backblaze.com",
    "railway.app",
)

GUIDED_QUERIES = {
    "opportunity": (
        "public creator economy trends social growth niche opportunities",
        "opportunity",
        "opportunity",
    ),
    "platform_signals": (
        "public social platform creator updates Instagram X OnlyFans notifications",
        "platform_signal",
        "research",
    ),
    "coo_context": (
        "public creator economy operational risks platform changes social growth",
        "coo_context",
        "coo_briefing",
    ),
}


@dataclass(frozen=True)
class SearchOptions:
    query_type: str = "validation"
    used_for: str = "research"
    max_results: int = DEFAULT_MAX_RESULTS
    recency_days: int | None = None
    topic: str | None = None
    force_refresh: bool = False


@dataclass(frozen=True)
class SearchComplianceResult:
    allowed: bool
    reason: str
    public_reason: str


@dataclass(frozen=True)
class ProviderSearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0
    published_at: datetime | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    enabled: bool
    configured: bool
    status: str
    reason: str
    next_action: str


@dataclass(frozen=True)
class SearchRunReport:
    status: str
    query: ExternalSearchQuery | None
    results: tuple[ExternalSearchResult, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    provider_status: ProviderStatus
    compliance: SearchComplianceResult | None = None
    cached: bool = False
    next_action: str = "Open Search Intelligence."


class SearchProvider(Protocol):
    provider_name: str

    def search(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        ...

    def search_news_or_recent(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        ...

    def get_provider_status(self) -> ProviderStatus:
        ...

    def validate_api_key(self) -> ProviderStatus:
        ...

    def normalize_results(self, payload: dict[str, Any]) -> tuple[ProviderSearchResult, ...]:
        ...


def _now() -> datetime:
    return datetime.now(UTC)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _search_provider_name() -> str:
    return (os.getenv("SEARCH_PROVIDER") or "tavily").strip().casefold() or "tavily"


def _search_enabled() -> bool:
    return _env_bool("SEARCH_ENABLED", False)


def _tavily_key_present() -> bool:
    return bool((os.getenv("TAVILY_API_KEY") or "").strip())


def _safe_actor(actor: User | None) -> str | None:
    if actor is None:
        return None
    return str(actor.telegram_id or actor.id)


def _clamp(value: float | int) -> int:
    return max(0, min(100, int(round(float(value)))))


def _truncate(text: str | None, limit: int = MAX_SNIPPET_CHARS) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _safe_url_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.casefold().removeprefix("www.")
    return domain or "unknown"


def _display_url(url: str) -> str:
    parsed = urlparse(url)
    domain = _safe_url_domain(url)
    path = parsed.path.strip("/")
    return domain if not path else f"{domain}/{path[:80]}"


def _result_hash(url: str, title: str) -> str:
    normalized = f"{url.strip().casefold()}|{title.strip().casefold()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _source_type(domain: str) -> str:
    if any(marker in domain for marker in FORUM_DOMAINS):
        return "forum_public"
    if any(domain == item or domain.endswith(f".{item}") for item in SOCIAL_PUBLIC_DOMAINS):
        return "social_public"
    return "website" if domain != "unknown" else "unknown"


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    for suffix in ("Z", "+00:00"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if "T" in fmt else text[:10], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _time_range_for_days(days: int | None) -> str | None:
    if days is None:
        days = _env_int("SEARCH_DEFAULT_RECENCY_DAYS", 0) or None
    if not days:
        return None
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


def _relevance_score(query: str, result: ProviderSearchResult) -> int:
    base = _clamp((result.score or 0.0) * 100)
    haystack = f"{result.title} {result.snippet}".casefold()
    terms = [term for term in query.casefold().split() if len(term) > 3]
    matched = sum(1 for term in set(terms) if term in haystack)
    boost = 25 if terms and matched >= max(1, len(set(terms)) // 2) else 10 if matched else 0
    return _clamp(max(base, 45) + boost)


def _freshness_score(published_at: datetime | None, *, query_type: str) -> int:
    if published_at is None:
        return 55 if query_type not in {"trend_monitoring", "notification_trigger"} else 35
    age_days = max(0, (_now() - published_at).days)
    if age_days <= 7:
        return 95
    if age_days <= 31:
        return 82
    if age_days <= 180:
        return 62
    if query_type in {"trend_monitoring", "notification_trigger", "platform_signal"}:
        return 30
    return 52


def _credibility_score(domain: str, title: str) -> int:
    if any(domain == official or domain.endswith(f".{official}") for official in OFFICIAL_DOMAINS):
        return 90
    if any(domain.endswith(marker) or marker in domain for marker in REPUTABLE_DOMAINS):
        return 78
    if _source_type(domain) == "forum_public":
        return 42
    if _source_type(domain) == "social_public":
        return 55
    if domain == "unknown":
        return 25
    if "official" in title.casefold():
        return 68
    return 58


def _risk_score(domain: str, title: str, snippet: str) -> int:
    text = f"{domain} {title} {snippet}".casefold()
    risk = 10
    sensitive_terms = ("private", "leak", "password", "token", "address", "phone", "ssn", "login")
    risk += sum(15 for term in sensitive_terms if term in text)
    if _source_type(domain) == "forum_public":
        risk += 10
    return _clamp(risk)


def _evidence_strength(relevance: int, freshness: int, credibility: int, risk: int) -> str:
    if credibility >= 85 and relevance >= 70 and freshness >= 50 and risk <= 25:
        return "strong"
    if (credibility >= 65 and relevance >= 60 and risk <= 45) or (relevance >= 75 and freshness >= 70 and risk <= 35):
        return "medium"
    return "weak"


def _score_result(query_text: str, result: ProviderSearchResult, *, query_type: str) -> dict[str, Any]:
    domain = _safe_url_domain(result.url)
    relevance = _relevance_score(query_text, result)
    freshness = _freshness_score(result.published_at, query_type=query_type)
    credibility = _credibility_score(domain, result.title)
    risk = _risk_score(domain, result.title, result.snippet)
    strength = _evidence_strength(relevance, freshness, credibility, risk)
    return {
        "source_domain": domain,
        "source_type": _source_type(domain),
        "relevance_score": relevance,
        "freshness_score": freshness,
        "credibility_score": credibility,
        "risk_score": risk,
        "evidence_strength": strength,
    }


def search_compliance_check(query_text: str, *, query_type: str = "validation") -> SearchComplianceResult:
    text = query_text.casefold()
    if not query_text.strip():
        return SearchComplianceResult(False, "empty_query", "Search needs a public topic or source to research.")
    blocked = next((marker for marker in BLOCKED_QUERY_MARKERS if marker in text), None)
    if blocked:
        return SearchComplianceResult(
            False,
            f"blocked_marker:{blocked}",
            "That search looks private, sensitive, or login-related, so Fortuna did not run it.",
        )
    if "site:" in text and any(marker in text for marker in ("private", "login", "followers", "messages")):
        return SearchComplianceResult(
            False,
            "blocked_login_or_private_site_query",
            "Fortuna only searches public web evidence and will not target private or login-required content.",
        )
    return SearchComplianceResult(True, "allowed_public_query", "Public search query allowed.")


class TavilySearchProvider:
    provider_name = "tavily"

    def __init__(self, *, api_key: str | None = None, timeout_seconds: int | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("TAVILY_API_KEY") or "").strip()
        self.timeout_seconds = timeout_seconds or _env_int("SEARCH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)

    def get_provider_status(self) -> ProviderStatus:
        enabled = _search_enabled()
        configured = bool(self.api_key)
        if not enabled:
            return ProviderStatus(
                self.provider_name,
                enabled=False,
                configured=configured,
                status="disabled",
                reason="SEARCH_ENABLED is not true.",
                next_action="Enable SEARCH_ENABLED when public search is ready.",
            )
        if not configured:
            return ProviderStatus(
                self.provider_name,
                enabled=True,
                configured=False,
                status="not_configured",
                reason="TAVILY_API_KEY is missing.",
                next_action="Add TAVILY_API_KEY in Railway.",
            )
        return ProviderStatus(
            self.provider_name,
            enabled=True,
            configured=True,
            status="configured",
            reason="Tavily key is present by name.",
            next_action="Run a safe public search.",
        )

    def validate_api_key(self) -> ProviderStatus:
        return self.get_provider_status()

    def search_news_or_recent(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        topic = options.topic or "news"
        return self.search(query, SearchOptions(**{**options.__dict__, "topic": topic}))

    def search(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        status = self.get_provider_status()
        if not status.enabled:
            raise SearchProviderError("Search execution is disabled.")
        if not status.configured:
            raise SearchProviderNotConfigured("Tavily API key is missing.")
        payload: dict[str, Any] = {
            "query": query,
            "search_depth": "basic",
            "max_results": max(1, min(options.max_results, 10)),
            "topic": options.topic or "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_image_descriptions": False,
            "include_favicon": False,
        }
        time_range = _time_range_for_days(options.recency_days)
        if time_range:
            payload["time_range"] = time_range
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            TAVILY_SEARCH_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise SearchProviderError("Tavily rejected the API key.") from exc
            if exc.code == 429:
                raise SearchRateLimitError("Tavily rate limit reached.") from exc
            raise SearchProviderError(f"Tavily request failed with HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise SearchProviderError("Tavily request timed out or could not connect.") from exc
        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise SearchProviderError("Tavily returned an unreadable response.") from exc
        return self.normalize_results(decoded)

    def normalize_results(self, payload: dict[str, Any]) -> tuple[ProviderSearchResult, ...]:
        results = payload.get("results") or []
        normalized: list[ProviderSearchResult] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = _truncate(str(item.get("title") or "Untitled public source"), 280)
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            snippet = _truncate(str(item.get("content") or item.get("snippet") or "No snippet available."))
            published_at = _parse_datetime(item.get("published_date") or item.get("published_at"))
            try:
                score = float(item.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            normalized.append(
                ProviderSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    score=score,
                    published_at=published_at,
                    raw={"request_id": payload.get("request_id"), "response_time": payload.get("response_time")},
                )
            )
        return tuple(normalized)


class SearchProviderError(Exception):
    pass


class SearchProviderNotConfigured(SearchProviderError):
    pass


class SearchRateLimitError(SearchProviderError):
    pass


def get_search_provider() -> SearchProvider:
    provider = _search_provider_name()
    if provider != "tavily":
        return UnsupportedSearchProvider(provider)
    return TavilySearchProvider()


class UnsupportedSearchProvider:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def get_provider_status(self) -> ProviderStatus:
        return ProviderStatus(
            self.provider_name,
            enabled=_search_enabled(),
            configured=False,
            status="not_configured",
            reason=f"Search provider '{self.provider_name}' is not implemented yet.",
            next_action="Set SEARCH_PROVIDER=tavily.",
        )

    validate_api_key = get_provider_status

    def search(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        raise SearchProviderNotConfigured(f"Search provider '{self.provider_name}' is not implemented yet.")

    def search_news_or_recent(self, query: str, options: SearchOptions) -> tuple[ProviderSearchResult, ...]:
        return self.search(query, options)

    def normalize_results(self, payload: dict[str, Any]) -> tuple[ProviderSearchResult, ...]:
        return ()


def _latest_cached_query(session: Session, *, query_text: str, query_type: str, provider: str) -> ExternalSearchQuery | None:
    return session.scalar(
        select(ExternalSearchQuery)
        .where(
            func.lower(ExternalSearchQuery.query_text) == query_text.strip().casefold(),
            ExternalSearchQuery.query_type == query_type,
            ExternalSearchQuery.provider == provider,
            ExternalSearchQuery.status == "succeeded",
        )
        .order_by(desc(ExternalSearchQuery.requested_at), desc(ExternalSearchQuery.id))
        .limit(1)
    )


def _results_for_query(session: Session, query: ExternalSearchQuery) -> tuple[ExternalSearchResult, ...]:
    return tuple(
        session.scalars(
            select(ExternalSearchResult)
            .where(ExternalSearchResult.query_id == query.id)
            .order_by(desc(ExternalSearchResult.evidence_strength), desc(ExternalSearchResult.relevance_score), desc(ExternalSearchResult.id))
        ).all()
    )


def _daily_search_count(session: Session) -> int:
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        session.scalar(
            select(func.count(ExternalSearchQuery.id)).where(ExternalSearchQuery.requested_at >= today)
        )
        or 0
    )


def _create_query(
    session: Session,
    *,
    query_text: str,
    query_type: str,
    provider: str,
    status: str,
    actor: User | None,
    error: str | None = None,
    metadata: dict | None = None,
) -> ExternalSearchQuery:
    query = ExternalSearchQuery(
        query_text=query_text,
        query_type=query_type,
        requested_by=_safe_actor(actor),
        requested_at=_now(),
        provider=provider,
        status=status,
        result_count=0,
        safe_error_summary=error,
        metadata_json=sanitize_details(metadata or {}),
    )
    session.add(query)
    session.flush()
    return query


def _store_result(
    session: Session,
    *,
    query: ExternalSearchQuery,
    provider_result: ProviderSearchResult,
    query_text: str,
    query_type: str,
    used_for: str,
) -> ExternalSearchResult | None:
    result_hash = _result_hash(provider_result.url, provider_result.title)
    existing = session.scalar(
        select(ExternalSearchResult)
        .where(ExternalSearchResult.provider == query.provider, ExternalSearchResult.result_hash == result_hash)
        .limit(1)
    )
    if existing is not None:
        return None
    scores = _score_result(query_text, provider_result, query_type=query_type)
    title = _truncate(provider_result.title, 280)
    snippet = _truncate(provider_result.snippet)
    result = ExternalSearchResult(
        query_id=query.id,
        provider=query.provider,
        title=title,
        url=provider_result.url,
        display_url=_display_url(provider_result.url),
        snippet=snippet,
        published_at=provider_result.published_at,
        retrieved_at=_now(),
        source_domain=scores["source_domain"],
        source_type=scores["source_type"],
        relevance_score=scores["relevance_score"],
        freshness_score=scores["freshness_score"],
        credibility_score=scores["credibility_score"],
        risk_score=scores["risk_score"],
        evidence_strength=scores["evidence_strength"],
        summary=f"{title}: {snippet}",
        used_for=used_for,
        result_hash=result_hash,
        metadata_json=sanitize_details({"provider_metadata": provider_result.raw or {}}),
    )
    session.add(result)
    session.flush()
    return result


def _create_external_evidence(
    session: Session,
    *,
    result: ExternalSearchResult,
    actor: User | None,
) -> EvidenceRecord:
    return create_evidence_record(
        session,
        evidence_type="external_search",
        category=result.used_for if result.used_for != "research" else "external_search",
        summary=f"Public source found: {result.title}",
        details=result.summary,
        evidence_strength=result.evidence_strength,
        actor=actor,
        metadata={
            "source_url": result.url,
            "source_domain": result.source_domain,
            "retrieved_at": result.retrieved_at.isoformat(),
            "query_id": result.query_id,
            "result_id": result.id,
            "credibility_score": result.credibility_score,
            "freshness_score": result.freshness_score,
            "relevance_score": result.relevance_score,
            "risk_score": result.risk_score,
        },
    )


def _maybe_create_search_recommendations(
    session: Session,
    *,
    query: ExternalSearchQuery,
    results: tuple[ExternalSearchResult, ...],
    actor: User | None,
) -> None:
    if not results:
        return
    best = max(results, key=lambda item: (item.evidence_strength == "strong", item.relevance_score, item.credibility_score))
    if query.query_type == "notification_trigger":
        if best.relevance_score >= 75 and best.freshness_score >= 70 and best.credibility_score >= 60:
            upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="search_notification_watch_review",
                title="Review Public Signal Alert Watch",
                description="A relevant public signal was found. Configure a notification route before alerting from it.",
                severity="warning",
                entity_type="external_search_query",
                entity_id=query.id,
                metadata={"result_id": best.id, "source_domain": best.source_domain},
            )
        return
    if query.query_type in {"opportunity", "niche_research", "trend_monitoring"}:
        severity = "warning" if best.evidence_strength in {"medium", "strong"} else "info"
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="external_opportunity_evidence_review",
            title="Review External Opportunity Evidence",
            description="Public search found context that may support an opportunity, but human review is required.",
            severity=severity,
            entity_type="external_search_query",
            entity_id=query.id,
            metadata={
                "result_id": best.id,
                "source_domain": best.source_domain,
                "evidence_strength": best.evidence_strength,
                "auto_contact": False,
            },
        )


def run_search(
    session: Session,
    query_text: str,
    *,
    actor: User | None = None,
    options: SearchOptions | None = None,
    provider: SearchProvider | None = None,
) -> SearchRunReport:
    options = options or SearchOptions()
    provider = provider or get_search_provider()
    provider_status = provider.get_provider_status()
    compliance = search_compliance_check(query_text, query_type=options.query_type)
    if not compliance.allowed:
        query = _create_query(
            session,
            query_text=query_text,
            query_type=options.query_type,
            provider=provider.provider_name,
            status="skipped",
            actor=actor,
            error=compliance.public_reason,
            metadata={"compliance_reason": compliance.reason},
        )
        emit_event(
            session,
            actor=actor,
            event_name="search.blocked",
            resource_type="external_search_query",
            resource_id=str(query.id),
            payload=sanitize_details({"reason": compliance.reason, "query_type": options.query_type}),
        )
        return SearchRunReport(
            status="skipped",
            query=query,
            results=(),
            evidence_records=(),
            provider_status=provider_status,
            compliance=compliance,
            next_action="Use public, non-sensitive search topics.",
        )
    if not provider_status.enabled:
        query = _create_query(
            session,
            query_text=query_text,
            query_type=options.query_type,
            provider=provider.provider_name,
            status="skipped",
            actor=actor,
            error="Search execution is disabled.",
        )
        return SearchRunReport(
            status="skipped",
            query=query,
            results=(),
            evidence_records=(),
            provider_status=provider_status,
            compliance=compliance,
            next_action=provider_status.next_action,
        )
    if not provider_status.configured:
        query = _create_query(
            session,
            query_text=query_text,
            query_type=options.query_type,
            provider=provider.provider_name,
            status="not_configured",
            actor=actor,
            error="Search provider key is not configured.",
        )
        return SearchRunReport(
            status="not_configured",
            query=query,
            results=(),
            evidence_records=(),
            provider_status=provider_status,
            compliance=compliance,
            next_action=provider_status.next_action,
        )
    daily_limit = _env_int("SEARCH_DAILY_LIMIT", DEFAULT_DAILY_LIMIT)
    if daily_limit and _daily_search_count(session) >= daily_limit:
        query = _create_query(
            session,
            query_text=query_text,
            query_type=options.query_type,
            provider=provider.provider_name,
            status="skipped",
            actor=actor,
            error="Search limit reached. Try again later.",
            metadata={"rate_limited": True, "daily_limit": daily_limit},
        )
        return SearchRunReport(
            status="skipped",
            query=query,
            results=(),
            evidence_records=(),
            provider_status=provider_status,
            compliance=compliance,
            next_action="Search limit reached. Try again later.",
        )
    if not options.force_refresh:
        cached = _latest_cached_query(
            session,
            query_text=query_text,
            query_type=options.query_type,
            provider=provider.provider_name,
        )
        if cached is not None:
            return SearchRunReport(
                status="succeeded",
                query=cached,
                results=_results_for_query(session, cached),
                evidence_records=(),
                provider_status=provider_status,
                compliance=compliance,
                cached=True,
                next_action="Open Search Results.",
            )
    query = _create_query(
        session,
        query_text=query_text,
        query_type=options.query_type,
        provider=provider.provider_name,
        status="running",
        actor=actor,
    )
    session.flush()
    try:
        provider_results = provider.search(query_text, options)
        stored: list[ExternalSearchResult] = []
        for provider_result in provider_results[: max(1, min(options.max_results, 10))]:
            stored_result = _store_result(
                session,
                query=query,
                provider_result=provider_result,
                query_text=query_text,
                query_type=options.query_type,
                used_for=options.used_for,
            )
            if stored_result is not None:
                stored.append(stored_result)
        query.status = "succeeded"
        query.result_count = len(stored)
        query.safe_error_summary = None
        query.metadata_json = sanitize_details({"cached": False, "daily_limit": daily_limit})
        evidence = tuple(_create_external_evidence(session, result=result, actor=actor) for result in stored[:3])
        _maybe_create_search_recommendations(session, query=query, results=tuple(stored), actor=actor)
        emit_event(
            session,
            actor=actor,
            event_name="search.completed",
            resource_type="external_search_query",
            resource_id=str(query.id),
            payload=sanitize_details({"result_count": len(stored), "query_type": options.query_type}),
        )
        return SearchRunReport(
            status="succeeded",
            query=query,
            results=tuple(stored),
            evidence_records=evidence,
            provider_status=provider_status,
            compliance=compliance,
            next_action="Review Search Results.",
        )
    except SearchProviderNotConfigured:
        query.status = "not_configured"
        query.safe_error_summary = "Search provider key is not configured."
        return SearchRunReport(
            status="not_configured",
            query=query,
            results=(),
            evidence_records=(),
            provider_status=provider.get_provider_status(),
            compliance=compliance,
            next_action="Add TAVILY_API_KEY in Railway.",
        )
    except SearchRateLimitError as exc:
        query.status = "skipped"
        query.safe_error_summary = str(exc)
        query.metadata_json = sanitize_details({"rate_limited": True})
        return SearchRunReport(
            status="skipped",
            query=query,
            results=(),
            evidence_records=(),
            provider_status=provider_status,
            compliance=compliance,
            next_action="Search limit reached. Try again later.",
        )
    except Exception as exc:
        query.status = "failed"
        query.safe_error_summary = str(exc)[:240]
        emit_event(
            session,
            actor=actor,
            event_name="search.failed",
            resource_type="external_search_query",
            resource_id=str(query.id),
            payload=sanitize_details({"error": query.safe_error_summary, "query_type": options.query_type}),
        )
        return SearchRunReport(
            status="failed",
            query=query,
            results=(),
            evidence_records=(),
            provider_status=provider_status,
            compliance=compliance,
            next_action="Open Search Details and review the safe error.",
        )


def run_guided_search(session: Session, workflow: str, *, actor: User | None = None, force_refresh: bool = False) -> SearchRunReport:
    query_text, query_type, used_for = GUIDED_QUERIES.get(workflow, GUIDED_QUERIES["coo_context"])
    recency = _env_int("SEARCH_DEFAULT_RECENCY_DAYS", 0) or None
    return run_search(
        session,
        query_text,
        actor=actor,
        options=SearchOptions(
            query_type=query_type,
            used_for=used_for,
            max_results=DEFAULT_MAX_RESULTS,
            recency_days=recency,
            force_refresh=force_refresh,
        ),
    )


def search_configuration_status(session: Session | None = None) -> dict[str, Any]:
    provider = get_search_provider()
    status = provider.get_provider_status()
    daily_count = 0
    latest_query = None
    if session is not None:
        try:
            daily_count = _daily_search_count(session)
            latest_query = session.scalar(
                select(ExternalSearchQuery).order_by(desc(ExternalSearchQuery.requested_at), desc(ExternalSearchQuery.id)).limit(1)
            )
        except SQLAlchemyError:
            daily_count = 0
    latest_status = latest_query.status if latest_query else "not_checked"
    latest_error = latest_query.safe_error_summary if latest_query else None
    return {
        "provider": status.provider,
        "enabled": status.enabled,
        "configured": status.configured,
        "status": status.status,
        "reason": status.reason,
        "next_action": status.next_action,
        "daily_count": daily_count,
        "daily_limit": _env_int("SEARCH_DAILY_LIMIT", DEFAULT_DAILY_LIMIT),
        "latest_query_status": latest_status,
        "latest_error": latest_error,
        "env_vars": {
            "SEARCH_PROVIDER": bool(os.getenv("SEARCH_PROVIDER")),
            "SEARCH_ENABLED": bool(os.getenv("SEARCH_ENABLED")),
            "TAVILY_API_KEY": _tavily_key_present(),
            "SEARCH_DAILY_LIMIT": bool(os.getenv("SEARCH_DAILY_LIMIT")),
            "SEARCH_TIMEOUT_SECONDS": bool(os.getenv("SEARCH_TIMEOUT_SECONDS")),
            "SEARCH_DEFAULT_RECENCY_DAYS": bool(os.getenv("SEARCH_DEFAULT_RECENCY_DAYS")),
        },
    }


def list_search_history(session: Session, *, limit: int = 8) -> tuple[ExternalSearchQuery, ...]:
    return tuple(
        session.scalars(
            select(ExternalSearchQuery).order_by(desc(ExternalSearchQuery.requested_at), desc(ExternalSearchQuery.id)).limit(limit)
        ).all()
    )


def latest_search_query(session: Session) -> ExternalSearchQuery | None:
    return session.scalar(
        select(ExternalSearchQuery).order_by(desc(ExternalSearchQuery.requested_at), desc(ExternalSearchQuery.id)).limit(1)
    )


def latest_search_results(session: Session, *, limit: int = 5) -> tuple[ExternalSearchResult, ...]:
    query = latest_search_query(session)
    if query is None:
        return ()
    return tuple(
        session.scalars(
            select(ExternalSearchResult)
            .where(ExternalSearchResult.query_id == query.id)
            .order_by(desc(ExternalSearchResult.relevance_score), desc(ExternalSearchResult.id))
            .limit(limit)
        ).all()
    )


def attach_latest_search_result_as_evidence(session: Session, *, actor: User | None = None) -> EvidenceRecord | None:
    result = next(iter(latest_search_results(session, limit=1)), None)
    if result is None:
        return None
    return _create_external_evidence(session, result=result, actor=actor)


def create_opportunity_from_latest_search_result(session: Session, *, actor: User | None = None) -> Opportunity | None:
    result = next(iter(latest_search_results(session, limit=1)), None)
    if result is None:
        return None
    score = min(78, max(35, (result.relevance_score + result.freshness_score + result.credibility_score - result.risk_score) // 3))
    priority = "normal" if result.evidence_strength in {"medium", "strong"} and score >= 60 else "low"
    opportunity = Opportunity(
        platform="other",
        source_type="manual",
        title=f"Review public signal: {result.title[:190]}",
        url=result.url,
        niche="external research",
        score=score,
        priority=priority,
        status="reviewing",
        reason=(
            "External search found public evidence that may support an opportunity. "
            "Fortuna has not contacted anyone or treated the result as proven truth."
        ),
        suggested_angle=f"Manually review {result.source_domain}; evidence strength is {result.evidence_strength}.",
    )
    session.add(opportunity)
    session.flush()
    create_evidence_record(
        session,
        evidence_type="external_search",
        category="opportunity",
        summary=f"External search attached to opportunity {opportunity.id}.",
        details=result.summary,
        evidence_strength=result.evidence_strength,
        actor=actor,
        metadata={"opportunity_id": opportunity.id, "result_id": result.id, "source_domain": result.source_domain, "source_url": result.url},
    )
    emit_event(
        session,
        actor=actor,
        event_name="search.opportunity_created_for_review",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        payload=sanitize_details({"result_id": result.id, "source_domain": result.source_domain, "human_review_required": True}),
    )
    return opportunity


def create_notification_watch_from_latest_search_result(session: Session, *, actor: User | None = None) -> bool:
    result = next(iter(latest_search_results(session, limit=1)), None)
    if result is None:
        return False
    if result.relevance_score < 70 or result.freshness_score < 60 or result.credibility_score < 55:
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="search_notification_watch_wait",
            title="Search Signal Needs Review",
            description="The latest public result is not strong enough to become an alert watch yet.",
            severity="info",
            entity_type="external_search_result",
            entity_id=result.id,
            metadata={"source_domain": result.source_domain, "evidence_strength": result.evidence_strength},
        )
        return False
    upsert_recommendation(
        session,
        actor=actor,
        recommendation_type="search_notification_watch_review",
        title="Configure Alert Watch for Public Signal",
        description="The latest public search result is relevant enough to review before configuring notifications.",
        severity="warning",
        entity_type="external_search_result",
        entity_id=result.id,
        metadata={"source_domain": result.source_domain, "evidence_strength": result.evidence_strength},
    )
    return True


def ignore_latest_search_result(session: Session, *, actor: User | None = None) -> bool:
    result = next(iter(latest_search_results(session, limit=1)), None)
    if result is None:
        return False
    metadata = dict(result.metadata_json or {})
    metadata["ignored_at"] = _now().isoformat()
    result.metadata_json = sanitize_details(metadata)
    emit_event(
        session,
        actor=actor,
        event_name="search.result_ignored",
        resource_type="external_search_result",
        resource_id=str(result.id),
        payload=sanitize_details({"source_domain": result.source_domain}),
    )
    return True


def search_observability_summary(session: Session) -> dict[str, Any]:
    status = search_configuration_status(session)
    latest = latest_search_query(session)
    failures = session.scalar(
        select(func.count(ExternalSearchQuery.id)).where(ExternalSearchQuery.status.in_(("failed", "skipped")))
    ) or 0
    meaningful = bool(
        status["configured"]
        or latest is not None
        or status["latest_query_status"] in {"failed", "skipped", "not_configured"}
    )
    if not status["enabled"]:
        health = "healthy"
        label = "Disabled"
    elif not status["configured"]:
        health = "needs_review" if latest is not None else "healthy"
        label = "Not configured yet"
    elif latest is not None and latest.status == "failed":
        health = "needs_review"
        label = "Needs review"
    elif latest is not None and latest.status == "skipped" and (latest.metadata_json or {}).get("rate_limited"):
        health = "needs_review"
        label = "Rate limited"
    else:
        health = "healthy"
        label = "Configured" if status["configured"] else "Not configured yet"
    return {
        **status,
        "health": health,
        "label": label,
        "meaningful": meaningful,
        "failed_or_skipped_count": int(failures),
        "latest_query_text": latest.query_text if latest else None,
        "latest_query_type": latest.query_type if latest else None,
        "latest_result_count": latest.result_count if latest else 0,
        "latest_requested_at": latest.requested_at if latest else None,
    }


def latest_external_context(session: Session) -> dict[str, Any]:
    result = session.scalar(
        select(ExternalSearchResult)
        .where(ExternalSearchResult.evidence_strength.in_(("medium", "strong")))
        .order_by(desc(ExternalSearchResult.retrieved_at), desc(ExternalSearchResult.id))
        .limit(1)
    )
    count = session.scalar(select(func.count(ExternalSearchResult.id))) or 0
    if result is None:
        return {"available": False, "count": int(count), "summary": "No useful external search evidence yet."}
    return {
        "available": True,
        "count": int(count),
        "title": result.title,
        "source_domain": result.source_domain,
        "strength": result.evidence_strength,
        "summary": result.summary,
        "retrieved_at": result.retrieved_at,
    }
