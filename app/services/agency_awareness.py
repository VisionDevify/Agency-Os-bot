from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.agency_awareness import AgencyAwarenessSnapshot, AgencyManualRecord
from app.models.evidence import EvidenceRecord, KnowledgeMemory
from app.models.model_brand import ModelBrand
from app.models.opportunity import CreatorWatch, Opportunity, PostWatch
from app.models.search import ExternalSearchResult
from app.models.user import User
from app.services.ai import ai_configuration_status
from app.services.audit import sanitize_details
from app.services.decision_engine import decision_memory_summary
from app.services.notification_intelligence import alert_health_summary
from app.services.platform_connections import platform_connection_status, platform_connections_status
from app.services.reality_calibration import safe_reality_calibration_report
from app.services.recovery import recovery_risk_assessment
from app.services.search_intelligence import search_observability_summary


DOMAIN_STATUS_VALUES = (
    "active",
    "inactive",
    "needs_review",
    "ready_to_connect",
    "not_connected",
    "insufficient_data",
)

DOMAIN_CONFIDENCE_VALUES = ("low", "medium", "high")

STALE_SNAPSHOT_HOURS = 6


@dataclass(frozen=True)
class AgencyDomainDefinition:
    domain_id: str
    display_name: str
    why_it_matters: str
    data_unlocked: str
    recommended_timing: str = "When the workflow needs it."


@dataclass(frozen=True)
class AgencyDomain:
    domain_id: str
    display_name: str
    status: str
    confidence: str
    evidence_summary: str
    next_best_move: str
    last_activity: datetime | None = None
    last_seen: datetime | None = None
    why_it_matters: str = ""
    data_unlocked: str = ""
    recommended_timing: str = "When needed."
    connection_state: str | None = None
    stale: bool = False
    unavailable: bool = False
    source: str = "system"

    def to_dict(self) -> dict[str, object]:
        return {
            "domain_id": self.domain_id,
            "display_name": self.display_name,
            "status": self.status,
            "confidence": self.confidence,
            "evidence_summary": self.evidence_summary,
            "next_best_move": self.next_best_move,
            "last_activity": _iso(self.last_activity),
            "last_seen": _iso(self.last_seen),
            "why_it_matters": self.why_it_matters,
            "data_unlocked": self.data_unlocked,
            "recommended_timing": self.recommended_timing,
            "connection_state": self.connection_state,
            "stale": self.stale,
            "unavailable": self.unavailable,
            "source": self.source,
        }


@dataclass(frozen=True)
class AgencyVisibilityScore:
    level: str
    score: int
    connected_domains: int
    active_domains: int
    evidence_quality: int
    manual_coverage: int
    system_coverage: int
    evidence_summary: str


@dataclass(frozen=True)
class AgencyAwarenessReport:
    generated_at: datetime
    overall_status: str
    active_domains: tuple[AgencyDomain, ...]
    inactive_domains: tuple[AgencyDomain, ...]
    missing_domains: tuple[AgencyDomain, ...]
    not_connected_domains: tuple[AgencyDomain, ...]
    domains: tuple[AgencyDomain, ...]
    visibility_score: int
    visibility_level: str
    confidence_score: int
    top_focus_area: str
    next_best_move: str
    evidence_summary: str
    snapshot_source: str = "live"
    stale: bool = False
    missing_inputs: tuple[str, ...] = ()
    degraded_mode: bool = False
    fallback_notice: str | None = None


