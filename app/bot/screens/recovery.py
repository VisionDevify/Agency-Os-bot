from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.menu import callback_for, page_controls
from app.services.recovery import backup_history, recovery_risk_assessment, run_backup, run_restore_test

from .formatting import *


def _recovery_status_icon(level: str) -> str:
    return {"Low": "🟢", "Moderate": "🟡", "High": "🟠", "Critical": "🔴"}.get(level, "🟡")


def _recovery_menu(*, back_to: str = "owner_advanced") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Run Backup", callback_data=callback_for("recovery:backup:run"))],
            [InlineKeyboardButton(text="📦 Backup History", callback_data=callback_for("recovery:history"))],
            [InlineKeyboardButton(text="🧪 Test Restore", callback_data=callback_for("recovery:restore:test"))],
            [InlineKeyboardButton(text="🚨 Disaster Plan", callback_data=callback_for("recovery:disaster_plan"))],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("recovery:details"))],
            *page_controls(back_to=back_to),
        ]
    )


def render_recovery_center_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    assessment = recovery_risk_assessment(session)
    icon = _recovery_status_icon(assessment.risk_level)
    if not details:
        if assessment.latest_backup is None:
            heading = "🟡 Recovery needs setup"
            summary = "Fortuna has not recorded a successful backup yet."
        elif assessment.alerts:
            heading = f"{icon} {assessment.alerts[0]}"
            summary = "Fortuna found backup or restore evidence that needs attention."
        else:
            heading = "🟢 Recovery Center"
            summary = "Fortuna checked backup evidence. Nothing urgent here."
        evidence_lines = [f"• {line}" for line in assessment.evidence[:3]]
        lines = [
            "🛡 Recovery Center",
            "",
            heading,
            summary,
            "",
            "Current Evidence",
            f"Protection: {assessment.protection_status}",
            f"Last Backup: {assessment.last_backup_status}",
            f"Restore Test: {assessment.restore_test_status}",
            f"Backup Copies: {assessment.backup_copies_count}",
            f"Recovery Risk: {assessment.risk_score}/100 ({assessment.risk_level})",
            "",
            "Why",
            *(evidence_lines or ["• No recovery records have been created yet."]),
            "",
            "✨ Next Best Move",
            assessment.next_best_move,
        ]
        return Screen("\n".join(lines), _recovery_menu())

    lines = [
        "🔎 Recovery Technical Details",
        "",
        f"Risk Score: {assessment.risk_score}/100",
        f"Risk Level: {assessment.risk_level}",
        f"Recovery Confidence: {assessment.recovery_confidence}",
        f"Encryption: {assessment.encryption_status}",
        f"Checksum: {assessment.checksum_status}",
        f"External Storage Configured: {'yes' if assessment.external_storage_configured else 'no'}",
        f"Recent Backup Failures: {assessment.recent_failure_count}",
        "",
        "Score Drivers:",
        *[f"- {line}" for line in assessment.evidence],
        "",
        "No secrets or backup contents are shown here.",
    ]
    return Screen(
        "\n".join(lines),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Executive Summary", callback_data=callback_for("recovery_center"))],
                [InlineKeyboardButton(text="📦 Backup History", callback_data=callback_for("recovery:history"))],
                *page_controls(back_to="recovery_center"),
            ]
        ),
    )


def render_backup_run_page(session: Session, user: User | None = None) -> Screen:
    run = run_backup(session, actor=user)
    status = "✅ Backup recorded" if run.status == "succeeded" else "🟡 Backup needs attention"
    lines = [
        "🔄 Run Backup",
        "",
        status,
        "",
        f"Status: {run.status.title()}",
        f"Encrypted: {'yes' if run.encrypted else 'no'}",
        f"Checksum: {'recorded' if run.checksum else 'not recorded'}",
        "",
        "Next:",
        "Run a restore test." if run.status == "succeeded" else (run.error_summary or "Review backup configuration."),
    ]
    return Screen("\n".join(lines), _recovery_menu(back_to="recovery_center"))


def render_backup_history_page(session: Session, user: User | None = None) -> Screen:
    runs = backup_history(session)
    lines = ["📦 Backup History", ""]
    if not runs:
        lines.extend(["No backups recorded yet.", "", "Next:", "Run your first encrypted backup."])
    else:
        for run in runs[:8]:
            when = format_user_datetime(user, run.started_at) if run.started_at else "Unknown"
            lines.append(f"• {when} — {run.status.title()}")
            lines.append(f"  Encrypted: {'yes' if run.encrypted else 'no'} | Checksum: {'yes' if run.checksum else 'no'}")
        lines.extend(["", "No backup contents or secrets are shown here."])
    return Screen("\n".join(lines), _recovery_menu(back_to="recovery_center"))


def render_restore_test_page(session: Session, user: User | None = None) -> Screen:
    test = run_restore_test(session, actor=user)
    if test.status == "verified":
        title = "🧪 Restore test readiness"
        summary = "Fortuna verified the backup file metadata, but no test restore database is configured yet."
    elif test.status == "succeeded":
        title = "✅ Restore tested"
        summary = test.result_summary or "Restore test completed."
    else:
        title = "🟡 Restore test needs attention"
        summary = test.error_summary or test.result_summary or "Restore readiness could not be verified."
    lines = [
        title,
        "",
        f"Status: {test.status.title()}",
        "",
        summary,
        "",
        "Next:",
        "Configure a restore-test database for a full restore drill." if test.status == "verified" else "Review Recovery Center details.",
    ]
    return Screen("\n".join(lines), _recovery_menu(back_to="recovery_center"))


def render_disaster_plan_page(*, details: bool = False) -> Screen:
    if not details:
        lines = [
            "🚨 Disaster Plan",
            "",
            "If Railway ever breaks, you need three things:",
            "1. Code repo",
            "2. Environment secrets",
            "3. Latest encrypted backup",
            "",
            "✨ Next Best Move",
            "Keep backups current and store secrets securely outside Telegram.",
        ]
        rows = [
            [InlineKeyboardButton(text="📋 View Steps", callback_data=callback_for("recovery:disaster_plan:details"))],
            [InlineKeyboardButton(text="📦 Latest Backup", callback_data=callback_for("recovery:history"))],
            [InlineKeyboardButton(text="🔎 Technical Details", callback_data=callback_for("recovery:details"))],
            *page_controls(back_to="recovery_center"),
        ]
        return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))
    lines = [
        "📋 Recovery Steps",
        "",
        "1. Create a new Railway project.",
        "2. Add Postgres and Redis.",
        "3. Deploy the Fortuna repo.",
        "4. Set required environment variables.",
        "5. Restore the latest encrypted backup.",
        "6. Run migrations.",
        "7. Verify /health, /integrity, /botstatus, and Telegram /start.",
        "",
        "Never paste secrets into Telegram or public logs.",
    ]
    return Screen("\n".join(lines), page_menu(back_to="recovery:disaster_plan"))
