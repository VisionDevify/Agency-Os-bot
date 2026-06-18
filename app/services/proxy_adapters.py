from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import socket
import time
from urllib.error import URLError
from urllib.request import urlopen

from app.core.config import settings
from app.models.proxy import Proxy
from app.services.crypto import decrypt_secret


@dataclass(frozen=True)
class ProxyAdapterResult:
    success: bool
    latency_ms: int | None = None
    detected_ip_masked: str | None = None
    detected_country: str | None = None
    detected_state: str | None = None
    detected_city: str | None = None
    location_confidence: str | None = None
    failure_reason: str | None = None


class ProxyProviderAdapter:
    provider_name = "generic"

    def check(self, proxy: Proxy, *, include_location: bool, timeout_seconds: int) -> ProxyAdapterResult:
        raise NotImplementedError


def mask_detected_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = ipaddress.ip_address(value.strip())
    except ValueError:
        return "masked"
    if parsed.version == 4:
        parts = str(parsed).split(".")
        return f"{parts[0]}.{parts[1]}.x.{parts[3]}"
    exploded = parsed.exploded.split(":")
    return f"{exploded[0]}:{exploded[1]}:...:{exploded[-1]}"


def _safe_failure(error: Exception | str) -> str:
    text = str(error).strip().lower()
    if not text:
        return "proxy check failed"
    for marker in ("password", "credential", "secret", "token", "username"):
        if marker in text:
            return "proxy check failed; sensitive details redacted"
    return text[:240]


def _socks5_http_get(
    *,
    proxy_host: str,
    proxy_port: int,
    username: str,
    password: str,
    target_host: str,
    target_path: str,
    timeout_seconds: int,
) -> str:
    if len(username.encode()) > 255 or len(password.encode()) > 255:
        raise ValueError("proxy credential length unsupported")
    host_bytes = target_host.encode("idna")
    if len(host_bytes) > 255:
        raise ValueError("target host too long")

    with socket.create_connection((proxy_host, proxy_port), timeout=timeout_seconds) as sock:
        sock.settimeout(timeout_seconds)
        sock.sendall(b"\x05\x01\x02")
        response = sock.recv(2)
        if response != b"\x05\x02":
            raise ConnectionError("proxy authentication method rejected")

        username_bytes = username.encode()
        password_bytes = password.encode()
        sock.sendall(
            b"\x01"
            + bytes([len(username_bytes)])
            + username_bytes
            + bytes([len(password_bytes)])
            + password_bytes
        )
        auth_response = sock.recv(2)
        if len(auth_response) != 2 or auth_response[1] != 0:
            raise ConnectionError("proxy authentication failed")

        request = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + (80).to_bytes(2, "big")
        sock.sendall(request)
        connect_response = sock.recv(10)
        if len(connect_response) < 2 or connect_response[1] != 0:
            raise ConnectionError("proxy connect failed")

        http_request = (
            f"GET {target_path} HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            "Connection: close\r\n"
            "User-Agent: FortunaOS-ProxyHealth/1.0\r\n"
            "\r\n"
        ).encode()
        sock.sendall(http_request)
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    response_text = b"".join(chunks).decode("utf-8", errors="replace")
    if "\r\n\r\n" not in response_text:
        raise ConnectionError("proxy response incomplete")
    header, body = response_text.split("\r\n\r\n", 1)
    status_line = header.splitlines()[0] if header.splitlines() else ""
    if " 200 " not in status_line:
        raise ConnectionError("proxy ip check failed")
    return body.strip()


def _detect_location(ip_address: str, *, timeout_seconds: int) -> dict[str, str | None]:
    provider = (settings.proxy_location_provider or "").strip().casefold()
    if provider not in {"ipwhois", "ipwho.is"}:
        return {"country": None, "state": None, "city": None, "confidence": "provider_disabled"}
    try:
        with urlopen(f"https://ipwho.is/{ip_address}", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return {"country": None, "state": None, "city": None, "confidence": "unknown"}
    if not payload.get("success", False):
        return {"country": None, "state": None, "city": None, "confidence": "unknown"}
    return {
        "country": payload.get("country"),
        "state": payload.get("region"),
        "city": payload.get("city"),
        "confidence": "provider_reported",
    }


class OlympixMobileSocks5Adapter(ProxyProviderAdapter):
    provider_name = "Olympix Mobile SOCKS5"

    def check(self, proxy: Proxy, *, include_location: bool, timeout_seconds: int) -> ProxyAdapterResult:
        started = time.monotonic()
        try:
            password = decrypt_secret(proxy.encrypted_password)
            detected_ip = _socks5_http_get(
                proxy_host=proxy.host,
                proxy_port=proxy.port,
                username=proxy.generated_username,
                password=password,
                target_host="api.ipify.org",
                target_path="/?format=text",
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            return ProxyAdapterResult(success=False, failure_reason=_safe_failure(exc))

        latency_ms = int((time.monotonic() - started) * 1000)
        masked_ip = mask_detected_ip(detected_ip)
        if not include_location:
            return ProxyAdapterResult(
                success=True,
                latency_ms=latency_ms,
                detected_ip_masked=masked_ip,
                location_confidence="not_requested",
            )

        location = _detect_location(detected_ip, timeout_seconds=timeout_seconds)
        return ProxyAdapterResult(
            success=True,
            latency_ms=latency_ms,
            detected_ip_masked=masked_ip,
            detected_country=location["country"],
            detected_state=location["state"],
            detected_city=location["city"],
            location_confidence=location["confidence"],
            failure_reason=None if location["country"] else "connectivity passed, location unknown",
        )


def adapter_for_proxy(proxy: Proxy) -> ProxyProviderAdapter:
    provider = (proxy.provider or "").casefold()
    if "olympix" in provider or proxy.host == "host.olympix.io":
        return OlympixMobileSocks5Adapter()
    return OlympixMobileSocks5Adapter()
