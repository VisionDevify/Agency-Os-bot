from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.agency_awareness import AgencyManualRecord
from app.models.command_center import ScoreSnapshot
from app.models.decision_memory import DecisionMemory
from app.models.decision_trends import DecisionQualityTrend, PredictiveCOOPrediction
from app.models.evidence import EvidenceRecord, KnowledgeMemory
from app.models.opportunity import CreatorWatch, Opportunity, PostWatch
from app.models.platform import PlatformConnection
from app.models.reality_calibration import PredictionOutcome
from app.models.recovery import BackupRun, BackupStorageTarget, RestoreTestRun
from app.models.reporting import NotificationTarget
from app.models.search import ExternalSearchResult
from app.models.social import SocialPost, SocialSource, SocialSourcePerformance
from app.models.user import User
from app.services.agency_awareness import AgencyAwarenessReport, agency_awareness_report
from app.services.ai import ai_configuration_status
from app.services.button_health import button_health_summary
from app.services.chat_cleanup import chat_cleanup_metrics
from app.services.recovery import RecoveryAssessment, recovery_risk_assessment
from app.services.reliability import active_jobs, reliability_summary
from app.services.search_intelligence import search_configuration_status
from app.services.system_truth import SystemTruth, system_truth


SCORE_WEIGHTS: dict[str, dict[str, int]] = {
    "agency_os": {
        "Infrastructure / Health": 20,
        "Recovery Safety": 15,
        "Reliability / UX": 15,
        "Intelligence Foundation": 20,
        "Agency Awareness": 15,
        "Revenue Intelligence": 15,
    },
    "intelligence": {
        "Decision Engine": 15,
        "Decision Memory": 15,
        "AI Brain": 15,
        "Search Intelligence": 15,
        "Reality Calibration": 15,
        "Knowledge Memory": 10,
        "Prediction Quality": 10,
        "Evidence Coverage": 5,
    },
    "team_readiness": {
        "Navigation Reliability": 25,
        "Screen Simplicity": 20,
        "Role Metadata": 15,
        "Help Brain": 10,
        "Reliability Center": 15,
        "Onboarding Friendliness": 15,
    },
    "revenue_intelligence": {
        "Fan Data": 20,
        "Whale Data": 20,
        "Source Quality Data": 20,
        "Creator Data": 15,
        "Content Data": 15,
        "Chatter Data": 10,
    },
    "recovery_safety": {
        "Last Backup Freshness": 25,
        "Backup Success Evidence": 25,
        "Restore Validation Evidence": 25,
        "Redundancy / Second Copy": 15,
        "Storage Health": 10,
    },
    "reliability": {
        "Command Success": 25,
        "Callback Success": 25,
        "Average Response Speed": 20,
        "Active Failure Count": 20,
        "Stale Menu Safety": 10,
    },
    "agency_visibility": {
        "Connected Domains": 30,
        "Active Domains with Evidence": 25,
        "Manual Records": 15,
        "Recent Activity Evidence": 15,
        "Missing Critical Domains": 15,
    },
}

SCORE_LABELS = {
    "agency_os": "Agency OS Readiness",
    "intelligence": "Intelligence",
    "team_readiness": "Team Readiness",
    "revenue_intelligence": "Revenue Intelligence",
    "recovery_safety": "Recovery Safety",
    "reliability": "Reliability",
    "agency_visibility": "Agency Visibility",
}

SCORE_ORDER = (
    "agency_os",
    "intelligence",
    "team_readiness",
    "revenue_intelligence",
    "recovery_safety",
    "reliability",
    "agency_visibility",
)

ROLE_HOME_FOUNDATION = {
    "owner": ("scores", "risks", "strategy", "systems"),
    "manager": ("tasks", "creators", "operations", "team"),
    "chatter": ("fans", "scripts", "training", "recommendations"),
    "va": ("posting", "checklists", "content ops"),
}


@dataclass(frozen=True)
class ScoreBreakdownItem:
    label: str
    weight: int
    earned: int
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {"label": self.label, "weight": self.weight, "earned": self.earned, "evidence": self.evidence}


@dataclass(frozen=True)
class LiveScore:
    score_name: str
    label: str
    score_percent: int
    confidence: str
    movement: str
    delta_since_last: int
    delta_period: str
    reason_for_change: str
    fastest_gain: str
    weak_spots: tuple[str, ...]
    evidence_summary: str
    score_breakdown: tuple[ScoreBreakdownItem, ...]
    evidence_version: str


