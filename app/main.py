from fastapi import FastAPI
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
    db_connected = False
    redis_status = "unknown"
    alembic_revision = "unknown"
    if SessionLocal is not None:
        try:
            with SessionLocal() as session:
                session.execute(text("select 1"))
                alembic_revision = current_alembic_revision(session).lower()
                db_connected = True
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
        except Exception:
            db_connected = False
    if settings.redis_url:
        try:
            from redis import Redis

            client = Redis.from_url(settings.redis_url)
            client.ping()
            redis_status = "healthy"
            if SessionLocal is not None:
                try:
                    with SessionLocal() as session:
                        record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "health"})
                        session.commit()
                except Exception:
                    pass
        except Exception:
            redis_status = "unhealthy"
            if SessionLocal is not None:
                try:
                    with SessionLocal() as session:
                        record_heartbeat(session, service_name="redis", status="unhealthy", metadata={"source": "health"})
                        session.commit()
                except Exception:
                    pass
    return health_payload(
        storage=storage,
        db_connected=db_connected,
        redis_status=redis_status,
        alembic_revision=alembic_revision,
    )
