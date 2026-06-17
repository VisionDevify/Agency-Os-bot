from datetime import UTC, datetime, timedelta
import hashlib
import hmac

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.account import (
    ACCOUNT_AUTH_STATUSES,
    ACCOUNT_CODE_TYPES,
    ACCOUNT_PLATFORMS,
    ACCOUNT_STATUSES,
    Account,
    AccountAuthSession,
    AccountVerificationCode,
)
from app.models.audit import AuditLog
from app.models.model_brand import ModelBrand
from app.models.user import User
from app.services.account_health import calculate_account_health
from app.services.auth import audit_action, is_owner, user_has_permission
from app.services.events import emit_event
from app.services.permissions import RoleName

AUTH_SESSION_TTL = timedelta(minutes=10)
VERIFICATION_CODE_TTL = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


def _is_owner_or_admin(user: User | None) -> bool:
    if user is None:
        return False
    return is_owner(user) or any(role.name == RoleName.ADMIN.value for role in user.roles)


def _require_manage_accounts(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_accounts"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="account",
        status="denied",
        details={"permission": "manage_accounts"},
    )
    raise PermissionError("Missing permission: manage_accounts")


def _require_sensitive_auth_permission(session: Session, actor: User | None) -> None:
    has_permission = user_has_permission(actor, "manage_accounts") or user_has_permission(actor, "view_credentials")
    if has_permission and _is_owner_or_admin(actor):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="account_auth_session",
        status="denied",
        details={"permission": "owner_or_admin_with_manage_accounts_or_view_credentials"},
    )
    raise PermissionError("Only Owner/Admin can handle account auth sessions")


def require_account_auth_permission(session: Session, actor: User | None) -> None:
    _require_sensitive_auth_permission(session, actor)


def _account_payload(account: Account, extra: dict | None = None) -> dict:
    payload = {
        "account_id": account.id,
        "model_brand_id": account.model_brand_id,
        "platform": account.platform,
        "username": account.username,
        "status": account.status,
        "auth_status": account.auth_status,
    }
    payload.update(extra or {})
    return payload


def hash_verification_code(auth_session_id: int, code: str) -> str:
    secret = settings.app_secret_key.get_secret_value() or "agency-os-local-test-secret"
    material = f"{auth_session_id}:{code.strip()}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


def list_accounts(session: Session, *, include_archived: bool = False) -> list[Account]:
    statement = (
        select(Account)
        .options(selectinload(Account.model_brand))
        .order_by(Account.id)
    )
    if not include_archived:
        statement = statement.where(Account.status != "archived")
    return list(session.scalars(statement).all())


def get_account(session: Session, account_id: int) -> Account | None:
    return session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .options(selectinload(Account.model_brand), selectinload(Account.auth_sessions))
    )


def create_account(
    session: Session,
    *,
    model_brand: ModelBrand | None,
    platform: str,
    username: str,
    actor: User,
    display_name: str | None = None,
    account_url: str | None = None,
    notes: str | None = None,
) -> Account:
    _require_manage_accounts(session, actor)
    if platform not in ACCOUNT_PLATFORMS:
        raise ValueError(f"Invalid platform: {platform}")
    clean_username = username.strip()
    if not clean_username:
        raise ValueError("Username is required")
    account = Account(
        model_brand_id=model_brand.id if model_brand else None,
        platform=platform,
        username=clean_username,
        display_name=(display_name or clean_username).strip(),
        account_url=account_url,
        status="healthy",
        auth_status="not_connected",
        notes=notes,
    )
    session.add(account)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="account.created",
        resource_type="account",
        resource_id=str(account.id),
        payload=_account_payload(account),
    )
    return account


def create_default_account(
    session: Session,
    *,
    model_brand: ModelBrand | None,
    platform: str,
    actor: User,
) -> Account:
    next_number = session.scalar(select(func.count(Account.id))) or 0
    return create_account(
        session,
        model_brand=model_brand,
        platform=platform,
        username=f"{platform}_account_{next_number + 1}",
        display_name=f"{platform.title()} Account {next_number + 1}",
        notes="Created from Telegram. TODO: replace placeholder username/display name.",
        actor=actor,
    )