@dataclass(frozen=True)
class Unlock:
    title: str
    impacted_score: str
    estimated_gain: int
    confidence: str
    why: str
    required_action: str
    dependencies: tuple[str, ...]
    status: str
    target_page: str


@dataclass(frozen=True)
class WeakSpot:
    weak_spot: str
    why_it_matters: str
    next_best_move: str
    urgency: str
    confidence: str
    target_page: str


@dataclass(frozen=True)
class CommandCenterReport:
    generated_at: datetime
    scores: dict[str, LiveScore]
    unlocks: tuple[Unlock, ...]
    weak_spots: tuple[WeakSpot, ...]
    fastest_gain: Unlock | None
    attention_items: tuple[str, ...]
    active_job_summary: str | None
    role_mode: str
    cache_status: str = "fresh"


def _now() -> datetime:
    return datetime.now(UTC)


_REPORT_CACHE_LOCK = threading.Lock()
_REPORT_CACHE_TTL_SECONDS = 90
_REPORT_CACHE: CommandCenterReport | None = None
_REPORT_CACHE_EXPIRES_AT: datetime | None = None


def _clamp(value: int | float, *, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, round(float(value))))


def _earned(weight: int, ratio: float) -> int:
    return _clamp(weight * ratio, low=0, high=weight)


def _count(session: Session, model, *criteria) -> int:
    try:
        statement = select(func.count(model.id))
        if criteria:
            statement = statement.where(*criteria)
        return int(session.scalar(statement) or 0)
    except SQLAlchemyError:
        session.rollback()
        return 0


def _latest_snapshot(session: Session, score_name: str) -> ScoreSnapshot | None:
    try:
        return session.scalar(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.score_name == score_name)
            .order_by(desc(ScoreSnapshot.generated_at), desc(ScoreSnapshot.id))
            .limit(1)
        )
    except SQLAlchemyError:
        session.rollback()
        return None


def _movement(delta: int) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _movement_reason(score_name: str, delta: int, weak_spots: tuple[str, ...]) -> str:
    if delta > 0:
        return f"{SCORE_LABELS[score_name]} improved because new evidence increased readiness."
    if delta < 0:
        return f"{SCORE_LABELS[score_name]} dropped because current evidence shows a wider gap."
    if weak_spots:
        return f"{SCORE_LABELS[score_name]} is steady. Weak spot: {weak_spots[0]}"
    return f"{SCORE_LABELS[score_name]} is steady based on current evidence."


def _confidence(score: int, evidence_points: int, missing_points: int = 0) -> str:
    if evidence_points >= 5 and missing_points == 0 and score >= 60:
        return "high"
    if evidence_points >= 3 and missing_points <= 2:
        return "medium"
    return "low"


def _evidence_version(name: str, breakdown: Iterable[ScoreBreakdownItem]) -> str:
    payload = json.dumps([item.to_dict() for item in breakdown], sort_keys=True)
    return hashlib.sha256(f"{name}:{payload}".encode("utf-8")).hexdigest()[:32]


def _score_from_breakdown(
    session: Session,
    *,
    score_name: str,
    breakdown: tuple[ScoreBreakdownItem, ...],
    fastest_gain: str,
    weak_spots: tuple[str, ...],
    evidence_summary: str,
    evidence_points: int,
    missing_points: int = 0,
) -> LiveScore:
    total_weight = sum(item.weight for item in breakdown) or 1
    percent = _clamp((sum(item.earned for item in breakdown) / total_weight) * 100)
    previous = _latest_snapshot(session, score_name)
    delta = 0 if previous is None else percent - previous.score_percent
    reason = _movement_reason(score_name, delta, weak_spots)
    return LiveScore(
        score_name=score_name,
        label=SCORE_LABELS[score_name],
        score_percent=percent,
        confidence=_confidence(percent, evidence_points, missing_points),
        movement=_movement(delta),
        delta_since_last=delta,
        delta_period="week",
        reason_for_change=reason,
        fastest_gain=fastest_gain,
        weak_spots=weak_spots,
        evidence_summary=evidence_summary,
        score_breakdown=breakdown,
        evidence_version=_evidence_version(score_name, breakdown),
    )


def _safe_system_truth(session: Session) -> SystemTruth | None:
    try:
        return system_truth(session)
    except Exception:
        session.rollback()
        return None


