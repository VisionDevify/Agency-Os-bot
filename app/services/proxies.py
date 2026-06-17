from dataclasses import dataclass
from datetime import UTC, datetime
import secrets

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.model_brand import ModelBrand
from app.models.proxy import PROXY_STATUSES, Proxy, ProxyRotationHistory
from app.models.user import User
from app.services.auth import audit_action, user_has_permission
from app.services.crypto import encrypt_secret
from app.services.events import emit_event
from app.services.incidents import normalize_severity

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


def generate_session_suffix() -> str:
    return f"session_{secrets.token_hex(4)}"


def generated_username(base_username: str, session_suffix: str) -> str:
    return f"{base_username}-{session_suffix}"


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
    target_country: str | None = None,
    target_state: str | None = None,
    target_city: str | None = None,
) -> Proxy:
    _require_any_permission(session, actor, "manage_proxies")
    if port < 0 or port > 65535:
        raise ValueError("Invalid proxy port")
    suffix = generate_session_suffix()
    proxy = Proxy(
        name=f"{provider} {host}:{port}",
        provider=provider.strip() or "unknown",
        host=host.strip(),
        port=port,
        base_username=base_username.strip(),
        session_suffix=suffix,
        encrypted_password=encrypt_secret(password),
        generated_username=generated_username(base_username.strip(), suffix),
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


def create_default_proxy(session: Session, *, actor: User) -> Proxy:
    next_number = session.scalar(select(func.count(Proxy.id))) or 0
    return create_proxy(
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


def list_proxies(session: Session, *, include_disabled: bool = True) -> list[Proxy]:
    statement = select(Proxy).options(selectinload(Proxy.accounts)).order_by(Proxy.id)
    if not include_disabled:
        statement = statement.where(Proxy.status != "disabled")
    return list(session.scalars(statement).all())


def get_proxy(session: Session, proxy_id: int) -> Proxy | None:
    return session.scalar(
        select(Proxy)
        .where(Proxy.id == proxy_id)
        .options(selectinload(Proxy.accounts).selectinload(Account.model_brand), selectinload(Proxy.rotation_history))
    )


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
        payload={"previous_session_suffix": previous, "new_session_suffix": suffix},
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
        payload=_safe_proxy_payload(proxy, {"rotation_history_id": history.id}),
    )
    return history


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
        event_name="proxy.rotation.succeeded",
        resource_type="proxy",
        resource_id=str(proxy.id),
        payload=_safe_proxy_payload(proxy, {"rollback": True, "rotation_history_id": history.id}),
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
