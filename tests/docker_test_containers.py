"""Interrupt-safe disposable PostgreSQL containers for pytest integration tests."""

from __future__ import annotations

import atexit
import fcntl
import os
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ALLOWED_CONTAINER_PREFIXES: tuple[str, ...] = (
    "linas-web-chat-accept-",
    "linas-web-chat-ha-",
    "linas-advisory-lock-",
    "linas-alembic-",
    "linas-debug-",
)

RUN_OWNER_LABEL = "linas.test.run_owner"
LEASE_EXPIRES_LABEL = "linas.test.lease_expires"
LEASE_SECONDS = 900
ORPHAN_MIN_AGE_SECONDS = 120
PURGE_LOCK_PATH = Path(os.environ.get("LINAS_TEST_DOCKER_PURGE_LOCK", "/tmp/linasbot-docker-purge.lock"))

_tracked: set[str] = set()
_lock = threading.Lock()
_handlers_installed = False
_run_owner = os.environ.get("LINAS_TEST_RUN_OWNER") or f"{os.getpid()}-{uuid.uuid4().hex[:8]}"


def current_run_owner() -> str:
    return _run_owner


def is_allowed_test_container(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in ALLOWED_CONTAINER_PREFIXES)


def docker_available() -> bool:
    return subprocess.run(["docker", "info"], check=False, capture_output=True).returncode == 0


@dataclass(frozen=True)
class _ContainerRecord:
    name: str
    run_owner: str
    lease_expires: float | None
    created_at: float | None
    running: bool


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _owner_pid(run_owner: str) -> int | None:
    head = run_owner.split("-", 1)[0]
    if not head.isdigit():
        return None
    return int(head)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _inspect_allowed_containers() -> list[_ContainerRecord]:
    proc = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--format",
            '{{.Names}}\\t{{.Label "'
            + RUN_OWNER_LABEL
            + '"}}\\t{{.Label "'
            + LEASE_EXPIRES_LABEL
            + '"}}\\t{{.Status}}\\t{{.CreatedAt}}',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    records: list[_ContainerRecord] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0].strip() if parts else ""
        if not name or not is_allowed_test_container(name):
            continue
        run_owner = parts[1].strip() if len(parts) > 1 else ""
        lease = _parse_float(parts[2].strip() if len(parts) > 2 else None)
        status = parts[3].strip() if len(parts) > 3 else ""
        created_raw = parts[4].strip() if len(parts) > 4 else ""
        created_at: float | None = None
        if created_raw:
            for fmt in ("%Y-%m-%d %H:%M:%S %z %Z", "%Y-%m-%d %H:%M:%S %z"):
                try:
                    created_at = datetime.strptime(created_raw, fmt).timestamp()
                    break
                except ValueError:
                    continue
        records.append(
            _ContainerRecord(
                name=name,
                run_owner=run_owner,
                lease_expires=lease,
                created_at=created_at,
                running=status.lower().startswith("up"),
            )
        )
    return records


def _is_proven_orphan(record: _ContainerRecord, *, now: float) -> bool:
    with _lock:
        if record.name in _tracked:
            return False
    if record.run_owner:
        owner_pid = _owner_pid(record.run_owner)
        if owner_pid is not None and _pid_alive(owner_pid):
            return False
        if record.lease_expires is not None and record.lease_expires > now and record.running:
            return False
        return True
    if record.created_at is None:
        return False
    return (now - record.created_at) >= ORPHAN_MIN_AGE_SECONDS


def _container_labels_match(name: str, *, run_owner: str, lease_expires: float) -> bool:
    proc = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            '{{index .Config.Labels "' + RUN_OWNER_LABEL + '"}} {{index .Config.Labels "' + LEASE_EXPIRES_LABEL + '"}}',
            name,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False
    parts = proc.stdout.strip().split()
    if len(parts) < 2:
        return False
    return parts[0] == run_owner and parts[1] == str(int(lease_expires))


@contextmanager
def _global_purge_lock() -> Iterator[None]:
    PURGE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PURGE_LOCK_PATH.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def list_stale_test_containers() -> list[str]:
    now = time.time()
    return sorted(record.name for record in _inspect_allowed_containers() if _is_proven_orphan(record, now=now))


def stop_disposable_container(name: str, *, owner: str | None = None) -> None:
    if not is_allowed_test_container(name):
        return
    expected_owner = owner or _run_owner
    proc = subprocess.run(
        ["docker", "inspect", "-f", '{{index .Config.Labels "' + RUN_OWNER_LABEL + '"}}', name],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        label_owner = proc.stdout.strip()
        if label_owner and label_owner != expected_owner:
            return
    subprocess.run(["docker", "stop", "-t", "2", name], check=False, capture_output=True)
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)


def _remove_owned_container(name: str, run_owner: str) -> str | None:
    if not is_allowed_test_container(name):
        return None
    inspect = subprocess.run(
        ["docker", "inspect", "-f", '{{index .Config.Labels "' + RUN_OWNER_LABEL + '"}}', name],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        return f"docker inspect failed for {name}: {inspect.stderr.strip() or inspect.stdout.strip()}"
    label_owner = inspect.stdout.strip()
    if label_owner != run_owner:
        return None
    stop = subprocess.run(["docker", "stop", "-t", "2", name], check=False, capture_output=True, text=True)
    if stop.returncode != 0:
        return f"docker stop failed for {name}: {stop.stderr.strip() or stop.stdout.strip()}"
    remove = subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True, text=True)
    if remove.returncode != 0:
        return f"docker rm failed for {name}: {remove.stderr.strip() or remove.stdout.strip()}"
    with _lock:
        _tracked.discard(name)
    return None


