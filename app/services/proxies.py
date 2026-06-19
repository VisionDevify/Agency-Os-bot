from dataclasses import dataclass
from datetime import UTC, datetime
import re
import secrets
import string

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.model_brand import ModelBrand
from app.models.proxy import PROXY_STATUSES, Proxy, ProxyHealthCheckResult, ProxyRotationHistory
from app.models.user import User
from app.services.auth import audit_action, is_owner, user_has_permission
from app.services.crypto import encrypt_secret
from app.services.events import emit_event
from app.services.incidents import normalize_severity
from app.services.proxy_adapters import ProxyAdapterResult, ProxyProviderAdapter, adapter_for_proxy
from app.services.recommendations import upsert_recommendation

PROXY_HEALTH_HEALTHY = "healthy"
PROXY_HEALTH_WARNING = "warning"
PROXY_HEALTH_CRITICAL = "critical"
PROXY_HEALTH_DISABLED = "disabled"


@dataclass(frozen=True)
class ProxyHealth:
    status: str
    label: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProxyTestResult:
    success: bool
    latency_ms: int | None = None
    detected_country: str | None = None
    detected_state: str | None = None
    detected_city: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class ProxyRepairResult:
    attempted: bool
    repaired: bool
    incident_created: bool
    message: str


@dataclass(frozen=True)
class SimulationSummary:
    would_rotate: int
    would_repair: int
    would_fail: int


@dataclass(frozen=True)
class InfrastructureStats:
    total_proxies: int
    healthy_proxies: int
    warning_proxies: int
    critical_proxies: int
    disabled_proxies: int
    accounts_assigned_proxy: int
    accounts_missing_proxy: int
    recent_rotations: tuple[str, ...]
    recent_failures: tuple[str, ...]
    recent_incidents: tuple[str, ...]
    average_health_score: int


@dataclass(frozen=True)
class ProxyCheckMode:
    real_health_enabled: bool
    real_location_enabled: bool
    timeout_seconds: int
    location_provider: str


@dataclass(frozen=True)
class ProxyRoutingCheckSummary:
    result: ProxyHealthCheckResult
    message: str


class ProxyStringParseError(ValueError):
    """Raised when an owner-pasted proxy string is not in the expected safe format."""


@dataclass(frozen=True)
class ParsedOlympixProxyString:
    host: str
    port: int
    full_username: str
    base_username: str
    session_suffix: str
    password: str


def _now() -> datetime:
    return datetime.now(UTC)


def _require_any_permission(session: Session, actor: User | None, *permissions: str) -> None:
    if any(user_has_permission(actor, permission) for permission in permissions):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="proxy",
        status="denied",
        details={"permissions": list(permissions)},
    )
    raise PermissionError(f"Missing permission: {' or '.join(permissions)}")


def normalize_session_suffix(session_suffix: str) -> str:
    clean = session_suffix.strip()
    if clean.casefold().startswith("session_"):
        return clean.split("_", 1)[1]
    return clean


def generate_session_suffix() -> str:
    return f"session_{secrets.token_hex(4)}"


def generate_olympix_session_suffix(length: int = 8) -> str:
    length = max(4, min(32, length))
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generated_username(base_username: str, session_suffix: str) -> str:
    if "," in base_username:
        return f"{base_username},session_{normalize_session_suffix(session_suffix)}"
    return f"{base_username}-{session_suffix}"


def mask_session_suffix(session_suffix: str | None) -> str:
    if not session_suffix:
        return "Not set"
    clean = normalize_session_suffix(session_suffix)
    return f"\u2022\u2022\u2022\u2022{clean[-4:]}" if len(clean) > 4 else f"\u2022\u2022\u2022\u2022{clean}"


def mask_proxy_username(username: str | None) -> str:
    if not username:
        return "Not set"
    first = username.split(",", 1)[0].strip()
    if "_" in first:
        return f"{first.split('_', 1)[0]}_\u2022\u2022\u2022\u2022\u2022\u2022"
    if len(first) <= 4:
        return f"{first[:1]}\u2022\u2022\u2022"
    return f"{first[:4]}\u2022\u2022\u2022\u2022"


def parse_olympix_proxy_string(proxy_string: str) -> ParsedOlympixProxyString:
    parts = [part.strip() for part in proxy_string.strip().split(":", 3)]
    if len(parts) != 4:
        raise ProxyStringParseError("Expected host:port:username:password")
    host, port_text, full_username, password = parts
    if not host or not port_text or not full_username or not password:
        raise ProxyStringParseError("Host, port, username, and password are required")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ProxyStringParseError("Port must be a number") from exc
    if port < 1 or port > 65535:
        raise ProxyStringParseError("Port must be between 1 and 65535")
    marker = ",session_"
    if marker not in full_username:
        raise ProxyStringParseError("Username must include ,session_")
    base_username, session_suffix = full_username.rsplit(marker, 1)
    session_suffix = normalize_session_suffix(session_suffix)
    if not base_username or not session_suffix:
        raise ProxyStringParseError("Username must include a base username and session suffix")
    if not re.fullmatch(r"[A-Za-z0-9]+", session_suffix):
        raise ProxyStringParseError("Session suffix must be alphanumeric")
    return ParsedOlympixProxyString(
        host=host,
        port=port,
        full_username=full_username,
        base_username=base_username,
        session_suffix=session_suffix,
        password=password,
    )


PLACEHOLDER_PROVIDERS = {"placeholder", "fake", "demo", "test"}
PLACEHOLDER_PORTS = set(range(8000, 8010))


