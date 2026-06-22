from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.agency_awareness import AgencyManualRecord
from app.models.agency_drift import AgencyDriftFinding, AgencyExpectation, AgencyPlan
from app.models.evidence import EvidenceRecord
from app.models.help import UISelfTestRun
from app.models.reliability import CallbackLatencyRecord
from app.services.agency_awareness import agency_awareness_report
from app.services.audit import sanitize_details
from app.services.recovery import recovery_risk_assessment
from app.services.reliability import reliability_summary


ACTIVE_FINDING_STATUSES = {"active", "needs_review", "reappeared"}
RESOLVED_PLAN_STATUSES = {"paused", "completed", "cancelled"}


@dataclass(frozen=True)
class PlanTemplate:
    key: str
    title: str
    domain: str
    owner_role: str
    expected_cadence: str
    expected_signal: str
    confidence: str
    evidence_summary: str


@dataclass(frozen=True)
class AgencyDriftReport:
    generated_at: datetime
    status: str
    checked: tuple[str, ...]
    active_findings: tuple[AgencyDriftFinding, ...]
    resolved_findings: tuple[AgencyDriftFinding, ...]
    plans: tuple[AgencyPlan, ...]
    top_drift: AgencyDriftFinding | None
    next_best_move: str
    evidence_summary: str
    visibility_gap_count: int


STARTER_TEMPLATES: tuple[PlanTemplate, ...] = (
    PlanTemplate(
        key="backup_freshness",
        title="Keep backups fresh and restore proof honest",
        domain="recovery",
        owner_role="owner",
        expected_cadence="daily",
        expected_signal="Fresh verified backup plus honest restore validation",
        confidence="high",
        evidence_summary="Internal system expectation created by Fortuna for Recovery safety.",
    ),
    PlanTemplate(
        key="reliability_check",
        title="Keep Reliability Center clean",
        domain="reliability",
        owner_role="owner",
        expected_cadence="daily",
        expected_signal="Reliability Center has no active blockers",
        confidence="high",
        evidence_summary="Internal system expectation created by Fortuna for team rollout safety.",
    ),
    PlanTemplate(
        key="selftest_health",
        title="Keep Self-Test non-critical",
        domain="reliability",
        owner_role="owner",
        expected_cadence="daily",
        expected_signal="/selftest stays healthy or has only non-blocking warnings",
        confidence="medium",
        evidence_summary="Internal system expectation created by Fortuna for system confidence.",
    ),
    PlanTemplate(
        key="command_verification",
        title="Verify important commands regularly",
        domain="reliability",
        owner_role="owner",
        expected_cadence="weekly",
        expected_signal="/verify_navigation passes",
        confidence="medium",
        evidence_summary="Internal system expectation created by Fortuna for navigation reliability.",
    ),
    PlanTemplate(
        key="agency_visibility",
        title="Improve agency visibility",
        domain="agency_visibility",
        owner_role="owner",
        expected_cadence="weekly",
        expected_signal="New manual or system evidence improves what Fortuna can see",
        confidence="low",
        evidence_summary="Internal system expectation created by Fortuna for awareness coverage.",
    ),
)