def list_owned_test_containers(run_owner: str) -> tuple[list[str], str | None]:
    proc = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--format",
            '{{.Names}}\\t{{.Label "' + RUN_OWNER_LABEL + '"}}',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "docker ps failed"
        return [], f"docker inspection failed: {detail}"
    owned: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0].strip() if parts else ""
        if not name or not is_allowed_test_container(name):
            continue
        label = parts[1].strip() if len(parts) > 1 else ""
        if label == run_owner:
            owned.append(name)
    return sorted(owned), None


def purge_owned_test_containers(run_owner: str) -> tuple[list[str], str | None]:
    """Remove only containers labeled for this run; never purge foreign owners."""
    removed: list[str] = []
    with _global_purge_lock():
        owned, list_error = list_owned_test_containers(run_owner)
        if list_error:
            return removed, list_error
        for name in owned:
            error = _remove_owned_container(name, run_owner)
            if error:
                return removed, error
            removed.append(name)
        remaining, verify_error = list_owned_test_containers(run_owner)
        if verify_error:
            return removed, verify_error
        if remaining:
            return removed, f"owned containers remain after purge: {remaining}"
    return sorted(removed), None


def purge_stale_test_containers() -> list[str]:
    purged: list[str] = []
    now = time.time()
    with _global_purge_lock():
        for record in list(_inspect_allowed_containers()):
            if not _is_proven_orphan(record, now=now):
                continue
            refreshed = next((item for item in _inspect_allowed_containers() if item.name == record.name), None)
            if refreshed is None or not _is_proven_orphan(refreshed, now=time.time()):
                continue
            stop_disposable_container(record.name, owner=record.run_owner or _run_owner)
            purged.append(record.name)
    return sorted(purged)


def cleanup_tracked_containers() -> None:
    _cleanup_tracked()


def _cleanup_tracked() -> None:
    with _lock:
        names = list(_tracked)
    for name in names:
        stop_disposable_container(name, owner=_run_owner)
    with _lock:
        for name in names:
            _tracked.discard(name)


def _signal_cleanup(signum: int, _frame: object | None) -> None:
    _cleanup_tracked()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def install_interrupt_safe_cleanup() -> None:
    global _handlers_installed
    if _handlers_installed:
        return
    _handlers_installed = True
    os.environ.setdefault("LINAS_TEST_RUN_OWNER", _run_owner)
    atexit.register(_cleanup_tracked)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_cleanup)
        except (ValueError, OSError):
            pass


def register_disposable_container(name: str) -> None:
    if not is_allowed_test_container(name):
        raise ValueError(f"container name must use allowed test prefix: {name!r}")
    install_interrupt_safe_cleanup()
    with _lock:
        _tracked.add(name)


def unregister_disposable_container(name: str) -> None:
    with _lock:
        _tracked.discard(name)


def _assert_allowed_prefix(container_prefix: str) -> None:
    expected = tuple(prefix.rstrip("-") for prefix in ALLOWED_CONTAINER_PREFIXES)
    if container_prefix not in expected:
        raise ValueError(f"container_prefix must be one of {expected!r}, got {container_prefix!r}")


def start_disposable_postgres(
    *,
    db_name: str,
    container_prefix: str,
    wait_for_ready: Callable[[str], None],
) -> Iterator[str]:
    """Start a local disposable PostgreSQL container and yield its SQLAlchemy URL."""
    _assert_allowed_prefix(container_prefix)
    if not docker_available():
        raise RuntimeError("Docker is required to start disposable PostgreSQL")

    name = f"{container_prefix}-{uuid.uuid4().hex[:8]}"
    lease_expires = time.time() + LEASE_SECONDS
    register_disposable_container(name)
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "--label",
            f"{RUN_OWNER_LABEL}={_run_owner}",
            "--label",
            f"{LEASE_EXPIRES_LABEL}={int(lease_expires)}",
            "-e",
            "POSTGRES_PASSWORD=linas-test",
            "-e",
            f"POSTGRES_DB={db_name}",
            "-p",
            "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        unregister_disposable_container(name)
        stop_disposable_container(name, owner=_run_owner)
        raise RuntimeError(f"could not start disposable PostgreSQL: {run.stderr.strip() or run.stdout.strip()}")
    if not _container_labels_match(name, run_owner=_run_owner, lease_expires=lease_expires):
        unregister_disposable_container(name)
        stop_disposable_container(name, owner=_run_owner)
        raise RuntimeError("disposable PostgreSQL container missing ownership labels")
    try:
        port_proc = subprocess.run(
            ["docker", "port", name, "5432/tcp"],
            check=True,
            capture_output=True,
            text=True,
        )
        host_port = port_proc.stdout.strip().rsplit(":", 1)[-1]
        url = f"postgresql+psycopg2://postgres:linas-test@127.0.0.1:{host_port}/{db_name}"
        wait_for_ready(url)
        yield url
    finally:
        stop_disposable_container(name, owner=_run_owner)
        unregister_disposable_container(name)
