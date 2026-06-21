from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.ai import AI_AUDIT_STATUSES, AIAuditLog
from app.models.decision_memory import DecisionMemory
from app.models.evidence import EvidenceRecord, KnowledgeMemory, OwnerValidation
from app.models.event_log import EventLog
from app.models.recommendation import Recommendation
from app.models.recovery import BackupRun, RestoreTestRun
from app.models.search import ExternalSearchResult
from app.models.user import User
from app.services.ai.providers import (
    AIProvider,
    AIProviderError,
    AIProviderNotConfigured,
    AIProviderOptions,
    AIProviderRateLimited,
    AIProviderStatus,
    AIProviderTimeout,
    ai_env_presence,
    get_ai_provider,
)
from app.services.audit import sanitize_details
from app.services.db_safety import safe_db_side_effect
from app.services.events import emit_event


CONFIDENCE_LEVELS = {"low", "medium", "high"}
REQUIRED_OUTPUT_FIELDS = {
    "conclusion",
    "evidence_used",
    "reasoning_summary",
    "confidence",
    "limitations",
    "next_best_move",
    "safety_flags",
}
SECRET_KEY_MARKERS = (
    "api_key",
    "secret",
    "token",
    "password",
    "credential",
    "session",
    "cookie",
    "private_key",
    "encryption_key",
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"tvly-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{16,}\b"),
)
UNSAFE_RECOMMENDATION_MARKERS = (
    "auto-like",
    "auto like",
    "auto-follow",
    "auto follow",
    "auto-comment",
    "auto comment",
    "auto-post",
    "auto post",
    "scrape private",
    "bypass",
    "bot detection",
)
TRUTH_WORDS = ("healthy", "protected", "passed", "fixed", "successful")


class _AIAuditPlaceholder:
    id: int | None = None


@dataclass(frozen=True)
class AIGroundedOutput:
    conclusion: str
    evidence_used: tuple[str, ...]
    reasoning_summary: str
    confidence: str
    limitations: tuple[str, ...]
    next_best_move: str
    safety_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AIReasoningResult:
    status: str
    output: AIGroundedOutput
    provider_status: AIProviderStatus
    critic_status: str
    fallback_used: bool
    audit_log_id: int | None = None
    safe_error_summary: str | None = None


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


def _truncate(text: Any, limit: int = 420) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _redact_text(text: Any) -> str:
    value = str(text or "")
    for pattern in SECRET_VALUE_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value