MANUAL_PLAN_TEMPLATES: dict[str, PlanTemplate] = {
    "posting": PlanTemplate(
        key="posting",
        title="Posting cadence plan",
        domain="content",
        owner_role="manager",
        expected_cadence="daily",
        expected_signal="Manual content activity record",
        confidence="low",
        evidence_summary="Owner-created plan template. Missing data starts as a visibility gap.",
    ),
    "creator_outreach": PlanTemplate(
        key="creator_outreach",
        title="Creator outreach plan",
        domain="creators",
        owner_role="manager",
        expected_cadence="weekly",
        expected_signal="Manual creator outreach activity record",
        confidence="low",
        evidence_summary="Owner-created plan template. Missing data starts as a visibility gap.",
    ),
    "fan_whale_tracking": PlanTemplate(
        key="fan_whale_tracking",
        title="Fan and whale tracking plan",
        domain="fans",
        owner_role="manager",
        expected_cadence="weekly",
        expected_signal="Manual fan or whale activity record",
        confidence="low",
        evidence_summary="Owner-created plan template. Missing data starts as a visibility gap.",
    ),
    "recovery_check": PlanTemplate(
        key="recovery_check",
        title="Recovery/system check plan",
        domain="reliability",
        owner_role="owner",
        expected_cadence="daily",
        expected_signal="Manual reliability or recovery check record",
        confidence="medium",
        evidence_summary="Owner-created plan template for daily system checks.",
    ),
    "custom_placeholder": PlanTemplate(
        key="custom_placeholder",
        title="Custom plan placeholder",
        domain="operations",
        owner_role="owner",
        expected_cadence="weekly",
        expected_signal="Manual update record",
        confidence="low",
        evidence_summary="Placeholder plan. Edit support can refine this later.",
    ),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _cadence_window(cadence: str) -> timedelta:
    value = (cadence or "").casefold()
    if "daily" in value or "24" in value:
        return timedelta(hours=30)
    if "monthly" in value:
        return timedelta(days=40)
    if "weekly" in value or "monday" in value:
        return timedelta(days=9)
    return timedelta(days=9)


def _cadence_next_check(cadence: str, start: datetime | None = None) -> datetime:
    return (start or _now()) + _cadence_window(cadence)


def _metadata_key(plan: AgencyPlan) -> str | None:
    metadata = plan.metadata_json or {}
    value = metadata.get("starter_key") or metadata.get("template_key")
    return str(value) if value else None


def _active_plans(session: Session) -> list[AgencyPlan]:
    return list(
        session.scalars(
            select(AgencyPlan).where(AgencyPlan.status == "active").order_by(AgencyPlan.start_at, AgencyPlan.id)
        ).all()
    )


def _latest_manual_record(session: Session, domain: str) -> AgencyManualRecord | None:
    domains = {domain}
    if domain == "fans":
        domains.add("whales")
    return session.scalar(
        select(AgencyManualRecord)
        .where(AgencyManualRecord.domain_id.in_(domains))
        .order_by(desc(AgencyManualRecord.created_at), desc(AgencyManualRecord.id))
        .limit(1)
    )


def _latest_evidence_at(session: Session) -> datetime | None:
    evidence_at = session.scalar(select(func.max(EvidenceRecord.created_at)))
    manual_at = session.scalar(select(func.max(AgencyManualRecord.created_at)))
    values = [_aware(value) for value in (evidence_at, manual_at) if value is not None]
    return max(values) if values else None


def _latest_command_success(session: Session, route: str) -> datetime | None:
    return _aware(
        session.scalar(
            select(func.max(CallbackLatencyRecord.received_at)).where(
                CallbackLatencyRecord.callback_route == route,
                CallbackLatencyRecord.result == "succeeded",
            )
        )
    )


def _resolve_findings_for_plan(session: Session, plan: AgencyPlan, *, reason: str, resolved_at: datetime) -> None:
    rows = session.scalars(
        select(AgencyDriftFinding).where(
            AgencyDriftFinding.plan_id == plan.id,
            AgencyDriftFinding.status.in_(tuple(ACTIVE_FINDING_STATUSES)),
        )
    ).all()
    for finding in rows:
        finding.status = "resolved"
        finding.resolved_at = resolved_at
        finding.last_seen_at = resolved_at
        finding.observed = reason
        metadata = dict(finding.metadata_json or {})
        metadata["resolved_by"] = reason
        finding.metadata_json = sanitize_details(metadata)


def _upsert_finding(
    session: Session,
    plan: AgencyPlan,
    *,
    expected: str,
    observed: str,
    gap: str,
    severity: str,
    confidence: str,
    status: str,
    next_best_move: str,
    evidence_records: Iterable[str] = (),
    metadata: dict | None = None,
) -> AgencyDriftFinding:
    current = _now()
    active = session.scalar(
        select(AgencyDriftFinding)
        .where(
            AgencyDriftFinding.plan_id == plan.id,
            AgencyDriftFinding.gap == gap,
            AgencyDriftFinding.status.in_(tuple(ACTIVE_FINDING_STATUSES)),
        )
        .order_by(desc(AgencyDriftFinding.last_seen_at), desc(AgencyDriftFinding.id))
        .limit(1)
    )
    if active is None:
        resolved = session.scalar(
            select(AgencyDriftFinding)
            .where(
                AgencyDriftFinding.plan_id == plan.id,
                AgencyDriftFinding.gap == gap,
                AgencyDriftFinding.status.in_(("resolved", "historical")),
            )
            .order_by(desc(AgencyDriftFinding.last_seen_at), desc(AgencyDriftFinding.id))
            .limit(1)
        )
        active = AgencyDriftFinding(
            plan_id=plan.id,
            domain=plan.domain,
            expected=expected,
            observed=observed,
            gap=gap,
            severity=severity,
            confidence=confidence,
            status="reappeared" if resolved is not None and status == "active" else status,
            next_best_move=next_best_move,
            evidence_records=list(evidence_records),
            first_seen_at=current,
            last_seen_at=current,
            metadata_json=sanitize_details(metadata or {}),
        )
        session.add(active)
    else:
        active.expected = expected
        active.observed = observed
        active.severity = severity
        active.confidence = confidence
        active.status = status
        active.next_best_move = next_best_move
        active.evidence_records = list(evidence_records)
        active.last_seen_at = current
        active.metadata_json = sanitize_details(metadata or active.metadata_json or {})
    session.flush()
    return active


def ensure_default_drift_plans(session: Session) -> tuple[AgencyPlan, ...]:
    existing = {
        _metadata_key(plan): plan
        for plan in session.scalars(select(AgencyPlan).where(AgencyPlan.status.in_(("active", "paused")))).all()
        if _metadata_key(plan)
    }
    created: list[AgencyPlan] = []
    now = _now()
    for template in STARTER_TEMPLATES:
        if template.key in existing:
            continue
        plan = AgencyPlan(
            title=template.title,
            domain=template.domain,
            owner_role=template.owner_role,
            expected_cadence=template.expected_cadence,
            expected_signal=template.expected_signal,
            start_at=now,
            status="active",
            confidence=template.confidence,
            evidence_summary=template.evidence_summary,
            metadata_json={"starter_key": template.key, "source": "default_internal_expectation"},
        )
        session.add(plan)
        session.flush()
        session.add(
            AgencyExpectation(
                plan_id=plan.id,
                title=plan.title,
                domain=plan.domain,
                expected_cadence=plan.expected_cadence,
                expected_signal=plan.expected_signal,
                status=plan.status,
                confidence=plan.confidence,
                next_check_at=_cadence_next_check(plan.expected_cadence, now),
                evidence_summary=plan.evidence_summary,
                metadata_json={"starter_key": template.key},
            )
        )
        created.append(plan)
    if created:
        session.flush()
    return tuple(created)


def create_manual_plan_from_template(session: Session, template_key: str, *, created_by: str = "owner") -> AgencyPlan:
    template = MANUAL_PLAN_TEMPLATES.get(template_key) or MANUAL_PLAN_TEMPLATES["custom_placeholder"]
    for existing in session.scalars(select(AgencyPlan).where(AgencyPlan.status.in_(("active", "paused")))).all():
        if (existing.metadata_json or {}).get("template_key") == template.key:
            return existing
    now = _now()
    plan = AgencyPlan(
        title=template.title,
        domain=template.domain,
        owner_role=template.owner_role,
        expected_cadence=template.expected_cadence,
        expected_signal=template.expected_signal,
        start_at=now,
        status="active",
        confidence=template.confidence,
        evidence_summary=template.evidence_summary,
        metadata_json={"template_key": template.key, "created_by": created_by, "manual": True},
    )
    session.add(plan)
    session.flush()
    session.add(
        AgencyExpectation(
            plan_id=plan.id,
            title=plan.title,
            domain=plan.domain,
            expected_cadence=plan.expected_cadence,
            expected_signal=plan.expected_signal,
            status=plan.status,
            confidence=plan.confidence,
            next_check_at=_cadence_next_check(plan.expected_cadence, now),
            evidence_summary=plan.evidence_summary,
            metadata_json={"template_key": template.key, "manual": True},
        )
    )
    session.flush()
    return plan


def set_plan_status(session: Session, plan_id: int, status: str) -> AgencyPlan | None:
    if status not in {"active", "paused", "completed", "cancelled"}:
        return None
    plan = session.get(AgencyPlan, plan_id)
    if plan is None:
        return None
    plan.status = status
    for expectation in session.scalars(select(AgencyExpectation).where(AgencyExpectation.plan_id == plan.id)).all():
        expectation.status = status
        expectation.last_checked_at = _now()
    if status in RESOLVED_PLAN_STATUSES:
        _resolve_findings_for_plan(session, plan, reason=f"Plan marked {status}.", resolved_at=_now())
    session.flush()
    return plan


class AgencyDriftEngine:
    def __init__(self, *, include_starter_expectations: bool = True) -> None:
        self.include_starter_expectations = include_starter_expectations

    def generate(self, session: Session, *, persist: bool = True) -> AgencyDriftReport:
        if self.include_starter_expectations:
            ensure_default_drift_plans(session)
        current = _now()
        checked: list[str] = []
        for plan in _active_plans(session):
            checked.append(plan.domain)
            self._evaluate_plan(session, plan, current=current)
        if persist:
            session.flush()
        return self._build_report(session, current=current)

    def safe_generate(self, session: Session, *, persist: bool = True) -> AgencyDriftReport:
        try:
            return self.generate(session, persist=persist)
        except Exception:
            session.rollback()
            current = _now()
            return AgencyDriftReport(
                generated_at=current,
                status="needs_review",
                checked=("unavailable",),
                active_findings=(),
                resolved_findings=(),
                plans=tuple(session.scalars(select(AgencyPlan).order_by(desc(AgencyPlan.start_at), desc(AgencyPlan.id)).limit(10)).all()),
                top_drift=None,
                next_best_move="Drift Detection is unavailable. Open Reliability Center and try again.",
                evidence_summary="Drift check failed safely. Fortuna did not invent findings.",
                visibility_gap_count=0,
            )

    def _evaluate_plan(self, session: Session, plan: AgencyPlan, *, current: datetime) -> None:
        key = _metadata_key(plan)
        if key == "backup_freshness":
            self._evaluate_recovery(session, plan, current=current)
        elif key == "reliability_check":
            self._evaluate_reliability(session, plan, current=current)
        elif key == "selftest_health":
            self._evaluate_selftest(session, plan, current=current)
        elif key == "command_verification":
            self._evaluate_command_verification(session, plan, current=current)
        elif key == "agency_visibility":
            self._evaluate_visibility(session, plan, current=current)
        else:
            self._evaluate_manual_plan(session, plan, current=current)

    def _evaluate_recovery(self, session: Session, plan: AgencyPlan, *, current: datetime) -> None:
        recovery = recovery_risk_assessment(session)
        backup = recovery.latest_backup
        restore = recovery.latest_restore_test
        if backup is None:
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed="No verified backup evidence is visible yet.",
                gap="backup_evidence_missing",
                severity="high",
                confidence="medium",
                status="active",
                next_best_move=recovery.next_best_move,
                evidence_records=("RecoveryAssessment:no_latest_backup",),
            )
            return
        backup_at = _aware(backup.finished_at or backup.started_at)
        if backup_at and current - backup_at > timedelta(hours=30):
            _upsert_finding(
                session,
                plan,
                expected="Fresh verified backup within roughly 24 hours.",
                observed=f"Latest verified backup is older than the freshness target ({backup_at.date().isoformat()}).",
                gap="backup_stale",
                severity="medium",
                confidence="high",
                status="active",
                next_best_move="Run a fresh backup.",
                evidence_records=(f"BackupRun:{backup.id}",),
            )
            return
        if restore is None or not restore.full_restore_performed:
            _upsert_finding(
                session,
                plan,
                expected="Backup is verified and restore proof is honest.",
                observed="Backup evidence exists, but full restore proof is still missing.",
                gap="full_restore_proof_missing",
                severity="medium",
                confidence="high" if restore is not None else "medium",
                status="needs_review",
                next_best_move="Run a full restore drill when the restore-test path is ready.",
                evidence_records=(f"BackupRun:{backup.id}", f"RestoreTestRun:{restore.id}" if restore else "RestoreTestRun:none"),
            )
            return
        _resolve_findings_for_plan(session, plan, reason="Backup is fresh and full restore proof exists.", resolved_at=current)

    def _evaluate_reliability(self, session: Session, plan: AgencyPlan, *, current: datetime) -> None:
        summary = reliability_summary(session)
        active = int(summary.get("active_issue_count") or 0)
        if active:
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed=f"Reliability Center reports {active} active issue(s).",
                gap="reliability_active_issue",
                severity="high",
                confidence="high",
                status="active",
                next_best_move="Open Reliability Center and fix the active issue.",
                evidence_records=("ReliabilitySummary:active_issue_count",),
            )
            return
        if str(summary.get("status")) != "healthy":
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed="Reliability has a non-blocking note, not an active crash.",
                gap="reliability_non_blocking_note",
                severity="low",
                confidence="medium",
                status="needs_review",
                next_best_move="Review Slow Buttons when convenient.",
                evidence_records=("ReliabilitySummary:non_blocking",),
            )
            return
        _resolve_findings_for_plan(session, plan, reason="Reliability Center has no active blockers.", resolved_at=current)

    def _evaluate_selftest(self, session: Session, plan: AgencyPlan, *, current: datetime) -> None:
        latest_run = session.scalar(select(UISelfTestRun).order_by(desc(UISelfTestRun.created_at), desc(UISelfTestRun.id)).limit(1))
        latest_command = _latest_command_success(session, "command:selftest")
        latest_seen = max([value for value in (_aware(latest_run.created_at) if latest_run else None, latest_command) if value is not None], default=None)
        if latest_run is not None and latest_run.status == "failed":
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed="Latest UI self-test failed.",
                gap="selftest_failed",
                severity="high",
                confidence="high",
                status="active",
                next_best_move="Open /selftest details and fix the failing check.",
                evidence_records=(f"UISelfTestRun:{latest_run.id}",),
            )
            return
        if latest_seen is None or current - latest_seen > timedelta(days=2):
            _upsert_finding(
                session,
                plan,
                expected="Recent self-test evidence.",
                observed="No recent self-test evidence is visible.",
                gap="selftest_recent_evidence_missing",
                severity="low",
                confidence="low",
                status="needs_review",
                next_best_move="Run /selftest when convenient.",
                evidence_records=("UISelfTestRun:none_recent",),
            )
            return
        _resolve_findings_for_plan(session, plan, reason="Recent self-test evidence is non-critical.", resolved_at=current)

    def _evaluate_command_verification(self, session: Session, plan: AgencyPlan, *, current: datetime) -> None:
        latest = _latest_command_success(session, "command:verify_navigation")
        if latest is None or current - latest > timedelta(days=9):
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed="No recent passing command verification is visible.",
                gap="command_verification_missing",
                severity="low",
                confidence="low",
                status="needs_review",
                next_best_move="Run /verify_navigation after releases or UX changes.",
                evidence_records=("CallbackLatencyRecord:command:verify_navigation",),
            )
            return
        _resolve_findings_for_plan(session, plan, reason="/verify_navigation passed recently.", resolved_at=current)

    def _evaluate_visibility(self, session: Session, plan: AgencyPlan, *, current: datetime) -> None:
        latest_evidence = _latest_evidence_at(session)
        awareness = agency_awareness_report(session, persist=False)
        if latest_evidence is None:
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed="No manual or system evidence has been added yet.",
                gap="agency_visibility_gap",
                severity="low",
                confidence="low",
                status="needs_review",
                next_best_move=awareness.next_best_move,
                evidence_records=("EvidenceRecord:none", "AgencyManualRecord:none"),
                metadata={"visibility_level": awareness.visibility_level},
            )
            return
        if current - latest_evidence > timedelta(days=9) and awareness.visibility_level == "low":
            _upsert_finding(
                session,
                plan,
                expected="Agency visibility improves through fresh evidence.",
                observed="Agency visibility remains low and evidence has not changed this week.",
                gap="agency_visibility_stale",
                severity="low",
                confidence="medium",
                status="needs_review",
                next_best_move=awareness.next_best_move,
                evidence_records=("AgencyAwarenessReport:low_visibility",),
                metadata={"visibility_level": awareness.visibility_level},
            )
            return
        _resolve_findings_for_plan(session, plan, reason="Agency visibility has recent evidence or is not currently low.", resolved_at=current)

    def _evaluate_manual_plan(self, session: Session, plan: AgencyPlan, *, current: datetime) -> None:
        record = _latest_manual_record(session, plan.domain)
        if record is None:
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed="Fortuna has no matching manual or system record yet.",
                gap="visibility_gap_no_manual_record",
                severity="low",
                confidence="low",
                status="needs_review",
                next_best_move="Add a manual update or pause the plan if this work is not active.",
                evidence_records=(f"AgencyManualRecord:{plan.domain}:none",),
                metadata={"visibility_gap": True},
            )
            return
        record_at = _aware(record.created_at) or current
        if current - record_at > _cadence_window(plan.expected_cadence):
            _upsert_finding(
                session,
                plan,
                expected=plan.expected_signal,
                observed=f"Last matching manual record was {record_at.date().isoformat()}.",
                gap="expected_activity_stale",
                severity="medium",
                confidence="medium",
                status="active",
                next_best_move="Update the plan with what happened, or pause it if the work is intentionally stopped.",
                evidence_records=(f"AgencyManualRecord:{record.id}",),
            )
            return
        _resolve_findings_for_plan(session, plan, reason="Expected activity has recent manual evidence.", resolved_at=current)

    def _build_report(self, session: Session, *, current: datetime) -> AgencyDriftReport:
        active = tuple(
            session.scalars(
                select(AgencyDriftFinding)
                .where(AgencyDriftFinding.status.in_(tuple(ACTIVE_FINDING_STATUSES)))
                .order_by(desc(AgencyDriftFinding.severity), desc(AgencyDriftFinding.last_seen_at), desc(AgencyDriftFinding.id))
                .limit(20)
            ).all()
        )
        resolved = tuple(
            session.scalars(
                select(AgencyDriftFinding)
                .where(AgencyDriftFinding.status.in_(("resolved", "historical")))
                .order_by(desc(AgencyDriftFinding.resolved_at), desc(AgencyDriftFinding.id))
                .limit(20)
            ).all()
        )
        plans = tuple(
            session.scalars(
                select(AgencyPlan).order_by(desc(AgencyPlan.status == "active"), desc(AgencyPlan.start_at), desc(AgencyPlan.id)).limit(30)
            ).all()
        )
        top = active[0] if active else None
        visibility_gap_count = sum(1 for item in active if item.status == "needs_review" or "visibility" in item.gap)
        status = "learning"
        if any(item.severity == "high" and item.status in {"active", "reappeared"} for item in active):
            status = "needs_review"
        elif active:
            status = "learning"
        next_move = top.next_best_move if top else "No active drift. Keep plans updated as reality changes."
        checked = tuple(dict.fromkeys(plan.domain for plan in plans if plan.status == "active")) or ("no active plans",)
        return AgencyDriftReport(
            generated_at=current,
            status=status,
            checked=checked,
            active_findings=active,
            resolved_findings=resolved,
            plans=plans,
            top_drift=top,
            next_best_move=next_move,
            evidence_summary="Drift compares active expectations with current system and manual evidence.",
            visibility_gap_count=visibility_gap_count,
        )


