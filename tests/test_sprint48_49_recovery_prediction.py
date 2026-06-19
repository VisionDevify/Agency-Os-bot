from datetime import UTC, datetime, timedelta

from app.bot.navigation import screen_for_page
from app.bot.screens.recovery import render_disaster_plan_page, render_recovery_center_page
from app.models.learning import ConfidenceRecord, LearningEvent
from app.models.opportunity import Opportunity, OpportunityResult
from app.models.recovery import BackupRun, BackupStorageTarget, RestoreTestRun
from app.models.social import SocialSourcePerformance
from app.models.task import Task
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from app.services.opportunity_prediction import (
    best_opportunity_prediction,
    predict_opportunity,
    update_prediction_learning_from_result,
)
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.recovery import backup_copy_count, recovery_risk_assessment, record_backup_run, run_restore_test
from app.services.team_intelligence import generate_team_performance_snapshot, team_intelligence_summary
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def test_recovery_center_missing_data_is_not_fake_protection() -> None:
    with session_scope() as session:
        owner = _owner(session)

        assessment = recovery_risk_assessment(session)
        screen = render_recovery_center_page(session, owner)

        assert assessment.protection_status == "Not set up yet"
        assert assessment.restore_test_status == "Not tested yet"
        assert assessment.risk_level in {"High", "Critical"}
        assert "Not set up yet" in screen.text
        assert "Not tested yet" in screen.text
        assert "Protected" not in screen.text
        assert "Backup Passed" not in screen.text


def test_recovery_risk_score_uses_backup_age_failures_restore_and_storage() -> None:
    with session_scope() as session:
        owner = _owner(session)
        old = datetime.now(UTC) - timedelta(days=4)
        session.add(BackupStorageTarget(name="Local", target_type="local_runtime", enabled=True, encrypted=True))
        record_backup_run(
            session,
            actor=owner,
            status="succeeded",
            storage_target="Local",
            encrypted=False,
            checksum=None,
            started_at=old,
            finished_at=old,
        )
        record_backup_run(
            session,
            actor=owner,
            status="failed",
            storage_target="Local",
            encrypted=False,
            error_summary="Network unavailable",
        )

        assessment = recovery_risk_assessment(session)

        assert assessment.risk_score >= 75
        assert assessment.risk_level == "Critical"
        assert "Backup is older than the freshness target." in assessment.evidence
        assert assessment.backup_copies_count == 1
        assert assessment.encryption_status == "Not set up yet"
        assert assessment.checksum_status == "Not set up yet"


def test_recovery_low_risk_requires_redundant_encrypted_checked_and_restored_evidence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        now = datetime.now(UTC)
        session.add_all(
            [
                BackupStorageTarget(name="External A", target_type="s3_compatible", enabled=True, encrypted=True),
                BackupStorageTarget(name="External B", target_type="backblaze_b2", enabled=True, encrypted=True),
            ]
        )
        first = record_backup_run(
            session,
            actor=owner,
            status="succeeded",
            storage_target="External A",
            encrypted=True,
            checksum="a" * 64,
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1),
        )
        record_backup_run(
            session,
            actor=owner,
            status="succeeded",
            storage_target="External B",
            encrypted=True,
            checksum="b" * 64,
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1),
        )
        session.add(
            RestoreTestRun(
                backup_run_id=first.id,
                status="succeeded",
                started_at=now,
                finished_at=now,
                result_summary='{"checksum_verified": true, "archive_decrypts": true, "test_database_restored": true}',
            )
        )
        session.flush()

        assessment = recovery_risk_assessment(session, now=now)

        assert backup_copy_count(session, now=now) == 2
        assert assessment.risk_score <= 24
        assert assessment.risk_level == "Low"
        assert assessment.recovery_confidence == "High"
        assert assessment.protection_status == "Protected by recent verified backups"


def test_restore_test_records_verified_not_fake_pass_when_no_test_database() -> None:
    with session_scope() as session:
        owner = _owner(session)
        record_backup_run(
            session,
            actor=owner,
            status="succeeded",
            encrypted=True,
            checksum="c" * 64,
            storage_target="local_runtime",
        )

        test = run_restore_test(session, actor=owner)

        assert test.status == "verified"
        assert "test_database_restored" in (test.result_summary or "")
        assert "False" not in render_recovery_center_page(session, owner).text


