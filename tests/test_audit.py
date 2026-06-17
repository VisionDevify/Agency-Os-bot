from app.services.audit import build_audit_event, sanitize_details
from app.services.auth import audit_action

from tests.utils import session_scope


def test_audit_details_redact_secrets() -> None:
    details = sanitize_details({"token": "secret-token", "count": 3, "session_string": "abc"})

    assert details == {"token": "[redacted]", "count": 3, "session_string": "[redacted]"}


def test_build_audit_event_shape() -> None:
    event = build_audit_event(
        actor_user_id=1,
        action="created",
        resource_type="user",
        resource_id="2",
        details={"safe": True},
    )

    assert event["actor_user_id"] == 1
    assert event["action"] == "created"
    assert event["resource_type"] == "user"
    assert event["resource_id"] == "2"
    assert event["details"] == {"safe": True}


def test_audit_action_persists_and_redacts_details() -> None:
    with session_scope() as session:
        log = audit_action(
            session,
            actor=None,
            action="restricted_page.accessed",
            resource_type="telegram_page",
            resource_id="users",
            status="denied",
            details={"token": "secret", "permission": "manage_users"},
        )

        assert log.id is not None
        assert log.status == "denied"
        assert log.details == {"token": "[redacted]", "permission": "manage_users"}
