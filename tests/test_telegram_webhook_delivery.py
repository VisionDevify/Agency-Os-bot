from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

import app.main as main
from app.bot.runner import _telegram_webhook_delivery_active


class _FakeRequest:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def json(self) -> dict[str, object]:
        return self.payload


def test_telegram_webhook_rejects_missing_secret(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "telegram_bot_token", SecretStr("123456:test-token"))
    monkeypatch.setattr(main.settings, "app_secret_key", SecretStr("test-app-secret"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.telegram_webhook(_FakeRequest({"update_id": 1}), None))

    assert exc.value.status_code == 403


def test_telegram_webhook_accepts_valid_secret_without_exposing_token(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_feed(payload: dict[str, object]) -> None:
        captured.update(payload)

    token = "123456:test-token"
    app_secret = "test-app-secret"
    monkeypatch.setattr(main.settings, "telegram_bot_token", SecretStr(token))
    monkeypatch.setattr(main.settings, "app_secret_key", SecretStr(app_secret))
    monkeypatch.setattr(main, "_feed_telegram_webhook_update", fake_feed)

    response = asyncio.run(
        main.telegram_webhook(
            _FakeRequest({"update_id": 42}),
            main._telegram_webhook_secret(token, app_secret),
        )
    )

    assert response == {"ok": True}
    assert captured == {"update_id": 42}
    assert token not in str(response)


class _WebhookInfoBot:
    def __init__(self, url: str) -> None:
        self.url = url

    async def get_webhook_info(self):
        return SimpleNamespace(url=self.url)


def test_worker_detects_active_webhook_delivery() -> None:
    assert asyncio.run(_telegram_webhook_delivery_active(_WebhookInfoBot("https://example.test/telegram/webhook"))) is True
    assert asyncio.run(_telegram_webhook_delivery_active(_WebhookInfoBot(""))) is False
