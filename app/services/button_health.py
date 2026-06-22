from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.bot.navigation_stack import parent_page_for
from app.models.button_issue import ButtonIssue
from app.models.user import User
from app.services.auth import audit_action
from app.services.callbacks import (
    SAFE_SMOKE_PAGES,
    callback_page,
    run_callback_health_smoke_test,
    safe_exception_message,
)
from app.services.chat_cleanup import chat_cleanup_metrics
from app.services.events import emit_event
from app.services.friction import create_friction_item
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.recommendations import upsert_recommendation
from app.services.shared_status import StatusCondition, compute_shared_status, normalize_status


NAVIGATION_ISSUES = {"bad_back_target", "missing_back", "missing_home", "dead_end"}
TECHNICAL_ISSUES = {"missing_handler", "renderer_error"}
UX_ISSUES = {"confusing_label", "raw_internal_label"}
RAW_SCREEN_PATTERNS = (
    "callback_data",
    "source_type",
    "entity_id",
    "metadata_json",
    "telegram_page:",
)
SNAKE_CASE_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+){1,}\b")


@dataclass(frozen=True)
class ButtonHealthSummary:
    technical_status: str
    navigation_status: str
    ux_status: str
    overall_status: str
    open_issue_count: int
    technical_issue_count: int
    navigation_issue_count: int
    ux_issue_count: int
    last_scan_at: datetime | None
    telegram_ui_status: str = "healthy"
    telegram_ui_issue_count: int = 0
    telegram_ui_evidence: str = "Telegram UI cleanup has not been checked yet."
    telegram_ui_next_action: str = "No cleanup action needed."
    issues: tuple[ButtonIssue, ...] = field(default_factory=tuple)

    @property
    def overall_label(self) -> str:
        return {
            "healthy": "Healthy",
            "needs_review": "Needs Review",
            "needs_attention": "Needs Attention",
            "critical": "Critical",
        }[self.overall_status]


def _callbacks_from_markup(markup) -> list[tuple[str, str]]:
    if markup is None:
        return []
    callbacks: list[tuple[str, str]] = []
    for row in getattr(markup, "inline_keyboard", []) or []:
        for button in row:
            data = getattr(button, "callback_data", None)
            text = getattr(button, "text", "") or ""
            if data:
                callbacks.append((str(text), str(data)))
    return callbacks


def _has_home(callbacks: Iterable[tuple[str, str]]) -> bool:
    for label, data in callbacks:
        normalized = label.strip().casefold()
        if callback_page(data) == "menu" or normalized in {"main menu", "home"}:
            return True
    return False


def _back_target(callbacks: Iterable[tuple[str, str]]) -> str | None:
    for label, data in callbacks:
        normalized = label.strip().casefold()
        if normalized == "back" or normalized.startswith("back "):
            return callback_page(data)
    return None


def _issue_key(issue: ButtonIssue) -> tuple[str, str | None, str | None, str]:
    return (issue.screen, issue.button_label, issue.callback_data, issue.issue_type)


def _find_open_issue(
    session: Session,
    *,
    screen: str,
    button_label: str | None,
    callback_data: str | None,
    issue_type: str,
) -> ButtonIssue | None:
    return session.scalar(
        select(ButtonIssue).where(
            ButtonIssue.screen == screen,
            ButtonIssue.button_label == button_label,
            ButtonIssue.callback_data == callback_data,
            ButtonIssue.issue_type == issue_type,
            ButtonIssue.status == "open",
        )
    )


def _record_issue(
    session: Session,
    *,
    actor: User | None,
    screen: str,
    button_label: str | None,
    callback_data: str | None,
    issue_type: str,
    severity: str,
    evidence_summary: str,
    recommended_fix: str,
) -> ButtonIssue:
    existing = _find_open_issue(
        session,
        screen=screen,
        button_label=button_label,
        callback_data=callback_data,
        issue_type=issue_type,
    )
    if existing is not None:
        existing.severity = severity
        existing.evidence_summary = evidence_summary
        existing.recommended_fix = recommended_fix
        return existing
    issue = ButtonIssue(
        screen=screen[:160],
        button_label=(button_label or "")[:160] or None,
        callback_data=(callback_data or "")[:260] or None,
        issue_type=issue_type,
        severity=severity,
        evidence_summary=evidence_summary,
        recommended_fix=recommended_fix,
    )
    session.add(issue)
    session.flush()
    if severity in {"medium", "high", "critical"}:
        create_friction_item(
            session,
            screen=screen,
            issue=evidence_summary,
            severity=severity,
            fix_recommendation=recommended_fix,
        )
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="button_issue_detected",
            title="Button path needs review",
            description=evidence_summary,
            severity="critical" if severity == "critical" else "warning",
            entity_type="button_issue",
            entity_id=issue.id,
            metadata={"issue_type": issue_type, "screen": screen},
        )
    return issue


