from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


DEFAULT_EXPECTED_SERVICES = {
    "api": ("api", "web", "agency-os-bot", "fortuna"),
    "worker": ("worker", "bot", "telegram", "sparkling-cat"),
    "postgres": ("postgres", "postgresql"),
    "redis": ("redis",),
}

SECRET_MARKERS = (
    "token",
    "secret",
    "password",
    "database_url",
    "redis_url",
    "telegram",
    "authorization",
    "credential",
)


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class Check:
    status: str
    evidence: str | None = None
    reason: str | None = None
    severity: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.evidence:
            payload["evidence"] = self.evidence
        if self.reason:
            payload["reason"] = self.reason
        if self.severity:
            payload["severity"] = self.severity
        if self.details:
            payload["details"] = self.details
        return payload


Runner = Callable[[list[str], int], CommandResult]


def _safe_text(value: str | None, *, limit: int = 500) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    redacted = text
    for marker in SECRET_MARKERS:
        redacted = redacted.replace(marker, "[redacted]")
        redacted = redacted.replace(marker.upper(), "[redacted]")
    return redacted[:limit]


def _command_from_env_or_path() -> list[str] | None:
    explicit = os.environ.get("RAILWAY_CLI_COMMAND")
    if explicit:
        return shlex.split(explicit, posix=os.name != "nt")
    binary = shutil.which("railway")
    return [binary] if binary else None


