from datetime import UTC, datetime, timedelta

from app.bot.navigation import screen_for_page
from app.models.event_log import EventLog
from app.models.incident import Incident
from app.models.intelligence import (
    ExecutiveInsight,
    IntelligenceRun,
    IntelligenceSignal,
    IssuePattern,
    TrendSnapshot,
    WorkloadSnapshot,
)
from app.models.opportunity import Opportunity, OpportunityResult
from app.models.proxy import Proxy
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.services.auth import USER_STATUS_ACTIVE, get_or_create_telegram_user, setup_owner_if_needed
from app.services.incidents import create_incident
from app.services.intelligence import (
    analyze_workload,
    calculate_workload_score,
    create_or_update_signal,
    detect_patterns,
    generate_executive_intelligence_briefing,
    generate_intelligence_recommendations,
    recommendation_why,
    record_trend_snapshot,
    run_intelligence_analysis,
)
from app.services.notifications import create_notification_target
from app.services.opportunities import (
    assign_opportunity,
    create_manual_opportunity,
    record_opportunity_result,
    score_opportunity,
)
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.tasks import create_task
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)


def _active_user(session, telegram_id: int = 900, display_name: str = "Ops User"):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    session.flush()
    return user


def _proxy(session) -> Proxy:
    proxy = Proxy(
        provider="Provider",
        host="127.0.0.1",
        port=8000,
        base_username="base",
        session_suffix="session_test",
        previous_session_suffix=None,
        encrypted_password="[encrypted]",
        generated_username="base-session_test",
        status="critical",
        health_score=20,
        target_country="US",
        target_state="Florida",
    )
    session.add(proxy)
    session.flush()
    return proxy


def test_intelligence_signal_creation_redacts_safe_metadata() -> None:
    with session_scope() as session:
        owner = _owner(session)

        signal = create_or_update_signal(
            session,
            actor=owner,
            signal_type="test_signal",
            title="Sensitive Signal",
            description="Metadata should be safe.",
            severity="warning",
            entity_type="system",
            entity_id="test",
            metadata={"token": "secret-token", "code": "123456", "safe": "visible"},
        )

        assert signal.metadata_json["token"] == "[redacted]"
        assert signal.metadata_json["code"] == "[redacted]"
        assert signal.metadata_json["safe"] == "visible"
        assert session.query(IntelligenceSignal).count() == 1


def test_pattern_detection_recurring_proxy_failure_creates_artifacts() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = _proxy(session)
        for _ in range(3):
            session.add(
                EventLog(
                    event_type="proxy.repair.failed",
                    actor_user_id=owner.id,
                    entity_type="proxy",
                    entity_id=str(proxy.id),
                    metadata_json={"safe": "yes"},
                    created_at=datetime.now(UTC),
                )
            )
        session.flush()

        detect_patterns(session, actor=owner)

        signal = session.query(IntelligenceSignal).filter_by(signal_type="recurring_proxy_failures").one()
        pattern = session.query(IssuePattern).filter_by(pattern_type="recurring_proxy_failures").one()
        recommendation = session.query(Recommendation).filter_by(recommendation_type="replace_rotate_proxy").one()

        assert signal.severity == "critical"
        assert pattern.occurrence_count == 3
        assert recommendation.metadata_json["source_signal_ids"] == [signal.id]


def test_incident_recurrence_pattern_detected() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = _proxy(session)
        create_incident(session, actor=owner, title="Proxy issue one", severity="critical", source_type="proxy", proxy=proxy)
        create_incident(session, actor=owner, title="Proxy issue two", severity="warning", source_type="proxy", proxy=proxy)

        detect_patterns(session, actor=owner)

        pattern = session.query(IssuePattern).filter_by(pattern_type="incident_recurrence").one()
        assert pattern.entity_type == "proxy"
        assert pattern.entity_id == str(proxy.id)


