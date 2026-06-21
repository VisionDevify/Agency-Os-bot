from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.recovery import BackupStorageTarget
from app.models.user import User
from app.services.auth import audit_action
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.events import emit_event
from app.services.recommendations import upsert_recommendation


SUPPORTED_BACKUP_PROVIDERS = ("s3_compatible", "backblaze_b2", "manual_export")
FUTURE_BACKUP_PROVIDERS = ("google_drive", "cloudflare_r2", "azure_blob")


@dataclass(frozen=True)
class ProviderOperationResult:
    success: bool
    status: str
    summary: str
    artifact_uri: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    data: bytes | None = None


class BackupStorageProvider(Protocol):
    target_type: str

    def test_connection(self) -> ProviderOperationResult:
        ...

    def upload_artifact(self, *, key: str, payload: bytes, checksum: str) -> ProviderOperationResult:
        ...

    def verify_artifact(self, *, artifact_uri: str, checksum: str) -> ProviderOperationResult:
        ...

    def download_artifact(self, *, artifact_uri: str) -> ProviderOperationResult:
        ...


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _safe_summary(value: str | None, *, fallback: str = "The storage provider could not complete that request.") -> str:
    if not value:
        return fallback
    redacted = value
    for marker in ("secret", "password", "token", "key=", "credential", "authorization"):
        redacted = redacted.replace(marker, "[redacted]")
        redacted = redacted.replace(marker.upper(), "[redacted]")
    redacted = re.sub(r"(?i)(the\s+key\s+)'[^']+'", r"\1'[redacted]'", redacted)
    redacted = re.sub(r"(?i)(access[_ -]?key(?:id)?\s*[:=]\s*)[A-Za-z0-9+/=_-]{8,}", r"\1[redacted]", redacted)
    redacted = re.sub(r"(?i)(application[_ -]?key\s*[:=]\s*)[A-Za-z0-9+/=_-]{8,}", r"\1[redacted]", redacted)
    redacted = re.sub(r"\b[A-Za-z0-9_-]{20,}\b", "[redacted]", redacted)
    return redacted[:300]


def _safe_http_error_summary(exc: urllib.error.HTTPError) -> str:
    base = f"Storage provider returned HTTP {exc.code}."
    try:
        body = exc.read(4096)
    except Exception:
        body = b""
    if not body:
        return base
    try:
        root = ET.fromstring(body.decode("utf-8", errors="replace"))
        code = root.findtext("Code") or root.findtext("{*}Code")
        message = root.findtext("Message") or root.findtext("{*}Message")
    except Exception:
        return base
    safe_parts: list[str] = []
    if code:
        safe_parts.append(f"code={_safe_summary(code, fallback='unknown')}")
    if message:
        safe_parts.append(f"message={_safe_summary(message)}")
    if not safe_parts:
        return base
    return f"{base} ({'; '.join(safe_parts)})"


def mask_credential(value: str | None) -> str:
    if not value:
        return "Not set"
    clean = str(value).strip()
    tail = clean[-4:] if len(clean) >= 4 else clean
    return f"****{tail}"


def mask_storage_config(target_type: str, config: dict[str, Any]) -> dict[str, str]:
    if target_type == "s3_compatible":
        return {
            "endpoint": str(config.get("endpoint") or "Not set"),
            "bucket": str(config.get("bucket") or "Not set"),
            "region": str(config.get("region") or "auto"),
            "access_key": mask_credential(str(config.get("access_key") or "")),
            "secret_key": "Encrypted" if config.get("secret_key") else "Not set",
        }
    if target_type == "backblaze_b2":
        return {
            "bucket": str(config.get("bucket") or "Not set"),
            "key_id": mask_credential(str(config.get("key_id") or "")),
            "application_key": "Encrypted" if config.get("application_key") else "Not set",
        }
    return {"mode": "Manual export"}