def _redact_context(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(marker in key_text.casefold() for marker in SECRET_KEY_MARKERS):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _redact_context(item, depth=depth + 1)
        return redacted
    if isinstance(value, (list, tuple, set)):
        return [_redact_context(item, depth=depth + 1) for item in list(value)[:30]]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return _truncate(_redact_text(value), 800)
    return value


def _contains_secret(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=True, default=str)
    return any(pattern.search(text) for pattern in SECRET_VALUE_PATTERNS)


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        decoded = json.loads(stripped)
        if isinstance(decoded, dict):
            return decoded
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        decoded = json.loads(stripped[start : end + 1])
        if isinstance(decoded, dict):
            return decoded
    raise ValueError("AI output was not valid JSON.")


def _coerce_output(payload: dict[str, Any]) -> AIGroundedOutput:
    missing = REQUIRED_OUTPUT_FIELDS.difference(payload)
    if missing:
        raise ValueError(f"AI output missing fields: {', '.join(sorted(missing))}")
    confidence = str(payload.get("confidence") or "low").casefold()
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "low"
    evidence_used = payload.get("evidence_used") or ()
    limitations = payload.get("limitations") or ()
    safety_flags = payload.get("safety_flags") or ()
    return AIGroundedOutput(
        conclusion=_truncate(payload.get("conclusion"), 500),
        evidence_used=tuple(str(item)[:140] for item in evidence_used if str(item).strip())[:8],
        reasoning_summary=_truncate(payload.get("reasoning_summary"), 700),
        confidence=confidence,
        limitations=tuple(_truncate(item, 220) for item in limitations if str(item).strip())[:6],
        next_best_move=_truncate(payload.get("next_best_move"), 280),
        safety_flags=tuple(str(item)[:120] for item in safety_flags if str(item).strip())[:6],
    )


def _hash_output(output: AIGroundedOutput) -> str:
    encoded = json.dumps(output.__dict__, sort_keys=True, default=list).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _daily_ai_call_count(session: Session) -> int:
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(session.scalar(select(func.count(AIAuditLog.id)).where(AIAuditLog.created_at >= today)) or 0)


def _create_audit(
    session: Session,
    *,
    use_case: str,
    provider_status: AIProviderStatus,
    status: str,
    evidence_count: int,
    input_context: dict[str, Any] | None = None,
    output: AIGroundedOutput | None = None,
    safe_error_summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AIAuditLog:
    context_text = json.dumps(_redact_context(input_context or {}), ensure_ascii=True, default=str)
    output_text = json.dumps(output.__dict__, ensure_ascii=True, default=list) if output is not None else ""
    audit: AIAuditLog | None = None

    def write_audit() -> AIAuditLog:
        nonlocal audit
        audit = AIAuditLog(
            use_case=use_case[:80],
            provider=(provider_status.provider or "unknown")[:40],
            model=(provider_status.model[:120] if provider_status.model else None),
            status=status if status in AI_AUDIT_STATUSES else "failed",
            evidence_count=max(0, int(evidence_count or 0)),
            estimated_input_chars=len(context_text),
            estimated_output_chars=len(output_text),
            safe_error_summary=_truncate(safe_error_summary, 500) if safe_error_summary else None,
            output_hash=_hash_output(output) if output is not None else None,
            completed_at=_now(),
            metadata_json=sanitize_details(metadata or {}),
        )
        session.add(audit)
        return audit

    _, result = safe_db_side_effect(session, f"ai_audit.{use_case}", write_audit)
    return audit or _AIAuditPlaceholder()  # type: ignore[return-value]


def _fallback_output(
    *,
    use_case: str,
    context: dict[str, Any],
    reason: str,
    next_action: str | None = None,
) -> AIGroundedOutput:
    decisions = context.get("decisions") or []
    top = decisions[0] if decisions else {}
    title = top.get("title") or "AI Brain is not configured yet"
    evidence = top.get("evidence_summary") or context.get("summary") or "Not enough AI-ready evidence yet."
    return AIGroundedOutput(
        conclusion=_truncate(title),
        evidence_used=tuple(str(item) for item in (top.get("source_records") or context.get("source_records") or ["DeterministicFallback"]))[:6],
        reasoning_summary=_truncate(evidence),
        confidence=str(top.get("confidence") or "low") if str(top.get("confidence") or "low") in CONFIDENCE_LEVELS else "low",
        limitations=(reason,),
        next_best_move=_truncate(next_action or top.get("next_best_move") or "Use deterministic Fortuna screens until AI is configured."),
        safety_flags=("fallback_used",),
    )


class AIGroundingContextBuilder:
    def __init__(self, session: Session, *, actor: User | None = None, max_records: int | None = None) -> None:
        self.session = session
        self.actor = actor
        self.max_records = max_records or _env_int("AI_MAX_CONTEXT_RECORDS", 12)

    def build(self, *, use_case: str, include_search: bool = True, decisions: tuple[Any, ...] | None = None) -> dict[str, Any]:
        from app.services.agency_awareness import agency_awareness_report
        from app.services.bot_instances import bot_instance_diagnostics
        from app.services.decision_engine import generate_decisions
        from app.services.notification_intelligence import alert_health_summary
        from app.services.platform_connections import platform_connections_overview
        from app.services.recovery import recovery_risk_assessment
        from app.services.system_truth import system_truth

        decision_items = decisions if decisions is not None else generate_decisions(self.session, actor=self.actor)
        recovery = recovery_risk_assessment(self.session)
        truth = system_truth(self.session)
        bot = bot_instance_diagnostics(self.session)
        alert_health = alert_health_summary(self.session)
        platforms = platform_connections_overview(self.session)
        awareness = agency_awareness_report(self.session, persist=False)

        evidence_records = list(
            self.session.scalars(select(EvidenceRecord).order_by(desc(EvidenceRecord.created_at), desc(EvidenceRecord.id)).limit(self.max_records)).all()
        )
        search_results: list[ExternalSearchResult] = []
        if include_search:
            search_results = list(
                self.session.scalars(
                    select(ExternalSearchResult)
                    .order_by(desc(ExternalSearchResult.retrieved_at), desc(ExternalSearchResult.id))
                    .limit(self.max_records)
                ).all()
            )
        latest_backup = self.session.scalar(select(BackupRun).order_by(desc(BackupRun.created_at), desc(BackupRun.id)).limit(1))
        latest_restore = self.session.scalar(select(RestoreTestRun).order_by(desc(RestoreTestRun.created_at), desc(RestoreTestRun.id)).limit(1))
        recommendations = list(
            self.session.scalars(
                select(Recommendation)
                .where(Recommendation.status.in_(("open", "acknowledged")))
                .order_by(desc(Recommendation.updated_at), desc(Recommendation.id))
                .limit(self.max_records)
            ).all()
        )
        memories = list(
            self.session.scalars(select(DecisionMemory).order_by(desc(DecisionMemory.updated_at), desc(DecisionMemory.id)).limit(self.max_records)).all()
        )
        owner_validations = list(
            self.session.scalars(select(OwnerValidation).order_by(desc(OwnerValidation.created_at), desc(OwnerValidation.id)).limit(self.max_records)).all()
        )
        knowledge = list(
            self.session.scalars(select(KnowledgeMemory).order_by(desc(KnowledgeMemory.created_at), desc(KnowledgeMemory.id)).limit(self.max_records)).all()
        )
        context = {
            "use_case": use_case,
            "generated_at": _now().isoformat(),
            "feature_flags": {
                "AI_ENABLED": _env_bool("AI_ENABLED", False),
                "AI_CRITIC_ENABLED": _env_bool("AI_CRITIC_ENABLED", True),
                "SEARCH_ENABLED": _env_bool("SEARCH_ENABLED", False),
            },
            "system_truth": {
                "production_ready": truth.production_ready,
                "issues": list(truth.current_issues[:5]),
                "issue_codes": list(truth.current_issue_codes[:5]),
            },
            "recovery": {
                "status": recovery.status,
                "risk_score": recovery.risk_score,
                "risk_level": recovery.risk_level,
                "next_best_move": recovery.next_best_move,
                "evidence": list(recovery.evidence[:5]),
                "latest_backup_status": getattr(latest_backup, "status", None),
                "latest_backup_verification": getattr(latest_backup, "verification_status", None),
                "latest_restore_status": getattr(latest_restore, "status", None),
                "latest_restore_outcome": getattr(latest_restore, "outcome", None),
            },
            "bot_status": {
                "risk": bot.get("risk"),
                "polling_conflict_active": bot.get("polling_conflict_active"),
                "active_polling_owner_count": bot.get("active_polling_owner_count"),
            },
            "notification_health": {
                "status": alert_health.status,
                "evidence": alert_health.evidence,
                "next_action": alert_health.next_action,
            },
            "platform_connections": {
                "status": platforms.get("status"),
                "waiting": platforms.get("waiting"),
                "needs_attention": platforms.get("needs_attention"),
                "next_action": platforms.get("next_action"),
            },
            "agency_awareness": {
                "status": awareness.overall_status,
                "visibility_level": awareness.visibility_level,
                "visibility_score": awareness.visibility_score,
                "confidence_score": awareness.confidence_score,
                "degraded_mode": awareness.degraded_mode,
                "snapshot_source": awareness.snapshot_source,
                "stale": awareness.stale,
                "top_focus_area": awareness.top_focus_area,
                "next_best_move": awareness.next_best_move,
                "active_domains": [item.display_name for item in awareness.active_domains[:8]],
                "missing_domains": [item.display_name for item in awareness.missing_domains[:8]],
                "not_connected_domains": [item.display_name for item in awareness.not_connected_domains[:8]],
                "missing_inputs": list(awareness.missing_inputs[:8]),
            },
            "decisions": [
                {
                    "title": item.title,
                    "category": item.category,
                    "severity": item.severity,
                    "priority_rank": item.priority_rank,
                    "impact": item.impact,
                    "risk": item.risk,
                    "recommendation": item.recommendation,
                    "confidence": item.confidence,
                    "evidence_summary": item.evidence_summary,
                    "source_records": list(item.source_records),
                    "next_best_move": item.next_best_move,
                    "can_wait": item.can_wait,
                }
                for item in tuple(decision_items)[: self.max_records]
            ],
            "evidence_records": [
                {
                    "source": f"EvidenceRecord:{item.id}",
                    "type": item.evidence_type,
                    "category": item.category,
                    "summary": item.summary,
                    "strength": item.evidence_strength,
                }
                for item in evidence_records
            ],
            "search_results": [
                {
                    "source": f"ExternalSearchResult:{item.id}",
                    "title": item.title,
                    "domain": item.source_domain,
                    "strength": item.evidence_strength,
                    "summary": item.summary,
                    "retrieved_at": item.retrieved_at.isoformat() if item.retrieved_at else None,
                }
                for item in search_results
            ],
            "recommendations": [
                {
                    "source": f"Recommendation:{item.id}",
                    "title": item.title,
                    "severity": item.severity,
                    "status": item.status,
                    "description": item.description,
                }
                for item in recommendations
            ],
            "decision_memory": [
                {
                    "decision_id": item.decision_id,
                    "category": item.category,
                    "outcome": item.outcome,
                    "lifecycle": item.lifecycle_status,
                    "usefulness_score": item.usefulness_score,
                }
                for item in memories
            ],
            "owner_validations": [
                {
                    "source": f"OwnerValidation:{item.id}",
                    "outcome": item.validation_outcome,
                    "summary": item.summary,
                }
                for item in owner_validations
            ],
            "knowledge_memory": [
                {
                    "source": f"KnowledgeMemory:{item.id}",
                    "category": item.category,
                    "lesson": item.lesson,
                    "confidence": item.confidence,
                }
                for item in knowledge
            ],
            "compliance_rules": [
                "No auto-post/comment/like/follow/message.",
                "No private scraping or bot-evasion.",
                "AI cannot mark health, backups, restore, or polling truth.",
                "Evidence overrides AI narrative.",
            ],
        }
        return _redact_context(context)

    @staticmethod
    def evidence_count(context: dict[str, Any]) -> int:
        return (
            len(context.get("decisions") or [])
            + len(context.get("evidence_records") or [])
            + len(context.get("search_results") or [])
            + len(context.get("recommendations") or [])
        )


class FortunaAICritic:
    def critique(self, output: AIGroundedOutput, context: dict[str, Any]) -> tuple[str, tuple[str, ...], AIGroundedOutput]:
        flags: list[str] = list(output.safety_flags)
        combined = " ".join(
            [
                output.conclusion,
                output.reasoning_summary,
                output.next_best_move,
                " ".join(output.limitations),
                " ".join(output.evidence_used),
            ]
        ).casefold()
        if _contains_secret(output.__dict__):
            flags.append("raw_secret_leak")
        if any(marker in combined for marker in UNSAFE_RECOMMENDATION_MARKERS):
            flags.append("compliance_violation")
        if not output.evidence_used:
            flags.append("missing_evidence")
        if output.confidence == "high" and len(output.evidence_used) < 2:
            flags.append("exaggerated_confidence")
        if self._uses_unavailable_evidence(output, context):
            flags.append("unsupported_claim")
        recovery = context.get("recovery") or {}
        if recovery.get("status") != "healthy" and any(word in combined for word in TRUTH_WORDS):
            if "backup" in combined or "restore" in combined or "recovery" in combined:
                flags.append("contradicts_recovery_truth")
        bot = context.get("bot_status") or {}
        if bot.get("polling_conflict_active") and any(word in combined for word in ("healthy", "stable", "fixed")):
            flags.append("contradicts_bot_truth")
        critical_flags = {
            "raw_secret_leak",
            "compliance_violation",
            "unsupported_claim",
            "contradicts_recovery_truth",
            "contradicts_bot_truth",
        }
        if critical_flags.intersection(flags):
            return "blocked", tuple(dict.fromkeys(flags)), output
        if "exaggerated_confidence" in flags:
            output = AIGroundedOutput(
                conclusion=output.conclusion,
                evidence_used=output.evidence_used,
                reasoning_summary=output.reasoning_summary,
                confidence="medium",
                limitations=(*output.limitations, "Confidence was downgraded because evidence was limited."),
                next_best_move=output.next_best_move,
                safety_flags=tuple(dict.fromkeys(flags)),
            )
            return "downgraded", tuple(dict.fromkeys(flags)), output
        return "passed", tuple(dict.fromkeys(flags)), output

    def _uses_unavailable_evidence(self, output: AIGroundedOutput, context: dict[str, Any]) -> bool:
        allowed = self._allowed_evidence_tokens(context)
        if not allowed:
            return bool(output.evidence_used)
        generic_allowed = {
            "decision engine",
            "system truth",
            "recovery status",
            "bot status",
            "observability",
            "search results",
            "evidence records",
            "decision memory",
        }
        for evidence in output.evidence_used:
            normalized = " ".join(str(evidence or "").casefold().split())
            if not normalized:
                continue
            if normalized in generic_allowed:
                continue
            if any(token in normalized or normalized in token for token in allowed):
                continue
            return True
        return False

    def _allowed_evidence_tokens(self, context: dict[str, Any]) -> set[str]:
        tokens = {
            "decision engine",
            "system truth",
            "recovery status",
            "bot status",
            "observability",
            "search results",
            "evidence records",
            "decision memory",
        }
        for key in ("decisions", "recommendations", "evidence_records", "owner_validations", "knowledge_memory", "search_results"):
            records = context.get(key) or []
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                for field in ("title", "decision_id", "recommendation_id", "source", "source_domain", "category", "summary"):
                    value = record.get(field)
                    if value:
                        token = " ".join(str(value).casefold().split())
                        if token:
                            tokens.add(token)
                source_records = record.get("source_records")
                if isinstance(source_records, list):
                    tokens.update(" ".join(str(item).casefold().split()) for item in source_records if str(item).strip())
        return tokens


class FortunaAIBrain:
    def __init__(
        self,
        *,
        provider: AIProvider | None = None,
        critic: FortunaAICritic | None = None,
    ) -> None:
        self.provider = provider or get_ai_provider()
        self.critic = critic or FortunaAICritic()

    def reason(
        self,
        session: Session,
        *,
        use_case: str,
        prompt: str,
        actor: User | None = None,
        context: dict[str, Any] | None = None,
        allow_empty_context: bool = False,
    ) -> AIReasoningResult:
        provider_status = self.provider.get_provider_status()
        builder = AIGroundingContextBuilder(session, actor=actor)
        context = context or builder.build(use_case=use_case)
        evidence_count = builder.evidence_count(context)
        if evidence_count <= 0 and not allow_empty_context:
            output = _fallback_output(
                use_case=use_case,
                context=context,
                reason="AI was not run because there was no evidence context.",
                next_action="Collect evidence first.",
            )
            audit = _create_audit(
                session,
                use_case=use_case,
                provider_status=provider_status,
                status="fallback_used",
                evidence_count=0,
                input_context=context,
                output=output,
                safe_error_summary="No evidence context.",
            )
            return AIReasoningResult("fallback_used", output, provider_status, "not_run", True, audit.id, "No evidence context.")
        if not provider_status.enabled or not provider_status.configured:
            output = _fallback_output(
                use_case=use_case,
                context=context,
                reason=provider_status.reason,
                next_action=provider_status.next_action,
            )
            audit = _create_audit(
                session,
                use_case=use_case,
                provider_status=provider_status,
                status="not_configured" if provider_status.status == "not_configured" else "fallback_used",
                evidence_count=evidence_count,
                input_context=context,
                output=output,
                safe_error_summary=provider_status.reason,
            )
            return AIReasoningResult(provider_status.status, output, provider_status, "not_run", True, audit.id, provider_status.reason)
        daily_limit = _env_int("AI_DAILY_LIMIT", 25)
        if daily_limit and _daily_ai_call_count(session) >= daily_limit:
            output = _fallback_output(use_case=use_case, context=context, reason="AI daily limit reached.", next_action="Try again later.")
            audit = _create_audit(
                session,
                use_case=use_case,
                provider_status=provider_status,
                status="rate_limited",
                evidence_count=evidence_count,
                input_context=context,
                output=output,
                safe_error_summary="AI daily limit reached.",
            )
            return AIReasoningResult("rate_limited", output, provider_status, "not_run", True, audit.id, "AI daily limit reached.")
        try:
            raw = self.provider.generate_reasoning(
                prompt,
                context,
                AIProviderOptions(use_case=use_case, model=provider_status.model, timeout_seconds=_env_int("AI_TIMEOUT_SECONDS", 20)),
            )
            parsed = _parse_json_object(raw.text)
            output = _coerce_output(parsed)
            critic_status, flags, checked_output = self.critic.critique(output, context)
            if critic_status == "blocked":
                fallback = _fallback_output(
                    use_case=use_case,
                    context=context,
                    reason=f"AI output blocked by critic: {', '.join(flags)}.",
                    next_action="Use deterministic Fortuna recommendation.",
                )
                audit = _create_audit(
                    session,
                    use_case=use_case,
                    provider_status=provider_status,
                    status="blocked_by_critic",
                    evidence_count=evidence_count,
                    input_context=context,
                    output=fallback,
                    safe_error_summary=f"Critic blocked: {', '.join(flags)}",
                    metadata={"critic_flags": list(flags)},
                )
                safe_db_side_effect(
                    session,
                    "ai.critic_blocked_event",
                    lambda: emit_event(
                        session,
                        actor=actor,
                        event_name="ai.critic_blocked",
                        resource_type="ai_brain",
                        payload=sanitize_details({"use_case": use_case, "critic_flags": list(flags)}),
                    ),
                )
                return AIReasoningResult("blocked_by_critic", fallback, provider_status, critic_status, True, audit.id, "AI critic blocked output.")
            audit = _create_audit(
                session,
                use_case=use_case,
                provider_status=AIProviderStatus(
                    provider_status.provider,
                    provider_status.enabled,
                    provider_status.configured,
                    provider_status.status,
                    provider_status.reason,
                    provider_status.next_action,
                    raw.model,
                ),
                status="succeeded" if critic_status == "passed" else "fallback_used",
                evidence_count=evidence_count,
                input_context=context,
                output=checked_output,
                metadata={"critic_status": critic_status, "critic_flags": list(flags), "usage": raw.usage or {}},
            )
            return AIReasoningResult("succeeded", checked_output, provider_status, critic_status, False, audit.id)
        except AIProviderNotConfigured as exc:
            status = "not_configured"
            error = str(exc)
        except AIProviderRateLimited as exc:
            status = "rate_limited"
            error = str(exc)
        except AIProviderTimeout as exc:
            status = "timeout"
            error = str(exc)
        except (AIProviderError, ValueError, json.JSONDecodeError) as exc:
            status = "failed"
            error = str(exc)
        output = _fallback_output(use_case=use_case, context=context, reason=error, next_action="Use deterministic Fortuna output.")
        audit = _create_audit(
            session,
            use_case=use_case,
            provider_status=provider_status,
            status=status,
            evidence_count=evidence_count,
            input_context=context,
            output=output,
            safe_error_summary=error,
        )
        safe_db_side_effect(
            session,
            "ai.fallback_used_event",
            lambda: emit_event(
                session,
                actor=actor,
                event_name="ai.fallback_used",
                resource_type="ai_brain",
                payload=sanitize_details({"use_case": use_case, "status": status, "error": error}),
            ),
        )
        return AIReasoningResult(status, output, provider_status, "fallback", True, audit.id, error)


def ai_configuration_status(session: Session | None = None) -> dict[str, Any]:
    provider = get_ai_provider()
    status = provider.get_provider_status()
    latest = None
    latest_success = None
    daily_count = 0
    if session is not None:
        latest = session.scalar(select(AIAuditLog).order_by(desc(AIAuditLog.created_at), desc(AIAuditLog.id)).limit(1))
        latest_success = session.scalar(
            select(AIAuditLog)
            .where(AIAuditLog.status == "succeeded")
            .order_by(desc(AIAuditLog.created_at), desc(AIAuditLog.id))
            .limit(1)
        )
        daily_count = _daily_ai_call_count(session)
    latest_status = latest.status if latest else "not_checked"
    latest_failure = latest.safe_error_summary if latest and latest.status != "succeeded" else None
    return {
        "provider": status.provider,
        "enabled": status.enabled,
        "configured": status.configured,
        "status": status.status,
        "reason": status.reason,
        "next_action": status.next_action,
        "model": status.model,
        "critic_enabled": _env_bool("AI_CRITIC_ENABLED", True),
        "daily_count": daily_count,
        "daily_limit": _env_int("AI_DAILY_LIMIT", 25),
        "last_call_status": latest_status,
        "latest_status": latest_status,
        "last_failure_reason": latest_failure,
        "latest_failure": latest_failure,
        "last_failure": latest_failure,
        "last_success_at": latest_success.created_at if latest_success else None,
        "env_vars": ai_env_presence(),
    }


def ai_observability_summary(session: Session) -> dict[str, Any]:
    status = ai_configuration_status(session)
    blocked = int(session.scalar(select(func.count(AIAuditLog.id)).where(AIAuditLog.status == "blocked_by_critic")) or 0)
    failures = int(
        session.scalar(select(func.count(AIAuditLog.id)).where(AIAuditLog.status.in_(("failed", "timeout", "rate_limited"))))
        or 0
    )
    fallback_count = int(session.scalar(select(func.count(AIAuditLog.id)).where(AIAuditLog.status == "fallback_used")) or 0)
    meaningful = bool(status["configured"] or status["last_call_status"] != "not_checked" or blocked or failures)
    if not status["enabled"]:
        health = "healthy"
        label = "Disabled"
    elif not status["configured"]:
        health = "needs_review" if meaningful else "healthy"
        label = "Not configured yet"
    elif failures or blocked:
        health = "needs_review"
        label = "Needs review"
    else:
        health = "healthy"
        label = "Configured"
    return {
        **status,
        "health": health,
        "label": label,
        "meaningful": meaningful,
        "critic_blocks": blocked,
        "failures": failures,
        "fallback_count": fallback_count,
    }


def generate_ai_decision_explanation(session: Session, *, actor: User | None = None) -> AIReasoningResult:
    brain = FortunaAIBrain()
    context = AIGroundingContextBuilder(session, actor=actor).build(use_case="decision_details")
    return brain.reason(
        session,
        use_case="decision_details",
        prompt="Explain why the top decision matters. Keep it concise and grounded.",
        actor=actor,
        context=context,
    )


def generate_ai_evidence_summary(session: Session, *, actor: User | None = None) -> AIReasoningResult:
    brain = FortunaAIBrain()
    context = AIGroundingContextBuilder(session, actor=actor).build(use_case="evidence_summary")
    return brain.reason(
        session,
        use_case="evidence_summary",
        prompt="Summarize the strongest internal evidence and the main limitation.",
        actor=actor,
        context=context,
    )


def generate_ai_search_summary(session: Session, *, actor: User | None = None) -> AIReasoningResult:
    brain = FortunaAIBrain()
    context = AIGroundingContextBuilder(session, actor=actor).build(use_case="search_summary", include_search=True)
    if not context.get("search_results"):
        provider_status = brain.provider.get_provider_status()
        output = _fallback_output(
            use_case="search_summary",
            context={"summary": "No search results are available."},
            reason="Tavily/search evidence is not configured or no results exist.",
            next_action="Run a safe public search after TAVILY_API_KEY is configured.",
        )
        audit = _create_audit(
            session,
            use_case="search_summary",
            provider_status=provider_status,
            status="fallback_used",
            evidence_count=0,
            input_context=context,
            output=output,
            safe_error_summary="No search results available.",
        )
        return AIReasoningResult("fallback_used", output, provider_status, "not_run", True, audit.id, "No search results available.")
    return brain.reason(
        session,
        use_case="search_summary",
        prompt="Summarize supplied search evidence into themes, source limitations, and a manual next move.",
        actor=actor,
        context=context,
    )
