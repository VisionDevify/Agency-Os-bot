import logging

SENSITIVE_WORDS = ("token", "secret", "password", "session", "key")


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if any(word in message.lower() for word in SENSITIVE_WORDS):
            record.msg = "[redacted sensitive log message]"
            record.args = ()
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    root.addFilter(SecretRedactionFilter())
