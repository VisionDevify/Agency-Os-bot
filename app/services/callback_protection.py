from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol
from uuid import uuid4

from redis import Redis


@dataclass(frozen=True)
class LockHandle:
    key: str
    owner_id: str
    expires_at_epoch: float
    backend: str = "memory"


@dataclass
class SafeRenderResult:
    success: bool
    edited: bool = False
    sent_new_message: bool = False
    message_id: Optional[int] = None
    outcome: str = "unknown"


class CallbackLockManagerProtocol(Protocol):
    async def acquire_callback_lock(
        self,
        *,
        chat_id: int,
        user_id: int,
        ttl_seconds: int = 5,
    ) -> Optional[LockHandle]:
        ...

    async def acquire_message_edit_lock(
        self,
        *,
        chat_id: int,
        message_id: int,
        ttl_seconds: int = 5,
    ) -> Optional[LockHandle]:
        ...

    async def release(self, handle: LockHandle) -> None:
        ...

    async def is_locked(self, key: str) -> bool:
        ...

    async def health_check(self) -> dict[str, object]:
        ...


class RedisIdempotencyStoreProtocol(Protocol):
    async def mark_callback_seen(
        self,
        *,
        fingerprint: str,
        ttl_seconds: int,
    ) -> bool:
        ...

    async def callback_seen(self, fingerprint: str) -> bool:
        ...

    async def reserve_action(
        self,
        *,
        action_type: str,
        action_id: str,
        ttl_seconds: int,
    ) -> bool:
        ...

    async def store_action_result(
        self,
        *,
        action_type: str,
        action_id: str,
        result: dict,
        ttl_seconds: int,
    ) -> None:
        ...

    async def get_action_result(
        self,
        *,
        action_type: str,
        action_id: str,
    ) -> Optional[dict]:
        ...


class CallbackLockManager:
    def __init__(self, redis_url: str | None = None, *, client: Redis | None = None) -> None:
        self.redis_url = redis_url or ""
        self.client = client
        self.redis_enabled = bool(redis_url or client)
        self.redis_degraded = False
        self.lock_contention_count = 0
        self.redis_error_count = 0
        self._locks: dict[str, asyncio.Lock] = {}
        self._owners: dict[str, LockHandle] = {}

    def _client(self) -> Redis:
        if self.client is None:
            self.client = Redis.from_url(self.redis_url, socket_connect_timeout=1, socket_timeout=1)
        return self.client

    async def acquire_callback_lock(
        self,
        *,
        chat_id: int,
        user_id: int,
        ttl_seconds: int = 5,
    ) -> Optional[LockHandle]:
        return await self._acquire(f"callback_lock:{chat_id}:{user_id}", ttl_seconds=ttl_seconds)

    async def acquire_message_edit_lock(
        self,
        *,
        chat_id: int,
        message_id: int,
        ttl_seconds: int = 5,
    ) -> Optional[LockHandle]:
        return await self._acquire(f"message_edit_lock:{chat_id}:{message_id}", ttl_seconds=ttl_seconds)

    async def acquire_cleanup_lock(
        self,
        *,
        chat_id: int,
        ttl_seconds: int = 10,
    ) -> Optional[LockHandle]:
        return await self._acquire(f"cleanup_lock:{chat_id}", ttl_seconds=ttl_seconds)

    async def _acquire(self, key: str, *, ttl_seconds: int) -> Optional[LockHandle]:
        ttl_seconds = max(1, min(int(ttl_seconds), 30))
        owner_id = str(uuid4())
        expires = time.time() + ttl_seconds
        if self.redis_enabled and not self.redis_degraded:
            try:
                acquired = bool(self._client().set(key, owner_id, nx=True, ex=ttl_seconds))
                if acquired:
                    return LockHandle(key=key, owner_id=owner_id, expires_at_epoch=expires, backend="redis")
                self.lock_contention_count += 1
                return None
            except Exception:
                self.redis_error_count += 1
                self.redis_degraded = True

        lock = self._locks.setdefault(key, asyncio.Lock())
        current = self._owners.get(key)
        if current is not None and current.expires_at_epoch <= time.time() and lock.locked():
            with contextlib.suppress(RuntimeError):
                lock.release()
            self._owners.pop(key, None)
        if lock.locked():
            self.lock_contention_count += 1
            return None
        await lock.acquire()
        handle = LockHandle(key=key, owner_id=owner_id, expires_at_epoch=expires, backend="memory")
        self._owners[key] = handle
        return handle

    async def release(self, handle: LockHandle) -> None:
        if handle.backend == "redis" and self.redis_enabled:
            try:
                script = """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                end
                return 0
                """
                self._client().eval(script, 1, handle.key, handle.owner_id)
                return
            except Exception:
                self.redis_error_count += 1
                self.redis_degraded = True
        lock = self._locks.get(handle.key)
        current = self._owners.get(handle.key)
        if lock is not None and lock.locked() and (current is None or current.owner_id == handle.owner_id):
            with contextlib.suppress(RuntimeError):
                lock.release()
        if current is None or current.owner_id == handle.owner_id:
            self._owners.pop(handle.key, None)

    async def is_locked(self, key: str) -> bool:
        if self.redis_enabled and not self.redis_degraded:
            try:
                return bool(self._client().exists(key))
            except Exception:
                self.redis_error_count += 1
                self.redis_degraded = True
        lock = self._locks.get(key)
        current = self._owners.get(key)
        if current is not None and current.expires_at_epoch <= time.time():
            return False
        return bool(lock and lock.locked())

    async def health_check(self) -> dict[str, object]:
        backend = "redis" if self.redis_enabled and not self.redis_degraded else "memory"
        healthy = True
        if self.redis_enabled and not self.redis_degraded:
            try:
                healthy = bool(self._client().ping())
            except Exception:
                healthy = False
                self.redis_error_count += 1
                self.redis_degraded = True
                backend = "memory"
        return {
            "backend": backend,
            "redis_configured": self.redis_enabled,
            "redis_degraded": self.redis_degraded,
            "healthy": healthy,
            "lock_contention_count": self.lock_contention_count,
            "redis_error_count": self.redis_error_count,
        }