def _safe_recovery(session: Session) -> RecoveryAssessment | None:
    try:
        return recovery_risk_assessment(session)
    except Exception:
        session.rollback()
        return None


def _safe_agency(session: Session) -> AgencyAwarenessReport | None:
    try:
        return agency_awareness_report(session, persist=False)
    except Exception:
        session.rollback()
        return None


def _score_recovery_safety(session: Session, recovery: RecoveryAssessment | None) -> LiveScore:
    latest_backup = recovery.latest_backup if recovery else None
    latest_restore = recovery.latest_restore_test if recovery else None
    copies = recovery.backup_copies_count if recovery else 0
    storage_configured = bool(recovery and recovery.external_storage_configured)
    now = _now()
    if latest_backup is None:
        freshness = 0
        freshness_evidence = "No verified backup exists yet."
    else:
        age_hours = max(0, round((now - (latest_backup.started_at if latest_backup.started_at.tzinfo else latest_backup.started_at.replace(tzinfo=UTC))).total_seconds() / 3600))
        freshness = 25 if age_hours <= 24 else 18 if age_hours <= 72 else 10
        freshness_evidence = f"Latest verified backup is {age_hours}h old."
    backup_success = 25 if latest_backup and latest_backup.status in {"success", "succeeded"} and latest_backup.artifact_verified and latest_backup.checksum and latest_backup.encrypted else 0
    restore_score = 0
    restore_evidence = "No restore validation has been recorded."
    if latest_restore:
        if latest_restore.status in {"passed", "succeeded"} and latest_restore.full_restore_performed:
            restore_score = 25
            restore_evidence = "Full restore evidence exists."
        elif latest_restore.status in {"verified_only", "verified"}:
            restore_score = 15
            restore_evidence = "Restore artifact was verified, but full restore proof is still missing."
        elif latest_restore.status == "failed":
            restore_evidence = "Latest restore validation failed."
    breakdown = (
        ScoreBreakdownItem("Last Backup Freshness", 25, freshness, freshness_evidence),
        ScoreBreakdownItem("Backup Success Evidence", 25, backup_success, "Backup must be encrypted, uploaded, checksumed, and verified."),
        ScoreBreakdownItem("Restore Validation Evidence", 25, restore_score, restore_evidence),
        ScoreBreakdownItem("Redundancy / Second Copy", 15, 15 if copies >= 2 else 7 if copies == 1 else 0, f"{copies} recent verified backup copy/copies found."),
        ScoreBreakdownItem("Storage Health", 10, 10 if storage_configured else 0, "External backup storage is active." if storage_configured else "External backup storage is not active."),
    )
    weak = []
    if restore_score < 25:
        weak.append("Full restore proof is still missing.")
    if copies < 2:
        weak.append("A second independent backup copy would improve safety.")
    if not storage_configured:
        weak.append("External storage needs setup.")
    return _score_from_breakdown(
        session,
        score_name="recovery_safety",
        breakdown=breakdown,
        fastest_gain="Run a full restore drill or add a second backup copy.",
        weak_spots=tuple(weak),
        evidence_summary="Recovery score uses verified backup, restore, redundancy, and storage evidence.",
        evidence_points=sum(1 for item in (latest_backup, latest_restore) if item is not None) + int(storage_configured) + int(copies > 0),
        missing_points=len(weak),
    )


def _score_reliability(session: Session) -> LiveScore:
    summary = reliability_summary(session)
    cleanup = chat_cleanup_metrics(session)
    reliability_percent = int(summary.get("button_reliability") or 0)
    average_ms = int(summary.get("average_response_ms") or 0)
    active_issues = int(summary.get("active_issue_count") or 0)
    stale_ok = cleanup.status == "healthy"
    speed_ratio = 1.0 if average_ms < 500 else 0.8 if average_ms < 1500 else 0.45 if average_ms <= 3000 else 0.1
    active_issue_ratio = 1.0 if active_issues == 0 else 0.6 if active_issues <= 3 else 0.25 if active_issues <= 10 else 0.0
    breakdown = (
        ScoreBreakdownItem("Command Success", 25, _earned(25, reliability_percent / 100), f"Recent command/callback success is {reliability_percent}%."),
        ScoreBreakdownItem("Callback Success", 25, _earned(25, reliability_percent / 100), "Callback health uses current Reliability Center evidence."),
        ScoreBreakdownItem("Average Response Speed", 20, _earned(20, speed_ratio), f"Average response is {average_ms}ms."),
        ScoreBreakdownItem("Active Failure Count", 20, _earned(20, active_issue_ratio), f"{active_issues} active reliability issue(s) counted."),
        ScoreBreakdownItem("Stale Menu Safety", 10, 10 if stale_ok else 5, cleanup.evidence),
    )
    weak = []
    if active_issues:
        weak.append("Active reliability issues need revalidation or cleanup.")
    if average_ms >= 1500:
        weak.append("Some routes are still slow.")
    if not stale_ok:
        weak.append("Old menu cleanup needs another pass.")
    return _score_from_breakdown(
        session,
        score_name="reliability",
        breakdown=breakdown,
        fastest_gain="Run /verify_navigation and resolve any active Reliability Center issues.",
        weak_spots=tuple(weak),
        evidence_summary="Reliability score uses current route success, response speed, active issues, and stale menu safety.",
        evidence_points=4,
        missing_points=len(weak),
    )


