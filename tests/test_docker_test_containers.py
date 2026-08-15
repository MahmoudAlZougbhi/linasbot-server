"""Ownership-safe disposable Docker container helpers for pytest."""

from __future__ import annotations

import multiprocessing as mp
import subprocess
import time
from pathlib import Path

import pytest

from tests.docker_test_containers import (
    LEASE_EXPIRES_LABEL,
    RUN_OWNER_LABEL,
    cleanup_tracked_containers,
    current_run_owner,
    docker_available,
    install_interrupt_safe_cleanup,
    purge_stale_test_containers,
    register_disposable_container,
    stop_disposable_container,
    unregister_disposable_container,
)


def _container_exists(name: str) -> bool:
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.Name}}", name],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _hold_active_container(ready_path: str, stop_path: str) -> None:
    import uuid

    install_interrupt_safe_cleanup()
    owner = current_run_owner()
    name = f"linas-debug-hold-{uuid.uuid4().hex[:8]}"
    lease = int(time.time()) + 900
    register_disposable_container(name)
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--label",
            f"{RUN_OWNER_LABEL}={owner}",
            "--label",
            f"{LEASE_EXPIRES_LABEL}={lease}",
            "-e",
            "POSTGRES_PASSWORD=linas-test",
            "-e",
            "POSTGRES_DB=linas_owner_test",
            "-p",
            "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        Path(ready_path).write_text(f"error:{run.stderr}\n", encoding="utf-8")
        return
    Path(ready_path).write_text(f"{name}\n", encoding="utf-8")
    while not Path(stop_path).exists():
        time.sleep(0.1)
    stop_disposable_container(name, owner=owner)
    unregister_disposable_container(name)


def test_concurrent_runs_do_not_purge_foreign_active_container(tmp_path: Path) -> None:
    if not docker_available():
        pytest.skip("Docker is required")

    ready_path = tmp_path / "ready.txt"
    stop_path = tmp_path / "stop.txt"
    process = mp.Process(
        target=_hold_active_container,
        args=(str(ready_path), str(stop_path)),
        daemon=True,
    )
    process.start()
    deadline = time.time() + 60
    while time.time() < deadline and not ready_path.exists():
        time.sleep(0.1)
    assert ready_path.exists(), "foreign run did not start disposable PostgreSQL"
    assert not ready_path.read_text(encoding="utf-8").startswith("error:"), ready_path.read_text(encoding="utf-8")
    foreign_name = ready_path.read_text(encoding="utf-8").strip()
    assert _container_exists(foreign_name)

    purged = purge_stale_test_containers()
    assert process.is_alive(), "foreign run process was interrupted by stale purge"
    assert foreign_name not in purged
    assert _container_exists(foreign_name)

    stop_path.write_text("stop\n", encoding="utf-8")
    process.join(timeout=30)
    assert not process.is_alive()


def test_interrupted_orphan_is_purged_when_owner_dead_and_lease_expired() -> None:
    if not docker_available():
        pytest.skip("Docker is required")

    name = f"linas-debug-orphan-{int(time.time())}"
    dead_owner = "99999999-deadowner"
    expired_lease = int(time.time()) - 60
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--label",
            f"{RUN_OWNER_LABEL}={dead_owner}",
            "--label",
            f"{LEASE_EXPIRES_LABEL}={expired_lease}",
            "-e",
            "POSTGRES_PASSWORD=linas-test",
            "-e",
            "POSTGRES_DB=linas_orphan_test",
            "-p",
            "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    try:
        assert _container_exists(name)
        purged = purge_stale_test_containers()
        assert name in purged
        assert not _container_exists(name)
    finally:
        stop_disposable_container(name, owner=dead_owner)


def test_tracked_container_is_not_purged_by_stale_scan() -> None:
    if not docker_available():
        pytest.skip("Docker is required")

    name = f"linas-debug-tracked-{int(time.time())}"
    lease = int(time.time()) + 900
    owner = current_run_owner()
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--label",
            f"{RUN_OWNER_LABEL}={owner}",
            "--label",
            f"{LEASE_EXPIRES_LABEL}={lease}",
            "-e",
            "POSTGRES_PASSWORD=linas-test",
            "-e",
            "POSTGRES_DB=linas_tracked_test",
            "-p",
            "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    register_disposable_container(name)
    try:
        assert _container_exists(name)
        purged = purge_stale_test_containers()
        assert name not in purged
        assert _container_exists(name)
    finally:
        stop_disposable_container(name, owner=owner)
        unregister_disposable_container(name)
        cleanup_tracked_containers()
