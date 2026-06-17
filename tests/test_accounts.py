from datetime import UTC, datetime, timedelta
import json

import pytest

from app.bot.screens import render_model_detail_page
from app.models.account import Account, AccountAuthSession, AccountVerificationCode
from app.models.audit import AuditLog
from app.services.account_health import (
    ACCOUNT_HEALTH_CRITICAL,
    ACCOUNT_HEALTH_DISABLED,
    ACCOUNT_HEALTH_HEALTHY,
    ACCOUNT_HEALTH_WARNING,
    calculate_account_health,
)
from app.services.accounts import (
    archive_account,
    create_account,
    expire_auth_sessions,
    start_auth_session,
    submit_verification_code,
    update_account,
)
from app.services.auth import (
    USER_STATUS_ACTIVE,
    assign_role_to_user,
    get_or_create_telegram_user,
    setup_owner_if_needed,
)
from app.services.dashboard import dashboard_stats
from app.services.model_brands import create_model_brand
from app.services.permissions import RoleName

from tests.utils import session_scope


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(
        session,
        telegram_user_id=telegram_id,
        display_name=display_name,
        owner_telegram_id=1,
    )
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_create_account_attached_to_model() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Account Model")

        account = create_account(
            session,
            model_brand=model,
            platform="instagram",
            username="fortuna",
            display_name="Fortuna IG",
            actor=owner,
        )

        assert account.model_brand_id == model.id
        assert account.platform == "instagram"
        assert account.username == "fortuna"
        assert account.auth_status == "not_connected"
        assert session.query(AuditLog).filter_by(action="account.created").count() == 1


def test_account_platform_status_and_auth_status_constraints() -> None:
    constraint_names = {constraint.name for constraint in Account.__table__.constraints}
    assert "ck_accounts_platform" in constraint_names
    assert "ck_accounts_status" in constraint_names
    assert "ck_accounts_auth_status" in constraint_names

    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Constraint Model")
        account = create_account(
            session,
            model_brand=model,
            platform="email",
            username="ops@example.com",
            actor=owner,
        )

        with pytest.raises(ValueError):
            create_account(
                session,
                model_brand=model,
                platform="bad_platform",
                username="bad",
                actor=owner,
            )
        with pytest.raises(ValueError):
            update_account(session, account, actor=owner, status="bad_status")
        with pytest.raises(ValueError):
            update_account(session, account, actor=owner, auth_status="bad_auth")


def test_start_auth_session_permission_checks() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Auth Model")
        account = create_account(session, model_brand=model, platform="x", username="fortuna_x", actor=owner)
        viewer = _active_user(session, 20, "Viewer User")
        assign_role_to_user(session, viewer, RoleName.VIEWER)

        with pytest.raises(PermissionError):
            start_auth_session(session, account, actor=viewer)

        auth_session = start_auth_session(session, account, actor=owner)
        assert auth_session.status == "waiting_for_code"
        assert account.auth_status == "needs_2fa"
        assert session.query(AuditLog).filter_by(action="account.auth_session.started").count() == 1


def test_2fa_code_stores_hash_only_and_audits_are_safe() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Code Model")
        account = create_account(session, model_brand=model, platform="onlyfans", username="creator", actor=owner)
        auth_session = start_auth_session(session, account, actor=owner)

        verification = submit_verification_code(
            session,
            auth_session,
            code="123456",
            code_type="sms",
            actor=owner,
        )

        assert verification.code_hash != "123456"
        assert len(verification.code_hash) == 64
        assert auth_session.status == "submitted"
        all_details = json.dumps([log.details for log in session.query(AuditLog).all()])
        assert "123456" not in all_details
        assert session.query(AuditLog).filter_by(action="account.auth_code.submitted").count() == 1


def test_auth_session_expires() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Expire Model")
        account = create_account(session, model_brand=model, platform="other", username="external", actor=owner)
        start = datetime(2026, 1, 1, tzinfo=UTC)
        auth_session = start_auth_session(session, account, actor=owner, now=start)

        expired = expire_auth_sessions(session, now=start + timedelta(minutes=11))

        assert expired == 1
        assert auth_session.status == "expired"
        assert account.auth_status == "expired"
        assert session.query(AuditLog).filter_by(action="account.auth_session.expired").count() == 1


def test_account_health_calculation_and_disabled_behavior() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Health Account Model")
        account = create_account(session, model_brand=model, platform="instagram", username="healthy", actor=owner)
        update_account(session, account, actor=owner, auth_status="connected")

        assert calculate_account_health(account).status == ACCOUNT_HEALTH_HEALTHY

        update_account(session, account, actor=owner, auth_status="needs_login")
        assert calculate_account_health(account).status == ACCOUNT_HEALTH_WARNING

        update_account(session, account, actor=owner, auth_status="expired")
        assert calculate_account_health(account).status == ACCOUNT_HEALTH_CRITICAL

        update_account(session, account, actor=owner, status="disabled")
        disabled = calculate_account_health(account)
        assert disabled.status == ACCOUNT_HEALTH_DISABLED
        assert account.status == "disabled"


def test_dashboard_account_counts() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Dashboard Account Model")
        create_account(session, model_brand=model, platform="instagram", username="ig", actor=owner)
        x_account = create_account(session, model_brand=model, platform="x", username="x_user", actor=owner)
        of_account = create_account(session, model_brand=model, platform="onlyfans", username="of_user", actor=owner)
        update_account(session, x_account, actor=owner, auth_status="needs_login")
        update_account(session, of_account, actor=owner, auth_status="needs_2fa")

        stats = dashboard_stats(session)

        assert stats.accounts == 3
        assert stats.instagram_accounts == 1
        assert stats.x_accounts == 1
        assert stats.onlyfans_accounts == 1
        assert stats.accounts_needing_login == 1
        assert stats.accounts_needing_2fa == 1


def test_model_account_counts() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Model Count Account")
        create_account(session, model_brand=model, platform="instagram", username="ig", actor=owner)
        create_account(session, model_brand=model, platform="email", username="ops@example.com", actor=owner)

        screen = render_model_detail_page(session, model.id)

        assert "Accounts Count: 2" in screen.text
        assert "Instagram Count: 1" in screen.text
        assert "Email Count: 1" in screen.text


def test_archive_account_preserves_audit() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Archive Account Model")
        account = create_account(session, model_brand=model, platform="other", username="old", actor=owner)

        archive_account(session, account, actor=owner)

        assert account.status == "archived"
        assert session.query(AuditLog).filter_by(action="account.archived").count() == 1