def _safe_proxy_payload(proxy: Proxy, extra: dict | None = None) -> dict:
    payload = {
        "proxy_id": proxy.id,
        "provider": proxy.provider,
        "host": proxy.host,
        "port": proxy.port,
        "status": proxy.status,
        "health_score": proxy.health_score,
        "target_country": proxy.target_country,
        "target_state": proxy.target_state,
        "target_city": proxy.target_city,
        "detected_country": proxy.detected_country,
        "detected_state": proxy.detected_state,
        "detected_city": proxy.detected_city,
    }
    payload.update(extra or {})
    return payload


def is_archived_proxy(proxy: Proxy) -> bool:
    metadata = proxy.metadata_json or {}
    return bool(metadata.get("archived") or metadata.get("is_archived"))


def is_placeholder_proxy(proxy: Proxy) -> bool:
    metadata = proxy.metadata_json or {}
    provider = (proxy.provider or "").casefold()
    host = (proxy.host or "").casefold()
    name = (proxy.name or "").casefold()
    if metadata.get("is_demo") or metadata.get("is_placeholder") or metadata.get("placeholder"):
        return True
    if provider in PLACEHOLDER_PROVIDERS or any(marker in provider for marker in ("placeholder", "demo", "fake", "test")):
        return True
    if "placeholder" in host or host.endswith(".local"):
        return True
    if "placeholder" in name:
        return True
    if proxy.port in PLACEHOLDER_PORTS and (host.startswith("proxy-") or "placeholder" in name or provider in {"provider", "placeholder"}):
        return True
    required_values = (proxy.host, proxy.port, proxy.base_username, proxy.session_suffix, proxy.encrypted_password)
    if any(value in (None, "", 0) for value in required_values):
        return True
    return False


def is_real_proxy(proxy: Proxy) -> bool:
    return not is_archived_proxy(proxy) and not is_placeholder_proxy(proxy)


def _safe_rotation_payload(proxy: Proxy, extra: dict | None = None) -> dict:
    payload = _safe_proxy_payload(
        proxy,
        {
            "session_suffix_masked": mask_session_suffix(proxy.session_suffix),
            "previous_session_suffix_masked": mask_session_suffix(proxy.previous_session_suffix),
            "username_masked": mask_proxy_username(proxy.base_username),
        },
    )
    payload.update(extra or {})
    return payload


def _safe_check_error(message: str | None) -> str | None:
    if not message:
        return None
    lowered = message.casefold()
    if any(marker in lowered for marker in ("password", "credential", "secret", "token", "username", "chat_id")):
        return "proxy check failed; sensitive details redacted"
    return message[:500]


def proxy_check_mode(proxy: Proxy) -> ProxyCheckMode:
    metadata = dict(proxy.metadata_json or {})
    real_health = bool(settings.proxy_real_health_checks_enabled or metadata.get("real_health_checks_enabled"))
    real_location = bool(settings.proxy_real_location_checks_enabled or metadata.get("real_location_checks_enabled"))
    return ProxyCheckMode(
        real_health_enabled=real_health,
        real_location_enabled=real_location,
        timeout_seconds=max(1, int(settings.proxy_health_timeout_seconds or 10)),
        location_provider=settings.proxy_location_provider or "ipwhois",
    )


def set_proxy_real_check_flags(
    session: Session,
    proxy: Proxy,
    *,
    actor: User,
    health_enabled: bool,
    location_enabled: bool | None = None,
) -> Proxy:
    if not is_owner(actor):
        audit_action(
            session,
            actor=actor,
            action="access.denied",
            resource_type="proxy",
            resource_id=str(proxy.id),
            status="denied",
            details={"permission": "owner", "action": "proxy_real_checks"},
        )
        raise PermissionError("Only Owner can enable real proxy checks.")
    metadata = dict(proxy.metadata_json or {})
    metadata["real_health_checks_enabled"] = bool(health_enabled)
    if location_enabled is not None:
        metadata["real_location_checks_enabled"] = bool(location_enabled and health_enabled)
    elif not health_enabled:
        metadata["real_location_checks_enabled"] = False
    proxy.metadata_json = metadata
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="proxy.real_checks.updated",
        resource_type="proxy",
        resource_id=str(proxy.id),
        details={
            "real_health_checks_enabled": metadata["real_health_checks_enabled"],
            "real_location_checks_enabled": metadata["real_location_checks_enabled"],
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name="proxy.real_checks.updated",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload={
            "real_health_checks_enabled": metadata["real_health_checks_enabled"],
            "real_location_checks_enabled": metadata["real_location_checks_enabled"],
        },
    )
    return proxy


def calculate_proxy_health(proxy: Proxy) -> ProxyHealth:
    if proxy.status == "disabled":
        return ProxyHealth(PROXY_HEALTH_DISABLED, "\u26ab Disabled", 0, ("disabled",))

    score = 100
    reasons: list[str] = []
    if proxy.connection_test_count:
        failure_rate = proxy.failure_count / proxy.connection_test_count
        score -= int(failure_rate * 45)
        if failure_rate >= 0.5:
            reasons.append("high_failure_rate")
    if proxy.latency_ms is not None:
        if proxy.latency_ms > 3000:
            score -= 25
            reasons.append("high_latency")
        elif proxy.latency_ms > 1500:
            score -= 12
            reasons.append("elevated_latency")
    if proxy.location_mismatch_count:
        score -= min(proxy.location_mismatch_count, 4) * 10
        reasons.append("location_mismatch")
    total_rotations = proxy.rotation_success_count + proxy.rotation_failure_count
    if total_rotations:
        rotation_failure_rate = proxy.rotation_failure_count / total_rotations
        score -= int(rotation_failure_rate * 20)
        if rotation_failure_rate >= 0.5:
            reasons.append("rotation_failures")
    score = max(0, min(100, score))

    if score >= 80:
        status = PROXY_HEALTH_HEALTHY
        label = "\U0001f7e2 Healthy"
    elif score >= 50:
        status = PROXY_HEALTH_WARNING
        label = "\U0001f7e1 Warning"
    else:
        status = PROXY_HEALTH_CRITICAL
        label = "\U0001f534 Critical"
    return ProxyHealth(status, label, score, tuple(reasons))


