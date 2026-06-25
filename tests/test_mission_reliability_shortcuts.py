from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import *  # noqa: F403
from app.bot.screens import render_page
from app.bot import runner as runner_module
from app.bot.screens.recovery import render_backup_history_page
from app.bot.screens.reliability import render_reliability_center_page, render_reliability_verify_page
from app.models.recovery import BackupRun
from app.models.recovery import BackupStorageTarget
from app.models.reliability import CallbackLatencyRecord, ReliabilityJob
from app.services.auth import setup_owner_if_needed
from app.services import live_scores
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.reliability import (
    SHORTCUT_BY_COMMAND,
    CallbackTiming,
    active_jobs,
    latency_label,
    mark_stale_reliability_jobs,
    record_callback_latency,
    reliability_summary,
    render_command_shortcut,
    route_health_registry,
    run_command_verification_harness,
    start_reliability_job,
    update_reliability_job,
    working_screen_for,
)
from app.services.freeze_watchdog import freeze_watchdog
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=6701, owner_telegram_id=6701, display_name="Owner")


def _principal(owner) -> PermissionPrincipal:
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


class _FakeChat:
    id = 10


class _FakeSentMessage:
    def __init__(self, message_id: int) -> None:
        self.chat = _FakeChat()
        self.message_id = message_id


class _FakeTelegramMessage:
    def __init__(self, telegram_id: int = 6701) -> None:
        self.chat = _FakeChat()
        self.message_id = 100
        self.from_user = SimpleNamespace(
            id=telegram_id,
            first_name="Owner",
            last_name=None,
            username="owner",
        )
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append(text)
        return _FakeSentMessage(1000 + len(self.answers))


class _SlowCallback:
    data = "nav:slow"

    def __init__(self) -> None:
        self.answered = False

    async def answer(self, text: str | None = None, show_alert: bool = False):
        await asyncio.sleep(0.05)
        self.answered = True


class _FastCallback:
    data = "nav:command_center"

    def __init__(self) -> None:
        self.answered = False
        self.message = SimpleNamespace(chat=_FakeChat(), message_id=111)
        self.from_user = SimpleNamespace(id=6701, first_name="Owner", last_name=None, username="owner")

    async def answer(self, text: str | None = None, show_alert: bool = False):
        self.answered = True


def test_latency_labels_and_records_are_persisted() -> None:
    with session_scope() as session:
        now = datetime.now(UTC)
        record = record_callback_latency(
            session,
            CallbackTiming(
                callback_route="agency_awareness",
                received_at=now,
                acknowledged_at=now + timedelta(milliseconds=100),
                render_started_at=now + timedelta(milliseconds=120),
                render_finished_at=now + timedelta(milliseconds=900),
                edit_or_send_completed_at=now + timedelta(milliseconds=1100),
            ),
            result="succeeded",
        )

        assert latency_label(400) == "excellent"
        assert latency_label(1200) == "good"
        assert latency_label(2500) == "slow"
        assert latency_label(3500) == "bad"
        assert record.total_latency_ms == 1100
        assert record.ack_latency_ms == 100
        assert record.latency_label == "good"
        assert session.query(CallbackLatencyRecord).count() == 1


def test_reliability_jobs_update_and_stale_jobs_time_out() -> None:
    with session_scope() as session:
        job = start_reliability_job(
            session,
            job_id="ai:test",
            job_type="ai_summary",
            status="running",
            current_step="Summarizing evidence",
        )
        update_reliability_job(session, "ai:test", status="completed", current_step="Summary ready", progress_percent=100)

        stale = start_reliability_job(session, job_id="search:stale", job_type="search", status="running")
        stale.updated_at = datetime.now(UTC) - timedelta(minutes=30)
        timed_out = mark_stale_reliability_jobs(session)

        assert job.status == "completed"
        assert job.finished_at is not None
        assert timed_out == 1
        assert stale.status == "timed_out"