def _score_agency_visibility(session: Session, agency: AgencyAwarenessReport | None) -> LiveScore:
    if agency is None:
        breakdown = (
            ScoreBreakdownItem("Connected Domains", 30, 0, "Agency Awareness is unavailable."),
            ScoreBreakdownItem("Active Domains with Evidence", 25, 0, "No live visibility snapshot is available."),
            ScoreBreakdownItem("Manual Records", 15, 0, "Manual agency records could not be checked."),
            ScoreBreakdownItem("Recent Activity Evidence", 15, 0, "No recent activity evidence could be checked."),
            ScoreBreakdownItem("Missing Critical Domains", 15, 0, "Missing visibility could not be assessed."),
        )
        return _score_from_breakdown(
            session,
            score_name="agency_visibility",
            breakdown=breakdown,
            fastest_gain="Open What Fortuna Can See after system health is verified.",
            weak_spots=("Agency Awareness is unavailable.",),
            evidence_summary="Agency visibility could not be calculated from live evidence.",
            evidence_points=0,
            missing_points=5,
        )
    manual_records = _count(session, AgencyManualRecord)
    recent_cutoff = _now() - timedelta(days=14)
    recent_evidence = _count(session, EvidenceRecord, EvidenceRecord.created_at >= recent_cutoff)
    connected = len([domain for domain in agency.domains if domain.status in {"active", "connected"}])
    active = len(agency.active_domains)
    missing = len(agency.missing_domains) + len(agency.not_connected_domains)
    domain_count = max(1, len(agency.domains))
    missing_ratio = max(0.0, 1.0 - min(1.0, missing / domain_count))
    breakdown = (
        ScoreBreakdownItem("Connected Domains", 30, _earned(30, connected / domain_count), f"{connected} domain(s) have live or connected evidence."),
        ScoreBreakdownItem("Active Domains with Evidence", 25, _earned(25, active / domain_count), f"{active} domain(s) are active."),
        ScoreBreakdownItem("Manual Records", 15, 15 if manual_records >= 3 else 8 if manual_records else 0, f"{manual_records} manual agency record(s) exist."),
        ScoreBreakdownItem("Recent Activity Evidence", 15, 15 if recent_evidence >= 5 else 8 if recent_evidence else 0, f"{recent_evidence} recent evidence record(s) found."),
        ScoreBreakdownItem("Missing Critical Domains", 15, _earned(15, missing_ratio), f"{missing} missing or not connected domain(s) remain."),
    )
    weak = []
    if agency.visibility_level == "low":
        weak.append("Creators, content, fans, or revenue activity need more evidence.")
    if manual_records == 0:
        weak.append("Add one manual creator/content activity record.")
    if missing:
        weak.append("Connect or document the most important missing agency area.")
    return _score_from_breakdown(
        session,
        score_name="agency_visibility",
        breakdown=breakdown,
        fastest_gain="Add one manual creator or content activity record.",
        weak_spots=tuple(weak),
        evidence_summary=agency.evidence_summary,
        evidence_points=2 + int(manual_records > 0) + int(recent_evidence > 0),
        missing_points=len(weak),
    )