def update_account(
    session: Session,
    account: Account,
    *,
    actor: User,
    status: str | None = None,
    auth_status: str | None = None,
    notes: str | None = None,
) -> Account:
    _require_manage_accounts(session, actor)
    old_auth_status = account.auth_status
    if status is not None:
        if status not in ACCOUNT_STATUSES:
            raise ValueError(f"Invalid account status: {status}")
        account.status = status
    if auth_status is not None:
        if auth_status not in ACCOUNT_AUTH_STATUSES:
            raise ValueError(f"Invalid account auth status: {auth_status}")
        account.auth_status = auth_status
    if notes is not None:
        account.notes = notes
    session.flush()
    event_name = "account.disabled" if status == "disabled" else "account.updated"
    emit_event(
        session,
        actor=actor,
        event_name=event_name,
        resource_type="account",
        resource_id=str(account.id),
        payload=_account_payload(account),
    )
    if auth_status is not None and auth_status != old_auth_status:
        emit_event(
            session,
            actor=actor,
            event_name="account.auth_status.changed",
            resource_type="account",
            resource_id=str(account.id),
            payload={"from": old_auth_status, "to": auth_status},
        )
    return account


def archive_account(session: Session, account: Account, *, actor: User) -> Account:
    _require_manage_accounts(session, actor)
    account.status = "archived"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="account.archived",
        resource_type="account",
        resource_id=str(account.id),
        payload=_account_payload(account),
    )
    return account


def start_auth_session(
    session: Session,
    account: Account,
    *,
    actor: User,
    now: datetime | None = None,
) -> AccountAuthSession:
    _require_sensitive_auth_permission(session, actor)
    current_time = now or _now()
    auth_session = AccountAuthSession(
        account_id=account.id,
        status="waiting_for_code",
        requested_by_user_id=actor.id,
        handled_by_user_id=actor.id,
        expires_at=current_time + AUTH_SESSION_TTL,
    )
    old_auth_status = account.auth_status
    account.auth_status = "needs_2fa"
    session.add(auth_session)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="account.auth_session.started",
        resource_type="account",
        resource_id=str(account.id),
        payload={"auth_session_id": auth_session.id, "status": auth_session.status},
    )
    emit_event(
        session,
        actor=actor,
        event_name="account.auth_session.waiting_for_code",
        resource_type="account",
        resource_id=str(account.id),
        payload={"auth_session_id": auth_session.id},
    )
    if old_auth_status != account.auth_status:
        emit_event(
            session,
            actor=actor,
            event_name="account.auth_status.changed",
            resource_type="account",
            resource_id=str(account.id),
            payload={"from": old_auth_status, "to": account.auth_status},
        )
    return auth_session


def latest_waiting_auth_session(session: Session, account_id: int) -> AccountAuthSession | None:
    return session.scalar(
        select(AccountAuthSession)
        .where(
            AccountAuthSession.account_id == account_id,
            AccountAuthSession.status == "waiting_for_code",
        )
        .order_by(AccountAuthSession.created_at.desc(), AccountAuthSession.id.desc())
        .limit(1)
    )


def latest_auth_session(session: Session, account_id: int) -> AccountAuthSession | None:
    return session.scalar(
        select(AccountAuthSession)
        .where(AccountAuthSession.account_id == account_id)
        .order_by(AccountAuthSession.created_at.desc(), AccountAuthSession.id.desc())
        .limit(1)
    )


def submit_verification_code(
    session: Session,
    auth_session: AccountAuthSession,
    *,
    code: str,
    code_type: str,
    actor: User,
    now: datetime | None = None,
) -> AccountVerificationCode:
    _require_sensitive_auth_permission(session, actor)
    if code_type not in ACCOUNT_CODE_TYPES:
        raise ValueError(f"Invalid code type: {code_type}")
    current_time = now or _now()
    if auth_session.status != "waiting_for_code" or auth_session.expires_at <= current_time:
        expire_auth_sessions(session, now=current_time)
        raise PermissionError("Auth session is not accepting codes")
    verification = AccountVerificationCode(
        auth_session_id=auth_session.id,
        code_hash=hash_verification_code(auth_session.id, code),
        code_type=code_type,
        submitted_by_user_id=actor.id,
        expires_at=current_time + VERIFICATION_CODE_TTL,
    )
    auth_session.status = "submitted"
    auth_session.handled_by_user_id = actor.id
    session.add(verification)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="account.auth_code.submitted",
        resource_type="account",
        resource_id=str(auth_session.account_id),
        payload={"auth_session_id": auth_session.id, "code_type": code_type},
    )
    return verification


