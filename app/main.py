from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router
from app.core.config import settings
from app.db.migrations import run_migrations
from app.db.session import SessionLocal
from app.services.heartbeats import record_heartbeat

app = FastAPI(title=settings.app_name)
app.include_router(router)


@app.on_event("startup")
async def startup() -> None:
    if SessionLocal is not None:
        run_migrations()


@app.get("/health")
async def health() -> dict[str, str]:
    status = {"status": "ok", "api": "healthy", "db": "unknown", "redis": "unknown"}
    if SessionLocal is not None:
        try:
            with SessionLocal() as session:
                session.execute(text("select 1"))
                status["db"] = "healthy"
                try:
                    record_heartbeat(session, service_name="api", status="healthy", metadata={"source": "health"})
                    record_heartbeat(session, service_name="db", status="healthy", metadata={"source": "health"})
                    session.commit()
                except Exception:
                    session.rollback()
        except Exception:
            status["db"] = "unhealthy"
    if settings.redis_url:
        try:
            from redis import Redis

            client = Redis.from_url(settings.redis_url)
            client.ping()
            status["redis"] = "healthy"
            if SessionLocal is not None:
                try:
                    with SessionLocal() as session:
                        record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "health"})
                        session.commit()
                except Exception:
                    pass
        except Exception:
            status["redis"] = "unhealthy"
            if SessionLocal is not None:
                try:
                    with SessionLocal() as session:
                        record_heartbeat(session, service_name="redis", status="unhealthy", metadata={"source": "health"})
                        session.commit()
                except Exception:
                    pass
    return status
