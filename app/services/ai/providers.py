from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_AI_MODEL = "gpt-5.4-mini"
DEFAULT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class AIProviderStatus:
    provider: str
    enabled: bool
    configured: bool
    status: str
    reason: str
    next_action: str
    model: str | None = None


@dataclass(frozen=True)
class AIProviderOptions:
    use_case: str
    model: str | None = None
    timeout_seconds: int | None = None
    max_output_chars: int = 1800


@dataclass(frozen=True)
class AIProviderResponse:
    text: str
    model: str
    raw_status: str = "succeeded"
    usage: dict[str, Any] | None = None


class AIProvider(Protocol):
    provider_name: str

    def generate_reasoning(self, prompt: str, context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        ...

    def summarize_evidence(self, context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        ...

    def critique_output(self, output: dict[str, Any], context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        ...

    def get_provider_status(self) -> AIProviderStatus:
        ...

    def validate_configuration(self) -> AIProviderStatus:
        ...


class AIProviderError(Exception):
    pass


class AIProviderNotConfigured(AIProviderError):
    pass


class AIProviderTimeout(AIProviderError):
    pass


class AIProviderRateLimited(AIProviderError):
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _ai_enabled() -> bool:
    return _env_bool("AI_ENABLED", False)


def _ai_provider_name() -> str:
    return (os.getenv("AI_PROVIDER") or "openai").strip().casefold() or "openai"


def _openai_key_present() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


def _ai_model() -> str:
    return (os.getenv("AI_MODEL") or DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL


def _extract_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("output_text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(part.strip() for part in chunks if part and part.strip()).strip()


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self, *, api_key: str | None = None, timeout_seconds: int | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY") or "").strip()
        self.timeout_seconds = timeout_seconds or _env_int("AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)

    def get_provider_status(self) -> AIProviderStatus:
        enabled = _ai_enabled()
        configured = bool(self.api_key)
        model = _ai_model()
        if not enabled:
            return AIProviderStatus(
                self.provider_name,
                enabled=False,
                configured=configured,
                status="disabled",
                reason="AI_ENABLED is not true.",
                next_action="Set AI_ENABLED=true after OPENAI_API_KEY is configured.",
                model=model,
            )
        if not configured:
            return AIProviderStatus(
                self.provider_name,
                enabled=True,
                configured=False,
                status="not_configured",
                reason="OPENAI_API_KEY is missing.",
                next_action="Add OPENAI_API_KEY in Railway.",
                model=model,
            )
        return AIProviderStatus(
            self.provider_name,
            enabled=True,
            configured=True,
            status="configured",
            reason="OpenAI key is present by name.",
            next_action="Run an AI evidence summary.",
            model=model,
        )

    def validate_configuration(self) -> AIProviderStatus:
        return self.get_provider_status()

    def summarize_evidence(self, context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        return self.generate_reasoning(
            "Summarize the supplied evidence into the required grounded JSON contract.",
            context,
            options,
        )

    def critique_output(self, output: dict[str, Any], context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        return self.generate_reasoning(
            "Critique this AI output against the supplied evidence and return the required grounded JSON contract.",
            {"candidate_output": output, "evidence_context": context},
            options,
        )

    def generate_reasoning(self, prompt: str, context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        status = self.get_provider_status()
        if not status.enabled:
            raise AIProviderNotConfigured("AI execution is disabled.")
        if not status.configured:
            raise AIProviderNotConfigured("OpenAI API key is missing.")
        model = options.model or status.model or DEFAULT_AI_MODEL
        system_prompt = (
            "You are Fortuna's grounded reasoning layer. Use only the supplied evidence. "
            "Return compact JSON with these keys exactly: conclusion, evidence_used, reasoning_summary, "
            "confidence, limitations, next_best_move, safety_flags. Do not invent facts. "
            "Never mark systems healthy, protected, passed, fixed, or successful unless evidence states that."
        )
        user_prompt = {
            "task": prompt,
            "context": context,
            "required_output": {
                "conclusion": "short string",
                "evidence_used": ["source labels from context"],
                "reasoning_summary": "short string",
                "confidence": "low|medium|high",
                "limitations": ["missing evidence or uncertainty"],
                "next_best_move": "short actionable string",
                "safety_flags": ["unsupported_claim if any"],
            },
        }
        payload: dict[str, Any] = {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(user_prompt, ensure_ascii=True)}],
                },
            ],
            "max_output_tokens": max(200, min(1200, options.max_output_chars // 3)),
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=options.timeout_seconds or self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise AIProviderError("OpenAI rejected the API key.") from exc
            if exc.code == 429:
                raise AIProviderRateLimited("OpenAI rate limit reached.") from exc
            raise AIProviderError(f"OpenAI request failed with HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise AIProviderTimeout("OpenAI request timed out or could not connect.") from exc
        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise AIProviderError("OpenAI returned an unreadable response.") from exc
        text = _extract_text(decoded)
        if not text:
            raise AIProviderError("OpenAI returned an empty response.")
        return AIProviderResponse(text=text, model=str(decoded.get("model") or model), usage=decoded.get("usage"))


class UnsupportedAIProvider:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def get_provider_status(self) -> AIProviderStatus:
        return AIProviderStatus(
            self.provider_name,
            enabled=_ai_enabled(),
            configured=False,
            status="not_configured",
            reason=f"AI provider '{self.provider_name}' is not implemented yet.",
            next_action="Set AI_PROVIDER=openai.",
            model=_ai_model(),
        )

    validate_configuration = get_provider_status

    def generate_reasoning(self, prompt: str, context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        raise AIProviderNotConfigured(f"AI provider '{self.provider_name}' is not implemented yet.")

    def summarize_evidence(self, context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        return self.generate_reasoning("Summarize evidence.", context, options)

    def critique_output(self, output: dict[str, Any], context: dict[str, Any], options: AIProviderOptions) -> AIProviderResponse:
        return self.generate_reasoning("Critique output.", {"output": output, "context": context}, options)


def get_ai_provider() -> AIProvider:
    provider = _ai_provider_name()
    if provider != "openai":
        return UnsupportedAIProvider(provider)
    return OpenAIProvider()


def ai_env_presence() -> dict[str, bool]:
    return {
        "AI_PROVIDER": bool(os.getenv("AI_PROVIDER")),
        "AI_ENABLED": bool(os.getenv("AI_ENABLED")),
        "OPENAI_API_KEY": _openai_key_present(),
        "AI_MODEL": bool(os.getenv("AI_MODEL")),
        "AI_TIMEOUT_SECONDS": bool(os.getenv("AI_TIMEOUT_SECONDS")),
        "AI_DAILY_LIMIT": bool(os.getenv("AI_DAILY_LIMIT")),
        "AI_MAX_CONTEXT_RECORDS": bool(os.getenv("AI_MAX_CONTEXT_RECORDS")),
        "AI_CRITIC_ENABLED": bool(os.getenv("AI_CRITIC_ENABLED")),
    }
