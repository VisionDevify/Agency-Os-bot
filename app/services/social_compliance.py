from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.social import (
    SOCIAL_PROTECTED_ACTIONS,
    SOCIAL_SOURCE_METHODS,
    SOCIAL_VALIDATION_OUTCOMES,
    SocialComplianceLog,
)
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.social_events import create_social_event

ALLOWED_SOURCE_METHODS = {"manual", "approved_export", "official_api", "compliant_public_source", "future_connector"}
BLOCKED_SOURCE_METHODS = {
    "unknown",
    "private_scrape",
    "unauthorized_scrape",
    "bypassed_rate_limit",
    "evasion",
    "stolen_export",
    "unsupported",
}


@dataclass(frozen=True)
class ComplianceGateResult:
    allowed: bool
    status: str
    reason: str
    evidence: dict
    compliance_log_id: int
    required_next_step: str


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_compliance_status(status: str | None) -> str:
    if status is None:
        return "needs_review"
    clean = status.strip().lower()
    if clean == "review_required":
        return "needs_review"
    if clean in {"approved", "needs_review", "blocked"}:
        return clean
    return "needs_review"


def validate_source_method(source_method: str | None) -> tuple[str, str, str]:
    if not source_method:
        return "unknown", "missing_required_field", "Source method is missing."
    clean = source_method.strip().lower()
    if clean not in SOCIAL_SOURCE_METHODS:
        return "unsupported", "unsupported_source", "This source type is not approved yet."
    if clean in BLOCKED_SOURCE_METHODS:
        return clean, "unsupported_source", "This source type is not approved."
    return clean, "passed", "Source method is approved."


def validate_compliance_status(compliance_status: str | None) -> tuple[str, str, str]:
    status = normalize_compliance_status(compliance_status)
    if status == "approved":
        return status, "passed", "Compliance status is approved."
    if status == "blocked":
        return status, "failed", "This entity is blocked for social intelligence actions."
    return status, "review_required", "This lead needs review before Fortuna can recommend it."


def _entity_value(entity: Any, attr: str) -> Any:
    if entity is None:
        return None
    return getattr(entity, attr, None)


def create_compliance_log(
    session: Session,
    *,
    entity_type: str,
    entity_id: int | str | None,
    action: str,
    source_method: str,
    compliance_status: str,
    validation_outcome: str,
    allowed: bool,
    reason: str,
    evidence: dict | None = None,
    actor: User | None = None,
) -> SocialComplianceLog:
    if action not in SOCIAL_PROTECTED_ACTIONS:
        raise ValueError(f"Invalid compliance action: {action}")
    if validation_outcome not in SOCIAL_VALIDATION_OUTCOMES:
        raise ValueError(f"Invalid validation outcome: {validation_outcome}")
    log = SocialComplianceLog(
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        action=action,
        source_method=source_method,
        compliance_status=compliance_status,
        validation_outcome=validation_outcome,
        allowed=allowed,
        reason=reason,
        evidence_summary=sanitize_details(evidence or {}),
        created_by_user_id=actor.id if actor else None,
        created_at=_now(),
    )
    session.add(log)
    session.flush()
    create_social_event(
        session,
        event_type="social.compliance.passed" if allowed else "social.compliance.blocked",
        event_category="compliance",
        source_module="compliance",
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        status="success" if allowed else "blocked",
        severity="info" if allowed else "medium",
        summary="Compliance gate allowed this action." if allowed else reason,
        details={"action": action, "allowed": allowed},
        evidence={"compliance_log_id": log.id, **(evidence or {})},
    )
    return log


def compliance_gate(
    session: Session,
    *,
    entity_type: str,
    entity_id: int | str | None = None,
    action: str,
    entity: Any | None = None,
    actor: User | None = None,
    source_method: str | None = None,
    compliance_status: str | None = None,
    evidence: dict | None = None,
) -> ComplianceGateResult:
    if action not in SOCIAL_PROTECTED_ACTIONS:
        raise ValueError(f"Invalid compliance action: {action}")
    source_method = source_method or _entity_value(entity, "source_method") or _entity_value(entity, "source_type")
    compliance_status = compliance_status or _entity_value(entity, "compliance_status")
    method, method_outcome, method_reason = validate_source_method(source_method)
    status, status_outcome, status_reason = validate_compliance_status(compliance_status)
    is_private = bool(_entity_value(entity, "is_private_data"))

    allowed = method in ALLOWED_SOURCE_METHODS and status == "approved" and not is_private
    if is_private:
        validation = "failed"
        reason = "Private data is not allowed for social intelligence actions."
        required = "Use manual public data, official APIs, or approved exports only."
    elif method_outcome != "passed":
        validation = method_outcome
        reason = method_reason
        required = "Use an approved source method."
    elif status_outcome != "passed":
        validation = status_outcome
        reason = status_reason
        required = "Review and approve this source before using it."
    else:
        validation = "passed"
        reason = "Compliance approved for this action."
        required = "Continue with human-reviewed workflow."

    log = create_compliance_log(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        source_method=method,
        compliance_status=status,
        validation_outcome=validation,
        allowed=allowed,
        reason=reason,
        evidence=evidence,
        actor=actor,
    )
    return ComplianceGateResult(
        allowed=allowed,
        status=status if allowed else ("blocked" if validation in {"failed", "unsupported_source"} else "needs_review"),
        reason=reason,
        evidence=sanitize_details(evidence or {}),
        compliance_log_id=log.id,
        required_next_step=required,
    )