def agency_drift_report(session: Session, *, persist: bool = True) -> AgencyDriftReport:
    return AgencyDriftEngine().safe_generate(session, persist=persist)


def drift_attention_item(session: Session) -> str | None:
    try:
        report = agency_drift_report(session, persist=False)
    except (SQLAlchemyError, Exception):
        session.rollback()
        return None
    top = report.top_drift
    if top is None:
        return None
    if top.status == "needs_review" and top.severity == "low":
        return None
    return top.next_best_move or top.gap


def drift_score_pressure(session: Session) -> dict[str, int]:
    try:
        report = agency_drift_report(session, persist=False)
    except (SQLAlchemyError, Exception):
        session.rollback()
        return {}
    pressure = {"agency_os": 0, "team_readiness": 0, "agency_visibility": 0, "recovery_safety": 0}
    for finding in report.active_findings:
        value = 6 if finding.severity == "high" else 3 if finding.severity == "medium" else 1
        if finding.status == "needs_review":
            value = min(value, 2)
        pressure["agency_os"] += value
        if finding.domain == "reliability":
            pressure["team_readiness"] += value
        if finding.domain in {"agency_visibility", "creators", "content", "fans", "whales"}:
            pressure["agency_visibility"] += value
        if finding.domain == "recovery":
            pressure["recovery_safety"] += value
    return {key: min(10, amount) for key, amount in pressure.items() if amount > 0}
