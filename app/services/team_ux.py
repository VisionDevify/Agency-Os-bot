from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.button_issue import ButtonIssue
from app.models.callback_error import CallbackErrorLog
from app.models.friction import FrictionItem
from app.models.recommendation import Recommendation
from app.models.user import User
from app.services.chat_cleanup import CleanupMetrics, chat_cleanup_metrics
from app.services.friction import create_friction_item


ROLE_METADATA: dict[str, dict[str, object]] = {
    "owner": {
        "label": "Owner",
        "intended_audience": "Runs production, approvals, recovery, and final decisions.",
        "owner_only": True,
        "manager_capable": False,
        "future_chatter_screen": False,
        "future_va_screen": False,
    },
    "manager": {
        "label": "Manager",
        "intended_audience": "Reviews team work, assignments, and operating priorities.",
        "owner_only": False,
        "manager_capable": True,
        "future_chatter_screen": False,
        "future_va_screen": False,
    },
    "chatter": {
        "label": "Chatter",
        "intended_audience": "Future simplified workspace for assigned conversations and opportunities.",
        "owner_only": False,
        "manager_capable": False,
        "future_chatter_screen": True,
        "future_va_screen": False,
    },
    "va": {
        "label": "VA",
        "intended_audience": "Future simplified workspace for assigned operational tasks.",
        "owner_only": False,
        "manager_capable": False,
        "future_chatter_screen": False,
        "future_va_screen": True,
    },
}


SCREEN_ROLE_METADATA: dict[str, dict[str, object]] = {
    "menu": {"intended_audience": "owner,manager,chatter,va", "owner_only": False, "manager_capable": True},
    "owner_advanced": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "coo:briefing": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "ai_brain": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "search": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "recovery_center": {"intended_audience": "owner", "owner_only": True, "manager_capable": False},
    "agency_activation": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "decision:memory": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "reality:check": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "intelligence:quality": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "platforms": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
    "platforms:notifications": {"intended_audience": "owner,manager", "owner_only": True, "manager_capable": True},
}


@dataclass(frozen=True)
class TeamRoleMetadata:
    role: str
    label: str
    intended_audience: str
    owner_only: bool
    manager_capable: bool
    future_chatter_screen: bool
    future_va_screen: bool


@dataclass(frozen=True)
class ScreenAudienceMetadata:
    screen: str
    intended_audience: str
    owner_only: bool
    manager_capable: bool
    future_chatter_screen: bool
    future_va_screen: bool


@dataclass(frozen=True)
class UserTrustSignals:
    status: str
    callback_failures: int
    navigation_failures: int
    stale_menu_confusion: int
    abandoned_screens: int
    repeated_back_usage: int
    help_usage_after_screen_open: int
    evidence: str
    next_action: str


@dataclass(frozen=True)
class TeamUXReadiness:
    status: str
    score: int
    navigation_clarity: int
    screen_clarity: int
    stale_menu_safety: int
    callback_reliability: int
    onboarding_friendliness: int
    next_action_clarity: int
    evidence: str
    next_action: str
    trust_signals: UserTrustSignals

    @property
    def label(self) -> str:
        return {
            "ready": "Ready",
            "needs_review": "Needs Review",
            "not_ready": "Not Ready",
            "unavailable": "Unavailable",
        }.get(self.status, "Needs Review")

    @property
    def meaningful(self) -> bool:
        return self.status != "ready"


@dataclass(frozen=True)
class AIReadabilityCheck:
    status: str
    score: int
    intended_audience: str
    issues: tuple[str, ...]
    simplified_suggestion: str


def team_role_metadata(role: str) -> TeamRoleMetadata:
    key = role.strip().casefold()
    data = ROLE_METADATA.get(key, ROLE_METADATA["owner"])
    return TeamRoleMetadata(
        role=key,
        label=str(data["label"]),
        intended_audience=str(data["intended_audience"]),
        owner_only=bool(data["owner_only"]),
        manager_capable=bool(data["manager_capable"]),
        future_chatter_screen=bool(data["future_chatter_screen"]),
        future_va_screen=bool(data["future_va_screen"]),
    )


def all_team_role_metadata() -> tuple[TeamRoleMetadata, ...]:
    return tuple(team_role_metadata(role) for role in ("owner", "manager", "chatter", "va"))


