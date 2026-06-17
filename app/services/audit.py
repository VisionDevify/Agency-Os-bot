SENSITIVE_KEYS = {"token", "secret", "password", "session_string", "api_key", "encryption_key"}


def sanitize_details(details: dict | None) -> dict:
    sanitized: dict = {}
    for key, value in (details or {}).items():
        if key.lower() in SENSITIVE_KEYS:
            sanitized[key] = "[redacted]"
        else:
            sanitized[key] = value
    return sanitized


def build_audit_event(
    *,
    actor_user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> dict:
    return {
        "actor_user_id": actor_user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": sanitize_details(details),
    }


class AuditRecorder:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict | None = None,
    ) -> dict:
        event = build_audit_event(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
        self.events.append(event)
        return event


audit_recorder = AuditRecorder()
