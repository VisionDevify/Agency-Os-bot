from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite"):
        return None
    parsed = urlsplit(database_url)
    if parsed.path in {"", ":memory:"} or ":memory:" in database_url:
        return None
    path = unquote(parsed.path)
    if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return Path(path)


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "")
    source = _sqlite_path(database_url)
    if source is None:
        print("No file-backed SQLite DATABASE_URL detected. Nothing exported.")
        return 0
    if not source.exists():
        print("SQLite file does not exist. Nothing exported.")
        return 1

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination_dir = Path("outputs") / "sqlite_backups"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"fortuna_sqlite_backup_{timestamp}.db"
    shutil.copy2(source, destination)
    print(f"SQLite backup exported to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
