from pathlib import Path

from alembic import command
from alembic.config import Config


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
    config = Config(str(_alembic_ini_path()))
    command.upgrade(config, "head")
