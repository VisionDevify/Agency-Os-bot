from datetime import UTC, datetime

from app.bot.navigation import screen_for_page
from app.bot.screens import render_main_menu
from app.models.learning import ConfidenceRecord, LearningEvent, OutcomeMemory
from app.models.recommendation import Recommendation
from app.models.social import SocialSourcePerformance
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.fortuna_personality import dynamic_greeting, screen_lines
from app.services.help_brain import help_brain_answer
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.social_intelligence import (
    comment_angles_for_discovery_lead,
    create_opportunity_from_discovery_lead,
    create_social_discovery_lead,
    create_social_discovery_run,
    create_social_discovery_source_config,
    create_social_source,
    rank_social_opportunity_leads,
    record_social_discovery_lead_feedback,
    route_social_discovery_lead_alert,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def test_dynamic_greeting_uses_user_timezone_and_no_moon_for_morning() -> None:
    with session_scope() as session:
        owner = _owner(session)
        owner.timezone = "America/New_York"

        morning = dynamic_greeting(owner, now=datetime(2026, 6, 19, 13, 0, tzinfo=UTC))
        evening = dynamic_greeting(owner, now=datetime(2026, 6, 19, 23, 0, tzinfo=UTC))

        assert morning.text == "Good Morning, Rex"
        assert morning.emoji == "\U0001f305"
        assert morning.emoji != "\U0001f319"
        assert evening.text == "Good Evening, Rex"


def test_visual_hierarchy_blocks_render_status_noticed_and_next_move() -> None:
    lines = screen_lines(
        header="Discovery Mode",
        header_emoji="?",
        status="No discovery sources connected yet.",
        noticed=["Manual public inputs only.", "No auto-posting."],
        next_move="Paste a public post URL.",
    )
    text = "\n".join(lines)

    assert "Status" in text
    assert "Fortuna Noticed" in text
    assert "Next Best Move" in text
    assert text.index("Status") < text.index("Fortuna Noticed") < text.index("Next Best Move")


def test_team_role_homes_are_simple_and_have_no_advanced_systems() -> None:
    with session_scope() as session:
        owner = _owner(session)
        manager = get_or_create_telegram_user(session, telegram_user_id=47, display_name="Mia")
        chatter = get_or_create_telegram_user(session, telegram_user_id=48, display_name="Chris")
        va = get_or_create_telegram_user(session, telegram_user_id=49, display_name="Val")
        for user in (manager, chatter, va):
            user.status = USER_STATUS_ACTIVE
            user.is_active = True
        assign_role_to_user(session, manager, RoleName.MANAGER, actor=owner)
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        assign_role_to_user(session, va, RoleName.VA, actor=owner)

        manager_screen = render_main_menu(session, manager)
        chatter_screen = render_main_menu(session, chatter)
        va_screen = render_main_menu(session, va)

        assert "Manager Home" in manager_screen.text
        assert "My Work" in chatter_screen.text
        assert "VA Tasks" in va_screen.text
        combined = "\n".join([manager_screen.text, chatter_screen.text, va_screen.text]).casefold()
        assert "automation" not in combined
        assert "observability" not in combined
        assert "callback" not in combined


def test_discovery_mode_empty_screen_is_simple_and_manual_only() -> None:
    with session_scope() as session:
        owner = _owner(session)

        screen = screen_for_page("opportunities:discovery", _principal(owner), session=session, user=owner)

        assert "Discovery Mode" in screen.text
        assert "No discovery sources connected yet" in screen.text
        assert "Next Best Move" in screen.text
        assert "No scraping" in screen.text
        assert "No auto-posting" in screen.text
        assert "metadata_json" not in screen.text
        assert "source_type" not in screen.text


def test_social_discovery_lead_ranking_conversion_and_learning() -> None:
    with session_scope() as session:
        owner = _owner(session)
        source = create_social_source(
            session,
            actor=owner,
            platform="x",
            creator_username="fitcreator",
            display_name="Fit Creator",
            niche="fitness",
            watch_reason="Strong manual test source.",
        )
        config = create_social_discovery_source_config(
            session,
            actor=owner,
            platform="x",
            name="Fitness manual watch",
            niche="fitness",
        )
        run = create_social_discovery_run(session, actor=owner, run_type="manual_source", source_config=config)
        lead = create_social_discovery_lead(
            session,
            actor=owner,
            platform="x",
            source_name="Fit Creator",
            post_reference="https://x.example/post/47",
            niche="fitness",
            reason_found="Active niche conversation with strong timing match.",
            confidence_score=86,
            recommended_angle="curiosity",
            discovery_run=run,
            social_source=source,
        )

        ranked = rank_social_opportunity_leads(session)
        opportunity = create_opportunity_from_discovery_lead(session, lead, actor=owner)

        assert ranked[0].id == lead.id
        assert lead.status == "converted_to_opportunity"
        assert opportunity.score == lead.opportunity_score
        assert "human review" in opportunity.reason.lower()
        assert session.query(LearningEvent).filter_by(event_type="social_discovery.lead_converted").count() == 1
        assert session.query(OutcomeMemory).filter(OutcomeMemory.memory_type == "opportunity_result").count() >= 1
        assert session.query(ConfidenceRecord).filter_by(subject_type="opportunity").count() >= 1
        assert session.query(SocialSourcePerformance).count() == 1


def test_comment_angles_are_safe_human_review_only() -> None:
    with session_scope() as session:
        owner = _owner(session)
        lead = create_social_discovery_lead(
            session,
            actor=owner,
            platform="instagram",
            source_name="Lifestyle Page",
            niche="lifestyle",
            reason_found="Manual public post with active conversation.",
        )

        strategies = comment_angles_for_discovery_lead(lead)
        text = " ".join(strategy.sample for strategy in strategies).casefold()
        screen = screen_for_page(f"social_lead:{lead.id}:angles", _principal(owner), session=session, user=owner)

        assert {strategy.angle for strategy in strategies} >= {"curiosity", "relatable", "playful", "question", "soft CTA"}
        assert "auto" not in text
        assert "password" not in text
        assert "No auto-posting" in screen.text
        assert "Human approval only" in screen.text


def test_discovery_feedback_updates_learning_confidence_and_source_performance() -> None:
    with session_scope() as session:
        owner = _owner(session)
        source = create_social_source(session, actor=owner, platform="x", creator_username="sourcepage", niche="fitness")
        lead = create_social_discovery_lead(
            session,
            actor=owner,
            platform="x",
            source_name="Source Page",
            niche="fitness",
            social_source=source,
        )

        record_social_discovery_lead_feedback(session, lead, actor=owner, status="skipped", notes="Not relevant today.")

        assert lead.status == "skipped"
        assert session.query(LearningEvent).filter_by(event_type="social_discovery.lead_skipped").count() == 1
        assert session.query(OutcomeMemory).filter(OutcomeMemory.memory_type == "opportunity_result").count() >= 1
        assert session.query(ConfidenceRecord).filter_by(subject_id=f"discovery_lead:{lead.id}").count() == 1
        assert session.query(SocialSourcePerformance).one().skipped_count == 1


def test_missing_alert_target_simulates_delivery_and_creates_recommendation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        lead = create_social_discovery_lead(
            session,
            actor=owner,
            platform="x",
            source_name="No Target Lead",
            reason_found="Active niche conversation.",
            confidence_score=80,
        )

        attempts = route_social_discovery_lead_alert(session, lead, actor=owner)

        assert attempts == []
        assert (
            session.query(Recommendation)
            .filter_by(recommendation_type="social_discovery_alert_target_missing")
            .count()
            == 1
        )


def test_help_brain_explains_discovery_mode_and_compliance_boundaries() -> None:
    with session_scope() as session:
        owner = _owner(session)

        discovery = help_brain_answer(session, owner, question="What is Discovery Mode?")
        posting = help_brain_answer(session, owner, question="Does Fortuna post automatically?")
        public_post = help_brain_answer(session, owner, question="How do I add a public post?")
        learning = help_brain_answer(session, owner, question="How does Fortuna learn?")
        angles = help_brain_answer(session, owner, question="What are comment angles?")
        compliance = help_brain_answer(session, owner, question="What is safe and compliant?")

        assert discovery.next_action == "opportunities:discovery"
        assert "does not scrape private data" in discovery.answer
        assert "does not auto-post" in posting.answer.lower() or "does not auto" in posting.answer.lower()
        assert public_post.next_action == "opportunities:discovery:paste_post"
        assert "manual outcomes" in learning.answer or "manual results" in learning.answer
        assert "human reviews" in angles.answer or "human-reviewed" in angles.answer
        assert "no automatic" in compliance.answer.lower()
