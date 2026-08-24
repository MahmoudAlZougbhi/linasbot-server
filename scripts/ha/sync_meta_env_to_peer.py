#!/usr/bin/env python3
"""Crash-safe two-node activation of the canonical Meta environment.

Secrets travel only in an encrypted SSH stdin request.  Every mutation is
preceded by a durable, root-owned journal and an exact 0600 backup.  Journals
survive process death, SSH acknowledgement loss, and reboot so a later run can
finish the recorded commit decision or confirm peer rollback before restoring
the coordinator.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    from scripts.ha.meta_env_file import require_secure_env_file
    from scripts.ha.production_mutation_guard import _require_exact_release, _require_inherited_lock
except ModuleNotFoundError:  # Direct production-script execution.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.ha.meta_env_file import require_secure_env_file
    from scripts.ha.production_mutation_guard import _require_exact_release, _require_inherited_lock

REPO_DIR = Path("/opt/linasbot")
ENV_PATH = REPO_DIR / ".env"
LOCK_PATH = Path("/run/lock/linasbot-meta-live.lock")
VOLATILE_MAINTENANCE_PATH = Path("/run/linasbot-maintenance")
STATE_ROOT = Path("/var/lib/linasbot/meta-ha")
PERSISTENT_MAINTENANCE_NAME = "maintenance"
JOURNAL_NAME = "transaction.json"
BACKUP_NAME = "env.before"
WORKER_STATE_NAME = "workers.before.json"
STAGE_AUTHORITY_NAME = "prestage.authority.json"
BOOTSTRAP_ACTIVE_NAME = "bootstrap.active"
DEPLOY_ACTIVE_NAME = "deploy.active"
DEPLOY_NODE_ACTIVE_NAME = "deploy-node.active"
BOOTSTRAP_COORDINATOR_NAME = "bootstrap.coordinator.json"
CONTROLLED_FAILOVER_ACTIVE_NAME = "controlled-failover.active"
NFS_RETIRE_ACTIVE_NAME = "registry-nfs-retire.active"
PYTHON_RUNTIME_PROVISION_ACTIVE_NAME = "python-runtime-provision.active"
PYTHON_RUNTIME_PROVISION_COORDINATOR_NAME = "python-runtime-provision.coordinator.json"
MAX_PAYLOAD_BYTES = 1024 * 1024
META_KEY_RE = re.compile(r"^META_[A-Z0-9_]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TX_ID_RE = re.compile(r"^[0-9a-f]{32}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
NODE_LOCAL_META_KEYS = frozenset({"META_DELETION_NODE_ID"})
LOCAL_NODE_ID = "node01"
PEER_NODE_ID = "node02"
PROTOCOL_SCHEMA = 4
JOURNAL_SCHEMA = 1
WORKER_STATE_SCHEMA = 1
STAGE_AUTHORITY_SCHEMA = 1
LOCK_TIMEOUT_SECONDS = 30.0
PEER_TIMEOUT_SECONDS = 180.0
PROCESS_TIMEOUT_SECONDS = 20.0
READY_TIMEOUT_SECONDS = 60.0
WORKER_UNITS = tuple(
    f"linasbot-worker@{queue}.service" for queue in ("high_priority", "interactive", "background", "expensive")
)
WORKER_STATE_STATUSES = frozenset({"captured", "quiesced", "restoring", "restored"})
JOURNAL_STATUSES = frozenset(
    {
        "coordinator_created",
        "peer_prepare_started",
        "peer_prepared",
        "local_activation_started",
        "local_active",
        "commit_requested",
        "peer_committed",
        "backup_created",
        "write_started",
        "prepared",
        "committed",
        "rollback_requested",
        "rolled_back",
        "parity_proven",
        "finalizing_committed",
        "finalizing_rolled_back",
    }
)
COORDINATOR_STATUSES = frozenset(
    {
        "coordinator_created",
        "peer_prepare_started",
        "peer_prepared",
        "local_activation_started",
        "local_active",
        "commit_requested",
        "peer_committed",
        "rolled_back",
        "parity_proven",
        "finalizing_committed",
        "finalizing_rolled_back",
    }
)
PEER_STATUSES = frozenset(
    {
        "backup_created",
        "write_started",
        "prepared",
        "commit_requested",
        "committed",
        "rollback_requested",
        "rolled_back",
        "parity_proven",
        "finalizing_committed",
        "finalizing_rolled_back",
    }
)
COMMIT_DECISION_STATUSES = frozenset(
    {"commit_requested", "peer_committed", "committed", "parity_proven", "finalizing_committed"}
)


def _journal_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / JOURNAL_NAME


def _backup_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / BACKUP_NAME


def _worker_state_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / WORKER_STATE_NAME


def _stage_authority_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / STAGE_AUTHORITY_NAME


def _persistent_maintenance_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / PERSISTENT_MAINTENANCE_NAME


def _bootstrap_active_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / BOOTSTRAP_ACTIVE_NAME


def _deploy_active_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / DEPLOY_ACTIVE_NAME


def _deploy_node_active_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / DEPLOY_NODE_ACTIVE_NAME


def _bootstrap_coordinator_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / BOOTSTRAP_COORDINATOR_NAME


def _controlled_failover_active_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / CONTROLLED_FAILOVER_ACTIVE_NAME


def _nfs_retire_active_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / NFS_RETIRE_ACTIVE_NAME


def _python_runtime_provision_active_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / PYTHON_RUNTIME_PROVISION_ACTIVE_NAME


def _python_runtime_provision_coordinator_path(state_root: Path = STATE_ROOT) -> Path:
    return state_root / PYTHON_RUNTIME_PROVISION_COORDINATOR_NAME


def _entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RuntimeError("Meta HA transaction path is unavailable") from exc
    return True


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise RuntimeError(
            "Meta HA directory fsync open failed: "
            f"errno={exc.errno} {exc.strerror or 'unknown'} path={directory}"
        ) from exc
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            raise RuntimeError(
                "Meta HA directory fsync failed: "
                f"errno={exc.errno} {exc.strerror or 'unknown'} path={directory}"
            ) from exc
    finally:
        os.close(fd)


def _authorize_registered_prestage_backup(
    local_prestage_backup: Path,
    durable_backup: Path,
) -> None:
    require_secure_env_file(durable_backup)
    require_secure_env_file(local_prestage_backup)
    try:
        authorized = local_prestage_backup.samefile(durable_backup)
    except OSError:
        try:
            authorized = local_prestage_backup.resolve() == durable_backup.resolve()
        except OSError as exc:
            raise RuntimeError(
                "Meta HA pre-stage backup authorization failed: "
                f"errno={exc.errno} {exc.strerror or 'unknown'} "
                f"path={exc.filename or '-'}"
            ) from exc
    if not authorized:
        raise RuntimeError("Only the registered durable Meta HA backup may authorize activation")


def _ensure_state_root(state_root: Path = STATE_ROOT) -> None:
    if state_root == STATE_ROOT and (os.geteuid() != 0 or os.getegid() != 0):
        raise RuntimeError("Canonical Meta HA state must be owned by root")
    state_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    current = state_root.lstat()
    if (
        not stat.S_ISDIR(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or stat.S_IMODE(current.st_mode) != 0o700
        or current.st_uid != os.geteuid()
        or current.st_gid != os.getegid()
    ):
        raise RuntimeError("Meta HA state directory security contract is invalid")


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.atomic.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _durable_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def _read_meta_values(path: Path) -> dict[str, str]:
    require_secure_env_file(path)
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if not raw_line or raw_line.lstrip().startswith("#") or "=" not in raw_line:
            continue
        raw_key, value = raw_line.split("=", 1)
        key = raw_key.strip()
        if META_KEY_RE.fullmatch(key) and key not in NODE_LOCAL_META_KEYS:
            if key in values:
                raise RuntimeError("Canonical Meta environment contains duplicate keys")
            if any(character in value for character in ("\n", "\r", "\0")) or len(value) > 65536:
                raise RuntimeError("Meta environment value is invalid")
            values[key] = value
    if not values:
        raise RuntimeError("Canonical Meta environment is empty")
    return values


def _read_node_identity(path: Path) -> str:
    require_secure_env_file(path)
    identities: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if not raw_line or raw_line.lstrip().startswith("#") or "=" not in raw_line:
            continue
        raw_key, raw_value = raw_line.split("=", 1)
        if raw_key.strip() != "META_DELETION_NODE_ID":
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        identities.append(value)
    if len(identities) != 1 or identities[0] not in {LOCAL_NODE_ID, PEER_NODE_ID}:
        raise RuntimeError("Meta deletion node identity is invalid")
    return identities[0]


def _require_node_identity(path: Path, expected: str) -> None:
    if _read_node_identity(path) != expected:
        raise RuntimeError("Meta synchronization is running on the wrong HA node")


def _meta_fingerprint(values: Mapping[str, str], expected_sha: str) -> str:
    payload = json.dumps(dict(values), separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hmac.new(expected_sha.encode("ascii"), payload, hashlib.sha256).hexdigest()


def _render_meta_values(path: Path, values: Mapping[str, str]) -> bytes:
    require_secure_env_file(path)
    output: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if META_KEY_RE.fullmatch(key) and key not in NODE_LOCAL_META_KEYS:
            continue
        output.append(line)
    output.extend(f"{key}={values[key]}" for key in sorted(values))
    return ("\n".join(output) + "\n").encode("utf-8")


def _write_meta_values(path: Path, values: dict[str, str]) -> None:
    _atomic_write_bytes(path, _render_meta_values(path, values))
    require_secure_env_file(path)
    if _read_meta_values(path) != values:
        raise RuntimeError("Meta environment verification failed")


def _install_exact_backup(source: Path, destination: Path) -> None:
    require_secure_env_file(source)
    _atomic_write_bytes(destination, source.read_bytes())
    require_secure_env_file(destination)
    if destination.read_bytes() != source.read_bytes():
        raise RuntimeError("Exact Meta environment backup verification failed")


def _restore_exact_backup(destination: Path, backup: Path) -> None:
    require_secure_env_file(destination)
    require_secure_env_file(backup)
    _atomic_write_bytes(destination, backup.read_bytes())
    require_secure_env_file(destination)
    if destination.read_bytes() != backup.read_bytes():
        raise RuntimeError("Exact Meta environment rollback verification failed")


def _journal_payload(
    *,
    tx_id: str,
    role: str,
    status: str,
    expected_sha: str,
    old_fingerprint: str,
    new_fingerprint: str,
    maintenance_active: bool,
    preserve_maintenance: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": JOURNAL_SCHEMA,
        "tx_id": tx_id,
        "role": role,
        "status": status,
        "expected_sha": expected_sha,
        "old_fingerprint": old_fingerprint,
        "new_fingerprint": new_fingerprint,
        "maintenance_active": maintenance_active,
        "preserve_maintenance": preserve_maintenance,
    }
    _validate_journal(payload)
    return payload


def _validate_journal(payload: object) -> dict[str, object]:
    required = {
        "schema",
        "tx_id",
        "role",
        "status",
        "expected_sha",
        "old_fingerprint",
        "new_fingerprint",
        "maintenance_active",
        "preserve_maintenance",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise RuntimeError("Meta HA transaction journal is invalid")
    if payload.get("schema") != JOURNAL_SCHEMA:
        raise RuntimeError("Meta HA transaction journal schema is invalid")
    if not isinstance(payload.get("tx_id"), str) or not TX_ID_RE.fullmatch(payload["tx_id"]):
        raise RuntimeError("Meta HA transaction ID is invalid")
    role = payload.get("role")
    status = payload.get("status")
    if role not in {"coordinator", "peer"}:
        raise RuntimeError("Meta HA transaction role is invalid")
    if status not in JOURNAL_STATUSES:
        raise RuntimeError("Meta HA transaction status is invalid")
    if (role == "coordinator" and status not in COORDINATOR_STATUSES) or (
        role == "peer" and status not in PEER_STATUSES
    ):
        raise RuntimeError("Meta HA transaction role/status combination is invalid")
    if not isinstance(payload.get("expected_sha"), str) or not SHA_RE.fullmatch(payload["expected_sha"]):
        raise RuntimeError("Meta HA transaction release is invalid")
    for key in ("old_fingerprint", "new_fingerprint"):
        if not isinstance(payload.get(key), str) or not FINGERPRINT_RE.fullmatch(payload[key]):
            raise RuntimeError("Meta HA transaction fingerprint is invalid")
    if not isinstance(payload.get("maintenance_active"), bool) or not isinstance(
        payload.get("preserve_maintenance"), bool
    ):
        raise RuntimeError("Meta HA transaction maintenance state is invalid")
    return dict(payload)


def _write_journal(state_root: Path, journal: Mapping[str, object]) -> dict[str, object]:
    _ensure_state_root(state_root)
    validated = _validate_journal(dict(journal))
    encoded = json.dumps(validated, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write_bytes(_journal_path(state_root), encoded)
    require_secure_env_file(_journal_path(state_root))
    return validated


def _worker_state_payload(
    *,
    tx_id: str,
    role: str,
    expected_sha: str,
    old_fingerprint: str,
    units: Mapping[str, Mapping[str, bool]],
    status: str = "captured",
    terminal_fingerprint: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": WORKER_STATE_SCHEMA,
        "tx_id": tx_id,
        "role": role,
        "expected_sha": expected_sha,
        "old_fingerprint": old_fingerprint,
        "status": status,
        "terminal_fingerprint": terminal_fingerprint,
        "units": {unit: dict(state) for unit, state in units.items()},
    }
    return _validate_worker_state(payload)


def _validate_worker_state(payload: object) -> dict[str, object]:
    required = {
        "schema",
        "tx_id",
        "role",
        "expected_sha",
        "old_fingerprint",
        "status",
        "terminal_fingerprint",
        "units",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise RuntimeError("Meta HA worker state is invalid")
    if payload.get("schema") != WORKER_STATE_SCHEMA:
        raise RuntimeError("Meta HA worker state schema is invalid")
    if not isinstance(payload.get("tx_id"), str) or not TX_ID_RE.fullmatch(payload["tx_id"]):
        raise RuntimeError("Meta HA worker transaction ID is invalid")
    if payload.get("role") not in {"coordinator", "peer"}:
        raise RuntimeError("Meta HA worker role is invalid")
    if not isinstance(payload.get("expected_sha"), str) or not SHA_RE.fullmatch(payload["expected_sha"]):
        raise RuntimeError("Meta HA worker release is invalid")
    if not isinstance(payload.get("old_fingerprint"), str) or not FINGERPRINT_RE.fullmatch(payload["old_fingerprint"]):
        raise RuntimeError("Meta HA worker source fingerprint is invalid")
    status = payload.get("status")
    if status not in WORKER_STATE_STATUSES:
        raise RuntimeError("Meta HA worker state status is invalid")
    terminal = payload.get("terminal_fingerprint")
    if not isinstance(terminal, str) or (
        (status in {"captured", "quiesced"} and terminal != "")
        or (status in {"restoring", "restored"} and not FINGERPRINT_RE.fullmatch(terminal))
    ):
        raise RuntimeError("Meta HA worker terminal fingerprint is invalid")
    raw_units = payload.get("units")
    if not isinstance(raw_units, dict) or set(raw_units) != set(WORKER_UNITS):
        raise RuntimeError("Meta HA worker inventory is incomplete")
    units: dict[str, dict[str, bool]] = {}
    for unit in WORKER_UNITS:
        raw_state = raw_units.get(unit)
        if not isinstance(raw_state, dict) or set(raw_state) != {"enabled", "active"}:
            raise RuntimeError("Meta HA worker inventory entry is invalid")
        enabled = raw_state.get("enabled")
        active = raw_state.get("active")
        if not isinstance(enabled, bool) or not isinstance(active, bool):
            raise RuntimeError("Meta HA worker inventory state is invalid")
        units[unit] = {"enabled": enabled, "active": active}
    validated = dict(payload)
    validated["units"] = units
    return validated


def _write_worker_state(state_root: Path, worker_state: Mapping[str, object]) -> dict[str, object]:
    _ensure_state_root(state_root)
    validated = _validate_worker_state(dict(worker_state))
    encoded = json.dumps(validated, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write_bytes(_worker_state_path(state_root), encoded)
    require_secure_env_file(_worker_state_path(state_root))
    return validated


def _load_worker_state(state_root: Path) -> dict[str, object] | None:
    path = _worker_state_path(state_root)
    if not _entry_exists(path):
        return None
    require_secure_env_file(path)
    try:
        decoded: Any = json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Meta HA worker state is unreadable") from exc
    return _validate_worker_state(decoded)


def _set_worker_state_status(
    state_root: Path,
    worker_state: Mapping[str, object],
    status: str,
    *,
    terminal_fingerprint: str | None = None,
) -> dict[str, object]:
    updated = dict(worker_state)
    updated["status"] = status
    if terminal_fingerprint is not None:
        updated["terminal_fingerprint"] = terminal_fingerprint
    return _write_worker_state(state_root, updated)


def _worker_state_digest(worker_state: Mapping[str, object]) -> str:
    validated = _validate_worker_state(dict(worker_state))
    encoded = json.dumps(validated, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stage_authority_payload(
    *,
    tx_id: str,
    expected_sha: str,
    old_fingerprint: str,
    backup_sha256: str,
    worker_state_sha256: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": STAGE_AUTHORITY_SCHEMA,
        "tx_id": tx_id,
        "expected_sha": expected_sha,
        "old_fingerprint": old_fingerprint,
        "backup_sha256": backup_sha256,
        "worker_state_sha256": worker_state_sha256,
        "status": "both_nodes_quiesced",
    }
    return _validate_stage_authority(payload)


def _validate_stage_authority(payload: object) -> dict[str, object]:
    required = {
        "schema",
        "tx_id",
        "expected_sha",
        "old_fingerprint",
        "backup_sha256",
        "worker_state_sha256",
        "status",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise RuntimeError("Meta HA pre-stage authority is invalid")
    if payload.get("schema") != STAGE_AUTHORITY_SCHEMA or payload.get("status") != "both_nodes_quiesced":
        raise RuntimeError("Meta HA pre-stage authority schema is invalid")
    if not isinstance(payload.get("tx_id"), str) or not TX_ID_RE.fullmatch(payload["tx_id"]):
        raise RuntimeError("Meta HA pre-stage authority transaction is invalid")
    if not isinstance(payload.get("expected_sha"), str) or not SHA_RE.fullmatch(payload["expected_sha"]):
        raise RuntimeError("Meta HA pre-stage authority release is invalid")
    for key in ("old_fingerprint", "backup_sha256", "worker_state_sha256"):
        if not isinstance(payload.get(key), str) or not FINGERPRINT_RE.fullmatch(payload[key]):
            raise RuntimeError("Meta HA pre-stage authority digest is invalid")
    return dict(payload)


def _write_stage_authority(state_root: Path, authority: Mapping[str, object]) -> dict[str, object]:
    _ensure_state_root(state_root)
    validated = _validate_stage_authority(dict(authority))
    encoded = json.dumps(validated, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write_bytes(_stage_authority_path(state_root), encoded)
    require_secure_env_file(_stage_authority_path(state_root))
    return validated


def _load_stage_authority(state_root: Path) -> dict[str, object] | None:
    path = _stage_authority_path(state_root)
    if not _entry_exists(path):
        return None
    require_secure_env_file(path)
    try:
        decoded: Any = json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Meta HA pre-stage authority is unreadable") from exc
    return _validate_stage_authority(decoded)


def _require_stage_authority(
    state_root: Path,
    *,
    expected_sha: str,
    require_preimage: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    authority = _load_stage_authority(state_root)
    worker_state = _load_worker_state(state_root)
    backup = _backup_path(state_root)
    if authority is None or worker_state is None or not _entry_exists(backup):
        raise RuntimeError("Both-node Meta pre-stage authority is absent")
    require_secure_env_file(backup)
    if (
        authority["expected_sha"] != expected_sha
        or authority["tx_id"] != worker_state["tx_id"]
        or authority["old_fingerprint"] != worker_state["old_fingerprint"]
        or worker_state["role"] != "coordinator"
        or worker_state["expected_sha"] != expected_sha
        or worker_state["status"] != "quiesced"
        or authority["backup_sha256"] != hashlib.sha256(backup.read_bytes()).hexdigest()
        or authority["worker_state_sha256"] != _worker_state_digest(worker_state)
    ):
        raise RuntimeError("Both-node Meta pre-stage authority does not match durable state")
    backup_values = _read_meta_values(backup)
    if _meta_fingerprint(backup_values, expected_sha) != authority["old_fingerprint"]:
        raise RuntimeError("Meta HA pre-stage backup fingerprint is invalid")
    if require_preimage and ENV_PATH.read_bytes() != backup.read_bytes():
        raise RuntimeError("Canonical Meta environment changed after pre-stage authorization")
    _verify_worker_units_quiesced()
    return authority, worker_state


def _refuse_conflicting_ha_transaction(state_root: Path) -> None:
    _ensure_state_root(state_root)
    conflicts = (
        (_bootstrap_active_path(state_root), "identity bootstrap"),
        (_deploy_active_path(state_root), "release deploy"),
        (_deploy_node_active_path(state_root), "node release deploy"),
        (_bootstrap_coordinator_path(state_root), "bootstrap coordinator"),
        (_controlled_failover_active_path(state_root), "controlled failover"),
        (_nfs_retire_active_path(state_root), "registry NFS retirement"),
        (_python_runtime_provision_active_path(state_root), "Python runtime provision participant"),
        (_python_runtime_provision_coordinator_path(state_root), "Python runtime provision coordinator"),
    )
    for path, label in conflicts:
        if _entry_exists(path):
            require_secure_env_file(path)
            raise RuntimeError(f"Meta HA {label} transaction requires recovery")


def _load_journal(state_root: Path) -> dict[str, object] | None:
    _refuse_conflicting_ha_transaction(state_root)
    path = _journal_path(state_root)
    if not _entry_exists(path):
        return None
    require_secure_env_file(path)
    try:
        decoded: Any = json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Meta HA transaction journal is unreadable") from exc
    return _validate_journal(decoded)


def _require_durable_backup(state_root: Path, journal: Mapping[str, object]) -> None:
    backup = _backup_path(state_root)
    if _entry_exists(backup):
        require_secure_env_file(backup)
        return
    if journal["status"] not in {"finalizing_committed", "finalizing_rolled_back"}:
        raise RuntimeError("Meta HA transaction backup is absent")


def _set_journal_status(
    state_root: Path,
    journal: Mapping[str, object],
    status: str,
    *,
    preserve_maintenance: bool | None = None,
) -> dict[str, object]:
    updated = dict(journal)
    updated["status"] = status
    if preserve_maintenance is not None:
        updated["preserve_maintenance"] = preserve_maintenance
    return _write_journal(state_root, updated)


def _require_secure_marker(path: Path) -> None:
    require_secure_env_file(path)


def _arm_marker(path: Path) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    _atomic_write_bytes(path, b"meta-ha-maintenance\n")
    _require_secure_marker(path)


def _ensure_maintenance_armed(
    state_root: Path,
    *,
    restore_missing_persistent: bool = False,
) -> None:
    _ensure_state_root(state_root)
    persistent = _persistent_maintenance_path(state_root)
    try:
        _require_secure_marker(persistent)
    except RuntimeError:
        if not restore_missing_persistent or _entry_exists(persistent):
            raise
        # A validated unresolved journal is durable authority to recreate a
        # marker lost in the terminal-cleanup crash window.  Insecure existing
        # entries are never repaired or followed.
        _arm_marker(persistent)
    try:
        _require_secure_marker(VOLATILE_MAINTENANCE_PATH)
    except RuntimeError:
        # /run is volatile across reboot.  A durable marker authorizes restoring
        # its volatile companion while the transaction remains unresolved.
        _arm_marker(VOLATILE_MAINTENANCE_PATH)


def _clear_maintenance(state_root: Path) -> None:
    # Clear the reboot-volatile marker first; the persistent marker remains the
    # fail-closed authority until the final durable unlink.
    _durable_unlink(VOLATILE_MAINTENANCE_PATH)
    _durable_unlink(_persistent_maintenance_path(state_root))


@contextmanager
def _exclusive_lock(path: Path = LOCK_PATH, timeout_seconds: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or current.st_uid != os.geteuid() or current.st_gid != os.getegid():
            raise RuntimeError("Meta HA synchronization lock security contract is invalid")
        os.fchmod(fd, 0o600)
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Peer Meta synchronization lock timed out") from None
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _verify_release(expected_sha: str) -> None:
    _require_exact_release(REPO_DIR, expected_sha, "scripts/ha/sync_meta_env_to_peer.py")


def _http_json(path: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8003{path}", timeout=3) as response:
            return response.status, json.loads(response.read(100000))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read(100000))


def _wait_for_ready(*, maintenance_active: bool = False) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            if maintenance_active:
                health_status, health = _http_json("/api/health")
                ready_status, ready = _http_json("/api/ready")
                check = ready.get("checks", {}).get("maintenance", {}) if isinstance(ready, dict) else {}
                if (
                    health_status == 200
                    and isinstance(health, dict)
                    and health.get("ok") is True
                    and health.get("role") == "liveness"
                    and ready_status == 503
                    and isinstance(ready, dict)
                    and ready.get("ok") is False
                    and ready.get("role") == "readiness"
                    and isinstance(check, dict)
                    and check.get("ok") is False
                ):
                    return
            else:
                status, ready = _http_json("/api/ready")
                if status == 200 and isinstance(ready, dict) and ready.get("ok") is True:
                    return
        except Exception:
            pass
        time.sleep(1)
    state = "maintenance liveness" if maintenance_active else "readiness"
    raise RuntimeError(f"API {state} failed after Meta environment change")


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["systemctl", *args],
        check=check,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=PROCESS_TIMEOUT_SECONDS,
    )


def _systemctl_output(*args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["systemctl", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=PROCESS_TIMEOUT_SECONDS,
    )
    return result.returncode, result.stdout.strip()


def _worker_unit_state(unit: str) -> dict[str, bool]:
    enabled_code, enabled_state = _systemctl_output("is-enabled", unit)
    if enabled_state == "enabled" and enabled_code == 0:
        enabled = True
    elif enabled_state == "disabled" and enabled_code != 0:
        enabled = False
    else:
        raise RuntimeError("Worker enablement state is unsupported")
    active_code, active_state = _systemctl_output("is-active", unit)
    if active_state == "active" and active_code == 0:
        active = True
    elif active_state == "inactive" and active_code != 0:
        active = False
    else:
        raise RuntimeError("Worker runtime state is unsafe")
    return {"enabled": enabled, "active": active}


def _capture_worker_units() -> dict[str, dict[str, bool]]:
    # Inventory every unit before the first persistent systemd mutation.  A
    # partial inventory must never be used as rollback authority.
    return {unit: _worker_unit_state(unit) for unit in WORKER_UNITS}


def _verify_worker_units_quiesced() -> None:
    for unit in WORKER_UNITS:
        state = _worker_unit_state(unit)
        if state["enabled"] or state["active"]:
            raise RuntimeError("All Meta workers must remain disabled and stopped")


def _quiesce_worker_units() -> None:
    for unit in WORKER_UNITS:
        _systemctl("disable", "--now", unit)
    deadline = time.monotonic() + PROCESS_TIMEOUT_SECONDS
    while True:
        try:
            _verify_worker_units_quiesced()
            return
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)


def _capture_and_quiesce_workers(
    state_root: Path,
    *,
    tx_id: str,
    role: str,
    expected_sha: str,
    old_fingerprint: str,
) -> dict[str, object]:
    current = _load_worker_state(state_root)
    if current is None:
        current = _worker_state_payload(
            tx_id=tx_id,
            role=role,
            expected_sha=expected_sha,
            old_fingerprint=old_fingerprint,
            units=_capture_worker_units(),
        )
        # The exact original state is durable before the first disable/stop.
        current = _write_worker_state(state_root, current)
    elif (
        current["tx_id"] != tx_id
        or current["role"] != role
        or current["expected_sha"] != expected_sha
        or current["old_fingerprint"] != old_fingerprint
        or current["status"] not in {"captured", "quiesced"}
    ):
        raise RuntimeError("Existing Meta HA worker state requires recovery")
    _quiesce_worker_units()
    if current["status"] != "quiesced":
        current = _set_worker_state_status(state_root, current, "quiesced")
    _verify_worker_units_quiesced()
    return current


def _require_matching_worker_state(
    state_root: Path,
    *,
    tx_id: str,
    role: str,
    expected_sha: str,
    old_fingerprint: str,
) -> dict[str, object]:
    current = _load_worker_state(state_root)
    if current is None or (
        current["tx_id"] != tx_id
        or current["role"] != role
        or current["expected_sha"] != expected_sha
        or current["old_fingerprint"] != old_fingerprint
    ):
        raise RuntimeError("Meta HA worker state does not match the transaction")
    return current


def _ensure_workers_quiesced(
    state_root: Path,
    journal: Mapping[str, object],
    *,
    role: str,
) -> dict[str, object]:
    current = _require_matching_worker_state(
        state_root,
        tx_id=str(journal["tx_id"]),
        role=role,
        expected_sha=str(journal["expected_sha"]),
        old_fingerprint=str(journal["old_fingerprint"]),
    )
    if current["status"] not in {"captured", "quiesced"}:
        raise RuntimeError("Meta HA workers are already in terminal restoration")
    _quiesce_worker_units()
    if current["status"] != "quiesced":
        current = _set_worker_state_status(state_root, current, "quiesced")
    return current


def _restart_api(*, maintenance_active: bool) -> None:
    _systemctl("restart", "linasbot")
    _systemctl("is-active", "--quiet", "linasbot")
    _wait_for_ready(maintenance_active=maintenance_active)


def _read_unit_runtime_meta_values(unit: str, expected_node_id: str) -> dict[str, str]:
    try:
        raw_pid = subprocess.check_output(
            ["systemctl", "show", unit, "--property=MainPID", "--value"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=PROCESS_TIMEOUT_SECONDS,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Current runtime process lookup failed for {unit}") from exc
    if not raw_pid.isdigit() or int(raw_pid) <= 0:
        raise RuntimeError("Current runtime process is unavailable")
    environ_path = Path("/proc") / raw_pid / "environ"
    try:
        raw_environment = environ_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Current runtime environment is unavailable for {unit}") from exc
    values: dict[str, str] = {}
    for entry in raw_environment.split(b"\0"):
        if b"=" not in entry:
            continue
        raw_key, raw_value = entry.split(b"=", 1)
        key = raw_key.decode("utf-8", "strict")
        if not META_KEY_RE.fullmatch(key):
            continue
        value = raw_value.decode("utf-8", "strict")
        if any(character in value for character in ("\n", "\r", "\0")) or len(value) > 65536:
            raise RuntimeError("Current runtime Meta environment is invalid")
        values[key] = value
    if values.get("META_DELETION_NODE_ID") != expected_node_id:
        raise RuntimeError("Current runtime Meta node identity is invalid")
    cluster = {key: value for key, value in values.items() if key not in NODE_LOCAL_META_KEYS}
    if not cluster:
        raise RuntimeError("Current runtime Meta environment is empty")
    return cluster


def _read_runtime_meta_values(expected_node_id: str) -> dict[str, str]:
    return _read_unit_runtime_meta_values("linasbot", expected_node_id)


def _verify_api_values(expected_values: dict[str, str], *, expected_node_id: str) -> None:
    if _read_runtime_meta_values(expected_node_id) != expected_values:
        raise RuntimeError("Live API Meta environment does not match the canonical environment")


def _verify_runtime_values(expected_values: dict[str, str], *, expected_node_id: str) -> None:
    _verify_api_values(expected_values, expected_node_id=expected_node_id)
    for unit in WORKER_UNITS:
        state = _worker_unit_state(unit)
        if state["active"] and _read_unit_runtime_meta_values(unit, expected_node_id) != expected_values:
            raise RuntimeError("Live worker Meta environment does not match the canonical environment")


def _restart_api_and_verify(
    expected_values: dict[str, str],
    *,
    expected_node_id: str,
    maintenance_active: bool,
) -> None:
    _restart_api(maintenance_active=maintenance_active)
    _verify_api_values(expected_values, expected_node_id=expected_node_id)


def _verify_transition_runtime(
    expected_values: dict[str, str],
    *,
    expected_node_id: str,
    state_root: Path,
    journal: Mapping[str, object],
    role: str,
) -> None:
    _ensure_workers_quiesced(state_root, journal, role=role)
    _verify_api_values(expected_values, expected_node_id=expected_node_id)


def _verify_worker_units_restored(
    worker_state: Mapping[str, object],
    expected_values: dict[str, str],
    *,
    expected_node_id: str,
) -> None:
    units = worker_state["units"]
    if not isinstance(units, dict):  # Defensive; validated durable state is required.
        raise RuntimeError("Meta HA worker inventory is invalid")
    for unit in WORKER_UNITS:
        expected = units[unit]
        if not isinstance(expected, dict) or _worker_unit_state(unit) != expected:
            raise RuntimeError("Meta HA worker state restoration is incomplete")
        if expected["active"] and _read_unit_runtime_meta_values(unit, expected_node_id) != expected_values:
            raise RuntimeError("Restored worker Meta environment does not match the canonical environment")


def _restore_worker_units(
    state_root: Path,
    worker_state: Mapping[str, object],
    *,
    terminal_fingerprint: str,
    expected_values: dict[str, str],
    expected_node_id: str,
) -> dict[str, object]:
    current = _validate_worker_state(dict(worker_state))
    status = str(current["status"])
    if status in {"captured", "quiesced"}:
        current = _set_worker_state_status(
            state_root,
            current,
            "restoring",
            terminal_fingerprint=terminal_fingerprint,
        )
    elif current["terminal_fingerprint"] != terminal_fingerprint:
        raise RuntimeError("Meta HA worker restoration target is inconsistent")
    units = current["units"]
    if not isinstance(units, dict):
        raise RuntimeError("Meta HA worker inventory is invalid")
    if current["status"] != "restored":
        # Restore persistent enablement for the full inventory before allowing
        # any queue to process again.  This is idempotent after a crash.
        for unit in WORKER_UNITS:
            expected = units[unit]
            if not isinstance(expected, dict):
                raise RuntimeError("Meta HA worker inventory is invalid")
            _systemctl("enable" if expected["enabled"] else "disable", unit)
        for unit in WORKER_UNITS:
            expected = units[unit]
            if not isinstance(expected, dict):
                raise RuntimeError("Meta HA worker inventory is invalid")
            _systemctl("start" if expected["active"] else "stop", unit)
        _verify_worker_units_restored(current, expected_values, expected_node_id=expected_node_id)
        current = _set_worker_state_status(
            state_root,
            current,
            "restored",
            terminal_fingerprint=terminal_fingerprint,
        )
    _verify_worker_units_restored(current, expected_values, expected_node_id=expected_node_id)
    return current


def _common_request(payload: object) -> tuple[str, str, str, bool, dict[str, object]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Peer Meta transaction request is invalid")
    action = str(payload.get("action") or "")
    if action not in {"quiesce", "prepare", "query", "commit", "rollback", "prove", "finalize"}:
        raise RuntimeError("Peer Meta transaction action is invalid")
    base = {"schema", "action", "expected_sha", "source_node_id", "tx_id", "maintenance_active"}
    expected = base | ({"meta_values"} if action == "prepare" else set())
    if action == "quiesce":
        expected |= {"old_fingerprint"}
    if action == "finalize":
        expected |= {"preserve_maintenance"}
    if set(payload) != expected or payload.get("schema") != PROTOCOL_SCHEMA:
        raise RuntimeError("Peer Meta transaction request schema is invalid")
    raw_expected_sha = payload.get("expected_sha")
    raw_tx_id = payload.get("tx_id")
    raw_source = payload.get("source_node_id")
    if not isinstance(raw_expected_sha, str) or not isinstance(raw_tx_id, str) or not isinstance(raw_source, str):
        raise RuntimeError("Peer Meta transaction identity is invalid")
    expected_sha = raw_expected_sha
    tx_id = raw_tx_id
    source = raw_source
    maintenance_active = payload.get("maintenance_active")
    if not SHA_RE.fullmatch(expected_sha) or not TX_ID_RE.fullmatch(tx_id):
        raise RuntimeError("Peer Meta transaction identity is invalid")
    if source != LOCAL_NODE_ID or source == PEER_NODE_ID:
        raise RuntimeError("Peer Meta synchronization source is invalid")
    if not isinstance(maintenance_active, bool):
        raise RuntimeError("Peer Meta maintenance state is invalid")
    if action == "quiesce":
        old_fingerprint = payload.get("old_fingerprint")
        if not isinstance(old_fingerprint, str) or not FINGERPRINT_RE.fullmatch(old_fingerprint):
            raise RuntimeError("Peer Meta source fingerprint is invalid")
    return action, expected_sha, tx_id, maintenance_active, dict(payload)


def _prepare_values(payload: Mapping[str, object]) -> dict[str, str]:
    raw_values = payload.get("meta_values")
    if not isinstance(raw_values, dict) or not raw_values:
        raise RuntimeError("Peer Meta environment mapping is invalid")
    values: dict[str, str] = {}
    for raw_key, raw_value in raw_values.items():
        key = str(raw_key)
        if not META_KEY_RE.fullmatch(key) or key in NODE_LOCAL_META_KEYS or not isinstance(raw_value, str):
            raise RuntimeError("Peer Meta environment entry is invalid")
        if any(character in raw_value for character in ("\n", "\r", "\0")) or len(raw_value) > 65536:
            raise RuntimeError("Peer Meta environment value is invalid")
        values[key] = raw_value
    return values


def _peer_response(
    state_root: Path, journal: Mapping[str, object] | None, env_path: Path, sha: str
) -> dict[str, object]:
    worker_state = _load_worker_state(state_root)
    if journal is None and worker_state is not None:
        tx_id = str(worker_state["tx_id"])
        status = "finalized" if worker_state["status"] == "restored" else "quiesced"
    else:
        tx_id = "" if journal is None else str(journal["tx_id"])
        status = "absent" if journal is None else str(journal["status"])
    return {
        "schema": PROTOCOL_SCHEMA,
        "tx_id": tx_id,
        "status": status,
        "fingerprint": _meta_fingerprint(_read_meta_values(env_path), sha),
        "journal_present": journal is not None,
        "backup_present": _entry_exists(_backup_path(state_root)),
    }


def _require_matching_peer_journal(
    state_root: Path,
    *,
    tx_id: str,
    expected_sha: str,
    maintenance_active: bool,
    journal: Mapping[str, object] | None = None,
) -> dict[str, object]:
    current = dict(journal) if journal is not None else _load_journal(state_root)
    if current is None:
        raise RuntimeError("Peer Meta transaction journal is absent")
    if (
        current["role"] != "peer"
        or current["tx_id"] != tx_id
        or current["expected_sha"] != expected_sha
        or current["maintenance_active"] is not maintenance_active
    ):
        raise RuntimeError("Peer Meta transaction journal does not match the request")
    return current


def _rollback_peer_journal(
    env_path: Path,
    state_root: Path,
    journal: Mapping[str, object],
) -> dict[str, object]:
    _ensure_workers_quiesced(state_root, journal, role="peer")
    updated = _set_journal_status(state_root, journal, "rollback_requested")
    backup = _backup_path(state_root)
    _restore_exact_backup(env_path, backup)
    _require_node_identity(env_path, PEER_NODE_ID)
    old_values = _read_meta_values(env_path)
    if _meta_fingerprint(old_values, str(updated["expected_sha"])) != updated["old_fingerprint"]:
        raise RuntimeError("Peer rollback backup fingerprint is invalid")
    _restart_api_and_verify(
        old_values,
        expected_node_id=PEER_NODE_ID,
        maintenance_active=bool(updated["maintenance_active"]),
    )
    _ensure_workers_quiesced(state_root, updated, role="peer")
    return _set_journal_status(state_root, updated, "rolled_back")


def _commit_peer_journal(
    env_path: Path,
    state_root: Path,
    journal: Mapping[str, object],
) -> dict[str, object]:
    _ensure_workers_quiesced(state_root, journal, role="peer")
    updated = _set_journal_status(state_root, journal, "commit_requested")
    values = _read_meta_values(env_path)
    if _meta_fingerprint(values, str(updated["expected_sha"])) != updated["new_fingerprint"]:
        return _rollback_peer_journal(env_path, state_root, updated)
    try:
        _restart_api_and_verify(
            values,
            expected_node_id=PEER_NODE_ID,
            maintenance_active=bool(updated["maintenance_active"]),
        )
        _ensure_workers_quiesced(state_root, updated, role="peer")
    except Exception:
        return _rollback_peer_journal(env_path, state_root, updated)
    return _set_journal_status(state_root, updated, "committed")


def _recover_peer_journal(
    env_path: Path,
    state_root: Path,
    journal: Mapping[str, object],
) -> dict[str, object]:
    status = str(journal["status"])
    if status in {"backup_created", "write_started", "rollback_requested"}:
        return _rollback_peer_journal(env_path, state_root, journal)
    if status == "commit_requested":
        return _commit_peer_journal(env_path, state_root, journal)
    if status in {"committed", "parity_proven"}:
        values = _read_meta_values(env_path)
        if _meta_fingerprint(values, str(journal["expected_sha"])) != journal["new_fingerprint"]:
            raise RuntimeError("Committed peer Meta environment fingerprint is invalid")
        try:
            _verify_transition_runtime(
                values,
                expected_node_id=PEER_NODE_ID,
                state_root=state_root,
                journal=journal,
                role="peer",
            )
        except Exception:
            _ensure_workers_quiesced(state_root, journal, role="peer")
            _restart_api_and_verify(
                values,
                expected_node_id=PEER_NODE_ID,
                maintenance_active=bool(journal["maintenance_active"]),
            )
        return dict(journal)
    if status == "rolled_back":
        values = _read_meta_values(env_path)
        if _meta_fingerprint(values, str(journal["expected_sha"])) != journal["old_fingerprint"]:
            raise RuntimeError("Rolled-back peer Meta environment fingerprint is invalid")
        try:
            _verify_transition_runtime(
                values,
                expected_node_id=PEER_NODE_ID,
                state_root=state_root,
                journal=journal,
                role="peer",
            )
        except Exception:
            _ensure_workers_quiesced(state_root, journal, role="peer")
            _restart_api_and_verify(
                values,
                expected_node_id=PEER_NODE_ID,
                maintenance_active=bool(journal["maintenance_active"]),
            )
        return dict(journal)
    if status == "prepared":
        _ensure_workers_quiesced(state_root, journal, role="peer")
        values = _read_meta_values(env_path)
        if _meta_fingerprint(values, str(journal["expected_sha"])) != journal["new_fingerprint"]:
            return _rollback_peer_journal(env_path, state_root, journal)
        return dict(journal)
    return dict(journal)


def _finalize_peer(
    env_path: Path,
    state_root: Path,
    journal: Mapping[str, object],
    *,
    preserve_maintenance: bool,
) -> dict[str, object]:
    status = str(journal["status"])
    if status not in {"parity_proven", "rolled_back", "finalizing_committed", "finalizing_rolled_back"}:
        raise RuntimeError("Peer Meta transaction is not safe to finalize")
    terminal_committed = status in {"parity_proven", "finalizing_committed"}
    terminal = "finalizing_committed" if terminal_committed else "finalizing_rolled_back"
    updated = _set_journal_status(
        state_root,
        journal,
        terminal,
        preserve_maintenance=preserve_maintenance,
    )
    expected = updated["new_fingerprint"] if terminal_committed else updated["old_fingerprint"]
    values = _read_meta_values(env_path)
    if _meta_fingerprint(values, str(updated["expected_sha"])) != expected:
        raise RuntimeError("Peer terminal Meta environment fingerprint is invalid")
    worker_state = _require_matching_worker_state(
        state_root,
        tx_id=str(updated["tx_id"]),
        role="peer",
        expected_sha=str(updated["expected_sha"]),
        old_fingerprint=str(updated["old_fingerprint"]),
    )
    if worker_state["status"] in {"captured", "quiesced"}:
        _verify_transition_runtime(
            values,
            expected_node_id=PEER_NODE_ID,
            state_root=state_root,
            journal=updated,
            role="peer",
        )
    worker_state = _restore_worker_units(
        state_root,
        worker_state,
        terminal_fingerprint=str(expected),
        expected_values=values,
        expected_node_id=PEER_NODE_ID,
    )
    _verify_runtime_values(values, expected_node_id=PEER_NODE_ID)
    _durable_unlink(_backup_path(state_root))
    if not preserve_maintenance:
        _clear_maintenance(state_root)
    _durable_unlink(_journal_path(state_root))
    _durable_unlink(_stage_authority_path(state_root))
    _durable_unlink(_worker_state_path(state_root))
    return {
        "schema": PROTOCOL_SCHEMA,
        "tx_id": str(updated["tx_id"]),
        "status": "finalized",
        "fingerprint": str(expected),
        "journal_present": False,
        "backup_present": False,
    }


def _finish_orphan_worker_restore(
    env_path: Path,
    state_root: Path,
    worker_state: Mapping[str, object],
) -> dict[str, object]:
    if worker_state["status"] not in {"restoring", "restored"}:
        raise RuntimeError("Meta HA worker state has no terminal restoration decision")
    values = _read_meta_values(env_path)
    terminal = str(worker_state["terminal_fingerprint"])
    if _meta_fingerprint(values, str(worker_state["expected_sha"])) != terminal:
        raise RuntimeError("Orphaned Meta HA worker terminal fingerprint is invalid")
    restored = _restore_worker_units(
        state_root,
        worker_state,
        terminal_fingerprint=terminal,
        expected_values=values,
        expected_node_id=PEER_NODE_ID,
    )
    _verify_runtime_values(values, expected_node_id=PEER_NODE_ID)
    _durable_unlink(_worker_state_path(state_root))
    return {
        "schema": PROTOCOL_SCHEMA,
        "tx_id": str(restored["tx_id"]),
        "status": "finalized",
        "fingerprint": terminal,
        "journal_present": False,
        "backup_present": _entry_exists(_backup_path(state_root)),
    }


def _execute_request(
    payload: object,
    *,
    env_path: Path = ENV_PATH,
    lock_path: Path = LOCK_PATH,
    state_root: Path = STATE_ROOT,
) -> dict[str, object]:
    action, expected_sha, tx_id, maintenance_active, request = _common_request(payload)
    with _exclusive_lock(lock_path):
        _verify_release(expected_sha)
        _refuse_conflicting_ha_transaction(state_root)
        _require_node_identity(env_path, PEER_NODE_ID)
        journal = _load_journal(state_root)
        worker_state = _load_worker_state(state_root)
        if journal is not None:
            journal = _require_matching_peer_journal(
                state_root,
                tx_id=tx_id,
                expected_sha=expected_sha,
                maintenance_active=maintenance_active,
                journal=journal,
            )
            _require_durable_backup(state_root, journal)
            if maintenance_active:
                _ensure_maintenance_armed(state_root, restore_missing_persistent=True)
            if journal["status"] in {"finalizing_committed", "finalizing_rolled_back"}:
                return _finalize_peer(
                    env_path,
                    state_root,
                    journal,
                    preserve_maintenance=bool(journal["preserve_maintenance"]),
                )
            _ensure_workers_quiesced(state_root, journal, role="peer")
        elif worker_state is not None:
            if (
                worker_state["tx_id"] != tx_id
                or worker_state["role"] != "peer"
                or worker_state["expected_sha"] != expected_sha
            ):
                raise RuntimeError("Peer Meta worker state does not match the request")
            if maintenance_active:
                _ensure_maintenance_armed(state_root, restore_missing_persistent=True)
            if worker_state["status"] in {"restoring", "restored"}:
                return _finish_orphan_worker_restore(env_path, state_root, worker_state)
            _quiesce_worker_units()
            if worker_state["status"] != "quiesced":
                worker_state = _set_worker_state_status(state_root, worker_state, "quiesced")
        elif maintenance_active and action == "quiesce":
            # The workflow drains and arms both nodes before asking the peer to
            # persist its worker inventory and stop every queue.
            _ensure_maintenance_armed(state_root)
        if action == "quiesce":
            if not maintenance_active:
                raise RuntimeError("Peer worker quiescence requires maintenance")
            old_fingerprint = str(request["old_fingerprint"])
            if journal is not None:
                if journal["old_fingerprint"] != old_fingerprint:
                    raise RuntimeError("Peer worker quiescence does not match the transaction")
                return _peer_response(state_root, journal, env_path, expected_sha)
            current_fingerprint = _meta_fingerprint(_read_meta_values(env_path), expected_sha)
            if current_fingerprint != old_fingerprint:
                raise RuntimeError("Peer canonical environment changed before worker quiescence")
            if _entry_exists(_backup_path(state_root)):
                raise RuntimeError("Orphaned peer Meta backup requires recovery")
            worker_state = _capture_and_quiesce_workers(
                state_root,
                tx_id=tx_id,
                role="peer",
                expected_sha=expected_sha,
                old_fingerprint=old_fingerprint,
            )
            return _peer_response(state_root, None, env_path, expected_sha)
        if action == "prepare":
            values = _prepare_values(request)
            if journal is not None:
                if _meta_fingerprint(values, expected_sha) != journal["new_fingerprint"]:
                    raise RuntimeError("Peer prepare retry does not match the durable transaction")
                recovered = _recover_peer_journal(env_path, state_root, journal)
                return _peer_response(state_root, recovered, env_path, expected_sha)
            if worker_state is None or worker_state["status"] != "quiesced":
                raise RuntimeError("Peer workers were not durably quiesced before the environment write")
            old_values = _read_meta_values(env_path)
            old_fingerprint = _meta_fingerprint(old_values, expected_sha)
            if worker_state["old_fingerprint"] != old_fingerprint:
                raise RuntimeError("Peer pre-stage worker state does not match the canonical environment")
            _ensure_state_root(state_root)
            journal = _journal_payload(
                tx_id=tx_id,
                role="peer",
                status="backup_created",
                expected_sha=expected_sha,
                old_fingerprint=_meta_fingerprint(old_values, expected_sha),
                new_fingerprint=_meta_fingerprint(values, expected_sha),
                maintenance_active=maintenance_active,
            )
            _install_exact_backup(env_path, _backup_path(state_root))
            journal = _write_journal(state_root, journal)
            journal = _set_journal_status(state_root, journal, "write_started")
            try:
                _write_meta_values(env_path, values)
                _require_node_identity(env_path, PEER_NODE_ID)
                journal = _set_journal_status(state_root, journal, "prepared")
            except Exception:
                journal = _rollback_peer_journal(env_path, state_root, journal)
            return _peer_response(state_root, journal, env_path, expected_sha)

        if journal is None:
            if worker_state is not None:
                if action == "rollback":
                    values = _read_meta_values(env_path)
                    old_fingerprint = str(worker_state["old_fingerprint"])
                    if _meta_fingerprint(values, expected_sha) != old_fingerprint:
                        raise RuntimeError("Peer pre-stage rollback environment is uncertain")
                    orphan_backup = _backup_path(state_root)
                    if _entry_exists(orphan_backup):
                        require_secure_env_file(orphan_backup)
                        if orphan_backup.read_bytes() != env_path.read_bytes():
                            raise RuntimeError("Peer pre-journal backup has an uncertain environment outcome")
                    try:
                        _verify_api_values(values, expected_node_id=PEER_NODE_ID)
                    except Exception:
                        _restart_api_and_verify(
                            values,
                            expected_node_id=PEER_NODE_ID,
                            maintenance_active=maintenance_active,
                        )
                    _restore_worker_units(
                        state_root,
                        worker_state,
                        terminal_fingerprint=old_fingerprint,
                        expected_values=values,
                        expected_node_id=PEER_NODE_ID,
                    )
                    _durable_unlink(orphan_backup)
                    _durable_unlink(_worker_state_path(state_root))
                    return _peer_response(state_root, None, env_path, expected_sha)
                return _peer_response(state_root, None, env_path, expected_sha)
            orphan = _backup_path(state_root)
            if _entry_exists(orphan):
                require_secure_env_file(orphan)
                if action == "finalize":
                    preserve = request.get("preserve_maintenance")
                    if not isinstance(preserve, bool):
                        raise RuntimeError("Peer finalize maintenance state is invalid")
                    old_fingerprint = _meta_fingerprint(_read_meta_values(orphan), expected_sha)
                    current_fingerprint = _meta_fingerprint(_read_meta_values(env_path), expected_sha)
                    if old_fingerprint != current_fingerprint:
                        raise RuntimeError("Orphaned peer backup has an uncertain transaction outcome")
                    # No peer write can precede its journal.  An equal orphan is
                    # therefore a pre-write backup and is safe to retire only
                    # when the coordinator explicitly finalizes recovery.
                    _durable_unlink(orphan)
            return _peer_response(state_root, None, env_path, expected_sha)
        journal = _recover_peer_journal(env_path, state_root, journal)
        if action == "query":
            return _peer_response(state_root, journal, env_path, expected_sha)
        if action == "commit":
            if journal["status"] not in {"prepared", "commit_requested", "committed", "parity_proven"}:
                return _peer_response(state_root, journal, env_path, expected_sha)
            if journal["status"] in {"prepared", "commit_requested"}:
                journal = _commit_peer_journal(env_path, state_root, journal)
            return _peer_response(state_root, journal, env_path, expected_sha)
        if action == "rollback":
            if journal["status"] in COMMIT_DECISION_STATUSES:
                raise RuntimeError("Committed peer Meta transaction cannot be rolled back")
            if journal["status"] != "rolled_back":
                journal = _rollback_peer_journal(env_path, state_root, journal)
            return _peer_response(state_root, journal, env_path, expected_sha)
        if action == "prove":
            if journal["status"] not in {"committed", "parity_proven"}:
                return _peer_response(state_root, journal, env_path, expected_sha)
            values = _read_meta_values(env_path)
            _verify_transition_runtime(
                values,
                expected_node_id=PEER_NODE_ID,
                state_root=state_root,
                journal=journal,
                role="peer",
            )
            if _meta_fingerprint(values, expected_sha) != journal["new_fingerprint"]:
                raise RuntimeError("Peer parity proof fingerprint is invalid")
            journal = _set_journal_status(state_root, journal, "parity_proven")
            return _peer_response(state_root, journal, env_path, expected_sha)
        preserve = request.get("preserve_maintenance")
        if not isinstance(preserve, bool):
            raise RuntimeError("Peer finalize maintenance state is invalid")
        return _finalize_peer(
            env_path,
            state_root,
            journal,
            preserve_maintenance=preserve,
        )


def _read_stdin_request() -> object:
    raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
    if not raw or len(raw) > MAX_PAYLOAD_BYTES:
        raise RuntimeError("Peer Meta transaction request size is invalid")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Peer Meta transaction request is invalid") from exc


def _write_stdout_response(payload: Mapping[str, object]) -> None:
    encoded = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise RuntimeError("Peer Meta transaction response is too large")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _execute_from_stdin() -> int:
    _write_stdout_response(_execute_request(_read_stdin_request()))
    return 0


def _resolved_addresses(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for family, _, _, _, sockaddr in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
        if family in {socket.AF_INET, socket.AF_INET6}:
            addresses.add(ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0]))
    return addresses


def _reject_self_peer(peer_host: str) -> None:
    try:
        peer_addresses = _resolved_addresses(peer_host)
    except socket.gaierror as exc:
        raise RuntimeError("HA peer host does not resolve") from exc
    if not peer_addresses or any(address.is_loopback or address.is_unspecified for address in peer_addresses):
        raise RuntimeError("HA peer resolves to the local node")
    local_addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = {
        ipaddress.ip_address("127.0.0.1"),
        ipaddress.ip_address("::1"),
    }
    try:
        local_addresses.update(_resolved_addresses(socket.gethostname()))
    except socket.gaierror:
        pass
    try:
        raw_local = subprocess.check_output(
            ["hostname", "-I"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        local_addresses.update(ipaddress.ip_address(item.split("%", 1)[0]) for item in raw_local.split())
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    if peer_addresses & local_addresses:
        raise RuntimeError("HA peer resolves to the local node")


def _peer_command(peer_host: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "StrictHostKeyChecking=yes",
        f"root@{peer_host}",
        str(REPO_DIR / "venv/bin/python"),
        "-I",
        str(REPO_DIR / "scripts/ha/sync_meta_env_to_peer.py"),
        "--execute-stdin",
    ]


def _call_peer(peer_host: str, payload: Mapping[str, object]) -> dict[str, object]:
    encoded = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise RuntimeError("Peer Meta transaction request is too large")
    result = subprocess.run(
        _peer_command(peer_host),
        input=encoded,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=PEER_TIMEOUT_SECONDS,
    )
    if result.returncode != 0 or not result.stdout or len(result.stdout) > MAX_PAYLOAD_BYTES:
        raise RuntimeError("Peer Meta transaction transport failed")
    try:
        response: Any = json.loads(result.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Peer Meta transaction response is invalid") from exc
    required = {"schema", "tx_id", "status", "fingerprint", "journal_present", "backup_present"}
    expected_tx_id = str(payload.get("tx_id") or "")
    if (
        not isinstance(response, dict)
        or set(response) != required
        or response.get("schema") != PROTOCOL_SCHEMA
        or response.get("status")
        not in {
            "absent",
            "quiesced",
            "prepared",
            "commit_requested",
            "committed",
            "rolled_back",
            "parity_proven",
            "finalized",
        }
        or not isinstance(response.get("tx_id"), str)
        or not isinstance(response.get("fingerprint"), str)
        or not FINGERPRINT_RE.fullmatch(response["fingerprint"])
        or not isinstance(response.get("journal_present"), bool)
        or not isinstance(response.get("backup_present"), bool)
    ):
        raise RuntimeError("Peer Meta transaction response contract is invalid")
    status = str(response["status"])
    response_tx_id = str(response["tx_id"])
    if status == "absent":
        consistent = response_tx_id == "" and response["journal_present"] is False
    elif status == "quiesced":
        consistent = response_tx_id == expected_tx_id and response["journal_present"] is False
    elif status == "finalized":
        consistent = (
            response_tx_id == expected_tx_id
            and response["journal_present"] is False
            and response["backup_present"] is False
        )
    else:
        consistent = (
            response_tx_id == expected_tx_id
            and response["journal_present"] is True
            and response["backup_present"] is True
        )
    if not consistent:
        raise RuntimeError("Peer Meta transaction response identity is invalid")
    return dict(response)


def _request_payload(
    *,
    action: str,
    expected_sha: str,
    tx_id: str,
    maintenance_active: bool,
    values: Mapping[str, str] | None = None,
    old_fingerprint: str | None = None,
    preserve_maintenance: bool | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": PROTOCOL_SCHEMA,
        "action": action,
        "expected_sha": expected_sha,
        "source_node_id": LOCAL_NODE_ID,
        "tx_id": tx_id,
        "maintenance_active": maintenance_active,
    }
    if values is not None:
        payload["meta_values"] = dict(values)
    if old_fingerprint is not None:
        payload["old_fingerprint"] = old_fingerprint
    if preserve_maintenance is not None:
        payload["preserve_maintenance"] = preserve_maintenance
    return payload


def _peer_phase(
    peer_host: str,
    *,
    action: str,
    journal: Mapping[str, object],
    values: Mapping[str, str] | None = None,
    preserve_maintenance: bool | None = None,
) -> dict[str, object]:
    return _call_peer(
        peer_host,
        _request_payload(
            action=action,
            expected_sha=str(journal["expected_sha"]),
            tx_id=str(journal["tx_id"]),
            maintenance_active=bool(journal["maintenance_active"]),
            values=values,
            old_fingerprint=str(journal["old_fingerprint"]) if action == "quiesce" else None,
            preserve_maintenance=preserve_maintenance,
        ),
    )


def _restore_local_journal(state_root: Path, journal: Mapping[str, object]) -> dict[str, object]:
    _ensure_workers_quiesced(state_root, journal, role="coordinator")
    backup = _backup_path(state_root)
    _restore_exact_backup(ENV_PATH, backup)
    _require_node_identity(ENV_PATH, LOCAL_NODE_ID)
    old_values = _read_meta_values(ENV_PATH)
    if _meta_fingerprint(old_values, str(journal["expected_sha"])) != journal["old_fingerprint"]:
        raise RuntimeError("Coordinator rollback backup fingerprint is invalid")
    _restart_api_and_verify(
        old_values,
        expected_node_id=LOCAL_NODE_ID,
        maintenance_active=bool(journal["maintenance_active"]),
    )
    _ensure_workers_quiesced(state_root, journal, role="coordinator")
    return _set_journal_status(state_root, journal, "rolled_back")


def _prove_committed_parity(
    peer_host: str,
    state_root: Path,
    journal: Mapping[str, object],
) -> dict[str, object]:
    values = _read_meta_values(ENV_PATH)
    if _meta_fingerprint(values, str(journal["expected_sha"])) != journal["new_fingerprint"]:
        raise RuntimeError("Coordinator committed Meta environment fingerprint is invalid")
    try:
        _verify_transition_runtime(
            values,
            expected_node_id=LOCAL_NODE_ID,
            state_root=state_root,
            journal=journal,
            role="coordinator",
        )
    except Exception:
        _ensure_workers_quiesced(state_root, journal, role="coordinator")
        _restart_api_and_verify(
            values,
            expected_node_id=LOCAL_NODE_ID,
            maintenance_active=bool(journal["maintenance_active"]),
        )
    response = _peer_phase(peer_host, action="prove", journal=journal)
    if response["status"] != "parity_proven" or response["fingerprint"] != journal["new_fingerprint"]:
        raise RuntimeError("Peer committed Meta parity proof failed")
    return _set_journal_status(state_root, journal, "parity_proven")


def _verify_local_terminal_runtime(state_root: Path, journal: Mapping[str, object]) -> None:
    status = str(journal["status"])
    if status not in {
        "parity_proven",
        "rolled_back",
        "finalizing_committed",
        "finalizing_rolled_back",
    }:
        raise RuntimeError("Coordinator Meta transaction has no terminal runtime to verify")
    expected = (
        journal["new_fingerprint"]
        if status in {"parity_proven", "finalizing_committed"}
        else journal["old_fingerprint"]
    )
    values = _read_meta_values(ENV_PATH)
    if _meta_fingerprint(values, str(journal["expected_sha"])) != expected:
        raise RuntimeError("Coordinator terminal Meta environment fingerprint is invalid")
    worker_state = _require_matching_worker_state(
        state_root,
        tx_id=str(journal["tx_id"]),
        role="coordinator",
        expected_sha=str(journal["expected_sha"]),
        old_fingerprint=str(journal["old_fingerprint"]),
    )
    if worker_state["status"] in {"restoring", "restored"}:
        _verify_worker_units_restored(worker_state, values, expected_node_id=LOCAL_NODE_ID)
        _verify_api_values(values, expected_node_id=LOCAL_NODE_ID)
    else:
        _verify_transition_runtime(
            values,
            expected_node_id=LOCAL_NODE_ID,
            state_root=state_root,
            journal=journal,
            role="coordinator",
        )


def _reconcile_coordinator(
    peer_host: str,
    state_root: Path,
    journal: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    response = _peer_phase(peer_host, action="query", journal=journal)
    peer_status = str(response["status"])
    local_status = str(journal["status"])
    if peer_status in {"committed", "parity_proven", "commit_requested"}:
        if local_status not in COMMIT_DECISION_STATUSES:
            raise RuntimeError("Peer committed without a durable coordinator commit decision")
        current = dict(journal)
        if peer_status == "commit_requested":
            response = _peer_phase(peer_host, action="commit", journal=current)
            peer_status = str(response["status"])
        if peer_status not in {"committed", "parity_proven"}:
            raise RuntimeError("Peer commit recovery did not reach a terminal state")
        current = _set_journal_status(state_root, current, "peer_committed")
        current = _prove_committed_parity(peer_host, state_root, current)
        return "committed", current
    if peer_status == "prepared" and local_status in COMMIT_DECISION_STATUSES:
        response = _peer_phase(peer_host, action="commit", journal=journal)
        if response["status"] not in {"committed", "parity_proven"}:
            if response["status"] == "rolled_back":
                if response["fingerprint"] != journal["old_fingerprint"]:
                    raise RuntimeError("Peer rollback fingerprint does not match the coordinator backup")
                restored = _restore_local_journal(state_root, journal)
                return "rolled_back", restored
            raise RuntimeError("Peer did not honor the durable commit decision")
        current = _set_journal_status(state_root, journal, "peer_committed")
        current = _prove_committed_parity(peer_host, state_root, current)
        return "committed", current
    if peer_status == "quiesced":
        if local_status in COMMIT_DECISION_STATUSES:
            raise RuntimeError("Peer has no durable prepare after the coordinator commit decision")
        response = _peer_phase(peer_host, action="rollback", journal=journal)
        peer_status = str(response["status"])
    if peer_status == "prepared":
        response = _peer_phase(peer_host, action="rollback", journal=journal)
        peer_status = str(response["status"])
    if peer_status in {"rolled_back", "finalized", "absent"} and response["fingerprint"] == journal["old_fingerprint"]:
        if local_status == "finalizing_rolled_back":
            _verify_local_terminal_runtime(state_root, journal)
            return "rolled_back", dict(journal)
        restored = _restore_local_journal(state_root, journal)
        return "rolled_back", restored
    if peer_status == "rolled_back":
        if response["fingerprint"] != journal["old_fingerprint"]:
            raise RuntimeError("Peer rollback fingerprint does not match the coordinator backup")
        raise RuntimeError("Peer rollback outcome is inconsistent")
    if (
        peer_status in {"absent", "finalized"}
        and response["fingerprint"] == journal["new_fingerprint"]
        and local_status in {"parity_proven", "finalizing_committed"}
    ):
        _verify_local_terminal_runtime(state_root, journal)
        return "committed", dict(journal)
    raise RuntimeError("Meta HA transaction outcome is uncertain; maintenance retained")


def _create_coordinator_transaction(
    *,
    expected_sha: str,
    local_prestage_backup: Path,
    maintenance_active: bool,
    state_root: Path,
) -> tuple[dict[str, object], dict[str, str]]:
    if _load_journal(state_root) is not None:
        raise RuntimeError("Existing Meta HA transaction requires recovery")
    if maintenance_active:
        _ensure_maintenance_armed(state_root)
    require_secure_env_file(local_prestage_backup)
    _require_node_identity(local_prestage_backup, LOCAL_NODE_ID)
    old_values = _read_meta_values(local_prestage_backup)
    if _read_runtime_meta_values(LOCAL_NODE_ID) != old_values:
        raise RuntimeError("Pre-stage backup does not match the live coordinator runtime")
    new_values = _read_meta_values(ENV_PATH)
    _require_node_identity(ENV_PATH, LOCAL_NODE_ID)
    old_fingerprint = _meta_fingerprint(old_values, expected_sha)
    authority, worker_state = _require_stage_authority(
        state_root,
        expected_sha=expected_sha,
        require_preimage=False,
    )
    if authority["old_fingerprint"] != old_fingerprint:
        raise RuntimeError("Meta HA stage authority does not match the supplied pre-stage backup")
    tx_id = str(worker_state["tx_id"])
    journal = _journal_payload(
        tx_id=tx_id,
        role="coordinator",
        status="coordinator_created",
        expected_sha=expected_sha,
        old_fingerprint=old_fingerprint,
        new_fingerprint=_meta_fingerprint(new_values, expected_sha),
        maintenance_active=maintenance_active,
    )
    _ensure_state_root(state_root)
    durable_backup = _backup_path(state_root)
    _authorize_registered_prestage_backup(local_prestage_backup, durable_backup)
    journal = _write_journal(state_root, journal)
    _durable_unlink(_stage_authority_path(state_root))
    _ensure_workers_quiesced(state_root, journal, role="coordinator")
    return journal, new_values


def _register_prestage_backup(
    *,
    expected_sha: str,
    peer_host: str,
    maintenance_active: bool,
    state_root: Path = STATE_ROOT,
) -> int:
    if not SHA_RE.fullmatch(expected_sha):
        raise RuntimeError("Authorized release SHA is invalid")
    if not HOST_RE.fullmatch(peer_host):
        raise RuntimeError("HA peer host is invalid")
    _verify_release(expected_sha)
    _refuse_conflicting_ha_transaction(state_root)
    _require_node_identity(ENV_PATH, LOCAL_NODE_ID)
    _reject_self_peer(peer_host)
    if not maintenance_active:
        raise RuntimeError("Pre-stage backup registration requires maintenance")
    _ensure_maintenance_armed(state_root)
    if _load_journal(state_root) is not None:
        raise RuntimeError("Existing Meta HA transaction state requires recovery")
    values = _read_meta_values(ENV_PATH)
    if _read_runtime_meta_values(LOCAL_NODE_ID) != values:
        raise RuntimeError("Canonical environment does not match the live pre-stage runtime")
    old_fingerprint = _meta_fingerprint(values, expected_sha)
    backup = _backup_path(state_root)
    if _entry_exists(backup):
        require_secure_env_file(backup)
        if backup.read_bytes() != ENV_PATH.read_bytes():
            raise RuntimeError("Existing Meta HA pre-stage backup requires recovery")
    else:
        _install_exact_backup(ENV_PATH, backup)
    existing_worker_state = _load_worker_state(state_root)
    tx_id = uuid.uuid4().hex if existing_worker_state is None else str(existing_worker_state["tx_id"])
    worker_state = _capture_and_quiesce_workers(
        state_root,
        tx_id=tx_id,
        role="coordinator",
        expected_sha=expected_sha,
        old_fingerprint=old_fingerprint,
    )
    response = _call_peer(
        peer_host,
        _request_payload(
            action="quiesce",
            expected_sha=expected_sha,
            tx_id=str(worker_state["tx_id"]),
            maintenance_active=True,
            old_fingerprint=old_fingerprint,
        ),
    )
    if response["status"] != "quiesced" or response["fingerprint"] != old_fingerprint:
        raise RuntimeError("Peer workers did not enter the durable pre-stage quiescence state")
    _verify_worker_units_quiesced()
    authority = _stage_authority_payload(
        tx_id=str(worker_state["tx_id"]),
        expected_sha=expected_sha,
        old_fingerprint=old_fingerprint,
        backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
        worker_state_sha256=_worker_state_digest(worker_state),
    )
    existing_authority = _load_stage_authority(state_root)
    if existing_authority is not None and existing_authority != authority:
        raise RuntimeError("Existing Meta HA pre-stage authority requires recovery")
    _write_stage_authority(state_root, authority)
    print(f"[meta-ha-env] tx_id={worker_state['tx_id']} prestage_workers_quiesced=true")
    return 0


def _send_to_peer(
    *,
    expected_sha: str,
    peer_host: str,
    maintenance_active: bool = False,
    local_prestage_backup: Path | None = None,
    state_root: Path = STATE_ROOT,
) -> int:
    if not SHA_RE.fullmatch(expected_sha):
        raise RuntimeError("Authorized release SHA is invalid")
    if not HOST_RE.fullmatch(peer_host):
        raise RuntimeError("HA peer host is invalid")
    if maintenance_active and local_prestage_backup is None:
        raise RuntimeError("Maintenance activation requires the exact local pre-stage backup")
    _verify_release(expected_sha)
    _refuse_conflicting_ha_transaction(state_root)
    _require_node_identity(ENV_PATH, LOCAL_NODE_ID)
    _reject_self_peer(peer_host)
    if local_prestage_backup is None:
        raise RuntimeError("Exact local pre-stage backup is required")
    journal, new_values = _create_coordinator_transaction(
        expected_sha=expected_sha,
        local_prestage_backup=local_prestage_backup,
        maintenance_active=maintenance_active,
        state_root=state_root,
    )
    try:
        _ensure_workers_quiesced(state_root, journal, role="coordinator")
        journal = _set_journal_status(state_root, journal, "peer_prepare_started")
        response = _peer_phase(peer_host, action="prepare", journal=journal, values=new_values)
        if response["status"] != "prepared" or response["fingerprint"] != journal["new_fingerprint"]:
            raise RuntimeError("Peer did not durably prepare the Meta environment")
        journal = _set_journal_status(state_root, journal, "peer_prepared")
        journal = _set_journal_status(state_root, journal, "local_activation_started")
        _ensure_workers_quiesced(state_root, journal, role="coordinator")
        _restart_api_and_verify(
            new_values,
            expected_node_id=LOCAL_NODE_ID,
            maintenance_active=maintenance_active,
        )
        _ensure_workers_quiesced(state_root, journal, role="coordinator")
        journal = _set_journal_status(state_root, journal, "local_active")
        journal = _set_journal_status(state_root, journal, "commit_requested")
        try:
            response = _peer_phase(peer_host, action="commit", journal=journal)
        except Exception:
            # The commit decision is durable.  Never guess rollback after a lost
            # final ACK; the journal query below decides the only safe outcome.
            response = _peer_phase(peer_host, action="query", journal=journal)
        if response["status"] == "rolled_back":
            if response["fingerprint"] != journal["old_fingerprint"]:
                raise RuntimeError("Peer rollback fingerprint does not match the coordinator backup")
            restored = _restore_local_journal(state_root, journal)
            raise RuntimeError(f"Peer commit failed and transaction {restored['tx_id']} rolled back")
        if response["status"] not in {"committed", "parity_proven", "commit_requested", "prepared"}:
            raise RuntimeError("Peer commit outcome is uncertain")
        outcome, journal = _reconcile_coordinator(peer_host, state_root, journal)
        if outcome != "committed" or journal["status"] != "parity_proven":
            raise RuntimeError("Meta HA parity proof did not commit")
        print(f"[meta-ha-env] tx_id={journal['tx_id']} parity_proven=true")
        return 0
    except BaseException as exc:
        latest = _load_journal(state_root) or journal
        try:
            outcome, _ = _reconcile_coordinator(peer_host, state_root, latest)
            if outcome == "committed":
                print(f"[meta-ha-env] tx_id={latest['tx_id']} recovered_commit=true")
                return 0
        except Exception:
            pass
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise RuntimeError("Meta HA transaction failed; durable maintenance state retained") from exc


def _cleanup_local_terminal(state_root: Path, journal: Mapping[str, object], *, preserve_maintenance: bool) -> None:
    status = str(journal["status"])
    if status not in {"parity_proven", "rolled_back", "finalizing_committed", "finalizing_rolled_back"}:
        raise RuntimeError("Coordinator Meta transaction is not safe to finalize")
    _verify_local_terminal_runtime(state_root, journal)
    finalizing = (
        "finalizing_committed" if status in {"parity_proven", "finalizing_committed"} else "finalizing_rolled_back"
    )
    updated = _set_journal_status(
        state_root,
        journal,
        finalizing,
        preserve_maintenance=preserve_maintenance,
    )
    terminal = updated["new_fingerprint"] if finalizing == "finalizing_committed" else updated["old_fingerprint"]
    values = _read_meta_values(ENV_PATH)
    if _meta_fingerprint(values, str(updated["expected_sha"])) != terminal:
        raise RuntimeError("Coordinator terminal Meta environment fingerprint is invalid")
    worker_state = _require_matching_worker_state(
        state_root,
        tx_id=str(updated["tx_id"]),
        role="coordinator",
        expected_sha=str(updated["expected_sha"]),
        old_fingerprint=str(updated["old_fingerprint"]),
    )
    _restore_worker_units(
        state_root,
        worker_state,
        terminal_fingerprint=str(terminal),
        expected_values=values,
        expected_node_id=LOCAL_NODE_ID,
    )
    _verify_runtime_values(values, expected_node_id=LOCAL_NODE_ID)
    _durable_unlink(_backup_path(state_root))
    if not preserve_maintenance:
        _clear_maintenance(state_root)
    _durable_unlink(_journal_path(state_root))
    _durable_unlink(_stage_authority_path(state_root))
    _durable_unlink(_worker_state_path(state_root))


def _recover_only(
    *,
    expected_sha: str,
    peer_host: str,
    maintenance_active: bool,
    state_root: Path = STATE_ROOT,
) -> int:
    _verify_release(expected_sha)
    _refuse_conflicting_ha_transaction(state_root)
    _require_node_identity(ENV_PATH, LOCAL_NODE_ID)
    _reject_self_peer(peer_host)
    journal = _load_journal(state_root)
    if journal is None:
        worker_state = _load_worker_state(state_root)
        stage_authority = _load_stage_authority(state_root)
        orphan = _backup_path(state_root)
        if worker_state is not None and worker_state["expected_sha"] != expected_sha:
            raise RuntimeError("Existing coordinator worker state cannot be recovered by this release")
        if worker_state is not None and worker_state["role"] != "coordinator":
            raise RuntimeError("Existing Meta HA worker state has the wrong role")
        if worker_state is not None and worker_state["status"] in {"restoring", "restored"}:
            values = _read_meta_values(ENV_PATH)
            terminal = str(worker_state["terminal_fingerprint"])
            if _meta_fingerprint(values, expected_sha) != terminal:
                raise RuntimeError("Coordinator orphaned worker terminal fingerprint is invalid")
            _restore_worker_units(
                state_root,
                worker_state,
                terminal_fingerprint=terminal,
                expected_values=values,
                expected_node_id=LOCAL_NODE_ID,
            )
            _verify_runtime_values(values, expected_node_id=LOCAL_NODE_ID)
            if _entry_exists(orphan):
                raise RuntimeError("Coordinator terminal cleanup order is invalid")
            _durable_unlink(_worker_state_path(state_root))
            _durable_unlink(_stage_authority_path(state_root))
            print("[meta-ha-env] recovered_worker_finalization=true")
            return 0
        if worker_state is not None:
            if not maintenance_active:
                raise RuntimeError("Pre-stage worker recovery requires maintenance")
            _ensure_maintenance_armed(state_root, restore_missing_persistent=True)
            if not _entry_exists(orphan):
                raise RuntimeError("Pre-stage worker recovery backup is absent")
            if stage_authority is not None:
                _require_stage_authority(
                    state_root,
                    expected_sha=expected_sha,
                    require_preimage=False,
                )
            require_secure_env_file(orphan)
            _require_node_identity(orphan, LOCAL_NODE_ID)
            old_values = _read_meta_values(orphan)
            old_fingerprint = _meta_fingerprint(old_values, expected_sha)
            if old_fingerprint != worker_state["old_fingerprint"]:
                raise RuntimeError("Pre-stage worker recovery backup fingerprint is invalid")
            _quiesce_worker_units()
            _restore_exact_backup(ENV_PATH, orphan)
            _restart_api_and_verify(
                old_values,
                expected_node_id=LOCAL_NODE_ID,
                maintenance_active=maintenance_active,
            )
            _quiesce_worker_units()
            response = _call_peer(
                peer_host,
                _request_payload(
                    action="rollback",
                    expected_sha=expected_sha,
                    tx_id=str(worker_state["tx_id"]),
                    maintenance_active=True,
                ),
            )
            if (
                response["status"] not in {"absent", "finalized"}
                or response["fingerprint"] != old_fingerprint
                or response["journal_present"] is not False
                or response["backup_present"] is not False
            ):
                raise RuntimeError("Peer pre-stage worker rollback was not proven")
            _restore_worker_units(
                state_root,
                worker_state,
                terminal_fingerprint=old_fingerprint,
                expected_values=old_values,
                expected_node_id=LOCAL_NODE_ID,
            )
            _verify_runtime_values(old_values, expected_node_id=LOCAL_NODE_ID)
            _durable_unlink(orphan)
            _durable_unlink(_worker_state_path(state_root))
            _durable_unlink(_stage_authority_path(state_root))
            print("[meta-ha-env] recovered_prestage_workers=true")
            return 0
        if _entry_exists(orphan):
            if stage_authority is not None:
                raise RuntimeError("Orphaned Meta HA stage authority has no worker inventory")
            require_secure_env_file(orphan)
            _require_node_identity(orphan, LOCAL_NODE_ID)
            if orphan.read_bytes() != ENV_PATH.read_bytes():
                raise RuntimeError("Orphaned Meta HA backup has an uncertain environment outcome")
            values = _read_meta_values(ENV_PATH)
            _verify_api_values(values, expected_node_id=LOCAL_NODE_ID)
            _durable_unlink(orphan)
            print("[meta-ha-env] recovered_pre_quiescence_backup=true")
            return 0
        print("[meta-ha-env] recovery_required=false")
        return 0
    if journal["role"] != "coordinator" or journal["expected_sha"] != expected_sha:
        raise RuntimeError("Existing coordinator Meta transaction cannot be recovered by this release")
    _require_durable_backup(state_root, journal)
    if journal["maintenance_active"] is not maintenance_active:
        raise RuntimeError("Coordinator recovery maintenance mode does not match the durable transaction")
    if maintenance_active:
        _ensure_maintenance_armed(state_root, restore_missing_persistent=True)
    outcome, journal = _reconcile_coordinator(peer_host, state_root, journal)
    try:
        response = _peer_phase(
            peer_host,
            action="finalize",
            journal=journal,
            preserve_maintenance=True,
        )
    except Exception:
        response = _peer_phase(peer_host, action="query", journal=journal)
    expected_terminal = journal["new_fingerprint"] if outcome == "committed" else journal["old_fingerprint"]
    if (
        response["status"] not in {"finalized", "absent"}
        or response["fingerprint"] != expected_terminal
        or response["backup_present"] is not False
    ):
        raise RuntimeError("Recovered peer Meta transaction did not finalize")
    _cleanup_local_terminal(state_root, journal, preserve_maintenance=True)
    print(f"[meta-ha-env] recovered_outcome={outcome}")
    return 0


def _finalize_transaction(
    *,
    expected_sha: str,
    peer_host: str,
    state_root: Path = STATE_ROOT,
) -> int:
    _verify_release(expected_sha)
    _refuse_conflicting_ha_transaction(state_root)
    _require_node_identity(ENV_PATH, LOCAL_NODE_ID)
    _reject_self_peer(peer_host)
    journal = _load_journal(state_root)
    if journal is None:
        raise RuntimeError("Coordinator Meta transaction journal is absent")
    if journal["role"] != "coordinator" or journal["expected_sha"] != expected_sha:
        raise RuntimeError("Coordinator Meta transaction journal does not match finalization")
    _require_durable_backup(state_root, journal)
    if journal["maintenance_active"]:
        _ensure_maintenance_armed(state_root, restore_missing_persistent=True)
    if journal["status"] == "parity_proven":
        journal = _prove_committed_parity(peer_host, state_root, journal)
    if journal["status"] not in {
        "parity_proven",
        "rolled_back",
        "finalizing_committed",
        "finalizing_rolled_back",
    }:
        raise RuntimeError("Coordinator Meta transaction has no proven terminal state")
    try:
        response = _peer_phase(
            peer_host,
            action="finalize",
            journal=journal,
            preserve_maintenance=False,
        )
    except Exception:
        response = _peer_phase(peer_host, action="query", journal=journal)
    expected_terminal = (
        journal["new_fingerprint"]
        if journal["status"] in {"parity_proven", "finalizing_committed"}
        else journal["old_fingerprint"]
    )
    if (
        response["status"] not in {"finalized", "absent"}
        or response["fingerprint"] != expected_terminal
        or response["backup_present"] is not False
    ):
        raise RuntimeError("Peer Meta transaction finalization failed")
    _cleanup_local_terminal(state_root, journal, preserve_maintenance=False)
    print("[meta-ha-env] finalized=true")
    return 0


def _require_coordinator_mutation_lock() -> int:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise RuntimeError("Meta HA coordinator mutation requires root")
    raw_fd = os.environ.get("LINAS_PRODUCTION_MUTATION_LOCK_FD", "")
    if not raw_fd.isdigit():
        raise RuntimeError("Inherited common Meta mutation lock is absent")
    descriptor = int(raw_fd)
    _require_inherited_lock(descriptor, LOCK_PATH)
    return descriptor


def _verify_stage_authority_command(
    *,
    expected_sha: str,
    state_root: Path = STATE_ROOT,
) -> int:
    _verify_release(expected_sha)
    _refuse_conflicting_ha_transaction(state_root)
    _require_node_identity(ENV_PATH, LOCAL_NODE_ID)
    if _load_journal(state_root) is not None:
        raise RuntimeError("Meta HA environment staging has already been consumed")
    _ensure_maintenance_armed(state_root)
    authority, _ = _require_stage_authority(
        state_root,
        expected_sha=expected_sha,
        require_preimage=True,
    )
    backup_values = _read_meta_values(_backup_path(state_root))
    if _read_runtime_meta_values(LOCAL_NODE_ID) != backup_values:
        raise RuntimeError("Live coordinator runtime changed after pre-stage authorization")
    print(f"[meta-ha-env] tx_id={authority['tx_id']} stage_authority_verified=true")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--peer-host", default=os.getenv("LINAS_HA_PEER_HOST", "10.106.0.4"))
    parser.add_argument("--execute-stdin", action="store_true")
    parser.add_argument("--maintenance-active", action="store_true")
    parser.add_argument("--local-prestage-backup", default="")
    parser.add_argument("--recover-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--register-prestage-backup", action="store_true")
    parser.add_argument("--verify-stage-authority", action="store_true")
    args = parser.parse_args()
    if args.execute_stdin:
        if any(
            (
                args.expected_sha,
                args.maintenance_active,
                args.local_prestage_backup,
                args.recover_only,
                args.finalize,
                args.register_prestage_backup,
                args.verify_stage_authority,
            )
        ):
            raise RuntimeError("Remote execution accepts transaction state only through stdin")
        return _execute_from_stdin()
    selected_modes = sum(
        bool(value)
        for value in (
            args.recover_only,
            args.finalize,
            args.register_prestage_backup,
            args.verify_stage_authority,
        )
    )
    if selected_modes > 1:
        raise RuntimeError("Recovery, registration, and finalization modes are mutually exclusive")
    expected_sha = str(args.expected_sha)
    peer_host = str(args.peer_host)
    _require_coordinator_mutation_lock()
    if args.recover_only:
        return _recover_only(
            expected_sha=expected_sha,
            peer_host=peer_host,
            maintenance_active=bool(args.maintenance_active),
        )
    if args.register_prestage_backup:
        if args.local_prestage_backup:
            raise RuntimeError("Pre-stage registration does not accept an external backup")
        return _register_prestage_backup(
            expected_sha=str(args.expected_sha),
            peer_host=str(args.peer_host),
            maintenance_active=bool(args.maintenance_active),
        )
    if args.verify_stage_authority:
        if args.local_prestage_backup or args.maintenance_active:
            raise RuntimeError("Stage authority verification accepts no mutation options")
        return _verify_stage_authority_command(expected_sha=str(args.expected_sha))
    if args.finalize:
        if args.local_prestage_backup:
            raise RuntimeError("Finalization does not accept a pre-stage backup")
        return _finalize_transaction(expected_sha=expected_sha, peer_host=peer_host)
    backup = Path(str(args.local_prestage_backup)) if args.local_prestage_backup else None
    return _send_to_peer(
        expected_sha=expected_sha,
        peer_host=peer_host,
        maintenance_active=bool(args.maintenance_active),
        local_prestage_backup=backup,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        detail = str(exc).strip()
        if isinstance(exc, OSError) and not detail:
            detail = f"errno={exc.errno} {exc.strerror or 'unknown'} path={exc.filename or '-'}"
        if detail:
            print(f"[meta-ha-env] failed={type(exc).__name__}: {detail}", file=sys.stderr)
        else:
            print(f"[meta-ha-env] failed={type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