def screen_audience_metadata(screen: str) -> ScreenAudienceMetadata:
    key = screen.strip() or "menu"
    data = SCREEN_ROLE_METADATA.get(
        key,
        {
            "intended_audience": "owner,manager",
            "owner_only": False,
            "manager_capable": True,
            "future_chatter_screen": False,
            "future_va_screen": False,
        },
    )
    return ScreenAudienceMetadata(
        screen=key,
        intended_audience=str(data["intended_audience"]),
        owner_only=bool(data["owner_only"]),
        manager_capable=bool(data["manager_capable"]),
        future_chatter_screen=bool(data.get("future_chatter_screen", False)),
        future_va_screen=bool(data.get("future_va_screen", False)),
    )


def all_screen_audience_metadata() -> tuple[ScreenAudienceMetadata, ...]:
    return tuple(screen_audience_metadata(screen) for screen in sorted(SCREEN_ROLE_METADATA))


def _count_friction(session: Session, needle: str) -> int:
    return int(
        session.scalar(
            select(func.count(FrictionItem.id)).where(FrictionItem.issue.ilike(f"%{needle}%"))
        )
        or 0
    )


def trust_signal_summary(session: Session, *, cleanup: CleanupMetrics | None = None) -> UserTrustSignals:
    cleanup = cleanup or chat_cleanup_metrics(session)
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    recent_callback_errors = list(
        session.scalars(select(CallbackErrorLog).where(CallbackErrorLog.created_at >= cutoff)).all()
    )
    callback_failures = 0
    for error in recent_callback_errors:
        page = error.page or error.callback_data or "unknown"
        resolved = session.scalar(
            select(Recommendation.id)
            .where(
                Recommendation.recommendation_type == "callback_failure",
                Recommendation.entity_type == "telegram_callback",
                Recommendation.entity_id == page,
                Recommendation.status == "resolved",
            )
            .limit(1)
        )
        if resolved is None:
            callback_failures += 1
    navigation_failures = int(
        session.scalar(
            select(func.count(ButtonIssue.id)).where(
                ButtonIssue.status == "open",
                ButtonIssue.issue_type.in_(("bad_back_target", "missing_back", "missing_home", "dead_end")),
            )
        )
        or 0
    )
    stale_menu_confusion = cleanup.stale_callback_count + cleanup.multiple_active_count + (1 if cleanup.remaining_count else 0)
    abandoned_screens = _count_friction(session, "abandon")
    repeated_back_usage = _count_friction(session, "back")
    help_usage = _count_friction(session, "help")
    total = callback_failures + navigation_failures + stale_menu_confusion + abandoned_screens + repeated_back_usage + help_usage
    if callback_failures or navigation_failures >= 3:
        status = "not_ready"
        evidence = "Recent callback or navigation failures may confuse live users."
        next_action = "Open Button Health."
    elif total:
        status = "needs_review"
        evidence = "Fortuna found trust signals such as old menus, Back/Help loops, or open navigation issues."
        next_action = cleanup.next_action if cleanup.old_menu_risk else "Review Button Health."
    else:
        status = "ready"
        evidence = "No current trust signals are blocking team navigation."
        next_action = "No action needed."
    return UserTrustSignals(
        status=status,
        callback_failures=callback_failures,
        navigation_failures=navigation_failures,
        stale_menu_confusion=stale_menu_confusion,
        abandoned_screens=abandoned_screens,
        repeated_back_usage=repeated_back_usage,
        help_usage_after_screen_open=help_usage,
        evidence=evidence,
        next_action=next_action,
    )


def record_user_trust_signal(
    session: Session,
    *,
    screen: str,
    signal_type: str,
    evidence: str,
    severity: str = "medium",
    actor: User | None = None,
) -> FrictionItem:
    del actor  # Friction records are intentionally lightweight in the current schema.
    return create_friction_item(
        session,
        screen=screen,
        issue=f"{signal_type}: {evidence}",
        severity=severity,
        fix_recommendation="Simplify the screen, verify Back/Home paths, and add a regression test if behavior changed.",
    )


def _score_from_cleanup(cleanup: CleanupMetrics) -> int:
    if cleanup.status == "healthy":
        return 100
    if cleanup.multiple_active_count:
        return 45
    if cleanup.failed_count >= 3:
        return 65
    return 75