def mark_auth_session_success(session: Session, auth_session: AccountAuthSession, *, actor: User) -> None:
    _require_sensitive_auth_permission(session, actor)
    account = get_account(session, auth_session.account_id)
    old_auth_status = account.auth_status if account else None
    auth_session.status = "success"
    auth_session.handled_by_user_id = actor.id
    if account is not None:
        account.auth_status = "connected"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="account.auth_session.success",
        resource_type="account",
        resource_id=str(auth_session.account_id),
        payload={"auth_session_id": auth_session.id},
    )
    if account is not None and old_auth_status != account.auth_status:
        emit_event(
            session,
            actor=actor,
            event_name="account.auth_status.changed",
            resource_type="account",
            resource_id=str(account.id),
            payload={"from": old_auth_status, "to": account.auth_status},
        )


def mark_auth_session_failed(
    session: Session,
    auth_session: AccountAuthSession,
    *,
    actor: User,
    failure_reason: str,
) -> None:
    _require_sensitive_auth_permission(session, actor)
    auth_session.status = "failed"
    auth_session.failure_reason = failure_reason[:255]
    auth_session.handled_by_user_id = actor.id
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="account.auth_session.failed",
        resource_type="account",
        resource_id=str(auth_session.account_id),
        payload={"auth_session_id": auth_session.id, "reason": "safe_failure_recorded"},
    )


def expire_auth_sessions(session: Session, *, now: datetime | None = None) -> int:
    current_time = now or _now()
    sessions = list(
        session.scalars(
            select(AccountAuthSession).where(
                AccountAuthSession.status.in_(("pending", "waiting_for_code", "submitted")),
                AccountAuthSession.expires_at <= current_time,
            )
        ).all()
    )
    for auth_session in sessions:
        auth_session.status = "expired"
        account = get_account(session, auth_session.account_id)
        old_auth_status = account.auth_status if account else None
        if account is not None:
            account.auth_status = "expired"
        emit_event(
            session,
            actor=None,
            event_name="account.auth_session.expired",
            resource_type="account",
            resource_id=str(auth_session.account_id),
            payload={"auth_session_id": auth_session.id},
        )
        if account is not None and old_auth_status != account.auth_status:
            emit_event(
                session,
                actor=None,
                event_name="account.auth_status.changed",
                resource_type="account",
                resource_id=str(account.id),
                payload={"from": old_auth_status, "to": account.auth_status},
            )
    session.flush()
    return len(sessions)


def account_audit_logs(session: Session, account: Account, *, limit: int = 10) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_type == "account", AuditLog.resource_id == str(account.id))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
    )


def accounts_for_model(session: Session, model_brand_id: int) -> list[Account]:
    return list(
        session.scalars(
            select(Account)
            .where(Account.model_brand_id == model_brand_id, Account.status != "archived")
            .options(selectinload(Account.model_brand))
            .order_by(Account.id)
        ).all()
    )


def platform_label(platform: str) -> str:
    return {
        "instagram": "Instagram",
        "x": "X",
        "onlyfans": "OnlyFans",
        "email": "Email",
        "other": "Other",
    }.get(platform, platform.title())


def accounts_needing_attention(session: Session) -> list[Account]:
    return list(
        session.scalars(
            select(Account)
            .where(
                Account.status != "archived",
                or_(
                    Account.status.in_(("warning", "critical", "disabled")),
                    Account.auth_status.in_(("needs_login", "needs_2fa", "expired", "locked")),
                ),
            )
            .options(selectinload(Account.model_brand))
            .order_by(Account.id)
        ).all()
    )


def account_health(account: Account):
    return calculate_account_health(account)


# TODO: connect real platform auth through official APIs/OAuth where available.
# TODO: connect assigned_proxy_id to the proxy vault once proxy ownership exists.
# TODO: connect automation rules after simulation-mode run records exist.
