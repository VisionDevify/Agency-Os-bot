from datetime import UTC, datetime, timedelta

import pytest

from app.bot.navigation import screen_for_page
from app.models.learning import LearningEvent, OutcomeMemory
from app.models.opportunity import CommentStrategy
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.models.social import SocialOpportunityScore, SocialSignal, SocialSourcePerformance
from app.services.auth import setup_owner_if_needed
from app.services.notifications import create_notification_target
from app.services.opportunities import create_creator_watch
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.social_intelligence import (
    best_social_opportunities,
    best_social_sources,
    create_opportunity_from_social_score,
    create_social_post,
    create_social_source,
    engagement_strategies_for_score,
    official_api_adapter_status,
    record_social_outcome,
    route_social_opportunity_alert,
    score_social_post,
    social_notification_framework_status,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _seed_score(session, owner):
    source = create_social_source(
        session,
        actor=owner,
        platform="x",
        creator_username="fitnesscreator",
        display_name="Fitness Creator",
        niche="fitness",
        follower_tier="mid",
        watch_reason="Strong audience overlap.",
    )
    post = create_social_post(
        session,
        actor=owner,
        source=source,
        platform="x",
        post_reference="https://x.example/post/1",
        post_url="https://x.example/post/1",
        post_time=datetime.now(UTC) - timedelta(hours=1),
        niche="fitness",
        content_summary="A useful question about morning fitness habits.",
        engagement_signals={"likes": 120, "comments": 34, "shares": 12, "views": 2400},
        audience_fit=92,
        niche_match=88,
        creator_relevance=84,
        competition_level=25,
        content_quality=86,
        comment_activity_quality=91,
    )
    return source, post, score_social_post(session, post, actor=owner)


def test_social_models_score_manual_public_opportunity() -> None:
    with session_scope() as session:
        owner = _owner(session)
        source, post, score = _seed_score(session, owner)

        assert source.platform == "x"
        assert post.compliance_status == "approved"
        assert score.score >= 75
        assert score.confidence_score >= 70
        assert score.best_timing_window == "Review now"
        assert score.suggested_engagement_angle in {"curiosity", "question", "educational", "soft_cta", "supportive"}
        assert session.query(SocialSignal).filter_by(social_opportunity_score_id=score.id).count() == 1


def test_social_compliance_blocks_private_data_and_auto_posting() -> None:
    with session_scope() as session:
        owner = _owner(session)
        source = create_social_source(session, actor=owner, platform="instagram", creator_username="privatecreator")
        post = create_social_post(
            session,
            actor=owner,
            source=source,
            platform="instagram",
            post_reference="private screenshot",
            is_private_data=True,
            engagement_signals={"private_dm": "redacted"},
        )
        score = score_social_post(session, post, actor=owner)

        assert post.compliance_status == "blocked"
        assert score.score == 0
        assert "Blocked" in score.compliance_warning
        with pytest.raises(PermissionError):
            create_opportunity_from_social_score(session, score, actor=owner)
        assert official_api_adapter_status()["scraping"] == "not_supported"
        assert official_api_adapter_status()["auto_posting"] == "not_supported"


def test_social_score_creates_human_review_opportunity_and_comment_ideas() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _source, _post, score = _seed_score(session, owner)

        opportunity = create_opportunity_from_social_score(session, score, actor=owner)
        strategies = engagement_strategies_for_score(score)

        assert opportunity.id == score.opportunity_id
        assert opportunity.status in {"discovered", "reviewing"}
        assert opportunity.score == score.score
        assert "human review" in opportunity.reason.lower()
        assert session.query(CommentStrategy).filter_by(opportunity_id=opportunity.id).count() >= 3
        assert {strategy.angle for strategy in strategies} >= {"curiosity", "relatable", "question"}


def test_social_outcome_learning_updates_source_creator_and_memory() -> None:
    with session_scope() as session:
        owner = _owner(session)
        creator = create_creator_watch(
            session,
            actor=owner,
            platform="x",
            creator_name="Fitness Creator",
            creator_username="fitnesscreator",
            niche="fitness",
            watch_reason="Manual test source.",
        )
        source, _post, score = _seed_score(session, owner)
        opportunity = create_opportunity_from_social_score(session, score, actor=owner)

        performance = record_social_outcome(
            session,
            score,
            actor=owner,
            outcome="success",
            clicks=7,
            replies=2,
            profile_visits=4,
            conversions=1,
            notes="Manual result entered by owner.",
        )
        session.refresh(source)
        session.refresh(creator)

        assert performance.reviewed_count == 1
        assert performance.conversions == 1
        assert source.historical_score > 0
        assert creator.historical_score > 0
        assert creator.last_useful_post_at is not None
        assert session.query(LearningEvent).filter_by(event_type="social.outcome_recorded").count() == 1
        assert session.query(OutcomeMemory).filter(OutcomeMemory.memory_type == "opportunity_result").count() >= 1
        assert opportunity.score == score.score


def test_best_source_and_best_opportunity_ranking() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _source, _post, score = _seed_score(session, owner)

        best_scores = best_social_opportunities(session)
        record_social_outcome(session, score, actor=owner, outcome="success", clicks=12, replies=3)
        best_sources = best_social_sources(session)

        assert best_scores[0].id == score.id
        assert best_sources[0].historical_score > 0


def test_social_alert_routing_records_attempt_or_missing_target_recommendation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _source, _post, score = _seed_score(session, owner)

        attempts = route_social_opportunity_alert(session, score, actor=owner)
        assert attempts == []
        assert session.query(Recommendation).filter_by(recommendation_type="social_alert_target_missing").count() == 1

        create_notification_target(
            session,
            actor=owner,
            name="Fortuna Alerts",
            target_type="telegram_group",
            purpose="alerts",
            telegram_chat_id="123456",
        )
        attempts = route_social_opportunity_alert(session, score, actor=owner)

        assert len(attempts) == 1
        assert attempts[0].status == "skipped"
        assert session.query(NotificationDeliveryAttempt).filter_by(event_type="social.opportunity.alert").count() == 1
        assert social_notification_framework_status(session)["notification_queue_placeholder"] is True


def test_social_opportunity_dashboard_and_help_are_calm_and_manual_only() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _source, _post, score = _seed_score(session, owner)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("opportunities:score", principal, session=session, user=owner)
        strategies = screen_for_page(f"social_score:{score.id}:strategies", principal, session=session, user=owner)
        help_screen = screen_for_page("help_copilot:social opportunity intelligence", principal, session=session, user=owner)

        assert "Fortuna found 1 possible engagement opportunity" in screen.text
        assert "Next Best Move" in screen.text
        assert "Fortuna will not post" in screen.text
        assert "Human review only" in strategies.text
        assert "never post" in strategies.text
        assert "scores public opportunities" in help_screen.text
        assert "auto_posting" not in screen.text.casefold()
