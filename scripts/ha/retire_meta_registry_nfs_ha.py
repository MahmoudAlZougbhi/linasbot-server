#!/usr/bin/env python3
"""Crash-recoverable two-node retirement of the stale Meta registry NFS path.

This coordinator never imports NFS data.  It serializes both nodes behind the
shared production lock, records an fsynced rollback decision before mutation,
retires node02's mount before node01's export, and retains exact config/data
backups.  Dry-run is the default; its apply token binds one transaction ID, the
release/Postgres authority, and all six node pre-/postimage digests.  Apply
re-proves that exact plan before publishing a journal or mutating either node.
Every mutation/recovery decision requires an exact, digest-bound confirmation.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

STATE_ROOT: Final = Path("/var/lib/linasbot/meta-ha")
ACTIVE_JOURNAL: Final = STATE_ROOT / "registry-nfs-retire.active"
APPLICATION_LOCK: Final = Path("/run/lock/linasbot-meta-live.lock")
REPO_DIR: Final = Path("/opt/linasbot")
NODE_SCRIPT: Final = REPO_DIR / "scripts/ha/remove_registry_nfs.sh"
PYTHON_BIN: Final = REPO_DIR / "venv/bin/python"
PEER_HOST: Final = "10.106.0.4"
NODE01_PRIVATE: Final = "10.106.0.3"
REGISTRY_DIR: Final = Path("/opt/linasbot_data/meta_registry")
FSTAB_PATH: Final = Path("/etc/fstab")
EXPORTS_PATH: Final = Path("/etc/exports")
VOLATILE_MAINTENANCE: Final = Path("/run/linasbot-maintenance")
OTHER_TRANSACTION_PATHS: Final = (
    STATE_ROOT / "maintenance",
    STATE_ROOT / "bootstrap.active",
    STATE_ROOT / "bootstrap.coordinator.json",
    STATE_ROOT / "deploy.active",
    STATE_ROOT / "deploy-node.active",
    STATE_ROOT / "transaction.json",
    STATE_ROOT / "env.before",
    STATE_ROOT / "controlled-failover.active",
    STATE_ROOT / "rekey/runtime.guard",
    STATE_ROOT / "python-runtime-provision.active",
    STATE_ROOT / "python-runtime-provision.coordinator.json",
)
SCHEMA: Final = "linas-meta-registry-nfs-retire-v1"
PLAN_SCHEMA: Final = "linas-meta-registry-nfs-retire-plan-v1"
TX_RE: Final = re.compile(r"mnr_[0-9a-f]{64}")
SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
DIGEST_RE: Final = re.compile(r"[0-9a-f]{64}")
STAMP_RE: Final = re.compile(r"[0-9]{8}T[0-9]{6}Z")
NODE_COMMAND_TIMEOUT_SECONDS: Final = 300.0
NODE_PROBE_TIMEOUT_SECONDS: Final = 30.0
PEER_RPC_TIMEOUT_SECONDS: Final = 150.0


class NfsRetirementError(RuntimeError):
    """Fixed-message operational failure; command output is never embedded."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_state_root(path: Path = STATE_ROOT) -> None:
    if path == STATE_ROOT and os.geteuid() != 0:
        raise PermissionError("canonical NFS retirement state requires root")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
    ):
        raise PermissionError("NFS retirement state directory security is invalid")


def _atomic_write(path: Path, payload: bytes) -> None:
    _ensure_state_root(path.parent)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_temp)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _secure_file(path: Path) -> os.stat_result:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
        or info.st_nlink != 1
    ):
        raise PermissionError("NFS retirement journal security is invalid")
    return info


