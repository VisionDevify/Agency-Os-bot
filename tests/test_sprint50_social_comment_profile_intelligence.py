import pytest

from app.bot.navigation import screen_for_page
from app.models.learning import ConfidenceRecord, LearningEvent
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation
from app.models.social import SocialComplianceLog, SocialEvent, SocialCommentProfile
from app.services.auth import setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.social_alert_engine import route_profile_lead_alert
from app.services.social_comment_intelligence import analyze_comment, ingest_comment
from app.services.social_compliance import compliance_gate
from app.services.social_evaluation import rank_social_comment_profiles, score_social_comment_profile
from app.services.social_opportunity_engine import convert_profile_lead
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _seed_profile(session, owner):
    first = ingest_comment(
        session,
        actor=owner,
        platform="x",
        post_reference="https://x.example/post/50",
        author_username="profilelead",
        author_profile_url="https://x.example/profilelead",
        comment_text="This is the useful part nobody talks about. How did you test it?",
        like_count=18,
        reply_count=4,
        niche="fitness",
    )
    analyze_comment(session, first, actor=owner, niche="fitness")
    second = ingest_comment(
        session,
        actor=owner,
        platform="x",
        post_reference="https://x.example/post/51",
        author_username="profilelead",
        author_profile_url="https://x.example/profilelead",
        comment_text="Same problem here. Curious how this compares with the usual advice?",
        like_count=12,
        reply_count=3,
        niche="fitness",
    )
    analyze_comment(session, second, actor=owner, niche="fitness")
    return session.query(SocialCommentProfile).filter_by(username="profilelead").one()


def test_central_compliance_gate_blocks_unsupported_and_logs_standard_event() -> None:
    with session_scope() as session:
        owner = _owner(session)
        result = compliance_gate(
            session,
            entity_type="social_comment_profile",
            entity_id="manual-test",
            action="rank",
            source_method="private_scrape",
            compliance_status="approved",
            actor=owner,
            evidence={"summary": "blocked test"},
        )

        assert result.allowed is False
        assert result.status == "blocked"
        log = session.get(SocialComplianceLog, result.compliance_log_id)
        assert log is not None
        assert log.validation_outcome == "unsupported_source"
        event = session.query(SocialEvent).filter_by(event_type="social.compliance.blocked").one()
        assert event.event_category == "compliance"
        assert event.source_module == "compliance"


def test_missing_compliance_status_needs_review_and_cannot_rank() -> None:
    with session_scope() as session:
        owner = _owner(session)
        profile = SocialCommentProfile(
            platform="x",
            username="needsreview",
            source_method="manual",
            compliance_status="needs_review",
            observed_comment_count=3,
            avg_comment_quality=70,
            avg_engagement=65,
            potential_value_score=72,
        )
        session.add(profile)
        session.flush()

        with pytest.raises(PermissionError):
            score_social_comment_profile(session, profile, actor=owner)
        assert rank_social_comment_profiles(session, actor=owner) == []


def test_comment_ingestion_analysis_creates_profile_observation_and_evidence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        profile = _seed_profile(session, owner)

        assert profile.observed_comment_count == 2
        assert profile.repeated_appearance_count == 1
        assert profile.avg_comment_quality > 0
        assert profile.avg_engagement > 0
        assert profile.potential_value_score > 0
        assert session.query(SocialEvent).filter_by(event_type="social.comment.analyzed").count() == 2
        assert session.query(SocialEvent).filter_by(event_type="social.profile.observation_created").count() == 2


def test_non_compliant_profile_cannot_convert_or_alert() -> None:
    with session_scope() as session:
        owner = _owner(session)
        profile = SocialCommentProfile(
            platform="x",
            username="blockedlead",
            source_method="unauthorized_scrape",
            compliance_status="blocked",
            observed_comment_count=5,
            avg_comment_quality=80,
            avg_engagement=80,
            potential_value_score=90,
        )
        session.add(profile)
        session.flush()

        with pytest.raises(PermissionError):
            convert_profile_lead(session, profile, actor=owner)
        assert route_profile_lead_alert(session, profile, actor=owner) == []
        assert session.query(Opportunity).count() == 0
        assert session.query(SocialEvent).filter_by(event_type="social.alert.blocked").count() == 1


def test_profile_lead_conversion_and_learning_are_human_review_only() -> None:
    with session_scope() as session:
        owner = _owner(session)
        profile = _seed_profile(session, owner)

        opportunity = convert_profile_lead(session, profile, actor=owner)

        assert opportunity.title == "Review @profilelead"
        assert opportunity.reason is not None and "Fortuna noticed" in opportunity.reason
        assert "auto" not in (opportunity.reason or "").casefold()
        assert profile.status == "converted_to_opportunity"
        assert session.query(LearningEvent).filter_by(event_type="social.profile_opportunity_created").count() == 1
        assert session.query(ConfidenceRecord).filter_by(subject_type="opportunity").count() >= 1


def test_profile_lead_alert_missing_target_is_simulated_and_recommended() -> None:
    with session_scope() as session:
        owner = _owner(session)
        profile = _seed_profile(session, owner)

        attempts = route_profile_lead_alert(session, profile, actor=owner)

        assert attempts == []
        assert (
            session.query(Recommendation)
            .filter_by(recommendation_type="social_profile_alert_target_missing")
            .count()
            == 1
        )
        assert session.query(SocialEvent).filter_by(event_type="social.alert.simulated").count() == 1


def test_profile_leads_and_comment_review_screens_are_simple_and_safe() -> None:
    with session_scope() as session:
        owner = _owner(session)
        profile = _seed_profile(session, owner)
        principal = _principal(owner)

        leads = screen_for_page("opportunities:profiles", principal, session=session, user=owner)
        detail = screen_for_page(f"social_profile:{profile.id}", principal, session=session, user=owner)
        review = screen_for_page("opportunities:comments", principal, session=session, user=owner)

        combined = "\n".join([leads.text, detail.text, review.text])
        assert "Comment Profile Leads" in leads.text
        assert "Comment Section Review" in review.text
        assert "Next Best Move" in combined
        assert "Fortuna will not follow, like, or comment" in detail.text
        assert "source_method" not in combined
        assert "compliance_status" not in combined
        assert "confidence_score" not in combined
        assert "entity_type" not in combined
        assert "👀 Review Profile" in [button.text for row in leads.reply_markup.inline_keyboard for button in row]


def test_help_brain_explains_comment_profiles_safety_and_manual_execution() -> None:
    with session_scope() as session:
        owner = _owner(session)

        profile_answer = help_brain_answer(session, owner, question="What are comment profile leads?")
        safe_data = help_brain_answer(session, owner, question="What data is safe to enter?")
        automation = help_brain_answer(session, owner, question="Does Fortuna follow people automatically?")

        assert profile_answer.next_action == "opportunities:profiles"
        assert "never follows" in profile_answer.answer
        assert safe_data.next_action == "opportunities:discovery"
        assert "Do not enter private data" in safe_data.answer
        assert "does not auto" in automation.answer.lower()