def _resolve_absent_issues(session: Session, active_keys: set[tuple[str, str | None, str | None, str]]) -> None:
    open_issues = session.scalars(select(ButtonIssue).where(ButtonIssue.status == "open")).all()
    now = datetime.now(UTC)
    for issue in open_issues:
        if _issue_key(issue) not in active_keys:
            issue.status = "resolved"
            issue.resolved_at = now


def _status_for_count(count: int, worst_severity: str = "medium") -> str:
    if count <= 0:
        return "healthy"
    return normalize_status(worst_severity)


def open_button_issues(session: Session, *, limit: int | None = None) -> list[ButtonIssue]:
    statement = (
        select(ButtonIssue)
        .where(ButtonIssue.status == "open")
        .order_by(desc(ButtonIssue.detected_at), desc(ButtonIssue.id))
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement).all())


def button_health_summary(session: Session) -> ButtonHealthSummary:
    issues = tuple(open_button_issues(session))
    technical = [issue for issue in issues if issue.issue_type in TECHNICAL_ISSUES]
    navigation = [issue for issue in issues if issue.issue_type in NAVIGATION_ISSUES]
    ux = [issue for issue in issues if issue.issue_type in UX_ISSUES]
    last_scan = max((issue.detected_at for issue in issues if issue.detected_at), default=None)

    def worst(items: list[ButtonIssue]) -> str:
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return max((issue.severity for issue in items), key=lambda severity: order.get(severity, 1), default="low")

    technical_status = _status_for_count(len(technical), worst(technical))
    navigation_status = _status_for_count(len(navigation), worst(navigation))
    ux_status = _status_for_count(len(ux), worst(ux))
    cleanup = chat_cleanup_metrics(session)
    telegram_ui_issue_count = 1 if cleanup.old_menu_risk else 0
    shared = compute_shared_status(
        [
            StatusCondition("technical", technical_status, "Technical button renderer issues.", len(technical)),
            StatusCondition("navigation", navigation_status, "Navigation button issues.", len(navigation)),
            StatusCondition("ux", ux_status, "Button UX issues.", len(ux)),
            StatusCondition(
                "telegram_ui",
                cleanup.status,
                cleanup.evidence,
                telegram_ui_issue_count,
                cleanup.next_action if cleanup.old_menu_risk else None,
            ),
        ]
    )
    return ButtonHealthSummary(
        technical_status=technical_status,
        navigation_status=navigation_status,
        ux_status=ux_status,
        overall_status=shared.status,
        open_issue_count=len(issues),
        technical_issue_count=len(technical),
        navigation_issue_count=len(navigation),
        ux_issue_count=len(ux),
        telegram_ui_status=cleanup.status,
        telegram_ui_issue_count=telegram_ui_issue_count,
        telegram_ui_evidence=cleanup.evidence,
        telegram_ui_next_action=cleanup.next_action,
        last_scan_at=last_scan,
        issues=issues,
    )


