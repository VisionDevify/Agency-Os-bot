from sqlalchemy import select

from app.bot.screens import (
    render_activation_blocker_detail_page,
    render_daily_autopilot_page,
    render_fortuna_action_log_page,
    render_notification_targets_page,
    render_owner_daily_checklist_page,
    render_proxy_detail_page,
    render_proxy_entry_check_page,
    render_team_onboarding_activation_page,
)
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.team_rollout import ActivationBlockerDecision, DailyAutopilotSetting
from app.services.agency_activation import build_activation_report
from app.services.auth import setup_owner_if_needed
from app.services.production_activation import (
    decide_activation_blocker,
    daily_autopilot_summary,
    proxy_entry_status,
    run_daily_autopilot_now,
    toggle_daily_autopilot,
)
from app.services.proxies import create_proxy
from app.services.setup_wizard import create_setup_model
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def test_readiness_blocker_fix_paths_and_decisions() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_setup_model(session, actor=owner, display_name="Incomplete Model")

        screen = render_activation_blocker_detail_page(session, "models", 0)
        assert "Fix Now" in str(screen.reply_markup.inline_keyboard)
        assert "Explain" in str(screen.reply_markup.inline_keyboard)
        assert "Skip for Later" in str(screen.reply_markup.inline_keyboard)
        assert "Mark Not Needed" in str(screen.reply_markup.inline_keyboard)

        blocker = decide_activation_blocker(session, actor=owner, section="models", index=0, status="not_needed")
        report = build_activation_report(session)

        assert blocker is not None
        assert blocker["code"] == "model.missing_country"
        assert "model.missing_country" not in {item["code"] for item in report["blockers"]}
        assert session.scalar(select(ActivationBlockerDecision)) is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "activation.blocker_not_needed")) is not None


def test_model_completion_flow_has_no_dead_end_buttons() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_setup_model(session, actor=owner, display_name="Live Completion Model")

        screen = render_activation_blocker_detail_page(session, "models", 0)
        markup = str(screen.reply_markup.inline_keyboard)

        assert f"agency_activation:blocker:models:0:fix" in markup
        assert "Back" in markup
        assert "Main Menu" in markup
        assert model.display_name in build_activation_report(session)["blockers"][0]["title"]


def test_daily_autopilot_schedule_toggle_and_run_now() -> None:
    with session_scope() as session:
        owner = _owner(session)
        summary = daily_autopilot_summary(session, owner)
        screen = render_daily_autopilot_page(session, owner)

        assert summary["enabled"] is True
        assert "Daily Readiness Scan" in screen.text
        assert "Run Now" in str(screen.reply_markup.inline_keyboard)

        toggle_daily_autopilot(session, actor=owner)
        assert daily_autopilot_summary(session, owner)["enabled"] is False
        setting = run_daily_autopilot_now(session, actor=owner)

        assert setting.last_run_at is not None
        assert setting.last_result == "Daily autopilot completed."
        assert session.scalar(select(DailyAutopilotSetting)) is not None


def test_owner_daily_checklist_and_action_log() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_setup_model(session, actor=owner, display_name="Checklist Model")
        run_daily_autopilot_now(session, actor=owner)

        checklist = render_owner_daily_checklist_page(session, owner)
        log = render_fortuna_action_log_page(session)

        assert "Owner Daily Checklist" in checklist.text
        assert "Fix Top Blocker" in str(checklist.reply_markup.inline_keyboard)
        assert "Run Daily Cycle" in str(checklist.reply_markup.inline_keyboard)
        assert "What Fortuna Did" in log.text
        assert "Actions Created:" in log.text
        assert "{" not in log.text


def test_team_onboarding_activation_invite_guidance() -> None:
    with session_scope() as session:
        _owner(session)
        screen = render_team_onboarding_activation_page(session)

        assert "No real team users are active yet." in screen.text
        assert "Invite packet:" in screen.text
        assert "Invite Team" in str(screen.reply_markup.inline_keyboard)


def test_notification_target_registration_guidance() -> None:
    with session_scope() as session:
        _owner(session)
        screen = render_notification_targets_page(session)
        markup = str(screen.reply_markup.inline_keyboard)

        assert "open that Telegram space first" in screen.text
        assert "Chat IDs stay masked" in screen.text
        assert "Register Current Chat as Fortuna Target" in markup


def test_proxy_entry_check_and_detail_mask_sensitive_values() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_setup_model(session, actor=owner, display_name="Proxy Model")
        account = Account(
            model_brand_id=model.id,
            platform="instagram",
            username="proxy_model",
            display_name="Proxy Model",
            status="healthy",
            auth_status="connected",
        )
        session.add(account)
        session.flush()

        empty_status = proxy_entry_status(session)
        empty_screen = render_proxy_entry_check_page(session)

        assert empty_status.needs_setup is True
        assert "Olympix wizard" in empty_screen.text
        assert "Open Olympix Wizard" in str(empty_screen.reply_markup.inline_keyboard)

        proxy = create_proxy(
            session,
            actor=owner,
            provider="Olympix Mobile",
            host="host.olympix.io",
            port=1080,
            base_username="customer-user",
            password="super-secret",
            target_country="United States",
            target_state="Florida",
        )
        detail = render_proxy_detail_page(session, proxy.id)

        assert "super-secret" not in detail.text
        assert proxy.generated_username not in detail.text
        assert proxy.session_suffix not in detail.text
        assert "Password: encrypted and hidden" in detail.text
