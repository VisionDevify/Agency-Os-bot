def test_model_tables_are_registered() -> None:
    from app.db.base import Base
    from app.models import Account, AuditLog, Automation, Incident, Proxy, Report, Role, Task, User

    expected = {
        "accounts",
        "audit_logs",
        "automations",
        "incidents",
        "proxies",
        "reports",
        "roles",
        "tasks",
        "user_roles",
        "users",
    }

    assert expected.issubset(Base.metadata.tables)
    assert User.__tablename__ == "users"
    assert Role.__tablename__ == "roles"
    assert AuditLog.__tablename__ == "audit_logs"
    assert "status" in AuditLog.__table__.columns
    assert Account.__tablename__ == "accounts"
    assert Proxy.__tablename__ == "proxies"
    assert Task.__tablename__ == "tasks"
    assert Incident.__tablename__ == "incidents"
    assert Report.__tablename__ == "reports"
    assert Automation.__tablename__ == "automations"