def _score_intelligence(session: Session) -> LiveScore:
    ai_status = ai_configuration_status(session)
    search_status = search_configuration_status(session)
    memory_count = _count(session, DecisionMemory)
    evidence_count = _count(session, EvidenceRecord)
    knowledge_count = _count(session, KnowledgeMemory)
    prediction_count = _count(session, PredictiveCOOPrediction)
    outcome_count = _count(session, PredictionOutcome)
    trend_count = _count(session, DecisionQualityTrend)
    breakdown = (
        ScoreBreakdownItem("Decision Engine", 15, 15, "Decision Engine is available and used by Today/COO flows."),
        ScoreBreakdownItem("Decision Memory", 15, 15 if memory_count else 7, f"{memory_count} decision memory record(s) found."),
        ScoreBreakdownItem("AI Brain", 15, 15 if ai_status.get("configured") else 0, "AI Brain is configured." if ai_status.get("configured") else "AI Brain needs OPENAI_API_KEY."),
        ScoreBreakdownItem("Search Intelligence", 15, 15 if search_status.get("configured") else 0, "Search Intelligence is configured." if search_status.get("configured") else "Search needs Tavily configuration."),
        ScoreBreakdownItem("Reality Calibration", 15, 15 if outcome_count else 8, f"{outcome_count} prediction outcome record(s) found."),
        ScoreBreakdownItem("Knowledge Memory", 10, 10 if knowledge_count else 3, f"{knowledge_count} durable lesson(s) found."),
        ScoreBreakdownItem("Prediction Quality", 10, 10 if trend_count or prediction_count else 4, f"{prediction_count} prediction(s), {trend_count} trend record(s)."),
        ScoreBreakdownItem("Evidence Coverage", 5, 5 if evidence_count >= 5 else 3 if evidence_count else 0, f"{evidence_count} evidence record(s) available."),
    )
    weak = []
    if not ai_status.get("configured"):
        weak.append("AI Brain is not configured.")
    if not search_status.get("configured"):
        weak.append("Search Intelligence is not configured.")
    if evidence_count < 5:
        weak.append("More evidence records would improve reasoning.")
    return _score_from_breakdown(
        session,
        score_name="intelligence",
        breakdown=breakdown,
        fastest_gain="Add or validate more evidence for recommendations.",
        weak_spots=tuple(weak),
        evidence_summary="Intelligence score uses decisions, memory, AI/Search configuration, calibration, and evidence coverage.",
        evidence_points=sum(1 for value in (memory_count, evidence_count, knowledge_count, prediction_count, outcome_count, trend_count) if value > 0)
        + int(bool(ai_status.get("configured")))
        + int(bool(search_status.get("configured"))),
        missing_points=len(weak),
    )


def _score_team_readiness(session: Session, reliability: LiveScore) -> LiveScore:
    button_summary = button_health_summary(session)
    cleanup = chat_cleanup_metrics(session)
    role_metadata_score = 15
    help_score = 10
    screen_simplicity = 20 if button_summary.ux_issue_count == 0 else 12 if button_summary.ux_issue_count <= 3 else 5
    onboarding = 15 if reliability.score_percent >= 80 and button_summary.open_issue_count == 0 else 9 if reliability.score_percent >= 60 else 4
    breakdown = (
        ScoreBreakdownItem("Navigation Reliability", 25, _earned(25, reliability.score_percent / 100), "Navigation uses command shortcuts, Back/Home, and stale-menu protection."),
        ScoreBreakdownItem("Screen Simplicity", 20, screen_simplicity, f"{button_summary.ux_issue_count} open screen wording issue(s) found."),
        ScoreBreakdownItem("Role Metadata", 15, role_metadata_score, "Owner, Manager, Chatter, and VA role foundations are mapped."),
        ScoreBreakdownItem("Help Brain", 10, help_score, "Help Brain and command help are available."),
        ScoreBreakdownItem("Reliability Center", 15, 15, "Reliability Center is available."),
        ScoreBreakdownItem("Onboarding Friendliness", 15, onboarding, cleanup.evidence),
    )
    weak = []
    if reliability.score_percent < 80:
        weak.append("Reliability needs review before broad team rollout.")
    if button_summary.ux_issue_count:
        weak.append("Some screens still need simpler wording.")
    if cleanup.status != "healthy":
        weak.append("Old menu cleanup still needs review.")
    return _score_from_breakdown(
        session,
        score_name="team_readiness",
        breakdown=breakdown,
        fastest_gain="Use the Command Center and /verify_navigation for a new-teammate test.",
        weak_spots=tuple(weak),
        evidence_summary="Team Readiness uses navigation, screen clarity, role metadata, help, reliability, and onboarding evidence.",
        evidence_points=5,
        missing_points=len(weak),
    )


