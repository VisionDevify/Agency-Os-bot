import pytest

from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.proxy import ProxyRotationHistory
from app.services.accounts import create_account
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.crypto import decrypt_secret
from app.services.model_brands import create_model_brand
from app.services.permissions import RoleName
from app.services.proxies import (
    PROXY_HEALTH_CRITICAL,
    ProxyTestResult,
    accounts_missing_proxy,
    assign_proxy_to_account,
    calculate_proxy_health,
    create_proxy,
    repair_proxy,
    rollback_session,
    rotate_session,
    simulation_mode_summary,
    verify_location_with_rotation,
)

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


def test_proxy_creation_encrypts_password_and_audits() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)

        proxy = create_proxy(
            session,
            actor=owner,
            provider="brightdata",
            host="proxy.example",
            port=8000,
            base_username="base",
            password="super-secret",
            target_country="United States",
            target_state="Florida",
        )

        assert proxy.encrypted_password != "super-secret"
        assert decrypt_secret(proxy.encrypted_password) == "super-secret"
        assert proxy.session_suffix.startswith("session_")
        assert proxy.generated_username.endswith(proxy.session_suffix)
        assert session.query(AuditLog).filter_by(action="proxy.created").count() == 1
        assert "super-secret" not in str(session.query(AuditLog).all())


def test_proxy_assignment_and_missing_accounts() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Proxy Account Model")
        account = create_account(session, model_brand=model, platform="instagram", username="ig", actor=owner)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.example.com",
            port=8001,
            base_username="base",
            password="secret",
        )

        assert account in accounts_missing_proxy(session)
        assign_proxy_to_account(session, proxy, account, actor=owner)

        assert account.assigned_proxy_id == proxy.id
        assert account not in accounts_missing_proxy(session)
        assert session.query(AuditLog).filter_by(action="proxy.assigned").count() == 1


def test_session_rotation_and_rollback() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.local",
            port=8002,
            base_username="base",
            password="secret",
        )
        original = proxy.session_suffix

        history = rotate_session(
            session,
            proxy,
            actor=owner,
            test_result=ProxyTestResult(success=True, latency_ms=150),
            new_suffix="session_abcdef12",
        )

        assert history.status == "succeeded"
        assert proxy.previous_session_suffix == original
        assert proxy.session_suffix == "session_abcdef12"
        assert proxy.rotation_count == 1

        rollback = rollback_session(session, proxy, actor=owner)

        assert rollback.status == "rolled_back"
        assert proxy.session_suffix == original
        assert session.query(ProxyRotationHistory).count() == 2


def test_location_verification_creates_incident_on_mismatch() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.local",
            port=8003,
            base_username="base",
            password="secret",
            target_country="United States",
            target_state="Florida",
        )

        matched = verify_location_with_rotation(
            session,
            proxy,
            actor=owner,
            attempts=[
                ProxyTestResult(success=True, detected_country="United States", detected_state="New York"),
                ProxyTestResult(success=True, detected_country="United States", detected_state="California"),
            ],
            max_attempts=2,
        )

        assert matched is False
        assert proxy.location_mismatch_count == 2
        assert session.query(Incident).filter_by(source_type="proxy", source_id=str(proxy.id)).count() == 1
        assert session.query(AuditLog).filter_by(action="proxy.location.mismatch").count() == 2


def test_health_score_calculation() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.local",
            port=8004,
            base_username="base",
            password="secret",
        )
        proxy.connection_test_count = 4
        proxy.failure_count = 4
        proxy.latency_ms = 4000
        proxy.location_mismatch_count = 2

        health = calculate_proxy_health(proxy)

        assert health.status == PROXY_HEALTH_CRITICAL
        assert health.score < 50


def test_repair_workflow_success_and_failure_paths() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        repaired_proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.local",
            port=8005,
            base_username="base",
            password="secret",
        )

        result = repair_proxy(
            session,
            repaired_proxy,
            actor=owner,
            initial_result=ProxyTestResult(success=False, failure_reason="offline"),
            repair_result=ProxyTestResult(success=True, detected_country=None, detected_state=None, latency_ms=200),
        )

        assert result.repaired is True
        assert session.query(AuditLog).filter_by(action="proxy.repair.succeeded").count() == 1

        failed_proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy2.local",
            port=8006,
            base_username="base2",
            password="secret",
        )
        failure = repair_proxy(
            session,
            failed_proxy,
            actor=owner,
            initial_result=ProxyTestResult(success=False, failure_reason="offline"),
            repair_result=ProxyTestResult(success=False, failure_reason="still_offline"),
        )

        assert failure.incident_created is True
        assert session.query(Incident).filter_by(source_type="proxy", source_id=str(failed_proxy.id)).count() == 1
        assert session.query(AuditLog).filter_by(action="proxy.repair.failed").count() == 1


def test_simulation_mode_counts_candidates() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.example.com",
            port=1081,
            base_username="base",
            password="secret",
        )
        proxy.status = "critical"
        proxy.health_score = 25
        proxy.failure_count = 4

        summary = simulation_mode_summary(session)

        assert summary.would_rotate == 1
        assert summary.would_repair == 1
        assert summary.would_fail == 1


def test_proxy_permission_checks() -> None:
    with session_scope() as session:
        setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        viewer = _active_user(session, 20, "Viewer")
        assign_role_to_user(session, viewer, RoleName.VIEWER)

        with pytest.raises(PermissionError):
            create_proxy(
                session,
                actor=viewer,
                provider="provider",
                host="proxy.local",
                port=8008,
                base_username="base",
                password="secret",
            )

        assert session.query(AuditLog).filter_by(action="access.denied", resource_type="proxy").count() == 1