def _run_subprocess(command: list[str], timeout_seconds: int) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)
    except FileNotFoundError as exc:
        return CommandResult(127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        return CommandResult(124, exc.stdout or "", exc.stderr or "Command timed out.")


def _run_cli(
    base_command: list[str] | None,
    args: list[str],
    *,
    runner: Runner,
    timeout_seconds: int = 20,
) -> CommandResult:
    if base_command is None:
        return CommandResult(127, "", "Railway CLI is not installed or not on PATH.")
    return runner([*base_command, *args], timeout_seconds)


def _status_from_return(result: CommandResult) -> Check:
    combined = f"{result.stdout}\n{result.stderr}".strip()
    safe = _safe_text(combined)
    lowered = combined.casefold()
    if result.returncode == 0:
        return Check("pass", evidence=safe or "Command completed successfully.")
    if "unauthorized" in lowered or "please login" in lowered or "not logged in" in lowered:
        return Check(
            "unavailable",
            reason="Railway CLI is installed but not authenticated.",
            severity="blocking",
            evidence=safe,
        )
    if result.returncode in {124, 127}:
        return Check("unavailable", reason=safe or "Railway CLI command could not run.", severity="blocking")
    return Check("fail", reason=safe or f"Railway CLI command failed with exit code {result.returncode}.")


def _parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _flatten_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                found.append(key)
            found.extend(_flatten_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_flatten_strings(item))
    elif isinstance(value, str):
        found.append(value)
    return found


def _service_checks(status_payload: Any | None, status_text: str, auth: Check) -> dict[str, Check]:
    if auth.status != "pass":
        return {
            key: Check("unavailable", reason="Railway authentication is required for service discovery.", severity="blocking")
            for key in DEFAULT_EXPECTED_SERVICES
        }

    haystack = " ".join(_flatten_strings(status_payload)).casefold() if status_payload is not None else status_text.casefold()
    if not haystack.strip():
        return {
            key: Check("unavailable", reason="Railway status output did not include service details.", severity="blocking")
            for key in DEFAULT_EXPECTED_SERVICES
        }

    checks: dict[str, Check] = {}
    for service, aliases in DEFAULT_EXPECTED_SERVICES.items():
        if any(alias in haystack for alias in aliases):
            checks[service] = Check("pass", evidence=f"Found Railway service signal for {service}.")
        else:
            checks[service] = Check(
                "unavailable",
                reason=f"Could not find a visible Railway service signal for {service}.",
                severity="blocking",
            )
    return checks


def _health_check(url: str | None) -> Check:
    if not url:
        return Check("unavailable", reason="No public health URL was provided.", severity="warning")
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return Check("fail", reason=f"Public health check failed: {type(exc).__name__}.")

    expected = {
        "status": "ok",
        "db_backend": "postgresql",
        "db_durable": True,
        "redis": "healthy",
    }
    mismatches = {
        key: {"expected": expected_value, "observed": payload.get(key)}
        for key, expected_value in expected.items()
        if payload.get(key) != expected_value
    }
    metadata = {
        "app_name": payload.get("app_name"),
        "environment": payload.get("environment"),
        "git_commit": payload.get("git_commit"),
        "build_version": payload.get("build_version"),
        "deployed_at": payload.get("deployed_at"),
        "alembic_revision": payload.get("alembic_revision"),
        "db_backend": payload.get("db_backend"),
        "db_durable": payload.get("db_durable"),
        "redis": payload.get("redis"),
    }
    if mismatches:
        return Check("fail", reason="Public health payload did not match production-ready expectations.", details={"mismatches": mismatches, "metadata": metadata})
    return Check("pass", evidence="Public /health reports ok, PostgreSQL durable, and Redis healthy.", details={"metadata": metadata})


def build_report(
    *,
    railway_command: list[str] | None = None,
    health_url: str | None = None,
    runner: Runner = _run_subprocess,
) -> dict[str, Any]:
    base_command = railway_command if railway_command is not None else _command_from_env_or_path()
    if base_command == []:
        base_command = None

    if base_command is None:
        cli = Check("unavailable", reason="Railway CLI is not installed or not on PATH.", severity="blocking")
        version_text = ""
    else:
        version_result = _run_cli(base_command, ["--version"], runner=runner)
        cli = _status_from_return(version_result)
        version_text = _safe_text(version_result.stdout or version_result.stderr, limit=120)
        if cli.status == "pass":
            cli.evidence = version_text or cli.evidence

    whoami = _run_cli(base_command, ["whoami"], runner=runner)
    auth = _status_from_return(whoami)

    status_payload = None
    status_text = ""
    project = Check("unavailable", reason="Railway authentication is required before project status can be checked.", severity="blocking")
    if auth.status == "pass":
        status_result = _run_cli(base_command, ["status", "--json"], runner=runner)
        if status_result.returncode != 0:
            status_result = _run_cli(base_command, ["status"], runner=runner)
        project = _status_from_return(status_result)
        status_text = _safe_text(status_result.stdout or status_result.stderr, limit=2000)
        status_payload = _parse_json(status_result.stdout)

    services = _service_checks(status_payload, status_text, auth)
    health = _health_check(health_url)

    return {
        "railway_cli": {**cli.as_dict(), "version": version_text or None},
        "auth": auth.as_dict(),
        "project": project.as_dict(),
        "services": {name: check.as_dict() for name, check in services.items()},
        "public_health": health.as_dict(),
    }


def _summary(report: dict[str, Any]) -> str:
    lines = ["Railway Verification Summary"]
    lines.append(f"- CLI: {report['railway_cli']['status']}")
    lines.append(f"- Auth: {report['auth']['status']}")
    lines.append(f"- Project: {report['project']['status']}")
    for name, payload in report["services"].items():
        lines.append(f"- {name}: {payload['status']}")
    lines.append(f"- public_health: {report['public_health']['status']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Railway status without mutating resources or printing secrets.")
    parser.add_argument("--health-url", default=os.environ.get("FORTUNA_HEALTH_URL"))
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args(argv)

    report = build_report(health_url=args.health_url)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_summary(report))
        print()
        print(json.dumps(report, indent=2, sort_keys=True))
    has_fail = any(
        payload.get("status") == "fail"
        for section, payload in report.items()
        if isinstance(payload, dict) and section != "services"
    ) or any(payload.get("status") == "fail" for payload in report["services"].values())
    return 1 if has_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
