from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.menu import callback_for, page_controls
from app.models.recovery import BackupStorageTarget
from app.services.backup_storage import backup_s3_environment_state, backup_storage_targets
from app.services.recovery import backup_history, recovery_risk_assessment, run_backup, run_restore_test

from .formatting import *


def _recovery_status_icon(level: str) -> str:
    return {"Low": "🟢", "Moderate": "🟡", "High": "🟠", "Critical": "🔴"}.get(level, "🟡")


def _legacy_recovery_menu(*, back_to: str = "owner_advanced") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Run Backup", callback_data=callback_for("recovery:backup:run"))],
            [InlineKeyboardButton(text="📦 Backup Storage", callback_data=callback_for("recovery:storage"))],
            [InlineKeyboardButton(text="📦 Backup History", callback_data=callback_for("recovery:history"))],
            [InlineKeyboardButton(text="🧪 Test Restore", callback_data=callback_for("recovery:restore:test"))],
            [InlineKeyboardButton(text="🚨 Disaster Plan", callback_data=callback_for("recovery:disaster_plan"))],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("recovery:details"))],
            [InlineKeyboardButton(text="❓ Help", callback_data=callback_for("help_from:recovery_center"))],
            *page_controls(back_to=back_to),
        ]
    )


def _recovery_menu(*, back_to: str = "owner_advanced", storage_setup: bool = False) -> InlineKeyboardMarkup:
    if storage_setup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="☁️ Add S3 Storage", callback_data=callback_for("recovery:storage:s3"))],
                [InlineKeyboardButton(text="📦 Add Backblaze B2", callback_data=callback_for("recovery:storage:b2"))],
                [InlineKeyboardButton(text="📁 Manual Export", callback_data=callback_for("recovery:storage:manual"))],
                [InlineKeyboardButton(text="🧪 Test Restore", callback_data=callback_for("recovery:restore:test"))],
                [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("recovery:details"))],
                [InlineKeyboardButton(text="❓ Help", callback_data=callback_for("help_from:recovery_center"))],
                *page_controls(back_to=back_to),
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Run Backup", callback_data=callback_for("recovery:backup:run"))],
            [InlineKeyboardButton(text="📦 Backup Storage", callback_data=callback_for("recovery:storage"))],
            [InlineKeyboardButton(text="📦 Backup History", callback_data=callback_for("recovery:history"))],
            [InlineKeyboardButton(text="🧪 Test Restore", callback_data=callback_for("recovery:restore:test"))],
            [InlineKeyboardButton(text="🚨 Disaster Plan", callback_data=callback_for("recovery:disaster_plan"))],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("recovery:details"))],
            [InlineKeyboardButton(text="❓ Help", callback_data=callback_for("help_from:recovery_center"))],
            *page_controls(back_to=back_to),
        ]
    )


