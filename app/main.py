import hashlib
import hmac
import asyncio
import logging

from aiogram import Bot
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy import text

from app.api.routes import router
from app.core.config import settings
from app.db.migrations import run_migrations
from app.db.session import SessionLocal
from app.services.heartbeats import record_heartbeat
from app.services.persistence import health_payload, storage_status
from app.services.system_truth import current_alembic_revision, reconcile_stale_system_warnings

app = FastAPI(title=settings.app_display_name)
app.include_router(router)
_telegram_webhook_bot: Bot | None = None
logger = logging.getLogger(__name__)
HEALTH_CHECK_TIMEOUT_SECONDS = 5


def _telegram_webhook_secret(token: str, app_secret: str) -> str:
    seed = f"{token}:{app_secret or 'fortuna-webhook'}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _get_telegram_webhook_bot() -> Bot:
    global _telegram_webhook_bot
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured.")
    if _telegram_webhook_bot is None:
        _telegram_webhook_bot = Bot(token=token)
    return _telegram_webhook_bot


async def _feed_telegram_webhook_update(payload: dict[str, object]) -> None:
    # Import lazily so the API can boot even if Telegram-specific startup has an issue.
    from app.bot import runner as bot_runner

    bot = _get_telegram_webhook_bot()
    update = Update.model_validate(payload, context={"bot": bot})
    delivery_token = bot_runner.TELEGRAM_DELIVERY_MODE.set("webhook")
    try:
        try:
            await bot_runner.dp.feed_update(bot, update)
        except Exception:
            logger.exception(
                "Telegram webhook update failed safely",
                extra={
                    "update_id": payload.get("update_id"),
                    "has_message": "message" in payload,
                    "has_callback_query": "callback_query" in payload,
                },
            )
    finally:
        bot_runner.TELEGRAM_DELIVERY_MODE.reset(delivery_token)


@app.on_event("startup")
async def startup() -> None:
    if SessionLocal is not None:
        run_migrations()
        try:
            with SessionLocal() as session:
                reconcile_stale_system_warnings(session)
                session.commit()
        except Exception:
            # Startup health must not be blocked by best-effort stale warning cleanup.
            pass


@app.get("/health")
async def health() -> dict[str, object]:
    storage = storage_status()
    try:
        db_connected, alembic_revision = await asyncio.wait_for(
            asyncio.to_thread(_health_check_database, storage),
            timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("Health database check timed out")
        db_connected, alembic_revision = False, "timeout"
    except Exception:
        logger.exception("Health database check failed safely")
        db_connected, alembic_revision = False, "unknown"

    redis_status = "unknown"
    if settings.redis_url:
        try:
            redis_status = await asyncio.wait_for(
                asyncio.to_thread(_health_check_redis),
                timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Health Redis check timed out")
            redis_status = "unhealthy"
        except Exception:
            logger.exception("Health Redis check failed safely")
            redis_status = "unhealthy"
    return health_payload(
        storage=storage,
        db_connected=db_connected,
        redis_status=redis_status,
        alembic_revision=alembic_revision,
    )


def _health_check_database(storage) -> tuple[bool, str]:
    if SessionLocal is None:
        return False, "unconfigured"
    with SessionLocal() as session:
        session.execute(text("select 1"))
        alembic_revision = current_alembic_revision(session).lower()
        try:
            db_heartbeat_status = "degraded" if storage.backend == "sqlite_fallback" and storage.is_production else "healthy"
            record_heartbeat(
                session,
                service_name="api",
                status="healthy",
                metadata={"source": "health", "db_backend": storage.backend},
            )
            record_heartbeat(
                session,
                service_name="db",
                status=db_heartbeat_status,
                metadata={
                    "source": "health",
                    "backend": storage.backend,
                    "driver": storage.scheme,
                    "durable": str(storage.durable),
                    "warning": storage.warning or "",
                },
            )
            session.commit()
        except Exception:
            session.rollback()
        return True, alembic_revision


def _health_check_redis() -> str:
    from redis import Redis

    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    client.ping()
    if SessionLocal is not None:
        try:
            with SessionLocal() as session:
                record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "health"})
                session.commit()
        except Exception:
            pass
    return "healthy"


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured.")
    expected = _telegram_webhook_secret(token, settings.app_secret_key.get_secret_value())
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(x_telegram_bot_api_secret_token, expected):
        raise HTTPException(status_code=403, detail="Forbidden.")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Telegram update.")
    await _feed_telegram_webhook_update(payload)
    return {"ok": True}
