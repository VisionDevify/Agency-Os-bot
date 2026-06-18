from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.bot.screens import render_page
from app.models.coo import PriorityItem
from app.models.incident import Incident
from app.models.model_brand import ModelBrand
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation
from app.models.task import Task
from app.models.user import User, UserAvailability
from app.services.coo import (
    chatter_work_queue,
    coo_briefing,
    generate_priority_items,
    manager_work_queue,
    readiness_score_v2,
    route_owner_for_item,
    run_coo_scan,
    score_priority,
    team_load_balancer,
    todays_top_5_actions,
)
from tests.utils import session_scope


def _owner(session) -> User:
    user = User(
        telegram_id=1001,
        display_name="Owner",
        is_owner=True,
        is_active=True,
        status="active",
        timezone="America/New_York",
    )
    session.add(user)
    session.flush()
    return user


def _active_user(session, telegram_id: int, name: str, *, timezone: str = "America/New_York") -> User:
    user = User(
        telegram_id=telegram_id,
        display_name=name,
        is_active=True,
        status="active",
        timezone=timezone,
    )
    session.add(user)
    session.flush()
    return user


def test_priority_scoring_weights_critical_and_urgent_higher() -> None:
    low = score_priority(severity="info", urgency="low", confidence=60, business_impact=30)
    high = score_priority(severity="critical", urgency="urgent", confidence=95, business_impact=100)

    assert high > low
    assert high <= 100


def test_priority_engine_creates_ranked_readiness_items() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(ModelBrand(display_name="New Model 1", status="active", is_demo=False))
        session.flush()

        priorities = generate_priority_items(session, actor=owner)

        assert priorities
        assert session.scalar(select(PriorityItem).where(PriorityItem.status == "open")) is not None
        assert any("country missing" in item.explanation for item in priorities)
        assert priorities[0].score >= priorities[-1].score


def test_owner_routing_keeps_critical_incidents_with_owner() -> None:
    with session_scope() as session:
        owner = _owner(session)
        incident = Incident(title="Critical outage", status="open", severity="critical")
        session.add(incident)
        session.flush()

        item = next(item for item in generate_priority_items(session, actor=owner) if item.category == "critical_incident")

        assert item.category == "critical_incident"
        assert route_owner_for_item(item) == "Owner"


def test_today_top_5_returns_action_paths() -> None:
    with session_scope() as session:
        owner = _owner(session)
        task = Task(
            title="Overdue launch task",
            status="open",
            priority="urgent",
            due_at=datetime.now(UTC) - timedelta(days=1),
            created_by_user_id=owner.id,
        )
        session.add(task)
        session.flush()

        actions = todays_top_5_actions(session, actor=owner)

        assert actions
        assert actions[0].score > 0
        assert actions[0].action_page.startswith(("task:", "agency_activation"))


def test_manager_queue_groups_assignment_and_overdue_work() -> None:
    with session_scope() as session:
        owner = _owner(session)
        task = Task(
            title="Assign me",
            status="open",
            priority="high",
            due_at=datetime.now(UTC) - timedelta(hours=1),
            created_by_user_id=owner.id,
        )
        opportunity = Opportunity(
            platform="x",
            title="Unassigned opportunity",
            status="reviewing",
            priority="high",
            score=75,
            is_demo=False,
        )
        session.add_all([task, opportunity])
        session.flush()

        queue = manager_work_queue(session, actor=owner)

        assert any(item["type"] == "task" for item in queue["needs_assignment"])
        assert any(item["type"] == "opportunity" for item in queue["needs_assignment"])
        assert queue["overdue"]


def test_chatter_queue_focuses_on_assigned_work() -> None:
    with session_scope() as session:
        chatter = _active_user(session, 2002, "Chatter")
        session.add(
            Task(
                title="Due today",
                status="open",
                priority="high",
                assigned_to_user_id=chatter.id,
                due_at=datetime.now(UTC),
            )
        )
        session.add(
            Opportunity(
                platform="instagram",
                title="Assigned opportunity",
                status="assigned",
                priority="normal",
                score=60,
                assigned_to_user_id=chatter.id,
                is_demo=False,
            )
        )
        session.flush()

        queue = chatter_work_queue(session, chatter)

        assert len(queue["today"]) == 1
        assert len(queue["opportunities"]) == 1
        assert queue["waiting_on_me"]


def test_readiness_v2_shows_estimated_score_gain() -> None:
    with session_scope() as session:
        _owner(session)
        session.add(ModelBrand(display_name="Incomplete Model", status="active", is_demo=False))
        session.flush()

        readiness = readiness_score_v2(session)

        assert readiness["readiness_score"] < 100
        assert readiness["fastest_path"]
        assert readiness["fastest_path"][0]["estimated_gain"] > 0


def test_coo_briefing_has_actionable_sections() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(ModelBrand(display_name="Briefing Model", status="active", is_demo=False))
        session.flush()

        briefing = coo_briefing(session, actor=owner)

        assert "what_changed" in briefing
        assert "needs_attention" in briefing
        assert "next_actions" in briefing
        assert briefing["readiness_score"] < 100


def test_team_load_balancer_detects_overloaded_and_idle_users() -> None:
    with session_scope() as session:
        overloaded = _active_user(session, 3001, "Busy")
        idle = _active_user(session, 3002, "Idle")
        session.add(UserAvailability(user_id=idle.id, status="on_shift", timezone="America/New_York"))
        for index in range(5):
            session.add(
                Task(
                    title=f"Busy task {index}",
                    status="open",
                    priority="urgent",
                    assigned_to_user_id=overloaded.id,
                    due_at=datetime.now(UTC) - timedelta(days=1),
                )
            )
        session.flush()

        load = team_load_balancer(session)

        assert any(row["name"] == "Busy" for row in load["overloaded"])
        assert any(row["name"] == "Idle" for row in load["idle"])
        assert load["recommendations"]


def test_coo_scan_creates_activation_recommendations_and_safe_ui() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _active_user(session, 4001, "New Team Member", timezone="UTC")
        session.flush()

        result = run_coo_scan(session, actor=owner)
        screen = render_page("coo:top5", session=session, user=owner)

        assert result["priorities"]
        assert session.scalar(select(Recommendation).where(Recommendation.recommendation_type == "team_activation")) is not None
        assert "{" not in screen.text
        assert "PriorityItem(" not in screen.text