def render_recovery_center_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    assessment = recovery_risk_assessment(session)
    icon = _recovery_status_icon(assessment.risk_level)
    if not details:
        if not assessment.external_storage_configured:
            heading = "Recovery Gap"
            summary = "No external backup storage has passed connection testing yet."
        elif assessment.latest_backup is None:
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
        return Screen("\n".join(lines), _recovery_menu(storage_setup=not assessment.external_storage_configured))

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
    status = "✅ Backup verified" if run.status in {"success", "succeeded"} else "🟡 Backup needs action"
    next_step = (
        "Run a restore test."
        if run.status in {"success", "succeeded"}
        else run.error_summary or run.result_summary or "Review backup storage and run a manual export."
    )
    lines = [
        "🔄 Run Backup",
        "",
        status,
        "",
        f"Status: {run.status.replace('_', ' ').title()}",
        f"Encrypted: {'yes' if run.encrypted else 'no'}",
        f"Checksum: {'recorded' if run.checksum else 'not recorded'}",
        "",
        "Next:",
        next_step,
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
    if test.status == "not_available":
        title = "🧪 Restore Test"
        summary = test.error_summary or "No backup is available yet."
        next_step = "Run your first backup."
    elif test.status == "verified_only":
        title = "🧪 Restore test readiness"
        summary = "Fortuna verified the backup file, but full restore testing needs a test database."
        next_step = "Configure a restore-test database for a full restore drill."
    elif test.status in {"passed", "succeeded"}:
        title = "✅ Restore tested"
        summary = test.result_summary or "Restore test completed."
        next_step = "Nothing urgent."
    else:
        title = "🟡 Restore test needs attention"
        summary = test.error_summary or test.result_summary or "Restore readiness could not be verified."
        next_step = "Review Recovery Center details."
    lines = [
        title,
        "",
        f"Status: {test.status.replace('_', ' ').title()}",
        "",
        summary,
        "",
        "Next:",
        next_step,
    ]
    return Screen("\n".join(lines), _recovery_menu(back_to="recovery_center"))


def _render_backup_storage_page_legacy() -> Screen:
    lines = [
        "📦 Backup Storage",
        "",
        "Status:",
        "External storage is not connected yet.",
        "",
        "Why it matters:",
        "If Railway breaks, external backups help restore Fortuna somewhere else.",
        "",
        "✨ Next Best Move",
        "Choose a backup storage target.",
        "",
        "S3-Compatible and Backblaze B2 are prepared as placeholders until credentials are configured safely.",
    ]
    return Screen(
        "\n".join(lines),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="☁️ S3-Compatible", callback_data=callback_for("recovery:storage:s3"))],
                [InlineKeyboardButton(text="📦 Backblaze B2", callback_data=callback_for("recovery:storage:b2"))],
                [InlineKeyboardButton(text="📁 Manual Export", callback_data=callback_for("recovery:storage:manual"))],
                [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("recovery:details"))],
                *page_controls(back_to="recovery_center"),
            ]
        ),
    )


def _storage_target_for_type(session: Session, target_type: str) -> BackupStorageTarget | None:
    for target in backup_storage_targets(session):
        if target.target_type == target_type:
            return target
    return None


def _storage_status_text(target: BackupStorageTarget | None) -> str:
    if target is None:
        return "Not configured yet."
    if target.connection_status == "active" and target.provider_available:
        return "Connected and available."
    if target.connection_status == "failed":
        return "Connection failed."
    if target.connection_status == "disabled":
        return "Removed."
    return "Not configured yet."


def _storage_target_rows(target: BackupStorageTarget | None) -> list[str]:
    if target is None:
        return ["Configured: No"]
    masked = target.masked_config_json or {}
    rows = [
        f"Configured: {'Yes' if target.connection_status == 'active' else 'No'}",
        f"Status: {_storage_status_text(target)}",
    ]
    for label, key in (
        ("Endpoint", "endpoint"),
        ("Bucket", "bucket"),
        ("Region", "region"),
        ("Access Key", "access_key"),
        ("Key ID", "key_id"),
    ):
        value = masked.get(key)
        if value:
            rows.append(f"{label}: {value}")
    if masked.get("secret_key") or masked.get("application_key"):
        rows.append("Secret: Encrypted")
    if target.last_test_at:
        rows.append(f"Last Test: {format_user_datetime(None, target.last_test_at)}")
    if target.last_test_summary:
        rows.append(f"Result: {target.last_test_summary}")
    return rows