def _sync_proxy_health(session: Session, proxy: Proxy, *, actor: User | None = None) -> ProxyHealth:
    old_status = proxy.status
    old_score = proxy.health_score
    health = calculate_proxy_health(proxy)
    proxy.health_score = health.score
    if proxy.status != "disabled":
        proxy.status = health.status
    if proxy.status != old_status or proxy.health_score != old_score:
        emit_event(
            session,
            actor=actor,
            event_name="proxy.health.changed",
            resource_type="proxy",
            resource_id=str(proxy.id),
            payload={
                "from_status": old_status,
                "to_status": proxy.status,
                "from_score": old_score,
                "to_score": proxy.health_score,
                "reasons": list(health.reasons),
            },
        )
    return health


def create_proxy(
    session: Session,
    *,
    actor: User,
    provider: str,
    host: str,
    port: int,
    base_username: str,
    password: str,
    session_suffix: str | None = None,
    proxy_type: str | None = None,
    target_country: str | None = None,
    target_state: str | None = None,
    target_city: str | None = None,
) -> Proxy:
    _require_any_permission(session, actor, "manage_proxies")
    if port < 0 or port > 65535:
        raise ValueError("Invalid proxy port")
    suffix = session_suffix.strip() if session_suffix else generate_session_suffix()
    metadata: dict[str, str] = {}
    if proxy_type:
        metadata["proxy_type"] = proxy_type
    proxy = Proxy(
        name=f"{provider} {host}:{port}",
        provider=provider.strip() or "unknown",
        host=host.strip(),
        port=port,
        base_username=base_username.strip(),
        session_suffix=suffix,
        encrypted_password=encrypt_secret(password),
        generated_username=generated_username(base_username.strip(), suffix),
        metadata_json=metadata,
        status="healthy",
        health_score=100,
        target_country=target_country,
        target_state=target_state,
        target_city=target_city,
    )
    session.add(proxy)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.created",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload=_safe_proxy_payload(proxy),
    )
    return proxy


def create_olympix_proxy_from_string(
    session: Session,
    *,
    actor: User,
    proxy_string: str,
    target_country: str | None = None,
    target_state: str | None = None,
    target_city: str | None = None,
) -> Proxy:
    parsed = parse_olympix_proxy_string(proxy_string)
    proxy = create_proxy(
        session,
        actor=actor,
        provider="Olympix",
        host=parsed.host,
        port=parsed.port,
        base_username=parsed.base_username,
        session_suffix=parsed.session_suffix,
        password=parsed.password,
        proxy_type="SOCKS5 Mobile",
        target_country=target_country,
        target_state=target_state,
        target_city=target_city,
    )
    audit_action(
        session,
        actor=actor,
        action="proxy.imported",
        resource_type="proxy",
        resource_id=str(proxy.id),
        details={
            "provider": "Olympix",
            "host": proxy.host,
            "port": proxy.port,
            "username_masked": mask_proxy_username(proxy.base_username),
            "session_suffix_masked": mask_session_suffix(proxy.session_suffix),
        },
    )
    return proxy


def create_default_proxy(session: Session, *, actor: User) -> Proxy:
    next_number = session.scalar(select(func.count(Proxy.id))) or 0
    proxy = create_proxy(
        session,
        actor=actor,
        provider="placeholder",
        host=f"proxy-{next_number + 1}.local",
        port=8000 + next_number,
        base_username=f"proxy_user_{next_number + 1}",
        password="placeholder-password",
        target_country="United States",
        target_state="Florida",
    )
    metadata = dict(proxy.metadata_json or {})
    metadata["is_placeholder"] = True
    metadata["archived"] = True
    proxy.metadata_json = metadata
    proxy.status = "disabled"
    session.flush()
    return proxy


def list_proxies(
    session: Session,
    *,
    include_disabled: bool = True,
    include_archived: bool = False,
    include_placeholders: bool = False,
) -> list[Proxy]:
    statement = select(Proxy).options(selectinload(Proxy.accounts)).order_by(Proxy.id)
    if not include_disabled:
        statement = statement.where(Proxy.status != "disabled")
    proxies = list(session.scalars(statement).all())
    if not include_archived:
        proxies = [proxy for proxy in proxies if not is_archived_proxy(proxy)]
    if not include_placeholders:
        proxies = [proxy for proxy in proxies if not is_placeholder_proxy(proxy)]
    return proxies


def list_placeholder_proxies(session: Session, *, include_archived: bool = True) -> list[Proxy]:
    statement = select(Proxy).options(selectinload(Proxy.accounts), selectinload(Proxy.rotation_history), selectinload(Proxy.health_check_results)).order_by(Proxy.id)
    proxies = [proxy for proxy in session.scalars(statement).all() if is_placeholder_proxy(proxy)]
    if not include_archived:
        proxies = [proxy for proxy in proxies if not is_archived_proxy(proxy)]
    return proxies


def get_proxy(session: Session, proxy_id: int) -> Proxy | None:
    return session.scalar(
        select(Proxy)
        .where(Proxy.id == proxy_id)
        .options(selectinload(Proxy.accounts).selectinload(Account.model_brand), selectinload(Proxy.rotation_history))
    )


