from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.db.session import engine
from app.services.persistence import enforce_sqlite_fallback_policy, storage_status


def _alembic_ini_path() -> Path:
    candidates = (
        Path.cwd() / "alembic.ini",
        Path(__file__).resolve().parents[2] / "alembic.ini",
    )
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError("alembic.ini not found")


def run_migrations() -> None:
    current_storage = storage_status()
    enforce_sqlite_fallback_policy(current_storage)
    if current_storage.backend == "sqlite_fallback" and engine is not None:
        from app.db.base import Base
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        return

    config = Config(str(_alembic_ini_path()))
    command.upgrade(config, "head")