class RedisIdempotencyStore:
    def __init__(self, redis_url: str | None = None, *, client: Redis | None = None) -> None:
        self.redis_url = redis_url or ""
        self.client = client
        self.redis_enabled = bool(redis_url or client)
        self.redis_degraded = False
        self.redis_error_count = 0
        self.duplicate_count = 0
        self._seen: dict[str, float] = {}
        self._results: dict[str, tuple[float, dict]] = {}

    def _client(self) -> Redis:
        if self.client is None:
            self.client = Redis.from_url(self.redis_url, socket_connect_timeout=1, socket_timeout=1)
        return self.client

    async def mark_callback_seen(
        self,
        *,
        fingerprint: str,
        ttl_seconds: int,
    ) -> bool:
        key = f"callback_seen:{fingerprint}"
        return await self._mark_seen(key, ttl_seconds=ttl_seconds)

    async def callback_seen(self, fingerprint: str) -> bool:
        key = f"callback_seen:{fingerprint}"
        return await self._seen_key(key)

    async def reserve_action(
        self,
        *,
        action_type: str,
        action_id: str,
        ttl_seconds: int,
    ) -> bool:
        key = f"action_seen:{_hash_part(action_type)}:{_hash_part(action_id)}"
        return await self._mark_seen(key, ttl_seconds=ttl_seconds)

    async def store_action_result(
        self,
        *,
        action_type: str,
        action_id: str,
        result: dict,
        ttl_seconds: int,
    ) -> None:
        key = self._result_key(action_type, action_id)
        ttl_seconds = max(1, int(ttl_seconds))
        if self.redis_enabled and not self.redis_degraded:
            try:
                self._client().set(key, json.dumps(result, default=str), ex=ttl_seconds)
                return
            except Exception:
                self.redis_error_count += 1
                self.redis_degraded = True
        self._purge()
        self._results[key] = (time.time() + ttl_seconds, dict(result))

    async def get_action_result(
        self,
        *,
        action_type: str,
        action_id: str,
    ) -> Optional[dict]:
        key = self._result_key(action_type, action_id)
        if self.redis_enabled and not self.redis_degraded:
            try:
                raw = self._client().get(key)
                if raw is None:
                    return None
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(str(raw))
            except Exception:
                self.redis_error_count += 1
                self.redis_degraded = True
        self._purge()
        item = self._results.get(key)
        return dict(item[1]) if item is not None else None

    async def _mark_seen(self, key: str, *, ttl_seconds: int) -> bool:
        ttl_seconds = max(1, int(ttl_seconds))
        if self.redis_enabled and not self.redis_degraded:
            try:
                is_new = bool(self._client().set(key, "1", nx=True, ex=ttl_seconds))
                if not is_new:
                    self.duplicate_count += 1
                return is_new
            except Exception:
                self.redis_error_count += 1
                self.redis_degraded = True
        self._purge()
        if key in self._seen:
            self.duplicate_count += 1
            return False
        self._seen[key] = time.time() + ttl_seconds
        return True

    async def _seen_key(self, key: str) -> bool:
        if self.redis_enabled and not self.redis_degraded:
            try:
                return bool(self._client().exists(key))
            except Exception:
                self.redis_error_count += 1
                self.redis_degraded = True
        self._purge()
        return key in self._seen

    def _purge(self) -> None:
        now = time.time()
        self._seen = {key: expires for key, expires in self._seen.items() if expires > now}
        self._results = {key: value for key, value in self._results.items() if value[0] > now}

    @staticmethod
    def _result_key(action_type: str, action_id: str) -> str:
        return f"action_result:{_hash_part(action_type)}:{_hash_part(action_id)}"


def callback_fingerprint(callback_query: Any, *, active_navigation_version: str | None = None) -> str:
    message = getattr(callback_query, "message", None)
    chat = getattr(message, "chat", None)
    from_user = getattr(callback_query, "from_user", None)
    parts = [
        str(getattr(chat, "id", "")),
        str(getattr(from_user, "id", "")),
        str(getattr(message, "message_id", "")),
        str(getattr(callback_query, "data", "")),
        active_navigation_version or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def safe_action_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def classify_telegram_error(exc: BaseException) -> str:
    text = str(exc).casefold()
    if "message is not modified" in text:
        return "harmless_duplicate"
    if "query is too old" in text or "callback query" in text and "expired" in text:
        return "stale_callback"
    if "message to edit not found" in text or "can't be edited" in text or "cannot be edited" in text:
        return "edit_conflict"
    if "retry after" in text or "flood" in text:
        return "telegram_retry"
    if "forbidden" in text or "bot was blocked" in text:
        return "telegram_forbidden"
    if "timeout" in text or "connection reset" in text or "network" in text:
        return "telegram_network"
    return "unexpected_error"


def _hash_part(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:32]
