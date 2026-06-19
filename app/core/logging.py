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
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    else:
        root.setLevel(logging.INFO)
    if not any(isinstance(item, SecretRedactionFilter) for item in root.filters):
        root.addFilter(SecretRedactionFilter())
