def test_model_tables_are_registered() -> None:
    from app.db.base import Base
    from app.models import (
        Account,
        AuditLog,
        Automation,
        Incident,
        ModelBrand,
        ModelBrandMember,
        Proxy,
        Report,
        Role,
        Task,
        User,
    )

    expected = {
        "accounts",
        "audit_logs",
        "automations",
        "incidents",
        "model_brand_members",
        "model_brands",
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
    assert ModelBrand.__tablename__ == "model_brands"
    assert ModelBrandMember.__tablename__ == "model_brand_members"
    assert Report.__tablename__ == "reports"
    assert Automation.__tablename__ == "automations"
