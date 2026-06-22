from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class FreezeWatchdogSnapshot:
    last_update_received_at: datetime | None
    last_callback_acknowledged_at: datetime | None
    last_successful_render_at: datetime | None
    current_active_route: str | None
    active_background_tasks: int
    pending_task_count: int | None
    last_exception_type: str | None
    last_exception_route: str | None
    last_exception_at: datetime | None
    last_restart_at: datetime
    last_event_loop_lag_ms: int | None
    monotonic_seconds_since_update: int | None


class FreezeWatchdog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.last_update_received_at: datetime | None = None
        self.last_update_monotonic: float | None = None
        self.last_callback_acknowledged_at: datetime | None = None
        self.last_successful_render_at: datetime | None = None
        self.current_active_route: str | None = None
        self.last_exception_type: str | None = None
        self.last_exception_route: str | None = None
        self.last_exception_at: datetime | None = None
        self.last_restart_at = _now()
        self.last_event_loop_lag_ms: int | None = None
        self._active_background_tasks: set[str] = set()

    def record_update_received(self, *, route: str | None = None) -> None:
        with self._lock:
            self.last_update_received_at = _now()
            self.last_update_monotonic = time.monotonic()
            if route:
                self.current_active_route = route[:160]

    def record_callback_acknowledged(self, *, route: str | None = None) -> None:
        with self._lock:
            self.last_callback_acknowledged_at = _now()
            if route:
                self.current_active_route = route[:160]

    def record_render_started(self, route: str) -> None:
        with self._lock:
            self.current_active_route = route[:160]

    def record_render_succeeded(self, route: str) -> None:
        with self._lock:
            self.current_active_route = route[:160]
            self.last_successful_render_at = _now()

    def record_exception(self, *, route: str | None, exc: BaseException | str) -> None:
        exc_type = exc if isinstance(exc, str) else type(exc).__name__
        with self._lock:
            self.last_exception_type = str(exc_type)[:120]
            self.last_exception_route = (route or "unknown")[:160]
            self.last_exception_at = _now()

    def record_task_started(self, task_name: str) -> str:
        name = f"{task_name}:{time.monotonic_ns()}"
        with self._lock:
            self._active_background_tasks.add(name)
        return name

    def record_task_finished(self, task_token: str) -> None:
        with self._lock:
            self._active_background_tasks.discard(task_token)

    def record_event_loop_lag(self, lag_ms: int) -> None:
        with self._lock:
            self.last_event_loop_lag_ms = max(0, int(lag_ms))

    def snapshot(self) -> FreezeWatchdogSnapshot:
        pending_task_count: int | None
        try:
            pending_task_count = sum(1 for task in asyncio.all_tasks() if not task.done())
        except RuntimeError:
            pending_task_count = None
        with self._lock:
            seconds_since_update = (
                int(time.monotonic() - self.last_update_monotonic)
                if self.last_update_monotonic is not None
                else None
            )
            return FreezeWatchdogSnapshot(
                last_update_received_at=self.last_update_received_at,
                last_callback_acknowledged_at=self.last_callback_acknowledged_at,
                last_successful_render_at=self.last_successful_render_at,
                current_active_route=self.current_active_route,
                active_background_tasks=len(self._active_background_tasks),
                pending_task_count=pending_task_count,
                last_exception_type=self.last_exception_type,
                last_exception_route=self.last_exception_route,
                last_exception_at=self.last_exception_at,
                last_restart_at=self.last_restart_at,
                last_event_loop_lag_ms=self.last_event_loop_lag_ms,
                monotonic_seconds_since_update=seconds_since_update,
            )

    def summary(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "last_update_received_at": snap.last_update_received_at,
            "last_callback_acknowledged_at": snap.last_callback_acknowledged_at,
            "last_successful_render_at": snap.last_successful_render_at,
            "current_active_route": snap.current_active_route,
            "active_background_tasks": snap.active_background_tasks,
            "pending_task_count": snap.pending_task_count,
            "last_exception_type": snap.last_exception_type,
            "last_exception_route": snap.last_exception_route,
            "last_exception_at": snap.last_exception_at,
            "last_restart_at": snap.last_restart_at,
            "last_event_loop_lag_ms": snap.last_event_loop_lag_ms,
            "monotonic_seconds_since_update": snap.monotonic_seconds_since_update,
        }


freeze_watchdog = FreezeWatchdog()