def test_trend_snapshot_and_negative_trend_signal() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            TrendSnapshot(
                snapshot_date=datetime.now(UTC).date() - timedelta(days=1),
                metric_name="critical_incidents",
                value_numeric=1,
                comparison_window="daily",
                trend_direction="flat",
                metadata_json={},
                created_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        session.flush()

        snapshot = record_trend_snapshot(
            session,
            actor=owner,
            metric_name="critical_incidents",
            value_numeric=3,
        )

        assert snapshot.percent_change == 200
        assert snapshot.trend_direction == "volatile"
        assert session.query(IntelligenceSignal).filter_by(signal_type="negative_trend").count() == 1


def test_workload_score_overloaded_detection_and_recommendation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        assignee = _active_user(session)
        past_due = datetime.now(UTC) - timedelta(hours=2)
        create_task(session, actor=owner, title="Past due one", assigned_to=assignee, due_at=past_due)
        create_task(session, actor=owner, title="Past due two", assigned_to=assignee, due_at=past_due)
        create_incident(session, actor=owner, title="Assigned critical", severity="critical", assigned_to=assignee)

        snapshots = analyze_workload(session, actor=owner)
        snapshot = next(item for item in snapshots if item.user_id == assignee.id)

        assert calculate_workload_score(
            open_tasks=2,
            overdue_tasks=2,
            open_incidents=1,
            critical_incidents=1,
            completed_tasks_24h=0,
            resolved_incidents_24h=0,
            availability_status="off_shift",
        ) >= 90
        assert snapshot.overload_status == "critical"
        assert session.query(WorkloadSnapshot).count() >= 1
        assert session.query(Recommendation).filter_by(recommendation_type="reassign_work").count() == 1


def test_recommendation_v2_and_why_data() -> None:
    with session_scope() as session:
        owner = _owner(session)
        signal = create_or_update_signal(
            session,
            actor=owner,
            signal_type="production_instability",
            title="Production Instability",
            description="Bot heartbeat is degraded.",
            severity="critical",
            entity_type="system",
            entity_id="bot",
        )

        recommendations = generate_intelligence_recommendations(session, actor=owner)
        why = recommendation_why(recommendations[0])

        assert recommendations[0].metadata_json["source_signal_ids"] == [signal.id]
        assert why["reason"] == "Bot heartbeat is degraded."
        assert why["confidence_score"] == signal.confidence_score


def test_executive_intelligence_briefing_generation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_or_update_signal(
            session,
            actor=owner,
            signal_type="test_risk",
            title="Test Risk",
            description="Risk description.",
            severity="warning",
        )

        briefing = generate_executive_intelligence_briefing(session, actor=owner)

        assert briefing["agency_health_score"] >= 0
        assert "summary_text" in briefing
        assert session.query(ExecutiveInsight).count() == 1


def test_intelligence_run_lifecycle() -> None:
    with session_scope() as session:
        owner = _owner(session)

        run = run_intelligence_analysis(session, actor=owner, run_type="trend_analysis")

        assert run.status == "succeeded"
        assert run.finished_at is not None
        assert "trend_snapshots" in run.summary_json
        assert session.query(IntelligenceRun).count() == 1


def test_opportunity_manual_flow_no_automatic_posting_or_scraping() -> None:
    with session_scope() as session:
        owner = _owner(session)
        assignee = _active_user(session, telegram_id=901, display_name="Opportunity Owner")

        opportunity = create_manual_opportunity(
            session,
            actor=owner,
            title="Manual X audience thread",
            platform="x",
            niche="fitness",
            reason="Audience match was reviewed manually.",
            suggested_angle="Human-approved reply angle only.",
        )
        score_opportunity(session, opportunity, actor=owner)
        assign_opportunity(session, opportunity, assignee, actor=owner)
        result = record_opportunity_result(session, opportunity, actor=assignee, status="posted", notes="Posted manually.")

        assert opportunity.score > 0
        assert opportunity.assigned_to_user_id == assignee.id
        assert opportunity.status == "completed"
        assert result.status == "posted"
        assert session.query(Opportunity).count() == 1
        assert session.query(OpportunityResult).count() == 1
        assert session.query(NotificationDeliveryAttempt).count() == 0


def test_critical_signal_routes_notification_attempts() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_notification_target(
            session,
            actor=owner,
            name="HQ",
            target_type="telegram_group",
            purpose="owner",
            telegram_chat_id="-100111",
        )
        create_notification_target(
            session,
            actor=owner,
            name="Incidents",
            target_type="telegram_group",
            purpose="incidents",
            telegram_chat_id="-100222",
        )

        create_or_update_signal(
            session,
            actor=owner,
            signal_type="critical_signal_test",
            title="Critical Signal",
            description="Route this safely.",
            severity="critical",
        )

        assert session.query(NotificationDeliveryAttempt).count() == 2


def test_telegram_intelligence_and_opportunity_callbacks_do_not_crash() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        intelligence = screen_for_page("intelligence", principal, session=session, user=owner)
        run_screen = screen_for_page("intelligence:run:trend_analysis", principal, session=session, user=owner)
        opportunity = screen_for_page("opportunities:add", principal, session=session, user=owner)
        recommendation = screen_for_page("reports:executive:recommendations", principal, session=session, user=owner)

        assert "Fortuna Insights" in intelligence.text
        assert "Intelligence Runs" in run_screen.text
        assert "Opportunity" in opportunity.text
        assert "Start Here" in recommendation.text
