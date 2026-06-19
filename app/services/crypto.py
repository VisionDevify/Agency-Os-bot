import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    raw_secret = settings.encryption_key.get_secret_value() or settings.app_secret_key.get_secret_value()
    secret = raw_secret or "agency-os-local-encryption-key"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def encrypt_bytes(value: bytes) -> bytes:
    return _fernet().encrypt(value)


def decrypt_bytes(value: bytes) -> bytes:
    return _fernet().decrypt(value)