def run_button_issue_scan(session: Session, *, actor: User | None) -> ButtonHealthSummary:
    from app.bot.navigation import screen_for_page
    from app.services.callbacks import _is_mutating_or_unsafe_page

    principal = PermissionPrincipal(
        telegram_id=actor.telegram_id if actor else 0,
        is_owner=True,
        role=RoleName.OWNER,
    )
    pages = sorted(SAFE_SMOKE_PAGES | {"recovery_center", "opportunities:discovery", "proxies"})
    active_keys: set[tuple[str, str | None, str | None, str]] = set()

    for page in pages:
        if _is_mutating_or_unsafe_page(page):
            continue
        try:
            screen = screen_for_page(page, principal, session=session, user=actor)
            text = getattr(screen, "text", "") or ""
            if not text.strip():
                issue = _record_issue(
                    session,
                    actor=actor,
                    screen=page,
                    button_label=None,
                    callback_data=f"nav:{page}",
                    issue_type="renderer_error",
                    severity="high",
                    evidence_summary=f"{page} returned an empty screen.",
                    recommended_fix="Make the renderer return a user-safe screen with text and navigation.",
                )
                active_keys.add(_issue_key(issue))
                continue
            callbacks = _callbacks_from_markup(getattr(screen, "reply_markup", None))
            if page not in {"menu", "command_center"}:
                back = _back_target(callbacks)
                if back is None:
                    issue = _record_issue(
                        session,
                        actor=actor,
                        screen=page,
                        button_label="Back",
                        callback_data=None,
                        issue_type="missing_back",
                        severity="medium",
                        evidence_summary=f"{page} has no Back button.",
                        recommended_fix="Add a Back button that returns to the screen parent.",
                    )
                    active_keys.add(_issue_key(issue))
                elif back != parent_page_for(page):
                    issue = _record_issue(
                        session,
                        actor=actor,
                        screen=page,
                        button_label="Back",
                        callback_data=f"nav:{back}" if back else None,
                        issue_type="bad_back_target",
                        severity="medium",
                        evidence_summary=f"{page} Back goes to {back}; expected {parent_page_for(page)}.",
                        recommended_fix="Update the page controls so Back returns to the correct parent screen.",
                    )
                    active_keys.add(_issue_key(issue))
                if not _has_home(callbacks):
                    issue = _record_issue(
                        session,
                        actor=actor,
                        screen=page,
                        button_label="Main Menu",
                        callback_data="nav:menu",
                        issue_type="missing_home",
                        severity="medium",
                        evidence_summary=f"{page} has no Home/Main Menu button.",
                        recommended_fix="Add a Home/Main Menu button so users can recover quickly.",
                    )
                    active_keys.add(_issue_key(issue))
            if not callbacks:
                issue = _record_issue(
                    session,
                    actor=actor,
                    screen=page,
                    button_label=None,
                    callback_data=None,
                    issue_type="dead_end",
                    severity="medium",
                    evidence_summary=f"{page} returned no buttons.",
                    recommended_fix="Add at least one clear action plus Back/Home navigation.",
                )
                active_keys.add(_issue_key(issue))
            for label, callback_data in callbacks:
                if "nav:" in label or SNAKE_CASE_RE.search(label):
                    issue = _record_issue(
                        session,
                        actor=actor,
                        screen=page,
                        button_label=label,
                        callback_data=callback_data,
                        issue_type="raw_internal_label",
                        severity="medium",
                        evidence_summary=f"{page} shows an internal-looking button label: {label}.",
                        recommended_fix="Rename the button in plain human language.",
                    )
                    active_keys.add(_issue_key(issue))
            lowered = text.casefold()
            for raw in RAW_SCREEN_PATTERNS:
                if raw in lowered:
                    issue = _record_issue(
                        session,
                        actor=actor,
                        screen=page,
                        button_label=None,
                        callback_data=f"nav:{page}",
                        issue_type="raw_internal_label",
                        severity="medium",
                        evidence_summary=f"{page} displays internal text: {raw}.",
                        recommended_fix="Move internal details behind Technical Details.",
                    )
                    active_keys.add(_issue_key(issue))
                    break
        except Exception as exc:
            issue = _record_issue(
                session,
                actor=actor,
                screen=page,
                button_label=None,
                callback_data=f"nav:{page}",
                issue_type="renderer_error",
                severity="high",
                evidence_summary=f"{page} failed during button scan: {type(exc).__name__}.",
                recommended_fix=f"Fix the renderer exception: {safe_exception_message(exc)}",
            )
            active_keys.add(_issue_key(issue))

    report = run_callback_health_smoke_test(session, actor=actor) if actor is not None else None
    if report is not None:
        for failure in report.failing:
            issue = _record_issue(
                session,
                actor=actor,
                screen=failure.page,
                button_label=None,
                callback_data=f"nav:{failure.page}",
                issue_type="renderer_error",
                severity="high",
                evidence_summary=f"{failure.page} failed callback smoke test: {failure.exception_type}.",
                recommended_fix=failure.message,
            )
            active_keys.add(_issue_key(issue))

    _resolve_absent_issues(session, active_keys)
    summary = button_health_summary(session)
    audit_action(
        session,
        actor=actor,
        action="button_issue.scan_completed",
        resource_type="button_health",
        status=summary.overall_status,
        details={
            "open_issues": summary.open_issue_count,
            "technical": summary.technical_issue_count,
            "navigation": summary.navigation_issue_count,
            "ux": summary.ux_issue_count,
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name="button_issue.scan_completed",
        resource_type="button_health",
        status=summary.overall_status,
        payload={
            "open_issues": summary.open_issue_count,
            "technical": summary.technical_issue_count,
            "navigation": summary.navigation_issue_count,
            "ux": summary.ux_issue_count,
        },
    )
    return summary