def test_active_jobs_excludes_completed_jobs() -> None:
    with session_scope() as session:
        start_reliability_job(session, job_id="backup:active", job_type="backup", status="verifying")
        start_reliability_job(session, job_id="ai:done", job_type="ai_summary", status="completed")

        jobs = active_jobs(session)

        assert [job.job_id for job in jobs] == ["backup:active"]


def test_command_shortcuts_reuse_screen_renderers(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        commands = {
            "home": "Fortuna OS",
            "coo": "COO Briefing",
            "today": "What Matters Today",
            "agency": "Agency Awareness",
            "agency_active": "Active Areas",
            "agency_missing": "Missing / Inactive",
            "agency_connected": "Not Connected",
            "ai": "AI Brain",
            "search": "Search Intelligence",
            "recovery": "Recovery Center",
            "backup_storage": "Backup Storage",
            "s3_storage": "S3-Compatible Storage",
            "reliability": "Reliability Center",
            "observability": "Production Status",
        }
        for command, expected in commands.items():
            screen = render_command_shortcut(session, command=command, principal=principal, user=owner)
            assert expected in screen.text


def test_coo_shortcut_does_not_call_ai_inline(monkeypatch) -> None:
    import app.bot.screens.coo as coo_module

    monkeypatch.setattr(coo_module, "ai_configuration_status", lambda session: {"enabled": True, "configured": True})
    monkeypatch.setattr(
        coo_module,
        "generate_ai_decision_explanation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("COO shortcut must not call AI inline")),
        raising=False,
    )

    with session_scope() as session:
        owner = _owner(session)
        screen = render_command_shortcut(session, command="coo", principal=_principal(owner), user=owner)

        assert "COO Briefing" in screen.text


def test_selftest_command_acknowledges_without_inline_render(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    message = _FakeTelegramMessage()

    monkeypatch.setattr(runner_module, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(runner_module.settings, "owner_telegram_id", 6701, raising=False)
    monkeypatch.setattr(
        runner_module,
        "render_ui_self_test_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selftest must not render inline")),
    )

    asyncio.run(runner_module.selftest(message))

    assert message.answers[0].startswith("Running self-test")
    assert "Self-test started" in message.answers[-1]
    with TestSessionLocal() as session:
        record = session.query(CallbackLatencyRecord).filter_by(callback_route="command:selftest").one()
        assert record.result == "succeeded"
        assert record.latency_label in {"excellent", "good"}
        assert record.safe_error_summary is None


def test_selftest_background_render_skips_full_button_scan(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSessionLocal() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=6701, owner_telegram_id=6701, display_name="Owner")
        owner_id = owner.id
        session.commit()

    calls: dict[str, bool] = {}

    def fake_render(session, user, *, run_now=False, run_button_scan=True, details=False):
        calls["run_now"] = bool(run_now)
        calls["run_button_scan"] = bool(run_button_scan)
        return SimpleNamespace(text="Self-test summary", reply_markup=None)

    monkeypatch.setattr(runner_module, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(runner_module, "render_ui_self_test_page", fake_render)

    text, reply_markup = runner_module._render_selftest_sync(owner_id)

    assert text == "Self-test summary"
    assert reply_markup is None
    assert calls == {"run_now": True, "run_button_scan": False}


def test_selftest_background_timeout_sends_visible_fallback(monkeypatch) -> None:
    import time

    class FakeBot:
        def __init__(self) -> None:
            self.messages: list[str] = []

        async def send_message(self, chat_id, text, reply_markup=None):
            self.messages.append(text)

    def slow_render(user_id: int):
        time.sleep(0.05)
        return ("late self-test", None)

    bot = FakeBot()
    monkeypatch.setattr(runner_module, "SELFTEST_BACKGROUND_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(runner_module, "_render_selftest_sync", slow_render)

    asyncio.run(runner_module._run_selftest_background(bot, 10, 6701))

    assert bot.messages
    assert "taking longer than expected" in bot.messages[0]


def test_safe_callback_answer_is_timeout_bounded(monkeypatch) -> None:
    monkeypatch.setattr(runner_module, "TELEGRAM_API_TIMEOUT_SECONDS", 0.001)
    callback = _SlowCallback()

    asyncio.run(runner_module._safe_callback_answer(callback, "Working"))

    assert callback.answered is False


def test_render_command_timeout_raises_without_dirtying_main_session(monkeypatch) -> None:
    import time

    with session_scope() as session:
        owner = _owner(session)

        def slow_render(**kwargs):
            time.sleep(0.05)
            return SimpleNamespace(text="late", reply_markup=None)

        monkeypatch.setattr(runner_module, "SIMPLE_RENDER_TIMEOUT_SECONDS", 0.001)
        monkeypatch.setattr(runner_module, "_render_command_in_isolated_session", slow_render)

        try:
            asyncio.run(
                runner_module._render_command_with_timeout(
                    "agency",
                    principal=_principal(owner),
                    user=owner,
                    session=session,
                )
            )
        except TimeoutError:
            pass
        else:
            raise AssertionError("command render should time out")

        assert session.is_active is True


def test_verify_navigation_uses_dedicated_render_timeout(monkeypatch) -> None:
    import time

    with session_scope() as session:
        owner = _owner(session)

        def slow_but_valid_render(**kwargs):
            time.sleep(0.01)
            return SimpleNamespace(text="Navigation Verification\n\nPassed Routes: 1", reply_markup=None)

        monkeypatch.setattr(runner_module, "SIMPLE_RENDER_TIMEOUT_SECONDS", 0.001)
        monkeypatch.setattr(runner_module, "NAVIGATION_VERIFY_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(runner_module, "_render_command_in_isolated_session", slow_but_valid_render)

        screen = asyncio.run(
            runner_module._render_command_with_timeout(
                "verify_navigation",
                principal=_principal(owner),
                user=owner,
                session=session,
            )
        )

        assert "Navigation Verification" in screen.text


def test_verify_navigation_isolated_render_commits_revalidation_evidence(monkeypatch, tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'verify-navigation.db'}")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSessionLocal() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=6701, owner_telegram_id=6701, display_name="Owner")
        session.commit()

        monkeypatch.setattr(runner_module, "SessionLocal", TestSessionLocal)

        screen = asyncio.run(
            runner_module._render_command_with_timeout(
                "verify_navigation",
                principal=_principal(owner),
                user=owner,
                session=session,
            )
        )

        assert "Navigation Verification" in screen.text

    with TestSessionLocal() as session:
        assert (
            session.query(CallbackLatencyRecord)
            .filter(
                CallbackLatencyRecord.callback_route == "command:verify_navigation",
                CallbackLatencyRecord.result == "succeeded",
            )
            .count()
            >= 1
        )


def test_fast_path_command_center_avoids_isolated_thread_render(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)

        def fail_isolated_render(**kwargs):
            raise AssertionError("cached command center routes should not use isolated render")

        monkeypatch.setattr(runner_module, "_render_command_in_isolated_session", fail_isolated_render)

        screen = asyncio.run(
            runner_module._render_command_with_timeout(
                "home",
                principal=_principal(owner),
                user=owner,
                session=session,
            )
        )

        assert "Fortuna Command Center" in screen.text


def test_callback_ack_happens_before_lock_acquisition(monkeypatch) -> None:
    callback = _FastCallback()
    observed: dict[str, bool] = {}

    class FakeLocks:
        async def acquire_callback_lock(self, *, chat_id, user_id, ttl_seconds=5):
            observed["answered_before_lock"] = callback.answered
            return None

        async def release(self, handle):
            raise AssertionError("lock was not acquired")

    monkeypatch.setattr(runner_module, "CALLBACK_LOCKS", FakeLocks())

    asyncio.run(runner_module.navigate(callback))

    assert observed["answered_before_lock"] is True


def test_callback_latency_logging_schedules_after_response(monkeypatch) -> None:
    scheduled: list[str] = []

    def fake_background(coro, *, task_name):
        scheduled.append(task_name)
        coro.close()
        return None

    monkeypatch.setattr(runner_module, "_tracked_background_task", fake_background)
    runner_module._record_callback_latency_after_response(
        page="command_center",
        received_at=datetime.now(UTC),
        result="succeeded",
    )

    assert scheduled == ["callback_latency"]


def test_command_center_report_cache_and_refresh(monkeypatch) -> None:
    with session_scope() as session:
        _owner(session)
        live_scores._REPORT_CACHE = None
        live_scores._REPORT_CACHE_EXPIRES_AT = None
        calls = {"count": 0}
        original = live_scores.build_command_center_report

        def counted_build(session, *, persist=False):
            calls["count"] += 1
            return original(session, persist=persist)

        monkeypatch.setattr(live_scores, "build_command_center_report", counted_build)

        first = live_scores.cached_command_center_report(session)
        second = live_scores.cached_command_center_report(session)
        refreshed = live_scores.cached_command_center_report(session, force_refresh=True)

        assert calls["count"] == 2
        assert first.cache_status == "fresh"
        assert second.cache_status == "cached"
        assert refreshed.cache_status == "fresh"


def test_tracked_background_task_records_exception() -> None:
    async def broken():
        raise RuntimeError("boom")

    async def scenario():
        await runner_module._tracked_background_task(broken(), task_name="test_broken")

    asyncio.run(scenario())

    snapshot = freeze_watchdog.summary()
    assert snapshot["last_exception_type"] == "RuntimeError"
    assert snapshot["last_exception_route"] == "test_broken"


def test_test_s3_storage_command_schedules_background_job_without_inline_provider_call(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSessionLocal() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=6701, owner_telegram_id=6701, display_name="Owner")
        session.add(
            BackupStorageTarget(
                name="S3-Compatible Backup Storage",
                target_type="s3_compatible",
                enabled=True,
                encrypted=True,
                connection_status="pending",
            )
        )
        session.commit()

    message = _FakeTelegramMessage()
    message.text = "/test_s3_storage"
    scheduled: list[str] = []

    def fail_if_inline(*args, **kwargs):
        raise AssertionError("storage provider test must not run inline")

    def fake_background(coro, *, task_name):
        scheduled.append(task_name)
        coro.close()
        return None

    monkeypatch.setattr(runner_module, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(runner_module.settings, "owner_telegram_id", 6701, raising=False)
    monkeypatch.setattr(runner_module, "test_storage_target_connection", fail_if_inline)
    monkeypatch.setattr(runner_module, "_tracked_background_task", fake_background)

    asyncio.run(runner_module.shortcut_command(message))

    assert scheduled == ["backup_storage_test"]
    assert any("S3-Compatible" in answer or "Backup Storage" in answer for answer in message.answers)


def test_verify_navigation_harness_reports_passed_routes(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        result = run_command_verification_harness(session, actor=owner)
        screen = render_reliability_verify_page(session, owner)

        assert len(result.passed) >= 10
        assert result.callback_issue_count >= 0
        assert (
            session.query(CallbackLatencyRecord)
            .filter(
                CallbackLatencyRecord.callback_route == "command:verify_navigation",
                CallbackLatencyRecord.result == "succeeded",
            )
            .count()
            >= 1
        )
        assert "Navigation Verification" in screen.text
        assert "Passed Routes" in screen.text


def test_verify_navigation_harness_uses_working_state_for_heavy_routes(monkeypatch) -> None:
    import app.services.reliability as reliability_module

    original_render = reliability_module.render_command_shortcut

    def guarded_render(session, *, command, principal, user, chat_id=None, chat_title=None):
        if command in {"coo", "observability"}:
            raise AssertionError("heavy shortcut render should not run inside verification harness")
        return original_render(
            session,
            command=command,
            principal=principal,
            user=user,
            chat_id=chat_id,
            chat_title=chat_title,
        )

    monkeypatch.setattr(reliability_module, "render_command_shortcut", guarded_render)

    with session_scope() as session:
        owner = _owner(session)
        result = run_command_verification_harness(session, actor=owner)

        assert not result.failed
        assert {item.command for item in result.passed}.issuperset({"coo", "observability"})


def test_reliability_command_has_visible_working_state() -> None:
    shortcut = SHORTCUT_BY_COMMAND["reliability"]
    screen = working_screen_for(shortcut)

    assert screen is not None
    assert "Checking reliability" in screen.text
    assert "Fortuna heard you" in screen.text


def test_today_command_has_working_state_and_extended_timeout(monkeypatch) -> None:
    shortcut = SHORTCUT_BY_COMMAND["today"]
    screen = working_screen_for(shortcut)

    monkeypatch.setattr(runner_module, "SIMPLE_RENDER_TIMEOUT_SECONDS", 3.0)

    assert screen is not None
    assert "Checking today" in screen.text
    assert runner_module._render_timeout_for_page("today_priorities") >= 15.0


def test_verify_navigation_screen_falls_back_when_harness_fails(monkeypatch) -> None:
    import app.bot.screens.reliability as reliability_screen_module

    monkeypatch.setattr(
        reliability_screen_module,
        "run_command_verification_harness",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with session_scope() as session:
        owner = _owner(session)
        screen = render_reliability_verify_page(session, owner)

        assert "Navigation Verification" in screen.text
        assert "could not finish safely (RuntimeError)" in screen.text


def test_reliability_center_excludes_historical_when_healthy() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screen = render_reliability_center_page(session, owner)

        assert "Reliability Center" in screen.text
        assert "Status:" in screen.text
        assert "Active Issues:" in screen.text
        assert "Button Reliability:" not in screen.text
        assert "Problem Buttons" in str(screen.reply_markup)


def test_recent_failed_job_counts_as_reliability_issue() -> None:
    with session_scope() as session:
        owner = _owner(session)
        start_reliability_job(session, job_id="backup:failed", job_type="backup", status="running")
        update_reliability_job(
            session,
            "backup:failed",
            status="failed",
            current_step="Backup failed safely",
            safe_error_summary="Storage provider returned HTTP 403.",
        )

        summary = reliability_summary(session)
        screen = render_reliability_center_page(session, owner)

        assert summary["status"] == "needs_review"
        assert summary["active_issue_count"] >= 1
        assert "Recent Backup: Failed" in screen.text


def test_newer_completed_job_retires_failed_job_from_active_reliability() -> None:
    with session_scope() as session:
        owner = _owner(session)
        now = datetime.now(UTC)
        start_reliability_job(session, job_id="backup:failed", job_type="backup", status="running")
        update_reliability_job(
            session,
            "backup:failed",
            status="failed",
            current_step="Backup failed safely",
            safe_error_summary="Storage provider returned HTTP 403.",
        )
        failed = session.query(ReliabilityJob).filter_by(job_id="backup:failed").one()
        failed.updated_at = now - timedelta(minutes=5)

        start_reliability_job(session, job_id="backup:completed", job_type="backup", status="running")
        update_reliability_job(
            session,
            "backup:completed",
            status="completed",
            current_step="Backup verified",
            result_summary="Backup completed after key rotation.",
        )
        completed = session.query(ReliabilityJob).filter_by(job_id="backup:completed").one()
        completed.updated_at = now
        session.flush()

        summary = reliability_summary(session)
        screen = render_reliability_center_page(session, owner)

        assert summary["status"] == "healthy"
        assert summary["active_issue_count"] == 0
        assert summary["failed_jobs"] == []
        assert "Recent Backup: Failed" not in screen.text


def test_backup_history_shows_safe_failure_reason() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            BackupRun(
                run_identifier="backup-failed",
                backup_type="manual",
                status="failed",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                storage_target="S3-Compatible Backup Storage",
                encrypted=True,
                checksum="abc123",
                error_summary="Storage provider returned HTTP 403.",
            )
        )
        session.flush()

        screen = render_backup_history_page(session, owner)

        assert "Reason: Storage provider returned HTTP 403." in screen.text
        assert "abc123" not in screen.text


def test_slow_callback_appears_in_reliability_and_observability() -> None:
    with session_scope() as session:
        owner = _owner(session)
        now = datetime.now(UTC)
        record_callback_latency(
            session,
            CallbackTiming(
                callback_route="ai_brain:evidence",
                received_at=now,
                acknowledged_at=now + timedelta(milliseconds=50),
                render_started_at=now + timedelta(milliseconds=100),
                render_finished_at=now + timedelta(milliseconds=3200),
                edit_or_send_completed_at=now + timedelta(milliseconds=3500),
            ),
            result="succeeded",
        )

        screen = render_page("reliability:slow", session=session, user=owner)
        summary = production_observability_summary(session)

        assert "AI Brain Evidence" in screen.text
        assert "ai_brain:evidence" not in screen.text
        assert summary["reliability_status"] == "needs_review"
        assert summary["reliability_slowest_area"] == "ai_brain:evidence"


def test_new_selftest_success_retires_stale_speed_note() -> None:
    with session_scope() as session:
        now = datetime.now(UTC)
        record_callback_latency(
            session,
            CallbackTiming(
                callback_route="selftest",
                received_at=now - timedelta(minutes=5),
                acknowledged_at=now - timedelta(minutes=5),
                render_started_at=now - timedelta(minutes=5),
                render_finished_at=now - timedelta(minutes=5) + timedelta(milliseconds=3200),
                edit_or_send_completed_at=now - timedelta(minutes=5) + timedelta(milliseconds=3500),
            ),
            result="succeeded",
        )
        record_callback_latency(
            session,
            CallbackTiming(
                callback_route="command:selftest",
                received_at=now,
                acknowledged_at=now + timedelta(milliseconds=100),
                render_started_at=now + timedelta(milliseconds=100),
                render_finished_at=now + timedelta(milliseconds=100),
                edit_or_send_completed_at=now + timedelta(milliseconds=100),
            ),
            result="succeeded",
        )

        summary = reliability_summary(session)

        assert summary["status"] == "healthy"
        assert summary["slowest_area"] == "None"
        assert summary["slow_records"] == []


def test_verify_navigation_summary_latency_is_not_a_slow_button_note() -> None:
    with session_scope() as session:
        now = datetime.now(UTC)
        record_callback_latency(
            session,
            CallbackTiming(
                callback_route="command:verify_navigation",
                received_at=now,
                acknowledged_at=now + timedelta(milliseconds=100),
                render_started_at=now + timedelta(milliseconds=100),
                render_finished_at=now + timedelta(milliseconds=5000),
                edit_or_send_completed_at=now + timedelta(milliseconds=5000),
            ),
            result="succeeded",
            metadata={"verification_harness": True, "summary": True},
        )

        summary = reliability_summary(session)

        assert summary["status"] == "healthy"
        assert summary["slowest_area"] == "None"
        assert summary["slow_records"] == []


def test_route_health_registry_contains_required_fields() -> None:
    with session_scope() as session:
        entries = route_health_registry(session)
        home = next(item for item in entries if item.route_name == "command:home")

        assert home.display_label
        assert home.parent_route
        assert isinstance(home.owner_only, bool)
        assert home.expected_render_function == "menu"
        assert home.health_status in {"healthy", "needs_review", "failing", "disabled_safe"}
        assert isinstance(home.average_latency_ms, int)


def test_shortcut_registry_contains_required_commands() -> None:
    required = {
        "home",
        "more",
        "coo",
        "today",
        "agency",
        "agency_active",
        "agency_missing",
        "agency_connected",
        "ai",
        "ai_settings",
        "ai_critic",
        "ai_evidence",
        "ai_coo",
        "search",
        "search_settings",
        "search_history",
        "recovery",
        "backup_storage",
        "s3_storage",
        "activate_s3_storage",
        "test_s3_storage",
        "backup_history",
        "run_backup",
        "restore_test",
        "reliability",
        "callback_failures",
        "button_health",
        "notifications",
        "platforms",
        "decision_memory",
        "reality",
        "intelligence",
        "observability",
        "verify_navigation",
    }

    assert required.issubset(set(SHORTCUT_BY_COMMAND))
