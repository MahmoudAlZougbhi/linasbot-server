"""Bounded process/file/Postgres lock for Facebook Page ``subscribed_apps`` writes."""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import math
import os
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from services.meta_app_registry_common import MetaRegistryError

if TYPE_CHECKING:
    from services.meta_app_registry import MetaAppRegistry

MetaPageLockBackend = Literal["file", "postgres", "dual"]

_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCK_ACQUIRE_TIMEOUT_SECONDS = 30.0
_LOCK_RETRY_INTERVAL_SECONDS = 0.05
_PG_RELEASE_TIMEOUT_MILLISECONDS = 2_000


class MetaOAuthPageLockError(MetaRegistryError):
    """The provider mutation lock could not be acquired safely."""


@dataclass(frozen=True)
class FacebookPageLockTarget:
    """Minimum durable-store information needed by an ops-script lock."""

    backend: MetaPageLockBackend
    lock_path: Path
    database_url: str = field(default="", repr=False)

    @property
    def _backend(self) -> MetaPageLockBackend:
        return self.backend


@dataclass(frozen=True)
class _AsyncLockOwnership:
    owner: asyncio.Task[Any]
    names: frozenset[str]


_ASYNC_LOCK_OWNERSHIP: contextvars.ContextVar[_AsyncLockOwnership | None] = contextvars.ContextVar(
    "meta_page_subscription_lock_ownership",
    default=None,
)
_SYNC_LOCK_OWNERSHIP = threading.local()


