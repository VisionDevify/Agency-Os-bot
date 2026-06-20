def test_model_tables_are_registered() -> None:
    from app.db.base import Base
    from app.models import (
        Account,
        AccountabilitySnapshot,
        AuditLog,
        CallbackErrorLog,
        Automation,
        AutomationApproval,
        AutomationRule,
        AutomationRun,
        AutomationRunStep,
        AutomationSchedule,
        AutomationSimulationRun,
        BackupRun,
        BackupStorageTarget,
        CommentStrategy,
        ConfidenceRecord,
        CreatorWatch,
        Incident,
        AccountAuthSession,
        AccountVerificationCode,
        ActivationBlockerDecision,
        DailyBriefing,
        DailyAutopilotSetting,
        DecisionMemory,
        EventLog,
        ExecutiveInsight,
        FrictionItem,
        IntelligenceRun,
        IntelligenceSignal,
        IssuePattern,
        LearningEvent,
        ModelBrand,
        ModelBrandMember,
        NotificationDigest,
        NotificationTarget,
        Opportunity,
        OpportunityPrediction,
        OpportunityResult,
        OpportunitySource,
        OutcomeMemory,
        Playbook,
        PlaybookRun,
        PostWatch,
        Proxy,
        ProxyHealthCheckResult,
        ProxyRotationHistory,
        Recommendation,
        Report,
        RestoreTestRun,
        Role,
        SocialDiscoveryLead,
        SocialDiscoveryRun,
        SocialDiscoverySourceConfig,
        SystemHeartbeat,
        Task,
        TeamPerformanceSnapshot,
        TeamOnboardingChecklist,
        TrendSnapshot,
        User,
        WorkloadSnapshot,
    )

    expected = {
        "accounts",
        "account_auth_sessions",
        "account_verification_codes",
        "accountability_snapshots",
        "activation_blocker_decisions",
        "audit_logs",
        "callback_error_logs",
        "automations",
        "automation_approvals",
        "automation_rules",
        "automation_runs",
        "automation_run_steps",
        "automation_schedules",
        "automation_simulation_runs",
        "backup_runs",
        "backup_storage_targets",
        "comment_strategies",
        "creator_watches",
        "daily_briefings",
        "daily_autopilot_settings",
        "decision_memory",
        "event_logs",
        "executive_insights",
        "friction_items",
        "incidents",
        "intelligence_runs",
        "intelligence_signals",
        "issue_patterns",
        "confidence_records",
        "learning_events",
        "model_brand_members",
        "model_brands",
        "notification_targets",
        "notification_digests",
        "opportunities",
        "opportunity_predictions",
        "opportunity_results",
        "opportunity_sources",
        "outcome_memory",
        "playbook_runs",
        "playbooks",
        "post_watches",
        "proxies",
        "proxy_health_check_results",
        "proxy_rotation_history",
        "recommendations",
        "reports",
        "restore_test_runs",
        "roles",
        "social_discovery_leads",
        "social_discovery_runs",
        "social_discovery_source_configs",
        "system_heartbeats",
        "tasks",
        "team_performance_snapshots",
        "team_onboarding_checklists",
        "trend_snapshots",
        "user_roles",
        "users",
        "workload_snapshots",
    }

    assert expected.issubset(Base.metadata.tables)
    assert User.__tablename__ == "users"
    assert Role.__tablename__ == "roles"
    assert AuditLog.__tablename__ == "audit_logs"
    assert "status" in AuditLog.__table__.columns
    assert EventLog.__tablename__ == "event_logs"
    assert DecisionMemory.__tablename__ == "decision_memory"
    assert FrictionItem.__tablename__ == "friction_items"
    assert CallbackErrorLog.__tablename__ == "callback_error_logs"
    assert DailyBriefing.__tablename__ == "daily_briefings"
    assert AccountabilitySnapshot.__tablename__ == "accountability_snapshots"
    assert ActivationBlockerDecision.__tablename__ == "activation_blocker_decisions"
    assert DailyAutopilotSetting.__tablename__ == "daily_autopilot_settings"
    assert NotificationTarget.__tablename__ == "notification_targets"
    assert NotificationDigest.__tablename__ == "notification_digests"
    assert Account.__tablename__ == "accounts"
    assert AccountAuthSession.__tablename__ == "account_auth_sessions"
    assert AccountVerificationCode.__tablename__ == "account_verification_codes"
    assert "auth_status" in Account.__table__.columns
    assert Proxy.__tablename__ == "proxies"
    assert ProxyHealthCheckResult.__tablename__ == "proxy_health_check_results"
    assert ProxyRotationHistory.__tablename__ == "proxy_rotation_history"
    assert "encrypted_password" in Proxy.__table__.columns
    assert "assigned_proxy_id" in Account.__table__.columns
    assert Task.__tablename__ == "tasks"
    assert Incident.__tablename__ == "incidents"
    assert "title" in Incident.__table__.columns
    assert ModelBrand.__tablename__ == "model_brands"
    assert ModelBrandMember.__tablename__ == "model_brand_members"
    assert Report.__tablename__ == "reports"
    assert SocialDiscoverySourceConfig.__tablename__ == "social_discovery_source_configs"
    assert SocialDiscoveryRun.__tablename__ == "social_discovery_runs"
    assert SocialDiscoveryLead.__tablename__ == "social_discovery_leads"
    assert Automation.__tablename__ == "automations"
    assert AutomationRule.__tablename__ == "automation_rules"
    assert AutomationRun.__tablename__ == "automation_runs"
    assert AutomationRunStep.__tablename__ == "automation_run_steps"
    assert AutomationApproval.__tablename__ == "automation_approvals"
    assert AutomationSchedule.__tablename__ == "automation_schedules"
    assert AutomationSimulationRun.__tablename__ == "automation_simulation_runs"
    assert BackupRun.__tablename__ == "backup_runs"
    assert BackupStorageTarget.__tablename__ == "backup_storage_targets"
    assert RestoreTestRun.__tablename__ == "restore_test_runs"
    assert Recommendation.__tablename__ == "recommendations"
    assert SystemHeartbeat.__tablename__ == "system_heartbeats"
    assert IntelligenceSignal.__tablename__ == "intelligence_signals"
    assert IssuePattern.__tablename__ == "issue_patterns"
    assert TrendSnapshot.__tablename__ == "trend_snapshots"
    assert WorkloadSnapshot.__tablename__ == "workload_snapshots"
    assert ExecutiveInsight.__tablename__ == "executive_insights"
    assert IntelligenceRun.__tablename__ == "intelligence_runs"
    assert LearningEvent.__tablename__ == "learning_events"
    assert Playbook.__tablename__ == "playbooks"
    assert PlaybookRun.__tablename__ == "playbook_runs"
    assert OutcomeMemory.__tablename__ == "outcome_memory"
    assert ConfidenceRecord.__tablename__ == "confidence_records"
    assert OpportunitySource.__tablename__ == "opportunity_sources"
    assert Opportunity.__tablename__ == "opportunities"
    assert OpportunityPrediction.__tablename__ == "opportunity_predictions"
    assert OpportunityResult.__tablename__ == "opportunity_results"
    assert CreatorWatch.__tablename__ == "creator_watches"
    assert PostWatch.__tablename__ == "post_watches"
    assert CommentStrategy.__tablename__ == "comment_strategies"
    assert TeamOnboardingChecklist.__tablename__ == "team_onboarding_checklists"
    assert TeamPerformanceSnapshot.__tablename__ == "team_performance_snapshots"
