SENSITIVE_KEYS = {
    "api_key",
    "chat_id",
    "code",
    "code_hash",
    "credential",
    "credentials",
    "encryption_key",
    "encrypted_password",
    "owner_telegram_id",
    "password",
    "proxy_password",
    "private_key",
    "raw_chat_id",
    "secret",
    "session_string",
    "telegram_chat_id",
    "token",
    "verification_code",
}


def sanitize_value(value):
    if isinstance(value, dict):
        return sanitize_details(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    return value


def sanitize_details(details: dict | None) -> dict:
    sanitized: dict = {}
    for key, value in (details or {}).items():
        if key.lower() in SENSITIVE_KEYS:
            sanitized[key] = "[redacted]"
        else:
            sanitized[key] = sanitize_value(value)
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
