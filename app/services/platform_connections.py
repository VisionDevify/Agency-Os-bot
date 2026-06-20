from __future__ import annotations

import datetime as dt
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.platform import PLATFORM_IDENTIFIERS, PlatformConnection
from app.models.recovery import BackupStorageTarget
from app.models.reporting import NotificationDeliveryAttempt, NotificationTarget
from app.services.notifications import purpose_aliases
from app.services.recovery import recovery_risk_assessment
from app.services.shared_status import StatusCondition, compute_shared_status


WEBSITE_REACHABILITY_STATUSES = ("reachable", "slow_or_limited", "unreachable", "not_checked")
CONNECTION_STATUSES = ("not_connected", "ready_to_connect", "connection_configured", "connected", "needs_review", "failed")
STATS_STATUSES = ("not_available", "waiting_for_connection", "fresh", "stale", "failed")
NOTIFICATION_STATUSES = ("not_configured", "configured", "verified", "simulated", "failed")
READINESS_STATUSES = ("healthy", "needs_review", "needs_attention", "critical")
SUPPORTED_CONNECTION_METHODS = ("manual", "official_api", "approved_connector", "session_based")
STATS_FRESHNESS_HOURS = 24

_SECRET_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "key=",
    "authorization",
    "credential",
    "cookie",
    "session",
    "database_url",
    "redis_url",
)


@dataclass(frozen=True)
class PlatformLayerState:
    status: str
    label: str
    evidence: str
    checked_at: dt.datetime | None = None
    next_action: str | None = None


@dataclass(frozen=True)
class PlatformIntegrationStatus:
    platform: str
    display_name: str
    emoji: str
    supported_connection_methods: tuple[str, ...]
    website: PlatformLayerState
    connection: PlatformLayerState
    stats: PlatformLayerState
    notifications: PlatformLayerState
    readiness: PlatformLayerState
    evidence_summary: str
    next_action: str
    compliance_metadata: dict[str, object] = field(default_factory=dict)


class PlatformIntegration(Protocol):
    platform: str
    display_name: str
    supported_connection_methods: tuple[str, ...]

    def website_reachability_check(self, session: Session, *, persist: bool = False) -> PlatformLayerState:
        ...

    def connection_verification(self, session: Session) -> PlatformLayerState:
        ...

    def stats_availability_check(self, session: Session) -> PlatformLayerState:
        ...

    def notification_route_validation(self, session: Session) -> PlatformLayerState:
        ...

    def activation_readiness_evaluation(self, session: Session) -> PlatformLayerState:
        ...

    def evidence_generation(self, session: Session) -> str:
        ...

    def status(self, session: Session) -> PlatformIntegrationStatus:
        ...


@dataclass(frozen=True)
class PlatformDefinition:
    platform: str
    display_name: str
    emoji: str
    website_url: str | None
    supported_connection_methods: tuple[str, ...]
    stats_requires_connection: bool
    notification_purpose: str | None
    activation_notes: str
    compliance_metadata: dict[str, object]