def archive_proxy(session: Session, proxy: Proxy, *, actor: User, reason: str = "owner_requested") -> Proxy:
    _require_any_permission(session, actor, "manage_proxies")
    metadata = dict(proxy.metadata_json or {})
    metadata["archived"] = True
    metadata["archive_reason"] = reason
    metadata["archived_at"] = _now().isoformat()
    proxy.metadata_json = metadata
    proxy.status = "disabled"
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="proxy.archived",
        resource_type="proxy",
        resource_id=str(proxy.id),
        details={"provider": proxy.provider, "username_masked": mask_proxy_username(proxy.base_username), "reason": reason},
    )
    emit_event(
        session,
        actor=actor,
        event_name="proxy.archived",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload={"reason": reason, "provider": proxy.provider},
    )
    return proxy


def disable_proxy(session: Session, proxy: Proxy, *, actor: User) -> Proxy:
    _require_any_permission(session, actor, "manage_proxies")
    proxy.status = "disabled"
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="proxy.disabled",
        resource_type="proxy",
        resource_id=str(proxy.id),
        details={"provider": proxy.provider, "username_masked": mask_proxy_username(proxy.base_username)},
    )
    emit_event(
        session,
        actor=actor,
        event_name="proxy.disabled",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload={"provider": proxy.provider},
    )
    return proxy


def reactivate_proxy(session: Session, proxy: Proxy, *, actor: User) -> Proxy:
    _require_any_permission(session, actor, "manage_proxies")
    metadata = dict(proxy.metadata_json or {})
    metadata.pop("archived", None)
    metadata.pop("is_archived", None)
    proxy.metadata_json = metadata
    proxy.status = "warning"
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="proxy.reactivated",
        resource_type="proxy",
        resource_id=str(proxy.id),
        details={"provider": proxy.provider, "username_masked": mask_proxy_username(proxy.base_username)},
    )
    emit_event(
        session,
        actor=actor,
        event_name="proxy.reactivated",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload={"provider": proxy.provider},
    )
    return proxy


def delete_proxy(session: Session, proxy: Proxy, *, actor: User) -> None:
    _require_any_permission(session, actor, "manage_proxies")
    assigned_accounts = accounts_for_proxy(session, proxy)
    if assigned_accounts:
        raise ValueError("Proxy is assigned to an active account. Remove it from accounts before deleting.")
    proxy_id = proxy.id
    provider = proxy.provider
    username_masked = mask_proxy_username(proxy.base_username)
    audit_action(
        session,
        actor=actor,
        action="proxy.deleted",
        resource_type="proxy",
        resource_id=str(proxy_id),
        details={"provider": provider, "username_masked": username_masked},
    )
    emit_event(
        session,
        actor=actor,
        event_name="proxy.deleted",
        resource_type="proxy",
        resource_id=str(proxy_id),
        payload={"provider": provider},
    )
    session.delete(proxy)
    session.flush()


def cleanup_placeholder_proxies(session: Session, *, actor: User) -> dict[str, int]:
    _require_any_permission(session, actor, "manage_proxies")
    archived = 0
    deleted = 0
    hidden = 0
    for proxy in list_placeholder_proxies(session, include_archived=False):
        has_history = bool(proxy.accounts or proxy.rotation_history or proxy.health_check_results)
        if has_history:
            archive_proxy(session, proxy, actor=actor, reason="placeholder_cleanup")
            archived += 1
            audit_action(
                session,
                actor=actor,
                action="proxy.placeholder.archived",
                resource_type="proxy",
                resource_id=str(proxy.id),
                details={"provider": proxy.provider, "host_masked": "hidden"},
            )
        else:
            proxy_id = proxy.id
            audit_action(
                session,
                actor=actor,
                action="proxy.placeholder.removed",
                resource_type="proxy",
                resource_id=str(proxy_id),
                details={"provider": proxy.provider, "host_masked": "hidden"},
            )
            session.delete(proxy)
            deleted += 1
        hidden += 1
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.placeholder.hidden",
        resource_type="proxy",
        payload={"archived": archived, "deleted": deleted, "hidden": hidden},
    )
    return {"archived": archived, "deleted": deleted, "hidden": hidden}


def update_proxy_location_target(
    session: Session,
    proxy: Proxy,
    *,
    actor: User,
    target_country: str | None = None,
    target_state: str | None = None,
    target_city: str | None = None,
) -> Proxy:
    _require_any_permission(session, actor, "manage_proxies")
    proxy.target_country = target_country
    proxy.target_state = target_state
    proxy.target_city = target_city
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.updated",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload=_safe_proxy_payload(proxy),
    )
    return proxy


def accounts_for_proxy(session: Session, proxy: Proxy) -> list[Account]:
    return list(
        session.scalars(
            select(Account)
            .where(Account.assigned_proxy_id == proxy.id, Account.status != "archived")
            .options(selectinload(Account.model_brand), selectinload(Account.assigned_proxy))
            .order_by(Account.id)
        ).all()
    )


def accounts_missing_proxy(session: Session) -> list[Account]:
    return list(
        session.scalars(
            select(Account)
            .where(Account.assigned_proxy_id.is_(None), Account.status != "archived")
            .options(selectinload(Account.model_brand))
            .order_by(Account.id)
        ).all()
    )


def affected_models_for_proxy(session: Session, proxy: Proxy) -> list[ModelBrand]:
    model_ids = {
        account.model_brand_id
        for account in accounts_for_proxy(session, proxy)
        if account.model_brand_id is not None
    }
    if not model_ids:
        return []
    return list(session.scalars(select(ModelBrand).where(ModelBrand.id.in_(model_ids)).order_by(ModelBrand.id)).all())