def _score_revenue_intelligence(session: Session) -> LiveScore:
    source_count = _count(session, SocialSource)
    source_quality_count = _count(session, SocialSourcePerformance)
    creator_count = _count(session, CreatorWatch) + _count(session, SocialSource)
    content_count = _count(session, PostWatch) + _count(session, SocialPost)
    chatter_count = _count(session, User, User.is_owner.is_(False), User.status == "active")
    opportunity_count = _count(session, Opportunity)
    fan_score = 0
    whale_score = 0
    breakdown = (
        ScoreBreakdownItem("Fan Data", 20, fan_score, "No fan data model is connected yet."),
        ScoreBreakdownItem("Whale Data", 20, whale_score, "No whale data model is connected yet."),
        ScoreBreakdownItem("Source Quality Data", 20, 20 if source_quality_count else 8 if source_count else 0, f"{source_quality_count} source performance record(s), {source_count} source(s)."),
        ScoreBreakdownItem("Creator Data", 15, 15 if creator_count else 6 if opportunity_count else 0, f"{creator_count} creator/source record(s), {opportunity_count} opportunity record(s)."),
        ScoreBreakdownItem("Content Data", 15, 15 if content_count else 0, f"{content_count} content/post watch record(s)."),
        ScoreBreakdownItem("Chatter Data", 10, 10 if chatter_count else 0, f"{chatter_count} active non-owner teammate record(s)."),
    )
    weak = ["Fan and whale data are not connected yet.", "Source-to-value data is still missing."]
    if creator_count == 0:
        weak.append("Creator activity needs first evidence.")
    if content_count == 0:
        weak.append("Content activity needs first evidence.")
    return _score_from_breakdown(
        session,
        score_name="revenue_intelligence",
        breakdown=breakdown,
        fastest_gain="Add the first fan, whale, or source-quality sample when revenue tracking begins.",
        weak_spots=tuple(weak),
        evidence_summary="Revenue Intelligence is intentionally low until fan, whale, source, creator, content, and chatter data exist.",
        evidence_points=sum(1 for value in (source_count, source_quality_count, creator_count, content_count, chatter_count, opportunity_count) if value > 0),
        missing_points=len(weak),
    )


def _score_agency_os(
    session: Session,
    *,
    truth: SystemTruth | None,
    recovery: LiveScore,
    reliability: LiveScore,
    intelligence: LiveScore,
    agency_visibility: LiveScore,
    revenue: LiveScore,
) -> LiveScore:
    infra_ratio = 0.0
    if truth is not None:
        checks = [
            truth.database_ready,
            bool(truth.database_durable),
            truth.redis_healthy,
            truth.migrations_current,
            truth.bot_polling_safe,
        ]
        infra_ratio = sum(1 for item in checks if item) / len(checks)
    breakdown = (
        ScoreBreakdownItem("Infrastructure / Health", 20, _earned(20, infra_ratio), "Database, Redis, migrations, and bot delivery are checked."),
        ScoreBreakdownItem("Recovery Safety", 15, _earned(15, recovery.score_percent / 100), recovery.evidence_summary),
        ScoreBreakdownItem("Reliability / UX", 15, _earned(15, reliability.score_percent / 100), reliability.evidence_summary),
        ScoreBreakdownItem("Intelligence Foundation", 20, _earned(20, intelligence.score_percent / 100), intelligence.evidence_summary),
        ScoreBreakdownItem("Agency Awareness", 15, _earned(15, agency_visibility.score_percent / 100), agency_visibility.evidence_summary),
        ScoreBreakdownItem("Revenue Intelligence", 15, _earned(15, revenue.score_percent / 100), revenue.evidence_summary),
    )
    weak = tuple(
        label
        for label, score in (
            ("Recovery still needs more protection.", recovery.score_percent),
            ("Reliability needs review before team rollout.", reliability.score_percent),
            ("Agency visibility needs more operational evidence.", agency_visibility.score_percent),
            ("Revenue Intelligence needs data.", revenue.score_percent),
        )
        if score < 70
    )
    return _score_from_breakdown(
        session,
        score_name="agency_os",
        breakdown=breakdown,
        fastest_gain="Add the smallest missing evidence source that improves visibility or safety.",
        weak_spots=weak,
        evidence_summary="Agency OS Readiness aggregates health, Recovery, Reliability, Intelligence, visibility, and revenue evidence.",
        evidence_points=4 + int(truth is not None),
        missing_points=len(weak),
    )