def test_recovery_screens_and_disaster_plan_hide_secrets_and_use_emoji_buttons() -> None:
    with session_scope() as session:
        owner = _owner(session)

        recovery = render_recovery_center_page(session, owner)
        disaster = render_disaster_plan_page()
        labels = [button.text for row in recovery.reply_markup.inline_keyboard for button in row]
        combined = f"{recovery.text}\n{disaster.text}".casefold()

        assert "password" not in combined
        assert "database_url" not in combined
        assert "encrypted backup" in disaster.text
        assert "🔄 Run Backup" in labels
        assert "🧪 Test Restore" in labels
        assert "🚨 Disaster Plan" in labels


def test_team_performance_snapshot_and_summary_use_real_work_data() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = get_or_create_telegram_user(session, telegram_user_id=48, display_name="Chris")
        chatter.status = USER_STATUS_ACTIVE
        chatter.is_active = True
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        session.add(
            Task(
                title="Done",
                status="complete",
                assigned_to_user_id=chatter.id,
                completed_at=datetime.now(UTC),
            )
        )
        session.add(
            OpportunityResult(
                opportunity_id=1,
                posted_by_user_id=chatter.id,
                status="posted",
                clicks=3,
            )
        )
        session.flush()

        snapshot = generate_team_performance_snapshot(session, chatter)
        summary = team_intelligence_summary(session)

        assert snapshot.tasks_completed == 1
        assert snapshot.opportunities_successful == 1
        assert snapshot.reliability_score > 70
        assert summary.best_chatter is not None


def test_opportunity_prediction_creation_and_best_opportunity_screen() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            SocialSourcePerformance(
                platform="x",
                niche="fitness",
                engagement_angle="curiosity",
                reviewed_count=4,
                conversions=1,
                success_rate=80,
                historical_score=86,
            )
        )
        opportunity = Opportunity(
            platform="x",
            title="Fitness creator thread",
            niche="fitness",
            score=72,
            priority="high",
            status="discovered",
        )
        session.add(opportunity)
        session.flush()

        prediction = predict_opportunity(session, opportunity, actor=owner)
        best = best_opportunity_prediction(session, actor=owner)
        screen = screen_for_page("opportunities:best", _principal(owner), session=session, user=owner)

        assert prediction.predicted_quality >= 70
        assert prediction.recommended_angle == "curiosity"
        assert best is not None
        assert "Best Opportunity" in screen.text
        assert "No auto-posting" in screen.text
        assert "auto-post" in prediction.risk_notes


def test_prediction_learning_updates_confidence_from_manual_result() -> None:
    with session_scope() as session:
        owner = _owner(session)
        opportunity = Opportunity(platform="x", title="Manual opportunity", niche="fitness", status="discovered", score=60)
        session.add(opportunity)
        session.flush()
        prediction = predict_opportunity(session, opportunity, actor=owner)
        result = OpportunityResult(opportunity_id=opportunity.id, posted_by_user_id=owner.id, status="posted", clicks=5)
        session.add(result)
        session.flush()

        update_prediction_learning_from_result(session, result, actor=owner)

        confidence = session.query(ConfidenceRecord).filter_by(subject_type="opportunity", subject_id=str(opportunity.id)).one()
        assert confidence.previous_score == prediction.confidence_score
        assert confidence.new_score > confidence.previous_score
        assert session.query(LearningEvent).filter_by(event_type="opportunity.prediction_outcome").count() == 1


def test_help_brain_explains_recovery_risk_and_opportunity_prediction() -> None:
    with session_scope() as session:
        owner = _owner(session)

        recovery = help_brain_answer(session, owner, question="How is Recovery Risk Score calculated?")
        prediction = help_brain_answer(session, owner, question="How does Fortuna choose best opportunities?")

        assert "backup age" in recovery.answer.lower()
        assert "Risk" in recovery.answer
        assert recovery.next_action == "recovery_center"
        assert "human reviews" in prediction.answer.lower() or "human review" in prediction.answer.lower()
        assert prediction.next_action == "opportunities:best"