def team_ux_readiness(session: Session) -> TeamUXReadiness:
    cleanup = chat_cleanup_metrics(session)
    trust = trust_signal_summary(session, cleanup=cleanup)
    open_nav = trust.navigation_failures
    ux_issues = int(
        session.scalar(
            select(func.count(ButtonIssue.id)).where(
                ButtonIssue.status == "open",
                ButtonIssue.issue_type.in_(("confusing_label", "raw_internal_label")),
            )
        )
        or 0
    )
    technical_issues = int(
        session.scalar(
            select(func.count(ButtonIssue.id)).where(
                ButtonIssue.status == "open",
                ButtonIssue.issue_type.in_(("missing_handler", "renderer_error")),
            )
        )
        or 0
    )
    dead_ends = int(
        session.scalar(
            select(func.count(ButtonIssue.id)).where(ButtonIssue.status == "open", ButtonIssue.issue_type == "dead_end")
        )
        or 0
    )
    navigation_clarity = 100 if open_nav == 0 and cleanup.status == "healthy" else 70 if open_nav <= 1 else 45
    screen_clarity = 100 if ux_issues == 0 else 80 if ux_issues <= 2 else 55
    stale_menu_safety = _score_from_cleanup(cleanup)
    callback_reliability = 100 if technical_issues == 0 and trust.callback_failures == 0 else 70 if technical_issues <= 1 else 45
    onboarding_friendliness = 100 if not (trust.repeated_back_usage or trust.help_usage_after_screen_open or trust.abandoned_screens) else 75
    next_action_clarity = 100 if dead_ends == 0 else 60
    score = round(
        (
            navigation_clarity
            + screen_clarity
            + stale_menu_safety
            + callback_reliability
            + onboarding_friendliness
            + next_action_clarity
        )
        / 6
    )
    if (trust.callback_failures and open_nav) or callback_reliability < 60 or navigation_clarity < 60 or stale_menu_safety < 50:
        status = "not_ready"
    elif score < 90 or trust.status != "ready":
        status = "needs_review"
    else:
        status = "ready"
    evidence_parts: list[str] = []
    if cleanup.old_menu_risk:
        evidence_parts.append(cleanup.evidence)
    if open_nav:
        evidence_parts.append(f"{open_nav} open navigation issue(s).")
    if ux_issues:
        evidence_parts.append(f"{ux_issues} confusing screen or button label issue(s).")
    if technical_issues:
        evidence_parts.append(f"{technical_issues} technical button issue(s).")
    if not evidence_parts:
        evidence_parts.append("Active screen, Back/Home paths, and next actions look clear.")
    if cleanup.old_menu_risk:
        next_action = cleanup.next_action
    elif open_nav or technical_issues or ux_issues:
        next_action = "Open Button Health."
    elif trust.status != "ready":
        next_action = trust.next_action
    else:
        next_action = "No action needed."
    return TeamUXReadiness(
        status=status,
        score=max(0, min(100, score)),
        navigation_clarity=navigation_clarity,
        screen_clarity=screen_clarity,
        stale_menu_safety=stale_menu_safety,
        callback_reliability=callback_reliability,
        onboarding_friendliness=onboarding_friendliness,
        next_action_clarity=next_action_clarity,
        evidence=" ".join(evidence_parts),
        next_action=next_action,
        trust_signals=trust,
    )


_SNAKE_CASE_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+){1,}\b")
_JARGON_TERMS = (
    "calibration",
    "callback",
    "constraint",
    "enum",
    "idempotency",
    "metadata",
    "observability",
    "telemetry",
    "traceback",
)


def ai_readability_check(text: str, *, intended_audience: str = "manager") -> AIReadabilityCheck:
    lowered = text.casefold()
    issues: list[str] = []
    jargon = [term for term in _JARGON_TERMS if term in lowered]
    if jargon:
        issues.append("Uses developer language.")
    if _SNAKE_CASE_RE.search(text):
        issues.append("Shows internal snake_case wording.")
    if any(len(line) > 180 for line in text.splitlines()):
        issues.append("Contains a long paragraph.")
    if "next" not in lowered and "what to do" not in lowered:
        issues.append("Does not clearly say what to do next.")
    score = 100 - 20 * len(issues)
    status = "ready" if score >= 85 else "needs_review" if score >= 60 else "not_ready"
    suggestion = (
        text.replace("Insufficient data", "Fortuna needs more information here")
        .replace("insufficient data", "Fortuna needs more information here")
        .replace("Calibration", "How accurate Fortuna is")
        .replace("calibration", "how accurate Fortuna is")
    )
    if "Next" not in suggestion and "next" not in suggestion.casefold():
        suggestion = f"{suggestion.rstrip()}\n\nNext: choose the safest recommended action."
    return AIReadabilityCheck(
        status=status,
        score=max(0, min(100, score)),
        intended_audience=intended_audience,
        issues=tuple(issues),
        simplified_suggestion=suggestion,
    )
