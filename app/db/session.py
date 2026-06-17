from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


engine = create_engine(normalize_database_url(settings.database_url), pool_pre_ping=True) if settings.database_url else None
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False) if engine else None


def get_session() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with SessionLocal() as session:
        yield session