DOMAIN_REGISTRY: tuple[AgencyDomainDefinition, ...] = (
    AgencyDomainDefinition("recovery", "Recovery", "Protects Fortuna if Railway or data storage breaks.", "Backup and restore confidence.", "Keep active before launch."),
    AgencyDomainDefinition("ai_brain", "AI Brain", "Explains decisions using Fortuna evidence.", "Grounded summaries and clearer recommendations.", "Use when evidence is available."),
    AgencyDomainDefinition("search_intelligence", "Search Intelligence", "Adds public external evidence safely.", "Trend and opportunity context.", "Connect when public research is useful."),
    AgencyDomainDefinition("notifications", "Notifications", "Routes meaningful alerts.", "Owner and team alert delivery.", "Configure before team rollout."),
    AgencyDomainDefinition("platform_connections", "Platform Connections", "Prepares external platform access.", "Connection readiness across channels.", "Can wait until final activation."),
    AgencyDomainDefinition("instagram", "Instagram", "Shows creator/content/social signals when approved.", "Followers, reach, posts, comments, and trends.", "Final activation or active Instagram workflow."),
    AgencyDomainDefinition("x", "X", "Shows public conversation and account signals when approved.", "Posts, engagement, and conversation trends.", "Final activation or active X workflow."),
    AgencyDomainDefinition("reddit", "Reddit", "Shows compliant public community signals.", "Public community trends and content opportunities.", "After search/compliance rules are ready."),
    AgencyDomainDefinition("onlyfans", "OnlyFans", "Shows approved creator/business signals.", "Account, fan, and approved activity metrics.", "Final activation only."),
    AgencyDomainDefinition("chaturbate", "Chaturbate", "Shows approved live-platform context if added later.", "Live-platform activity and routing context.", "Future connector."),
    AgencyDomainDefinition("creators", "Creators", "Shows creator outreach and watch activity.", "Creator watch, outreach, and lead movement.", "Add records when creator ops begin."),
    AgencyDomainDefinition("content", "Content", "Shows posting and content pipeline visibility.", "Post watches and content cadence.", "Add when content operations start."),
    AgencyDomainDefinition("traffic_sources", "Traffic Sources", "Shows where attention comes from.", "Source quality and opportunity context.", "Add manual records or connectors."),
    AgencyDomainDefinition("fans", "Fans", "Shows fan/customer visibility.", "Audience activity and retention signals.", "Future secure data source."),
    AgencyDomainDefinition("whales", "Whales", "Shows high-value fan/customer visibility.", "VIP tracking and risk/opportunity context.", "Future secure data source."),
    AgencyDomainDefinition("chatters", "Chatters", "Shows team/chat operator coverage.", "Team readiness and assignment visibility.", "During team onboarding."),
    AgencyDomainDefinition("opportunities", "Opportunities", "Shows active leads and growth chances.", "Opportunity queue and outcomes.", "Use during daily operations."),
    AgencyDomainDefinition("operations", "Operations / Telegram Bot", "Shows system and work execution health.", "Bot, tasks, incidents, and operational flow.", "Always active."),
    AgencyDomainDefinition("compliance", "Compliance", "Keeps social/platform activity safe.", "Compliance logs and blocked actions.", "Always active for social workflows."),
    AgencyDomainDefinition("finance", "Finance", "Shows money movement when safely connected.", "Revenue, costs, and runway context.", "Future approved source."),
    AgencyDomainDefinition("knowledge_memory", "Knowledge Memory", "Stores durable lessons.", "Institutional learning and decisions.", "Use after evidence accumulates."),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.isoformat()


def _parse_datetime(value: object | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _definition(domain_id: str) -> AgencyDomainDefinition:
    return next(item for item in DOMAIN_REGISTRY if item.domain_id == domain_id)


def _domain(
    domain_id: str,
    *,
    status: str,
    confidence: str,
    evidence_summary: str,
    next_best_move: str,
    last_activity: datetime | None = None,
    last_seen: datetime | None = None,
    connection_state: str | None = None,
    stale: bool = False,
    unavailable: bool = False,
    source: str = "system",
) -> AgencyDomain:
    definition = _definition(domain_id)
    safe_status = status if status in DOMAIN_STATUS_VALUES else "insufficient_data"
    safe_confidence = confidence if confidence in DOMAIN_CONFIDENCE_VALUES else "low"
    return AgencyDomain(
        domain_id=definition.domain_id,
        display_name=definition.display_name,
        status=safe_status,
        confidence=safe_confidence,
        evidence_summary=evidence_summary,
        next_best_move=next_best_move,
        last_activity=last_activity,
        last_seen=last_seen or last_activity,
        why_it_matters=definition.why_it_matters,
        data_unlocked=definition.data_unlocked,
        recommended_timing=definition.recommended_timing,
        connection_state=connection_state or safe_status,
        stale=stale,
        unavailable=unavailable,
        source=source,
    )


def _manual_record_for(session: Session, domain_id: str) -> AgencyManualRecord | None:
    return session.scalar(
        select(AgencyManualRecord)
        .where(AgencyManualRecord.domain_id == domain_id)
        .order_by(desc(AgencyManualRecord.created_at), desc(AgencyManualRecord.id))
        .limit(1)
    )


def _manual_domain(session: Session, domain_id: str) -> AgencyDomain | None:
    record = _manual_record_for(session, domain_id)
    if record is None:
        return None
    status = "needs_review" if record.record_type == "blocker" else "inactive" if record.record_type == "loss" else "active"
    return _domain(
        domain_id,
        status=status,
        confidence=record.confidence,
        evidence_summary=f"Manual {record.record_type}: {record.summary}",
        next_best_move="Review or update this manual record when reality changes.",
        last_activity=record.created_at,
        last_seen=record.updated_at or record.created_at,
        source="manual",
    )


def _count(session: Session, model, *criteria) -> int:
    statement = select(func.count(model.id))
    for criterion in criteria:
        statement = statement.where(criterion)
    return int(session.scalar(statement) or 0)


class AgencyAwarenessEngine:
    def __init__(
        self,
        *,
        external_outages: Iterable[str] | None = None,
        unavailable_inputs: Iterable[str] | None = None,
        freshness_hours: int = STALE_SNAPSHOT_HOURS,
    ) -> None:
        self.external_outages = {item.strip().casefold() for item in external_outages or () if item}
        self.unavailable_inputs = {item.strip().casefold() for item in unavailable_inputs or () if item}
        self.freshness_hours = freshness_hours
        self.missing_inputs: list[str] = []

    def generate(self, session: Session, *, persist: bool = True) -> AgencyAwarenessReport:
        domains: list[AgencyDomain] = []
        for definition in DOMAIN_REGISTRY:
            domains.append(self._safe_domain(session, definition.domain_id))
        report = self._build_report(domains, snapshot_source="live")
        if persist:
            persist_awareness_snapshot(session, report)
        return report

    def safe_generate(self, session: Session, *, persist: bool = True) -> AgencyAwarenessReport:
        try:
            return self.generate(session, persist=persist)
        except Exception as exc:
            fallback = latest_awareness_snapshot(session)
            if fallback is not None:
                report = report_from_snapshot(fallback)
                notice = (
                    "Fortuna is operating with limited visibility. Some data sources are currently unavailable. "
                    "Showing the most recent verified snapshot."
                )
                return AgencyAwarenessReport(
                    generated_at=report.generated_at,
                    overall_status="degraded",
                    active_domains=report.active_domains,
                    inactive_domains=report.inactive_domains,
                    missing_domains=report.missing_domains,
                    not_connected_domains=report.not_connected_domains,
                    domains=report.domains,
                    visibility_score=report.visibility_score,
                    visibility_level=report.visibility_level,
                    confidence_score=report.confidence_score,
                    top_focus_area=report.top_focus_area,
                    next_best_move=report.next_best_move,
                    evidence_summary=f"Fallback snapshot used because live awareness failed: {type(exc).__name__}.",
                    snapshot_source="fallback",
                    stale=True,
                    missing_inputs=("agency_awareness_live_generation",),
                    degraded_mode=True,
                    fallback_notice=notice,
                )
            return insufficient_data_report(reason=f"Live awareness unavailable: {type(exc).__name__}.")

    def _safe_domain(self, session: Session, domain_id: str) -> AgencyDomain:
        if domain_id in self.unavailable_inputs:
            self.missing_inputs.append(domain_id)
            return _domain(
                domain_id,
                status="insufficient_data",
                confidence="low",
                evidence_summary="This data source is currently unavailable.",
                next_best_move="Use manual records or retry later.",
                unavailable=True,
            )
        try:
            return self._domain_from_evidence(session, domain_id)
        except Exception:
            self.missing_inputs.append(domain_id)
            manual = _manual_domain(session, domain_id)
            if manual is not None:
                return replace(manual, unavailable=True, source="manual_fallback")
            return _domain(
                domain_id,
                status="insufficient_data",
                confidence="low",
                evidence_summary="Fortuna could not read this source right now.",
                next_best_move="Retry awareness refresh or add a manual update.",
                unavailable=True,
            )

    def _domain_from_evidence(self, session: Session, domain_id: str) -> AgencyDomain:
        manual = _manual_domain(session, domain_id)
        if domain_id == "recovery":
            recovery = recovery_risk_assessment(session)
            if recovery.latest_backup is not None:
                return _domain(
                    domain_id,
                    status="active" if recovery.status in {"healthy", "needs_review"} else "needs_review",
                    confidence="high",
                    evidence_summary=f"{recovery.last_backup_status}; restore {recovery.restore_test_status}.",
                    next_best_move=recovery.next_best_move,
                    last_activity=recovery.latest_backup.finished_at or recovery.latest_backup.started_at,
                )
            return _domain(
                domain_id,
                status="needs_review",
                confidence="medium" if recovery.external_storage_configured else "low",
                evidence_summary="Recovery exists, but no verified backup is visible yet.",
                next_best_move=recovery.next_best_move,
            )
        if domain_id == "ai_brain":
            status = ai_configuration_status(session)
            configured = bool(status.get("enabled") and status.get("configured"))
            return _domain(
                domain_id,
                status="active" if configured else "not_connected",
                confidence="medium" if configured else "low",
                evidence_summary="AI Brain is configured for grounded explanations." if configured else "AI Brain is not configured yet.",
                next_best_move="Open AI Brain." if configured else "Add OPENAI_API_KEY in Railway when ready.",
            )
        if domain_id == "search_intelligence":
            status = search_observability_summary(session)
            configured = status.get("configured") or status.get("health") == "healthy"
            latest = session.scalar(select(ExternalSearchResult).order_by(desc(ExternalSearchResult.retrieved_at), desc(ExternalSearchResult.id)).limit(1))
            return _domain(
                domain_id,
                status="active" if configured else "not_connected",
                confidence="medium" if configured else "low",
                evidence_summary=str(status.get("summary") or status.get("reason") or "Search status checked."),
                next_best_move=str(status.get("next_action") or "Open Search Intelligence."),
                last_activity=latest.retrieved_at if latest else None,
            )
        if domain_id == "notifications":
            alert = alert_health_summary(session)
            return _domain(
                domain_id,
                status="active" if alert.status == "healthy" else "needs_review",
                confidence="high" if alert.total_attempts else "medium",
                evidence_summary=alert.evidence,
                next_best_move=alert.next_action,
                last_activity=alert.last_delivery_at,
            )
        if domain_id == "platform_connections":
            statuses = platform_connections_status(session)
            connected = sum(1 for item in statuses if item.connection.status == "connected")
            configured = sum(1 for item in statuses if item.connection.status in {"connected", "connection_configured"})
            return _domain(
                domain_id,
                status="active" if connected else "ready_to_connect",
                confidence="medium" if configured else "low",
                evidence_summary=f"{configured} platform connection(s) configured; {connected} connected.",
                next_best_move="Connect platforms when final activation requires them.",
            )
        if domain_id in {"instagram", "x", "onlyfans"}:
            return self._platform_domain(session, domain_id)
        if domain_id in {"reddit", "chaturbate"}:
            if domain_id in self.external_outages:
                return _domain(
                    domain_id,
                    status="needs_review",
                    confidence="low",
                    evidence_summary=f"{_definition(domain_id).display_name} is currently unavailable; no live connector is active.",
                    next_best_move="Use historical/manual context until access is restored.",
                    connection_state="temporarily_unavailable",
                    unavailable=True,
                )
            return _domain(
                domain_id,
                status="not_connected",
                confidence="low",
                evidence_summary="No approved connector is configured yet.",
                next_best_move="Keep this as a future connector unless the workflow needs it.",
            )
        if domain_id == "creators":
            watches = _count(session, CreatorWatch)
            if watches:
                latest = session.scalar(select(CreatorWatch).order_by(desc(CreatorWatch.created_at), desc(CreatorWatch.id)).limit(1))
                return _domain(domain_id, status="active", confidence="medium", evidence_summary=f"{watches} creator watch record(s) exist.", next_best_move="Review creator watch activity.", last_activity=latest.created_at if latest else None)
            return manual or _missing_domain(domain_id, "No creator watch or manual creator activity is recorded yet.")
        if domain_id == "content":
            posts = _count(session, PostWatch)
            if posts:
                latest = session.scalar(select(PostWatch).order_by(desc(PostWatch.created_at), desc(PostWatch.id)).limit(1))
                return _domain(domain_id, status="active", confidence="medium", evidence_summary=f"{posts} post watch record(s) exist.", next_best_move="Review content watch activity.", last_activity=latest.created_at if latest else None)
            return manual or _missing_domain(domain_id, "No content pipeline records are visible yet.")
        if domain_id == "opportunities":
            opportunities = _count(session, Opportunity)
            latest = session.scalar(select(Opportunity).order_by(desc(Opportunity.created_at), desc(Opportunity.id)).limit(1))
            if opportunities:
                return _domain(domain_id, status="active", confidence="high", evidence_summary=f"{opportunities} opportunity record(s) exist.", next_best_move="Open Opportunities.", last_activity=latest.created_at if latest else None)
            return manual or _missing_domain(domain_id, "No opportunity records are visible yet.")
        if domain_id == "operations":
            tasks_or_incidents = _count(session, Account) + _count(session, ModelBrand)
            return _domain(
                domain_id,
                status="active" if tasks_or_incidents else "needs_review",
                confidence="high" if tasks_or_incidents else "medium",
                evidence_summary="Fortuna can see setup, bot, database, and operational records.",
                next_best_move="Keep using Today and COO Briefing.",
            )
        if domain_id == "compliance":
            evidence_count = _count(session, EvidenceRecord, EvidenceRecord.category.in_(("compliance", "social_intelligence", "search")))
            return _domain(
                domain_id,
                status="active" if evidence_count else "insufficient_data",
                confidence="medium" if evidence_count else "low",
                evidence_summary=f"{evidence_count} compliance-adjacent evidence record(s)." if evidence_count else "No compliance-specific evidence is recorded yet.",
                next_best_move="Keep compliance gates active for social/search workflows.",
            )
        if domain_id == "knowledge_memory":
            lessons = _count(session, KnowledgeMemory)
            latest = session.scalar(select(KnowledgeMemory).order_by(desc(KnowledgeMemory.created_at), desc(KnowledgeMemory.id)).limit(1))
            return _domain(
                domain_id,
                status="active" if lessons else "insufficient_data",
                confidence="medium" if lessons else "low",
                evidence_summary=f"{lessons} durable lesson(s) stored." if lessons else "No durable lessons are stored yet.",
                next_best_move="Add evidence or validate decisions to grow memory.",
                last_activity=latest.created_at if latest else None,
            )
        if domain_id == "chatters":
            users = _count(session, User)
            if users > 1:
                return _domain(domain_id, status="active", confidence="medium", evidence_summary=f"{users} user record(s) exist.", next_best_move="Review team readiness.")
            return manual or _missing_domain(domain_id, "No chatter workflow records are visible yet.")
        if domain_id in {"traffic_sources", "fans", "whales", "finance"}:
            return manual or _missing_domain(domain_id, "Fortuna needs more information here.")
        return manual or _missing_domain(domain_id, "Fortuna needs more information here.")

    def _platform_domain(self, session: Session, domain_id: str) -> AgencyDomain:
        status = platform_connection_status(session, domain_id)
        if domain_id in self.external_outages:
            return _domain(
                domain_id,
                status="needs_review" if status.connection.status == "connected" else "not_connected",
                confidence="low",
                evidence_summary=(
                    f"{status.display_name} is currently unavailable. Fortuna is using previously collected information if any exists."
                    if status.connection.status == "connected"
                    else f"{status.display_name} is not connected and live checks are currently unavailable."
                ),
                next_best_move="Wait for access to recover or add a manual update.",
                connection_state="temporarily_unavailable",
                unavailable=True,
            )
        if status.connection.status == "connected":
            return _domain(domain_id, status="active", confidence="high", evidence_summary=status.evidence_summary, next_best_move=status.next_action, last_activity=status.connection.checked_at, connection_state="connected")
        if status.connection.status in {"ready_to_connect", "connection_configured"}:
            return _domain(domain_id, status="ready_to_connect", confidence="medium", evidence_summary=status.evidence_summary, next_best_move=status.next_action, connection_state=status.connection.status)
        return _domain(domain_id, status="not_connected", confidence="low", evidence_summary=status.evidence_summary, next_best_move=status.next_action, connection_state="not_connected")

    def _build_report(self, domains: list[AgencyDomain], *, snapshot_source: str) -> AgencyAwarenessReport:
        active = tuple(domain for domain in domains if domain.status == "active")
        inactive = tuple(domain for domain in domains if domain.status in {"inactive", "needs_review"})
        missing = tuple(domain for domain in domains if domain.status == "insufficient_data")
        not_connected = tuple(domain for domain in domains if domain.status in {"not_connected", "ready_to_connect"})
        visibility = calculate_visibility_score(domains)
        degraded = bool(self.missing_inputs or any(domain.unavailable for domain in domains))
        overall_status = _overall_status(domains, visibility, degraded=degraded)
        focus = _top_focus(domains)
        return AgencyAwarenessReport(
            generated_at=_now(),
            overall_status=overall_status,
            active_domains=active,
            inactive_domains=inactive,
            missing_domains=missing,
            not_connected_domains=not_connected,
            domains=tuple(domains),
            visibility_score=visibility.score,
            visibility_level=visibility.level,
            confidence_score=visibility.evidence_quality,
            top_focus_area=focus.display_name,
            next_best_move=focus.next_best_move,
            evidence_summary=visibility.evidence_summary,
            snapshot_source=snapshot_source,
            stale=False,
            missing_inputs=tuple(sorted(set(self.missing_inputs))),
            degraded_mode=degraded,
            fallback_notice=(
                "Fortuna is operating with limited visibility. Some data sources are currently unavailable."
                if degraded
                else None
            ),
        )


def _missing_domain(domain_id: str, reason: str) -> AgencyDomain:
    return _domain(
        domain_id,
        status="insufficient_data",
        confidence="low",
        evidence_summary=reason,
        next_best_move="Add a manual record or connect an approved source when this work starts.",
    )


def calculate_visibility_score(domains: Iterable[AgencyDomain]) -> AgencyVisibilityScore:
    domain_list = list(domains)
    total = max(1, len(domain_list))
    connected = sum(1 for domain in domain_list if domain.status in {"active", "needs_review", "ready_to_connect"})
    active = sum(1 for domain in domain_list if domain.status == "active")
    manual = sum(1 for domain in domain_list if domain.source.startswith("manual"))
    system = sum(1 for domain in domain_list if domain.source == "system" and domain.status != "insufficient_data")
    confidence_points = {"low": 35, "medium": 65, "high": 90}
    evidence_quality = round(sum(confidence_points.get(domain.confidence, 35) for domain in domain_list) / total)
    coverage_score = round(((connected + active) / (total * 2)) * 100)
    score = max(0, min(100, round((coverage_score * 0.65) + (evidence_quality * 0.35))))
    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"
    return AgencyVisibilityScore(
        level=level,
        score=score,
        connected_domains=connected,
        active_domains=active,
        evidence_quality=evidence_quality,
        manual_coverage=manual,
        system_coverage=system,
        evidence_summary=f"Visibility is {level}: {active} active domain(s), {connected} visible or ready domain(s), {manual} manual domain(s).",
    )


def _overall_status(domains: list[AgencyDomain], visibility: AgencyVisibilityScore, *, degraded: bool) -> str:
    if degraded:
        return "degraded"
    if visibility.level == "low":
        return "insufficient_data"
    if any(domain.status == "needs_review" for domain in domains):
        return "needs_review"
    return "healthy"


def _top_focus(domains: list[AgencyDomain]) -> AgencyDomain:
    for status in ("needs_review", "insufficient_data", "not_connected", "ready_to_connect"):
        match = next((domain for domain in domains if domain.status == status), None)
        if match is not None:
            return match
    return domains[0] if domains else _missing_domain("operations", "No agency domains were available.")


def persist_awareness_snapshot(session: Session, report: AgencyAwarenessReport) -> AgencyAwarenessSnapshot:
    snapshot = AgencyAwarenessSnapshot(
        generated_at=report.generated_at,
        overall_status=report.overall_status,
        active_domains=[domain.to_dict() for domain in report.active_domains],
        inactive_domains=[domain.to_dict() for domain in report.inactive_domains],
        missing_domains=[domain.to_dict() for domain in report.missing_domains],
        not_connected_domains=[domain.to_dict() for domain in report.not_connected_domains],
        domain_records=[domain.to_dict() for domain in report.domains],
        visibility_score=report.visibility_score,
        confidence_score=report.confidence_score,
        top_focus_area=report.top_focus_area,
        next_best_move=report.next_best_move,
        snapshot_source=report.snapshot_source,
        stale=report.stale,
        missing_inputs=list(report.missing_inputs),
        degraded_mode=report.degraded_mode,
        evidence_summary=report.evidence_summary,
        metadata_json=sanitize_details(
            {
                "visibility_level": report.visibility_level,
                "fallback_notice": report.fallback_notice,
            }
        ),
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def latest_awareness_snapshot(session: Session) -> AgencyAwarenessSnapshot | None:
    return session.scalar(
        select(AgencyAwarenessSnapshot).order_by(desc(AgencyAwarenessSnapshot.generated_at), desc(AgencyAwarenessSnapshot.id)).limit(1)
    )


def _domain_from_dict(data: dict[str, object]) -> AgencyDomain:
    return AgencyDomain(
        domain_id=str(data.get("domain_id") or "operations"),
        display_name=str(data.get("display_name") or "Operations"),
        status=str(data.get("status") or "insufficient_data"),
        confidence=str(data.get("confidence") or "low"),
        evidence_summary=str(data.get("evidence_summary") or "No evidence summary available."),
        next_best_move=str(data.get("next_best_move") or "Add evidence."),
        last_activity=_parse_datetime(data.get("last_activity")),
        last_seen=_parse_datetime(data.get("last_seen")),
        why_it_matters=str(data.get("why_it_matters") or ""),
        data_unlocked=str(data.get("data_unlocked") or ""),
        recommended_timing=str(data.get("recommended_timing") or "When needed."),
        connection_state=str(data.get("connection_state") or data.get("status") or "insufficient_data"),
        stale=bool(data.get("stale")),
        unavailable=bool(data.get("unavailable")),
        source=str(data.get("source") or "snapshot"),
    )


def report_from_snapshot(snapshot: AgencyAwarenessSnapshot) -> AgencyAwarenessReport:
    domains = tuple(_domain_from_dict(item) for item in snapshot.domain_records)
    generated = snapshot.generated_at if snapshot.generated_at.tzinfo else snapshot.generated_at.replace(tzinfo=UTC)
    stale = snapshot.stale or generated < _now() - timedelta(hours=STALE_SNAPSHOT_HOURS)
    visibility_level = str((snapshot.metadata_json or {}).get("visibility_level") or ("high" if snapshot.visibility_score >= 70 else "medium" if snapshot.visibility_score >= 40 else "low"))
    return AgencyAwarenessReport(
        generated_at=generated,
        overall_status=snapshot.overall_status,
        active_domains=tuple(_domain_from_dict(item) for item in snapshot.active_domains),
        inactive_domains=tuple(_domain_from_dict(item) for item in snapshot.inactive_domains),
        missing_domains=tuple(_domain_from_dict(item) for item in snapshot.missing_domains),
        not_connected_domains=tuple(_domain_from_dict(item) for item in snapshot.not_connected_domains),
        domains=domains,
        visibility_score=snapshot.visibility_score,
        visibility_level=visibility_level,
        confidence_score=snapshot.confidence_score,
        top_focus_area=snapshot.top_focus_area,
        next_best_move=snapshot.next_best_move,
        evidence_summary=snapshot.evidence_summary,
        snapshot_source="fallback" if snapshot.snapshot_source != "live" or stale else snapshot.snapshot_source,
        stale=stale,
        missing_inputs=tuple(snapshot.missing_inputs or ()),
        degraded_mode=bool(snapshot.degraded_mode or stale),
        fallback_notice=(snapshot.metadata_json or {}).get("fallback_notice"),
    )


def insufficient_data_report(*, reason: str = "No valid Agency Awareness snapshot exists yet.") -> AgencyAwarenessReport:
    domain = _missing_domain("operations", reason)
    return AgencyAwarenessReport(
        generated_at=_now(),
        overall_status="insufficient_data",
        active_domains=(),
        inactive_domains=(),
        missing_domains=(domain,),
        not_connected_domains=(),
        domains=(domain,),
        visibility_score=0,
        visibility_level="low",
        confidence_score=0,
        top_focus_area=domain.display_name,
        next_best_move="Open Agency Awareness after more evidence exists or add a manual record.",
        evidence_summary=reason,
        snapshot_source="none",
        stale=False,
        missing_inputs=("agency_awareness_snapshot",),
        degraded_mode=True,
        fallback_notice="No verified Agency Awareness snapshot is available yet.",
    )


def create_manual_record(
    session: Session,
    *,
    domain_id: str,
    record_type: str,
    summary: str,
    confidence: str = "low",
    details: str | None = None,
    created_by: str | None = None,
) -> AgencyManualRecord:
    record = AgencyManualRecord(
        domain_id=domain_id,
        record_type=record_type,
        summary=summary,
        details=details,
        confidence=confidence,
        created_by=created_by,
        metadata_json={},
    )
    session.add(record)
    session.flush()
    return record


def agency_awareness_report(
    session: Session,
    *,
    persist: bool = True,
    external_outages: Iterable[str] | None = None,
    unavailable_inputs: Iterable[str] | None = None,
) -> AgencyAwarenessReport:
    engine = AgencyAwarenessEngine(external_outages=external_outages, unavailable_inputs=unavailable_inputs)
    return engine.safe_generate(session, persist=persist)


def agency_awareness_observability(session: Session) -> dict[str, object]:
    try:
        report = agency_awareness_report(session, persist=False)
    except SQLAlchemyError:
        return {
            "status": "needs_review",
            "meaningful": True,
            "summary": "Agency Awareness is unavailable.",
            "next_action": "Open Agency Awareness after database health is verified.",
            "missing_inputs": ["agency_awareness"],
            "degraded": True,
        }
    meaningful = report.overall_status in {"degraded", "insufficient_data", "needs_attention"} or bool(report.missing_inputs)
    return {
        "status": report.overall_status,
        "meaningful": meaningful,
        "summary": report.evidence_summary,
        "next_action": report.next_best_move,
        "missing_inputs": list(report.missing_inputs),
        "degraded": report.degraded_mode,
        "visibility_score": report.visibility_score,
        "visibility_level": report.visibility_level,
    }