def assign_proxy_to_account(session: Session, proxy: Proxy, account: Account, *, actor: User) -> None:
    _require_any_permission(session, actor, "manage_proxies", "manage_accounts")
    account.assigned_proxy_id = proxy.id
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.assigned",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload=_safe_proxy_payload(
            proxy,
            {"account_id": account.id, "model_brand_id": account.model_brand_id},
        ),
    )
    from app.services.autonomous_operations import run_account_autopilot
    from app.services.learning import capture_proxy_outcome

    run_account_autopilot(session, account, actor=actor)
    run_simulated_proxy_check(session, proxy, actor=actor)
    capture_proxy_outcome(
        session,
        proxy,
        actor=actor,
        event_type="proxy.assigned",
        succeeded=True,
        details={"account_id": account.id},
    )


def remove_proxy_from_account(session: Session, account: Account, *, actor: User) -> None:
    _require_any_permission(session, actor, "manage_proxies", "manage_accounts")
    previous_proxy_id = account.assigned_proxy_id
    account.assigned_proxy_id = None
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.unassigned",
        resource_type="proxy",
        resource_id=str(previous_proxy_id) if previous_proxy_id else None,
        payload={"account_id": account.id, "model_brand_id": account.model_brand_id},
    )


def _location_matches(proxy: Proxy) -> bool:
    comparisons = [
        (proxy.target_country, proxy.detected_country),
        (proxy.target_state, proxy.detected_state),
        (proxy.target_city, proxy.detected_city),
    ]
    for expected, detected in comparisons:
        if expected and (detected or "").casefold() != expected.casefold():
            return False
    return True


def record_proxy_test(
    session: Session,
    proxy: Proxy,
    result: ProxyTestResult,
    *,
    actor: User | None = None,
) -> bool:
    proxy.connection_test_count += 1
    proxy.last_health_check = _now()
    proxy.latency_ms = result.latency_ms
    if result.detected_country is not None:
        proxy.detected_country = result.detected_country
    if result.detected_state is not None:
        proxy.detected_state = result.detected_state
    if result.detected_city is not None:
        proxy.detected_city = result.detected_city
    if result.success:
        proxy.success_count += 1
    else:
        proxy.failure_count += 1
    location_match = _location_matches(proxy)
    if result.success and not location_match:
        proxy.location_mismatch_count += 1
        emit_event(
            session,
            actor=actor,
            event_name="proxy.location.mismatch",
            resource_type="proxy",
            resource_id=str(proxy.id),
            status="warning",
            payload=_safe_proxy_payload(proxy),
        )
    _sync_proxy_health(session, proxy, actor=actor)
    session.flush()
    return result.success and location_match


def _target_match_for_values(
    proxy: Proxy,
    *,
    detected_country: str | None,
    detected_state: str | None,
    detected_city: str | None,
) -> bool | None:
    checks = [
        (proxy.target_country, detected_country),
        (proxy.target_state, detected_state),
        (proxy.target_city, detected_city),
    ]
    checked = False
    for expected, detected in checks:
        if expected:
            checked = True
            if (detected or "").casefold() != expected.casefold():
                return False
    return True if checked else None


def record_proxy_health_check_result(
    session: Session,
    proxy: Proxy,
    *,
    actor: User | None,
    check_type: str,
    status: str,
    latency_ms: int | None = None,
    detected_ip_masked: str | None = None,
    detected_country: str | None = None,
    detected_state: str | None = None,
    detected_city: str | None = None,
    target_match: bool | None = None,
    error_message: str | None = None,
) -> ProxyHealthCheckResult:
    result = ProxyHealthCheckResult(
        proxy_id=proxy.id,
        check_type=check_type,
        status=status,
        latency_ms=latency_ms,
        detected_ip_masked=detected_ip_masked,
        detected_country=detected_country,
        detected_state=detected_state,
        detected_city=detected_city,
        target_match=target_match,
        error_message=_safe_check_error(error_message),
    )
    session.add(result)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="proxy.health_check.performed",
        resource_type="proxy",
        resource_id=str(proxy.id),
        status=status,
        details={
            "check_type": check_type,
            "status": status,
            "latency_ms": latency_ms,
            "target_match": target_match,
            "has_detected_ip": bool(detected_ip_masked),
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name=f"proxy.health_check.{status}",
        resource_type="proxy",
        resource_id=str(proxy.id),
        status=status,
        payload={
            "check_type": check_type,
            "latency_ms": latency_ms,
            "target_match": target_match,
            "result_id": result.id,
        },
    )
    return result


def latest_proxy_health_check_results(
    session: Session,
    proxy: Proxy,
    *,
    limit: int = 5,
) -> list[ProxyHealthCheckResult]:
    return list(
        session.scalars(
            select(ProxyHealthCheckResult)
            .where(ProxyHealthCheckResult.proxy_id == proxy.id)
            .order_by(desc(ProxyHealthCheckResult.created_at), desc(ProxyHealthCheckResult.id))
            .limit(limit)
        ).all()
    )