def page_lock_target_from_environment() -> FacebookPageLockTarget:
    """Resolve the same backend/lock path used by the default Meta registry."""

    from services.meta_app_registry_backend import resolve_meta_registry_backend
    from storage.persistent_storage import get_data_root

    return FacebookPageLockTarget(
        backend=resolve_meta_registry_backend(),
        lock_path=get_data_root() / "meta_registry" / "registry.lock",
        database_url=(os.getenv("LINAS_WHATSAPP_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip(),
    )


def page_lock_target_from_env_file(path: Path) -> FacebookPageLockTarget:
    """Resolve lock settings from the root-owned env used by privileged scripts."""

    from dotenv import dotenv_values

    from services.meta_app_registry_backend import resolve_meta_registry_backend
    from storage.persistent_storage import get_data_root

    if not path.is_file():
        return page_lock_target_from_environment()
    parsed = dotenv_values(path, interpolate=False)
    raw_backend = str(parsed.get("META_REGISTRY_BACKEND") or os.getenv("META_REGISTRY_BACKEND") or "postgres")
    backend = raw_backend.strip().lower()
    if backend not in {"file", "postgres", "dual"}:
        # Reuse the canonical public validation/error contract when ambient env
        # was selected; otherwise fail with the lock-specific safe message.
        if parsed.get("META_REGISTRY_BACKEND") is None:
            resolve_meta_registry_backend()
        raise MetaOAuthPageLockError("Facebook Page subscription lock backend is invalid")
    raw_root = str(parsed.get("LINASBOT_DATA_ROOT") or os.getenv("LINASBOT_DATA_ROOT") or "").strip()
    data_root = Path(raw_root).expanduser().resolve() if raw_root else get_data_root()
    lock_database_url = str(
        parsed.get("LINAS_WHATSAPP_DATABASE_URL")
        or parsed.get("DATABASE_URL")
        or os.getenv("LINAS_WHATSAPP_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    return FacebookPageLockTarget(
        backend=cast(MetaPageLockBackend, backend),
        lock_path=data_root / "meta_registry" / "registry.lock",
        database_url=lock_database_url,
    )


def _lock_names(*, app_key: str, page_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Use a Page-wide key so all apps and all internal writers serialize."""

    normalized_pages = sorted({str(page_id or "").strip() for page_id in page_ids if str(page_id or "").strip()})
    if not app_key.strip() or not normalized_pages:
        raise MetaOAuthPageLockError("Facebook Page subscription lock requires an app and Page")
    return tuple(f"meta-page-subscribed-apps:{page_id}" for page_id in normalized_pages)


def _local_lock(name: str) -> threading.Lock:
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(name, threading.Lock())


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


async def _acquire_local_lock(lock: threading.Lock, *, deadline: float) -> None:
    """Acquire without a background waiter that could outlive cancellation."""

    while not lock.acquire(blocking=False):
        remaining = _remaining(deadline)
        if remaining <= 0:
            raise MetaOAuthPageLockError("Facebook Page subscription process lock timed out")
        await asyncio.sleep(min(_LOCK_RETRY_INTERVAL_SECONDS, remaining))


def _acquire_local_lock_sync(lock: threading.Lock, *, deadline: float) -> None:
    while not lock.acquire(blocking=False):
        remaining = _remaining(deadline)
        if remaining <= 0:
            raise MetaOAuthPageLockError("Facebook Page subscription process lock timed out")
        time.sleep(min(_LOCK_RETRY_INTERVAL_SECONDS, remaining))


def _postgres_lock_key(name: str) -> int:
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big", signed=True)


def _file_lock_path(registry: MetaAppRegistry | FacebookPageLockTarget, name: str) -> Path:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
    base = Path(registry.lock_path)
    return base.with_name(f"{base.name}.page-subscription-{digest}")


def _registry_backend(registry: MetaAppRegistry | FacebookPageLockTarget) -> MetaPageLockBackend:
    backend = str(getattr(registry, "_backend", "") or "").strip().lower()
    if backend not in {"file", "postgres", "dual"}:
        raise MetaOAuthPageLockError("Facebook Page subscription lock backend is invalid")
    return cast(MetaPageLockBackend, backend)


def _create_dedicated_postgres_engine(*, deadline: float, database_url_override: str = "") -> Any:
    """Create a one-use physical connection pool with bounded connect time.

    Advisory locks are session scoped. A pooled application session could return
    a still-locked connection to the pool after an error, so this engine always
    uses ``NullPool`` and is disposed after the lock worker exits.
    """

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from db.session import _normalize_database_url, database_url

    raw_url = database_url_override.strip() or database_url()
    if not raw_url:
        raise MetaOAuthPageLockError("Facebook Page subscription database lock is unavailable")
    url = _normalize_database_url(raw_url)
    if not (url.startswith("postgresql://") or url.startswith("postgresql+psycopg2://")):
        raise MetaOAuthPageLockError("Facebook Page subscription lock requires PostgreSQL")
    remaining = _remaining(deadline)
    if remaining <= 0:
        raise MetaOAuthPageLockError("Facebook Page subscription database lock timed out")
    connect_timeout_seconds = math.floor(remaining)
    if connect_timeout_seconds < 1:
        raise MetaOAuthPageLockError("Facebook Page subscription database lock timed out")
    statement_timeout_ms = max(1, math.floor(remaining * 1_000))
    return create_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": connect_timeout_seconds,
            "options": f"-c statement_timeout={statement_timeout_ms}",
        },
        future=True,
    )


def _set_statement_timeout(connection: Any, *, deadline: float) -> None:
    from sqlalchemy import text

    remaining_ms = max(1, math.floor(_remaining(deadline) * 1_000))
    connection.execute(
        text("SELECT set_config('statement_timeout', :timeout, false)"),
        {"timeout": f"{remaining_ms}ms"},
    )


class _DurableLockWorker:
    """Hold file/dedicated-Postgres session locks without blocking asyncio."""

    def __init__(
        self,
        registry: MetaAppRegistry | FacebookPageLockTarget,
        names: tuple[str, ...],
        *,
        deadline: float,
    ) -> None:
        self._registry = registry
        self._names = names
        self._deadline = deadline
        self.acquired = threading.Event()
        self.release = threading.Event()
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, name="meta-page-subscription-lock", daemon=True)

    def _run(self) -> None:
        file_handles: list[Any] = []
        pg_engine: Any = None
        pg_connection: Any = None
        pg_keys: list[int] = []
        try:
            backend = _registry_backend(self._registry)
            if backend in {"file", "dual"}:
                import fcntl

                for name in self._names:
                    path = _file_lock_path(self._registry, name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    handle = path.open("a+", encoding="utf-8")
                    os.chmod(path, 0o600)
                    while True:
                        if self.release.is_set() or _remaining(self._deadline) <= 0:
                            handle.close()
                            raise MetaOAuthPageLockError("Facebook Page subscription file lock timed out")
                        try:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            self.release.wait(min(_LOCK_RETRY_INTERVAL_SECONDS, _remaining(self._deadline)))
                    file_handles.append(handle)

            if backend in {"postgres", "dual"}:
                from sqlalchemy import text

                pg_engine = _create_dedicated_postgres_engine(
                    deadline=self._deadline,
                    database_url_override=str(getattr(self._registry, "database_url", "") or ""),
                )
                pg_connection = pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
                _set_statement_timeout(pg_connection, deadline=self._deadline)
                for name in self._names:
                    key = _postgres_lock_key(name)
                    while True:
                        if self.release.is_set() or _remaining(self._deadline) <= 0:
                            raise MetaOAuthPageLockError("Facebook Page subscription database lock timed out")
                        _set_statement_timeout(pg_connection, deadline=self._deadline)
                        acquired = pg_connection.execute(
                            text("SELECT pg_try_advisory_lock(:key)"),
                            {"key": key},
                        ).scalar()
                        if acquired is True:
                            break
                        self.release.wait(min(_LOCK_RETRY_INTERVAL_SECONDS, _remaining(self._deadline)))
                    pg_keys.append(key)

            self.acquired.set()
            self.release.wait()
        except BaseException as exc:  # noqa: BLE001 - forwarded to the awaiting operation
            self.error = exc
            self.acquired.set()
        finally:
            if pg_connection is not None:
                from sqlalchemy import text

                unlock_failed = False
                for key in reversed(pg_keys):
                    try:
                        pg_connection.execute(
                            text("SELECT set_config('statement_timeout', :timeout, false)"),
                            {"timeout": f"{_PG_RELEASE_TIMEOUT_MILLISECONDS}ms"},
                        )
                        pg_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    except Exception:
                        # Closing this NullPool connection releases every remaining
                        # session advisory lock even when an explicit unlock failed.
                        unlock_failed = True
                        break
                if unlock_failed:
                    try:
                        pg_connection.invalidate()
                    except Exception:
                        pass
                try:
                    pg_connection.close()
                except Exception:
                    pass
            if pg_engine is not None:
                try:
                    pg_engine.dispose(close=True)
                except Exception:
                    pass
            if file_handles:
                import fcntl

                for handle in reversed(file_handles):
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        handle.close()


def _raise_worker_error(worker: _DurableLockWorker) -> None:
    if worker.error is None:
        return
    if isinstance(worker.error, MetaOAuthPageLockError):
        raise worker.error
    raise MetaOAuthPageLockError("Facebook Page subscription durable lock could not be acquired") from worker.error


async def _join_worker_shielded(worker: _DurableLockWorker) -> None:
    """Release/join even when the caller is cancelled again during cleanup."""

    worker.release.set()
    join_task = asyncio.create_task(asyncio.to_thread(worker.thread.join))
    cancelled = False
    while not join_task.done():
        try:
            await asyncio.shield(join_task)
        except asyncio.CancelledError:
            cancelled = True
    join_task.result()
    if cancelled:
        raise asyncio.CancelledError


@asynccontextmanager
async def lock_facebook_page_oauth_operation(
    registry: MetaAppRegistry | FacebookPageLockTarget,
    *,
    app_key: str,
    page_ids: tuple[str, ...],
) -> AsyncIterator[None]:
    """Serialize a complete Facebook Page subscription transaction.

    Re-entry is permitted only for the same asyncio task and only for a subset
    of the Pages that task already holds. A child task inherits contextvars but
    never inherits lock ownership.
    """

    names = _lock_names(app_key=app_key, page_ids=page_ids)
    requested = frozenset(names)
    current_task = asyncio.current_task()
    if current_task is None:
        raise MetaOAuthPageLockError("Facebook Page subscription lock requires an asyncio task")
    ownership = _ASYNC_LOCK_OWNERSHIP.get()
    if ownership is not None and ownership.owner is current_task:
        if not requested.issubset(ownership.names):
            raise MetaOAuthPageLockError("Nested Facebook Page subscription lock cannot expand its Page set")
        yield
        return

    deadline = time.monotonic() + _LOCK_ACQUIRE_TIMEOUT_SECONDS
    acquired_local: list[threading.Lock] = []
    worker: _DurableLockWorker | None = None
    ownership_token: contextvars.Token[_AsyncLockOwnership | None] | None = None
    try:
        for name in names:
            lock = _local_lock(name)
            await _acquire_local_lock(lock, deadline=deadline)
            acquired_local.append(lock)

        if _remaining(deadline) <= 0:
            raise MetaOAuthPageLockError("Facebook Page subscription lock timed out")
        worker = _DurableLockWorker(registry, names, deadline=deadline)
        worker.thread.start()
        ready_task = asyncio.create_task(asyncio.to_thread(worker.acquired.wait, max(0.0, _remaining(deadline))))
        ready = await asyncio.shield(ready_task)
        if not ready or _remaining(deadline) <= 0:
            raise MetaOAuthPageLockError("Facebook Page subscription durable lock timed out")
        _raise_worker_error(worker)
        ownership_token = _ASYNC_LOCK_OWNERSHIP.set(_AsyncLockOwnership(owner=current_task, names=requested))
        yield
    finally:
        if ownership_token is not None:
            _ASYNC_LOCK_OWNERSHIP.reset(ownership_token)
        try:
            if worker is not None:
                await _join_worker_shielded(worker)
        finally:
            for lock in reversed(acquired_local):
                lock.release()


@contextmanager
def lock_facebook_page_subscription_operation_sync(
    *,
    app_key: str,
    page_ids: tuple[str, ...],
    target: FacebookPageLockTarget | None = None,
) -> Iterator[None]:
    """Synchronous counterpart used by privileged production ops scripts."""

    names = _lock_names(app_key=app_key, page_ids=page_ids)
    requested = frozenset(names)
    held = cast(frozenset[str] | None, getattr(_SYNC_LOCK_OWNERSHIP, "names", None))
    if held is not None:
        if not requested.issubset(held):
            raise MetaOAuthPageLockError("Nested Facebook Page subscription lock cannot expand its Page set")
        yield
        return

    deadline = time.monotonic() + _LOCK_ACQUIRE_TIMEOUT_SECONDS
    acquired_local: list[threading.Lock] = []
    worker: _DurableLockWorker | None = None
    try:
        for name in names:
            lock = _local_lock(name)
            _acquire_local_lock_sync(lock, deadline=deadline)
            acquired_local.append(lock)
        if _remaining(deadline) <= 0:
            raise MetaOAuthPageLockError("Facebook Page subscription lock timed out")
        worker = _DurableLockWorker(target or page_lock_target_from_environment(), names, deadline=deadline)
        worker.thread.start()
        ready = worker.acquired.wait(max(0.0, _remaining(deadline)))
        if not ready or _remaining(deadline) <= 0:
            raise MetaOAuthPageLockError("Facebook Page subscription durable lock timed out")
        _raise_worker_error(worker)
        _SYNC_LOCK_OWNERSHIP.names = requested
        yield
    finally:
        if hasattr(_SYNC_LOCK_OWNERSHIP, "names"):
            delattr(_SYNC_LOCK_OWNERSHIP, "names")
        if worker is not None:
            worker.release.set()
            worker.thread.join()
        for lock in reversed(acquired_local):
            lock.release()
