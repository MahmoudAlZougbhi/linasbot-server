#!/usr/bin/env python3
"""One-time, confirmation-gated bootstrap of the two-node Meta HA contract.

Normal deploy and environment-sync paths intentionally refuse the live drift
this tool repairs.  This transaction verifies the fixed topology and exact
per-node Git baselines, binds the owner's exact local DigitalOcean /api/ready
attestation and proves the shared writable PostgreSQL authority, archives every historical .env* file,
sets the nonsecret HA contract atomically, and retires (without deleting) the
node01 legacy service.  Any failed or uncertain operation keeps both nodes
stopped behind persistent maintenance until exact rollback is proved.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_nested_spec = importlib.util.spec_from_file_location(
    "bootstrap_nested_runtime_quarantine",
    Path(__file__).with_name("bootstrap_nested_runtime_quarantine.py"),
)
if _nested_spec is None or _nested_spec.loader is None:
    raise RuntimeError("nested runtime quarantine module is missing")
_nested = importlib.util.module_from_spec(_nested_spec)
_nested_spec.loader.exec_module(_nested)
_nested_evidence_spec = importlib.util.spec_from_file_location(
    "bootstrap_nested_runtime_evidence",
    Path(__file__).with_name("bootstrap_nested_runtime_evidence.py"),
)
if _nested_evidence_spec is None or _nested_evidence_spec.loader is None:
    raise RuntimeError("nested runtime evidence module is missing")
_nested_evidence = importlib.util.module_from_spec(_nested_evidence_spec)
_nested_evidence_spec.loader.exec_module(_nested_evidence)
_lb_contract_spec = importlib.util.spec_from_file_location(
    "do_lb_ready_contract",
    Path(__file__).with_name("do_lb_ready_contract.py"),
)
if _lb_contract_spec is None or _lb_contract_spec.loader is None:
    raise RuntimeError("DigitalOcean ready contract module is missing")
_lb_contract = importlib.util.module_from_spec(_lb_contract_spec)
_lb_contract_spec.loader.exec_module(_lb_contract)

REPO_DIR = Path("/opt/linasbot")
ENV_PATH = REPO_DIR / ".env"
STATE_ROOT = Path("/var/lib/linasbot/meta-ha")
ACTIVE_PATH = STATE_ROOT / "bootstrap.active"
COMMITTED_PROOF_PATH = STATE_ROOT / "bootstrap.last-committed.json"
COORDINATOR_PATH = STATE_ROOT / "bootstrap.coordinator.json"
SYNC_JOURNAL = STATE_ROOT / "transaction.json"
SYNC_BACKUP = STATE_ROOT / "env.before"
DEPLOY_ACTIVE = STATE_ROOT / "deploy.active"
DEPLOY_NODE_ACTIVE = STATE_ROOT / "deploy-node.active"
PYTHON_RUNTIME_PROVISION_ACTIVE = STATE_ROOT / "python-runtime-provision.active"
PYTHON_RUNTIME_PROVISION_COORDINATOR = STATE_ROOT / "python-runtime-provision.coordinator.json"
PYTHON_RUNTIME_LOCAL_RECEIPT = STATE_ROOT / "python-runtime-provisioned.json"
PYTHON_RUNTIME_CLUSTER_RECEIPT = STATE_ROOT / "python-runtime-cluster.json"
PYTHON_RUNTIME_TRANSACTIONS = STATE_ROOT / "python-runtime-transactions"
PYTHON_RUNTIME_LAUNCHER_RECEIPTS = STATE_ROOT / "python-runtime-provision-launchers"
PYTHON_RUNTIME_ROOT = Path("/opt/linasbot-runtime/cpython-3.13.15")
SYSTEM_PYTHON = PYTHON_RUNTIME_ROOT / "bin/python3.13"
PYTHON_RUNTIME_ARTIFACT_NAME = "cpython-3.13.15+20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
RUNTIME_RELEASE_BUNDLE_FILES = frozenset(
    {
        "release-manifest.json",
        "wheelhouse.tar",
        "dashboard-build.tar",
        "control-plane.tar",
        "source.bundle",
        PYTHON_RUNTIME_ARTIFACT_NAME,
    }
)
CONTROLLED_FAILOVER_ACTIVE = STATE_ROOT / "controlled-failover.active"
REGISTRY_NFS_RETIRE_ACTIVE = STATE_ROOT / "registry-nfs-retire.active"
LB_BOOTSTRAP_ATTESTATION_PATH = STATE_ROOT / "lb-ready-bootstrap-attestation.json"
PERSISTENT_MARKER = STATE_ROOT / "maintenance"
VOLATILE_MARKER = Path("/run/linasbot-maintenance")
LOCK_PATH = Path("/run/lock/linasbot-meta-live.lock")
HELPER_REPO_PATH = "scripts/ha/bootstrap_meta_ha_contract.py"
LEGACY_UNIT = Path("/etc/systemd/system/linas_ai_bot.service")
LEGACY_RETIREMENT_MARKER = STATE_ROOT / "legacy-linas-ai-bot-retired"
LEGACY_RETIREMENT_GUARD = Path("/etc/systemd/system/linas_ai_bot.service.d/90-linasbot-retired.conf")
LEGACY_RETIREMENT_GUARD_BYTES = (
    b"[Unit]\n"
    b"# Exact persistent retirement guard for the legacy :8000 runtime.\n"
    b"ConditionPathExists=!/var/lib/linasbot/meta-ha/bootstrap.active\n"
    b"ConditionPathExists=!/var/lib/linasbot/meta-ha/legacy-linas-ai-bot-retired\n"
)
API_UNIT = "linasbot.service"
API_UNIT_PATH = Path("/etc/systemd/system/linasbot.service")
WORKER_TEMPLATE_PATH = Path("/etc/systemd/system/linasbot-worker@.service")
WORKER_UNITS = tuple(
    f"linasbot-worker@{queue}.service" for queue in ("high_priority", "interactive", "background", "expensive")
)
NGINX_CONFIG = Path("/etc/nginx/sites-available/linasaibot")
BOOT_GUARDS = (
    Path("/etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf"),
    Path("/etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf"),
)
BOOT_GUARD = (
    b"[Unit]\n"
    b"# Exact one-time Meta HA bootstrap boot guard.\n"
    b"ConditionPathExists=!/var/lib/linasbot/meta-ha/bootstrap.runtime.guard\n"
)
CONTROLLED_FAILOVER_RUNTIME_GUARD = STATE_ROOT / "controlled-failover.runtime.guard"
BOOTSTRAP_RUNTIME_GUARD = STATE_ROOT / "bootstrap.runtime.guard"
CONTROLLED_FAILOVER_GUARDS = (
    Path("/etc/systemd/system/linasbot.service.d/92-meta-controlled-failover.conf"),
    Path("/etc/systemd/system/linasbot-worker@.service.d/92-meta-controlled-failover.conf"),
)
CONTROLLED_FAILOVER_GUARD = (
    b"[Unit]\n"
    b"# Permanently installed controlled Meta failover reboot guard.\n"
    b"ConditionPathExists=!/var/lib/linasbot/meta-ha/controlled-failover.runtime.guard\n"
)
BOOTSTRAP_RUNTIME_GUARD_BYTES = b"linasbot-meta-ha-bootstrap-runtime-guard-v1\n"
LB_ID = "2535b8ff-b89c-442b-b5bf-91eae51ed3f6"
LB_NAME = "linas-http-lb-lon1"
LB_IP = "157.245.31.104"
LB_DROPLETS = [510629908, 591901417]
LB_READY_ATTESTATION_SCHEMA = 2
LB_PROJECT_ID = "70160077-6e21-4fc7-9c81-45e6b60d8919"
LB_READY_PROJECTION_KEYS = _lb_contract.LB_READY_PROJECTION_KEYS
LB_HEALTH_CONTRACT = _lb_contract.LB_HEALTH_CONTRACT_READY
CONTRACT_KEYS = {
    "META_DELETION_REQUIRED_NODES": "node01,node02",
    "META_REGISTRY_BACKEND": "postgres",
    "META_HA_LB_READY_HEALTHCHECK_APPROVED": "true",
    "META_HA_LB_DRAIN_SECONDS": "30",
    "LINAS_MAINTENANCE_DRAIN_FILE": str(PERSISTENT_MARKER),
}
FORBIDDEN_EXECUTION_ENV_KEYS = frozenset(
    {
        "BASHOPTS",
        "BASH_ENV",
        "CDPATH",
        "ENV",
        "GCONV_PATH",
        "GLOBIGNORE",
        "GLIBC_TUNABLES",
        "HOSTALIASES",
        "IFS",
        "JAVA_TOOL_OPTIONS",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "LOCPATH",
        "NODE_OPTIONS",
        "NODE_PATH",
        "OPENSSL_CONF",
        "OPENSSL_MODULES",
        "PATH",
        "PERL5LIB",
        "PERL5OPT",
        "PROMPT_COMMAND",
        "PYTHONBREAKPOINT",
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "PYTHONWARNINGS",
        "RUBYLIB",
        "RUBYOPT",
        "SHELLOPTS",
        "SSLKEYLOGFILE",
        "TZDIR",
        "_JAVA_OPTIONS",
    }
)
FORBIDDEN_EXECUTION_ENV_PREFIXES = (
    "BASH_FUNC_",
    "DYLD_",
    "GIT_",
    "LD_",
    "LINAS_DEPLOY_MUTATION_",
    "LINAS_PRODUCTION_MUTATION_",
)
FIXED_NODES = {
    "node01": {
        "hostname": "ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01",
        "public_ip": "139.59.167.62",
        "private_ip": "10.106.0.3",
        "peer_ip": "10.106.0.4",
    },
    "node02": {
        "hostname": "linas-app-lon1-02",
        "public_ip": "167.99.89.243",
        "private_ip": "10.106.0.4",
        "peer_ip": "10.106.0.3",
    },
}
SSH_OPTIONS = (
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
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
TX_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_ENV_BYTES = 1024 * 1024
MAX_AUTHORITY_BYTES = 1024 * 1024
MAX_CONTROL_ARCHIVE_BYTES = 1024**3
MAX_RELEASE_PAYLOAD_BYTES = 4 * 1024**3
MAX_PYTHON_RUNTIME_ARCHIVE_BYTES = 256 * 1024**2
MAX_WHEELHOUSE_BYTES = 4 * 1024**3
MAX_GIT_METADATA_BYTES = 128 * 1024**2
RUNTIME_TX_RE = re.compile(r"^pyr_[0-9a-f]{32}$")
RELEASE_TREE_DOMAIN = b"linasbot-release-tree-v1\0"
RUNTIME_NODE_RECEIPT_KEYS = {
    "schema",
    "format",
    "transaction_id",
    "decision",
    "status",
    "node_id",
    "required_nodes",
    "runtime_path",
    "python_executable",
    "python_version",
    "implementation",
    "cache_tag",
    "soabi",
    "platform_system",
    "machine",
    "pip_version",
    "artifact_repository",
    "artifact_release",
    "artifact_name",
    "artifact_sha256",
    "cpython_source_sha256",
    "runtime_tree_sha256",
    "python_executable_sha256",
    "wheelhouse_archive_sha256",
    "wheelhouse_tree_sha256",
    "wheelhouse_file_count",
    "wheelhouse_total_size",
    "plan_sha256",
    "qg_repository",
    "qg_workflow_ref",
    "qg_run_id",
    "qg_run_attempt",
    "qg_target_sha",
    "qg_artifact_id",
    "qg_artifact_api_sha256",
    "qg_manifest_sha256",
}
RUNTIME_CLUSTER_RECEIPT_KEYS = (RUNTIME_NODE_RECEIPT_KEYS - {"node_id", "python_executable_sha256"}) | {
    "node_receipt_sha256"
}
RUNTIME_LAUNCHER_RECEIPT_KEYS = {
    "schema",
    "format",
    "artifact_id",
    "artifact_api_sha256",
    "manifest_sha256",
    "run_id",
    "run_attempt",
    "target_sha",
    "bundle_root",
    "control_root",
    "control_plane_archive_sha256",
    "control_plane_tree_sha256",
    "launcher_path",
    "launcher_sha256",
    "launcher_size",
}
RUNTIME_CONTROL_FILES = {
    "deploy/systemd/linasbot-worker@.service",
    "deploy/systemd/linasbot.service",
    "requirements.lock",
    "scripts/ha/bootstrap_meta_ha_contract.py",
    "scripts/ha/bootstrap_nested_runtime_quarantine.py",
    "scripts/ha/bootstrap_nested_runtime_evidence.py",
    "scripts/ha/do_lb_ready_contract.py",
    "scripts/ha/python_runtime_archive_contract.py",
    "scripts/ha/python_runtime_provision_contract.py",
    "scripts/ha/python_runtime_provision_ingest_contract.py",
    "scripts/ha/release_archive_contract.py",
    "scripts/ha/release_artifact_contract.py",
}
ROTATION_WARNING = (
    "CREDENTIAL ROTATION REQUIRED: historical .env backups were group/world-readable; "
    "rotate every credential that may have appeared in them."
)


def _log(message: str) -> None:
    print(f"[meta-ha-bootstrap] {message}")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _digest_bytes(_canonical(value))


def _require_root() -> None:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise PermissionError("Meta HA bootstrap must run as root")


def _local_node_id() -> str:
    hostname = os.uname().nodename
    for node_id, identity in FIXED_NODES.items():
        if hostname == identity["hostname"]:
            return node_id
    raise RuntimeError("bootstrap host is outside the fixed two-node identity")


def _assert_authenticated_entry(node_id: str) -> dict[str, Any]:
    if (
        Path(sys.executable).resolve() != SYSTEM_PYTHON
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or any(name.startswith(("PYTHON", "GIT_")) for name in os.environ)
    ):
        raise RuntimeError("bootstrap must enter through the OS-authenticated runtime launcher with -B -I -S")
    return _runtime_authority(node_id)


@contextmanager
def _exclusive_lock() -> Iterator[None]:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(LOCK_PATH, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("Meta HA transaction lock is not root-owned and private")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _run(args: list[str], *, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if check and result.returncode:
        raise RuntimeError(f"required command failed: {args[0]} {args[1] if len(args) > 1 else ''}".strip())
    return result


def _validate_sha(value: str, label: str) -> str:
    if not SHA_RE.fullmatch(value or ""):
        raise ValueError(f"{label} is not an exact 40-character SHA")
    return value


def _validate_digest(value: str, label: str) -> str:
    if not DIGEST_RE.fullmatch(value or ""):
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _secure_dir(path: Path, *, create: bool = False, mode: int = 0o700) -> None:
    if create:
        path.mkdir(parents=True, mode=mode, exist_ok=True)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != mode
    ):
        raise PermissionError(f"unsafe root state directory: {path}")


def _repair_no_replace_publication(
    path: Path,
    info: os.stat_result,
    *,
    expected_uid: int,
    expected_gid: int,
    mode: int,
) -> os.stat_result:
    """Finish the sole safe interrupted hard-link publication state.

    ``_atomic_write(..., no_replace=True)`` publishes by linking a fully
    synced private temporary file to its final name.  Power loss after the
    link but before temporary-name removal leaves two names for the same
    inode.  That state is authenticated by the exact generated-name prefix,
    inode identity, link count, owner and mode; removing only that second name
    makes the publication replayable without weakening normal authority reads.
    """

    if info.st_nlink == 1:
        return info
    if (
        info.st_nlink != 2
        or not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != mode
    ):
        return info
    prefix = f".{path.name}.bootstrap."
    aliases: list[Path] = []
    with os.scandir(path.parent) as entries:
        for entry in entries:
            if not entry.name.startswith(prefix):
                continue
            candidate = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(candidate.st_mode):
                continue
            if (candidate.st_dev, candidate.st_ino) == (info.st_dev, info.st_ino):
                aliases.append(path.parent / entry.name)
    if len(aliases) != 1:
        return info
    aliases[0].unlink()
    _fsync_dir(path.parent)
    repaired = path.lstat()
    if (repaired.st_dev, repaired.st_ino) != (info.st_dev, info.st_ino) or repaired.st_nlink != 1:
        raise RuntimeError(f"bootstrap authority publication could not be reconciled: {path}")
    return repaired


def _secure_regular(path: Path, *, mode: int = 0o600) -> os.stat_result:
    info = path.lstat()
    info = _repair_no_replace_publication(
        path,
        info,
        expected_uid=0,
        expected_gid=0,
        mode=mode,
    )
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_nlink != 1
    ):
        raise PermissionError(f"unsafe root state file: {path}")
    return info


def _read_regular_any_owner(path: Path) -> tuple[bytes, os.stat_result]:
    before = path.lstat()
    before = _repair_no_replace_publication(
        path,
        before,
        expected_uid=before.st_uid,
        expected_gid=before.st_gid,
        mode=stat.S_IMODE(before.st_mode),
    )
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > MAX_ENV_BYTES
    ):
        raise PermissionError(f"unsafe or oversized file: {path}")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"file changed while opening: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
            if sum(map(len, chunks)) > MAX_ENV_BYTES:
                raise RuntimeError("environment file exceeds the safety limit")
        return b"".join(chunks), opened
    finally:
        os.close(fd)


def _read_authority_file(
    path: Path,
    *,
    limit: int = MAX_AUTHORITY_BYTES,
    expected_uid: int = 0,
    expected_gid: int = 0,
    mode: int = 0o600,
) -> bytes:
    """Read one immutable root authority without following or racing a path."""

    before = path.lstat()
    before = _repair_no_replace_publication(
        path,
        before,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        mode=mode,
    )
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_nlink != 1
        or not 1 <= before.st_size <= limit
    ):
        raise PermissionError(f"unsafe bootstrap authority file: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"bootstrap authority changed while opening: {path}")
        chunks: list[bytes] = []
        consumed = 0
        while consumed < opened.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - consumed))
            if not chunk:
                raise RuntimeError(f"bootstrap authority is truncated: {path}")
            chunks.append(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(opened, key) != getattr(after, key) for key in identity):
        raise RuntimeError(f"bootstrap authority changed while reading: {path}")
    return b"".join(chunks)


def _authority_file_evidence(
    path: Path,
    *,
    limit: int,
    expected_uid: int = 0,
    expected_gid: int = 0,
    mode: int = 0o600,
) -> tuple[str, int]:
    before = path.lstat()
    before = _repair_no_replace_publication(
        path,
        before,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        mode=mode,
    )
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_nlink != 1
        or not 1 <= before.st_size <= limit
    ):
        raise PermissionError(f"unsafe bootstrap authority file: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"bootstrap authority changed while opening: {path}")
        consumed = 0
        while consumed < opened.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - consumed))
            if not chunk:
                raise RuntimeError(f"bootstrap authority is truncated: {path}")
            digest.update(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(opened, key) != getattr(after, key) for key in identity):
        raise RuntimeError(f"bootstrap authority changed while hashing: {path}")
    return digest.hexdigest(), opened.st_size


def _read_authority_json(
    path: Path,
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> tuple[dict[str, Any], bytes]:
    raw = _read_authority_file(path, expected_uid=expected_uid, expected_gid=expected_gid)
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"bootstrap authority is invalid JSON: {path}") from exc
    if not isinstance(payload, dict) or raw != _canonical(payload) + b"\n":
        raise RuntimeError(f"bootstrap authority is not canonical JSON: {path}")
    return payload, raw


def _secure_authority_dir(
    path: Path,
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
    mode: int = 0o700,
) -> None:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != mode
    ):
        raise PermissionError(f"unsafe bootstrap authority directory: {path}")


def _release_tree_evidence(
    root: Path,
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> tuple[str, int, int, frozenset[str]]:
    """Recompute the QG normalized tree before importing any control module."""

    _secure_authority_dir(
        root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    inventory: list[tuple[str, Path, os.stat_result]] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if (
            not relative
            or relative.startswith("/")
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or any(ord(character) < 32 or ord(character) == 127 for character in relative)
        ):
            raise RuntimeError("authenticated control tree contains an unsafe path")
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
        ):
            raise PermissionError("authenticated control tree contains an unsafe object")
        if stat.S_ISDIR(info.st_mode):
            if stat.S_IMODE(info.st_mode) != 0o755:
                raise PermissionError("authenticated control tree directory mode is unsafe")
        elif stat.S_IMODE(info.st_mode) not in {0o644, 0o755} or info.st_nlink != 1:
            raise PermissionError("authenticated control tree file mode is unsafe")
        inventory.append((relative, path, info))
        if len(inventory) > 100_000:
            raise RuntimeError("authenticated control tree is too large")
    if not inventory:
        raise RuntimeError("authenticated control tree is empty")
    digest = hashlib.sha256(RELEASE_TREE_DOMAIN)
    file_count = 0
    total_size = 0
    names: set[str] = set()
    for relative, path, info in sorted(inventory, key=lambda item: item[0].encode("utf-8")):
        names.add(relative)
        if stat.S_ISDIR(info.st_mode):
            record: list[Any] = ["dir", relative, 0o755, 0, None]
        else:
            raw = _read_authority_file(
                path,
                limit=8 * 1024**2,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                mode=stat.S_IMODE(info.st_mode),
            )
            record = [
                "file",
                relative,
                0o755 if stat.S_IMODE(info.st_mode) & 0o111 else 0o644,
                len(raw),
                _digest_bytes(raw),
            ]
            file_count += 1
            total_size += len(raw)
        digest.update(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest(), file_count, total_size, frozenset(names)


def _runtime_authority(
    node_id: str,
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> dict[str, Any]:
    """Authenticate the retained provision transaction before any live probe."""

    if node_id not in FIXED_NODES:
        raise RuntimeError("runtime authority node identity is invalid")
    for directory, mode in (
        (STATE_ROOT, 0o700),
        (PYTHON_RUNTIME_TRANSACTIONS, 0o700),
        (PYTHON_RUNTIME_LAUNCHER_RECEIPTS, 0o700),
    ):
        _secure_authority_dir(
            directory,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            mode=mode,
        )
    local, local_raw = _read_authority_json(
        PYTHON_RUNTIME_LOCAL_RECEIPT,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    cluster, cluster_raw = _read_authority_json(
        PYTHON_RUNTIME_CLUSTER_RECEIPT,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if (
        set(local) != RUNTIME_NODE_RECEIPT_KEYS
        or set(cluster) != RUNTIME_CLUSTER_RECEIPT_KEYS
        or local.get("schema") != 2
        or cluster.get("schema") != 2
        or local.get("format") != "linas-python-runtime-node-v2"
        or cluster.get("format") != "linas-python-runtime-cluster-v2"
        or local.get("node_id") != node_id
    ):
        raise RuntimeError("committed Python runtime receipt schema is invalid")
    transaction_id = str(local.get("transaction_id") or "")
    if RUNTIME_TX_RE.fullmatch(transaction_id) is None or cluster.get("transaction_id") != transaction_id:
        raise RuntimeError("committed Python runtime transaction identity is invalid")
    common = RUNTIME_NODE_RECEIPT_KEYS - {
        "format",
        "node_id",
        "python_executable_sha256",
    }
    if any(local.get(key) != cluster.get(key) for key in common):
        raise RuntimeError("node and cluster Python runtime receipts differ")
    if (
        local.get("decision") != "commit"
        or local.get("status") != "committed"
        or local.get("required_nodes") != ["node01", "node02"]
        or local.get("runtime_path") != str(PYTHON_RUNTIME_ROOT)
        or local.get("python_executable") != str(SYSTEM_PYTHON)
    ):
        raise RuntimeError("committed Python runtime receipt state is invalid")
    node_map = cluster.get("node_receipt_sha256")
    if (
        not isinstance(node_map, dict)
        or set(node_map) != set(FIXED_NODES)
        or node_map.get(node_id) != _digest_bytes(local_raw)
        or any(DIGEST_RE.fullmatch(str(value)) is None for value in node_map.values())
    ):
        raise RuntimeError("cluster Python runtime receipt map is invalid")
    plan_sha = _validate_digest(str(local.get("plan_sha256") or ""), "Python runtime provision plan")
    tx_root = PYTHON_RUNTIME_TRANSACTIONS / transaction_id
    authority_root = tx_root / "authority"
    control_root = tx_root / "control"
    for directory in (tx_root, authority_root, control_root):
        _secure_authority_dir(
            directory,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    if {entry.name for entry in os.scandir(authority_root)} != {
        "plan.json",
        *RUNTIME_RELEASE_BUNDLE_FILES,
    }:
        raise RuntimeError("retained Python runtime authority file set is not exact")
    plan, plan_raw = _read_authority_json(
        authority_root / "plan.json",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    manifest, manifest_raw = _read_authority_json(
        authority_root / "release-manifest.json",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if _digest_bytes(plan_raw) != plan_sha or plan.get("transaction_id") != transaction_id:
        raise RuntimeError("retained Python runtime plan differs from its receipt")
    if _digest_bytes(manifest_raw) != local.get("qg_manifest_sha256"):
        raise RuntimeError("retained QG manifest differs from the runtime receipt")
    artifact_id = local.get("qg_artifact_id")
    artifact_api_sha = str(local.get("qg_artifact_api_sha256") or "")
    if type(artifact_id) is not int or artifact_id < 1 or DIGEST_RE.fullmatch(artifact_api_sha) is None:
        raise RuntimeError("runtime receipt QG artifact identity is invalid")
    launcher_receipt_path = PYTHON_RUNTIME_LAUNCHER_RECEIPTS / f"{artifact_id}-{artifact_api_sha}.json"
    launcher_receipt, launcher_receipt_raw = _read_authority_json(
        launcher_receipt_path,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if (
        set(launcher_receipt) != RUNTIME_LAUNCHER_RECEIPT_KEYS
        or launcher_receipt.get("schema") != 1
        or launcher_receipt.get("format") != "linas-python-runtime-launcher-v1"
        or launcher_receipt.get("artifact_id") != artifact_id
        or launcher_receipt.get("artifact_api_sha256") != artifact_api_sha
        or launcher_receipt.get("manifest_sha256") != local.get("qg_manifest_sha256")
        or launcher_receipt.get("run_id") != local.get("qg_run_id")
        or launcher_receipt.get("run_attempt") != local.get("qg_run_attempt")
        or launcher_receipt.get("target_sha") != local.get("qg_target_sha")
        or launcher_receipt.get("control_plane_archive_sha256") != plan.get("control_plane_archive_sha256")
        or launcher_receipt.get("control_plane_tree_sha256") != plan.get("control_plane_tree_sha256")
    ):
        raise RuntimeError("runtime launcher receipt differs from the provision authority")
    bundle_key = f"{artifact_id}-{artifact_api_sha}"
    bundle_root = STATE_ROOT / "release-bundles" / bundle_key
    launcher_control = STATE_ROOT / "python-runtime-provision-control" / bundle_key
    launcher_path = launcher_control / "scripts/ha/python_runtime_provision_trusted_launcher.py"
    if (
        launcher_receipt.get("bundle_root") != str(bundle_root)
        or launcher_receipt.get("control_root") != str(launcher_control)
        or launcher_receipt.get("launcher_path") != str(launcher_path)
    ):
        raise RuntimeError("runtime launcher receipt paths are invalid")
    _secure_authority_dir(
        bundle_root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if {entry.name for entry in os.scandir(bundle_root)} != RUNTIME_RELEASE_BUNDLE_FILES:
        raise RuntimeError("runtime launcher release bundle file set is incomplete")
    bundle_limits = {
        "release-manifest.json": MAX_AUTHORITY_BYTES,
        "wheelhouse.tar": MAX_RELEASE_PAYLOAD_BYTES,
        "dashboard-build.tar": MAX_RELEASE_PAYLOAD_BYTES,
        "control-plane.tar": MAX_CONTROL_ARCHIVE_BYTES,
        "source.bundle": 1024**3,
        PYTHON_RUNTIME_ARTIFACT_NAME: MAX_PYTHON_RUNTIME_ARCHIVE_BYTES,
    }
    bundle_evidence = {
        name: _authority_file_evidence(
            bundle_root / name,
            limit=limit,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        for name, limit in bundle_limits.items()
    }
    if bundle_evidence["release-manifest.json"][0] != _digest_bytes(manifest_raw):
        raise RuntimeError("runtime launcher bundle manifest differs from retained authority")
    launcher_size = launcher_receipt.get("launcher_size")
    if type(launcher_size) is not int or not 1 <= launcher_size <= 8 * 1024**2:
        raise RuntimeError("runtime launcher receipt size is invalid")
    launcher_evidence = _authority_file_evidence(
        launcher_path,
        limit=8 * 1024**2,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        mode=0o644,
    )
    if launcher_evidence != (launcher_receipt.get("launcher_sha256"), launcher_size):
        raise RuntimeError("runtime launcher bytes differ from its immutable receipt")
    control_archive = authority_root / "control-plane.tar"
    control_archive_evidence = _authority_file_evidence(
        control_archive,
        limit=MAX_CONTROL_ARCHIVE_BYTES,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if control_archive_evidence[0] != plan.get("control_plane_archive_sha256"):
        raise RuntimeError("retained control-plane archive differs from the runtime plan")
    control_tree_sha, control_count, control_size, control_names = _release_tree_evidence(
        control_root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if control_tree_sha != plan.get("control_plane_tree_sha256") or not RUNTIME_CONTROL_FILES <= control_names:
        raise RuntimeError("authenticated runtime control tree differs from its plan")
    helper_path = control_root / HELPER_REPO_PATH
    helper_raw = _read_authority_file(
        helper_path,
        limit=8 * 1024**2,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        mode=0o644,
    )
    if Path(__file__).resolve() != helper_path or Path(__file__).read_bytes() != helper_raw:
        raise RuntimeError("bootstrap helper is not the authenticated provision control blob")

    # Import only after the complete extracted control tree has matched the
    # QG-bound digest. In production this module was itself entered through
    # the OS-Python run-bootstrap trust bridge, which also verified the full
    # portable runtime before this interpreter was executed.
    from scripts.ha import python_runtime_archive_contract as runtime_archive
    from scripts.ha import python_runtime_provision_contract as provision
    from scripts.ha import python_runtime_provision_ingest_contract as ingest
    from scripts.ha import release_artifact_contract as release

    provision.EXPECTED_UID = expected_uid
    provision.EXPECTED_GID = expected_gid
    runtime_archive.EXPECTED_UID = expected_uid
    runtime_archive.EXPECTED_GID = expected_gid
    validated_plan = provision.validate_plan(plan, plan_sha)
    provision.validate_node_receipt(local, validated_plan, plan_sha)
    provision.validate_cluster_receipt(cluster, validated_plan, plan_sha)
    ingest.validate_launcher_receipt(launcher_receipt)
    validated_manifest = release.validate_manifest(
        manifest,
        expected_repository=str(plan["qg_repository"]),
        expected_workflow_ref=str(plan["qg_workflow_ref"]),
        expected_run_id=int(plan["qg_run_id"]),
        expected_run_attempt=int(plan["qg_run_attempt"]),
        expected_target_sha=str(plan["qg_target_sha"]),
    )
    verified_bundle_manifest = release.verify_release_bundle(
        bundle_root,
        expected_repository=str(plan["qg_repository"]),
        expected_workflow_ref=str(plan["qg_workflow_ref"]),
        expected_run_id=int(plan["qg_run_id"]),
        expected_run_attempt=int(plan["qg_run_attempt"]),
        expected_target_sha=str(plan["qg_target_sha"]),
    )
    if verified_bundle_manifest != validated_manifest:
        raise RuntimeError("global runtime launcher bundle differs from retained transaction authority")
    expected_control = validated_manifest["payloads"]["control_plane"]
    if (
        expected_control["archive_sha256"] != control_archive_evidence[0]
        or expected_control["tree_sha256"] != control_tree_sha
        or expected_control["file_count"] != control_count
        or expected_control["total_size"] != control_size
        or control_names != release.CONTROL_PLANE_MEMBERS
    ):
        raise RuntimeError("retained control-plane evidence differs from the QG manifest")
    wheelhouse = authority_root / "wheelhouse.tar"
    wheel = release.verify_archive(
        wheelhouse,
        str(plan["wheelhouse_archive_sha256"]),
        str(plan["wheelhouse_tree_sha256"]),
    )
    if (wheel.file_count, wheel.total_size) != (
        plan["wheelhouse_file_count"],
        plan["wheelhouse_total_size"],
    ):
        raise RuntimeError("retained wheelhouse evidence differs from the provision plan")
    runtime_tree_sha, _runtime_count = runtime_archive.runtime_tree_evidence(PYTHON_RUNTIME_ROOT)
    if runtime_tree_sha != plan.get("runtime_tree_sha256"):
        raise RuntimeError("portable Python runtime tree differs from the committed provision plan")
    requirements_raw = _read_authority_file(
        control_root / "requirements.lock",
        limit=8 * 1024**2,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        mode=0o644,
    )
    requirements_sha = _digest_bytes(requirements_raw)
    if requirements_sha != validated_manifest["source_locks"]["requirements_lock_sha256"]:
        raise RuntimeError("authenticated production lock differs from the QG manifest")
    shared = {
        "schema": 1,
        "transaction_id": transaction_id,
        "plan_sha256": plan_sha,
        "cluster_receipt_sha256": _digest_bytes(cluster_raw),
        "launcher_receipt_sha256": _digest_bytes(launcher_receipt_raw),
        "manifest_sha256": _digest_bytes(manifest_raw),
        "control_plane_archive_sha256": control_archive_evidence[0],
        "control_plane_tree_sha256": control_tree_sha,
        "wheelhouse_archive_sha256": wheel.archive_sha256,
        "wheelhouse_tree_sha256": wheel.tree_sha256,
        "wheelhouse_file_count": wheel.file_count,
        "wheelhouse_total_size": wheel.total_size,
        "requirements_lock_sha256": requirements_sha,
        "runtime_tree_sha256": runtime_tree_sha,
        "qg_artifact_id": artifact_id,
        "qg_artifact_api_sha256": artifact_api_sha,
        "qg_run_id": plan["qg_run_id"],
        "qg_run_attempt": plan["qg_run_attempt"],
        "qg_target_sha": plan["qg_target_sha"],
    }
    return {
        "schema": 1,
        "node_id": node_id,
        "node_receipt_sha256": _digest_bytes(local_raw),
        "shared": shared,
        "shared_sha256": _digest(shared),
        "authority_root": str(authority_root),
        "control_root": str(control_root),
        "launcher_path": str(launcher_path),
    }


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600, no_replace: bool = False) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.bootstrap.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if no_replace:
            os.link(temporary, path, follow_symlinks=False)
            # Persist the final name before removing the temporary alias.  A
            # crash in this interval is repaired by
            # ``_repair_no_replace_publication`` on the next authenticated
            # read.
            _fsync_dir(path.parent)
            temporary.unlink()
        else:
            os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _unlink_durable(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_dir(path.parent)


def _write_coordinator_journal(payload: dict[str, Any]) -> None:
    expected_keys = {
        "schema",
        "tx_id",
        "plan_sha256",
        "target_sha",
        "node01_previous_sha",
        "node02_previous_sha",
        "expected_pg_state_sha256",
        "lb_attestation_sha256",
        "source_sha256",
        "peer_host",
        "phase",
        "decision",
    }
    if set(payload) != expected_keys or payload.get("schema") != 1:
        raise RuntimeError("bootstrap coordinator journal schema is invalid")
    if not TX_RE.fullmatch(str(payload.get("tx_id") or "")):
        raise RuntimeError("bootstrap coordinator transaction ID is invalid")
    for key in ("target_sha", "node01_previous_sha", "node02_previous_sha"):
        _validate_sha(str(payload.get(key) or ""), f"bootstrap coordinator {key}")
    for key in ("plan_sha256", "expected_pg_state_sha256", "lb_attestation_sha256", "source_sha256"):
        _validate_digest(str(payload.get(key) or ""), f"bootstrap coordinator {key}")
    if payload.get("peer_host") != FIXED_NODES["node01"]["peer_ip"]:
        raise RuntimeError("bootstrap coordinator peer is invalid")
    if payload.get("decision") not in {"rollback", "commit"} or not re.fullmatch(
        r"[a-z0-9-]{3,64}", str(payload.get("phase") or "")
    ):
        raise RuntimeError("bootstrap coordinator state is invalid")
    _secure_dir(STATE_ROOT, create=True)
    if COORDINATOR_PATH.exists() or COORDINATOR_PATH.is_symlink():
        _secure_regular(COORDINATOR_PATH)
        current_payload, _ = _read_regular_any_owner(COORDINATOR_PATH)
        current = json.loads(current_payload)
        immutable = expected_keys - {"phase", "decision"}
        if set(current) != expected_keys or any(current.get(key) != payload[key] for key in immutable):
            raise RuntimeError("bootstrap coordinator immutable contract changed")
        if current.get("decision") == "commit" and payload.get("decision") != "commit":
            raise RuntimeError("durable bootstrap commit decision cannot be reversed")
    elif payload.get("phase") != "planned" or payload.get("decision") != "rollback":
        raise RuntimeError("bootstrap coordinator journal must precede every mutation")
    _atomic_write(COORDINATOR_PATH, _canonical(payload) + b"\n")


def _read_coordinator_journal(expected_sha256: str) -> dict[str, Any]:
    _validate_digest(expected_sha256, "bootstrap coordinator journal")
    payload, payload_bytes = _read_current_coordinator_journal()
    if _digest_bytes(payload_bytes) != expected_sha256:
        raise RuntimeError("bootstrap coordinator journal changed after owner confirmation")
    return payload


def _read_current_coordinator_journal() -> tuple[dict[str, Any], bytes]:
    _secure_regular(COORDINATOR_PATH)
    payload_bytes, _ = _read_regular_any_owner(COORDINATOR_PATH)
    payload = json.loads(payload_bytes)
    expected_keys = {
        "schema",
        "tx_id",
        "plan_sha256",
        "target_sha",
        "node01_previous_sha",
        "node02_previous_sha",
        "expected_pg_state_sha256",
        "lb_attestation_sha256",
        "source_sha256",
        "peer_host",
        "phase",
        "decision",
    }
    if set(payload) != expected_keys or payload.get("schema") != 1:
        raise RuntimeError("bootstrap coordinator journal schema is invalid")
    if not TX_RE.fullmatch(str(payload.get("tx_id") or "")):
        raise RuntimeError("bootstrap coordinator journal transaction ID is invalid")
    for key in ("target_sha", "node01_previous_sha", "node02_previous_sha"):
        _validate_sha(str(payload.get(key) or ""), f"bootstrap coordinator {key}")
    for key in ("plan_sha256", "expected_pg_state_sha256", "lb_attestation_sha256", "source_sha256"):
        _validate_digest(str(payload.get(key) or ""), f"bootstrap coordinator {key}")
    if payload.get("peer_host") != FIXED_NODES["node01"]["peer_ip"]:
        raise RuntimeError("bootstrap coordinator journal peer is invalid")
    if not re.fullmatch(r"[a-z0-9-]{3,64}", str(payload.get("phase") or "")):
        raise RuntimeError("bootstrap coordinator journal phase is invalid")
    if payload.get("decision") not in {"rollback", "commit"}:
        raise RuntimeError("bootstrap coordinator journal decision is invalid")
    return payload, payload_bytes


def _publish_commit_decision(payload: dict[str, Any]) -> dict[str, Any]:
    """Publish and read back the one irreversible decision before memory flips."""

    if payload.get("decision") != "rollback":
        raise RuntimeError("bootstrap commit publication requires the durable rollback state")
    candidate = {**payload, "phase": "commit-decided", "decision": "commit"}
    _write_coordinator_journal(candidate)
    persisted, _ = _read_current_coordinator_journal()
    if persisted != candidate:
        raise RuntimeError("bootstrap commit decision was not durably read back")
    return persisted


def _parse_env(payload: bytes) -> dict[str, str]:
    if b"\0" in payload:
        raise RuntimeError("canonical environment contains NUL")
    text = payload.decode("utf-8", errors="strict")
    values: dict[str, str] = {}
    duplicates: set[str] = set()
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            duplicates.add(key)
        values[key] = value.strip().strip("\"'")
    if duplicates:
        raise RuntimeError("canonical environment contains duplicate keys")
    return values


def _assert_no_execution_env_injection(values: dict[str, str]) -> None:
    if any(
        key in FORBIDDEN_EXECUTION_ENV_KEYS
        or key.startswith(FORBIDDEN_EXECUTION_ENV_PREFIXES)
        or (key.startswith("PYTHON") and key not in {"PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE"})
        for key in values
    ):
        raise RuntimeError("canonical environment contains a forbidden code-loader control")


def _render_env(payload: bytes, node_id: str) -> bytes:
    text = payload.decode("utf-8", errors="strict")
    replacements = {
        **CONTRACT_KEYS,
        "META_DELETION_NODE_ID": node_id,
        "LINAS_HA_PEER_HOST": str(FIXED_NODES[node_id]["peer_ip"]),
    }
    output: list[str] = []
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in replacements:
                continue
        output.append(line)
    output.extend(f"{key}={replacements[key]}" for key in sorted(replacements))
    return ("\n".join(output) + "\n").encode()


def _interface_addresses() -> set[str]:
    output = _run(["ip", "-o", "-4", "addr", "show", "scope", "global"]).stdout
    addresses: set[str] = set()
    for line in output.splitlines():
        fields = line.split()
        if "inet" in fields:
            addresses.add(fields[fields.index("inet") + 1].split("/", 1)[0])
    return addresses


def _assert_identity(node_id: str) -> None:
    expected = FIXED_NODES[node_id]
    actual_hostname = _run(["hostname", "-s"]).stdout.strip()
    if actual_hostname != expected["hostname"]:
        raise RuntimeError(f"{node_id} hostname does not match the explicit fixed identity")
    addresses = _interface_addresses()
    for kind in ("public_ip", "private_ip"):
        if expected[kind] not in addresses:
            raise RuntimeError(f"{node_id} {kind} is not assigned to this host")
    if expected["peer_ip"] in addresses:
        raise RuntimeError(f"{node_id} peer address resolves to the local host")


def _git(*args: str, check: bool = True, strip: bool = True) -> str:
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    result = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.attributesFile=/dev/null",
            "-C",
            str(REPO_DIR),
            *args,
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError("sanitized Git operation failed")
    return result.stdout.strip() if strip else result.stdout


def _git_control_path(label: str) -> Path:
    if label == "opt":
        return Path("/opt")
    if label == "repo":
        return REPO_DIR
    if label == "git":
        return REPO_DIR / ".git"
    if label.startswith("git/"):
        relative = label.removeprefix("git/")
        if not relative or relative.startswith("/") or any(part in {"", ".", ".."} for part in relative.split("/")):
            raise RuntimeError("Git metadata path is invalid")
        return REPO_DIR / ".git" / relative
    raise RuntimeError("Git metadata path is outside the canonical control roots")


def _collect_git_metadata() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def append(label: str, path: Path) -> None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise RuntimeError("Git control metadata contains an unsafe object")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise RuntimeError("Git control metadata contains a hard-linked file")
        result.append(
            {
                "path": label,
                "type": "directory" if stat.S_ISDIR(info.st_mode) else "file",
                "uid": info.st_uid,
                "gid": info.st_gid,
                "mode": stat.S_IMODE(info.st_mode),
            }
        )

    append("opt", Path("/opt"))
    append("repo", REPO_DIR)
    git_root = REPO_DIR / ".git"
    append("git", git_root)
    for current, dirnames, filenames in os.walk(git_root, topdown=True, followlinks=False):
        directory = Path(current)
        relative_directory = directory.relative_to(git_root)
        for name in sorted(dirnames, key=os.fsencode):
            relative = (relative_directory / name).as_posix()
            append(f"git/{relative}", directory / name)
        for name in sorted(filenames, key=os.fsencode):
            relative = (relative_directory / name).as_posix()
            append(f"git/{relative}", directory / name)
        if len(result) > 500_000:
            raise RuntimeError("Git control metadata exceeds the reviewed entry limit")
    return sorted(result, key=lambda entry: os.fsencode(str(entry["path"])))


def _normalized_git_metadata(entry: dict[str, Any]) -> tuple[int, int, int]:
    if entry["type"] == "directory":
        mode = 0o755 if entry["path"] in {"opt", "repo"} else 0o700
    else:
        mode = 0o600
    return 0, 0, mode


def _assert_git_repository_trust(*, normalized: bool) -> None:
    if Path(os.path.realpath(REPO_DIR)) != REPO_DIR:
        raise RuntimeError("canonical repository path is aliased")
    metadata = _collect_git_metadata()
    for entry in metadata:
        observed = (entry["uid"], entry["gid"], entry["mode"])
        if normalized:
            if observed != _normalized_git_metadata(entry):
                raise RuntimeError("canonical Git control metadata is not root-normalized")
        else:
            if entry["path"] == "opt" and observed != (0, 0, 0o755):
                raise RuntimeError("canonical /opt trust root is not exact before bootstrap")
            if int(entry["mode"]) & 0o022:
                raise RuntimeError("pre-bootstrap Git control metadata is group/world writable")
    forbidden = (
        REPO_DIR / ".git/refs/replace",
        REPO_DIR / ".git/commondir",
        REPO_DIR / ".git/info/grafts",
        REPO_DIR / ".git/info/attributes",
        REPO_DIR / ".git/objects/info/alternates",
        REPO_DIR / ".git/objects/info/http-alternates",
    )
    if any(path.exists() or path.is_symlink() for path in forbidden):
        raise RuntimeError("Git replacement, alternate, or local attribute authority is forbidden")
    for entry in metadata:
        if str(entry["path"]).endswith(".lock"):
            raise RuntimeError("stale Git lock requires explicit recovery before bootstrap")
    packed_refs = REPO_DIR / ".git/packed-refs"
    if packed_refs.exists() or packed_refs.is_symlink():
        packed_raw, _ = _read_regular_any_owner(packed_refs)
        if b" refs/replace/" in packed_raw:
            raise RuntimeError("packed Git replacement references are forbidden")
    config_raw, config_info = _read_regular_any_owner(REPO_DIR / ".git/config")
    if config_info.st_nlink != 1 or stat.S_IMODE(config_info.st_mode) & 0o022:
        raise RuntimeError("local Git configuration metadata is unsafe")
    if not config_raw or len(config_raw) > MAX_AUTHORITY_BYTES:
        raise RuntimeError("local Git configuration size is invalid")
    allowed = {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "remote.origin.url",
        "remote.origin.fetch",
        "branch.main.remote",
        "branch.main.merge",
    }
    names = set(_git("config", "--local", "--no-includes", "--name-only", "--get-regexp", ".*").splitlines())
    if names != allowed:
        raise RuntimeError("local Git configuration key set is not exact")
    expected = {
        "core.repositoryformatversion": "0",
        "core.filemode": "true",
        "core.bare": "false",
        "core.logallrefupdates": "true",
        "remote.origin.url": "git@github.com:MahmoudAlZougbhi/linasbot-server.git",
        "remote.origin.fetch": "+refs/heads/*:refs/remotes/origin/*",
        "branch.main.remote": "origin",
        "branch.main.merge": "refs/heads/main",
    }
    if any(_git("config", "--local", "--no-includes", "--get", key) != value for key, value in expected.items()):
        raise RuntimeError("local Git configuration value is not exact")
    if _git("symbolic-ref", "-q", "HEAD") != "refs/heads/main":
        raise RuntimeError("canonical Git HEAD is not the protected main branch")
    if _git("rev-parse", "--absolute-git-dir") != str(REPO_DIR / ".git"):
        raise RuntimeError("Git directory resolves outside the canonical repository")
    if _git("rev-parse", "--path-format=absolute", "--git-common-dir") != str(REPO_DIR / ".git"):
        raise RuntimeError("Git common directory resolves outside the canonical repository")
    attribute_path = _git("rev-parse", "--path-format=absolute", "--git-path", "info/attributes")
    if attribute_path != str(REPO_DIR / ".git/info/attributes"):
        raise RuntimeError("Git attribute authority resolves outside the canonical repository")
    tracked_control = _git(
        "ls-files",
        "--",
        ".gitattributes",
        "*/.gitattributes",
        ".gitmodules",
        "*/.gitmodules",
        check=False,
    )
    if tracked_control:
        raise RuntimeError("tracked Git attribute or submodule authority is forbidden")


def _git_metadata_evidence() -> dict[str, Any]:
    metadata = _collect_git_metadata()
    return {"sha256": _digest(metadata), "entry_count": len(metadata)}


def _read_git_metadata_backup(backup: Path) -> list[dict[str, Any]]:
    raw = _read_authority_file(backup / "git-metadata.before.json", limit=MAX_GIT_METADATA_BYTES)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Git metadata rollback authority is invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "entries"}
        or payload.get("schema") != 1
        or not isinstance(payload.get("entries"), list)
        or raw != _canonical(payload) + b"\n"
    ):
        raise RuntimeError("Git metadata rollback authority is invalid")
    raw_entries = payload["entries"]
    if len(raw_entries) > 500_000:
        raise RuntimeError("Git metadata rollback entry count is invalid")
    entries: list[dict[str, Any]] = []
    labels: set[str] = set()
    for raw_entry in raw_entries:
        if (
            not isinstance(raw_entry, dict)
            or set(raw_entry) != {"path", "type", "uid", "gid", "mode"}
            or not isinstance(raw_entry.get("path"), str)
            or raw_entry.get("type") not in {"directory", "file"}
            or type(raw_entry.get("uid")) is not int
            or type(raw_entry.get("gid")) is not int
            or type(raw_entry.get("mode")) is not int
            or int(raw_entry["uid"]) < 0
            or int(raw_entry["gid"]) < 0
            or not 0 <= int(raw_entry["mode"]) <= 0o777
        ):
            raise RuntimeError("Git metadata rollback entry schema is invalid")
        label = str(raw_entry["path"])
        if label in labels:
            raise RuntimeError("Git metadata rollback contains a duplicate path")
        labels.add(label)
        _git_control_path(label)
        entries.append(dict(raw_entry))
    if entries != sorted(entries, key=lambda entry: os.fsencode(str(entry["path"]))):
        raise RuntimeError("Git metadata rollback entries are not canonical")
    return entries


def _backup_git_metadata(backup: Path, expected: dict[str, Any]) -> None:
    metadata = _collect_git_metadata()
    if expected != {"sha256": _digest(metadata), "entry_count": len(metadata)}:
        raise RuntimeError("Git control metadata changed after the owner-authorized plan")
    payload = _canonical({"schema": 1, "entries": metadata}) + b"\n"
    path = backup / "git-metadata.before.json"
    if path.exists() or path.is_symlink():
        if _read_authority_file(path, limit=MAX_GIT_METADATA_BYTES) != payload:
            raise RuntimeError("Git metadata rollback authority changed")
    else:
        _atomic_write(path, payload, no_replace=True)


def _apply_git_metadata(entries: list[dict[str, Any]], *, normalized: bool) -> None:
    observed = {str(entry["path"]): entry for entry in _collect_git_metadata()}
    expected = {str(entry["path"]): entry for entry in entries}
    if set(observed) != set(expected):
        raise RuntimeError("Git control object set changed during metadata migration")
    for label, original in expected.items():
        if observed[label]["type"] != original["type"]:
            raise RuntimeError("Git control object type changed during metadata migration")
        target = _normalized_git_metadata(original)
        current = (observed[label]["uid"], observed[label]["gid"], observed[label]["mode"])
        original_metadata = (original["uid"], original["gid"], original["mode"])
        # chown(2) changes the owner pair atomically, while chmod(2) is a
        # separate durability boundary.  A killed apply/rollback may therefore
        # expose either exact owner pair with either exact mode.  Accept only
        # that closed cross-product and deterministically finish the requested
        # direction; all other partial metadata remains fail-closed.
        if (current[0], current[1]) not in {
            (original_metadata[0], original_metadata[1]),
            (target[0], target[1]),
        } or current[2] not in {original_metadata[2], target[2]}:
            raise RuntimeError("Git control metadata has an unauthenticated partial state")
    gates = {str(entry["path"]): entry for entry in entries if entry["path"] in {"opt", "repo", "git"}}
    if set(gates) != {"opt", "repo", "git"}:
        raise RuntimeError("Git metadata migration is missing a canonical path gate")
    remaining = [entry for entry in entries if entry["path"] not in gates]
    if normalized:
        # /opt is already an exact root-owned trust anchor.  Lock the worktree
        # and then .git against non-root mutation before touching descendants.
        ordered = [gates["opt"], gates["repo"], gates["git"], *remaining]
    else:
        # Restore descendants while .git remains root-only.  Return ownership
        # of the gates only after every child has reached its exact baseline.
        ordered = [*remaining, gates["git"], gates["repo"], gates["opt"]]
    for entry in ordered:
        path = _git_control_path(str(entry["path"]))
        uid, gid, mode = (
            _normalized_git_metadata(entry)
            if normalized
            else (int(entry["uid"]), int(entry["gid"]), int(entry["mode"]))
        )
        os.chown(path, uid, gid, follow_symlinks=False)
        os.chmod(path, mode, follow_symlinks=False)
        if entry["type"] == "file":
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        else:
            _fsync_dir(_git_control_path(str(entry["path"])))


def _normalize_git_metadata(backup: Path, expected: dict[str, Any]) -> None:
    entries = _read_git_metadata_backup(backup)
    if expected != {"sha256": _digest(entries), "entry_count": len(entries)}:
        raise RuntimeError("Git metadata rollback authority differs from the bootstrap plan")
    _apply_git_metadata(entries, normalized=True)
    _assert_normalized_git_metadata(backup, expected)


def _assert_normalized_git_metadata(backup: Path, expected: dict[str, Any]) -> None:
    entries = _read_git_metadata_backup(backup)
    if expected != {"sha256": _digest(entries), "entry_count": len(entries)}:
        raise RuntimeError("Git metadata rollback authority differs from the bootstrap plan")
    normalized = [
        {
            **entry,
            "uid": _normalized_git_metadata(entry)[0],
            "gid": _normalized_git_metadata(entry)[1],
            "mode": _normalized_git_metadata(entry)[2],
        }
        for entry in entries
    ]
    if _collect_git_metadata() != normalized:
        raise RuntimeError("Git control metadata migration is not exact")
    _assert_git_repository_trust(normalized=True)


def _restore_git_metadata(backup: Path, expected: dict[str, Any]) -> None:
    entries = _read_git_metadata_backup(backup)
    if expected != {"sha256": _digest(entries), "entry_count": len(entries)}:
        raise RuntimeError("Git metadata rollback authority differs from the bootstrap plan")
    _apply_git_metadata(entries, normalized=False)
    _assert_restored_git_metadata(backup, expected)


def _assert_restored_git_metadata(backup: Path, expected: dict[str, Any]) -> None:
    entries = _read_git_metadata_backup(backup)
    if expected != {"sha256": _digest(entries), "entry_count": len(entries)}:
        raise RuntimeError("Git metadata rollback authority differs from the bootstrap plan")
    if _collect_git_metadata() != entries:
        raise RuntimeError("Git control metadata rollback is not exact")
    _assert_git_repository_trust(normalized=False)


def _assert_repo(expected_sha: str) -> None:
    _assert_git_repository_trust(normalized=False)
    if Path(os.path.realpath(REPO_DIR)) != REPO_DIR or _git("rev-parse", "--show-toplevel") != str(REPO_DIR):
        raise RuntimeError("canonical repository root is invalid")
    if _git("rev-parse", "HEAD") != expected_sha:
        raise RuntimeError("node Git baseline changed from the explicit expected SHA")
    _git("diff", "--no-ext-diff", "--quiet", expected_sha, "--")
    _git("diff", "--cached", "--no-ext-diff", "--quiet", expected_sha, "--")


def _historical_env_manifest(expected_sha: str) -> list[dict[str, Any]]:
    if _git("ls-files", "--error-unmatch", ".env.example") != ".env.example":
        raise RuntimeError(".env.example is not a tracked exception")
    expected_example = _git("show", f"{expected_sha}:.env.example", strip=False).encode()
    if (REPO_DIR / ".env.example").read_bytes() != expected_example:
        raise RuntimeError("tracked .env.example differs from the exact baseline")
    manifest: list[dict[str, Any]] = []
    for path in sorted(REPO_DIR.glob(".env*"), key=lambda item: os.fsencode(item.name)):
        if path in {ENV_PATH, REPO_DIR / ".env.example"}:
            continue
        payload, info = _read_regular_any_owner(path)
        manifest.append(
            {
                "name": path.name,
                "sha256": _digest_bytes(payload),
                "size": len(payload),
                "uid": info.st_uid,
                "gid": info.st_gid,
                "mode": stat.S_IMODE(info.st_mode),
            }
        )
    return manifest


def _render_unit_template(payload: bytes) -> bytes:
    if payload.count(b"__APP_DIR__") < 1:
        raise RuntimeError("authenticated canonical unit template has no application placeholder")
    rendered = payload.replace(b"__APP_DIR__", os.fsencode(REPO_DIR))
    if b"__APP_DIR__" in rendered or b"Environment=PYTHONDONTWRITEBYTECODE=1\n" not in rendered:
        raise RuntimeError("authenticated canonical unit template is incomplete")
    return rendered


def _target_unit_contract(runtime_authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    control_root = Path(str(runtime_authority["control_root"]))
    result: dict[str, dict[str, Any]] = {}
    for name, relative, destination in (
        (API_UNIT, "deploy/systemd/linasbot.service", API_UNIT_PATH),
        (
            "linasbot-worker@.service",
            "deploy/systemd/linasbot-worker@.service",
            WORKER_TEMPLATE_PATH,
        ),
    ):
        source = control_root / relative
        payload = _read_authority_file(source, limit=1024 * 1024, mode=0o644)
        rendered = _render_unit_template(payload)
        result[name] = {
            "destination": str(destination),
            "source_sha256": _digest_bytes(payload),
            "rendered_sha256": _digest_bytes(rendered),
            "size": len(rendered),
        }
    return result


def _live_unit_contract() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, path in (
        (API_UNIT, API_UNIT_PATH),
        ("linasbot-worker@.service", WORKER_TEMPLATE_PATH),
    ):
        payload, info = _read_regular_any_owner(path)
        if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o644 or info.st_nlink != 1:
            raise RuntimeError("live canonical unit is not root-owned mode 0644")
        result[name] = {
            "destination": str(path),
            "sha256": _digest_bytes(payload),
            "size": len(payload),
            "mode": 0o644,
        }
    return result


def _target_unit_payloads(runtime_authority: dict[str, Any]) -> dict[str, bytes]:
    control_root = Path(str(runtime_authority["control_root"]))
    return {
        API_UNIT: _render_unit_template(
            _read_authority_file(
                control_root / "deploy/systemd/linasbot.service",
                limit=1024 * 1024,
                mode=0o644,
            )
        ),
        "linasbot-worker@.service": _render_unit_template(
            _read_authority_file(
                control_root / "deploy/systemd/linasbot-worker@.service",
                limit=1024 * 1024,
                mode=0o644,
            )
        ),
    }


def _backup_live_units(backup: Path, live: dict[str, dict[str, Any]]) -> None:
    unit_root = backup / "units.before"
    if unit_root.exists() or unit_root.is_symlink():
        _secure_dir(unit_root)
    else:
        unit_root.mkdir(mode=0o700)
        os.chown(unit_root, 0, 0)
        _fsync_dir(backup)
    for name, path in ((API_UNIT, API_UNIT_PATH), ("linasbot-worker@.service", WORKER_TEMPLATE_PATH)):
        payload, info = _read_regular_any_owner(path)
        expected = live[name]
        if (
            _digest_bytes(payload) != expected["sha256"]
            or len(payload) != expected["size"]
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != expected["mode"]
        ):
            raise RuntimeError("live canonical unit changed after the owner-authorized plan")
        destination = unit_root / name
        if destination.exists() or destination.is_symlink():
            _secure_regular(destination)
            if destination.read_bytes() != payload:
                raise RuntimeError("partial canonical unit backup changed")
        else:
            _atomic_write(destination, payload, no_replace=True)


def _assert_target_units(runtime_authority: dict[str, Any]) -> None:
    target = _target_unit_payloads(runtime_authority)
    for name, path in ((API_UNIT, API_UNIT_PATH), ("linasbot-worker@.service", WORKER_TEMPLATE_PATH)):
        payload, info = _read_regular_any_owner(path)
        if (
            payload != target[name]
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o644
            or info.st_nlink != 1
        ):
            raise RuntimeError("installed canonical unit differs from authenticated control authority")
    for unit in (API_UNIT, *WORKER_UNITS):
        if _run(["systemctl", "show", unit, "--property=NeedDaemonReload", "--value"]).stdout.strip() != "no":
            raise RuntimeError("installed canonical unit contract is not loaded")


def _install_target_units(
    runtime_authority: dict[str, Any],
    live: dict[str, dict[str, Any]],
) -> None:
    target = _target_unit_payloads(runtime_authority)
    for name, path in ((API_UNIT, API_UNIT_PATH), ("linasbot-worker@.service", WORKER_TEMPLATE_PATH)):
        if path.exists() or path.is_symlink():
            current, info = _read_regular_any_owner(path)
            if current != target[name] and _digest_bytes(current) != live[name]["sha256"]:
                raise RuntimeError("canonical unit changed before authenticated migration")
            if current == target[name] and (
                info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o644
            ):
                raise RuntimeError("canonical target unit has unsafe metadata")
        _atomic_write(path, target[name], mode=0o644)
    _run(["systemctl", "daemon-reload"])
    _assert_target_units(runtime_authority)


def _restore_live_units(backup: Path, live: dict[str, dict[str, Any]]) -> None:
    unit_root = backup / "units.before"
    _secure_dir(unit_root)
    for name, path in ((API_UNIT, API_UNIT_PATH), ("linasbot-worker@.service", WORKER_TEMPLATE_PATH)):
        archived = unit_root / name
        _secure_regular(archived)
        payload = archived.read_bytes()
        expected = live[name]
        if _digest_bytes(payload) != expected["sha256"] or len(payload) != expected["size"]:
            raise RuntimeError("canonical unit rollback authority changed")
        _atomic_write(path, payload, mode=int(expected["mode"]))
    _run(["systemctl", "daemon-reload"])
    for unit in (API_UNIT, *WORKER_UNITS):
        if _run(["systemctl", "show", unit, "--property=NeedDaemonReload", "--value"]).stdout.strip() != "no":
            raise RuntimeError("restored canonical unit contract is not loaded")


def _assert_live_units(live: dict[str, dict[str, Any]]) -> None:
    for name, path in ((API_UNIT, API_UNIT_PATH), ("linasbot-worker@.service", WORKER_TEMPLATE_PATH)):
        payload, info = _read_regular_any_owner(path)
        expected = live[name]
        if (
            _digest_bytes(payload) != expected["sha256"]
            or len(payload) != expected["size"]
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != expected["mode"]
        ):
            raise RuntimeError("restored canonical unit baseline is not exact")


def _repo_bytecode_manifest() -> list[dict[str, Any]]:
    excluded_roots = {".git", ".venv", "venv", "linaslaserbot-2.7.22"}
    manifest: list[dict[str, Any]] = []
    total_size = 0
    for current, dirnames, filenames in os.walk(REPO_DIR, topdown=True, followlinks=False):
        directory = Path(current)
        relative_directory = directory.relative_to(REPO_DIR)
        if relative_directory.parts[:1] == ("linaslaserbot-2.7.22",):
            dirnames[:] = []
            filenames.clear()
            continue
        if not relative_directory.parts:
            dirnames[:] = [name for name in dirnames if name not in excluded_roots]
        if relative_directory.parts[:2] in {("dashboard", "node_modules"), ("dashboard", "build")}:
            dirnames[:] = []
            continue
        for name in list(dirnames):
            path = directory / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                if name == "__pycache__":
                    raise RuntimeError("repository Python bytecode path is a symlink")
                dirnames.remove(name)
                continue
            if name == "__pycache__" or "__pycache__" in relative_directory.parts:
                relative = path.relative_to(REPO_DIR).as_posix()
                manifest.append(
                    {
                        "path": relative,
                        "type": "directory",
                        "uid": info.st_uid,
                        "gid": info.st_gid,
                        "mode": stat.S_IMODE(info.st_mode),
                    }
                )
        for name in filenames:
            path = directory / name
            relative_path = path.relative_to(REPO_DIR)
            if "__pycache__" not in relative_path.parts and path.suffix not in {".pyc", ".pyo"}:
                continue
            payload, info = _read_regular_any_owner(path)
            total_size += len(payload)
            if len(manifest) >= 100_000 or total_size > 1024**3:
                raise RuntimeError("repository Python bytecode archive exceeds the safety limit")
            manifest.append(
                {
                    "path": relative_path.as_posix(),
                    "type": "file",
                    "sha256": _digest_bytes(payload),
                    "size": len(payload),
                    "uid": info.st_uid,
                    "gid": info.st_gid,
                    "mode": stat.S_IMODE(info.st_mode),
                }
            )
    return sorted(manifest, key=lambda entry: os.fsencode(str(entry["path"])))


def _assert_repo_bytecode_absent() -> None:
    if _repo_bytecode_manifest():
        raise RuntimeError("repository retains executable Python bytecode outside the release venv")


def _archive_repo_bytecode(backup: Path, expected: list[dict[str, Any]]) -> None:
    archive_root = backup / "legacy-python-bytecode"
    payload_root = archive_root / "payload"
    receipt = archive_root / "archive.complete.json"
    expected_receipt = {
        "schema": 1,
        "manifest_sha256": _digest(expected),
        "entry_count": len(expected),
    }
    current = _repo_bytecode_manifest()
    if receipt.exists() or receipt.is_symlink():
        _secure_regular(receipt)
        if json.loads(receipt.read_text(encoding="utf-8")) != expected_receipt:
            raise RuntimeError("legacy Python bytecode archive receipt changed")
        expected_by_path = {str(entry["path"]): entry for entry in expected}
        if any(expected_by_path.get(str(entry["path"])) != entry for entry in current):
            raise RuntimeError("repository Python bytecode changed during durable removal")
    else:
        if current != expected:
            raise RuntimeError("repository Python bytecode changed after the owner-authorized plan")
        if archive_root.exists() or archive_root.is_symlink():
            _secure_dir(archive_root)
        else:
            archive_root.mkdir(mode=0o700)
            os.chown(archive_root, 0, 0)
            _fsync_dir(backup)
        payload_root.mkdir(mode=0o700, exist_ok=True)
        _secure_dir(payload_root)
        for entry in expected:
            if entry["type"] != "file":
                continue
            source = REPO_DIR / str(entry["path"])
            destination = payload_root / str(entry["path"])
            destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            for parent in (destination.parent, *destination.parents):
                if parent == payload_root.parent:
                    break
                if payload_root not in parent.parents and parent != payload_root:
                    raise RuntimeError("legacy Python bytecode archive escaped its root")
                os.chown(parent, 0, 0)
                os.chmod(parent, 0o700)
            source_payload, _ = _read_regular_any_owner(source)
            if _digest_bytes(source_payload) != entry["sha256"]:
                raise RuntimeError("legacy Python bytecode changed during archive")
            if destination.exists() or destination.is_symlink():
                _secure_regular(destination)
                if destination.read_bytes() != source_payload:
                    raise RuntimeError("partial legacy Python bytecode archive changed")
            else:
                _atomic_write(destination, source_payload, no_replace=True)
        _fsync_private_tree(payload_root)
        _atomic_write(receipt, _canonical(expected_receipt) + b"\n", no_replace=True)
    for entry in reversed(expected):
        live = REPO_DIR / str(entry["path"])
        if entry["type"] == "file":
            if live.exists() or live.is_symlink():
                payload, _ = _read_regular_any_owner(live)
                if _digest_bytes(payload) != entry["sha256"]:
                    raise RuntimeError("legacy Python bytecode changed before removal")
                _unlink_durable(live)
        elif live.exists() or live.is_symlink():
            info = live.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or any(os.scandir(live)):
                raise RuntimeError("legacy Python bytecode directory is not empty after archive")
            live.rmdir()
            _fsync_dir(live.parent)
    _assert_repo_bytecode_absent()


def _restore_repo_bytecode(backup: Path, expected: list[dict[str, Any]]) -> None:
    archive_root = backup / "legacy-python-bytecode"
    if not archive_root.exists() and not archive_root.is_symlink():
        if _repo_bytecode_manifest() != expected:
            raise RuntimeError("repository Python bytecode changed before rollback")
        return
    receipt, _ = _read_authority_json(archive_root / "archive.complete.json")
    if receipt != {
        "schema": 1,
        "manifest_sha256": _digest(expected),
        "entry_count": len(expected),
    }:
        raise RuntimeError("legacy Python bytecode rollback authority is invalid")
    observed = _repo_bytecode_manifest()
    expected_by_path = {str(entry["path"]): entry for entry in expected}
    if any(expected_by_path.get(str(entry["path"])) != entry for entry in observed):
        raise RuntimeError("new repository Python bytecode blocks exact rollback")
    payload_root = archive_root / "payload"
    for entry in expected:
        live = REPO_DIR / str(entry["path"])
        if entry["type"] == "directory":
            if live.exists() or live.is_symlink():
                info = live.lstat()
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise RuntimeError("legacy Python bytecode rollback directory conflicts")
            else:
                live.mkdir(mode=int(entry["mode"]))
            os.chown(live, int(entry["uid"]), int(entry["gid"]))
            os.chmod(live, int(entry["mode"]))
            _fsync_dir(live.parent)
            continue
        archived = payload_root / str(entry["path"])
        payload = _read_authority_file(archived, limit=MAX_ENV_BYTES)
        if _digest_bytes(payload) != entry["sha256"]:
            raise RuntimeError("legacy Python bytecode rollback payload changed")
        if live.exists() or live.is_symlink():
            current, _ = _read_regular_any_owner(live)
            if current != payload:
                raise RuntimeError("legacy Python bytecode rollback destination conflicts")
        else:
            live.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(live, payload, mode=int(entry["mode"]), no_replace=True)
        # A crash after the no-replace publication but before metadata restore
        # is replayed through this same branch with the final file already
        # present.  Normalize ownership on both paths before accepting it.
        os.chown(live, int(entry["uid"]), int(entry["gid"]), follow_symlinks=False)
        os.chmod(live, int(entry["mode"]), follow_symlinks=False)
        _fsync_dir(live.parent)
    if _repo_bytecode_manifest() != expected:
        raise RuntimeError("legacy Python bytecode exact rollback failed")


PG_PROBE = r"""
import hashlib, json, os
from sqlalchemy import create_engine, text