def _build_unlocks(scores: dict[str, LiveScore]) -> tuple[Unlock, ...]:
    unlocks = [
        Unlock(
            title="Complete full restore proof",
            impacted_score="Recovery Safety",
            estimated_gain=10,
            confidence="medium",
            why="Backups are verified, but full restore evidence is still the safety gap.",
            required_action="Run a full restore drill when a restore-test path is ready.",
            dependencies=("restore-test database/path",),
            status="available" if scores["recovery_safety"].score_percent < 90 else "completed",
            target_page="recovery_center",
        ),
        Unlock(
            title="Add creator/content activity",
            impacted_score="Agency Visibility",
            estimated_gain=9,
            confidence="medium",
            why="One manual agency record immediately improves what Fortuna can see.",
            required_action="Add a manual creator, content, or traffic update.",
            dependencies=("manual agency record",),
            status="available" if scores["agency_visibility"].score_percent < 70 else "completed",
            target_page="agency_awareness",
        ),
        Unlock(
            title="Add first revenue data sample",
            impacted_score="Revenue Intelligence",
            estimated_gain=12,
            confidence="low",
            why="Fan, whale, and source quality data are not connected yet.",
            required_action="Add the first fan, whale, or source-quality record when that workflow starts.",
            dependencies=("future revenue data source",),
            status="not_ready",
            target_page="command_center:operations",
        ),
        Unlock(
            title="Run command verification",
            impacted_score="Team Readiness",
            estimated_gain=5,
            confidence="high",
            why="A fresh command pass proves teammates can reach important screens.",
            required_action="Run /verify_navigation after UX changes deploy.",
            dependencies=("Telegram bot responsive",),
            status="available" if scores["team_readiness"].score_percent < 85 else "completed",
            target_page="reliability:verify",
        ),
    ]
    return tuple(unlocks)


def _build_weak_spots(scores: dict[str, LiveScore]) -> tuple[WeakSpot, ...]:
    items: list[WeakSpot] = []
    for name in SCORE_ORDER:
        score = scores[name]
        if score.score_percent >= 75:
            continue
        weak = score.weak_spots[0] if score.weak_spots else "More evidence would improve this score."
        items.append(
            WeakSpot(
                weak_spot=score.label,
                why_it_matters=weak,
                next_best_move=score.fastest_gain,
                urgency="high" if name in {"recovery_safety", "reliability"} and score.score_percent < 60 else "medium" if score.score_percent < 50 else "low",
                confidence=score.confidence,
                target_page={
                    "recovery_safety": "recovery_center",
                    "reliability": "reliability",
                    "agency_visibility": "agency_awareness",
                    "revenue_intelligence": "command_center:operations",
                    "intelligence": "command_center:intelligence",
                    "team_readiness": "reliability",
                    "agency_os": "command_center:scores",
                }.get(name, "command_center:scores"),
            )
        )
    return tuple(items)


def _attention_items(scores: dict[str, LiveScore], truth: SystemTruth | None = None) -> tuple[str, ...]:
    candidates: list[tuple[int, str]] = []
    if truth is not None and truth.database_backend == "sqlite_fallback":
        candidates.append((20, "Production Degraded: Fortuna is running in emergency storage mode. Data may not persist."))
    elif truth is not None and not truth.production_ready:
        candidates.append((12, "Production needs review in System Watch."))
    if scores["recovery_safety"].score_percent < 80:
        candidates.append((10, "Recovery still needs full restore proof or redundancy."))
    if scores["reliability"].score_percent < 80:
        candidates.append((9, "Reliability has active or recent issues to review."))
    if scores["agency_visibility"].score_percent < 55:
        candidates.append((6, "Fortuna needs more creator, content, fan, or source visibility."))
    if scores["revenue_intelligence"].score_percent < 30:
        candidates.append((4, "Revenue Intelligence needs its first data sources."))
    return tuple(item for _priority, item in sorted(candidates, reverse=True)[:3])


def _active_job_summary(session: Session) -> str | None:
    jobs = active_jobs(session)
    if not jobs:
        return None
    job = jobs[0]
    label = job.job_type.replace("_", " ").title()
    step = job.current_step or job.status.title()
    return f"{label}: {step}"


