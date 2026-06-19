from datetime import UTC, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.navigation import screen_for_page
from app.bot.navigation_stack import parent_page_for
from app.bot.screens.formatting import Screen
from app.bot.screens.home import render_today_priorities_page
from app.bot.screens.settings import render_production_observability_page
from app.models.button_issue import ButtonIssue
from app.models.recovery import BackupRun, RestoreTestRun
from app.services.auth import setup_owner_if_needed
from app.services.button_health import button_health_summary, run_button_issue_scan
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.recovery import record_backup_run, run_backup, run_restore_test
from app.services.shared_status import StatusCondition, compute_shared_status, status_from_risk_level
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=51, owner_telegram_id=51, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _button_labels(screen: Screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _callback_for_label(screen: Screen, label_part: str) -> str | None:
    for row in screen.reply_markup.inline_keyboard:
        for button in row:
            if label_part in button.text:
                return button.callback_data
    return None


def _callback_for_exact_label(screen: Screen, label: str) -> str | None:
    for row in screen.reply_markup.inline_keyboard:
        for button in row:
            if button.text == label:
                return button.callback_data
    return None


def test_shared_status_uses_worst_active_condition() -> None:
    result = compute_shared_status(
        [
            StatusCondition("operations", "healthy", "Operations healthy.", 0),
            StatusCondition("recovery", "critical", "No backup evidence.", 1, "Run your first backup."),
            StatusCondition("navigation", "needs_review", "One button issue.", 1),
        ]
    )

    assert result.status == "critical"
    assert result.issue_count == 2
    assert result.recommended_action == "Run your first backup."
    assert status_from_risk_level("High") == "needs_attention"


def test_observability_cannot_be_healthy_when_recovery_is_critical() -> None:
    with session_scope() as session:
        owner = _owner(session)

        summary = production_observability_summary(session)
        screen = render_production_observability_page(session, owner)

        assert summary["recovery_status"] == "critical"
        assert summary["shared_status"] == "critical"
        assert summary["active_issue_count"] >= 1
        assert "Recovery" in screen.text
        assert "Issues Found: 0" not in screen.text
        assert "Healthy\n\nIssues Found: 0" not in screen.text


def test_run_backup_records_honest_manual_required_not_fake_success() -> None:
    with session_scope() as session:
        owner = _owner(session)

        run = run_backup(session, actor=owner)

        assert run.run_identifier
        assert run.status in {"manual_required", "failed", "not_configured"}
        assert run.status not in {"success", "succeeded"}
        assert not run.artifact_verified
        assert run.artifact_uri is None
        assert session.query(BackupRun).filter_by(run_identifier=run.run_identifier).count() == 1


def test_backup_run_identifier_is_idempotent_and_terminal_state_is_not_overwritten() -> None:
    with session_scope() as session:
        owner = _owner(session)

        first = record_backup_run(
            session,
            actor=owner,
            run_identifier="backup-idempotent",
            status="failed",
            encrypted=False,
            error_summary="Safe failure",
        )
        second = record_backup_run(
            session,
            actor=owner,
            run_identifier="backup-idempotent",
            status="succeeded",
            encrypted=True,
            checksum="a" * 64,
            artifact_uri="file:///backup.dump.enc",
            artifact_verified=True,
        )

        assert second.id == first.id
        assert second.status == "failed"
        assert session.query(BackupRun).filter_by(run_identifier="backup-idempotent").count() == 1


def test_restore_test_semantics_and_idempotency_are_honest() -> None:
    with session_scope() as session:
        owner = _owner(session)

        missing = run_restore_test(session, actor=owner, run_identifier="restore-idempotent")
        repeated = run_restore_test(session, actor=owner, run_identifier="restore-idempotent")

        assert missing.id == repeated.id
        assert missing.status == "not_available"
        assert session.query(RestoreTestRun).filter_by(run_identifier="restore-idempotent").count() == 1

        record_backup_run(
            session,
            actor=owner,
            run_identifier="backup-verified-only",
            status="succeeded",
            encrypted=True,
            checksum="b" * 64,
            artifact_uri="file:///backup-b.dump.enc",
            artifact_verified=True,
        )
        verified = run_restore_test(session, actor=owner, run_identifier="restore-verified-only")

        assert verified.status == "verified_only"
        assert verified.checksum_verified is True
        assert verified.full_restore_performed is False


def test_help_navigation_preserves_source_context() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        proxy_help = screen_for_page("help_from:proxies", principal, session=session, user=owner)
        recovery_help = screen_for_page("help_from:recovery_center", principal, session=session, user=owner)
        discovery_help = screen_for_page("help_from:opportunities:discovery", principal, session=session, user=owner)
        topic = screen_for_page("help_from:recovery_center:topic:proxy_setup", principal, session=session, user=owner)

        assert _callback_for_label(proxy_help, "Back") == "nav:proxies"
        assert _callback_for_label(recovery_help, "Back") == "nav:recovery_center"
        assert _callback_for_label(discovery_help, "Back") == "nav:opportunities:discovery"
        assert _callback_for_label(topic, "Back") == "nav:recovery_center"
        assert "Ask Fortuna" in _button_labels(proxy_help)
        assert parent_page_for("help_from:recovery_center:topic:proxy_setup") == "recovery_center"


def test_recovery_center_navigation_renders_recovery_screen() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        recovery = screen_for_page("recovery_center", principal, session=session, user=owner)

        assert "Recovery Center" in recovery.text
        assert "More" not in recovery.text.splitlines()[0]
        assert _callback_for_exact_label(recovery, "Back") == "nav:owner_advanced"


def test_button_issue_summary_drives_observability_and_today() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            ButtonIssue(
                screen="proxy:1:manage",
                button_label="Back",
                callback_data="nav:menu",
                issue_type="bad_back_target",
                severity="medium",
                status="open",
                detected_at=datetime.now(UTC),
                evidence_summary="Proxy Manage Back goes to Main Menu instead of Proxy Detail.",
                recommended_fix="Return Back to the selected proxy detail screen.",
            )
        )
        session.flush()

        health = button_health_summary(session)
        summary = production_observability_summary(session)
        today = render_today_priorities_page(session, owner)

        assert health.navigation_issue_count == 1
        assert health.overall_status == "needs_review"
        assert summary["button_health_open_issue_count"] == 1
        assert summary["active_issue_count"] >= 1
        assert "Button Health" in today.text


def test_active_button_scan_detects_bad_back_target(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)

        def fake_screen_for_page(page, principal, recorder=None, session=None, user=None, chat_id=None, chat_title=None):
            return Screen(
                text=f"{page}\n\nFriendly screen.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Back", callback_data="nav:menu")],
                        [InlineKeyboardButton(text="Main Menu", callback_data="nav:menu")],
                    ]
                ),
            )

        monkeypatch.setattr("app.bot.navigation.screen_for_page", fake_screen_for_page)

        summary = run_button_issue_scan(session, actor=owner)

        assert summary.navigation_issue_count > 0
        assert session.query(ButtonIssue).filter_by(issue_type="bad_back_target", status="open").count() > 0


def test_button_scan_does_not_treat_callback_failure_as_back_button() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        settings = screen_for_page("settings", principal, session=session, user=owner)
        summary = run_button_issue_scan(session, actor=owner)

        assert _callback_for_label(settings, "Back") == "nav:owner_advanced"
        assert _callback_for_label(settings, "Callback Failure Review") == "nav:callback_failure_review"
        assert summary.technical_issue_count == 0
        assert summary.navigation_issue_count == 0
        assert summary.ux_issue_count == 0