def canonical(value):
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

dsn = (os.environ.get("LINAS_WHATSAPP_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
if dsn.startswith("postgres://"):
    dsn = "postgresql://" + dsn[len("postgres://"):]
if not dsn.startswith(("postgresql://", "postgresql+psycopg2://")):
    raise SystemExit("PostgreSQL authority URL is invalid")
lower_dsn = dsn.lower()
require_ssl = (os.environ.get("LINAS_WHATSAPP_REQUIRE_SSL") or "").strip().lower() in {
    "1", "true", "yes", "on"
}
sslmode = (os.environ.get("LINAS_WHATSAPP_DB_SSLMODE") or "").strip()
if require_ssl and "sslmode=" not in lower_dsn:
    raise SystemExit("PostgreSQL authority URL lacks required sslmode")
if sslmode and "sslmode=" not in lower_dsn:
    dsn += ("&" if "?" in dsn else "?") + "sslmode=" + sslmode

expected_columns = {
    "meta_asset_bindings": {
        "binding_id", "tenant_id", "channel", "asset_id", "page_id",
        "instagram_account_id", "app_key", "credential_id", "status", "generation",
        "created_at", "updated_at", "previous_binding_id", "page_name", "instagram_username",
        "authorized_meta_user_id_hash", "superseded_by_binding_id", "auth_flow",
        "webhook_subscription_status", "webhook_subscribed_fields", "webhook_subscription_error",
        "webhook_subscription_checked_at",
    },
    "meta_binding_credentials": {
        "credential_id", "binding_id", "sealed", "aad", "created_at", "archived_at",
    },
    "meta_oauth_states": {"nonce", "payload", "expires_at"},
    "meta_registry_audit_events": {
        "id", "timestamp", "event", "actor_id_hash", "tenant_id", "channel",
        "asset_id_hash", "app_key", "binding_id", "result",
    },
}
engine = create_engine(dsn, pool_pre_ping=True, future=True)
try:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            recovery, readonly, database, address, port = connection.execute(text(
                "SELECT pg_is_in_recovery(), current_setting('transaction_read_only'), "
                "current_database(), inet_server_addr()::text, inet_server_port()"
            )).one()
            if recovery or readonly != "off":
                raise SystemExit("PostgreSQL authority is not the writable primary")
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 0x4D45544152454731})
            schema_rows = connection.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name IN "
                "('meta_asset_bindings','meta_binding_credentials','meta_oauth_states',"
                "'meta_registry_audit_events')"
            )).all()
            observed_columns = {name: set() for name in expected_columns}
            for table_name, column_name in schema_rows:
                if table_name in observed_columns:
                    observed_columns[table_name].add(column_name)
            if observed_columns != expected_columns:
                raise SystemExit("PostgreSQL Meta registry table schema differs from the exact contract")

            bindings = {}
            for row in connection.execute(text(
                "SELECT binding_id, tenant_id, channel, asset_id, page_id, instagram_account_id, "
                "app_key, credential_id, status, generation, created_at, updated_at, "
                "previous_binding_id, page_name, instagram_username, authorized_meta_user_id_hash, "
                "superseded_by_binding_id, auth_flow, webhook_subscription_status, "
                "webhook_subscribed_fields, webhook_subscription_error, "
                "webhook_subscription_checked_at FROM meta_asset_bindings"
            )).mappings():
                fields = row["webhook_subscribed_fields"] or []
                if not isinstance(fields, list):
                    raise SystemExit("PostgreSQL Meta subscribed-fields shape is invalid")
                binding_id = str(row["binding_id"])
                bindings[binding_id] = {
                    "binding_id": binding_id,
                    "tenant_id": str(row["tenant_id"]),
                    "channel": str(row["channel"]),
                    "asset_id": str(row["asset_id"]),
                    "page_id": str(row["page_id"] or ""),
                    "instagram_account_id": str(row["instagram_account_id"] or ""),
                    "app_key": str(row["app_key"]),
                    "credential_id": str(row["credential_id"]),
                    "status": str(row["status"]),
                    "generation": int(row["generation"] or 1),
                    "created_at": float(row["created_at"] or 0),
                    "updated_at": float(row["updated_at"] or 0),
                    "previous_binding_id": str(row["previous_binding_id"] or ""),
                    "page_name": str(row["page_name"] or ""),
                    "instagram_username": str(row["instagram_username"] or ""),
                    "authorized_meta_user_id_hash": str(row["authorized_meta_user_id_hash"] or ""),
                    "superseded_by_binding_id": str(row["superseded_by_binding_id"] or ""),
                    "auth_flow": str(row["auth_flow"] or "facebook_login"),
                    "webhook_subscription_status": str(row["webhook_subscription_status"] or "unknown"),
                    "webhook_subscribed_fields": list(fields),
                    "webhook_subscription_error": str(row["webhook_subscription_error"] or ""),
                    "webhook_subscription_checked_at": float(row["webhook_subscription_checked_at"] or 0),
                }

            credentials = {}
            for row in connection.execute(text(
                "SELECT credential_id, binding_id, sealed, aad, created_at, archived_at "
                "FROM meta_binding_credentials"
            )).mappings():
                credential_id = str(row["credential_id"])
                credentials[credential_id] = {
                    "binding_id": str(row["binding_id"]),
                    "aad": str(row["aad"]),
                    "sealed": str(row["sealed"]),
                    "created_at": float(row["created_at"] or 0),
                    "archived_at": float(row["archived_at"] or 0),
                }

            oauth_states = {}
            for row in connection.execute(text(
                "SELECT nonce, payload, expires_at FROM meta_oauth_states"
            )).mappings():
                payload = dict(row["payload"] or {})
                if "expires_at" not in payload:
                    payload["expires_at"] = float(row["expires_at"] or 0)
                oauth_states[str(row["nonce"])] = payload

            audit_events = []
            for row in connection.execute(text(
                "SELECT id, timestamp, event, actor_id_hash, tenant_id, channel, asset_id_hash, "
                "app_key, binding_id, result FROM meta_registry_audit_events"
            )).mappings():
                audit_events.append({
                    "id": str(row["id"]),
                    "timestamp": float(row["timestamp"] or 0),
                    "event": str(row["event"]),
                    "actor_id_hash": str(row["actor_id_hash"] or ""),
                    "tenant_id": str(row["tenant_id"] or ""),
                    "channel": str(row["channel"] or ""),
                    "asset_id_hash": str(row["asset_id_hash"] or ""),
                    "app_key": str(row["app_key"] or ""),
                    "binding_id": str(row["binding_id"] or ""),
                    "result": str(row["result"] or "ok"),
                })