def record_score_snapshots(session: Session, scores: Iterable[LiveScore], *, generated_at: datetime | None = None) -> tuple[ScoreSnapshot, ...]:
    created: list[ScoreSnapshot] = []
    now = generated_at or _now()
    for score in scores:
        previous = _latest_snapshot(session, score.score_name)
        if previous and previous.evidence_version == score.evidence_version and abs(previous.score_percent - score.score_percent) < 2 and previous.confidence == score.confidence:
            continue
        snapshot = ScoreSnapshot(
            score_name=score.score_name,
            score_percent=score.score_percent,
            confidence=score.confidence,
            movement=score.movement,
            movement_delta=score.delta_since_last,
            delta_period=score.delta_period,
            reason_for_change=score.reason_for_change,
            generated_at=now,
            evidence_version=score.evidence_version,
            score_breakdown=[item.to_dict() for item in score.score_breakdown],
        )
        session.add(snapshot)
        created.append(snapshot)
    if created:
        session.flush()
    return tuple(created)


def build_command_center_report(session: Session, *, persist: bool = False) -> CommandCenterReport:
    truth = _safe_system_truth(session)
    recovery_assessment = _safe_recovery(session)
    agency = _safe_agency(session)

    recovery = _score_recovery_safety(session, recovery_assessment)
    reliability = _score_reliability(session)
    agency_visibility = _score_agency_visibility(session, agency)
    intelligence = _score_intelligence(session)
    team = _score_team_readiness(session, reliability)
    revenue = _score_revenue_intelligence(session)
    agency_os = _score_agency_os(
        session,
        truth=truth,
        recovery=recovery,
        reliability=reliability,
        intelligence=intelligence,
        agency_visibility=agency_visibility,
        revenue=revenue,
    )
    scores = {
        "agency_os": agency_os,
        "intelligence": intelligence,
        "team_readiness": team,
        "revenue_intelligence": revenue,
        "recovery_safety": recovery,
        "reliability": reliability,
        "agency_visibility": agency_visibility,
    }
    if persist:
        record_score_snapshots(session, scores.values())
    unlocks = _build_unlocks(scores)
    available_unlocks = [unlock for unlock in unlocks if unlock.status == "available"]
    fastest_gain = sorted(available_unlocks or list(unlocks), key=lambda item: item.estimated_gain, reverse=True)[0] if unlocks else None
    return CommandCenterReport(
        generated_at=_now(),
        scores=scores,
        unlocks=unlocks,
        weak_spots=_build_weak_spots(scores),
        fastest_gain=fastest_gain,
        attention_items=_attention_items(scores, truth),
        active_job_summary=_active_job_summary(session),
        role_mode="owner",
    )


def cached_command_center_report(
    session: Session,
    *,
    force_refresh: bool = False,
    persist: bool = False,
    ttl_seconds: int = _REPORT_CACHE_TTL_SECONDS,
) -> CommandCenterReport:
    """Return a short-lived deterministic score report for fast UI navigation.

    Scores are still calculated by the same deterministic engine. The cache only
    keeps repeated Home/menu taps from re-running every query before the user sees
    a response.
    """
    global _REPORT_CACHE, _REPORT_CACHE_EXPIRES_AT
    now = _now()
    with _REPORT_CACHE_LOCK:
        cached = _REPORT_CACHE
        expires_at = _REPORT_CACHE_EXPIRES_AT
        if not force_refresh and cached is not None and expires_at is not None and expires_at > now:
            return CommandCenterReport(
                generated_at=cached.generated_at,
                scores=cached.scores,
                unlocks=cached.unlocks,
                weak_spots=cached.weak_spots,
                fastest_gain=cached.fastest_gain,
                attention_items=cached.attention_items,
                active_job_summary=cached.active_job_summary,
                role_mode=cached.role_mode,
                cache_status="cached",
            )

    report = build_command_center_report(session, persist=persist)
    with _REPORT_CACHE_LOCK:
        _REPORT_CACHE = report
        _REPORT_CACHE_EXPIRES_AT = now + timedelta(seconds=ttl_seconds)
    return report


def refresh_command_center_score_snapshots() -> None:
    """Best-effort score snapshot persistence outside the callback response path."""
    from app.db.session import SessionLocal

    if SessionLocal is None:
        return
    try:
        with SessionLocal() as session:
            report = cached_command_center_report(session, force_refresh=True, persist=False)
            record_score_snapshots(session, report.scores.values())
            session.commit()
    except Exception:
        # Snapshot history is useful, but it must never slow or break navigation.
        return