def _record_proxy_check_learning(
    session: Session,
    proxy: Proxy,
    *,
    actor: User | None,
    result: ProxyHealthCheckResult,
) -> None:
    if result.status == "skipped":
        return
    succeeded = result.status == "passed"
    from app.services.learning import capture_proxy_outcome

    capture_proxy_outcome(
        session,
        proxy,
        actor=actor,
        event_type=f"proxy.health_check.{result.status}",
        succeeded=succeeded,
        summary=f"Proxy {result.check_type} check {result.status}.",
        details={
            "health_check_result_id": result.id,
            "check_type": result.check_type,
            "latency_ms": result.latency_ms,
            "target_match": result.target_match,
        },
    )
    if succeeded:
        return
    upsert_recommendation(
        session,
        actor=actor,
        recommendation_type="proxy_real_check_failed",
        title="Proxy Health Check Failed",
        description=f"Proxy {proxy.id} failed a {result.check_type} check. Review the proxy or rotate the session.",
        severity="warning" if result.status == "warning" else "critical",
        entity_type="proxy",
        entity_id=proxy.id,
        metadata={"check_type": result.check_type, "result_id": result.id},
    )
    try:
        from app.services.coo import _upsert_priority

        _upsert_priority(
            session,
            source_type="proxy",
            source_id=proxy.id,
            category="proxy_health_failure",
            severity="warning" if result.status == "warning" else "critical",
            urgency="high",
            confidence=80,
            business_impact=70,
            explanation=f"Proxy {proxy.id} failed its latest {result.check_type} check.",
            recommended_owner="Admin",
        )
    except Exception:
        # Priority creation is useful but should never block the health check path.
        pass


def run_simulated_proxy_check(session: Session, proxy: Proxy, *, actor: User | None) -> ProxyHealthCheckResult:
    test_result = ProxyTestResult(
        success=True,
        latency_ms=proxy.latency_ms or 250,
        detected_country=proxy.target_country,
        detected_state=proxy.target_state,
        detected_city=proxy.target_city,
    )
    matched = record_proxy_test(session, proxy, test_result, actor=actor)
    result = record_proxy_health_check_result(
        session,
        proxy,
        actor=actor,
        check_type="simulated",
        status="passed" if matched else "warning",
        latency_ms=test_result.latency_ms,
        detected_country=test_result.detected_country,
        detected_state=test_result.detected_state,
        detected_city=test_result.detected_city,
        target_match=matched,
    )
    _record_proxy_check_learning(session, proxy, actor=actor, result=result)
    return result


def run_real_proxy_check(
    session: Session,
    proxy: Proxy,
    *,
    actor: User,
    adapter: ProxyProviderAdapter | None = None,
) -> ProxyHealthCheckResult:
    _require_any_permission(session, actor, "manage_proxies", "rotate_proxy")
    mode = proxy_check_mode(proxy)
    if not mode.real_health_enabled:
        return record_proxy_health_check_result(
            session,
            proxy,
            actor=actor,
            check_type="connectivity",
            status="skipped",
            error_message="real checks disabled by owner",
        )
    provider = adapter or adapter_for_proxy(proxy)
    adapter_result: ProxyAdapterResult = provider.check(
        proxy,
        include_location=mode.real_location_enabled,
        timeout_seconds=mode.timeout_seconds,
    )
    target_match = _target_match_for_values(
        proxy,
        detected_country=adapter_result.detected_country,
        detected_state=adapter_result.detected_state,
        detected_city=adapter_result.detected_city,
    )
    check_type = "full" if mode.real_location_enabled else "connectivity"
    if not adapter_result.success:
        status = "failed"
    elif mode.real_location_enabled and target_match is False:
        status = "warning"
    elif mode.real_location_enabled and adapter_result.detected_country is None:
        status = "warning"
    else:
        status = "passed"

    if status != "skipped":
        record_proxy_test(
            session,
            proxy,
            ProxyTestResult(
                success=adapter_result.success,
                latency_ms=adapter_result.latency_ms,
                detected_country=adapter_result.detected_country,
                detected_state=adapter_result.detected_state,
                detected_city=adapter_result.detected_city,
                failure_reason=adapter_result.failure_reason,
            ),
            actor=actor,
        )
    result = record_proxy_health_check_result(
        session,
        proxy,
        actor=actor,
        check_type=check_type,
        status=status,
        latency_ms=adapter_result.latency_ms,
        detected_ip_masked=adapter_result.detected_ip_masked,
        detected_country=adapter_result.detected_country,
        detected_state=adapter_result.detected_state,
        detected_city=adapter_result.detected_city,
        target_match=target_match,
        error_message=adapter_result.failure_reason,
    )
    _record_proxy_check_learning(session, proxy, actor=actor, result=result)
    return result


