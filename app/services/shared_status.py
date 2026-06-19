from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


SHARED_STATUS_ORDER = {
    "healthy": 0,
    "needs_review": 1,
    "needs_attention": 2,
    "critical": 3,
}

SEVERITY_TO_STATUS = {
    "low": "healthy",
    "info": "healthy",
    "medium": "needs_review",
    "warning": "needs_attention",
    "high": "needs_attention",
    "critical": "critical",
}


@dataclass(frozen=True)
class StatusCondition:
    name: str
    status: str
    evidence: str
    issue_count: int = 0
    recommended_action: str | None = None


@dataclass(frozen=True)
class SharedStatus:
    status: str
    issue_count: int
    evidence: tuple[str, ...] = field(default_factory=tuple)
    recommended_action: str = "No action needed."

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"

    @property
    def label(self) -> str:
        return {
            "healthy": "Healthy",
            "needs_review": "Needs Review",
            "needs_attention": "Needs Attention",
            "critical": "Critical",
        }[self.status]

    @property
    def icon(self) -> str:
        return {
            "healthy": "🟢",
            "needs_review": "🟡",
            "needs_attention": "🟠",
            "critical": "🔴",
        }[self.status]


def normalize_status(value: str | None) -> str:
    text = (value or "healthy").strip().lower()
    if text in SHARED_STATUS_ORDER:
        return text
    return SEVERITY_TO_STATUS.get(text, "needs_review")


def status_from_risk_level(risk_level: str | None) -> str:
    mapping = {
        "low": "healthy",
        "moderate": "needs_review",
        "high": "needs_attention",
        "critical": "critical",
    }
    return mapping.get((risk_level or "").strip().lower(), "needs_review")


def compute_shared_status(conditions: Iterable[StatusCondition]) -> SharedStatus:
    items = list(conditions)
    if not items:
        return SharedStatus(status="healthy", issue_count=0)
    worst = max((normalize_status(item.status) for item in items), key=lambda status: SHARED_STATUS_ORDER[status])
    issue_count = sum(max(0, item.issue_count) for item in items)
    evidence = tuple(item.evidence for item in items if item.evidence and normalize_status(item.status) != "healthy")
    recommended = next(
        (
            item.recommended_action
            for item in sorted(items, key=lambda item: SHARED_STATUS_ORDER[normalize_status(item.status)], reverse=True)
            if normalize_status(item.status) != "healthy" and item.recommended_action
        ),
        "No action needed.",
    )
    return SharedStatus(status=worst, issue_count=issue_count, evidence=evidence, recommended_action=recommended)
