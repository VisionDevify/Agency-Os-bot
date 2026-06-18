from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.db.session import engine


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
    if settings.database_url.startswith("sqlite") and engine is not None:
        from app.db.base import Base
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        return

    config = Config(str(_alembic_ini_path()))
    command.upgrade(config, "head")