def rotate_session(
    session: Session,
    proxy: Proxy,
    *,
    actor: User,
    test_result: ProxyTestResult | None = None,
    new_suffix: str | None = None,
) -> ProxyRotationHistory:
    _require_any_permission(session, actor, "manage_proxies", "rotate_proxy")
    previous = proxy.session_suffix
    suffix = new_suffix or generate_session_suffix()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.rotation.started",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload={
            "previous_session_suffix_masked": mask_session_suffix(previous),
            "new_session_suffix_masked": mask_session_suffix(suffix),
        },
    )
    proxy.previous_session_suffix = previous
    proxy.session_suffix = suffix
    proxy.generated_username = generated_username(proxy.base_username, suffix)
    proxy.rotation_count += 1
    proxy.last_rotation = _now()
    result = test_result or ProxyTestResult(
        success=True,
        latency_ms=250,
        detected_country=proxy.target_country,
        detected_state=proxy.target_state,
        detected_city=proxy.target_city,
    )
    if result.detected_country is not None:
        proxy.detected_country = result.detected_country
    if result.detected_state is not None:
        proxy.detected_state = result.detected_state
    if result.detected_city is not None:
        proxy.detected_city = result.detected_city
    proxy.latency_ms = result.latency_ms

    location_match = _location_matches(proxy)
    success = result.success and location_match
    if success:
        status = "succeeded"
        proxy.rotation_success_count += 1
        proxy.last_successful_rotation = proxy.last_rotation
        event_name = "proxy.rotation.succeeded"
        event_status = "success"
    else:
        status = "failed"
        proxy.rotation_failure_count += 1
        event_name = "proxy.rotation.failed"
        event_status = "failed"
        if result.success and not location_match:
            proxy.location_mismatch_count += 1
            emit_event(
                session,
                actor=actor,
                event_name="proxy.location.mismatch",
                resource_type="proxy",
                resource_id=str(proxy.id),
                status="warning",
                payload=_safe_proxy_payload(proxy),
            )
    history = ProxyRotationHistory(
        proxy_id=proxy.id,
        previous_session_suffix=previous,
        new_session_suffix=suffix,
        status=status,
        detected_country=proxy.detected_country,
        detected_state=proxy.detected_state,
        detected_city=proxy.detected_city,
        latency_ms=result.latency_ms,
        failure_reason=None if success else (result.failure_reason or "location_mismatch"),
        created_by_user_id=actor.id,
    )
    session.add(history)
    _sync_proxy_health(session, proxy, actor=actor)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=event_name,
        resource_type="proxy",
        resource_id=str(proxy.id),
        status=event_status,
        payload=_safe_rotation_payload(proxy, {"rotation_history_id": history.id}),
    )
    from app.services.learning import capture_proxy_outcome

    capture_proxy_outcome(
        session,
        proxy,
        actor=actor,
        event_type=event_name,
        succeeded=success,
        details={"rotation_history_id": history.id},
    )
    return history


def rotate_olympix_session(session: Session, proxy: Proxy, *, actor: User) -> ProxyRotationHistory:
    current = normalize_session_suffix(proxy.session_suffix)
    if "olympix" not in proxy.provider.casefold() and "," not in proxy.base_username:
        return rotate_session(session, proxy, actor=actor)
    length = len(current) if current else 8
    new_suffix = generate_olympix_session_suffix(length)
    for _ in range(5):
        if new_suffix != current:
            break
        new_suffix = generate_olympix_session_suffix(length)
    return rotate_session(session, proxy, actor=actor, new_suffix=new_suffix)


def rollback_session(session: Session, proxy: Proxy, *, actor: User) -> ProxyRotationHistory:
    _require_any_permission(session, actor, "manage_proxies", "rotate_proxy")
    if not proxy.previous_session_suffix:
        raise ValueError("No previous session available")
    current = proxy.session_suffix
    previous = proxy.previous_session_suffix
    proxy.session_suffix = previous
    proxy.previous_session_suffix = current
    proxy.generated_username = generated_username(proxy.base_username, proxy.session_suffix)
    proxy.last_rotation = _now()
    audit_action(
        session,
        actor=actor,
        action="proxy.rotation.rollback_started",
        resource_type="proxy",
        resource_id=str(proxy.id),
        details={
            "current_session_suffix_masked": mask_session_suffix(current),
            "rollback_session_suffix_masked": mask_session_suffix(previous),
        },
    )
    history = ProxyRotationHistory(
        proxy_id=proxy.id,
        previous_session_suffix=current,
        new_session_suffix=previous,
        status="rolled_back",
        detected_country=proxy.detected_country,
        detected_state=proxy.detected_state,
        detected_city=proxy.detected_city,
        latency_ms=proxy.latency_ms,
        created_by_user_id=actor.id,
    )
    session.add(history)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.rotation.rolled_back",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload=_safe_rotation_payload(proxy, {"rollback": True, "rotation_history_id": history.id}),
    )
    return history


def verify_location_with_rotation(
    session: Session,
    proxy: Proxy,
    *,
    actor: User,
    attempts: list[ProxyTestResult],
    max_attempts: int = 3,
) -> bool:
    _require_any_permission(session, actor, "manage_proxies", "rotate_proxy")
    for result in attempts[:max_attempts]:
        history = rotate_session(session, proxy, actor=actor, test_result=result)
        if history.status == "succeeded":
            return True
    create_proxy_incident(
        session,
        proxy,
        actor=actor,
        title="Proxy location mismatch",
        severity="warning",
        reason="location_mismatch",
    )
    return False


def create_proxy_incident(
    session: Session,
    proxy: Proxy,
    *,
    actor: User | None,
    title: str,
    severity: str,
    reason: str,
) -> Incident:
    incident = Incident(
        name=title,
        title=title,
        description=f"Proxy event: {reason}",
        status="open",
        severity=normalize_severity(severity),
        source_type="proxy",
        source_id=str(proxy.id),
        proxy_id=proxy.id,
        created_by_user_id=actor.id if actor else None,
        metadata_json={"reason": reason, "proxy_id": proxy.id},
    )
    session.add(incident)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="proxy.incident.created",
        resource_type="proxy",
        resource_id=str(proxy.id),
        status="open",
        payload={"incident_id": incident.id, "severity": incident.severity, "reason": reason},
    )
    return incident


def close_proxy_incidents(session: Session, proxy: Proxy, *, actor: User | None, notes: str) -> int:
    incidents = list(
        session.scalars(
            select(Incident).where(
                Incident.source_type == "proxy",
                Incident.source_id == str(proxy.id),
                Incident.status.in_(("open", "investigating")),
            )
        ).all()
    )
    for incident in incidents:
        incident.status = "resolved"
        incident.resolution_notes = notes
        incident.resolved_by_user_id = actor.id if actor else None
        incident.resolved_at = _now()
    if incidents:
        session.flush()
    return len(incidents)