def _journal_payload(
    *,
    tx_id: str,
    expected_release_sha: str,
    expected_pg_sha256: str,
    stamp: str,
    node01_config_sha256: str,
    node01_runtime_sha256: str,
    node01_post_config_sha256: str,
    node02_config_sha256: str,
    node02_runtime_sha256: str,
    node02_post_config_sha256: str,
    phase: str,
    decision: str,
) -> dict[str, Any]:
    payload = {
        "schema": SCHEMA,
        "tx_id": tx_id,
        "expected_release_sha": expected_release_sha,
        "expected_pg_sha256": expected_pg_sha256,
        "stamp": stamp,
        "node01_config_sha256": node01_config_sha256,
        "node01_runtime_sha256": node01_runtime_sha256,
        "node01_post_config_sha256": node01_post_config_sha256,
        "node02_config_sha256": node02_config_sha256,
        "node02_runtime_sha256": node02_runtime_sha256,
        "node02_post_config_sha256": node02_post_config_sha256,
        "phase": phase,
        "decision": decision,
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    _validate_journal(payload)
    return payload


def _validate_journal(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema",
        "tx_id",
        "expected_release_sha",
        "expected_pg_sha256",
        "stamp",
        "node01_config_sha256",
        "node01_runtime_sha256",
        "node01_post_config_sha256",
        "node02_config_sha256",
        "node02_runtime_sha256",
        "node02_post_config_sha256",
        "phase",
        "decision",
        "updated_at",
    }
    if set(value) != expected or value.get("schema") != SCHEMA:
        raise NfsRetirementError("NFS retirement journal schema is invalid")
    if TX_RE.fullmatch(str(value.get("tx_id") or "")) is None:
        raise NfsRetirementError("NFS retirement transaction id is invalid")
    if SHA_RE.fullmatch(str(value.get("expected_release_sha") or "")) is None:
        raise NfsRetirementError("NFS retirement release SHA is invalid")
    if DIGEST_RE.fullmatch(str(value.get("expected_pg_sha256") or "")) is None:
        raise NfsRetirementError("NFS retirement PG digest is invalid")
    if STAMP_RE.fullmatch(str(value.get("stamp") or "")) is None:
        raise NfsRetirementError("NFS retirement stamp is invalid")
    for key in (
        "node01_config_sha256",
        "node01_runtime_sha256",
        "node01_post_config_sha256",
        "node02_config_sha256",
        "node02_runtime_sha256",
        "node02_post_config_sha256",
    ):
        if DIGEST_RE.fullmatch(str(value.get(key) or "")) is None:
            raise NfsRetirementError("NFS retirement preimage digest is invalid")
    if value.get("phase") not in {"prepared", "node02_retired", "both_retired", "committed", "aborted"}:
        raise NfsRetirementError("NFS retirement phase is invalid")
    if value.get("decision") not in {"rollback", "commit"}:
        raise NfsRetirementError("NFS retirement decision is invalid")
    try:
        datetime.fromisoformat(str(value.get("updated_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise NfsRetirementError("NFS retirement journal time is invalid") from exc
    return dict(value)


def _write_journal(path: Path, value: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    validated = _validate_journal(value)
    payload = _canonical(validated)
    _atomic_write(path, payload)
    _secure_file(path)
    reread = _load_journal(path)
    if reread != validated:
        raise NfsRetirementError("NFS retirement journal readback differs")
    return validated, _sha256_bytes(payload)


def _load_journal(path: Path = ACTIVE_JOURNAL) -> dict[str, Any]:
    _secure_file(path)
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NfsRetirementError("NFS retirement journal is unreadable") from exc
    if not isinstance(value, dict):
        raise NfsRetirementError("NFS retirement journal is invalid")
    return _validate_journal(value)


def _journal_digest(path: Path = ACTIVE_JOURNAL) -> str:
    _secure_file(path)
    return _sha256_bytes(path.read_bytes())


def _durable_unlink(path: Path) -> None:
    path.unlink()
    _fsync_dir(path.parent)


def _run(command: list[str], *, env: Mapping[str, str] | None = None, pass_fds: tuple[int, ...] = ()) -> None:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(env) if env is not None else None,
        pass_fds=pass_fds,
        start_new_session=True,
    )
    try:
        _stdout, _stderr = process.communicate(timeout=NODE_COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise NfsRetirementError("NFS retirement child timed out") from exc
    if process.returncode != 0:
        raise NfsRetirementError(f"NFS retirement child failed rc={process.returncode}")


def _capture(
    command: list[str],
    *,
    input_value: bytes | str | None = None,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if input_value is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=text,
    )
    try:
        stdout, stderr = process.communicate(input=input_value, timeout=NODE_PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise NfsRetirementError("NFS retirement child timed out") from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _terminate_process_group(process: subprocess.Popen[bytes], *, grace_seconds: float = 2.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=grace_seconds)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=grace_seconds)


def _open_application_lock() -> int:
    APPLICATION_LOCK.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(APPLICATION_LOCK, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
    ):
        os.close(fd)
        raise PermissionError("NFS retirement application lock security is invalid")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise NfsRetirementError("another production mutation holds the application lock") from exc
    return fd


def _assert_no_other_transaction() -> None:
    for path in (*OTHER_TRANSACTION_PATHS, VOLATILE_MAINTENANCE):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise NfsRetirementError("HA collision state is unreadable") from exc
        raise NfsRetirementError("another HA transaction or maintenance state is active")


def _node_command(
    role: str,
    journal: Mapping[str, Any],
    *,
    lock_fd: int,
    action: str,
) -> None:
    command = [
        "bash",
        str(NODE_SCRIPT),
        role,
        "--expected-release-sha",
        str(journal["expected_release_sha"]),
        "--expected-pg-sha256",
        str(journal["expected_pg_sha256"]),
        "--expected-config-sha256",
        str(journal[f"{role}_config_sha256"]),
        "--expected-runtime-sha256",
        str(journal[f"{role}_runtime_sha256"]),
        "--expected-post-config-sha256",
        str(journal[f"{role}_post_config_sha256"]),
        "--transaction-stamp",
        str(journal["stamp"]),
        "--coordinator-tx-id",
        str(journal["tx_id"]),
    ]
    if action == "apply":
        command.extend(["--apply", "--confirm", "REMOVE_META_REGISTRY_NFS"])
    elif action == "rollback":
        command.append("--rollback")
    elif action != "preflight":
        raise NfsRetirementError("NFS retirement node action is invalid")
    env = os.environ.copy()
    env["META_NFS_COORDINATOR_TX_ID"] = str(journal["tx_id"])
    env["META_NFS_LOCK_FD"] = str(lock_fd)
    _run(command, env=env, pass_fds=(lock_fd,))


def _root_regular_bytes(path: Path) -> bytes:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or info.st_nlink != 1
    ):
        raise NfsRetirementError("NFS configuration preimage is unsafe")
    return path.read_bytes()


def _preimage_digests(role: str) -> dict[str, str]:
    helper = REPO_DIR / "scripts/ha/registry_nfs_config.py"
    if role == "node02":
        config = _root_regular_bytes(FSTAB_PATH)
        post = _capture(
            [
                str(PYTHON_BIN),
                str(helper),
                "fstab-filter",
                str(FSTAB_PATH),
                "--source",
                f"{NODE01_PRIVATE}:{REGISTRY_DIR}",
                "--target",
                str(REGISTRY_DIR),
            ],
        )
        runtime = _capture(
            ["findmnt", "-rn", "-o", "SOURCE,TARGET,FSTYPE", "--target", str(REGISTRY_DIR)],
        )
    elif role == "node01":
        config = _root_regular_bytes(EXPORTS_PATH)
        post = _capture(
            [
                str(PYTHON_BIN),
                str(helper),
                "exports-filter",
                str(EXPORTS_PATH),
                "--target",
                str(REGISTRY_DIR),
            ],
        )
        exportfs = _capture(["exportfs", "-v"])
        if exportfs.returncode != 0:
            raise NfsRetirementError("NFS runtime export preimage is unavailable")
        runtime = _capture(
            [str(PYTHON_BIN), str(helper), "exports-select", "/dev/stdin", "--target", str(REGISTRY_DIR)],
            input_value=exportfs.stdout,
        )
    else:
        raise NfsRetirementError("NFS retirement role is invalid")
    if post.returncode != 0 or runtime.returncode != 0 or not runtime.stdout:
        raise NfsRetirementError("NFS runtime preimage is unavailable")
    return {
        "config_sha256": _sha256_bytes(config),
        "runtime_sha256": _sha256_bytes(runtime.stdout),
        "post_config_sha256": _sha256_bytes(post.stdout),
    }


def _journal_identity(journal: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: str(journal[key])
        for key in (
            "tx_id",
            "expected_release_sha",
            "expected_pg_sha256",
            "stamp",
            "node01_config_sha256",
            "node01_runtime_sha256",
            "node01_post_config_sha256",
            "node02_config_sha256",
            "node02_runtime_sha256",
            "node02_post_config_sha256",
        )
    }


def _trusted_backup_bytes(path: Path) -> bytes | None:
    if not (path.exists() or path.is_symlink()):
        return None
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or info.st_nlink != 1
    ):
        raise NfsRetirementError("NFS retirement rollback preimage is unsafe")
    return path.read_bytes()


def _config_state(
    role: str,
    *,
    stamp: str = "",
    expected_config_sha256: str = "",
    expected_runtime_sha256: str = "",
    expected_post_config_sha256: str = "",
) -> str:
    if stamp and STAMP_RE.fullmatch(stamp) is None:
        raise NfsRetirementError("NFS retirement state stamp is invalid")
    for digest in (expected_config_sha256, expected_runtime_sha256, expected_post_config_sha256):
        if digest and DIGEST_RE.fullmatch(digest) is None:
            raise NfsRetirementError("NFS retirement expected preimage is invalid")
    helper = REPO_DIR / "scripts/ha/registry_nfs_config.py"
    if role == "node02":
        result = _capture(
            [
                str(PYTHON_BIN),
                str(helper),
                "fstab-count",
                str(FSTAB_PATH),
                "--source",
                f"{NODE01_PRIVATE}:{REGISTRY_DIR}",
                "--target",
                str(REGISTRY_DIR),
            ],
            text=True,
        )
        mounted = _capture(
            ["findmnt", "-rn", "-o", "SOURCE,TARGET,FSTYPE", "--target", str(REGISTRY_DIR)],
            text=True,
        )
        count = result.stdout.strip() if result.returncode == 0 else "invalid"
        mount_rows = [line.split() for line in mounted.stdout.splitlines() if line.strip()]
        exact_mount = (
            len(mount_rows) == 1
            and len(mount_rows[0]) == 3
            and mount_rows[0][0] == f"{NODE01_PRIVATE}:{REGISTRY_DIR}"
            and mount_rows[0][1] == str(REGISTRY_DIR)
            and mount_rows[0][2] in {"nfs", "nfs4"}
        )
        backup = _trusted_backup_bytes(Path(f"/etc/fstab.meta-registry-backup-{stamp}")) if stamp else None
        config_bytes = FSTAB_PATH.read_bytes()
        config_matches = (
            (backup is None or config_bytes == backup)
            and (not expected_config_sha256 or _sha256_bytes(config_bytes) == expected_config_sha256)
            and (not expected_runtime_sha256 or _sha256_bytes(mounted.stdout.encode()) == expected_runtime_sha256)
        )
        if count == "1" and exact_mount and config_matches:
            return "active"
        if (
            count == "0"
            and not mount_rows
            and (not expected_post_config_sha256 or _sha256_bytes(config_bytes) == expected_post_config_sha256)
        ):
            return "retired"
        return "inconsistent"
    if role != "node01":
        raise NfsRetirementError("NFS retirement role is invalid")
    file_result = _capture(
        [str(PYTHON_BIN), str(helper), "exports-count", str(EXPORTS_PATH), "--target", str(REGISTRY_DIR)],
        text=True,
    )
    exportfs = _capture(["exportfs", "-v"], text=True)
    if file_result.returncode != 0 or exportfs.returncode != 0:
        return "inconsistent"
    active_result = _capture(
        [str(PYTHON_BIN), str(helper), "exports-count", "/dev/stdin", "--target", str(REGISTRY_DIR)],
        input_value=exportfs.stdout,
        text=True,
    )
    active_selected = _capture(
        [str(PYTHON_BIN), str(helper), "exports-select", "/dev/stdin", "--target", str(REGISTRY_DIR)],
        input_value=exportfs.stdout,
        text=True,
    )
    if active_result.returncode != 0 or active_selected.returncode != 0:
        return "inconsistent"
    file_count = int(file_result.stdout.strip() or "0") if file_result.stdout.strip().isdigit() else -1
    active_count = int(active_result.stdout.strip() or "0") if active_result.stdout.strip().isdigit() else -1
    config_backup = _trusted_backup_bytes(Path(f"/etc/exports.meta-registry-backup-{stamp}")) if stamp else None
    active_backup = _trusted_backup_bytes(Path(f"/etc/exports.meta-registry-active-backup-{stamp}")) if stamp else None
    config_bytes = EXPORTS_PATH.read_bytes()
    active_bytes = active_selected.stdout.encode()
    config_matches = (config_backup is None or config_bytes == config_backup) and (
        not expected_config_sha256 or _sha256_bytes(config_bytes) == expected_config_sha256
    )
    active_matches = (active_backup is None or active_bytes == active_backup) and (
        not expected_runtime_sha256 or _sha256_bytes(active_bytes) == expected_runtime_sha256
    )
    if file_count >= 1 and active_count >= 1 and config_matches and active_matches:
        return "active"
    if (
        file_count == 0
        and active_count == 0
        and (not expected_post_config_sha256 or _sha256_bytes(config_bytes) == expected_post_config_sha256)
    ):
        return "retired"
    return "inconsistent"


def _journaled_config_state(role: str, journal: Mapping[str, Any]) -> str:
    return _config_state(
        role,
        stamp=str(journal["stamp"]),
        expected_config_sha256=str(journal[f"{role}_config_sha256"]),
        expected_runtime_sha256=str(journal[f"{role}_runtime_sha256"]),
        expected_post_config_sha256=str(journal[f"{role}_post_config_sha256"]),
    )


def _postverify_node(role: str, journal: Mapping[str, Any]) -> None:
    peer = PEER_HOST if role == "node01" else NODE01_PRIVATE
    env = os.environ.copy()
    env["LINAS_HA_PEER_HOST"] = peer
    _run(
        [
            "bash",
            str(REPO_DIR / "scripts/ha/verify_meta_release_ha.sh"),
            str(journal["expected_release_sha"]),
            "local-only",
            "",
            role,
        ],
        env=env,
    )
    _run(
        [
            str(PYTHON_BIN),
            str(REPO_DIR / "scripts/ha/verify_meta_registry_postgres.py"),
            "--env-file",
            str(REPO_DIR / ".env"),
            "--store",
            str(REGISTRY_DIR / "registry.json"),
            "--expected-pg-sha256",
            str(journal["expected_pg_sha256"]),
        ]
    )
    _run(
        [
            str(PYTHON_BIN),
            "-c",
            (
                "import json,urllib.request;"
                "r=urllib.request.urlopen('http://127.0.0.1:8003/api/ready',timeout=8);"
                "p=json.load(r);"
                "assert r.status==200 and p.get('ok') is True"
            ),
        ]
    )


def _receipt_path(tx_id: str) -> Path:
    return STATE_ROOT / f"registry-nfs-retire-{tx_id}.json"


def _write_receipt(journal: Mapping[str, Any], *, outcome: str) -> Path:
    if outcome not in {"committed", "aborted"}:
        raise NfsRetirementError("NFS retirement receipt outcome is invalid")
    path = _receipt_path(str(journal["tx_id"]))
    payload = {
        "schema": SCHEMA,
        **_journal_identity(journal),
        "outcome": outcome,
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    if path.exists() or path.is_symlink():
        existing = _read_receipt(str(journal["tx_id"]))
        if existing is None:
            raise NfsRetirementError("NFS retirement receipt disappeared")
        if existing.get("outcome") != outcome or any(
            existing.get(key) != value for key, value in _journal_identity(journal).items()
        ):
            raise NfsRetirementError("NFS retirement receipt conflicts")
        return path
    _atomic_write(path, _canonical(payload))
    _secure_file(path)
    return path


def _read_receipt(tx_id: str) -> dict[str, Any] | None:
    path = _receipt_path(tx_id)
    if not (path.exists() or path.is_symlink()):
        return None
    _secure_file(path)
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NfsRetirementError("NFS retirement receipt is unreadable") from exc
    expected = {
        "schema",
        "tx_id",
        "expected_release_sha",
        "expected_pg_sha256",
        "stamp",
        "node01_config_sha256",
        "node01_runtime_sha256",
        "node01_post_config_sha256",
        "node02_config_sha256",
        "node02_runtime_sha256",
        "node02_post_config_sha256",
        "outcome",
        "completed_at",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != expected
        or payload.get("schema") != SCHEMA
        or payload.get("tx_id") != tx_id
        or payload.get("outcome") not in {"committed", "aborted"}
    ):
        raise NfsRetirementError("NFS retirement receipt is invalid")
    _journal_payload(
        **_journal_identity(payload),
        phase="committed",
        decision="commit",
    )
    try:
        datetime.fromisoformat(str(payload["completed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise NfsRetirementError("NFS retirement receipt time is invalid") from exc
    return payload


def _receipt_status(tx_id: str) -> str:
    payload = _read_receipt(tx_id)
    return "absent" if payload is None else str(payload["outcome"])


class PeerSession:
    def __init__(self, peer_host: str = PEER_HOST) -> None:
        self._buffer = b""
        self._process = subprocess.Popen(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "ServerAliveInterval=10",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "StrictHostKeyChecking=yes",
                f"root@{peer_host}",
                str(PYTHON_BIN),
                str(REPO_DIR / "scripts/ha/retire_meta_registry_nfs_ha.py"),
                "--peer-server",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        ready = self.call({"action": "hello"})
        if ready.get("status") != "ready":
            raise NfsRetirementError("NFS retirement peer did not acquire its lock")

    def call(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self._process.stdin is None or self._process.stdout is None:
            raise NfsRetirementError("NFS retirement peer channel is unavailable")
        if self._process.poll() is not None:
            raise NfsRetirementError("NFS retirement peer exited")
        encoded = (json.dumps(dict(request), separators=(",", ":"), sort_keys=True) + "\n").encode()
        try:
            self._process.stdin.write(encoded)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._terminate()
            raise NfsRetirementError("NFS retirement peer request failed") from exc
        deadline = time.monotonic() + _peer_rpc_timeout(request)
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._terminate()
                raise NfsRetirementError("NFS retirement peer response timed out")
            readable, _, _ = select.select([self._process.stdout], [], [], remaining)
            if not readable:
                self._terminate()
                raise NfsRetirementError("NFS retirement peer response timed out")
            chunk = os.read(self._process.stdout.fileno(), 65_536)
            if not chunk:
                self._terminate()
                raise NfsRetirementError("NFS retirement peer response is unavailable")
            self._buffer += chunk
            if len(self._buffer) > 1_048_576:
                self._terminate()
                raise NfsRetirementError("NFS retirement peer response is too large")
        raw_line, self._buffer = self._buffer.split(b"\n", 1)
        try:
            response = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NfsRetirementError("NFS retirement peer response is invalid") from exc
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise NfsRetirementError("NFS retirement peer operation failed")
        return response

    def _terminate(self) -> None:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        _terminate_process_group(self._process)

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                self.call({"action": "close"})
            except NfsRetirementError:
                pass
        if self._process.stdin is not None and not self._process.stdin.closed:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._terminate()


def _peer_rpc_timeout(request: Mapping[str, Any]) -> float:
    action = str(request.get("action") or "")
    if action == "postverify":
        # Three independently bounded release/readiness/PG probes run in order.
        return max(PEER_RPC_TIMEOUT_SECONDS, (3 * NODE_COMMAND_TIMEOUT_SECONDS) + 30.0)
    if action in {"preflight", "apply", "rollback"}:
        # One bounded node action followed by exact config/runtime state probes.
        return max(
            PEER_RPC_TIMEOUT_SECONDS,
            NODE_COMMAND_TIMEOUT_SECONDS + (4 * NODE_PROBE_TIMEOUT_SECONDS) + 30.0,
        )
    return PEER_RPC_TIMEOUT_SECONDS


def _peer_server() -> int:
    if os.geteuid() != 0:
        return 2
    lock_fd = _open_application_lock()
    try:
        _assert_no_other_transaction()
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise NfsRetirementError("peer request invalid")
                action = request.get("action")
                response: dict[str, Any] = {"ok": True}
                if action == "hello":
                    response["status"] = "ready"
                elif action == "preimage":
                    response.update(_preimage_digests("node02"))
                elif action == "journal-write":
                    journal, digest = _write_journal(ACTIVE_JOURNAL, request["journal"])
                    response.update({"status": journal["phase"], "journal_sha256": digest})
                elif action == "journal-read":
                    if ACTIVE_JOURNAL.exists() or ACTIVE_JOURNAL.is_symlink():
                        response.update({"journal": _load_journal(), "journal_sha256": _journal_digest()})
                    else:
                        tx_id = str(request.get("tx_id") or "")
                        receipt = _read_receipt(tx_id)
                        response.update(
                            {
                                "journal": None,
                                "receipt": receipt,
                                "receipt_status": "absent" if receipt is None else receipt["outcome"],
                            }
                        )
                elif action == "journal-remove":
                    expected = str(request.get("expected_sha256") or "")
                    if not hashlib.sha256(ACTIVE_JOURNAL.read_bytes()).hexdigest() == expected:
                        raise NfsRetirementError("peer journal CAS failed")
                    _durable_unlink(ACTIVE_JOURNAL)
                    response["status"] = "removed"
                elif action in {"preflight", "apply", "rollback"}:
                    journal = _validate_journal(request["journal"])
                    _node_command("node02", journal, lock_fd=lock_fd, action=str(action))
                    response["status"] = (
                        _config_state("node02") if action == "preflight" else _journaled_config_state("node02", journal)
                    )
                elif action == "state":
                    journal = _validate_journal(request["journal"])
                    response["status"] = _journaled_config_state("node02", journal)
                elif action == "postverify":
                    journal = _validate_journal(request["journal"])
                    _postverify_node("node02", journal)
                    response["status"] = "verified"
                elif action == "finalize":
                    journal = _validate_journal(request["journal"])
                    expected = str(request.get("expected_sha256") or "")
                    if _journal_digest() != expected:
                        raise NfsRetirementError("peer journal finalize CAS failed")
                    outcome = str(request.get("outcome") or "")
                    _write_receipt(journal, outcome=outcome)
                    _durable_unlink(ACTIVE_JOURNAL)
                    response["status"] = _receipt_status(str(journal["tx_id"]))
                elif action == "close":
                    response["status"] = "closed"
                    print(json.dumps(response, separators=(",", ":"), sort_keys=True), flush=True)
                    break
                else:
                    raise NfsRetirementError("peer action invalid")
            except Exception as exc:  # noqa: BLE001 - fixed type only, never child output.
                response = {"ok": False, "error_type": type(exc).__name__}
            print(json.dumps(response, separators=(",", ":"), sort_keys=True), flush=True)
    finally:
        os.close(lock_fd)
    return 0


def _new_tx_id(expected_release_sha: str, expected_pg_sha256: str) -> str:
    random = os.urandom(32)
    return (
        "mnr_"
        + hashlib.sha256(
            b"linas-meta-registry-nfs-retire-v1\x00"
            + expected_release_sha.encode()
            + expected_pg_sha256.encode()
            + random
        ).hexdigest()
    )


def _plan_contract(journal: Mapping[str, Any]) -> dict[str, str]:
    """Return the immutable, secret-free operator-approved detach baseline."""

    validated = _validate_journal(journal)
    return {
        "schema": PLAN_SCHEMA,
        **{
            key: str(validated[key])
            for key in (
                "tx_id",
                "expected_release_sha",
                "expected_pg_sha256",
                "node01_config_sha256",
                "node01_runtime_sha256",
                "node01_post_config_sha256",
                "node02_config_sha256",
                "node02_runtime_sha256",
                "node02_post_config_sha256",
            )
        },
    }


def _plan_contract_sha256(journal: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical(_plan_contract(journal)))


def _confirm_apply(journal: Mapping[str, Any]) -> str:
    contract = _plan_contract(journal)
    return (
        "RETIRE_META_REGISTRY_NFS:"
        f"{contract['tx_id']}:"
        f"{contract['expected_release_sha']}:"
        f"{contract['expected_pg_sha256']}:"
        f"{_plan_contract_sha256(journal)}"
    )


def _parse_apply_confirmation(confirmation: str) -> tuple[str, str, str, str]:
    parts = str(confirmation or "").split(":")
    if (
        len(parts) != 5
        or parts[0] != "RETIRE_META_REGISTRY_NFS"
        or TX_RE.fullmatch(parts[1]) is None
        or SHA_RE.fullmatch(parts[2]) is None
        or DIGEST_RE.fullmatch(parts[3]) is None
        or DIGEST_RE.fullmatch(parts[4]) is None
    ):
        raise PermissionError("exact NFS retirement plan confirmation is missing or invalid")
    return parts[1], parts[2], parts[3], parts[4]


def _confirm_recovery(tx_id: str, decision: str, journal_sha256: str) -> str:
    return f"RECOVER_META_REGISTRY_NFS:{tx_id}:{decision}:{journal_sha256}"


def _plan(expected_release_sha: str, expected_pg_sha256: str) -> int:
    if ACTIVE_JOURNAL.exists() or ACTIVE_JOURNAL.is_symlink():
        journal = _load_journal()
        print(
            f"RECOVERY_REQUIRED tx={journal['tx_id']} phase={journal['phase']} "
            f"decision={journal['decision']} journal_sha256={_journal_digest()}"
        )
        return 3
    draft = _journal_payload(
        tx_id=_new_tx_id(expected_release_sha, expected_pg_sha256),
        expected_release_sha=expected_release_sha,
        expected_pg_sha256=expected_pg_sha256,
        stamp=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        node01_config_sha256="0" * 64,
        node01_runtime_sha256="0" * 64,
        node01_post_config_sha256="0" * 64,
        node02_config_sha256="0" * 64,
        node02_runtime_sha256="0" * 64,
        node02_post_config_sha256="0" * 64,
        phase="prepared",
        decision="rollback",
    )
    lock_fd = _open_application_lock()
    _assert_no_other_transaction()
    peer = PeerSession()
    try:
        peer.call({"action": "preflight", "journal": draft})
        _node_command("node01", draft, lock_fd=lock_fd, action="preflight")
        node02 = peer.call({"action": "preimage"})
        node01 = _preimage_digests("node01")
        plan = _journal_payload(
            **{
                **_journal_identity(draft),
                "node01_config_sha256": node01["config_sha256"],
                "node01_runtime_sha256": node01["runtime_sha256"],
                "node01_post_config_sha256": node01["post_config_sha256"],
                "node02_config_sha256": str(node02["config_sha256"]),
                "node02_runtime_sha256": str(node02["runtime_sha256"]),
                "node02_post_config_sha256": str(node02["post_config_sha256"]),
                "phase": "prepared",
                "decision": "rollback",
            }
        )
    finally:
        peer.close()
        os.close(lock_fd)
    print("PLAN_OK: both nodes and Postgres authority passed read-only preflight")
    print(f"PLAN_TRANSACTION_ID={plan['tx_id']}")
    print(f"PLAN_CONTRACT_SHA256={_plan_contract_sha256(plan)}")
    print(f"APPLY_CONFIRMATION={_confirm_apply(plan)}")
    return 0


def _apply(expected_release_sha: str, expected_pg_sha256: str, confirmation: str) -> int:
    tx_id, confirmed_release_sha, confirmed_pg_sha256, confirmed_plan_sha256 = _parse_apply_confirmation(confirmation)
    if confirmed_release_sha != expected_release_sha or confirmed_pg_sha256 != expected_pg_sha256:
        raise PermissionError("NFS retirement confirmation targets another release or Postgres baseline")
    if ACTIVE_JOURNAL.exists() or ACTIVE_JOURNAL.is_symlink():
        raise NfsRetirementError("existing NFS retirement requires recovery")
    if _read_receipt(tx_id) is not None:
        raise NfsRetirementError("NFS retirement confirmation transaction was already finalized")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    journal = _journal_payload(
        tx_id=tx_id,
        expected_release_sha=expected_release_sha,
        expected_pg_sha256=expected_pg_sha256,
        stamp=stamp,
        node01_config_sha256="0" * 64,
        node01_runtime_sha256="0" * 64,
        node01_post_config_sha256="0" * 64,
        node02_config_sha256="0" * 64,
        node02_runtime_sha256="0" * 64,
        node02_post_config_sha256="0" * 64,
        phase="prepared",
        decision="rollback",
    )
    lock_fd = _open_application_lock()
    _assert_no_other_transaction()
    peer = PeerSession()
    peer_retired = False
    local_retired = False
    try:
        peer_existing = peer.call({"action": "journal-read", "tx_id": tx_id})
        if peer_existing.get("journal") is not None or peer_existing.get("receipt_status") != "absent":
            raise NfsRetirementError("peer NFS retirement transaction state already exists")
        peer.call({"action": "preflight", "journal": journal})
        _node_command("node01", journal, lock_fd=lock_fd, action="preflight")
        node02 = peer.call({"action": "preimage"})
        node01 = _preimage_digests("node01")
        journal = _journal_payload(
            **{
                **_journal_identity(journal),
                "node01_config_sha256": node01["config_sha256"],
                "node01_runtime_sha256": node01["runtime_sha256"],
                "node01_post_config_sha256": node01["post_config_sha256"],
                "node02_config_sha256": str(node02["config_sha256"]),
                "node02_runtime_sha256": str(node02["runtime_sha256"]),
                "node02_post_config_sha256": str(node02["post_config_sha256"]),
                "phase": "prepared",
                "decision": "rollback",
            }
        )
        if not hmac.compare_digest(_plan_contract_sha256(journal), confirmed_plan_sha256):
            raise PermissionError("NFS retirement plan confirmation is stale or the baseline changed")
        if confirmation != _confirm_apply(journal):
            raise PermissionError("NFS retirement plan confirmation is stale or invalid")
        journal, _ = _write_journal(ACTIVE_JOURNAL, journal)
        peer.call({"action": "journal-write", "journal": journal})
        peer_state = peer.call({"action": "apply", "journal": journal}).get("status")
        if peer_state != "retired":
            raise NfsRetirementError("node02 NFS mount did not retire exactly")
        peer_retired = True
        journal = _journal_payload(
            **{
                **_journal_identity(journal),
                "phase": "node02_retired",
                "decision": "rollback",
            }
        )
        journal, _ = _write_journal(ACTIVE_JOURNAL, journal)
        peer.call({"action": "journal-write", "journal": journal})
        _node_command("node01", journal, lock_fd=lock_fd, action="apply")
        if _journaled_config_state("node01", journal) != "retired":
            raise NfsRetirementError("node01 NFS export did not retire exactly")
        local_retired = True
        journal = _journal_payload(
            **{
                **_journal_identity(journal),
                "phase": "both_retired",
                "decision": "rollback",
            }
        )
        journal, _ = _write_journal(ACTIVE_JOURNAL, journal)
        peer.call({"action": "journal-write", "journal": journal})
        if (
            peer.call({"action": "state", "journal": journal}).get("status") != "retired"
            or _journaled_config_state("node01", journal) != "retired"
        ):
            raise NfsRetirementError("NFS retirement postcondition is not exact")
        peer.call({"action": "postverify", "journal": journal})
        _postverify_node("node01", journal)
        journal = _journal_payload(
            **{
                **_journal_identity(journal),
                "phase": "committed",
                "decision": "commit",
            }
        )
        journal, local_digest = _write_journal(ACTIVE_JOURNAL, journal)
        peer_response = peer.call({"action": "journal-write", "journal": journal})
        _write_receipt(journal, outcome="committed")
        peer.call(
            {
                "action": "finalize",
                "journal": journal,
                "expected_sha256": peer_response["journal_sha256"],
                "outcome": "committed",
            }
        )
        if _journal_digest() != local_digest:
            raise NfsRetirementError("local NFS retirement journal changed before closeout")
        _durable_unlink(ACTIVE_JOURNAL)
        print(f"OK: NFS retirement committed tx={tx_id} receipt={_receipt_path(tx_id)}")
        return 0
    except Exception:
        try:
            durable_decision = str(_load_journal().get("decision"))
        except Exception:
            durable_decision = "unknown"
        if durable_decision == "commit":
            raise
        if local_retired:
            try:
                _node_command("node01", journal, lock_fd=lock_fd, action="rollback")
            except Exception:
                pass
        if peer_retired:
            try:
                peer.call({"action": "rollback", "journal": journal})
            except Exception:
                pass
        raise
    finally:
        peer.close()
        os.close(lock_fd)


def _recover(*, expected_journal_sha256: str, decision: str, confirmation: str) -> int:
    journal = _load_journal()
    journal_sha = _journal_digest()
    if journal_sha != expected_journal_sha256:
        raise NfsRetirementError("NFS retirement recovery journal digest changed")
    tx_id = str(journal["tx_id"])
    if journal["decision"] == "commit" and decision != "forward":
        raise PermissionError("a durable NFS commit decision cannot be rolled back automatically")
    if decision not in {"forward", "rollback"} or confirmation != _confirm_recovery(tx_id, decision, journal_sha):
        raise PermissionError("exact NFS retirement recovery confirmation is missing")
    lock_fd = _open_application_lock()
    _assert_no_other_transaction()
    peer = PeerSession()
    try:
        peer_read = peer.call({"action": "journal-read", "tx_id": tx_id})
        peer_journal = peer_read.get("journal")
        peer_receipt = peer_read.get("receipt")
        peer_receipt_status = str(peer_read.get("receipt_status") or "absent")
        if peer_receipt_status not in {"absent", "committed", "aborted"} or (
            peer_receipt_status != "absent" and peer_receipt is None
        ):
            raise NfsRetirementError("peer NFS retirement receipt status is invalid")
        if peer_journal is not None and (
            not isinstance(peer_journal, dict)
            or peer_journal.get("tx_id") != tx_id
            or _journal_identity(peer_journal) != _journal_identity(journal)
        ):
            raise NfsRetirementError("peer NFS retirement journal does not match")
        if peer_journal is None and peer_receipt_status == "absent":
            if journal["phase"] != "prepared" or journal["decision"] != "rollback":
                raise NfsRetirementError("peer NFS retirement recovery state is absent")
            peer_read = peer.call({"action": "journal-write", "journal": journal})
            peer_journal = journal
        if peer_receipt is not None and (
            not isinstance(peer_receipt, dict) or _journal_identity(peer_receipt) != _journal_identity(journal)
        ):
            raise NfsRetirementError("peer NFS retirement receipt identity differs")
        local_receipt = _read_receipt(tx_id)
        if local_receipt is not None and _journal_identity(local_receipt) != _journal_identity(journal):
            raise NfsRetirementError("local NFS retirement receipt identity differs")
        local_receipt_status = "absent" if local_receipt is None else str(local_receipt["outcome"])
        if decision == "forward" and "aborted" in {local_receipt_status, peer_receipt_status}:
            raise PermissionError("a durable aborted NFS receipt cannot be forwarded")
        if decision == "rollback" and "committed" in {local_receipt_status, peer_receipt_status}:
            raise PermissionError("a durable committed NFS receipt cannot be rolled back")
        local_state = _journaled_config_state("node01", journal)
        peer_state = str(peer.call({"action": "state", "journal": journal}).get("status"))
        if "inconsistent" in {local_state, peer_state}:
            raise NfsRetirementError("NFS configuration is inconsistent; automatic recovery refused")
        if decision == "rollback":
            if local_state == "retired":
                _node_command("node01", journal, lock_fd=lock_fd, action="rollback")
            if peer_state == "retired":
                peer.call({"action": "rollback", "journal": journal})
            if (
                _journaled_config_state("node01", journal) != "active"
                or peer.call({"action": "state", "journal": journal}).get("status") != "active"
            ):
                raise NfsRetirementError("NFS rollback did not restore both exact states")
            _write_receipt(journal, outcome="aborted")
        else:
            if peer_state == "active":
                if local_state == "retired":
                    raise NfsRetirementError("reversed partial NFS retirement requires rollback")
                peer.call({"action": "apply", "journal": journal})
            if local_state == "active":
                _node_command("node01", journal, lock_fd=lock_fd, action="apply")
            if (
                _journaled_config_state("node01", journal) != "retired"
                or peer.call({"action": "state", "journal": journal}).get("status") != "retired"
            ):
                raise NfsRetirementError("forward NFS recovery did not retire both exact states")
            peer.call({"action": "postverify", "journal": journal})
            _postverify_node("node01", journal)
            journal = _journal_payload(
                **{
                    **_journal_identity(journal),
                    "phase": "committed",
                    "decision": "commit",
                }
            )
            journal, _ = _write_journal(ACTIVE_JOURNAL, journal)
            peer.call({"action": "journal-write", "journal": journal})
            _write_receipt(journal, outcome="committed")
        peer_read = peer.call({"action": "journal-read", "tx_id": tx_id})
        if peer_read.get("journal") is not None:
            peer.call(
                {
                    "action": "finalize",
                    "journal": journal,
                    "expected_sha256": peer_read["journal_sha256"],
                    "outcome": "aborted" if decision == "rollback" else "committed",
                }
            )
        _durable_unlink(ACTIVE_JOURNAL)
        print(f"OK: NFS retirement recovery outcome={decision} tx={tx_id}")
        return 0
    finally:
        peer.close()
        os.close(lock_fd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer-server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--expected-release-sha", default="")
    parser.add_argument("--expected-pg-sha256", default="")
    parser.add_argument("--expected-journal-sha256", default="")
    parser.add_argument("--decision", choices=("forward", "rollback"))
    parser.add_argument("--confirm", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.peer_server:
        return _peer_server()
    if os.geteuid() != 0:
        raise PermissionError("NFS retirement coordinator requires root")
    if sum((bool(args.plan), bool(args.apply), bool(args.recover))) != 1:
        raise NfsRetirementError("choose exactly one of --plan, --apply, or --recover")
    if args.plan or args.apply:
        if SHA_RE.fullmatch(args.expected_release_sha) is None or DIGEST_RE.fullmatch(args.expected_pg_sha256) is None:
            raise NfsRetirementError("exact release and PG digests are required")
    if args.plan:
        return _plan(args.expected_release_sha, args.expected_pg_sha256)
    if args.apply:
        return _apply(args.expected_release_sha, args.expected_pg_sha256, args.confirm)
    if DIGEST_RE.fullmatch(args.expected_journal_sha256) is None or args.decision is None:
        raise NfsRetirementError("recovery requires exact journal digest and decision")
    return _recover(
        expected_journal_sha256=args.expected_journal_sha256,
        decision=args.decision,
        confirmation=args.confirm,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - fixed type only; no paths, IDs, or child output.
        print(f"ERROR: NFS retirement failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(2) from None
