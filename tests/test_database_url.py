from app.db.session import _engine_kwargs, normalize_database_url


def test_plain_postgres_url_uses_psycopg_driver() -> None:
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == (
        "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_driver_specific_database_url_is_preserved() -> None:
    assert normalize_database_url("postgresql+psycopg://user:pass@host:5432/db") == (
        "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_postgres_engine_uses_bounded_connection_timeouts() -> None:
    kwargs = _engine_kwargs("postgresql://user:pass@host:5432/db")

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_timeout"] == 5
    assert kwargs["connect_args"]["connect_timeout"] == 5
