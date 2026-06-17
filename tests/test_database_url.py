from app.db.session import normalize_database_url


def test_plain_postgres_url_uses_psycopg_driver() -> None:
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == (
        "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_driver_specific_database_url_is_preserved() -> None:
    assert normalize_database_url("postgresql+psycopg://user:pass@host:5432/db") == (
        "postgresql+psycopg://user:pass@host:5432/db"
    )
