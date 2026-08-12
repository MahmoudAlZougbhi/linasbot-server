"""Distributed rate limiting for auth and sensitive mutations.

Backends (via ``RATE_LIMIT_BACKEND``):
  - ``redis`` — shared sliding window (sorted sets); required by default in production
  - ``file`` — durable per-process files under ``_DATA_ROOT/auth/rate_limits`` (non-prod default)
  - ``memory`` — in-process only (dev/test)

Production (``ENVIRONMENT`` / ``ENV`` in ``prod``|``production``) defaults to Redis and
**never** silently falls back to file/memory when Redis is required but unavailable.
Unavailable Redis in fail-closed mode denies the hit (callers may map to 429/503).

Redis URL: ``RATE_LIMIT_REDIS_URL`` or ``REDIS_URL`` or ``LINAS_REDIS_URL``.

This change does **not** provision or activate production Redis.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from storage.persistent_storage import _DATA_ROOT

logger = logging.getLogger(__name__)

BackendName = Literal["redis", "file", "memory"]

_REDIS_HIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 1
  if oldest[2] then
    retry = math.max(1, math.ceil(window - (now - tonumber(oldest[2]))))
  end
  return {0, retry}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window) + 1)
return {1, 0}
"""


class RateLimitUnavailableError(RuntimeError):
    """Raised when a required rate-limit backend cannot serve the request (fail-closed)."""

    def __init__(self, message: str, *, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


def _is_production_env() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower()
    return env in {"prod", "production"}


def _redis_url_from_env() -> str | None:
    raw = (os.getenv("RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL") or os.getenv("LINAS_REDIS_URL") or "").strip()
    return raw or None


def _unavailable_retry_after() -> int:
    try:
        return max(1, int(os.getenv("RATE_LIMIT_UNAVAILABLE_RETRY_AFTER") or "60"))
    except ValueError:
        return 60


class RateLimitService:
    """Sliding-window rate limiter with selectable backends."""

    def __init__(
        self,
        *,
        backend: BackendName | None = None,
        redis_client: Any | None = None,
        redis_url: str | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._local = threading.local()
        self._forced_backend = backend
        self._redis_client = redis_client
        self._redis_url_override = redis_url
        self._redis_script: Any | None = None
        self._memory: dict[str, list[float]] = {}
        self._dir = data_dir or (Path(_DATA_ROOT) / "auth" / "rate_limits")

    def reconfigure(
        self,
        *,
        backend: BackendName | None = None,
        redis_client: Any | None = None,
        redis_url: str | None = None,
        data_dir: Path | None = None,
    ) -> None:
        """Test/helper hook to reset backend selection and clients."""
        with self._lock:
            self._forced_backend = backend
            self._redis_client = redis_client
            self._redis_url_override = redis_url
            self._redis_script = None
            self._memory = {}
            if data_dir is not None:
                self._dir = data_dir
                self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def last_deny_reason(self) -> str | None:
        """Per-thread reason for the most recent denied ``hit`` (e.g. ``backend_unavailable``)."""
        return getattr(self._local, "deny_reason", None)

    def resolve_backend(self) -> BackendName:
        if self._forced_backend is not None:
            return self._forced_backend
        explicit = (os.getenv("RATE_LIMIT_BACKEND") or "").strip().lower()
        if explicit in {"redis", "file", "memory"}:
            return explicit  # type: ignore[return-value]
        if _is_production_env():
            return "redis"
        return "file"

    def _redis_url(self) -> str | None:
        if self._redis_url_override is not None:
            return self._redis_url_override.strip() or None
        return _redis_url_from_env()

    def _get_redis(self) -> Any:
        if self._redis_client is not None:
            return self._redis_client
        url = self._redis_url()
        if not url:
            raise RateLimitUnavailableError(
                "RATE_LIMIT_BACKEND=redis but RATE_LIMIT_REDIS_URL / REDIS_URL / LINAS_REDIS_URL is unset",
                retry_after=_unavailable_retry_after(),
            )
        import redis

        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        self._redis_client = client
        return client

    def _redis_key(self, key: str) -> str:
        prefix = (os.getenv("RATE_LIMIT_KEY_PREFIX") or "linas:rl").strip() or "linas:rl"
        safe = "".join(c if c.isalnum() or c in "-_.:/" else "_" for c in key)[:200]
        return f"{prefix}:{safe}"

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:180]
        return self._dir / f"{safe}.json"

    def _set_deny_reason(self, reason: str | None) -> None:
        self._local.deny_reason = reason

    def _fail_closed_deny(self, message: str) -> tuple[bool, int]:
        retry = _unavailable_retry_after()
        logger.error("rate_limit fail-closed: %s (retry_after=%s)", message, retry)
        self._set_deny_reason("backend_unavailable")
        return False, retry

    def _hit_memory(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        with self._lock:
            timestamps = [t for t in self._memory.get(key, []) if t >= window_start]
            if len(timestamps) >= limit:
                oldest = min(timestamps) if timestamps else now
                retry = max(1, int(window_seconds - (now - oldest)) + 1)
                self._memory[key] = timestamps
                return False, retry
            timestamps.append(now)
            self._memory[key] = timestamps
            return True, 0

    def _hit_file(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        path = self._path(key)
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            timestamps: list[Any] = []
            if path.exists():
                try:
                    timestamps = json.loads(path.read_text(encoding="utf-8")).get("hits") or []
                except Exception:
                    timestamps = []
            timestamps = [float(t) for t in timestamps if float(t) >= window_start]
            if len(timestamps) >= limit:
                oldest = min(timestamps) if timestamps else now
                retry = max(1, int(window_seconds - (now - oldest)) + 1)
                path.write_text(json.dumps({"hits": timestamps}), encoding="utf-8")
                return False, retry
            timestamps.append(now)
            path.write_text(json.dumps({"hits": timestamps}), encoding="utf-8")
            return True, 0

    def _hit_redis(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        rkey = self._redis_key(key)
        client = self._get_redis()
        try:
            if self._redis_script is None:
                try:
                    self._redis_script = client.register_script(_REDIS_HIT_LUA)
                except Exception:
                    self._redis_script = None
            if callable(self._redis_script):
                try:
                    result = self._redis_script(keys=[rkey], args=[now, window_seconds, limit, member])
                    allowed = int(result[0]) == 1
                    retry = int(result[1]) if not allowed else 0
                    return allowed, retry
                except Exception as script_exc:
                    # Some test doubles (older fakeredis) lack EVALSHA — fall back once.
                    logger.warning(
                        "rate_limit Redis Lua unavailable (%s); using pipeline fallback",
                        script_exc,
                    )
                    self._redis_script = None
            return self._hit_redis_pipeline(
                client, rkey, now=now, window_seconds=window_seconds, limit=limit, member=member
            )
        except RateLimitUnavailableError:
            raise
        except Exception as exc:
            raise RateLimitUnavailableError(
                f"Redis rate-limit backend unavailable: {exc}",
                retry_after=_unavailable_retry_after(),
            ) from exc

    def _hit_redis_pipeline(
        self,
        client: Any,
        rkey: str,
        *,
        now: float,
        window_seconds: int,
        limit: int,
        member: str,
    ) -> tuple[bool, int]:
        """Non-Lua sliding window (shared; slightly racy under extreme contention)."""
        pipe = client.pipeline()
        pipe.zremrangebyscore(rkey, "-inf", now - window_seconds)
        pipe.zcard(rkey)
        _rem, count = pipe.execute()
        count = int(count or 0)
        if count >= limit:
            oldest = client.zrange(rkey, 0, 0, withscores=True)
            if oldest:
                retry = max(1, int(window_seconds - (now - float(oldest[0][1]))) + 1)
            else:
                retry = max(1, int(window_seconds))
            return False, retry
        pipe = client.pipeline()
        pipe.zadd(rkey, {member: now})
        pipe.expire(rkey, int(window_seconds) + 1)
        pipe.execute()
        return True, 0

    def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        """
        Record a hit. Returns ``(allowed, retry_after_seconds)``.

        When Redis is required but unavailable, returns ``(False, retry_after)``
        (fail-closed) and sets ``last_deny_reason`` to ``backend_unavailable``.
        Never silently falls back to file/memory in that case.
        """
        self._set_deny_reason(None)
        backend = self.resolve_backend()
        try:
            if backend == "redis":
                return self._hit_redis(key, limit=limit, window_seconds=window_seconds)
            if backend == "memory":
                return self._hit_memory(key, limit=limit, window_seconds=window_seconds)
            return self._hit_file(key, limit=limit, window_seconds=window_seconds)
        except RateLimitUnavailableError as exc:
            # Production (and any explicit redis backend) must not fall back to file.
            return self._fail_closed_deny(str(exc))


rate_limit_service = RateLimitService()