def backup_s3_environment_state() -> dict[str, Any]:
    fields = {
        "BACKUP_S3_ENDPOINT": settings.backup_s3_endpoint,
        "BACKUP_S3_BUCKET": settings.backup_s3_bucket,
        "BACKUP_S3_REGION": settings.backup_s3_region,
        "BACKUP_S3_ACCESS_KEY": settings.backup_s3_access_key.get_secret_value(),
        "BACKUP_S3_SECRET_KEY": settings.backup_s3_secret_key.get_secret_value(),
    }
    required = ("BACKUP_S3_ENDPOINT", "BACKUP_S3_BUCKET", "BACKUP_S3_ACCESS_KEY", "BACKUP_S3_SECRET_KEY")
    missing = [name for name in required if not str(fields.get(name) or "").strip()]
    return {
        "configured": not missing,
        "missing": missing,
        "endpoint_configured": bool(settings.backup_s3_endpoint),
        "bucket_configured": bool(settings.backup_s3_bucket),
        "region_configured": bool(settings.backup_s3_region),
        "access_key_masked": mask_credential(settings.backup_s3_access_key.get_secret_value()),
        "secret_key_status": "Configured" if settings.backup_s3_secret_key.get_secret_value() else "Missing",
    }


def encrypt_storage_config(config: dict[str, Any]) -> str:
    return encrypt_secret(json.dumps(config, sort_keys=True))


def decrypt_storage_config(target: BackupStorageTarget) -> dict[str, Any]:
    if not target.encrypted_config_json:
        return {}
    try:
        payload = decrypt_secret(target.encrypted_config_json)
        parsed = json.loads(payload)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class ManualExportProvider:
    target_type = "manual_export"

    def test_connection(self) -> ProviderOperationResult:
        return ProviderOperationResult(
            success=True,
            status="manual_required",
            summary="Manual export is available. External upload still requires owner action.",
        )

    def upload_artifact(self, *, key: str, payload: bytes, checksum: str) -> ProviderOperationResult:
        return ProviderOperationResult(
            success=False,
            status="manual_required",
            summary="Manual Export needs the owner to download and store the encrypted artifact outside Railway.",
        )

    def verify_artifact(self, *, artifact_uri: str, checksum: str) -> ProviderOperationResult:
        return ProviderOperationResult(
            success=False,
            status="manual_required",
            summary="Manual Export cannot verify external storage until the owner stores and confirms the file.",
        )

    def download_artifact(self, *, artifact_uri: str) -> ProviderOperationResult:
        return ProviderOperationResult(
            success=False,
            status="manual_required",
            summary="Manual Export does not provide an automatic download path.",
        )


class BackblazeB2Provider(ManualExportProvider):
    target_type = "backblaze_b2"

    def test_connection(self) -> ProviderOperationResult:
        return ProviderOperationResult(
            success=False,
            status="not_configured",
            summary=(
                "Backblaze B2 setup is prepared, but direct B2 upload is not active yet. "
                "Use a Backblaze S3-compatible endpoint through S3-Compatible storage."
            ),
        )


