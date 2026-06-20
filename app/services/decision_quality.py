from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.button_issue import ButtonIssue
from app.models.decision_memory import DecisionMemory
from app.models.friction import FrictionItem
from app.models.recommendation import Recommendation
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.events import emit_event


CRITICAL_CATEGORIES = {"recovery", "telegram_bot", "system_health", "security", "deployment"}
GENERIC_NEXT_ACTIONS = {"open recommendations.", "review details.", "open details.", "check later."}


@dataclass(frozen=True)
class RecommendationQualityScore:
    relevance_score: int
    impact_score: int
    confidence_score: int
    evidence_score: int
    actionability_score: int
    overall_recommendation_score: int
    adjusted_confidence: str
    evidence_version: str
    recommendation_hash: str
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionQualityFinding:
    title: str
    category: str
    severity: str
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class FrictionSeveritySummary:
    severity: str
    repeated_help_count: int
    repeated_back_count: int
    abandoned_screen_count: int
    owner_complaint_count: int
    navigation_loop_count: int
    open_button_issue_count: int
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class DecisionQualityReport:
    status: str
    available: bool
    decision_quality_score: int
    recommendation_accuracy: int
    category_accuracy: int
    confidence_accuracy: int
    briefing_quality_score: int
    learning_status: str
    acted_on_rate: float
    resolved_rate: float
    ignored_rate: float
    dismissal_rate: float
    usefulness_score: int
    total_memories: int
    suppressed_count: int
    duplicate_suppression_status: str
    findings: tuple[DecisionQualityFinding, ...]
    friction: FrictionSeveritySummary
    generated_at: datetime
    unavailable_reason: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _clamp(value: int | float, *, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def _hash_parts(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _word_count(value: str) -> int:
    return len([part for part in value.replace(".", " ").replace(",", " ").split() if part.strip()])


def recommendation_hash(decision: Any) -> str:
    return _hash_parts(
        getattr(decision, "category", ""),
        getattr(decision, "title", ""),
        getattr(decision, "action_page", ""),
        getattr(decision, "next_best_move", ""),
    )


def evidence_version(decision: Any) -> str:
    return _hash_parts(
        getattr(decision, "severity", ""),
        getattr(decision, "confidence", ""),
        getattr(decision, "evidence_summary", ""),
        tuple(getattr(decision, "source_records", ()) or ()),
    )


def _score_dimension(text: str, *, minimum_words: int = 4) -> int:
    words = _word_count(text)
    if not text:
        return 0
    if words >= minimum_words * 3:
        return 90
    if words >= minimum_words:
        return 70
    return 40


class DecisionQualityEngine:
    """Audits decision quality without replacing the Decision Engine truth path."""

    def score_decision_recommendation(self, decision: Any) -> RecommendationQualityScore:
        title = _safe_text(getattr(decision, "title", ""))
        risk = _safe_text(getattr(decision, "risk", ""))
        impact = _safe_text(getattr(decision, "impact", ""))
        confidence = _safe_text(getattr(decision, "confidence", "medium")).casefold()
        evidence = _safe_text(getattr(decision, "evidence_summary", ""))
        next_action = _safe_text(getattr(decision, "next_best_move", ""))
        sources = tuple(getattr(decision, "source_records", ()) or ())
        findings: list[str] = []

        relevance = 85 if title and getattr(decision, "category", None) else 35
        impact_score = _score_dimension(impact, minimum_words=5)
        evidence_score = _score_dimension(evidence, minimum_words=5) + (15 if sources else 0)
        evidence_score = _clamp(evidence_score)
        actionability = _score_dimension(next_action, minimum_words=3)
        if next_action.casefold() in GENERIC_NEXT_ACTIONS:
            actionability = min(actionability, 45)
            findings.append("Next action is generic.")
        if "not enough evidence" in evidence.casefold():
            evidence_score = min(evidence_score, 35)
            findings.append("Evidence is incomplete.")

        if confidence == "high" and evidence_score < 65:
            confidence_score = 45
            adjusted_confidence = "medium"
            findings.append("High confidence did not have enough evidence.")
        elif confidence == "medium" and evidence_score < 40:
            confidence_score = 45
            adjusted_confidence = "low"
            findings.append("Medium confidence was downgraded by weak evidence.")
        else:
            confidence_score = {"high": 88, "medium": 72, "low": 58}.get(confidence, 60)
            adjusted_confidence = confidence if confidence in {"high", "medium", "low"} else "medium"

        overall = _clamp((relevance + impact_score + confidence_score + evidence_score + actionability) / 5)
        if overall < 55:
            findings.append("Recommendation needs stronger why, evidence, or next action.")
        return RecommendationQualityScore(
            relevance_score=relevance,
            impact_score=impact_score,
            confidence_score=confidence_score,
            evidence_score=evidence_score,
            actionability_score=actionability,
            overall_recommendation_score=overall,
            adjusted_confidence=adjusted_confidence,
            evidence_version=evidence_version(decision),
            recommendation_hash=recommendation_hash(decision),
            findings=tuple(findings),
        )

    def score_recommendation_record(self, recommendation: Recommendation) -> RecommendationQualityScore:
        metadata = recommendation.metadata_json or {}
        description = recommendation.description or ""
        title = recommendation.title or ""
        pseudo = type(
            "RecommendationDecision",
            (),
            {
                "title": title,
                "category": recommendation.entity_type or "general",
                "risk": description,
                "impact": metadata.get("impact") or ("Clears an open recommendation." if description else ""),
                "confidence": metadata.get("confidence") or "medium",
                "evidence_summary": metadata.get("evidence") or description,
                "source_records": (f"Recommendation:{recommendation.id}",),
                "next_best_move": metadata.get("next_best_move") or "Open Recommendations.",
                "action_page": f"recommendation:{recommendation.id}",
                "severity": recommendation.severity,
            },
        )()
        return self.score_decision_recommendation(pseudo)

    def should_suppress_duplicate(self, decision: Any, memory: DecisionMemory | None) -> bool:
        if memory is None:
            return False
        if getattr(decision, "severity", "") == "critical" or getattr(decision, "category", "") in CRITICAL_CATEGORIES:
            return False
        metadata = memory.metadata_json or {}
        same_evidence = metadata.get("quality_evidence_version") == evidence_version(decision)
        if not same_evidence:
            return False
        if memory.lifecycle_status == "dismissed":
            return True
        if memory.outcome in {"ignored", "dismissed", "stale"} and (memory.usefulness_score or 50) < 45:
            return True
        return bool(getattr(decision, "can_wait", False) and memory.outcome in {"ignored", "stale"})

    def adjust_decisions(self, session: Session, decisions: tuple[Any, ...], *, actor: User | None = None) -> tuple[Any, ...]:
        adjusted: list[Any] = []
        suppressed_count = 0
        metadata_updated = False
        for decision in decisions:
            score = self.score_decision_recommendation(decision)
            memory = session.scalar(
                select(DecisionMemory)
                .where(DecisionMemory.decision_id == self._memory_key_for_decision(decision))
                .limit(1)
            )
            if self.should_suppress_duplicate(decision, memory):
                suppressed_count += 1
                continue
            if memory is not None:
                memory.metadata_json = sanitize_details(
                    {
                        **(memory.metadata_json or {}),
                        "quality_evidence_version": score.evidence_version,
                        "recommendation_hash": score.recommendation_hash,
                        "recommendation_quality_score": score.overall_recommendation_score,
                    }
                )
                metadata_updated = True
            priority = getattr(decision, "priority_rank", 1)
            confidence = getattr(decision, "confidence", "medium")
            if score.overall_recommendation_score < 55 and getattr(decision, "severity", "") != "critical":
                priority = max(1, priority - 10)
                confidence = score.adjusted_confidence
            details = {
                **(getattr(decision, "details", {}) or {}),
                "recommendation_quality": {
                    "overall": score.overall_recommendation_score,
                    "relevance": score.relevance_score,
                    "impact": score.impact_score,
                    "confidence": score.confidence_score,
                    "evidence": score.evidence_score,
                    "actionability": score.actionability_score,
                    "findings": list(score.findings),
                },
                "duplicate_suppression": "checked",
                "quality_evidence_version": score.evidence_version,
            }
            adjusted.append(replace(decision, priority_rank=priority, confidence=confidence, details=sanitize_details(details)))
        if suppressed_count:
            emit_event(
                session,
                actor=actor,
                event_name="decision_quality.duplicates_suppressed",
                resource_type="decision_quality",
                status="success",
                payload={"suppressed_count": suppressed_count},
            )
        elif metadata_updated:
            session.flush()
        return tuple(sorted(adjusted, key=lambda item: (-item.priority_rank, item.can_wait, item.title)))

    def _memory_key_for_decision(self, decision: Any) -> str:
        # Mirrors Decision Engine without importing it, avoiding a circular dependency.
        import re

        title = re.sub(r"[^a-z0-9]+", "-", _safe_text(getattr(decision, "title", "")).casefold()).strip("-")[:80] or "decision"
        action = re.sub(r"[^a-z0-9:]+", "-", _safe_text(getattr(decision, "action_page", "")).casefold()).strip("-")[:80] or "none"
        return f"{getattr(decision, 'category', 'general')}:{title}:{action}"[:220]

    def friction_summary(self, session: Session) -> FrictionSeveritySummary:
        friction_items = list(session.scalars(select(FrictionItem)).all())
        open_button_issues = int(session.scalar(select(func.count(ButtonIssue.id)).where(ButtonIssue.status == "open")) or 0)
        text_rows = " ".join(f"{item.screen} {item.issue} {item.fix_recommendation}".casefold() for item in friction_items)
        help_count = text_rows.count("help")
        back_count = text_rows.count("back")
        abandoned_count = text_rows.count("abandon") + text_rows.count("exit")
        complaint_count = text_rows.count("complaint") + text_rows.count("owner")
        loop_count = text_rows.count("loop") + text_rows.count("stuck")
        total_signal = help_count + back_count + abandoned_count + complaint_count + loop_count + open_button_issues
        if total_signal >= 10 or any(item.severity == "critical" for item in friction_items):
            severity = "critical"
        elif total_signal >= 6 or any(item.severity == "high" for item in friction_items):
            severity = "high"
        elif total_signal >= 3 or open_button_issues:
            severity = "medium"
        else:
            severity = "low"
        if severity == "low":
            evidence = "No repeated friction pattern is strong enough to interrupt the owner."
            recommendation = "Keep watching."
        else:
            evidence = f"{total_signal} friction signal(s) found across Help, Back, loops, complaints, and button issues."
            recommendation = "Review Button Health and simplify the repeated path."
        return FrictionSeveritySummary(
            severity=severity,
            repeated_help_count=help_count,
            repeated_back_count=back_count,
            abandoned_screen_count=abandoned_count,
            owner_complaint_count=complaint_count,
            navigation_loop_count=loop_count,
            open_button_issue_count=open_button_issues,
            evidence=evidence,
            recommendation=recommendation,
        )

    def audit(self, session: Session, decisions: tuple[Any, ...]) -> DecisionQualityReport:
        memories = list(session.scalars(select(DecisionMemory)).all())
        total = len(memories)
        opened = sum(1 for item in memories if item.opened_at is not None)
        acted = sum(1 for item in memories if item.acted_on_at is not None or item.outcome == "acted_on")
        ignored = sum(1 for item in memories if item.outcome == "ignored")
        dismissed = sum(1 for item in memories if item.outcome == "dismissed")
        resolved = sum(1 for item in memories if item.resolved_at is not None or item.outcome == "resolved")
        failed = sum(1 for item in memories if item.outcome == "failed")
        usefulness = _clamp(sum(item.usefulness_score or 0 for item in memories) / total) if total else 0
        denominator = max(1, acted + resolved + dismissed + failed)
        recommendation_accuracy = _clamp(((acted + resolved) / denominator) * 100)
        category_accuracy = self._category_accuracy(memories)
        confidence_accuracy = self._confidence_accuracy(memories)
        quality_scores = [self.score_decision_recommendation(decision).overall_recommendation_score for decision in decisions]
        decision_quality_score = _clamp(sum(quality_scores) / len(quality_scores)) if quality_scores else 0
        briefing_quality = self._briefing_quality(decisions)
        friction = self.friction_summary(session)
        findings = list(self._priority_findings(decisions))
        for decision, score in zip(decisions, quality_scores, strict=False):
            if score < 55 and getattr(decision, "severity", "") != "critical":
                findings.append(
                    DecisionQualityFinding(
                        title=f"{getattr(decision, 'title', 'Decision')} needs sharper evidence",
                        category=getattr(decision, "category", "general"),
                        severity="medium",
                        evidence=f"Recommendation quality score was {score}/100.",
                        recommendation="Add clearer why, impact, evidence, or next action.",
                    )
                )
        if not total:
            findings.append(
                DecisionQualityFinding(
                    title="Decision memory is still warming up",
                    category="learning",
                    severity="low",
                    evidence="No decision outcomes have been recorded yet.",
                    recommendation="Open decisions and record feedback as you operate.",
                )
            )
        if friction.severity in {"medium", "high", "critical"}:
            findings.append(
                DecisionQualityFinding(
                    title="Friction pattern needs review",
                    category="friction",
                    severity=friction.severity,
                    evidence=friction.evidence,
                    recommendation=friction.recommendation,
                )
            )
        status = "healthy"
        if any(finding.severity == "critical" for finding in findings):
            status = "critical"
        elif any(finding.severity == "high" for finding in findings) or decision_quality_score < 45:
            status = "needs_attention"
        elif findings or decision_quality_score < 70 or not total:
            status = "needs_review"
        learning_status = "healthy" if total and usefulness >= 55 and status in {"healthy", "needs_review"} else "needs_review"
        return DecisionQualityReport(
            status=status,
            available=True,
            decision_quality_score=decision_quality_score,
            recommendation_accuracy=recommendation_accuracy,
            category_accuracy=category_accuracy,
            confidence_accuracy=confidence_accuracy,
            briefing_quality_score=briefing_quality,
            learning_status=learning_status,
            acted_on_rate=(acted / total) if total else 0.0,
            resolved_rate=(resolved / total) if total else 0.0,
            ignored_rate=(ignored / total) if total else 0.0,
            dismissal_rate=(dismissed / total) if total else 0.0,
            usefulness_score=usefulness,
            total_memories=total,
            suppressed_count=0,
            duplicate_suppression_status="available",
            findings=tuple(findings[:8]),
            friction=friction,
            generated_at=_now(),
        )

    def _priority_findings(self, decisions: tuple[Any, ...]) -> tuple[DecisionQualityFinding, ...]:
        if not decisions:
            return ()
        findings: list[DecisionQualityFinding] = []
        active = [decision for decision in decisions if not getattr(decision, "can_wait", False)]
        top = active[0] if active else decisions[0]
        recovery = next((decision for decision in decisions if getattr(decision, "category", "") == "recovery"), None)
        polling = next((decision for decision in decisions if getattr(decision, "category", "") == "telegram_bot"), None)
        platforms = [decision for decision in decisions if getattr(decision, "category", "") == "platform_connection"]
        if recovery is not None and getattr(recovery, "severity", "") == "critical" and top is not recovery:
            findings.append(
                DecisionQualityFinding(
                    title="Recovery priority ordering needs review",
                    category="recovery",
                    severity="critical",
                    evidence="Recovery is critical but was not the top active decision.",
                    recommendation="Keep Recovery first until backup and restore evidence improves.",
                )
            )
        if polling is not None and getattr(polling, "severity", "") == "critical" and top is not polling and recovery is None:
            findings.append(
                DecisionQualityFinding(
                    title="Polling conflict priority ordering needs review",
                    category="telegram_bot",
                    severity="critical",
                    evidence="Polling conflict is critical but was not top priority.",
                    recommendation="Keep Telegram polling conflicts above notification or platform setup.",
                )
            )
        if any(not getattr(item, "can_wait", False) and getattr(item, "severity", "") == "needs_review" for item in platforms):
            findings.append(
                DecisionQualityFinding(
                    title="Platform setup may be too urgent",
                    category="platform_connection",
                    severity="low",
                    evidence="A platform setup item is not marked Can Wait.",
                    recommendation="Keep platform logins low unless an active workflow depends on them.",
                )
            )
        return tuple(findings)

    def _category_accuracy(self, memories: list[DecisionMemory]) -> int:
        if not memories:
            return 0
        category_totals: dict[str, list[int]] = {}
        for memory in memories:
            value = 100 if memory.outcome in {"resolved", "acted_on"} else 45 if memory.outcome in {"ignored", "dismissed"} else 65
            category_totals.setdefault(memory.category, []).append(value)
        averages = [sum(values) / len(values) for values in category_totals.values()]
        return _clamp(sum(averages) / len(averages))

    def _confidence_accuracy(self, memories: list[DecisionMemory]) -> int:
        scored = 0
        total = 0
        for memory in memories:
            if memory.confidence == "high":
                total += 1
                scored += 100 if memory.outcome in {"resolved", "acted_on", "opened"} else 35 if memory.outcome in {"failed", "dismissed"} else 70
            elif memory.confidence == "medium":
                total += 1
                scored += 85 if memory.outcome in {"resolved", "acted_on", "opened"} else 55
            elif memory.confidence == "low":
                total += 1
                scored += 80 if memory.outcome in {"stale", "ignored", "dismissed"} else 60
        return _clamp(scored / total) if total else 0

    def _briefing_quality(self, decisions: tuple[Any, ...]) -> int:
        if not decisions:
            return 0
        active = [decision for decision in decisions if not getattr(decision, "can_wait", False)]
        top = active[0] if active else None
        score = 70
        if top is not None:
            score += 10
            if getattr(top, "evidence_summary", "") and getattr(top, "next_best_move", ""):
                score += 10
        if len([decision for decision in decisions if not getattr(decision, "can_wait", False)]) > 6:
            score -= 15
        if any(getattr(decision, "can_wait", False) for decision in decisions):
            score += 5
        return _clamp(score)


def safe_decision_quality_report(
    session: Session,
    decisions: tuple[Any, ...] = (),
    *,
    actor: User | None = None,
) -> DecisionQualityReport:
    try:
        return DecisionQualityEngine().audit(session, decisions)
    except Exception as exc:  # pragma: no cover - defensive, tested through monkeypatch.
        try:
            emit_event(
                session,
                actor=actor,
                event_name="decision_quality.engine_unavailable",
                resource_type="decision_quality",
                status="warning",
                payload={"error": str(exc)[:160]},
            )
        except Exception:
            pass
        friction = FrictionSeveritySummary(
            severity="low",
            repeated_help_count=0,
            repeated_back_count=0,
            abandoned_screen_count=0,
            owner_complaint_count=0,
            navigation_loop_count=0,
            open_button_issue_count=0,
            evidence="Friction check unavailable.",
            recommendation="Try again later.",
        )
        return DecisionQualityReport(
            status="needs_review",
            available=False,
            decision_quality_score=0,
            recommendation_accuracy=0,
            category_accuracy=0,
            confidence_accuracy=0,
            briefing_quality_score=0,
            learning_status="needs_review",
            acted_on_rate=0.0,
            resolved_rate=0.0,
            ignored_rate=0.0,
            dismissal_rate=0.0,
            usefulness_score=0,
            total_memories=0,
            suppressed_count=0,
            duplicate_suppression_status="unavailable",
            findings=(
                DecisionQualityFinding(
                    title="Intelligence quality check unavailable",
                    category="learning",
                    severity="medium",
                    evidence="Decision Quality Engine could not finish.",
                    recommendation="Use current evidence and try the quality check again.",
                ),
            ),
            friction=friction,
            generated_at=_now(),
            unavailable_reason=str(exc)[:160],
        )


def adjust_decisions_with_quality(
    session: Session,
    decisions: tuple[Any, ...],
    *,
    actor: User | None = None,
) -> tuple[Any, ...]:
    return DecisionQualityEngine().adjust_decisions(session, decisions, actor=actor)


def log_quality_failure(session: Session, *, actor: User | None, error: Exception) -> None:
    try:
        emit_event(
            session,
            actor=actor,
            event_name="decision_quality.fallback_activated",
            resource_type="decision_quality",
            status="warning",
            payload={"error": str(error)[:160]},
        )
    except Exception:
        pass
