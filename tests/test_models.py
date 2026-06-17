def test_model_tables_are_registered() -> None:
    from app.db.base import Base
    from app.models import (
        Account,
        AccountabilitySnapshot,
        AuditLog,
        Automation,
        AutomationRule,
        AutomationSimulationRun,
        Incident,
        AccountAuthSession,
        AccountVerificationCode,
        DailyBriefing,
        EventLog,
        ModelBrand,
        ModelBrandMember,
        NotificationTarget,
        Proxy,
        ProxyRotationHistory,
        Recommendation,
        Report,
        Role,
        SystemHeartbeat,
        Task,
        User,
    )

    expected = {
        "accounts",
        "account_auth_sessions",
        "account_verification_codes",
        "accountability_snapshots",
        "audit_logs",
        "automations",
        "automation_rules",
        "automation_simulation_runs",
        "daily_briefings",
        "event_logs",
        "incidents",
        "model_brand_members",
        "model_brands",
        "notification_targets",
        "proxies",
        "proxy_rotation_history",
        "recommendations",
        "reports",
        "roles",
        "system_heartbeats",
        "tasks",
        "user_roles",
        "users",
    }

    assert expected.issubset(Base.metadata.tables)
    assert User.__tablename__ == "users"
    assert Role.__tablename__ == "roles"
    assert AuditLog.__tablename__ == "audit_logs"
    assert "status" in AuditLog.__table__.columns
    assert EventLog.__tablename__ == "event_logs"
    assert DailyBriefing.__tablename__ == "daily_briefings"
    assert AccountabilitySnapshot.__tablename__ == "accountability_snapshots"
    assert NotificationTarget.__tablename__ == "notification_targets"
    assert Account.__tablename__ == "accounts"
    assert AccountAuthSession.__tablename__ == "account_auth_sessions"
    assert AccountVerificationCode.__tablename__ == "account_verification_codes"
    assert "auth_status" in Account.__table__.columns
    assert Proxy.__tablename__ == "proxies"
    assert ProxyRotationHistory.__tablename__ == "proxy_rotation_history"
    assert "encrypted_password" in Proxy.__table__.columns
    assert "assigned_proxy_id" in Account.__table__.columns
    assert Task.__tablename__ == "tasks"
    assert Incident.__tablename__ == "incidents"
    assert "title" in Incident.__table__.columns
    assert ModelBrand.__tablename__ == "model_brands"
    assert ModelBrandMember.__tablename__ == "model_brand_members"
    assert Report.__tablename__ == "reports"
    assert Automation.__tablename__ == "automations"
    assert AutomationRule.__tablename__ == "automation_rules"
    assert AutomationSimulationRun.__tablename__ == "automation_simulation_runs"
    assert Recommendation.__tablename__ == "recommendations"
    assert SystemHeartbeat.__tablename__ == "system_heartbeats"