def render_backup_storage_page(session: Session, user: User | None = None, *, target_type: str | None = None) -> Screen:
    if target_type in {"s3_compatible", "backblaze_b2"}:
        target = _storage_target_for_type(session, target_type)
        title = "S3-Compatible Storage" if target_type == "s3_compatible" else "Backblaze B2 Storage"
        activate_page = "recovery:storage:s3:activate" if target_type == "s3_compatible" else "recovery:storage:b2:activate"
        env_state = backup_s3_environment_state()
        guidance = (
            "Add BACKUP_S3_* variables in Railway, then tap Activate. Fortuna tests write, read, and cleanup before enabling it."
            if target_type == "s3_compatible"
            else "Use Backblaze's S3-compatible endpoint in S3-Compatible Storage for now. Direct B2 setup stays unavailable until its connector is finished."
        )
        env_lines = (
            [
                "Railway Variables:",
                f"Endpoint: {'Configured' if env_state['endpoint_configured'] else 'Missing'}",
                f"Bucket: {'Configured' if env_state['bucket_configured'] else 'Missing'}",
                f"Region: {'Configured' if env_state['region_configured'] else 'Optional / auto'}",
                f"Access Key: {env_state['access_key_masked']}",
                f"Secret Key: {env_state['secret_key_status']}",
            ]
            if target_type == "s3_compatible"
            else [
                "Backblaze note:",
                "Use Backblaze's S3-compatible endpoint with the S3-Compatible setup path.",
            ]
        )
        rows = [[InlineKeyboardButton(text="Activate / Test From Railway Env", callback_data=callback_for(activate_page))]]
        if target is not None:
            rows.append([InlineKeyboardButton(text="Test Connection", callback_data=callback_for(f"recovery:storage:test:{target.id}"))])
            rows.append([InlineKeyboardButton(text="Remove", callback_data=callback_for(f"recovery:storage:remove:{target.id}"))])
        rows.extend(
            [
                [InlineKeyboardButton(text="Backup Storage", callback_data=callback_for("recovery:storage"))],
                *page_controls(back_to="recovery_center"),
            ]
        )
        lines = [
            title,
            "",
            "Status:",
            _storage_status_text(target),
            "",
            "Configuration:",
            *_storage_target_rows(target),
            "",
            *env_lines,
            "",
            "How to connect:",
            guidance,
            "",
            "Security:",
            "Credentials are encrypted and never shown in Telegram.",
            "",
            "Next Best Move",
            "Add the Railway variables, then activate and test the connection.",
        ]
        return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    if target_type == "manual_export":
        lines = [
            "Manual Export",
            "",
            "Status:",
            "Available as a manual recovery option.",
            "",
            "What happens:",
            "Fortuna can guide the export, but it will not call recovery protected until an external verified backup exists.",
            "",
            "Next Best Move",
            "Connect S3-compatible storage for automated verified backups.",
            "",
            "No credentials are shown here.",
        ]
        return Screen(
            "\n".join(lines),
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Backup Storage", callback_data=callback_for("recovery:storage"))],
                    *page_controls(back_to="recovery_center"),
                ]
            ),
        )

    targets = backup_storage_targets(session)
    active = [target for target in targets if target.enabled and target.connection_status == "active"]
    lines = [
        "📦 Backup Storage",
        "",
        "Status:",
        "External storage is connected." if active else "External storage is not connected yet.",
        "",
        "Why it matters:",
        "If Railway breaks, external backups help restore Fortuna somewhere else.",
        "",
        "✨ Next Best Move",
        "Run a backup." if active else "Add your backup storage variables in Railway, then test the connection.",
        "",
        "Configured Targets:",
        *(f"- {target.name}: {_storage_status_text(target)}" for target in targets[:5]),
        *([] if targets else ["- None yet"]),
        "",
        "Backblaze B2:",
        "Use its S3-compatible endpoint through S3-Compatible setup for now.",
        "",
        "No credentials are shown here.",
    ]
    return Screen(
        "\n".join(lines),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="S3-Compatible", callback_data=callback_for("recovery:storage:s3"))],
                [InlineKeyboardButton(text="Backblaze B2", callback_data=callback_for("recovery:storage:b2"))],
                [InlineKeyboardButton(text="Manual Export", callback_data=callback_for("recovery:storage:manual"))],
                [InlineKeyboardButton(text="Details", callback_data=callback_for("recovery:details"))],
                *page_controls(back_to="recovery_center"),
            ]
        ),
    )


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
