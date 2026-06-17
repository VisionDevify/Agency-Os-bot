from app.services.audit import build_audit_event, sanitize_details


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