finally:
    engine.dispose()

state = {
    "schema_version": 1,
    "bindings": bindings,
    "credentials": credentials,
    "oauth_states": oauth_states,
}
for key, binding in bindings.items():
    if binding.get("binding_id") != key:
        raise SystemExit("PostgreSQL Meta binding primary-key invariant failed")
    credential = credentials.get(binding.get("credential_id"))
    # Exact data-deletion/deauthorization intentionally leaves a disconnected
    # binding tombstone after removing its credential. Every other lifecycle
    # state still requires the referenced credential to exist.
    if credential is None and binding.get("status") != "disconnected":
        raise SystemExit("PostgreSQL Meta binding credential invariant failed")
    if credential is not None and credential.get("binding_id") != key:
        raise SystemExit("PostgreSQL Meta binding credential owner invariant failed")
for credential in credentials.values():
    if credential.get("binding_id") not in bindings or not credential.get("sealed", "").startswith("v1."):
        raise SystemExit("PostgreSQL Meta credential invariant failed")
audit_events.sort(key=lambda item: item["id"])
snapshot = {"format_version": 1, "state": state, "audit_events": audit_events}
identity = digest({"database": database, "address": address, "port": port})
print(json.dumps({
    "pg_identity_sha256": identity,
    "state_sha256": digest(state),
    "tables_sha256": digest(snapshot),
    "binding_count": len(bindings),
    "credential_count": len(credentials),
    "oauth_count": len(oauth_states),
    "audit_count": len(audit_events),
}, separators=(",", ":"), sort_keys=True))
"""


def _remove_private_tree(
    root: Path,
    *,
    expected_parent: Path,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> None:
    if root.parent != expected_parent or root == expected_parent:
        raise RuntimeError("private bootstrap cleanup path is outside its exact parent")
    if not root.exists() and not root.is_symlink():
        return

    def remove(directory: Path) -> None:
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise PermissionError("private bootstrap cleanup directory is unsafe")
        for entry in os.scandir(directory):
            path = Path(entry.path)
            observed = entry.stat(follow_symlinks=False)
            if observed.st_uid != expected_uid or observed.st_gid != expected_gid:
                raise PermissionError("private bootstrap cleanup object is unsafe")
            if stat.S_ISDIR(observed.st_mode) and not stat.S_ISLNK(observed.st_mode):
                remove(path)
            elif stat.S_ISREG(observed.st_mode) or stat.S_ISLNK(observed.st_mode):
                path.unlink()
                _fsync_dir(directory)
            else:
                raise PermissionError("private bootstrap cleanup contains a special object")
        directory.rmdir()
        _fsync_dir(directory.parent)

    remove(root)


def _fsync_private_tree(root: Path) -> None:
    directories: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory = Path(current)
        directories.append(directory)
        for name in filenames:
            path = directory / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise RuntimeError("bootstrap probe tree contains an unsafe object")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        for name in dirnames:
            info = (directory / name).lstat()
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError("bootstrap probe tree contains an unsafe link")
    for directory in reversed(directories):
        _fsync_dir(directory)


def _assert_no_probe_bytecode(root: Path) -> None:
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            raise RuntimeError("hash-locked PostgreSQL probe contains forbidden Python bytecode")


def _probe_authority_payload(runtime_authority: dict[str, Any]) -> dict[str, Any]:
    shared = runtime_authority["shared"]
    return {
        "schema": 1,
        "runtime_shared_sha256": runtime_authority["shared_sha256"],
        "runtime_plan_sha256": shared["plan_sha256"],
        "runtime_cluster_receipt_sha256": shared["cluster_receipt_sha256"],
        "manifest_sha256": shared["manifest_sha256"],
        "wheelhouse_archive_sha256": shared["wheelhouse_archive_sha256"],
        "wheelhouse_tree_sha256": shared["wheelhouse_tree_sha256"],
        "wheelhouse_file_count": shared["wheelhouse_file_count"],
        "wheelhouse_total_size": shared["wheelhouse_total_size"],
        "requirements_lock_sha256": shared["requirements_lock_sha256"],
    }


def _assert_probe_environment(
    root: Path,
    runtime_authority: dict[str, Any],
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> Path:
    _secure_authority_dir(
        root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if {entry.name for entry in os.scandir(root)} != {
        "probe-authority.json",
        "probe-env",
        "wheels",
    }:
        raise RuntimeError("PostgreSQL probe root has an incomplete or unknown object")
    proof, _ = _read_authority_json(
        root / "probe-authority.json",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    expected = _probe_authority_payload(runtime_authority)
    if set(proof) != set(expected) | {
        "probe_tree_sha256",
        "probe_file_count",
        "probe_total_size",
    } or any(proof.get(key) != value for key, value in expected.items()):
        raise RuntimeError("PostgreSQL probe authority differs from the runtime plan")
    wheels_sha, wheels_count, wheels_size, _ = _release_tree_evidence(
        root / "wheels",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if (wheels_sha, wheels_count, wheels_size) != (
        expected["wheelhouse_tree_sha256"],
        expected["wheelhouse_file_count"],
        expected["wheelhouse_total_size"],
    ):
        raise RuntimeError("extracted PostgreSQL probe wheelhouse differs from authority")
    probe_sha, probe_count, probe_size, _ = _release_tree_evidence(
        root / "probe-env",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if (probe_sha, probe_count, probe_size) != (
        proof.get("probe_tree_sha256"),
        proof.get("probe_file_count"),
        proof.get("probe_total_size"),
    ):
        raise RuntimeError("installed PostgreSQL probe environment changed")
    _assert_no_probe_bytecode(root)
    site_packages = root / "probe-env/lib/python3.13/site-packages"
    if not site_packages.is_dir() or site_packages.is_symlink():
        raise RuntimeError("hash-locked PostgreSQL probe site-packages is missing")
    return site_packages


def _prepare_probe_environment(
    root: Path,
    runtime_authority: dict[str, Any],
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> Path:
    proof = root / "probe-authority.json"
    if proof.exists() or proof.is_symlink():
        return _assert_probe_environment(
            root,
            runtime_authority,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    if root.exists() or root.is_symlink():
        _remove_private_tree(
            root,
            expected_parent=root.parent,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    root.mkdir(mode=0o700)
    os.chown(root, expected_uid, expected_gid)
    os.chmod(root, 0o700)
    _fsync_dir(root.parent)
    control_root = Path(str(runtime_authority["control_root"]))
    authority_root = Path(str(runtime_authority["authority_root"]))
    from scripts.ha import release_artifact_contract as release

    shared = runtime_authority["shared"]
    release.extract_archive(
        authority_root / "wheelhouse.tar",
        root / "wheels",
        str(shared["wheelhouse_archive_sha256"]),
        str(shared["wheelhouse_tree_sha256"]),
    )
    environment = {
        "HOME": str(root),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "PIP_CONFIG_FILE": "/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_CACHE_DIR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    venv_root = root / "probe-env"
    result = subprocess.run(
        [str(SYSTEM_PYTHON), "-B", "-I", "-m", "venv", "--without-pip", "--copies", str(venv_root)],
        env=environment,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("isolated PostgreSQL probe environment creation failed")
    os.chown(venv_root, expected_uid, expected_gid)
    os.chmod(venv_root, 0o700)
    lib64 = venv_root / "lib64"
    if lib64.is_symlink() and os.readlink(lib64) == "lib":
        lib64.unlink()
        _fsync_dir(venv_root)
    site_packages = venv_root / "lib/python3.13/site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(SYSTEM_PYTHON),
            "-B",
            "-I",
            "-m",
            "pip",
            "--isolated",
            "install",
            "--no-index",
            "--no-cache-dir",
            "--find-links",
            str(root / "wheels"),
            "--require-hashes",
            "--only-binary=:all:",
            "--no-compile",
            "--target",
            str(site_packages),
            "-r",
            str(control_root / "requirements.lock"),
        ],
        env=environment,
        capture_output=True,
        timeout=600,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("hash-locked PostgreSQL probe dependency installation failed")
    _assert_no_probe_bytecode(root)
    _fsync_private_tree(root)
    probe_sha, probe_count, probe_size, _ = _release_tree_evidence(
        venv_root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    payload = {
        **_probe_authority_payload(runtime_authority),
        "probe_tree_sha256": probe_sha,
        "probe_file_count": probe_count,
        "probe_total_size": probe_size,
    }
    _atomic_write(proof, _canonical(payload) + b"\n", no_replace=True)
    return _assert_probe_environment(
        root,
        runtime_authority,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )


def _pg_probe(
    values: dict[str, str],
    runtime_authority: dict[str, Any],
    *,
    probe_root: Path | None = None,
) -> dict[str, Any]:
    primary = values.get("LINAS_WHATSAPP_DATABASE_URL", "").strip()
    fallback = values.get("DATABASE_URL", "").strip()
    if primary and fallback and primary != fallback:
        raise RuntimeError("canonical environment contains conflicting PostgreSQL DSNs")
    dsn = primary or fallback
    if not dsn.startswith(("postgres://", "postgresql://", "postgresql+psycopg2://")):
        raise RuntimeError("canonical environment has no explicit PostgreSQL DSN")
    ephemeral = probe_root is None
    if probe_root is None:
        probe_root = Path(tempfile.mkdtemp(prefix=".bootstrap-pg-probe.", dir=STATE_ROOT))
        os.chmod(probe_root, 0o700)
        _fsync_dir(STATE_ROOT)
        # The builder requires an absent destination so the temporary root is
        # removed before its first durable publication.
        probe_root.rmdir()
    site_packages = _prepare_probe_environment(probe_root, runtime_authority)
    child_env = {
        "HOME": str(probe_root),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LINAS_WHATSAPP_DATABASE_URL": dsn,
        "DATABASE_URL": dsn,
        "META_REGISTRY_BACKEND": "postgres",
    }
    for key in ("LINAS_WHATSAPP_REQUIRE_SSL", "LINAS_WHATSAPP_DB_SSLMODE"):
        value = values.get(key)
        if value is None:
            continue
        else:
            child_env[key] = value
    runner = (
        "import sys;sys.path.insert(0,sys.argv[1]);exec(compile(sys.stdin.read(),'<authenticated-pg-probe>','exec'))"
    )
    try:
        result = subprocess.run(
            [str(SYSTEM_PYTHON), "-B", "-I", "-S", "-c", runner, str(site_packages)],
            input=PG_PROBE,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("authoritative PostgreSQL Meta registry probe failed")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise RuntimeError("PostgreSQL probe returned an invalid result")
        _assert_probe_environment(probe_root, runtime_authority)
        return payload
    finally:
        if ephemeral and probe_root.exists():
            _remove_private_tree(probe_root, expected_parent=STATE_ROOT)


def _service_state(unit: str) -> dict[str, str]:
    return {
        "enabled": _run(["systemctl", "is-enabled", unit], check=False).stdout.strip() or "not-found",
        "active": _run(["systemctl", "is-active", unit], check=False).stdout.strip() or "unknown",
    }


def _assert_durable_worker_preconditions(
    values: dict[str, str],
    states: dict[str, dict[str, str]],
) -> None:
    expected_units = {API_UNIT, *WORKER_UNITS}
    if set(states) != expected_units:
        raise RuntimeError("canonical API/worker service membership is incomplete")
    redis_url = values.get("REDIS_URL") or values.get("LINAS_REDIS_URL")
    durable_flag = values.get("LINAS_REQUIRE_REDIS") or values.get("LINAS_ENABLE_DURABLE_QUEUES")
    if not redis_url or str(durable_flag or "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("all four production queue workers require the durable Redis contract")
    for unit in (API_UNIT, *WORKER_UNITS):
        state = states[unit]
        if state.get("active") != "active" or state.get("enabled") != "enabled":
            raise RuntimeError(f"bootstrap requires every canonical API/worker active and enabled: {unit}")


def _port_listening(port: int) -> bool:
    output = _run(["ss", "-H", "-ltn"], check=False).stdout
    return any(re.search(rf"(^|:)({port})$", line.split()[3]) for line in output.splitlines() if len(line.split()) >= 4)


def _node_probe(
    node_id: str,
    expected_sha: str,
    *,
    current_tx_id: str = "",
    current_plan_sha256: str = "",
) -> dict[str, Any]:
    _require_root()
    runtime_authority = _runtime_authority(node_id)
    _assert_identity(node_id)
    _assert_repo(expected_sha)
    if node_id == "node01" and (COORDINATOR_PATH.exists() or COORDINATOR_PATH.is_symlink()):
        coordinator, _ = _read_current_coordinator_journal()
        if (
            not current_tx_id
            or coordinator.get("tx_id") != current_tx_id
            or coordinator.get("plan_sha256") != current_plan_sha256
        ):
            raise RuntimeError("an interrupted bootstrap coordinator decision requires confirmed recovery")
    if ACTIVE_PATH.exists() or ACTIVE_PATH.is_symlink():
        active_payload, _ = _read_regular_any_owner(ACTIVE_PATH)
        active = json.loads(active_payload)
        if (
            not current_tx_id
            or active.get("tx_id") != current_tx_id
            or active.get("plan_sha256") != current_plan_sha256
            or active.get("node_id") != node_id
        ):
            raise RuntimeError("a Meta HA bootstrap transaction is already active")
    if COMMITTED_PROOF_PATH.exists() or COMMITTED_PROOF_PATH.is_symlink():
        raise RuntimeError("one-time Meta HA bootstrap already has a committed proof")
    if SYNC_JOURNAL.exists() or SYNC_JOURNAL.is_symlink() or SYNC_BACKUP.exists() or SYNC_BACKUP.is_symlink():
        raise RuntimeError("a Meta environment synchronization transaction is active")
    if (
        DEPLOY_ACTIVE.exists()
        or DEPLOY_ACTIVE.is_symlink()
        or DEPLOY_NODE_ACTIVE.exists()
        or DEPLOY_NODE_ACTIVE.is_symlink()
    ):
        raise RuntimeError("an interrupted HA release transaction requires confirmed recovery")
    if (
        PYTHON_RUNTIME_PROVISION_ACTIVE.exists()
        or PYTHON_RUNTIME_PROVISION_ACTIVE.is_symlink()
        or PYTHON_RUNTIME_PROVISION_COORDINATOR.exists()
        or PYTHON_RUNTIME_PROVISION_COORDINATOR.is_symlink()
    ):
        raise RuntimeError("a Python runtime provisioning transaction requires confirmed recovery")
    if CONTROLLED_FAILOVER_ACTIVE.exists() or CONTROLLED_FAILOVER_ACTIVE.is_symlink():
        raise RuntimeError("a controlled Meta failover evidence transaction is active")
    if REGISTRY_NFS_RETIRE_ACTIVE.exists() or REGISTRY_NFS_RETIRE_ACTIVE.is_symlink():
        raise RuntimeError("a Meta registry NFS retirement transaction is active")
    if (
        PERSISTENT_MARKER.exists()
        or PERSISTENT_MARKER.is_symlink()
        or VOLATILE_MARKER.exists()
        or VOLATILE_MARKER.is_symlink()
    ):
        raise RuntimeError("pre-existing maintenance requires recovery, not bootstrap")
    env_payload, env_info = _read_regular_any_owner(ENV_PATH)
    values = _parse_env(env_payload)
    _assert_no_execution_env_injection(values)
    pg = _pg_probe(values, runtime_authority)
    legacy_payload = b""
    legacy_info: os.stat_result | None = None
    if node_id == "node01":
        if (
            LEGACY_RETIREMENT_MARKER.exists()
            or LEGACY_RETIREMENT_MARKER.is_symlink()
            or LEGACY_RETIREMENT_GUARD.exists()
            or LEGACY_RETIREMENT_GUARD.is_symlink()
        ):
            raise RuntimeError("node01 legacy retirement state already exists before one-time bootstrap")
        legacy_payload, legacy_info = _read_regular_any_owner(LEGACY_UNIT)
        if not _port_listening(8000):
            raise RuntimeError("node01 legacy :8000 observation changed before bootstrap")
    else:
        if (
            LEGACY_UNIT.exists()
            or LEGACY_UNIT.is_symlink()
            or LEGACY_RETIREMENT_MARKER.exists()
            or LEGACY_RETIREMENT_MARKER.is_symlink()
            or LEGACY_RETIREMENT_GUARD.exists()
            or LEGACY_RETIREMENT_GUARD.is_symlink()
            or _port_listening(8000)
        ):
            raise RuntimeError("node02 unexpectedly has the node01-only legacy runtime")
    canonical_services = {unit: _service_state(unit) for unit in (API_UNIT, *WORKER_UNITS)}
    _assert_durable_worker_preconditions(values, canonical_services)
    _assert_process_contract(node_id, require_enabled=True, require_bootstrapped_contract=False)
    live_units = _live_unit_contract()
    target_units = _target_unit_contract(runtime_authority)
    repo_bytecode = _repo_bytecode_manifest()
    git_metadata = _git_metadata_evidence()
    nested_runtime = _nested.probe_evidence(REPO_DIR)
    return {
        "node_id": node_id,
        "hostname": FIXED_NODES[node_id]["hostname"],
        "public_ip": FIXED_NODES[node_id]["public_ip"],
        "private_ip": FIXED_NODES[node_id]["private_ip"],
        "peer_ip": FIXED_NODES[node_id]["peer_ip"],
        "previous_sha": expected_sha,
        "runtime_authority": runtime_authority,
        "env": {
            "sha256": _digest_bytes(env_payload),
            "uid": env_info.st_uid,
            "gid": env_info.st_gid,
            "mode": stat.S_IMODE(env_info.st_mode),
            "size": len(env_payload),
        },
        "historical_env": _historical_env_manifest(expected_sha),
        "pg": pg,
        "canonical_services": canonical_services,
        "live_units": live_units,
        "target_units": target_units,
        "repo_bytecode": repo_bytecode,
        "nested_runtime": nested_runtime,
        "git_metadata": git_metadata,
        "legacy": (
            {
                "sha256": _digest_bytes(legacy_payload),
                "uid": legacy_info.st_uid if legacy_info else -1,
                "gid": legacy_info.st_gid if legacy_info else -1,
                "mode": stat.S_IMODE(legacy_info.st_mode) if legacy_info else -1,
                "state": _service_state("linas_ai_bot.service"),
                "port_8000": True,
                "retirement_guard_sha256": _digest_bytes(LEGACY_RETIREMENT_GUARD_BYTES),
                "retirement_marker": str(LEGACY_RETIREMENT_MARKER),
            }
            if node_id == "node01"
            else None
        ),
    }


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is None:
        raise RuntimeError(f"{label} is not an exact UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RuntimeError(f"{label} is not an exact UTC timestamp") from exc
    return parsed.astimezone(UTC)


def _validate_lb_ready_projection(projection: Any, expected_ready_sha256: str) -> dict[str, Any]:
    if not isinstance(projection, dict):
        raise RuntimeError("DigitalOcean ready attestation has an incomplete or unknown full projection")
    if _digest(projection) != expected_ready_sha256:
        raise RuntimeError("DigitalOcean ready attestation projection digest changed")
    _lb_contract.validate_ready_projection_values(projection)
    return projection


def _validate_lb_ready_attestation(payload: Any, expected_ready_sha256: str) -> str:
    expected_keys = {
        "schema",
        "load_balancer_id",
        "observed_at",
        "transaction_before_sha256",
        "ready_mutable_sha256",
        "ready_projection",
        "health_check",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise RuntimeError("DigitalOcean ready attestation closed schema is invalid")
    if payload.get("schema") != LB_READY_ATTESTATION_SCHEMA or payload.get("load_balancer_id") != LB_ID:
        raise RuntimeError("DigitalOcean ready attestation identity is invalid")
    _validate_digest(expected_ready_sha256, "DigitalOcean ready mutable projection")
    if expected_ready_sha256 == "0" * 64 or payload.get("ready_mutable_sha256") != expected_ready_sha256:
        raise RuntimeError("DigitalOcean ready attestation names an unauthorized projection digest")
    projection = _validate_lb_ready_projection(payload.get("ready_projection"), expected_ready_sha256)
    if payload.get("health_check") != LB_HEALTH_CONTRACT or payload.get("health_check") != projection["health_check"]:
        raise RuntimeError("DigitalOcean ready attestation health projection changed")
    before = payload.get("transaction_before_sha256")
    if before is not None:
        _validate_digest(str(before), "DigitalOcean ready attestation prior projection")
        if before == "0" * 64:
            raise RuntimeError("DigitalOcean ready attestation prior projection is invalid")
    observed = _parse_utc(payload.get("observed_at"), "DigitalOcean ready attestation observation")
    now = datetime.now(UTC)
    if observed > now + timedelta(seconds=30) or (now - observed).total_seconds() > 300:
        raise RuntimeError("DigitalOcean ready attestation is not fresh enough for bootstrap")
    return str(payload["observed_at"])


def _lb_attestation_install_confirmation(attestation_sha256: str, ready_sha256: str) -> str:
    _validate_digest(attestation_sha256, "DigitalOcean ready attestation artifact")
    _validate_digest(ready_sha256, "DigitalOcean ready mutable projection")
    return f"INSTALL_BOOTSTRAP_LB_READY_{attestation_sha256[:16].upper()}_{ready_sha256[:16].upper()}"


def _install_lb_ready_attestation(
    expected_attestation_sha256: str,
    expected_ready_sha256: str,
    confirm: str,
) -> None:
    _require_root()
    _assert_identity("node01")
    _validate_digest(expected_attestation_sha256, "DigitalOcean ready attestation artifact")
    _validate_digest(expected_ready_sha256, "DigitalOcean ready mutable projection")
    if expected_attestation_sha256 == "0" * 64 or expected_ready_sha256 == "0" * 64:
        raise RuntimeError("all-zero DigitalOcean attestation digests are never authority")
    if confirm != _lb_attestation_install_confirmation(expected_attestation_sha256, expected_ready_sha256):
        raise PermissionError("exact bootstrap LB attestation installation confirmation is missing")
    for collision in (
        ACTIVE_PATH,
        COORDINATOR_PATH,
        SYNC_JOURNAL,
        SYNC_BACKUP,
        DEPLOY_ACTIVE,
        DEPLOY_NODE_ACTIVE,
        PYTHON_RUNTIME_PROVISION_ACTIVE,
        PYTHON_RUNTIME_PROVISION_COORDINATOR,
        CONTROLLED_FAILOVER_ACTIVE,
        REGISTRY_NFS_RETIRE_ACTIVE,
        PERSISTENT_MARKER,
        VOLATILE_MARKER,
    ):
        if collision.exists() or collision.is_symlink():
            raise RuntimeError("cannot install bootstrap LB attestation during another maintenance transaction")
    raw = sys.stdin.buffer.read(131_073)
    if not raw or len(raw) > 131_072 or sys.stdin.buffer.read(1):
        raise RuntimeError("DigitalOcean ready attestation input size is invalid")
    if _digest_bytes(raw) != expected_attestation_sha256:
        raise RuntimeError("DigitalOcean ready attestation artifact digest changed")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("DigitalOcean ready attestation input is invalid JSON") from exc
    if raw != _canonical(payload) + b"\n":
        raise RuntimeError("DigitalOcean ready attestation bytes are not canonical")
    _validate_lb_ready_attestation(payload, expected_ready_sha256)
    _secure_dir(STATE_ROOT, create=True)
    if LB_BOOTSTRAP_ATTESTATION_PATH.exists() or LB_BOOTSTRAP_ATTESTATION_PATH.is_symlink():
        _secure_regular(LB_BOOTSTRAP_ATTESTATION_PATH)
    _atomic_write(LB_BOOTSTRAP_ATTESTATION_PATH, raw)
    _secure_regular(LB_BOOTSTRAP_ATTESTATION_PATH)
    installed, _ = _read_regular_any_owner(LB_BOOTSTRAP_ATTESTATION_PATH)
    if installed != raw:
        raise RuntimeError("installed DigitalOcean ready attestation changed")
    print(f"lb_ready_attestation={LB_BOOTSTRAP_ATTESTATION_PATH}")
    print(f"lb_attestation_sha256={expected_attestation_sha256}")
    print(f"lb_ready_projection_sha256={expected_ready_sha256}")


def _lb_owner_attestation(
    path: Path,
    expected_attestation_sha256: str,
    expected_ready_sha256: str,
) -> dict[str, Any]:
    """Consume one exact protected provider observation without a prod token."""

    if path != LB_BOOTSTRAP_ATTESTATION_PATH or path.resolve(strict=True) != LB_BOOTSTRAP_ATTESTATION_PATH:
        raise PermissionError("bootstrap LB attestation path is not the canonical protected path")
    _secure_dir(STATE_ROOT)
    _secure_regular(path)
    raw, _ = _read_regular_any_owner(path)
    _validate_digest(expected_attestation_sha256, "DigitalOcean ready attestation artifact")
    if expected_attestation_sha256 == "0" * 64 or _digest_bytes(raw) != expected_attestation_sha256:
        raise RuntimeError("DigitalOcean ready attestation artifact digest changed")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("DigitalOcean ready attestation is invalid JSON") from exc
    if raw != _canonical(payload) + b"\n":
        raise RuntimeError("DigitalOcean ready attestation bytes are not canonical")
    observed_at = _validate_lb_ready_attestation(payload, expected_ready_sha256)
    check_interval = LB_HEALTH_CONTRACT["check_interval_seconds"]
    unhealthy_threshold = LB_HEALTH_CONTRACT["unhealthy_threshold"]
    if (
        not isinstance(check_interval, int)
        or isinstance(check_interval, bool)
        or not isinstance(unhealthy_threshold, int)
        or isinstance(unhealthy_threshold, bool)
    ):
        raise RuntimeError("DigitalOcean health timing contract is invalid")
    minimum_drain = check_interval * unhealthy_threshold + 10
    configured_drain = int(CONTRACT_KEYS["META_HA_LB_DRAIN_SECONDS"])
    if configured_drain < minimum_drain or not 30 <= configured_drain <= 300:
        raise RuntimeError("configured HA drain does not safely exceed the attested LB unhealthy window")
    return {
        "owner_attested_ready_mutable_sha256": expected_ready_sha256,
        "attestation_sha256": expected_attestation_sha256,
        "observed_at": observed_at,
        "id": LB_ID,
        "name": LB_NAME,
        "ip": LB_IP,
        "droplet_ids": LB_DROPLETS,
        "health_check": LB_HEALTH_CONTRACT,
        "minimum_drain_seconds": minimum_drain,
    }


def _helper_source() -> tuple[bytes, str]:
    path = Path(__file__).resolve()
    source = path.read_bytes()
    return source, _digest_bytes(source)


def _remote(peer: str, helper_source: bytes, helper_sha: str, args: list[str]) -> str:
    authority = _runtime_authority("node01")
    if _digest_bytes(helper_source) != helper_sha or helper_sha != _digest_bytes(Path(__file__).read_bytes()):
        raise RuntimeError("remote bootstrap helper authority changed")
    tx_root = Path(str(authority["authority_root"])).parent
    control_root = Path(str(authority["control_root"]))
    command = [
        "ssh",
        *SSH_OPTIONS,
        f"root@{peer}",
        "/usr/bin/env",
        "-i",
        "HOME=/root",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        "/usr/bin/python3",
        "-B",
        "-I",
        "-S",
        str(authority["launcher_path"]),
        "run-bootstrap",
        str(tx_root),
        str(control_root),
        str(authority["shared"]["plan_sha256"]),
        *args,
    ]
    result = subprocess.run(command, capture_output=True, timeout=900, check=False)
    if result.returncode:
        raise RuntimeError("peer bootstrap phase failed")
    return result.stdout.decode("utf-8", errors="strict")


def _assert_exact_helper(target_sha: str, source_sha: str) -> None:
    authority = _runtime_authority("node01")
    if authority["shared"]["qg_target_sha"] != target_sha:
        raise RuntimeError("bootstrap target differs from the authenticated QG control authority")
    helper = Path(str(authority["control_root"])) / HELPER_REPO_PATH
    if _digest_bytes(_read_authority_file(helper, limit=8 * 1024**2, mode=0o644)) != source_sha:
        raise RuntimeError("running bootstrap helper is not the authenticated QG control blob")


def _combined_plan(args: argparse.Namespace) -> tuple[dict[str, Any], bytes, str]:
    source, source_sha = _helper_source()
    node01 = _node_probe("node01", args.expected_node01_sha)
    node02_raw = _remote(
        FIXED_NODES["node01"]["peer_ip"],
        source,
        source_sha,
        ["node-probe", "--node-id", "node02", "--expected-sha", args.expected_node02_sha],
    )
    node02 = json.loads(node02_raw)
    if node01["runtime_authority"]["shared"] != node02["runtime_authority"]["shared"]:
        raise RuntimeError("nodes do not share one identical committed Python runtime authority")
    if node01["runtime_authority"]["shared"]["qg_target_sha"] != args.target_sha:
        raise RuntimeError("bootstrap target differs from the authenticated QG release authority")
    if node01["live_units"] != node02["live_units"]:
        raise RuntimeError("nodes do not share one identical rollback-safe canonical unit baseline")
    if node01["pg"] != node02["pg"]:
        raise RuntimeError("nodes do not observe one identical authoritative PostgreSQL registry")
    if node01["pg"]["state_sha256"] != args.expected_pg_state_sha256:
        raise RuntimeError("PostgreSQL Meta state differs from the owner-authorized digest")
    if _nested_evidence.portable_content_identity(
        node01["nested_runtime"]
    ) != _nested_evidence.portable_content_identity(node02["nested_runtime"]):
        raise RuntimeError("nodes do not share one identical nested runtime authority")
    lb = _lb_owner_attestation(
        args.lb_ready_attestation,
        args.expected_lb_attestation_sha256,
        args.expected_lb_ready_sha256,
    )
    plan = {
        "schema": 1,
        "target_sha": args.target_sha,
        "expected_pg_state_sha256": args.expected_pg_state_sha256,
        "lb": lb,
        "node01": node01,
        "node02": node02,
        "drain_seconds": 30,
        "credential_rotation_required": True,
    }
    return plan, source, source_sha


def _confirmation(plan_sha256: str) -> str:
    return f"BOOTSTRAP_META_HA_{plan_sha256[:16].upper()}_AND_ROTATE_EXPOSED_CREDENTIALS"


def _recovery_confirmation(tx_id: str, plan_sha256: str) -> str:
    return f"ROLLBACK_META_HA_{tx_id[:12].upper()}_{plan_sha256[:12].upper()}"


def _backup_dir(tx_id: str) -> Path:
    if not TX_RE.fullmatch(tx_id):
        raise ValueError("bootstrap transaction ID is invalid")
    return Path(f"/opt/.linasbot-meta-bootstrap-{tx_id}")


def _write_journal(backup: Path, payload: dict[str, Any]) -> None:
    _atomic_write(backup / "journal.json", _canonical(payload) + b"\n")


def _node_prepare(
    node_id: str,
    expected_sha: str,
    tx_id: str,
    plan_sha256: str,
    expected_probe_sha256: str,
) -> None:
    probe = _node_probe(
        node_id,
        expected_sha,
        current_tx_id=tx_id,
        current_plan_sha256=plan_sha256,
    )
    _validate_digest(expected_probe_sha256, "owner-authorized node probe")
    if _digest(probe) != expected_probe_sha256:
        raise RuntimeError("node state changed after the owner-authorized bootstrap plan")
    active_payload = _canonical({"schema": 1, "tx_id": tx_id, "plan_sha256": plan_sha256, "node_id": node_id}) + b"\n"
    _secure_dir(STATE_ROOT, create=True)
    # Publish the exact transaction identity before creating any backup
    # artifact. A SIGKILL at every later prepare boundary is therefore
    # discoverable and the same prepare request can finish idempotently.
    if ACTIVE_PATH.exists() or ACTIVE_PATH.is_symlink():
        _secure_regular(ACTIVE_PATH)
        existing_active, _ = _read_regular_any_owner(ACTIVE_PATH)
        if existing_active != active_payload:
            raise RuntimeError("bootstrap active sentinel belongs to another prepare")
    else:
        _atomic_write(ACTIVE_PATH, active_payload, no_replace=True)
    backup = _backup_dir(tx_id)
    if backup.exists() or backup.is_symlink():
        _secure_dir(backup)
    else:
        backup.mkdir(mode=0o700)
        os.chown(backup, 0, 0)
    _secure_dir(backup)
    if backup.stat().st_dev != REPO_DIR.stat().st_dev:
        raise RuntimeError("bootstrap backup is not an atomic /opt sibling")
    (backup / "historical-env").mkdir(mode=0o700, exist_ok=True)
    _secure_dir(backup / "historical-env")

    def write_or_verify(path: Path, payload: bytes) -> None:
        if path.exists() or path.is_symlink():
            _secure_regular(path)
            current, _ = _read_regular_any_owner(path)
            if current != payload:
                raise RuntimeError(f"partial bootstrap prepare artifact changed: {path.name}")
        else:
            _atomic_write(path, payload, no_replace=True)

    env_payload, _ = _read_regular_any_owner(ENV_PATH)
    write_or_verify(backup / "env.before", env_payload)
    if node_id == "node01":
        legacy_payload, _ = _read_regular_any_owner(LEGACY_UNIT)
        write_or_verify(backup / "linas_ai_bot.service.before", legacy_payload)
    _backup_git_metadata(backup, probe["git_metadata"])
    write_or_verify(backup / "probe.before.json", _canonical(probe) + b"\n")
    _nested.publish_authority(REPO_DIR, backup, probe["nested_runtime"], tx_id)
    _backup_live_units(backup, probe["live_units"])
    _prepare_probe_environment(backup / "runtime-probe", probe["runtime_authority"])
    prepared = {
        "schema": 1,
        "tx_id": tx_id,
        "status": "prepared",
        "plan_sha256": plan_sha256,
    }
    journal_path = backup / "journal.json"
    if journal_path.exists() or journal_path.is_symlink():
        _secure_regular(journal_path)
        current_journal, _ = _read_regular_any_owner(journal_path)
        if current_journal != _canonical(prepared) + b"\n":
            raise RuntimeError("partial bootstrap prepare journal changed")
    else:
        _write_journal(backup, prepared)


def _node_abort_prepare(tx_id: str, plan_sha256: str) -> None:
    backup = _backup_dir(tx_id)
    abort_receipt = backup / "abort.complete.json"
    expected_abort = {
        "schema": 1,
        "tx_id": tx_id,
        "plan_sha256": plan_sha256,
        "status": "aborted_before_drain",
    }
    active_exists = ACTIVE_PATH.exists() or ACTIVE_PATH.is_symlink()
    if not active_exists:
        if not backup.exists() and not backup.is_symlink():
            return
        _secure_dir(backup)
        journal_path = backup / "journal.json"
        if journal_path.exists() or journal_path.is_symlink():
            _secure_regular(journal_path)
            journal_payload, _ = _read_regular_any_owner(journal_path)
            journal = json.loads(journal_payload)
            if (
                journal.get("tx_id") == tx_id
                and journal.get("plan_sha256") == plan_sha256
                and journal.get("status") == "aborted_before_drain"
            ):
                _secure_regular(abort_receipt)
                if json.loads(abort_receipt.read_text(encoding="utf-8")) != expected_abort:
                    raise RuntimeError("bootstrap prepare abort receipt is invalid")
                return
        raise RuntimeError("bootstrap prepare backup exists without a recoverable active sentinel")
    _secure_regular(ACTIVE_PATH)
    active_payload, _ = _read_regular_any_owner(ACTIVE_PATH)
    active = json.loads(active_payload)
    if active.get("tx_id") != tx_id or active.get("plan_sha256") != plan_sha256:
        raise RuntimeError("bootstrap active sentinel does not match prepare abort")
    if (
        PERSISTENT_MARKER.exists()
        or PERSISTENT_MARKER.is_symlink()
        or VOLATILE_MARKER.exists()
        or VOLATILE_MARKER.is_symlink()
        or BOOTSTRAP_RUNTIME_GUARD.exists()
        or BOOTSTRAP_RUNTIME_GUARD.is_symlink()
        or any(path.exists() or path.is_symlink() for path in BOOT_GUARDS)
        or not _port_listening(8003)
    ):
        raise RuntimeError("bootstrap prepare crossed the drain boundary")
    if backup.exists() or backup.is_symlink():
        _secure_dir(backup)
        _write_journal(
            backup,
            {
                "schema": 1,
                "tx_id": tx_id,
                "status": "aborted_before_drain",
                "plan_sha256": plan_sha256,
            },
        )
        if abort_receipt.exists() or abort_receipt.is_symlink():
            _secure_regular(abort_receipt)
            if json.loads(abort_receipt.read_text(encoding="utf-8")) != expected_abort:
                raise RuntimeError("bootstrap prepare abort receipt changed")
        else:
            _atomic_write(
                abort_receipt,
                _canonical(expected_abort) + b"\n",
                no_replace=True,
            )
        probe_root = backup / "runtime-probe"
        if probe_root.exists() or probe_root.is_symlink():
            _remove_private_tree(probe_root, expected_parent=backup)
    _unlink_durable(ACTIVE_PATH)


def _assert_active(tx_id: str, plan_sha256: str) -> Path:
    _secure_dir(STATE_ROOT)
    _secure_regular(ACTIVE_PATH)
    payload = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
    if payload.get("tx_id") != tx_id or payload.get("plan_sha256") != plan_sha256:
        raise RuntimeError("bootstrap active sentinel does not match this transaction")
    backup = _backup_dir(tx_id)
    _secure_dir(backup)
    _secure_regular(backup / "env.before")
    _secure_regular(backup / "probe.before.json")
    return backup


def _arm_marker(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _secure_regular(path)
    else:
        _atomic_write(path, b"meta-ha-bootstrap-maintenance\n", no_replace=True)


def _install_boot_guards(backup: Path) -> None:
    # bootstrap.active is durable before the coordinator crosses its first
    # mutation boundary.  Including it in each condition closes the otherwise
    # unsafe guard-published/maintenance-marker-not-yet-published reboot gap.
    _secure_regular(ACTIVE_PATH)
    for path in BOOT_GUARDS:
        path.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
        if path.exists() or path.is_symlink():
            current, _ = _read_regular_any_owner(path)
            if current != BOOT_GUARD:
                raise RuntimeError("unknown HA boot guard already exists")
        else:
            _atomic_write(path, BOOT_GUARD, mode=0o644, no_replace=True)
    _run(["systemctl", "daemon-reload"])
    _atomic_write(backup / "boot-guard.sha256", (_digest_bytes(BOOT_GUARD) + "\n").encode())


def _remove_boot_guards(backup: Path, *, require_quiesced: bool = True) -> None:
    expected = (backup / "boot-guard.sha256").read_text(encoding="ascii").strip()
    if expected != _digest_bytes(BOOT_GUARD):
        raise RuntimeError("boot guard proof changed")
    if require_quiesced:
        for unit in (API_UNIT, *WORKER_UNITS):
            if (
                _run(["systemctl", "is-active", unit], check=False).returncode == 0
                or _run(["systemctl", "is-enabled", unit], check=False).returncode == 0
            ):
                raise RuntimeError("canonical unit must be stopped and disabled before boot guard removal")
    elif BOOTSTRAP_RUNTIME_GUARD.exists() or BOOTSTRAP_RUNTIME_GUARD.is_symlink():
        raise RuntimeError("bootstrap runtime guard must be released before final drop-in cleanup")
    for path in BOOT_GUARDS:
        if path.exists() or path.is_symlink():
            payload, _ = _read_regular_any_owner(path)
            if payload != BOOT_GUARD:
                raise RuntimeError("HA boot guard changed")
            _unlink_durable(path)
    _run(["systemctl", "daemon-reload"])


def _assert_controlled_failover_guard_contract() -> None:
    """Prove both permanent drop-ins are exact and loaded.

    Controlled failover changes only one transaction-bound marker.  It never
    writes this multi-file systemd contract while production is serving.
    """

    if CONTROLLED_FAILOVER_RUNTIME_GUARD.exists() or CONTROLLED_FAILOVER_RUNTIME_GUARD.is_symlink():
        raise RuntimeError("controlled failover runtime guard unexpectedly exists during bootstrap")
    for path in CONTROLLED_FAILOVER_GUARDS:
        payload, info = _read_regular_any_owner(path)
        if (
            payload != CONTROLLED_FAILOVER_GUARD
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o644
            or info.st_nlink != 1
        ):
            raise RuntimeError("controlled failover static guard contract changed")
    for unit in (API_UNIT, *WORKER_UNITS):
        if _run(["systemctl", "show", unit, "--property=NeedDaemonReload", "--value"]).stdout.strip() != "no":
            raise RuntimeError("controlled failover static guard contract is not loaded")


def _install_controlled_failover_guard_contract() -> None:
    """Install permanent guards only while bootstrap already fails closed."""

    _secure_regular(ACTIVE_PATH)
    for unit in (API_UNIT, *WORKER_UNITS):
        if (
            _run(["systemctl", "is-active", unit], check=False).returncode == 0
            or _run(["systemctl", "is-enabled", unit], check=False).returncode == 0
        ):
            raise RuntimeError("canonical units must stay quiesced while installing failover guards")
    for path in CONTROLLED_FAILOVER_GUARDS:
        path.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
        parent = path.parent.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or stat.S_ISLNK(parent.st_mode)
            or parent.st_uid != 0
            or parent.st_gid != 0
            or stat.S_IMODE(parent.st_mode) & 0o022
        ):
            raise PermissionError("controlled failover drop-in directory is unsafe")
        if path.exists() or path.is_symlink():
            payload, info = _read_regular_any_owner(path)
            if (
                payload != CONTROLLED_FAILOVER_GUARD
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o644
                or info.st_nlink != 1
            ):
                raise RuntimeError("unknown controlled failover static guard exists")
        else:
            _atomic_write(path, CONTROLLED_FAILOVER_GUARD, mode=0o644, no_replace=True)
    _run(["systemctl", "daemon-reload"])
    _assert_controlled_failover_guard_contract()


def _assert_bootstrap_runtime_guard() -> None:
    payload, info = _read_regular_any_owner(BOOTSTRAP_RUNTIME_GUARD)
    if (
        payload != BOOTSTRAP_RUNTIME_GUARD_BYTES
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise RuntimeError("bootstrap runtime reboot guard changed")


def _arm_bootstrap_runtime_guard() -> None:
    if BOOTSTRAP_RUNTIME_GUARD.exists() or BOOTSTRAP_RUNTIME_GUARD.is_symlink():
        _assert_bootstrap_runtime_guard()
    else:
        _atomic_write(
            BOOTSTRAP_RUNTIME_GUARD,
            BOOTSTRAP_RUNTIME_GUARD_BYTES,
            no_replace=True,
        )


def _clear_bootstrap_runtime_guard() -> None:
    if BOOTSTRAP_RUNTIME_GUARD.exists() or BOOTSTRAP_RUNTIME_GUARD.is_symlink():
        _assert_bootstrap_runtime_guard()
        _unlink_durable(BOOTSTRAP_RUNTIME_GUARD)


def _install_nginx_override(backup: Path) -> None:
    original, original_info = _read_regular_any_owner(NGINX_CONFIG)
    if b"linasbot-meta-ha-bootstrap-readiness" in original:
        raise RuntimeError("unknown bootstrap nginx override already exists")
    _atomic_write(backup / "nginx.before", original)
    _atomic_write(
        backup / "nginx.before.meta.json",
        _canonical({"sha256": _digest_bytes(original), "mode": stat.S_IMODE(original_info.st_mode)}) + b"\n",
    )
    block = (
        b"    # linasbot-meta-ha-bootstrap-readiness\n"
        b"    location = /api/ready {\n"
        b"        default_type application/json;\n"
        b'        add_header Cache-Control "no-store" always;\n'
        b'        return 503 \'{"ok":false,"role":"readiness","checks":{"maintenance":{"ok":false}}}\';\n'
        b"    }\n\n"
    )
    candidate, count = re.subn(rb"(?m)^(server\s*\{\s*\n)", rb"\1" + block, original)
    if count < 1:
        raise RuntimeError("canonical nginx config has no server block")
    _atomic_write(NGINX_CONFIG, candidate, mode=0o644)
    if _run(["nginx", "-t"], check=False).returncode:
        _atomic_write(NGINX_CONFIG, original, mode=stat.S_IMODE(original_info.st_mode))
        raise RuntimeError("bootstrap nginx override validation failed")
    _run(["systemctl", "reload", "nginx"])


def _restore_nginx(backup: Path) -> None:
    _secure_regular(backup / "nginx.before")
    metadata = json.loads((backup / "nginx.before.meta.json").read_text(encoding="utf-8"))
    original = (backup / "nginx.before").read_bytes()
    if _digest_bytes(original) != metadata.get("sha256"):
        raise RuntimeError("nginx backup digest changed")
    _atomic_write(NGINX_CONFIG, original, mode=int(metadata["mode"]))
    _run(["nginx", "-t"])
    _run(["systemctl", "reload", "nginx"])


def _stop_canonical() -> None:
    for unit in reversed(WORKER_UNITS):
        _run(["systemctl", "stop", unit], check=False)
    _run(["systemctl", "stop", API_UNIT])
    for _ in range(30):
        if not _port_listening(8003):
            return
        time.sleep(1)
    raise RuntimeError("direct LB port 8003 did not close")


def _node_drain(tx_id: str, plan_sha256: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    active_payload, _ = _read_regular_any_owner(ACTIVE_PATH)
    active = json.loads(active_payload)
    probe_payload, _ = _read_regular_any_owner(backup / "probe.before.json")
    probe = json.loads(probe_payload)
    # Publish and load both pass-through guards before arming their durable
    # marker.  Once the marker is durable, every disable-prefix/reboot boundary
    # is blocked without interrupting the still-serving baseline beforehand.
    _install_boot_guards(backup)
    _arm_bootstrap_runtime_guard()
    _quiesce_and_disable_units(probe["canonical_services"])
    _arm_marker(PERSISTENT_MARKER)
    _arm_marker(VOLATILE_MARKER)
    _install_nginx_override(backup)
    _stop_canonical()
    if active.get("node_id") == "node01":
        # Retire the known legacy runtime as part of the first durable drain,
        # not later during env apply. Its exact prior state is already backed
        # up and rollback admission can restore it.
        _install_legacy_retirement()
    if _port_listening(8003):
        raise RuntimeError("direct LB port 8003 remains available while drained")
    _nested.apply_quarantine(REPO_DIR, backup, probe["nested_runtime"], tx_id)
    _write_journal(backup, {"schema": 1, "tx_id": tx_id, "status": "drained", "plan_sha256": plan_sha256})


def _transition_historical_env(
    entry: dict[str, Any],
    source: Path,
    destination: Path,
    *,
    source_owner: tuple[int, int],
    source_mode: int,
    target_owner: tuple[int, int],
    target_mode: int,
    direction: str,
) -> None:
    """Finish one rename+metadata transition from either durable side.

    rename(2), chown(2), and chmod(2) are distinct power-loss boundaries.  A
    replay may therefore find the exact file at the source, or at the
    destination with either exact owner pair and either exact mode.  No other
    source/destination or metadata combination is authorized.
    """

    source_exists = source.exists() or source.is_symlink()
    destination_exists = destination.exists() or destination.is_symlink()
    if source_exists == destination_exists:
        raise RuntimeError(f"historical environment {direction} location is ambiguous")
    current = source if source_exists else destination
    payload, info = _read_regular_any_owner(current)
    if _digest_bytes(payload) != entry["sha256"] or len(payload) != int(entry["size"]):
        raise RuntimeError(f"historical environment {direction} bytes changed")
    current_owner = (info.st_uid, info.st_gid)
    current_mode = stat.S_IMODE(info.st_mode)
    if source_exists:
        if current_owner != source_owner or current_mode != source_mode:
            raise RuntimeError(f"historical environment {direction} source metadata changed")
        if source.stat().st_dev != destination.parent.stat().st_dev:
            raise RuntimeError(f"historical environment {direction} would cross devices")
        os.rename(source, destination)
        # Persist either side of the atomic rename before beginning the
        # independently replayable metadata transition.
        _fsync_dir(source.parent)
        _fsync_dir(destination.parent)
    elif current_owner not in {source_owner, target_owner} or current_mode not in {
        source_mode,
        target_mode,
    }:
        raise RuntimeError(f"historical environment {direction} partial metadata is invalid")

    os.chown(destination, target_owner[0], target_owner[1], follow_symlinks=False)
    os.chmod(destination, target_mode, follow_symlinks=False)
    descriptor = os.open(
        destination,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise RuntimeError(f"historical environment {direction} target is unsafe")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    final_payload, final_info = _read_regular_any_owner(destination)
    if (
        _digest_bytes(final_payload) != entry["sha256"]
        or len(final_payload) != int(entry["size"])
        or (final_info.st_uid, final_info.st_gid) != target_owner
        or stat.S_IMODE(final_info.st_mode) != target_mode
    ):
        raise RuntimeError(f"historical environment {direction} target is not exact")
    if source.exists() or source.is_symlink():
        raise RuntimeError(f"historical environment {direction} retained both names")
    _fsync_dir(destination.parent)


def _move_historical(backup: Path, manifest: list[dict[str, Any]]) -> None:
    destination_root = backup / "historical-env"
    for entry in manifest:
        _transition_historical_env(
            entry,
            REPO_DIR / str(entry["name"]),
            destination_root / str(entry["name"]),
            source_owner=(int(entry["uid"]), int(entry["gid"])),
            source_mode=int(entry["mode"]),
            target_owner=(0, 0),
            target_mode=0o600,
            direction="archive",
        )


def _assert_legacy_retired(*, prove_manual_start_denied: bool = False) -> None:
    """Prove the old :8000 unit cannot be resurrected across a reboot."""

    _read_regular_any_owner(LEGACY_UNIT)
    marker_payload, _ = _read_regular_any_owner(LEGACY_RETIREMENT_MARKER)
    if marker_payload != b"legacy-linas-ai-bot-retired\n":
        raise RuntimeError("legacy retirement marker changed")
    guard_payload, guard_info = _read_regular_any_owner(LEGACY_RETIREMENT_GUARD)
    if (
        guard_payload != LEGACY_RETIREMENT_GUARD_BYTES
        or guard_info.st_uid != 0
        or guard_info.st_gid != 0
        or stat.S_IMODE(guard_info.st_mode) != 0o644
    ):
        raise RuntimeError("legacy retirement guard changed")
    if prove_manual_start_denied:
        # A disabled unit can still be manually started.  The persistent
        # ConditionPathExists guard must independently keep that attempt inert.
        _run(["systemctl", "start", "linas_ai_bot.service"], check=False)
        time.sleep(1)
    if (
        _run(["systemctl", "is-active", "linas_ai_bot.service"], check=False).returncode == 0
        or _run(["systemctl", "is-enabled", "linas_ai_bot.service"], check=False).returncode == 0
        or _port_listening(8000)
    ):
        raise RuntimeError("legacy runtime retirement verification failed")


def _install_legacy_retirement() -> None:
    _secure_regular(ACTIVE_PATH)
    # Disable and stop first.  A crash before either persistent retirement file
    # is published therefore still cannot resurrect this unit on the next boot.
    _run(["systemctl", "disable", "--now", "linas_ai_bot.service"])
    if (
        _run(["systemctl", "is-active", "linas_ai_bot.service"], check=False).returncode == 0
        or _run(["systemctl", "is-enabled", "linas_ai_bot.service"], check=False).returncode == 0
        or _port_listening(8000)
    ):
        raise RuntimeError("legacy runtime did not stop before persistent retirement")
    LEGACY_RETIREMENT_GUARD.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    parent_info = LEGACY_RETIREMENT_GUARD.parent.lstat()
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_ISLNK(parent_info.st_mode)
        or parent_info.st_uid != 0
        or parent_info.st_gid != 0
        or stat.S_IMODE(parent_info.st_mode) & 0o022
    ):
        raise PermissionError("legacy retirement drop-in directory is unsafe")
    if LEGACY_RETIREMENT_GUARD.exists() or LEGACY_RETIREMENT_GUARD.is_symlink():
        guard_payload, guard_info = _read_regular_any_owner(LEGACY_RETIREMENT_GUARD)
        if (
            guard_payload != LEGACY_RETIREMENT_GUARD_BYTES
            or guard_info.st_uid != 0
            or guard_info.st_gid != 0
            or stat.S_IMODE(guard_info.st_mode) != 0o644
        ):
            raise RuntimeError("partial legacy retirement guard changed")
    else:
        _atomic_write(
            LEGACY_RETIREMENT_GUARD,
            LEGACY_RETIREMENT_GUARD_BYTES,
            mode=0o644,
            no_replace=True,
        )
    _run(["systemctl", "daemon-reload"])
    if LEGACY_RETIREMENT_MARKER.exists() or LEGACY_RETIREMENT_MARKER.is_symlink():
        marker_payload, _ = _read_regular_any_owner(LEGACY_RETIREMENT_MARKER)
        if marker_payload != b"legacy-linas-ai-bot-retired\n":
            raise RuntimeError("partial legacy retirement marker changed")
    else:
        _atomic_write(
            LEGACY_RETIREMENT_MARKER,
            b"legacy-linas-ai-bot-retired\n",
            no_replace=True,
        )
    _assert_legacy_retired(prove_manual_start_denied=True)


def _remove_legacy_retirement_for_rollback() -> None:
    marker_exists = LEGACY_RETIREMENT_MARKER.exists() or LEGACY_RETIREMENT_MARKER.is_symlink()
    guard_exists = LEGACY_RETIREMENT_GUARD.exists() or LEGACY_RETIREMENT_GUARD.is_symlink()
    if not marker_exists and not guard_exists:
        return
    # Exact partial states are valid after SIGKILL at either publication
    # boundary.  Quiesce the unit first, validate every object that exists, then
    # remove the marker before its guard.  The caller restores prior state only
    # after the remainder of the node rollback has been proved.
    _run(["systemctl", "disable", "--now", "linas_ai_bot.service"], check=False)
    if _port_listening(8000):
        raise RuntimeError("legacy port 8000 remained active during retirement rollback")
    if marker_exists:
        marker_payload, _ = _read_regular_any_owner(LEGACY_RETIREMENT_MARKER)
        if marker_payload != b"legacy-linas-ai-bot-retired\n":
            raise RuntimeError("legacy retirement marker changed before rollback")
        _unlink_durable(LEGACY_RETIREMENT_MARKER)
    if guard_exists:
        guard_payload, guard_info = _read_regular_any_owner(LEGACY_RETIREMENT_GUARD)
        if (
            guard_payload != LEGACY_RETIREMENT_GUARD_BYTES
            or guard_info.st_uid != 0
            or guard_info.st_gid != 0
            or stat.S_IMODE(guard_info.st_mode) != 0o644
        ):
            raise RuntimeError("legacy retirement guard changed before rollback")
        _unlink_durable(LEGACY_RETIREMENT_GUARD)
    _run(["systemctl", "daemon-reload"])


def _restore_legacy_after_final_rollback(backup: Path) -> None:
    """Idempotently restore :8000 only after rollback is durably final."""

    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    legacy_before = (backup / "linas_ai_bot.service.before").read_bytes()
    current, _ = _read_regular_any_owner(LEGACY_UNIT)
    if current != legacy_before:
        raise RuntimeError("legacy unit changed before final rollback restoration")
    legacy_state = probe["legacy"]["state"]
    _remove_legacy_retirement_for_rollback()
    legacy_states = {"linas_ai_bot.service": legacy_state}
    _start_units_disabled(legacy_states)
    if legacy_state["active"] == "active" and not _port_listening(8000):
        raise RuntimeError("legacy final rollback did not restore port 8000")
    if legacy_state["active"] != "active" and _port_listening(8000):
        raise RuntimeError("legacy final rollback unexpectedly exposed port 8000")
    _enable_units_after_verification(legacy_states)
    active = _run(["systemctl", "is-active", "linas_ai_bot.service"], check=False).returncode == 0
    if active != (legacy_state["active"] == "active"):
        raise RuntimeError("legacy final rollback active state is not exact")


def _node_apply(node_id: str, tx_id: str, plan_sha256: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    env_payload, info = _read_regular_any_owner(ENV_PATH)
    if _digest_bytes(env_payload) != probe["env"]["sha256"]:
        raise RuntimeError("canonical environment changed after bootstrap plan")
    _normalize_git_metadata(backup, probe["git_metadata"])
    _archive_repo_bytecode(backup, probe["repo_bytecode"])
    _install_target_units(probe["runtime_authority"], probe["live_units"])
    desired = _render_env(env_payload, node_id)
    _atomic_write(ENV_PATH, desired)
    _secure_regular(ENV_PATH)
    _move_historical(backup, probe["historical_env"])
    if node_id == "node01":
        legacy_payload, _ = _read_regular_any_owner(LEGACY_UNIT)
        if _digest_bytes(legacy_payload) != probe["legacy"]["sha256"]:
            raise RuntimeError("legacy unit changed after owner plan")
        _install_legacy_retirement()
    _write_journal(backup, {"schema": 1, "tx_id": tx_id, "status": "applied", "plan_sha256": plan_sha256})


def _assert_env_contract(
    node_id: str,
    expected_pg_state: str,
    runtime_authority: dict[str, Any],
    probe_root: Path,
) -> dict[str, Any]:
    _secure_regular(ENV_PATH)
    payload = ENV_PATH.read_bytes()
    values = _parse_env(payload)
    _assert_no_execution_env_injection(values)
    expected = {
        **CONTRACT_KEYS,
        "META_DELETION_NODE_ID": node_id,
        "LINAS_HA_PEER_HOST": str(FIXED_NODES[node_id]["peer_ip"]),
    }
    for key, value in expected.items():
        if values.get(key) != value:
            raise RuntimeError(f"bootstrapped HA contract key is invalid: {key}")
    pg = _pg_probe(values, runtime_authority, probe_root=probe_root)
    if pg["state_sha256"] != expected_pg_state:
        raise RuntimeError("PostgreSQL Meta registry changed during bootstrap")
    return {"env_sha256": _digest_bytes(payload), "pg": pg}


def _node_verify(node_id: str, tx_id: str, plan_sha256: str, expected_pg_state: str) -> dict[str, Any]:
    backup = _assert_active(tx_id, plan_sha256)
    if _port_listening(8003):
        raise RuntimeError("node verification requires direct LB port 8003 closed")
    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    _assert_normalized_git_metadata(backup, probe["git_metadata"])
    _assert_target_units(probe["runtime_authority"])
    _assert_repo_bytecode_absent()
    _nested.assert_quarantined(REPO_DIR, probe["nested_runtime"], tx_id)
    result = _assert_env_contract(
        node_id,
        expected_pg_state,
        probe["runtime_authority"],
        backup / "runtime-probe",
    )
    for entry in probe["historical_env"]:
        if (REPO_DIR / entry["name"]).exists() or (REPO_DIR / entry["name"]).is_symlink():
            raise RuntimeError("historical environment file remains in the live repository")
        archived = backup / "historical-env" / entry["name"]
        _secure_regular(archived)
        if _digest_bytes(archived.read_bytes()) != entry["sha256"]:
            raise RuntimeError("historical environment archive changed")
    if node_id == "node01":
        _assert_legacy_retired(prove_manual_start_denied=True)
    return result


def _quiesce_and_disable_units(states: dict[str, dict[str, str]]) -> None:
    units = list(reversed(tuple(states)))
    _run(["systemctl", "disable", "--now", *units])
    for unit in units:
        if (
            _run(["systemctl", "is-active", unit], check=False).returncode == 0
            or _run(["systemctl", "is-enabled", unit], check=False).returncode == 0
        ):
            raise RuntimeError(f"unit remained active or enabled during fail-closed quiesce: {unit}")


def _ordered_units(states: dict[str, dict[str, str]]) -> list[str]:
    ordered = [unit for unit in (API_UNIT, *WORKER_UNITS) if unit in states]
    ordered.extend(unit for unit in states if unit not in ordered)
    return ordered


def _start_units_disabled(states: dict[str, dict[str, str]]) -> None:
    """Restore active state while every unit remains disabled across reboot."""

    for unit in _ordered_units(states):
        if states[unit]["active"] == "active":
            _run(["systemctl", "start", unit])
            if _run(["systemctl", "is-active", unit], check=False).returncode != 0:
                raise RuntimeError(f"service failed crash-safe restore: {unit}")
        else:
            _run(["systemctl", "stop", unit], check=False)


def _enable_units_after_verification(states: dict[str, dict[str, str]]) -> None:
    # Enabling is deliberately after callers verify the manually started
    # processes. A crash earlier leaves every unit disabled across reboot.
    for unit in _ordered_units(states):
        if states[unit]["enabled"] == "enabled":
            _run(["systemctl", "enable", unit])
        else:
            _run(["systemctl", "disable", unit], check=False)
    wants = Path("/etc/systemd/system/multi-user.target.wants")
    _fsync_dir(wants)
    for unit in _ordered_units(states):
        enabled = _run(["systemctl", "is-enabled", unit], check=False).returncode == 0
        if enabled != (states[unit]["enabled"] == "enabled"):
            raise RuntimeError(f"service enablement was not durably restored: {unit}")


def _wait_ready() -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=3) as response:
                payload = json.load(response)
            if response.status == 200 and payload.get("ok") is True:
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise RuntimeError("canonical API did not become ready")


def _wait_health() -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8003/api/health", timeout=3) as response:
                payload = json.load(response)
            if response.status == 200 and payload.get("ok") is True:
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise RuntimeError("canonical API did not become healthy")


def _assert_process_contract(
    node_id: str,
    *,
    require_enabled: bool,
    require_bootstrapped_contract: bool = True,
) -> None:
    """Prove the exact live API and four queue-worker process contracts.

    This reads the processes, not merely unit files: exact argv, cwd and every
    canonical EnvironmentFile value must match.  PID stability is rechecked so
    a crash/restart cannot satisfy different portions of the proof.
    """

    env_expected = _parse_env(ENV_PATH.read_bytes())
    _assert_no_execution_env_injection(env_expected)
    env_expected.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PATH": f"{REPO_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin",
        }
    )
    if require_bootstrapped_contract:
        env_expected.update(
            {
                **CONTRACT_KEYS,
                "META_DELETION_NODE_ID": node_id,
                "LINAS_HA_PEER_HOST": str(FIXED_NODES[node_id]["peer_ip"]),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
    specs: dict[str, tuple[list[str], str | None]] = {
        API_UNIT: ([str(REPO_DIR / "venv/bin/python"), "main.py"], None),
    }
    for unit in WORKER_UNITS:
        queue = unit.removeprefix("linasbot-worker@").removesuffix(".service")
        specs[unit] = (
            [str(REPO_DIR / "venv/bin/python"), "scripts/run_queue_worker.py", "--queue", queue],
            queue,
        )

    for unit, (expected_argv, expected_queue) in specs.items():
        if _run(["systemctl", "is-active", unit], check=False).returncode != 0:
            raise RuntimeError(f"canonical process is not active before maintenance clear: {unit}")
        if require_enabled and _run(["systemctl", "is-enabled", unit], check=False).returncode != 0:
            raise RuntimeError(f"canonical process is not enabled before maintenance clear: {unit}")
        working_directory = _run(["systemctl", "show", unit, "--property=WorkingDirectory", "--value"]).stdout.strip()
        if working_directory != str(REPO_DIR):
            raise RuntimeError(f"canonical process unit has the wrong working directory: {unit}")
        pid = _run(["systemctl", "show", unit, "--property=MainPID", "--value"]).stdout.strip()
        if not pid.isdigit() or int(pid) <= 0:
            raise RuntimeError(f"canonical process has no live MainPID: {unit}")
        proc = Path("/proc") / pid
        argv = [part.decode("utf-8", errors="strict") for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
        if argv != expected_argv:
            raise RuntimeError(f"canonical process argv is not exact: {unit}")
        if Path(os.path.realpath(proc / "cwd")) != REPO_DIR:
            raise RuntimeError(f"canonical process cwd is not exact: {unit}")
        process_values: dict[str, str] = {}
        for entry in (proc / "environ").read_bytes().split(b"\0"):
            if b"=" in entry:
                key, value = entry.split(b"=", 1)
                process_values[key.decode(errors="strict")] = value.decode(errors="strict")
        _assert_no_execution_env_injection(process_values)
        expected = dict(env_expected)
        if expected_queue is not None:
            expected["LINAS_WORKER_QUEUE"] = expected_queue
        if any(process_values.get(key) != value for key, value in expected.items()):
            raise RuntimeError(f"canonical process did not load the exact environment: {unit}")
        stable_pid = _run(["systemctl", "show", unit, "--property=MainPID", "--value"]).stdout.strip()
        if stable_pid != pid or _run(["systemctl", "is-active", unit], check=False).returncode != 0:
            raise RuntimeError(f"canonical process changed during exact verification: {unit}")


def _node_admit(node_id: str, tx_id: str, plan_sha256: str, expected_pg_state: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    _assert_normalized_git_metadata(backup, probe["git_metadata"])
    _assert_env_contract(
        node_id,
        expected_pg_state,
        probe["runtime_authority"],
        backup / "runtime-probe",
    )
    states = probe["canonical_services"]
    _assert_target_units(probe["runtime_authority"])
    _assert_repo_bytecode_absent()
    _assert_durable_worker_preconditions(_parse_env(ENV_PATH.read_bytes()), states)
    _quiesce_and_disable_units(states)
    # This is the only installation boundary for the permanent controlled
    # failover guard. Both bootstrap guards are already loaded and every unit
    # is stopped+disabled, so a crash after either drop-in write remains safe;
    # forward recovery idempotently completes the exact pair before admission.
    _install_controlled_failover_guard_contract()
    _clear_bootstrap_runtime_guard()
    _start_units_disabled({API_UNIT: states[API_UNIT]})
    _wait_health()
    _start_units_disabled({unit: states[unit] for unit in WORKER_UNITS})
    _arm_bootstrap_runtime_guard()
    _assert_process_contract(node_id, require_enabled=False)
    _enable_units_after_verification(states)
    _assert_process_contract(node_id, require_enabled=True)
    _unlink_durable(VOLATILE_MARKER)
    _unlink_durable(PERSISTENT_MARKER)
    _restore_nginx(backup)
    _wait_ready()
    if node_id == "node01":
        _assert_legacy_retired(prove_manual_start_denied=True)
    _assert_bootstrap_runtime_guard()
    _write_journal(backup, {"schema": 1, "tx_id": tx_id, "status": "admitted", "plan_sha256": plan_sha256})


def _node_redrain(tx_id: str, plan_sha256: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    active_payload, _ = _read_regular_any_owner(ACTIVE_PATH)
    active = json.loads(active_payload)
    probe_payload, _ = _read_regular_any_owner(backup / "probe.before.json")
    probe = json.loads(probe_payload)
    _arm_bootstrap_runtime_guard()
    _quiesce_and_disable_units(probe["canonical_services"])
    _install_boot_guards(backup)
    _arm_marker(PERSISTENT_MARKER)
    _arm_marker(VOLATILE_MARKER)
    current = NGINX_CONFIG.read_bytes()
    if b"linasbot-meta-ha-bootstrap-readiness" not in current:
        # Reinstall from the exact saved original after an admission attempt.
        original = (backup / "nginx.before").read_bytes()
        if current != original:
            raise RuntimeError("nginx changed during bootstrap admission")
        _install_nginx_override(backup)
    _stop_canonical()
    if active.get("node_id") == "node01" and (
        _run(["systemctl", "is-active", "linas_ai_bot.service"], check=False).returncode == 0
        or _run(["systemctl", "is-enabled", "linas_ai_bot.service"], check=False).returncode == 0
        or _port_listening(8000)
    ):
        _run(["systemctl", "disable", "--now", "linas_ai_bot.service"], check=False)
        if _port_listening(8000):
            raise RuntimeError("legacy port 8000 remained active during fail-closed redrain")


def _node_rollback(node_id: str, tx_id: str, plan_sha256: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    _node_redrain(tx_id, plan_sha256)
    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    before = (backup / "env.before").read_bytes()
    if _digest_bytes(before) != probe["env"]["sha256"]:
        raise RuntimeError("canonical environment rollback backup changed")
    _restore_live_units(backup, probe["live_units"])
    _restore_repo_bytecode(backup, probe["repo_bytecode"])
    _nested.restore_quarantine(REPO_DIR, backup, probe["nested_runtime"], tx_id)
    _atomic_write(ENV_PATH, before, mode=int(probe["env"]["mode"]))
    os.chown(ENV_PATH, int(probe["env"]["uid"]), int(probe["env"]["gid"]))
    for entry in probe["historical_env"]:
        _transition_historical_env(
            entry,
            backup / "historical-env" / str(entry["name"]),
            REPO_DIR / str(entry["name"]),
            source_owner=(0, 0),
            source_mode=0o600,
            target_owner=(int(entry["uid"]), int(entry["gid"])),
            target_mode=int(entry["mode"]),
            direction="rollback",
        )
    if node_id == "node01":
        legacy_before = (backup / "linas_ai_bot.service.before").read_bytes()
        current, _ = _read_regular_any_owner(LEGACY_UNIT)
        if current != legacy_before:
            raise RuntimeError("legacy unit changed; refusing rollback start")
    restored, info = _read_regular_any_owner(ENV_PATH)
    if (
        _digest_bytes(restored) != probe["env"]["sha256"]
        or info.st_uid != probe["env"]["uid"]
        or info.st_gid != probe["env"]["gid"]
        or stat.S_IMODE(info.st_mode) != probe["env"]["mode"]
    ):
        raise RuntimeError("canonical environment exact rollback failed")
    _restore_git_metadata(backup, probe["git_metadata"])
    _write_journal(backup, {"schema": 1, "tx_id": tx_id, "status": "rolled_back_drained", "plan_sha256": plan_sha256})


def _node_admit_rollback(tx_id: str, plan_sha256: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    active_payload, _ = _read_regular_any_owner(ACTIVE_PATH)
    active = json.loads(active_payload)
    node_id = str(active.get("node_id") or "")
    if node_id not in FIXED_NODES:
        raise RuntimeError("bootstrap active node identity is invalid")
    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    states = probe["canonical_services"]
    _assert_restored_git_metadata(backup, probe["git_metadata"])
    _assert_live_units(probe["live_units"])
    if _repo_bytecode_manifest() != probe["repo_bytecode"]:
        raise RuntimeError("repository Python bytecode rollback baseline is not exact")
    _nested.assert_live_matches(REPO_DIR, probe["nested_runtime"])
    _quiesce_and_disable_units(states)
    _clear_bootstrap_runtime_guard()
    _start_units_disabled({API_UNIT: states[API_UNIT]})
    _wait_health()
    _start_units_disabled({unit: states[unit] for unit in WORKER_UNITS})
    _arm_bootstrap_runtime_guard()
    _assert_process_contract(node_id, require_enabled=False, require_bootstrapped_contract=False)
    _enable_units_after_verification(states)
    _assert_process_contract(node_id, require_enabled=True, require_bootstrapped_contract=False)
    _unlink_durable(VOLATILE_MARKER)
    _unlink_durable(PERSISTENT_MARKER)
    _restore_nginx(backup)
    _wait_ready()
    if node_id == "node01":
        _assert_legacy_retired(prove_manual_start_denied=True)


def _bootstrap_commit_proof_payload(
    probe: dict[str, Any],
    *,
    tx_id: str,
    plan_sha256: str,
    node_id: str,
) -> dict[str, Any]:
    runtime = probe["runtime_authority"]
    shared = runtime["shared"]
    return {
        "schema": 2,
        "format": "linas-meta-ha-bootstrap-node-v2",
        "tx_id": tx_id,
        "plan_sha256": plan_sha256,
        "node_id": node_id,
        "status": "committed",
        "runtime_transaction_id": shared["transaction_id"],
        "runtime_plan_sha256": shared["plan_sha256"],
        "runtime_cluster_receipt_sha256": shared["cluster_receipt_sha256"],
        "runtime_shared_sha256": runtime["shared_sha256"],
        "runtime_launcher_receipt_sha256": shared["launcher_receipt_sha256"],
        "qg_manifest_sha256": shared["manifest_sha256"],
        "control_plane_archive_sha256": shared["control_plane_archive_sha256"],
        "control_plane_tree_sha256": shared["control_plane_tree_sha256"],
        "wheelhouse_archive_sha256": shared["wheelhouse_archive_sha256"],
        "wheelhouse_tree_sha256": shared["wheelhouse_tree_sha256"],
        "wheelhouse_file_count": shared["wheelhouse_file_count"],
        "wheelhouse_total_size": shared["wheelhouse_total_size"],
        "requirements_lock_sha256": shared["requirements_lock_sha256"],
        "runtime_tree_sha256": shared["runtime_tree_sha256"],
        "target_unit_contract_sha256": _digest(probe["target_units"]),
        "legacy_bytecode_manifest_sha256": _digest(probe["repo_bytecode"]),
        "repo_bytecode_absent": True,
        "nested_runtime_present": bool(probe["nested_runtime"]["present"]),
        "nested_runtime_evidence_sha256": _nested.digest_evidence(probe["nested_runtime"]),
        "nested_runtime_quarantined": bool(probe["nested_runtime"]["present"]),
    }


def _read_bootstrap_commit_proof(
    probe: dict[str, Any],
    *,
    tx_id: str,
    plan_sha256: str,
    node_id: str,
) -> dict[str, Any]:
    payload, raw = _read_authority_json(COMMITTED_PROOF_PATH)
    expected = _bootstrap_commit_proof_payload(
        probe,
        tx_id=tx_id,
        plan_sha256=plan_sha256,
        node_id=node_id,
    )
    if payload != expected or raw != _canonical(expected) + b"\n":
        raise RuntimeError("bootstrap commit proof differs from the exact first-transition authority")
    return payload


def _node_commit_proof(tx_id: str, plan_sha256: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    active = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
    if active.get("node_id") == "node01":
        _assert_legacy_retired(prove_manual_start_denied=True)
    node_id = str(active.get("node_id") or "")
    if node_id not in FIXED_NODES:
        raise RuntimeError("bootstrap commit proof node identity is invalid")
    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    _assert_normalized_git_metadata(backup, probe["git_metadata"])
    if _runtime_authority(node_id) != probe["runtime_authority"]:
        raise RuntimeError("Python runtime authority changed before bootstrap commit proof")
    _assert_target_units(probe["runtime_authority"])
    _assert_repo_bytecode_absent()
    _nested.assert_quarantined(REPO_DIR, probe["nested_runtime"], tx_id)
    _assert_process_contract(node_id, require_enabled=True)
    _assert_controlled_failover_guard_contract()
    _assert_bootstrap_runtime_guard()
    if (
        PERSISTENT_MARKER.exists()
        or PERSISTENT_MARKER.is_symlink()
        or VOLATILE_MARKER.exists()
        or VOLATILE_MARKER.is_symlink()
        or _port_listening(8003) is False
    ):
        raise RuntimeError("bootstrap cannot record commit before proven traffic restoration")
    proof_payload = _bootstrap_commit_proof_payload(
        probe,
        tx_id=tx_id,
        plan_sha256=plan_sha256,
        node_id=node_id,
    )
    if COMMITTED_PROOF_PATH.exists() or COMMITTED_PROOF_PATH.is_symlink():
        _secure_regular(COMMITTED_PROOF_PATH)
        existing = json.loads(COMMITTED_PROOF_PATH.read_text(encoding="utf-8"))
        if existing != proof_payload:
            raise RuntimeError("a different bootstrap commit proof already exists")
    else:
        _atomic_write(
            COMMITTED_PROOF_PATH,
            _canonical(proof_payload) + b"\n",
            no_replace=True,
        )
    _write_journal(
        backup,
        {"schema": 1, "tx_id": tx_id, "status": "commit_proved", "plan_sha256": plan_sha256},
    )


def _node_finalize(tx_id: str, plan_sha256: str, status_value: str) -> None:
    backup = _assert_active(tx_id, plan_sha256)
    active = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
    if active.get("node_id") == "node01":
        _assert_legacy_retired(prove_manual_start_denied=True)
    node_id = str(active.get("node_id") or "")
    if node_id not in FIXED_NODES:
        raise RuntimeError("bootstrap finalization node identity is invalid")
    _assert_process_contract(
        node_id,
        require_enabled=True,
        require_bootstrapped_contract=status_value == "committed",
    )
    _assert_bootstrap_runtime_guard()
    if status_value == "committed":
        _assert_controlled_failover_guard_contract()
    if (
        PERSISTENT_MARKER.exists()
        or PERSISTENT_MARKER.is_symlink()
        or VOLATILE_MARKER.exists()
        or VOLATILE_MARKER.is_symlink()
        or _port_listening(8003) is False
    ):
        raise RuntimeError("bootstrap cannot finalize before proven traffic restoration")
    _write_journal(
        backup,
        {"schema": 1, "tx_id": tx_id, "status": status_value, "plan_sha256": plan_sha256},
    )
    if status_value == "committed":
        probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
        _assert_normalized_git_metadata(backup, probe["git_metadata"])
        _read_bootstrap_commit_proof(
            probe,
            tx_id=tx_id,
            plan_sha256=plan_sha256,
            node_id=node_id,
        )
    elif COMMITTED_PROOF_PATH.exists() or COMMITTED_PROOF_PATH.is_symlink():
        _secure_regular(COMMITTED_PROOF_PATH)
        proof = json.loads(COMMITTED_PROOF_PATH.read_text(encoding="utf-8"))
        if proof.get("tx_id") != tx_id or proof.get("plan_sha256") != plan_sha256:
            raise RuntimeError("a different bootstrap commit proof already exists")
        _unlink_durable(COMMITTED_PROOF_PATH)


def _node_release_active(tx_id: str, plan_sha256: str, status_value: str) -> None:
    """Idempotently release the node sentinel only after a durable final state."""

    backup = _backup_dir(tx_id)
    _secure_dir(backup)
    release_receipt = backup / "release.complete.json"
    expected_release = {
        "schema": 1,
        "tx_id": tx_id,
        "plan_sha256": plan_sha256,
        "status": status_value,
    }
    if release_receipt.exists() or release_receipt.is_symlink():
        _secure_regular(release_receipt)
        if json.loads(release_receipt.read_text(encoding="utf-8")) != expected_release:
            raise RuntimeError("bootstrap release receipt differs from the durable final state")
        if (backup / "runtime-probe").exists() or (backup / "runtime-probe").is_symlink():
            raise RuntimeError("bootstrap release receipt preceded probe cleanup")
        return
    _secure_regular(backup / "journal.json")
    journal = json.loads((backup / "journal.json").read_text(encoding="utf-8"))
    probe = json.loads((backup / "probe.before.json").read_text(encoding="utf-8"))
    if (
        journal.get("tx_id") != tx_id
        or journal.get("plan_sha256") != plan_sha256
        or journal.get("status") != status_value
    ):
        raise RuntimeError("bootstrap node is not durably finalized")
    if status_value == "committed":
        node_id = str(probe.get("node_id") or "")
        if node_id not in FIXED_NODES:
            raise RuntimeError("bootstrap commit proof node identity is invalid")
        _read_bootstrap_commit_proof(
            probe,
            tx_id=tx_id,
            plan_sha256=plan_sha256,
            node_id=node_id,
        )
    elif COMMITTED_PROOF_PATH.exists() or COMMITTED_PROOF_PATH.is_symlink():
        raise RuntimeError("rollback finalization cannot release a commit proof")
    if ACTIVE_PATH.exists() or ACTIVE_PATH.is_symlink():
        _assert_active(tx_id, plan_sha256)
        _unlink_durable(ACTIVE_PATH)
    _clear_bootstrap_runtime_guard()
    _remove_boot_guards(backup, require_quiesced=False)
    if status_value in {"rolled_back", "recovery_rolled_back"} and probe.get("node_id") == "node01":
        _restore_legacy_after_final_rollback(backup)
    for path in (*BOOT_GUARDS, BOOTSTRAP_RUNTIME_GUARD):
        if path.exists() or path.is_symlink():
            raise RuntimeError("bootstrap final release retained a transaction reboot guard")
    node_id = str(probe.get("node_id") or "")
    if node_id not in FIXED_NODES:
        raise RuntimeError("bootstrap release receipt node identity is invalid")
    _assert_process_contract(
        node_id,
        require_enabled=True,
        require_bootstrapped_contract=status_value == "committed",
    )
    if status_value == "committed":
        _assert_normalized_git_metadata(backup, probe["git_metadata"])
        _assert_target_units(probe["runtime_authority"])
        _assert_repo_bytecode_absent()
    else:
        _assert_restored_git_metadata(backup, probe["git_metadata"])
        _assert_live_units(probe["live_units"])
        if _repo_bytecode_manifest() != probe["repo_bytecode"]:
            raise RuntimeError("bootstrap rollback bytecode baseline changed before release")
    if status_value == "committed" and node_id == "node01":
        _assert_legacy_retired(prove_manual_start_denied=True)
    probe_root = backup / "runtime-probe"
    if probe_root.exists() or probe_root.is_symlink():
        _remove_private_tree(probe_root, expected_parent=backup)
    _atomic_write(
        release_receipt,
        _canonical(expected_release) + b"\n",
        no_replace=True,
    )


def _node_status(tx_id: str, plan_sha256: str) -> dict[str, Any]:
    backup = _backup_dir(tx_id)
    backup_exists = backup.exists() or backup.is_symlink()
    active = ACTIVE_PATH.exists() or ACTIVE_PATH.is_symlink()
    if not backup_exists and not active:
        return {"state": "absent", "status": "absent", "commit_proof": False}
    if active:
        _secure_regular(ACTIVE_PATH)
        active_payload, _ = _read_regular_any_owner(ACTIVE_PATH)
        active_state = json.loads(active_payload)
        if active_state.get("tx_id") != tx_id or active_state.get("plan_sha256") != plan_sha256:
            raise RuntimeError("bootstrap active sentinel belongs to another transaction")
    journal: dict[str, Any] = {}
    if backup_exists:
        _secure_dir(backup)
        journal_path = backup / "journal.json"
        if journal_path.exists() or journal_path.is_symlink():
            _secure_regular(journal_path)
            journal_payload, _ = _read_regular_any_owner(journal_path)
            journal = json.loads(journal_payload)
            if journal.get("tx_id") != tx_id or journal.get("plan_sha256") != plan_sha256:
                raise RuntimeError("bootstrap node backup belongs to another transaction")
    status = str(journal.get("status") or "preparing")
    release_receipt = backup / "release.complete.json"
    released = release_receipt.exists() or release_receipt.is_symlink()
    if released:
        _secure_regular(release_receipt)
        receipt = json.loads(release_receipt.read_text(encoding="utf-8"))
        if receipt != {
            "schema": 1,
            "tx_id": tx_id,
            "plan_sha256": plan_sha256,
            "status": status,
        }:
            raise RuntimeError("bootstrap release receipt is invalid")
    aborted = status == "aborted_before_drain"
    if aborted:
        abort_receipt = backup / "abort.complete.json"
        if abort_receipt.exists() or abort_receipt.is_symlink():
            _secure_regular(abort_receipt)
            if json.loads(abort_receipt.read_text(encoding="utf-8")) != {
                "schema": 1,
                "tx_id": tx_id,
                "plan_sha256": plan_sha256,
                "status": "aborted_before_drain",
            }:
                raise RuntimeError("bootstrap prepare abort receipt is invalid")
        elif not active:
            raise RuntimeError("released bootstrap prepare abort has no durable receipt")
        if not active and (
            PERSISTENT_MARKER.exists()
            or PERSISTENT_MARKER.is_symlink()
            or VOLATILE_MARKER.exists()
            or VOLATILE_MARKER.is_symlink()
            or BOOTSTRAP_RUNTIME_GUARD.exists()
            or BOOTSTRAP_RUNTIME_GUARD.is_symlink()
            or any(path.exists() or path.is_symlink() for path in BOOT_GUARDS)
            or not _port_listening(8003)
        ):
            raise RuntimeError("released bootstrap prepare abort is not an exact serving baseline")
    if active and status not in {"preparing", "aborted_before_drain"}:
        _assert_active(tx_id, plan_sha256)
    if not active and status not in {
        "aborted_before_drain",
        "committed",
        "rolled_back",
        "recovery_rolled_back",
    }:
        raise RuntimeError("bootstrap backup is not durably finalized and has no active sentinel")
    proof = COMMITTED_PROOF_PATH.exists() or COMMITTED_PROOF_PATH.is_symlink()
    if proof:
        _secure_regular(COMMITTED_PROOF_PATH)
        proof_payload = json.loads(COMMITTED_PROOF_PATH.read_text(encoding="utf-8"))
        if proof_payload.get("tx_id") != tx_id or proof_payload.get("plan_sha256") != plan_sha256:
            raise RuntimeError("bootstrap node commit proof belongs to another transaction")
    return {
        "state": "active" if active else ("released" if released or aborted else "release-pending"),
        "status": status,
        "commit_proof": proof,
    }


def _public_ready() -> None:
    request = urllib.request.Request(
        "https://linasaibot.com/api/ready",
        headers={"User-Agent": "linasbot-meta-ha-bootstrap-readiness-proof/1"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if response.status != 200 or payload.get("ok") is not True:
        raise RuntimeError("public readiness is not healthy")


def _node_call_local(command: str, **kwargs: str) -> Any:
    functions: dict[str, Callable[..., Any]] = {
        "prepare": _node_prepare,
        "abort-prepare": _node_abort_prepare,
        "drain": _node_drain,
        "apply": _node_apply,
        "verify": _node_verify,
        "admit": _node_admit,
        "redrain": _node_redrain,
        "rollback": _node_rollback,
        "admit-rollback": _node_admit_rollback,
        "commit-proof": _node_commit_proof,
        "finalize": _node_finalize,
        "release-active": _node_release_active,
        "status": _node_status,
    }
    return functions[command](**kwargs)


def _remote_phase(source: bytes, source_sha: str, command: str, **kwargs: str) -> Any:
    argv = ["node-phase", command]
    for key, value in kwargs.items():
        argv.extend([f"--{key.replace('_', '-')}", value])
    output = _remote(FIXED_NODES["node01"]["peer_ip"], source, source_sha, argv)
    return json.loads(output) if output.strip().startswith("{") else output


def _orchestrate_apply(args: argparse.Namespace) -> int:
    plan, source, source_sha = _combined_plan(args)
    plan_sha = _digest(plan)
    if plan_sha != args.expected_plan_sha256:
        raise RuntimeError("bootstrap plan changed after owner dry-run")
    if args.confirm != _confirmation(plan_sha):
        raise PermissionError("exact bootstrap/credential-rotation confirmation is missing")
    tx_id = uuid.uuid4().hex
    decision = "rollback"
    coordinator = {
        "schema": 1,
        "tx_id": tx_id,
        "plan_sha256": plan_sha,
        "target_sha": args.target_sha,
        "node01_previous_sha": args.expected_node01_sha,
        "node02_previous_sha": args.expected_node02_sha,
        "expected_pg_state_sha256": args.expected_pg_state_sha256,
        "lb_attestation_sha256": str(plan["lb"]["attestation_sha256"]),
        "source_sha256": source_sha,
        "peer_host": FIXED_NODES["node01"]["peer_ip"],
        "phase": "planned",
        "decision": decision,
    }

    def update_coordinator(phase: str) -> None:
        coordinator["phase"] = phase
        coordinator["decision"] = decision
        _write_coordinator_journal(coordinator)

    update_coordinator("planned")
    peer_kwargs = {
        "node_id": "node02",
        "expected_sha": args.expected_node02_sha,
        "tx_id": tx_id,
        "plan_sha256": plan_sha,
        "expected_probe_sha256": _digest(plan["node02"]),
    }
    local_kwargs = {
        "node_id": "node01",
        "expected_sha": args.expected_node01_sha,
        "tx_id": tx_id,
        "plan_sha256": plan_sha,
        "expected_probe_sha256": _digest(plan["node01"]),
    }
    drain_started = False
    commit_decided = False
    try:
        update_coordinator("node01-prepare-started")
        _node_call_local("prepare", **local_kwargs)
        update_coordinator("node01-prepared")
        update_coordinator("node02-prepare-started")
        _remote_phase(source, source_sha, "prepare", **peer_kwargs)
        update_coordinator("node02-prepared")
        drain_started = True
        update_coordinator("node02-drain-started")
        _remote_phase(source, source_sha, "drain", tx_id=tx_id, plan_sha256=plan_sha)
        update_coordinator("node02-drained")
        _public_ready()
        time.sleep(30)
        _public_ready()
        update_coordinator("node01-drain-started")
        _node_call_local("drain", tx_id=tx_id, plan_sha256=plan_sha)
        update_coordinator("node01-drained")
        time.sleep(30)
        update_coordinator("node02-apply-started")
        _remote_phase(source, source_sha, "apply", node_id="node02", tx_id=tx_id, plan_sha256=plan_sha)
        update_coordinator("node02-applied")
        update_coordinator("node01-apply-started")
        _node_call_local("apply", node_id="node01", tx_id=tx_id, plan_sha256=plan_sha)
        update_coordinator("node01-applied")
        peer_verified = _remote_phase(
            source,
            source_sha,
            "verify",
            node_id="node02",
            tx_id=tx_id,
            plan_sha256=plan_sha,
            expected_pg_state=args.expected_pg_state_sha256,
        )
        local_verified = _node_call_local(
            "verify",
            node_id="node01",
            tx_id=tx_id,
            plan_sha256=plan_sha,
            expected_pg_state=args.expected_pg_state_sha256,
        )
        if peer_verified["pg"] != local_verified["pg"]:
            raise RuntimeError("post-bootstrap PostgreSQL proof differs between nodes")
        update_coordinator("both-verified")
        # Both exact env/PG/legacy-retirement states are now proved while both
        # nodes are still persistently drained.  Record the irreversible commit
        # before removing any boot guard or starting any canonical process;
        # interruption from here is forward-only recovery.
        coordinator = _publish_commit_decision(coordinator)
        decision = str(coordinator["decision"])
        commit_decided = True
        update_coordinator("node02-admit-started")
        _remote_phase(
            source,
            source_sha,
            "admit",
            node_id="node02",
            tx_id=tx_id,
            plan_sha256=plan_sha,
            expected_pg_state=args.expected_pg_state_sha256,
        )
        update_coordinator("node02-admitted")
        update_coordinator("node01-admit-started")
        _node_call_local(
            "admit",
            node_id="node01",
            tx_id=tx_id,
            plan_sha256=plan_sha,
            expected_pg_state=args.expected_pg_state_sha256,
        )
        update_coordinator("node01-admitted")
        _public_ready()
        _remote_phase(source, source_sha, "commit-proof", tx_id=tx_id, plan_sha256=plan_sha)
        _node_call_local("commit-proof", tx_id=tx_id, plan_sha256=plan_sha)
        update_coordinator("both-commit-proved")
        _remote_phase(source, source_sha, "finalize", tx_id=tx_id, plan_sha256=plan_sha, status_value="committed")
        _node_call_local("finalize", tx_id=tx_id, plan_sha256=plan_sha, status_value="committed")
        update_coordinator("both-finalized")
        _remote_phase(
            source,
            source_sha,
            "release-active",
            tx_id=tx_id,
            plan_sha256=plan_sha,
            status_value="committed",
        )
        _node_call_local("release-active", tx_id=tx_id, plan_sha256=plan_sha, status_value="committed")
        update_coordinator("complete")
        _unlink_durable(COORDINATOR_PATH)
    except BaseException:
        # In-memory state is never authority after any journal-write ambiguity.
        # A replace may have succeeded even when fsync/chown/readback raised.
        try:
            persisted_coordinator, _ = _read_current_coordinator_journal()
        except BaseException:
            if drain_started:
                for action in (
                    lambda: _node_call_local("redrain", tx_id=tx_id, plan_sha256=plan_sha),
                    lambda: _remote_phase(source, source_sha, "redrain", tx_id=tx_id, plan_sha256=plan_sha),
                ):
                    try:
                        action()
                    except BaseException:
                        pass
            raise RuntimeError(
                "bootstrap durable decision is unreadable; no rollback or admission is authorized"
            ) from None
        coordinator = persisted_coordinator
        decision = str(coordinator["decision"])
        commit_decided = decision == "commit"
        if not drain_started:
            abort_ok = True
            # RPC acknowledgement is not authority. Either prepare may have
            # published bootstrap.active and completed after the coordinator
            # lost its reply, so query/abort both exact transaction identities.
            for action in (
                lambda: _remote_phase(source, source_sha, "abort-prepare", tx_id=tx_id, plan_sha256=plan_sha),
                lambda: _node_call_local("abort-prepare", tx_id=tx_id, plan_sha256=plan_sha),
            ):
                try:
                    action()
                except BaseException:
                    abort_ok = False
            if abort_ok:
                update_coordinator("aborted-before-drain")
                _unlink_durable(COORDINATOR_PATH)
                raise RuntimeError("bootstrap preparation failed before drain; live state was not changed") from None
            raise RuntimeError("bootstrap prepare cleanup is uncertain; active sentinel retained") from None
        if commit_decided:
            finalize_ok = True
            for action in (
                lambda: _remote_phase(
                    source,
                    source_sha,
                    "admit",
                    node_id="node02",
                    tx_id=tx_id,
                    plan_sha256=plan_sha,
                    expected_pg_state=args.expected_pg_state_sha256,
                ),
                lambda: _node_call_local(
                    "admit",
                    node_id="node01",
                    tx_id=tx_id,
                    plan_sha256=plan_sha,
                    expected_pg_state=args.expected_pg_state_sha256,
                ),
                lambda: _remote_phase(source, source_sha, "commit-proof", tx_id=tx_id, plan_sha256=plan_sha),
                lambda: _node_call_local("commit-proof", tx_id=tx_id, plan_sha256=plan_sha),
                lambda: _remote_phase(
                    source,
                    source_sha,
                    "finalize",
                    tx_id=tx_id,
                    plan_sha256=plan_sha,
                    status_value="committed",
                ),
                lambda: _node_call_local("finalize", tx_id=tx_id, plan_sha256=plan_sha, status_value="committed"),
                lambda: _remote_phase(
                    source,
                    source_sha,
                    "release-active",
                    tx_id=tx_id,
                    plan_sha256=plan_sha,
                    status_value="committed",
                ),
                lambda: _node_call_local("release-active", tx_id=tx_id, plan_sha256=plan_sha, status_value="committed"),
            ):
                try:
                    action()
                except BaseException:
                    finalize_ok = False
            if finalize_ok:
                update_coordinator("complete")
                _unlink_durable(COORDINATOR_PATH)
                _log("commit decision and both proofs were durable; interrupted finalization completed")
                _log(ROTATION_WARNING)
                return 0
            raise RuntimeError(
                "bootstrap commit is proven on both nodes but finalization is incomplete; do not roll back"
            ) from None
        rollback_ok = True
        for action in (
            lambda: _node_call_local("redrain", tx_id=tx_id, plan_sha256=plan_sha),
            lambda: _remote_phase(source, source_sha, "redrain", tx_id=tx_id, plan_sha256=plan_sha),
            lambda: _node_call_local("rollback", node_id="node01", tx_id=tx_id, plan_sha256=plan_sha),
            lambda: _remote_phase(
                source,
                source_sha,
                "rollback",
                node_id="node02",
                tx_id=tx_id,
                plan_sha256=plan_sha,
            ),
        ):
            try:
                action()
            except BaseException:
                rollback_ok = False
        if rollback_ok:
            try:
                _remote_phase(source, source_sha, "admit-rollback", tx_id=tx_id, plan_sha256=plan_sha)
                _node_call_local("admit-rollback", tx_id=tx_id, plan_sha256=plan_sha)
                _public_ready()
                _remote_phase(
                    source,
                    source_sha,
                    "finalize",
                    tx_id=tx_id,
                    plan_sha256=plan_sha,
                    status_value="rolled_back",
                )
                _node_call_local("finalize", tx_id=tx_id, plan_sha256=plan_sha, status_value="rolled_back")
                _remote_phase(
                    source,
                    source_sha,
                    "release-active",
                    tx_id=tx_id,
                    plan_sha256=plan_sha,
                    status_value="rolled_back",
                )
                _node_call_local("release-active", tx_id=tx_id, plan_sha256=plan_sha, status_value="rolled_back")
            except BaseException:
                rollback_ok = False
        if not rollback_ok:
            # Admission or its acknowledgement may have succeeded on one node.
            # Re-withdraw both before reporting uncertainty so no mixed or
            # partially rolled-back state keeps serving.
            for action in (
                lambda: _node_call_local("redrain", tx_id=tx_id, plan_sha256=plan_sha),
                lambda: _remote_phase(source, source_sha, "redrain", tx_id=tx_id, plan_sha256=plan_sha),
            ):
                try:
                    action()
                except BaseException:
                    pass
            update_coordinator("rollback-uncertain")
            raise RuntimeError(
                "bootstrap outcome or drain parity is uncertain; durable coordinator/guards retained for recovery"
            ) from None
        update_coordinator("rollback-complete")
        _unlink_durable(COORDINATOR_PATH)
        raise RuntimeError("bootstrap failed; both nodes were restored to their exact prior state") from None
    _log(f"one-time Meta HA contract committed; backups retained under {_backup_dir(tx_id)} on each node")
    _log(ROTATION_WARNING)
    _log("next: run the exact distinct-baseline deploy reconciliation mode; routine deploy stays strict")
    return 0


def _orchestrate_recovery(args: argparse.Namespace) -> int:
    if COORDINATOR_PATH.exists() or COORDINATOR_PATH.is_symlink():
        raise RuntimeError("durable bootstrap decision exists; use recover-decided, never force rollback")
    if not TX_RE.fullmatch(args.tx_id):
        raise ValueError("bootstrap recovery transaction ID is invalid")
    _validate_digest(args.plan_sha256, "bootstrap recovery plan digest")
    if args.peer_host != FIXED_NODES["node01"]["peer_ip"]:
        raise RuntimeError("bootstrap recovery peer is not the fixed node02 identity")
    if args.confirm != _recovery_confirmation(args.tx_id, args.plan_sha256):
        raise PermissionError("exact bootstrap rollback recovery confirmation is missing")
    source, source_sha = _helper_source()
    _assert_exact_helper(args.target_sha, source_sha)
    _assert_identity("node01")
    tx_id = args.tx_id
    plan_sha = args.plan_sha256
    local_status = _node_call_local("status", tx_id=tx_id, plan_sha256=plan_sha)
    peer_status = _remote_phase(source, source_sha, "status", tx_id=tx_id, plan_sha256=plan_sha)

    # A standalone rollback may be retried after either node has already
    # completed or crossed the ACTIVE-unlink release boundary.  Only a node
    # that is still active and beyond the prepare-only state may be re-drained;
    # released and release-pending nodes must instead be reconciled by their
    # exact durable receipts below.
    for status, redrain in (
        (
            local_status,
            lambda: _node_call_local("redrain", tx_id=tx_id, plan_sha256=plan_sha),
        ),
        (
            peer_status,
            lambda: _remote_phase(source, source_sha, "redrain", tx_id=tx_id, plan_sha256=plan_sha),
        ),
    ):
        if status["state"] == "active" and status["status"] not in {
            "preparing",
            "prepared",
            "aborted_before_drain",
        }:
            redrain()
    try:
        _recover_decided_node(
            local=False,
            source=source,
            source_sha=source_sha,
            decision="rollback",
            node_id="node02",
            tx_id=tx_id,
            plan_sha=plan_sha,
            expected_pg_state="",
        )
        _recover_decided_node(
            local=True,
            source=source,
            source_sha=source_sha,
            decision="rollback",
            node_id="node01",
            tx_id=tx_id,
            plan_sha=plan_sha,
            expected_pg_state="",
        )
        _public_ready()
    except BaseException:
        for status_call, redrain in (
            (
                lambda: _node_call_local("status", tx_id=tx_id, plan_sha256=plan_sha),
                lambda: _node_call_local("redrain", tx_id=tx_id, plan_sha256=plan_sha),
            ),
            (
                lambda: _remote_phase(source, source_sha, "status", tx_id=tx_id, plan_sha256=plan_sha),
                lambda: _remote_phase(source, source_sha, "redrain", tx_id=tx_id, plan_sha256=plan_sha),
            ),
        ):
            try:
                status = status_call()
                if status["state"] == "active" and status["status"] not in {
                    "preparing",
                    "prepared",
                    "aborted_before_drain",
                }:
                    redrain()
            except BaseException:
                pass
        raise RuntimeError("bootstrap recovery is uncertain; persistent maintenance retained") from None
    _log("exact pre-bootstrap state restored on both nodes; recoverable backups retained")
    return 0


def _decided_recovery_confirmation(tx_id: str, journal_sha256: str, decision: str) -> str:
    return f"RECOVER_BOOTSTRAP_{tx_id[:12].upper()}_{journal_sha256[:12].upper()}_TO_{decision.upper()}"


def _recover_decided_node(
    *,
    local: bool,
    source: bytes,
    source_sha: str,
    decision: str,
    node_id: str,
    tx_id: str,
    plan_sha: str,
    expected_pg_state: str,
) -> None:
    call = _node_call_local if local else lambda command, **kwargs: _remote_phase(source, source_sha, command, **kwargs)
    status = call("status", tx_id=tx_id, plan_sha256=plan_sha)
    if status["state"] == "absent":
        if decision == "rollback":
            return
        raise RuntimeError("commit recovery found a node that was never prepared")
    if status["state"] == "released":
        expected_status = (
            "committed" if decision == "commit" else {"aborted_before_drain", "rolled_back", "recovery_rolled_back"}
        )
        if (isinstance(expected_status, str) and status["status"] != expected_status) or (
            isinstance(expected_status, set) and status["status"] not in expected_status
        ):
            raise RuntimeError("released bootstrap node has the wrong durable decision")
        return
    if status["state"] == "release-pending":
        expected_status = "committed" if decision == "commit" else {"rolled_back", "recovery_rolled_back"}
        if (isinstance(expected_status, str) and status["status"] != expected_status) or (
            isinstance(expected_status, set) and status["status"] not in expected_status
        ):
            raise RuntimeError("pending bootstrap release has the wrong durable decision")
        call(
            "release-active",
            tx_id=tx_id,
            plan_sha256=plan_sha,
            status_value=str(status["status"]),
        )
        return
    if decision == "commit":
        call(
            "admit",
            node_id=node_id,
            tx_id=tx_id,
            plan_sha256=plan_sha,
            expected_pg_state=expected_pg_state,
        )
        call("commit-proof", tx_id=tx_id, plan_sha256=plan_sha)
        call("finalize", tx_id=tx_id, plan_sha256=plan_sha, status_value="committed")
        call("release-active", tx_id=tx_id, plan_sha256=plan_sha, status_value="committed")
        return

    if status["status"] in {"preparing", "prepared", "aborted_before_drain"}:
        try:
            call("abort-prepare", tx_id=tx_id, plan_sha256=plan_sha)
            return
        except BaseException:
            # An ACK can be lost after the drain crossed its mutation boundary
            # but before the node journal advanced. Continue with exact rollback.
            pass
    try:
        call("redrain", tx_id=tx_id, plan_sha256=plan_sha)
    except BaseException:
        call("drain", tx_id=tx_id, plan_sha256=plan_sha)
    call("rollback", node_id=node_id, tx_id=tx_id, plan_sha256=plan_sha)
    call("admit-rollback", tx_id=tx_id, plan_sha256=plan_sha)
    call(
        "finalize",
        tx_id=tx_id,
        plan_sha256=plan_sha,
        status_value="recovery_rolled_back",
    )
    call(
        "release-active",
        tx_id=tx_id,
        plan_sha256=plan_sha,
        status_value="recovery_rolled_back",
    )


def _orchestrate_decided_recovery(args: argparse.Namespace) -> int:
    journal = _read_coordinator_journal(args.journal_sha256)
    source, source_sha = _helper_source()
    if source_sha != journal["source_sha256"]:
        raise RuntimeError("bootstrap recovery helper differs from the durable coordinator")
    _assert_exact_helper(str(journal["target_sha"]), source_sha)
    _assert_identity("node01")
    decision = str(journal["decision"])
    expected_confirmation = _decided_recovery_confirmation(str(journal["tx_id"]), args.journal_sha256, decision)
    if args.confirm != expected_confirmation:
        raise PermissionError("exact digest-bound bootstrap recovery confirmation is missing")
    tx_id = str(journal["tx_id"])
    plan_sha = str(journal["plan_sha256"])
    expected_pg = str(journal["expected_pg_state_sha256"])
    try:
        # Peer first mirrors the normal transaction and is safe to replay after
        # an ACK loss because every node phase is exact-transaction idempotent.
        _recover_decided_node(
            local=False,
            source=source,
            source_sha=source_sha,
            decision=decision,
            node_id="node02",
            tx_id=tx_id,
            plan_sha=plan_sha,
            expected_pg_state=expected_pg,
        )
        _recover_decided_node(
            local=True,
            source=source,
            source_sha=source_sha,
            decision=decision,
            node_id="node01",
            tx_id=tx_id,
            plan_sha=plan_sha,
            expected_pg_state=expected_pg,
        )
        _public_ready()
    except BaseException:
        if decision == "rollback":
            for local in (True, False):
                try:
                    call = (
                        _node_call_local
                        if local
                        else lambda command, **kwargs: _remote_phase(source, source_sha, command, **kwargs)
                    )
                    status = call("status", tx_id=tx_id, plan_sha256=plan_sha)
                    if status["state"] == "active" and status["status"] != "prepared":
                        call("redrain", tx_id=tx_id, plan_sha256=plan_sha)
                except BaseException:
                    pass
        raise RuntimeError(
            f"bootstrap {decision} recovery is incomplete; durable coordinator journal retained"
        ) from None
    _unlink_durable(COORDINATOR_PATH)
    _log(f"durable bootstrap decision={decision} recovered on both fixed nodes")
    return 0


def _decided_recovery_status(args: argparse.Namespace) -> int:
    _validate_sha(args.target_sha, "bootstrap recovery target SHA")
    _secure_regular(COORDINATOR_PATH)
    raw, _ = _read_regular_any_owner(COORDINATOR_PATH)
    digest = _digest_bytes(raw)
    journal = _read_coordinator_journal(digest)
    if journal["target_sha"] != args.target_sha:
        raise RuntimeError("bootstrap recovery status target differs from the durable transaction")
    source, source_sha = _helper_source()
    if source_sha != journal["source_sha256"]:
        raise RuntimeError("bootstrap recovery-status helper differs from the durable transaction")
    _assert_exact_helper(args.target_sha, source_sha)
    confirmation = _decided_recovery_confirmation(str(journal["tx_id"]), digest, str(journal["decision"]))
    print(f"journal_sha256={digest}")
    print(f"decision={journal['decision']}")
    print(f"phase={journal['phase']}")
    print(f"confirmation={confirmation}")
    return 0


def _common_orchestrator_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--expected-node01-sha", required=True)
    parser.add_argument("--expected-node02-sha", required=True)
    parser.add_argument("--expected-pg-state-sha256", required=True)
    parser.add_argument("--expected-lb-ready-sha256", required=True)
    parser.add_argument("--expected-lb-attestation-sha256", required=True)
    parser.add_argument("--lb-ready-attestation", type=Path, required=True)
    parser.add_argument("--node01-hostname", required=True)
    parser.add_argument("--node01-public-ip", required=True)
    parser.add_argument("--node01-private-ip", required=True)
    parser.add_argument("--node02-hostname", required=True)
    parser.add_argument("--node02-public-ip", required=True)
    parser.add_argument("--node02-private-ip", required=True)
    parser.add_argument("--peer-host", required=True)
    parser.add_argument("--drain-seconds", type=int, required=True)


def _validate_explicit_topology(args: argparse.Namespace) -> None:
    _validate_sha(args.target_sha, "target SHA")
    _validate_sha(args.expected_node01_sha, "node01 expected SHA")
    _validate_sha(args.expected_node02_sha, "node02 expected SHA")
    _validate_digest(args.expected_pg_state_sha256, "PostgreSQL state digest")
    _validate_digest(args.expected_lb_ready_sha256, "DigitalOcean ready mutable projection")
    _validate_digest(args.expected_lb_attestation_sha256, "DigitalOcean ready attestation artifact")
    if args.expected_lb_ready_sha256 == "0" * 64 or args.expected_lb_attestation_sha256 == "0" * 64:
        raise RuntimeError("all-zero DigitalOcean attestation digests are never authority")
    if args.lb_ready_attestation != LB_BOOTSTRAP_ATTESTATION_PATH:
        raise PermissionError("bootstrap LB attestation path is not the canonical protected path")
    supplied = {
        "node01_hostname": FIXED_NODES["node01"]["hostname"],
        "node01_public_ip": FIXED_NODES["node01"]["public_ip"],
        "node01_private_ip": FIXED_NODES["node01"]["private_ip"],
        "node02_hostname": FIXED_NODES["node02"]["hostname"],
        "node02_public_ip": FIXED_NODES["node02"]["public_ip"],
        "node02_private_ip": FIXED_NODES["node02"]["private_ip"],
        "peer_host": FIXED_NODES["node01"]["peer_ip"],
        "drain_seconds": 30,
    }
    for attribute, expected in supplied.items():
        if getattr(args, attribute) != expected:
            raise RuntimeError(f"explicit fixed topology value is wrong: {attribute}")


def _node_phase(args: argparse.Namespace) -> int:
    kwargs = {
        key: value
        for key, value in vars(args).items()
        if key
        not in {
            "command",
            "phase",
        }
        and value is not None
    }
    result = _node_call_local(args.phase, **kwargs)
    if isinstance(result, dict):
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="read-only exact two-node/LB/PG plan")
    _common_orchestrator_args(plan)
    apply = commands.add_parser("apply", help="execute the confirmed one-time transaction")
    _common_orchestrator_args(apply)
    apply.add_argument("--expected-plan-sha256", required=True)
    apply.add_argument("--confirm", required=True)
    install_lb = commands.add_parser(
        "install-lb-ready-attestation",
        help="install exact owner-workstation LB attestation bytes through stdin",
    )
    install_lb.add_argument("--target-sha", required=True)
    install_lb.add_argument("--expected-attestation-sha256", required=True)
    install_lb.add_argument("--expected-ready-sha256", required=True)
    install_lb.add_argument("--confirm", required=True)
    recover = commands.add_parser("recover-rollback", help="fail-closed rollback of an interrupted bootstrap")
    recover.add_argument("--target-sha", required=True)
    recover.add_argument("--tx-id", required=True)
    recover.add_argument("--plan-sha256", required=True)
    recover.add_argument("--peer-host", required=True)
    recover.add_argument("--confirm", required=True)
    recover_decided = commands.add_parser(
        "recover-decided",
        help="replay the exact digest-bound durable bootstrap commit/rollback decision",
    )
    recover_decided.add_argument("--journal-sha256", required=True)
    recover_decided.add_argument("--confirm", required=True)
    recovery_status = commands.add_parser(
        "recovery-status",
        help="read the safe digest/decision/confirmation for an interrupted bootstrap",
    )
    recovery_status.add_argument("--target-sha", required=True)
    probe = commands.add_parser("node-probe", help=argparse.SUPPRESS)
    probe.add_argument("--node-id", choices=tuple(FIXED_NODES), required=True)
    probe.add_argument("--expected-sha", required=True)
    phase = commands.add_parser("node-phase", help=argparse.SUPPRESS)
    phase.add_argument(
        "phase",
        choices=(
            "prepare",
            "abort-prepare",
            "drain",
            "apply",
            "verify",
            "admit",
            "redrain",
            "rollback",
            "admit-rollback",
            "commit-proof",
            "finalize",
            "release-active",
            "status",
        ),
    )
    phase.add_argument("--node-id", choices=tuple(FIXED_NODES))
    phase.add_argument("--expected-sha")
    phase.add_argument("--tx-id")
    phase.add_argument("--plan-sha256")
    phase.add_argument("--expected-pg-state")
    phase.add_argument("--expected-probe-sha256")
    phase.add_argument("--status-value")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {
            "plan",
            "apply",
            "install-lb-ready-attestation",
            "recover-rollback",
            "recover-decided",
            "recovery-status",
        }:
            _require_root()
            if args.command in {"plan", "apply"}:
                _validate_explicit_topology(args)
            elif args.command == "install-lb-ready-attestation":
                _validate_sha(args.target_sha, "target SHA")
                _, source_sha = _helper_source()
                _assert_exact_helper(args.target_sha, source_sha)
            elif args.command == "recover-rollback":
                _validate_sha(args.target_sha, "target SHA")
            with _exclusive_lock():
                _assert_authenticated_entry("node01")
                if args.command == "plan":
                    plan, _, _ = _combined_plan(args)
                    plan_sha = _digest(plan)
                    print(f"plan_sha256={plan_sha}")
                    print(f"confirmation={_confirmation(plan_sha)}")
                    print(f"node01_previous_sha={plan['node01']['previous_sha']}")
                    print(f"node02_previous_sha={plan['node02']['previous_sha']}")
                    print(f"postgres_state_sha256={plan['node01']['pg']['state_sha256']}")
                    print(f"digitalocean_ready_mutable_sha256={plan['lb']['owner_attested_ready_mutable_sha256']}")
                    print(f"safe_plan_manifest_json={_canonical(plan).decode('utf-8')}")
                    print(ROTATION_WARNING)
                    return 0
                if args.command == "apply":
                    _validate_digest(args.expected_plan_sha256, "bootstrap plan digest")
                    return _orchestrate_apply(args)
                if args.command == "install-lb-ready-attestation":
                    _install_lb_ready_attestation(
                        args.expected_attestation_sha256,
                        args.expected_ready_sha256,
                        args.confirm,
                    )
                    return 0
                if args.command == "recover-rollback":
                    return _orchestrate_recovery(args)
                if args.command == "recover-decided":
                    _validate_digest(args.journal_sha256, "bootstrap coordinator journal")
                    return _orchestrate_decided_recovery(args)
                return _decided_recovery_status(args)
        if args.command == "node-probe":
            _validate_sha(args.expected_sha, "node expected SHA")
            with _exclusive_lock():
                _assert_authenticated_entry(args.node_id)
                print(json.dumps(_node_probe(args.node_id, args.expected_sha), separators=(",", ":"), sort_keys=True))
            return 0
        if args.command == "node-phase":
            _require_root()
            with _exclusive_lock():
                _assert_authenticated_entry(args.node_id or _local_node_id())
                return _node_phase(args)
        raise AssertionError("unreachable")
    except Exception as exc:  # noqa: BLE001 - never print env values, DSNs, provider bodies, or row data
        print(f"ERROR: Meta HA bootstrap failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