PLATFORM_DEFINITIONS: dict[str, PlatformDefinition] = {
    "instagram": PlatformDefinition(
        platform="instagram",
        display_name="Instagram",
        emoji="📸",
        website_url="https://www.instagram.com/",
        supported_connection_methods=("official_api", "approved_connector", "session_based", "manual"),
        stats_requires_connection=True,
        notification_purpose="alerts",
        activation_notes="Prepare official/API or owner-approved session access before requesting stats.",
        compliance_metadata={"automation": "human_review_only", "prohibited": ("auto_like", "auto_comment", "auto_follow")},
    ),
    "x": PlatformDefinition(
        platform="x",
        display_name="X",
        emoji="𝕏",
        website_url="https://x.com/",
        supported_connection_methods=("official_api", "approved_connector", "session_based", "manual"),
        stats_requires_connection=True,
        notification_purpose="alerts",
        activation_notes="Use official/API, approved connector, session-based, or manual workflows only.",
        compliance_metadata={"automation": "human_review_only", "prohibited": ("auto_like", "auto_comment", "auto_follow")},
    ),
    "onlyfans": PlatformDefinition(
        platform="onlyfans",
        display_name="OnlyFans",
        emoji="🔥",
        website_url="https://onlyfans.com/",
        supported_connection_methods=("approved_connector", "session_based", "manual"),
        stats_requires_connection=True,
        notification_purpose="alerts",
        activation_notes="Use owner-approved access only. Do not collect credentials in normal chat.",
        compliance_metadata={"automation": "human_review_only", "private_data": "do_not_scrape"},
    ),
    "telegram": PlatformDefinition(
        platform="telegram",
        display_name="Telegram",
        emoji="📢",
        website_url="https://telegram.org/",
        supported_connection_methods=("approved_connector", "manual"),
        stats_requires_connection=False,
        notification_purpose="hq",
        activation_notes="Register Fortuna HQ, Ops, and Alerts targets from inside approved Telegram chats.",
        compliance_metadata={"automation": "notifications_only"},
    ),
    "email": PlatformDefinition(
        platform="email",
        display_name="Email",
        emoji="📧",
        website_url=None,
        supported_connection_methods=("approved_connector", "manual"),
        stats_requires_connection=False,
        notification_purpose=None,
        activation_notes="Email delivery is prepared as a future connector. It is not connected yet.",
        compliance_metadata={"automation": "future_connector"},
    ),
    "backup_storage": PlatformDefinition(
        platform="backup_storage",
        display_name="Backup Storage",
        emoji="🛡",
        website_url=None,
        supported_connection_methods=("manual", "approved_connector"),
        stats_requires_connection=False,
        notification_purpose=None,
        activation_notes="Configure external S3-compatible storage, then run backup and restore validation.",
        compliance_metadata={"credentials": "owner_only_encrypted_storage"},
    ),
    "system_alerts": PlatformDefinition(
        platform="system_alerts",
        display_name="System Alerts",
        emoji="🚨",
        website_url=None,
        supported_connection_methods=("manual",),
        stats_requires_connection=False,
        notification_purpose="hq",
        activation_notes="System alerts use configured Fortuna notification targets.",
        compliance_metadata={"automation": "internal_alerts_only"},
    ),
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def sanitize_platform_payload(value: object) -> object:
    text = str(value)
    lowered = text.casefold()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(key): sanitize_platform_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_platform_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_platform_payload(item) for item in value)
    if isinstance(value, str):
        return value[:500]
    return value


def _safe_text(value: object, fallback: str = "") -> str:
    text = str(sanitize_platform_payload(value or fallback))
    return text if text else fallback


def _evidence_dict(connection: PlatformConnection) -> dict[str, object]:
    return connection.evidence_json if isinstance(connection.evidence_json, dict) else {}


def _bool_to_status(value: bool | None, *, true_status: str, false_status: str, none_status: str) -> str:
    if value is True:
        return true_status
    if value is False:
        return false_status
    return none_status


def _connection_for_platform(session: Session, definition: PlatformDefinition) -> PlatformConnection:
    connection = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == definition.platform))
    if connection is None:
        connection = PlatformConnection(
            platform=definition.platform,
            display_name=definition.display_name,
            status="ready_to_connect" if definition.platform in {"instagram", "x", "onlyfans"} else "not_connected",
            approved_method="not_configured",
            evidence_summary="No connection has been verified yet.",
            evidence_json={},
            next_action=definition.activation_notes,
        )
        session.add(connection)
        session.flush()
    return connection


def ensure_platform_connections(session: Session) -> list[PlatformConnection]:
    connections = [_connection_for_platform(session, PLATFORM_DEFINITIONS[platform]) for platform in PLATFORM_IDENTIFIERS]
    session.flush()
    return connections


