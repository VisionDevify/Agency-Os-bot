from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.callback_error import CallbackErrorLog
from app.models.recommendation import Recommendation
from app.services.audit import sanitize_details
from app.services.build_metadata import safe_build_metadata

ISSUE_LIFECYCLE_STATES = (
    "active",
    "validating",
    "resolved",
    "historical",
    "ignored",
    "stale",
    "reappeared",
)


@dataclass(frozen=True)
class IssueLifecycleView:
    issue_id: int
    issue_type: str
    source: str
    status: str
    evidence_summary: str
    next_action: str
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    fixed_by_commit: str | None = None
    revalidated_at: datetime | None = None
    revalidated_commit: str | None = None


@dataclass(frozen=True)
class IssueRevalidationResult:
    active_count: int
    validating_count: int
    resolved_count: int
    historical_count: int
    ignored_count: int
    stale_count: int
    reappeared_count: int
    revalidated_at: datetime | None
    revalidated_commit: str | None
    evidence_summary: str


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class IssueRevalidationEngine:
    """Classify issue history against current evidence without deleting audit records."""

    def __init__(
        self,
        *,
        current_commit: str | None = None,
        revalidated_at: datetime | None = None,
    ) -> None:
        metadata = safe_build_metadata()
        self.current_commit = current_commit or metadata.get("git_commit") or "unknown"
        self.revalidated_at = _as_aware(revalidated_at)

    def classify_callback_error(
        self,
        error: CallbackErrorLog,
        *,
        working_pages: set[str] | None = None,
        failing_pages: set[str] | None = None,
    ) -> IssueLifecycleView:
        working_pages = working_pages or set()
        failing_pages = failing_pages or set()
        page = error.page or error.callback_data or "unknown"
        first_seen = _as_aware(error.created_at)
        last_seen = first_seen

        if page in failing_pages:
            status = "reappeared" if self.revalidated_at and first_seen and first_seen < self.revalidated_at else "active"
            return IssueLifecycleView(
                issue_id=error.id,
                issue_type="callback_failure",
                source=page,
                status=status,
                evidence_summary="Fresh callback scan still reproduces this route failure.",
                next_action="Fix the callback route, then run Button Health again.",
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                revalidated_at=self.revalidated_at,
                revalidated_commit=self.current_commit,
            )

        if self.revalidated_at and first_seen and first_seen > self.revalidated_at:
            status = "active"
            evidence = "Failure occurred after the latest revalidation boundary."
            action = "Run Button Health and inspect the failing route."
        elif page in working_pages and self.revalidated_at:
            return IssueLifecycleView(
                issue_id=error.id,
                issue_type="callback_failure",
                source=page,
                status="historical",
                evidence_summary="Fresh callback scan passed after this failure was logged.",
                next_action="Keep as audit history. No active action needed.",
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                fixed_by_commit=self.current_commit,
                revalidated_at=self.revalidated_at,
                revalidated_commit=self.current_commit,
            )
        elif self.revalidated_at is None:
            status = "active"
            evidence = "No successful revalidation has been recorded after this failure yet."
            action = "Run Button Health and inspect the failing route."
        else:
            status = "validating"
            evidence = "No fresh targeted revalidation evidence is available for this route yet."
            action = "Run Button Health to revalidate this callback."
        return IssueLifecycleView(
            issue_id=error.id,
            issue_type="callback_failure",
            source=page,
            status=status,
            evidence_summary=evidence,
            next_action=action,
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            revalidated_at=self.revalidated_at,
            revalidated_commit=self.current_commit if self.revalidated_at else None,
        )

    def summarize(self, views: list[IssueLifecycleView]) -> IssueRevalidationResult:
        counts = {state: 0 for state in ISSUE_LIFECYCLE_STATES}
        for view in views:
            counts[view.status] = counts.get(view.status, 0) + 1
        if self.revalidated_at:
            evidence = "Lifecycle classified with fresh revalidation evidence."
        else:
            evidence = "Lifecycle classified without a fresh validation run; unresolved items remain validating or active."
        return IssueRevalidationResult(
            active_count=counts["active"],
            validating_count=counts["validating"],
            resolved_count=counts["resolved"] + counts["historical"],
            historical_count=counts["historical"],
            ignored_count=counts["ignored"],
            stale_count=counts["stale"],
            reappeared_count=counts["reappeared"],
            revalidated_at=self.revalidated_at,
            revalidated_commit=self.current_commit if self.revalidated_at else None,
            evidence_summary=evidence,
        )

    def resolve_callback_recommendations(
        self,
        session: Session,
        *,
        fixed_pages: set[str],
    ) -> int:
        if not fixed_pages or not self.revalidated_at:
            return 0
        recommendations = session.scalars(
            select(Recommendation).where(
                Recommendation.recommendation_type == "callback_failure",
                Recommendation.entity_type == "telegram_callback",
                Recommendation.entity_id.in_(fixed_pages),
                Recommendation.status.in_(("open", "acknowledged")),
            )
        ).all()
        now = datetime.now(UTC)
        for recommendation in recommendations:
            metadata = dict(recommendation.metadata_json or {})
            metadata.update(
                {
                    "lifecycle_status": "resolved",
                    "fixed_by_commit": self.current_commit,
                    "revalidated_at": self.revalidated_at.isoformat(),
                }
            )
            recommendation.status = "resolved"
            recommendation.metadata_json = sanitize_details(metadata)
            recommendation.updated_at = now
        if recommendations:
            session.flush()
        return len(recommendations)
