from collections.abc import Generator
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _engine_kwargs(database_url: str) -> dict:
    normalized = normalize_database_url(database_url)
    scheme = urlsplit(normalized).scheme.lower()
    kwargs: dict = {"pool_pre_ping": True}
    if scheme.startswith("postgresql"):
        kwargs.update(
            {
                "pool_timeout": 5,
                "pool_recycle": 300,
                "connect_args": {"connect_timeout": 5},
            }
        )
    return kwargs


engine = (
    create_engine(normalize_database_url(settings.database_url), **_engine_kwargs(settings.database_url))
    if settings.database_url
    else None
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False) if engine else None


def get_session() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with SessionLocal() as session:
        yield session