def _safe_http_reachability(url: str, *, timeout_seconds: int = 5) -> PlatformLayerState:
    checked_at = _now()
    parsed = urlparse(url)
    if parsed.hostname:
        try:
            socket.getaddrinfo(parsed.hostname, 443, proto=socket.IPPROTO_TCP)
        except OSError:
            return PlatformLayerState(
                status="unreachable",
                label="Unreachable",
                evidence=f"DNS lookup failed for {parsed.hostname}.",
                checked_at=checked_at,
                next_action="Try again later or confirm the public website is reachable.",
            )
    request = urllib.request.Request(url, headers={"User-Agent": "FortunaOS-ReachabilityCheck/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 405, 429}:
            return PlatformLayerState(
                status="slow_or_limited",
                label="Reachable but limited",
                evidence=f"Public website responded with HTTP {exc.code}.",
                checked_at=checked_at,
                next_action="This does not mean Fortuna is logged in. Use connection setup when ready.",
            )
        return PlatformLayerState(
            status="unreachable",
            label="Unreachable",
            evidence=f"Public website responded with HTTP {exc.code}.",
            checked_at=checked_at,
            next_action="Try again later.",
        )
    except (TimeoutError, urllib.error.URLError, OSError):
        return PlatformLayerState(
            status="unreachable",
            label="Unreachable",
            evidence="Public website check timed out or could not connect.",
            checked_at=checked_at,
            next_action="Try again later.",
        )
    if status_code < 400:
        return PlatformLayerState(
            status="reachable",
            label="Reachable",
            evidence=f"Public website responded with HTTP {status_code}.",
            checked_at=checked_at,
            next_action="Connection setup is still required for account access.",
        )
    return PlatformLayerState(
        status="slow_or_limited",
        label="Reachable but limited",
        evidence=f"Public website responded with HTTP {status_code}.",
        checked_at=checked_at,
        next_action="Connection setup is still required for account access.",
    )


class StaticPlatformIntegration:
    def __init__(self, definition: PlatformDefinition):
        self.definition = definition
        self.platform = definition.platform
        self.display_name = definition.display_name
        self.supported_connection_methods = definition.supported_connection_methods

    def website_reachability_check(self, session: Session, *, persist: bool = False) -> PlatformLayerState:
        connection = _connection_for_platform(session, self.definition)
        if self.definition.website_url is None:
            return PlatformLayerState(
                status="not_checked",
                label="Not checked",
                evidence="This platform does not have a public website check in Fortuna yet.",
                next_action=self.definition.activation_notes,
            )
        if not persist:
            evidence = _evidence_dict(connection)
            status = _bool_to_status(
                connection.website_reachable,
                true_status="reachable",
                false_status="unreachable",
                none_status="not_checked",
            )
            return PlatformLayerState(
                status=status,
                label={
                    "reachable": "Reachable",
                    "unreachable": "Unreachable",
                    "not_checked": "Not checked yet",
                }[status],
                evidence=_safe_text(
                    evidence.get("website", {}).get("summary") if isinstance(evidence.get("website"), dict) else None,
                    "No public website check has been recorded yet.",
                ),
                checked_at=evidence.get("website", {}).get("checked_at") if isinstance(evidence.get("website"), dict) else None,
                next_action="Test Website." if status == "not_checked" else "Connection setup is still separate.",
            )
        result = _safe_http_reachability(self.definition.website_url)
        connection.website_reachable = result.status in {"reachable", "slow_or_limited"}
        connection.last_connection_check_at = result.checked_at
        evidence = dict(connection.evidence_json or {})
        evidence["website"] = {
            "status": result.status,
            "summary": sanitize_platform_payload(result.evidence),
            "checked_at": result.checked_at.isoformat() if result.checked_at else None,
            "platform": self.platform,
        }
        connection.evidence_json = evidence
        connection.evidence_summary = _safe_text(result.evidence)
        connection.next_action = result.next_action
        session.flush()
        return result

    def connection_verification(self, session: Session) -> PlatformLayerState:
        connection = _connection_for_platform(session, self.definition)
        evidence = _evidence_dict(connection)
        status = connection.status
        if connection.login_connected:
            return PlatformLayerState(
                status="connected",
                label="Connected",
                evidence=_safe_text(
                    evidence.get("connection", {}).get("summary") if isinstance(evidence.get("connection"), dict) else None,
                    "A connection verification has been recorded.",
                ),
                checked_at=connection.last_connection_check_at,
                next_action="Run Stats Check.",
            )
        if status == "failed":
            return PlatformLayerState(
                status="failed",
                label="Failed",
                evidence=_safe_text(connection.evidence_summary, "The latest connection attempt failed."),
                checked_at=connection.last_connection_check_at,
                next_action="Review setup details.",
            )
        if connection.approved_method != "not_configured":
            return PlatformLayerState(
                status="connection_configured",
                label="Configured, not verified",
                evidence=f"Approved method is {connection.approved_method.replace('_', ' ')}.",
                checked_at=connection.last_connection_check_at,
                next_action="Run connection verification.",
            )
        return PlatformLayerState(
            status="ready_to_connect",
            label="Not connected yet",
            evidence="No owner-approved login, API, session, or connector has been verified.",
            checked_at=connection.last_connection_check_at,
            next_action="Secure credential flow not active yet.",
        )

    def stats_availability_check(self, session: Session) -> PlatformLayerState:
        connection = _connection_for_platform(session, self.definition)
        if not self.definition.stats_requires_connection:
            return PlatformLayerState(
                status="not_available",
                label="Not available",
                evidence="This platform does not expose a stats layer in Fortuna yet.",
                checked_at=connection.last_stats_check_at,
                next_action=self.definition.activation_notes,
            )
        if not connection.login_connected:
            return PlatformLayerState(
                status="waiting_for_connection",
                label="Waiting for connection",
                evidence="Stats require a verified owner-approved platform connection.",
                checked_at=connection.last_stats_check_at,
                next_action="Complete connection setup first.",
            )
        stats_evidence = _evidence_dict(connection).get("stats", {})
        if not isinstance(stats_evidence, dict):
            stats_evidence = {}
        stats_summary = stats_evidence.get("summary")
        if connection.stats_available and connection.stats_fresh and connection.last_stats_check_at and stats_summary:
            return PlatformLayerState(
                status="fresh",
                label="Fresh",
                evidence=_safe_text(stats_summary, "Recent stats retrieval succeeded."),
                checked_at=connection.last_stats_check_at,
                next_action="Review platform insights.",
            )
        if connection.stats_available:
            return PlatformLayerState(
                status="stale",
                label="Stale",
                evidence="Stats were retrieved before, but they are outside the freshness window or missing timestamp evidence.",
                checked_at=connection.last_stats_check_at,
                next_action="Run Stats Check.",
            )
        return PlatformLayerState(
            status="not_available",
            label="Not available",
            evidence="No successful stats retrieval has been recorded.",
            checked_at=connection.last_stats_check_at,
            next_action="Run Stats Check after connection setup.",
        )

    def notification_route_validation(self, session: Session) -> PlatformLayerState:
        connection = _connection_for_platform(session, self.definition)
        if self.definition.notification_purpose is None:
            return PlatformLayerState(
                status="not_configured",
                label="Not configured",
                evidence="No notification route is active for this platform yet.",
                checked_at=connection.last_notification_check_at,
                next_action="Open Notification Center when routing is needed.",
            )
        aliases = purpose_aliases(self.definition.notification_purpose)
        target = session.scalar(
            select(NotificationTarget)
            .where(NotificationTarget.is_active.is_(True), NotificationTarget.purpose.in_(aliases))
            .order_by(desc(NotificationTarget.created_at), desc(NotificationTarget.id))
            .limit(1)
        )
        latest_attempt = session.scalar(
            select(NotificationDeliveryAttempt)
            .where(
                NotificationDeliveryAttempt.notification_target_id == target.id
                if target
                else NotificationDeliveryAttempt.id.is_(None)
            )
            .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
            .limit(1)
        )
        connection.notifications_configured = target is not None
        connection.last_notification_check_at = _now()
        session.flush()
        if target is None:
            return PlatformLayerState(
                status="not_configured",
                label="Not configured",
                evidence=f"No active {self.definition.notification_purpose.title()} target is registered.",
                checked_at=connection.last_notification_check_at,
                next_action="Register Fortuna Alerts or HQ in Notification Routing.",
            )
        if latest_attempt and latest_attempt.status == "sent":
            return PlatformLayerState(
                status="verified",
                label="Verified",
                evidence="A recent delivery attempt succeeded for this route.",
                checked_at=latest_attempt.attempted_at,
                next_action="No action needed.",
            )
        return PlatformLayerState(
            status="configured",
            label="Configured",
            evidence=f"A {self.definition.notification_purpose.title()} notification target exists, but no successful delivery validation is recorded yet.",
            checked_at=connection.last_notification_check_at,
            next_action="Run a safe notification route test.",
        )

    def activation_readiness_evaluation(self, session: Session) -> PlatformLayerState:
        website = self.website_reachability_check(session)
        connection = self.connection_verification(session)
        stats = self.stats_availability_check(session)
        notifications = self.notification_route_validation(session)
        conditions = [
            StatusCondition(
                "website",
                "healthy" if website.status in {"reachable", "slow_or_limited", "not_checked"} else "needs_review",
                website.evidence,
                0 if website.status in {"reachable", "slow_or_limited", "not_checked"} else 1,
                website.next_action,
            ),
            StatusCondition(
                "connection",
                "healthy" if connection.status == "connected" else "needs_review",
                connection.evidence,
                0 if connection.status == "connected" else 1,
                connection.next_action,
            ),
            StatusCondition(
                "stats",
                "healthy" if stats.status in {"fresh", "not_available"} else "needs_review",
                stats.evidence,
                0 if stats.status in {"fresh", "not_available"} else 1,
                stats.next_action,
            ),
            StatusCondition(
                "notifications",
                "healthy" if notifications.status in {"configured", "verified"} else "needs_review",
                notifications.evidence,
                0 if notifications.status in {"configured", "verified"} else 1,
                notifications.next_action,
            ),
        ]
        shared = compute_shared_status(conditions)
        return PlatformLayerState(
            status=shared.status,
            label=shared.label,
            evidence="; ".join(shared.evidence) or "Activation readiness is prepared from current evidence.",
            next_action=shared.recommended_action if not shared.is_healthy else self.definition.activation_notes,
        )

    def evidence_generation(self, session: Session) -> str:
        website = self.website_reachability_check(session)
        connection = self.connection_verification(session)
        stats = self.stats_availability_check(session)
        notifications = self.notification_route_validation(session)
        return (
            f"Website: {website.label}. "
            f"Login: {connection.label}. "
            f"Stats: {stats.label}. "
            f"Notifications: {notifications.label}."
        )

    def status(self, session: Session) -> PlatformIntegrationStatus:
        website = self.website_reachability_check(session)
        connection = self.connection_verification(session)
        stats = self.stats_availability_check(session)
        notifications = self.notification_route_validation(session)
        readiness = self.activation_readiness_evaluation(session)
        return PlatformIntegrationStatus(
            platform=self.platform,
            display_name=self.display_name,
            emoji=self.definition.emoji,
            supported_connection_methods=self.supported_connection_methods,
            website=website,
            connection=connection,
            stats=stats,
            notifications=notifications,
            readiness=readiness,
            evidence_summary=self.evidence_generation(session),
            next_action=readiness.next_action or self.definition.activation_notes,
            compliance_metadata=self.definition.compliance_metadata,
        )


class BackupStorageIntegration(StaticPlatformIntegration):
    def connection_verification(self, session: Session) -> PlatformLayerState:
        _connection_for_platform(session, self.definition)
        target = session.scalar(
            select(BackupStorageTarget)
            .where(
                BackupStorageTarget.enabled.is_(True),
                BackupStorageTarget.connection_status == "active",
                BackupStorageTarget.provider_available.is_(True),
            )
            .order_by(desc(BackupStorageTarget.last_success_at), desc(BackupStorageTarget.id))
            .limit(1)
        )
        if target is None:
            return PlatformLayerState(
                status="ready_to_connect",
                label="Not connected yet",
                evidence="No external backup storage target has passed connection testing.",
                next_action="Open Recovery Center -> Backup Storage.",
            )
        return PlatformLayerState(
            status="connected",
            label="Connected",
            evidence=f"{target.name} has passed storage connection testing.",
            checked_at=target.last_success_at or target.last_test_at,
            next_action="Run Backup.",
        )

    def stats_availability_check(self, session: Session) -> PlatformLayerState:
        recovery = recovery_risk_assessment(session)
        if recovery.latest_backup is None:
            return PlatformLayerState(
                status="not_available",
                label="No backup yet",
                evidence="No successful backup is recorded yet.",
                next_action="Run your first backup.",
            )
        return PlatformLayerState(
            status="fresh" if recovery.status in {"healthy", "needs_review"} else "stale",
            label="Backup evidence recorded",
            evidence=recovery.last_backup_status,
            checked_at=recovery.latest_backup.finished_at or recovery.latest_backup.started_at,
            next_action=recovery.next_best_move,
        )


class InternalAlertIntegration(StaticPlatformIntegration):
    def website_reachability_check(self, session: Session, *, persist: bool = False) -> PlatformLayerState:
        return PlatformLayerState(
            status="not_checked",
            label="Internal",
            evidence="System Alerts are internal and do not use a public website check.",
            next_action="Validate notification routing.",
        )


def platform_integration(platform: str) -> PlatformIntegration:
    definition = PLATFORM_DEFINITIONS[platform]
    if platform == "backup_storage":
        return BackupStorageIntegration(definition)
    if platform == "system_alerts":
        return InternalAlertIntegration(definition)
    return StaticPlatformIntegration(definition)


def platform_connections_status(session: Session) -> list[PlatformIntegrationStatus]:
    ensure_platform_connections(session)
    return [platform_integration(platform).status(session) for platform in PLATFORM_IDENTIFIERS]


def platform_connection_status(session: Session, platform: str) -> PlatformIntegrationStatus:
    if platform not in PLATFORM_DEFINITIONS:
        raise ValueError(f"Unsupported platform: {platform}")
    ensure_platform_connections(session)
    return platform_integration(platform).status(session)


def test_platform_website(session: Session, platform: str) -> PlatformLayerState:
    if platform not in PLATFORM_DEFINITIONS:
        raise ValueError(f"Unsupported platform: {platform}")
    return platform_integration(platform).website_reachability_check(session, persist=True)


def platform_connections_overview(session: Session) -> dict[str, object]:
    statuses = platform_connections_status(session)
    ready = sum(1 for item in statuses if item.readiness.status == "healthy")
    needs_attention = [item for item in statuses if item.readiness.status in {"needs_attention", "critical"}]
    waiting = [item for item in statuses if item.connection.status in {"ready_to_connect", "not_connected"}]
    next_action = (
        "Open Platform Connections and connect the first priority platform."
        if waiting
        else "Review notification routes."
        if needs_attention
        else "No action needed."
    )
    return {
        "total": len(statuses),
        "ready": ready,
        "waiting": len(waiting),
        "needs_attention": len(needs_attention),
        "next_action": next_action,
        "statuses": statuses,
    }