def repair_proxy(
    session: Session,
    proxy: Proxy,
    *,
    actor: User | None,
    initial_result: ProxyTestResult,
    repair_result: ProxyTestResult,
) -> ProxyRepairResult:
    if actor is not None:
        _require_any_permission(session, actor, "manage_proxies", "rotate_proxy")
    if record_proxy_test(session, proxy, initial_result, actor=actor):
        return ProxyRepairResult(False, True, False, "Proxy is already healthy.")

    repair_actor = actor
    if repair_actor is None:
        rotation_actor = None
    else:
        rotation_actor = repair_actor
    if rotation_actor is None:
        proxy.previous_session_suffix = proxy.session_suffix
        proxy.session_suffix = generate_session_suffix()
        proxy.generated_username = generated_username(proxy.base_username, proxy.session_suffix)
        proxy.rotation_count += 1
        proxy.last_rotation = _now()
        history_status = "succeeded" if repair_result.success else "failed"
        session.add(
            ProxyRotationHistory(
                proxy_id=proxy.id,
                previous_session_suffix=proxy.previous_session_suffix,
                new_session_suffix=proxy.session_suffix,
                status=history_status,
                failure_reason=None if repair_result.success else repair_result.failure_reason or "repair_failed",
            )
        )
    else:
        rotate_session(session, proxy, actor=rotation_actor, test_result=repair_result)

    if record_proxy_test(session, proxy, repair_result, actor=actor):
        closed = close_proxy_incidents(session, proxy, actor=actor, notes="Proxy repaired by session rotation.")
        emit_event(
            session,
            actor=actor,
            event_name="proxy.repair.succeeded",
            resource_type="proxy",
            resource_id=str(proxy.id),
            payload={"closed_incidents": closed},
        )
        from app.services.learning import capture_proxy_outcome

        capture_proxy_outcome(
            session,
            proxy,
            actor=actor,
            event_type="proxy.repair.succeeded",
            succeeded=True,
            summary="Proxy repair succeeded through session rotation.",
            details={"closed_incidents": closed},
        )
        return ProxyRepairResult(True, True, False, "Proxy repaired by rotating the session.")

    incident = create_proxy_incident(
        session,
        proxy,
        actor=actor,
        title="Proxy offline after repair attempt",
        severity="critical",
        reason="repair_failed",
    )
    emit_event(
        session,
        actor=actor,
        event_name="proxy.repair.failed",
        resource_type="proxy",
        resource_id=str(proxy.id),
        status="failed",
        payload={"incident_id": incident.id},
    )
    from app.services.learning import capture_proxy_outcome

    capture_proxy_outcome(
        session,
        proxy,
        actor=actor,
        event_type="proxy.repair.failed",
        succeeded=False,
        summary="Proxy repair failed and created an incident.",
        details={"incident_id": incident.id},
    )
    return ProxyRepairResult(True, False, True, "Proxy repair failed and an incident was created.")


def simulation_mode_summary(session: Session) -> SimulationSummary:
    proxies = list_proxies(session)
    candidates = [proxy for proxy in proxies if proxy.status in {"warning", "critical"} or proxy.health_score < 70]
    likely_failures = [
        proxy
        for proxy in candidates
        if proxy.status == "critical" or proxy.failure_count > proxy.success_count
    ]
    return SimulationSummary(
        would_rotate=len(candidates),
        would_repair=len(candidates),
        would_fail=len(likely_failures),
    )


def recent_proxy_audit_logs(session: Session, proxy: Proxy, *, limit: int = 10) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_type == "proxy", AuditLog.resource_id == str(proxy.id))
            .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
            .limit(limit)
        ).all()
    )


def infrastructure_stats(session: Session) -> InfrastructureStats:
    proxies = list_proxies(session)
    accounts = list(session.scalars(select(Account).where(Account.status != "archived")).all())
    incidents = list(
        session.scalars(
            select(Incident)
            .where(Incident.source_type == "proxy")
            .order_by(desc(Incident.created_at), desc(Incident.id))
            .limit(5)
        ).all()
    )
    rotations = list(
        session.scalars(
            select(ProxyRotationHistory).order_by(desc(ProxyRotationHistory.created_at), desc(ProxyRotationHistory.id)).limit(5)
        ).all()
    )
    failures = [rotation for rotation in rotations if rotation.status == "failed"]
    total_score = sum(proxy.health_score for proxy in proxies)
    return InfrastructureStats(
        total_proxies=len(proxies),
        healthy_proxies=sum(1 for proxy in proxies if proxy.status == "healthy"),
        warning_proxies=sum(1 for proxy in proxies if proxy.status == "warning"),
        critical_proxies=sum(1 for proxy in proxies if proxy.status == "critical"),
        disabled_proxies=sum(1 for proxy in proxies if proxy.status == "disabled"),
        accounts_assigned_proxy=sum(1 for account in accounts if account.assigned_proxy_id is not None),
        accounts_missing_proxy=sum(1 for account in accounts if account.assigned_proxy_id is None),
        recent_rotations=tuple(f"Proxy {rotation.proxy_id}: {rotation.status}" for rotation in rotations),
        recent_failures=tuple(f"Proxy {rotation.proxy_id}: {rotation.failure_reason or 'rotation failed'}" for rotation in failures),
        recent_incidents=tuple(f"{incident.severity}: {incident.title}" for incident in incidents),
        average_health_score=round(total_score / len(proxies)) if proxies else 0,
    )


def rotation_status() -> dict[str, str]:
    return {
        "status": "ready",
        "message": "Proxy session rotation is available through simulation-safe service workflows.",
    }
