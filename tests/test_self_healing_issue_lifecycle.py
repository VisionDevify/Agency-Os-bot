from datetime import UTC, datetime, timedelta

from app.bot.screens.errors import render_button_health_report_page, render_callback_failure_review_page
from app.models.button_issue import ButtonIssue
from app.models.callback_error import CallbackErrorLog
from app.models.recommendation import Recommendation
from app.services.auth import setup_owner_if_needed
from app.services.button_health import button_health_summary
from app.services.callbacks import callback_failure_review
from app.services.observability import production_observability_summary
from app.services.team_ux import trust_signal_summary
from tests.utils import session_scope


def _callback_error(page: str, *, created_at: datetime | None = None) -> CallbackErrorLog:
    error = CallbackErrorLog(
        callback_data=f"nav:{page}",
        page=page,
        affected_screen=page,
        exception_type="IntegrityError",
        error_message="IntegrityError table=callback_audit constraint=callback_unique",
    )
    if created_at is not None:
        error.created_at = created_at
    return error


def _callback_recommendation(page: str, *, status: str = "open") -> Recommendation:
    return Recommendation(
        recommendation_type="callback_failure",
        title="Button Needs Repair",
        description=f"Callback {page} failed and needs review.",
        severity="warning",
        entity_type="telegram_callback",
        entity_id=page,
        status=status,
        metadata_json={"source": "test"},
    )


def test_old_callback_failures_become_historical_after_successful_revalidation() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(_callback_error("coo:briefing", created_at=now - timedelta(hours=2)))
        session.add(_callback_recommendation("coo:briefing"))
        session.flush()

        review = callback_failure_review(
            session,
            working_pages=["coo:briefing"],
            failing_pages=[],
            revalidated_at=now,
            current_commit="fixed-commit",
        )
        recommendation = session.query(Recommendation).filter_by(entity_id="coo:briefing").one()

        assert review.active_items == []
        assert len(review.historical_items) == 1
        assert review.lifecycle_summary.active_count == 0
        assert review.lifecycle_summary.historical_count == 1
        assert recommendation.status == "resolved"
        assert recommendation.metadata_json["fixed_by_commit"] == "fixed-commit"


def test_new_callback_failures_stay_active_without_revalidation_success() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(_callback_error("ai_brain:coo", created_at=now + timedelta(seconds=1)))
        session.add(_callback_recommendation("ai_brain:coo"))
        session.flush()

        review = callback_failure_review(
            session,
            working_pages=[],
            failing_pages=[],
            revalidated_at=now,
            current_commit="current-commit",
        )

        assert len(review.active_items) == 1
        assert review.active_items[0].lifecycle_status == "active"
        assert review.historical_items == []


def test_failed_revalidation_marks_callback_issue_reappeared() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(_callback_error("ai_brain:evidence", created_at=now - timedelta(hours=1)))
        session.add(_callback_recommendation("ai_brain:evidence"))
        session.flush()

        review = callback_failure_review(
            session,
            working_pages=[],
            failing_pages=["ai_brain:evidence"],
            revalidated_at=now,
            current_commit="current-commit",
        )

        assert len(review.active_items) == 1
        assert review.active_items[0].lifecycle_status == "reappeared"
        assert review.lifecycle_summary.reappeared_count == 1


def test_resolved_issue_reappears_when_new_failure_occurs_after_revalidation() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        resolved = _callback_recommendation("coo:briefing", status="resolved")
        resolved.metadata_json = {
            "lifecycle_status": "resolved",
            "revalidated_at": (now - timedelta(hours=1)).isoformat(),
        }
        session.add(resolved)
        session.add(_callback_error("coo:briefing", created_at=now))
        session.flush()

        review = callback_failure_review(session, current_commit="current-commit")

        assert len(review.active_items) == 1
        assert review.active_items[0].lifecycle_status == "active"
        assert review.historical_items == []


def test_failure_without_revalidation_does_not_fake_resolution() -> None:
    with session_scope() as session:
        session.add(_callback_error("ai_brain:opportunity", created_at=datetime.now(UTC) - timedelta(days=1)))
        session.add(_callback_recommendation("ai_brain:opportunity"))
        session.flush()

        review = callback_failure_review(session, working_pages=[], failing_pages=[])

        assert review.historical_items == []
        assert len(review.validating_items) == 1
        assert session.query(Recommendation).filter_by(entity_id="ai_brain:opportunity").one().status == "open"


def test_button_health_ignores_resolved_issues_in_active_count() -> None:
    with session_scope() as session:
        session.add(
            ButtonIssue(
                screen="coo:briefing",
                button_label="COO Briefing",
                callback_data="nav:coo:briefing",
                issue_type="renderer_error",
                severity="high",
                status="resolved",
                evidence_summary="Historical renderer error.",
                recommended_fix="Already revalidated.",
                resolved_at=datetime.now(UTC),
            )
        )
        session.flush()

        summary = button_health_summary(session)

        assert summary.open_issue_count == 0
        assert summary.technical_issue_count == 0


def test_observability_active_count_excludes_historical_callback_recommendations() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(_callback_error("coo:briefing", created_at=now - timedelta(hours=2)))
        session.add(_callback_recommendation("coo:briefing"))
        session.flush()
        callback_failure_review(
            session,
            working_pages=["coo:briefing"],
            failing_pages=[],
            revalidated_at=now,
            current_commit="fixed-commit",
        )

        summary = production_observability_summary(session)

        assert summary["issue_lifecycle_active_callback_recommendations"] == 0
        assert not any("Callback Issue Lifecycle" in issue for issue in summary["observability_current_issues"])


def test_unresolved_callback_recommendation_remains_observable() -> None:
    with session_scope() as session:
        session.add(_callback_error("ai_brain:coo", created_at=datetime.now(UTC)))
        session.add(_callback_recommendation("ai_brain:coo"))
        session.flush()

        summary = production_observability_summary(session)

        assert summary["issue_lifecycle_active_callback_recommendations"] == 1
        assert any("Callback Issue Lifecycle" in issue for issue in summary["observability_current_issues"])


def test_team_ux_does_not_count_resolved_callback_history_as_active_trust_issue() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(_callback_error("coo:briefing", created_at=now - timedelta(minutes=30)))
        session.add(_callback_recommendation("coo:briefing"))
        session.flush()
        callback_failure_review(
            session,
            working_pages=["coo:briefing"],
            failing_pages=[],
            revalidated_at=now,
            current_commit="fixed-commit",
        )

        trust = trust_signal_summary(session)

        assert trust.callback_failures == 0


def test_callback_failure_review_screen_separates_historical_from_active() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        session.add(_callback_error("coo:briefing", created_at=now - timedelta(hours=2)))
        session.add(_callback_recommendation("coo:briefing"))
        session.flush()
        callback_failure_review(
            session,
            working_pages=["coo:briefing"],
            failing_pages=[],
            revalidated_at=now,
            current_commit="fixed-commit",
        )

        screen = render_callback_failure_review_page(session, owner)

        assert "No new callback failures since latest deployment" in screen.text
        assert "Historical Fixed Issues:" in screen.text
        assert "Active Failures:" in screen.text


def test_button_health_details_reports_historical_callback_errors_without_active_alert() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        session.add(_callback_error("menu", created_at=now - timedelta(hours=2)))
        session.add(_callback_recommendation("menu"))
        session.flush()

        screen = render_button_health_report_page(session, owner, details=True)

        assert "Active callback errors: 0" in screen.text
        assert "Historical fixed callback errors:" in screen.text
        assert "Historical Fixed Issues:" in screen.text
