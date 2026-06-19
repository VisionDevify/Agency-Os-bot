from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.bot.screens import render_production_observability_page
from app.core.config import settings
from app.models.autonomous_operations import FollowUp
from app.models.coo import PriorityItem
from app.models.intelligence import IntelligenceSignal, IssuePattern
from app.models.recommendation import Recommendation
from app.services.auth import setup_owner_if_needed
from app.services.bot_instances import record_bot_instance_heartbeat
from app.services.heartbeats import record_heartbeat
from app.services.system_truth import (
    expected_alembic_head,
    reconcile_stale_system_warnings,
    system_truth,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _healthy_truth_state(session, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setattr(settings, "bot_instance_id", "primary-instance")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    session.execute(text("create table alembic_version (version_num varchar(64) not null)"))
    session.execute(text("insert into alembic_version (version_num) values (:head)"), {"head": expected_alembic_head()})
    record_heartbeat(session, service_name="api", status="healthy", metadata={"source": "test"})
    record_heartbeat(session, service_name="db", status="healthy", metadata={"source": "test", "backend": "postgresql"})
    record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "test"})
    record_heartbeat(
        session,
        service_name="bot",
        status="healthy",
        metadata={"polling_guard": "redis_lock", "redis_lock_status": "held"},
    )
    record_bot_instance_heartbeat(session, instance_id="primary-instance")


def test_system_truth_reports_postgresql_redis_healthy(monkeypatch) -> None:
    with session_scope() as session:
        _healthy_truth_state(session, monkeypatch)
        truth = system_truth(session)

        assert truth.database_backend == "postgresql"
        assert truth.database_durable is True
        assert truth.database_ready is True
        assert truth.redis_healthy is True
        assert truth.bot_instance_count == 1
        assert truth.duplicate_bot_instance_count == 0
        assert truth.migrations_current is True
        assert truth.production_ready is True


def test_observability_does_not_show_storage_warning_when_truth_is_healthy(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        _healthy_truth_state(session, monkeypatch)

        screen = render_production_observability_page(session, owner)
        details = render_production_observability_page(session, owner, details=True)

        assert "Production Status" in screen.text
        assert "Recovery" in screen.text
        assert "PostgreSQL is durable" in screen.text
        assert "Redis is healthy" in screen.text
        assert "One bot instance is active" in screen.text
        assert "Migrations are current" in screen.text
        assert "Storage is not production-ready" not in screen.text
        assert "sqlite_fallback" not in screen.text
        assert "storage_not_production_ready" not in screen.text
        assert "Risk: Production Ready" in details.text
        assert "Current Truth Issues: None" in details.text


def test_stale_storage_sqlite_duplicate_and_proxy_warnings_auto_resolve(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        _healthy_truth_state(session, monkeypatch)
        now = datetime.now(UTC)
        recommendation = Recommendation(
            recommendation_type="storage_not_production_ready",
            title="Storage is not production-ready",
            description="Old SQLite fallback warning.",
            severity="critical",
            status="open",
            metadata_json={"db_backend": "sqlite_fallback"},
        )
        duplicate_recommendation = Recommendation(
            recommendation_type="duplicate_bot_polling",
            title="Duplicate polling warning",
            description="Old duplicate bot instance warning.",
            severity="warning",
            status="acknowledged",
            metadata_json={},
        )
        proxy_recommendation = Recommendation(
            recommendation_type="placeholder_proxy",
            title="Placeholder proxies visible",
            description="Old placeholder proxy warning.",
            severity="warning",
            status="open",
            metadata_json={},
        )
        priority = PriorityItem(
            source_type="system",
            source_id="storage",
            category="production_instability",
            severity="critical",
            urgency="urgent",
            confidence=90,
            business_impact=90,
            score=90,
            explanation="Production instability from old SQLite fallback.",
            recommended_owner="Owner",
            status="open",
        )
        signal = IntelligenceSignal(
            signal_type="production_instability",
            severity="critical",
            title="Production instability",
            description="Historical production issue.",
            confidence_score=90,
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            status="open",
            metadata_json={},
        )
        pattern = IssuePattern(
            pattern_type="production_instability",
            title="Production instability",
            description="Historical production pattern.",
            severity="critical",
            confidence_score=90,
            occurrence_count=1,
            related_event_ids_json=[],
            suggested_action="Inspect production.",
            status="active",
            first_seen_at=now,
            last_seen_at=now,
        )
        follow_up = FollowUp(
            source_type="sqlite_fallback",
            source_id="storage",
            due_at=now + timedelta(days=1),
            status="pending",
        )
        session.add_all([recommendation, duplicate_recommendation, proxy_recommendation, priority, signal, pattern, follow_up])
        session.flush()

        result = reconcile_stale_system_warnings(session, actor=owner)

        assert result["recommendations"] == 3
        assert result["priority_items"] == 1
        assert result["intelligence_signals"] == 1
        assert result["issue_patterns"] == 1
        assert result["follow_ups"] == 1
        assert recommendation.status == "resolved"
        assert duplicate_recommendation.status == "resolved"
        assert proxy_recommendation.status == "resolved"
        assert priority.status == "resolved"
        assert signal.status == "resolved"
        assert pattern.status == "resolved"
        assert follow_up.status == "completed"


def test_historical_production_issue_does_not_appear_as_active_current_health(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        _healthy_truth_state(session, monkeypatch)
        now = datetime.now(UTC)
        session.add(
            IntelligenceSignal(
                signal_type="production_instability",
                severity="warning",
                title="Production instability",
                description="This happened before.",
                confidence_score=80,
                first_seen_at=now,
                last_seen_at=now,
                occurrence_count=2,
                status="open",
                metadata_json={},
            )
        )
        session.flush()

        screen = render_production_observability_page(session, owner)

        assert "Production instability" not in screen.text
        assert "Operations are running" in screen.text
        assert session.query(IntelligenceSignal).one().status == "resolved"