class S3CompatibleProvider:
    target_type = "s3_compatible"

    def __init__(self, config: dict[str, Any]) -> None:
        self.endpoint = str(config.get("endpoint") or "").rstrip("/")
        self.bucket = str(config.get("bucket") or "").strip("/")
        self.access_key = str(config.get("access_key") or "")
        self.secret_key = str(config.get("secret_key") or "")
        self.region = str(config.get("region") or "us-east-1")

    def test_connection(self) -> ProviderOperationResult:
        missing = [
            name
            for name, value in {
                "endpoint": self.endpoint,
                "bucket": self.bucket,
                "access key": self.access_key,
                "secret key": self.secret_key,
            }.items()
            if not value
        ]
        if missing:
            return ProviderOperationResult(
                success=False,
                status="not_configured",
                summary=f"Missing storage setting: {', '.join(missing)}.",
            )
        key = f"fortuna-connection-test/{hashlib.sha256(str(_now()).encode()).hexdigest()[:16]}.txt"
        payload = b"fortuna backup storage connection test"
        checksum = hashlib.sha256(payload).hexdigest()
        uploaded = self.upload_artifact(key=key, payload=payload, checksum=checksum)
        if not uploaded.success:
            return uploaded
        verified = self.verify_artifact(artifact_uri=uploaded.artifact_uri or "", checksum=checksum)
        self._request("DELETE", key)
        return verified

    def upload_artifact(self, *, key: str, payload: bytes, checksum: str) -> ProviderOperationResult:
        try:
            self._request("PUT", key, payload)
            uri = f"s3://{self.bucket}/{key}"
            return ProviderOperationResult(
                success=True,
                status="uploaded",
                summary="Backup artifact uploaded and ready for verification.",
                artifact_uri=uri,
                size_bytes=len(payload),
                checksum=checksum,
            )
        except Exception as exc:
            return ProviderOperationResult(success=False, status="failed", summary=_safe_summary(str(exc)))

    def verify_artifact(self, *, artifact_uri: str, checksum: str) -> ProviderOperationResult:
        downloaded = self.download_artifact(artifact_uri=artifact_uri)
        if not downloaded.success or downloaded.data is None:
            return downloaded
        actual = hashlib.sha256(downloaded.data).hexdigest()
        if actual != checksum:
            return ProviderOperationResult(
                success=False,
                status="failed",
                summary="Uploaded backup exists, but checksum verification failed.",
            )
        return ProviderOperationResult(
            success=True,
            status="verified",
            summary="Upload verified with matching checksum.",
            artifact_uri=artifact_uri,
            size_bytes=len(downloaded.data),
            checksum=checksum,
            data=downloaded.data,
        )

    def download_artifact(self, *, artifact_uri: str) -> ProviderOperationResult:
        try:
            key = self._key_from_uri(artifact_uri)
            data = self._request("GET", key)
            return ProviderOperationResult(
                success=True,
                status="downloaded",
                summary="Backup artifact downloaded for verification.",
                artifact_uri=artifact_uri,
                size_bytes=len(data),
                checksum=hashlib.sha256(data).hexdigest(),
                data=data,
            )
        except Exception as exc:
            return ProviderOperationResult(success=False, status="failed", summary=_safe_summary(str(exc)))

    def _key_from_uri(self, artifact_uri: str) -> str:
        prefix = f"s3://{self.bucket}/"
        if not artifact_uri.startswith(prefix):
            raise ValueError("Artifact URI does not match configured bucket.")
        return artifact_uri.removeprefix(prefix)

    def _request(self, method: str, key: str, payload: bytes | None = None) -> bytes:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("S3 endpoint must start with http:// or https://.")
        parsed_endpoint = urllib.parse.urlparse(self.endpoint)
        path = f"/{self.bucket}/{urllib.parse.quote(key, safe='/')}"
        url = urllib.parse.urlunparse(
            (parsed_endpoint.scheme, parsed_endpoint.netloc, path, "", "", "")
        )
        body = payload or b""
        now = dt.datetime.now(dt.UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        host = parsed_endpoint.netloc
        canonical_headers = (
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join(
            [method, path, "", canonical_headers, signed_headers, payload_hash]
        )
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._signing_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        request = urllib.request.Request(
            url,
            data=body if method in {"PUT", "POST"} else None,
            method=method,
            headers={
                "Authorization": authorization,
                "Host": host,
                "x-amz-content-sha256": payload_hash,
                "x-amz-date": amz_date,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(_safe_http_error_summary(exc)) from exc

    def _signing_key(self, date_stamp: str) -> bytes:
        key = ("AWS4" + self.secret_key).encode("utf-8")
        date_key = hmac.new(key, date_stamp.encode("utf-8"), hashlib.sha256).digest()
        date_region_key = hmac.new(date_key, self.region.encode("utf-8"), hashlib.sha256).digest()
        date_region_service_key = hmac.new(date_region_key, b"s3", hashlib.sha256).digest()
        return hmac.new(date_region_service_key, b"aws4_request", hashlib.sha256).digest()


def provider_for_target(target: BackupStorageTarget) -> BackupStorageProvider:
    if target.target_type == "s3_compatible":
        return S3CompatibleProvider(decrypt_storage_config(target))
    if target.target_type == "backblaze_b2":
        return BackblazeB2Provider()
    return ManualExportProvider()


def select_active_storage_target(session: Session) -> BackupStorageTarget | None:
    return session.scalar(
        select(BackupStorageTarget)
        .where(
            BackupStorageTarget.enabled.is_(True),
            BackupStorageTarget.connection_status == "active",
            BackupStorageTarget.provider_available.is_(True),
            BackupStorageTarget.target_type.not_in(("local_runtime", "manual_export")),
        )
        .order_by(BackupStorageTarget.last_success_at.desc().nulls_last(), BackupStorageTarget.id)
        .limit(1)
    )


def upsert_storage_target(
    session: Session,
    *,
    actor: User | None,
    name: str,
    target_type: str,
    config: dict[str, Any],
    provider: BackupStorageProvider | None = None,
    test_connection: bool = True,
) -> BackupStorageTarget:
    target = session.scalar(
        select(BackupStorageTarget).where(
            BackupStorageTarget.name == name,
            BackupStorageTarget.target_type == target_type,
        )
    )
    if target is None:
        target = BackupStorageTarget(name=name, target_type=target_type, enabled=False, encrypted=True)
        session.add(target)
        session.flush()
    target.encrypted = True
    target.encrypted_config_json = encrypt_storage_config(config)
    target.masked_config_json = mask_storage_config(target_type, config)
    target.connection_status = "pending"
    target.provider_available = False
    target.enabled = False
    target.last_test_summary = "Connection test has not completed yet."
    session.flush()

    result = test_storage_target_connection(session, target, actor=actor, provider=provider) if test_connection else None
    if result is None:
        target.last_test_at = _now()
        target.last_test_status = "pending"
        target.connection_status = "pending"
    session.flush()
    return target


def configure_s3_storage_from_environment(session: Session, *, actor: User | None) -> BackupStorageTarget:
    config = {
        "endpoint": settings.backup_s3_endpoint or "",
        "bucket": settings.backup_s3_bucket or "",
        "region": settings.backup_s3_region or "us-east-1",
        "access_key": settings.backup_s3_access_key.get_secret_value(),
        "secret_key": settings.backup_s3_secret_key.get_secret_value(),
    }
    return upsert_storage_target(
        session,
        actor=actor,
        name="S3-Compatible Backup Storage",
        target_type="s3_compatible",
        config=config,
    )


def configure_b2_storage_from_environment(session: Session, *, actor: User | None) -> BackupStorageTarget:
    config = {
        "bucket": settings.backup_b2_bucket or "",
        "key_id": settings.backup_b2_key_id.get_secret_value(),
        "application_key": settings.backup_b2_application_key.get_secret_value(),
    }
    return upsert_storage_target(
        session,
        actor=actor,
        name="Backblaze B2 Backup Storage",
        target_type="backblaze_b2",
        config=config,
    )


def test_storage_target_connection(
    session: Session,
    target: BackupStorageTarget,
    *,
    actor: User | None,
    provider: BackupStorageProvider | None = None,
) -> ProviderOperationResult:
    provider = provider or provider_for_target(target)
    result = provider.test_connection()
    target.last_test_at = _now()
    target.last_test_status = result.status
    target.last_test_summary = result.summary
    if result.success:
        target.connection_status = "active"
        target.provider_available = True
        target.enabled = target.target_type not in {"manual_export", "local_runtime"}
        target.last_success_at = target.last_test_at
    else:
        target.connection_status = "failed" if result.status != "not_configured" else "not_configured"
        target.provider_available = False
        target.enabled = False
        target.last_failure_at = target.last_test_at
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="backup_storage_connection_failed",
            title="Backup storage needs attention",
            description=result.summary,
            severity="critical" if result.status == "not_configured" else "warning",
            entity_type="backup_storage_target",
            entity_id=target.id,
            metadata={"target_type": target.target_type, "status": result.status},
        )
    audit_action(
        session,
        actor=actor,
        action="backup_storage.connection_tested",
        resource_type="backup_storage_target",
        resource_id=str(target.id),
        status="success" if result.success else "failed",
        details={
            "target_type": target.target_type,
            "connection_status": target.connection_status,
            "provider_available": target.provider_available,
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name="backup_storage.connection_tested",
        resource_type="backup_storage_target",
        resource_id=str(target.id),
        status="success" if result.success else "failed",
        payload={"target_type": target.target_type, "connection_status": target.connection_status},
    )
    session.flush()
    return result


def backup_storage_targets(session: Session) -> list[BackupStorageTarget]:
    return list(session.scalars(select(BackupStorageTarget).order_by(BackupStorageTarget.name)).all())


def disable_storage_target(session: Session, target: BackupStorageTarget, *, actor: User | None) -> BackupStorageTarget:
    target.enabled = False
    target.provider_available = False
    target.connection_status = "disabled"
    target.encrypted_config_json = None
    target.masked_config_json = {}
    target.last_test_summary = "Storage target was removed from active recovery setup."
    audit_action(
        session,
        actor=actor,
        action="backup_storage.removed",
        resource_type="backup_storage_target",
        resource_id=str(target.id),
        status="success",
        details={"target_type": target.target_type},
    )
    emit_event(
        session,
        actor=actor,
        event_name="backup_storage.removed",
        resource_type="backup_storage_target",
        resource_id=str(target.id),
        status="success",
        payload={"target_type": target.target_type},
    )
    session.flush()
    return target
