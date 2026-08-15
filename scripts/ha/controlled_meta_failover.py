#!/usr/bin/env python3
"""Produce signed, crash-recoverable two-node controlled Meta failover proofs.

The operator first creates the controlled evidence manifest, then runs
``plan-initial`` and the digest-confirmed ``prepare-initial`` command before
sending any original events.  ``switch-to-replay`` is allowed only after the
manifest's initial cutoff.  It drains the original node before admitting the
opposite node, so there is never an overlap window.  ``restore-closeout`` is a
separate confirmed operation after evidence collection; it restores both nodes
and signs a closeout bound to the immutable initial and replay proof digests.

No provider credential is used.  The DigitalOcean /api/ready projection is an
exact owner-supplied digest, while direct and public readiness are re-proved at
every phase.  Node and coordinator proofs use independent pinned Ed25519 keys.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import io
import json
import os
import re
import shlex
import stat
import subprocess  # nosec B404 - every executable/remote identity is fixed.
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from dotenv import dotenv_values

SOURCE_ROOT = Path(__file__).resolve().parents[2]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scripts.ha.manage_do_lb_ready_healthcheck import (  # noqa: E402
    FAILOVER_OBSERVATIONS as LB_ATTESTATION_OBSERVATIONS,
)
from scripts.ha.manage_do_lb_ready_healthcheck import (  # noqa: E402
    FAILOVER_PHASES as LB_ATTESTATION_PHASES,
)
from scripts.ha.manage_do_lb_ready_healthcheck import (  # noqa: E402
    _validate_failover_attestation as _validate_lb_failover_attestation,
)
from scripts.ha.manage_do_lb_ready_healthcheck import (  # noqa: E402
    failover_attestation_path_for as _lb_failover_attestation_path_for,
)
from scripts.prod_meta_comment_runtime_probe import (  # noqa: E402
    ControlledEvidenceError,
    parse_controlled_manifest,
)

SCHEMA = "linas-meta-controlled-failover-v1"
STATE_SCHEMA = "linas-meta-controlled-failover-state-v1"
ABORT_SCHEMA = "linas-meta-controlled-failover-abort-v1"
REQUIRED_NODES = ("node01", "node02")
REPO_DIR = Path("/opt/linasbot")
HELPER_PATH = REPO_DIR / "scripts/ha/controlled_meta_failover.py"
ENV_PATH = REPO_DIR / ".env"
STATE_ROOT = Path("/var/lib/linasbot/meta-ha")
EVIDENCE_ROOT = Path("/var/lib/linasbot/meta-evidence/failover")
NODE_SENTINEL = STATE_ROOT / "controlled-failover.active"
RUNTIME_GUARD = STATE_ROOT / "controlled-failover.runtime.guard"
PERSISTENT_MAINTENANCE = STATE_ROOT / "maintenance"
VOLATILE_MAINTENANCE = Path("/run/linasbot-maintenance")
SIGNING_KEY_FILE = STATE_ROOT / "node-signing-key.env"
VERIFICATION_KEYS_FILE = STATE_ROOT / "node-verification-keys.env"
LOCK_FILE = Path("/run/lock/linasbot-meta-live.lock")
MACHINE_ID_FILE = Path("/etc/machine-id")
PROC_ROOT = Path("/proc")
STATIC_GUARD_NAME = "92-meta-controlled-failover.conf"
STATIC_GUARD_PATHS = (
    Path("/etc/systemd/system/linasbot.service.d") / STATIC_GUARD_NAME,
    Path("/etc/systemd/system/linasbot-worker@.service.d") / STATIC_GUARD_NAME,
)
STATIC_GUARD = (
    b"[Unit]\n"
    b"# Permanently installed controlled Meta failover reboot guard.\n"
    b"ConditionPathExists=!/var/lib/linasbot/meta-ha/controlled-failover.runtime.guard\n"
)
API_UNIT = "linasbot.service"
WORKER_QUEUES = ("high_priority", "interactive", "background", "expensive")
WORKER_UNITS = tuple(f"linasbot-worker@{queue}.service" for queue in WORKER_QUEUES)
ALL_UNITS = (API_UNIT, *WORKER_UNITS)
PEER_HOST = "10.106.0.4"
FIXED_HOSTNAMES = {
    "node01": "ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01",
    "node02": "linas-app-lon1-02",
}
COLLISION_PATHS = (
    STATE_ROOT / "bootstrap.active",
    STATE_ROOT / "bootstrap.coordinator.json",
    STATE_ROOT / "deploy.active",
    STATE_ROOT / "deploy-node.active",
    STATE_ROOT / "transaction.json",
    STATE_ROOT / "env.before",
    STATE_ROOT / "rekey/runtime.guard",
    STATE_ROOT / "registry-nfs-retire.active",
    STATE_ROOT / "python-runtime-provision.active",
    STATE_ROOT / "python-runtime-provision.coordinator.json",
)
HA_CONTRACT = {
    "META_DELETION_REQUIRED_NODES": "node01,node02",
    "META_REGISTRY_BACKEND": "postgres",
    "META_HA_LB_READY_HEALTHCHECK_APPROVED": "true",
    "META_HA_LB_DRAIN_SECONDS": "30",
    "LINAS_MAINTENANCE_DRAIN_FILE": str(PERSISTENT_MAINTENANCE),
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
        "MALLOC_TRACE",
        "NLSPATH",
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
    "GIT_CONFIG_",
    "LD_",
    "LINAS_DEPLOY_MUTATION_",
    "LINAS_PRODUCTION_MUTATION_",
)
TX_RE = re.compile(r"mft_[0-9a-f]{64}")
RUN_RE = re.compile(r"mtr_[0-9a-f]{64}")
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
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


class AwaitingPostLBAttestation(RuntimeError):
    """The topology is safely transaction-bound while owner obtains a post-GET."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if _b64encode(decoded) != raw:
        raise ValueError("non-canonical base64")
    return decoded


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(raw: str) -> datetime:
    if TIMESTAMP_RE.fullmatch(raw) is None:
        raise RuntimeError("controlled failover timestamp is invalid")
    return datetime.fromisoformat(raw[:-1] + "+00:00").astimezone(UTC)


def _require_root() -> None:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise PermissionError("controlled failover operations require root")


def _run(argv: list[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout)  # nosec B603
    if check and result.returncode:
        raise RuntimeError("controlled failover command failed: " + Path(argv[0]).name)
    return result


def _secure_directory(path: Path, *, create: bool = False) -> None:
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise PermissionError("controlled failover directory is not root:root mode 0700")


def _secure_file(path: Path) -> os.stat_result:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise PermissionError("controlled failover file is not a private single-link regular file")
    return info


def _read_secure(path: Path, *, limit: int = 65_536) -> bytes:
    before = _secure_file(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise RuntimeError("controlled failover file changed while opening")
        raw = os.read(fd, limit + 1)
        if len(raw) > limit or os.read(fd, 1):
            raise RuntimeError("controlled failover file is too large")
        return raw
    finally:
        os.close(fd)


def _atomic_write(path: Path, payload: bytes, *, no_replace: bool = False) -> None:
    _secure_directory(path.parent, create=True)
    if path.exists() or path.is_symlink():
        if no_replace:
            raise FileExistsError("controlled failover artifact already exists")
        _secure_file(path)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_temp)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, 0, 0)
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        if no_replace:
            os.link(temporary, path, follow_symlinks=False)
        else:
            os.replace(temporary, path)
        _secure_file(path)
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _unlink_durable(path: Path) -> None:
    _secure_file(path)
    path.unlink()
    parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


@contextmanager
def _lock() -> Iterator[None]:
    LOCK_FILE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise PermissionError("shared Meta live lock is unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _parse_env_bytes(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="strict").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            raise RuntimeError("protected environment file contains duplicate keys")
        values[key] = value.strip().strip("\"'")
    return values


def _canonical_env_values() -> dict[str, str]:
    """Read the exact systemd EnvironmentFile without interpolation or races."""

    raw = _read_secure(ENV_PATH)
    # The small parser is intentionally run first to reject duplicate keys;
    # python-dotenv otherwise silently lets the last duplicate win.
    simple = _parse_env_bytes(raw)
    parsed = dotenv_values(stream=io.StringIO(raw.decode("utf-8", errors="strict")), interpolate=False)
    if set(parsed) != set(simple) or any(value is None for value in parsed.values()):
        raise RuntimeError("canonical environment file has unsupported or ambiguous syntax")
    if any(key in FORBIDDEN_EXECUTION_ENV_KEYS or key.startswith(FORBIDDEN_EXECUTION_ENV_PREFIXES) for key in parsed):
        raise RuntimeError("canonical environment contains a forbidden code-loader control")
    return {str(key): str(value) for key, value in parsed.items()}


def _assert_ha_env_contract(node: str) -> dict[str, str]:
    values = _canonical_env_values()
    expected = {
        **HA_CONTRACT,
        "META_DELETION_NODE_ID": node,
        "LINAS_HA_PEER_HOST": "10.106.0.4" if node == "node01" else "10.106.0.3",
    }
    if any(values.get(key) != value for key, value in expected.items()):
        raise RuntimeError("canonical environment does not match the bootstrapped Meta HA contract")
    return values


def _load_private_key() -> Ed25519PrivateKey:
    values = _parse_env_bytes(_read_secure(SIGNING_KEY_FILE, limit=4096))
    if set(values) != {"CREDENTIAL_REKEY_NODE_SIGNING_KEY"}:
        raise RuntimeError("node signing key file has an invalid schema")
    try:
        raw = _b64decode(values["CREDENTIAL_REKEY_NODE_SIGNING_KEY"])
        if len(raw) != 32:
            raise ValueError("wrong length")
        return Ed25519PrivateKey.from_private_bytes(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("node signing key is invalid") from exc


def _load_verification_keys() -> dict[str, Ed25519PublicKey]:
    values = _parse_env_bytes(_read_secure(VERIFICATION_KEYS_FILE, limit=4096))
    names = {node: f"CREDENTIAL_REKEY_{node.upper()}_VERIFY_KEY" for node in REQUIRED_NODES}
    if set(values) != set(names.values()):
        raise RuntimeError("node verification key file must pin exactly node01 and node02")
    keys: dict[str, Ed25519PublicKey] = {}
    raws: list[bytes] = []
    try:
        for node, name in names.items():
            raw = _b64decode(values[name])
            if len(raw) != 32:
                raise ValueError("wrong length")
            raws.append(raw)
            keys[node] = Ed25519PublicKey.from_public_bytes(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("node verification key set is invalid") from exc
    if hmac.compare_digest(raws[0], raws[1]):
        raise RuntimeError("fixed nodes must use independent signing keys")
    return keys


def _public_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _node_id() -> str:
    values = _canonical_env_values()
    node = values.get("META_DELETION_NODE_ID", "")
    if node not in REQUIRED_NODES:
        raise RuntimeError("canonical environment has no fixed HA node identity")
    if _run(["/bin/hostname", "-s"]).stdout.strip() != FIXED_HOSTNAMES[node]:
        raise RuntimeError("fixed HA hostname does not match the canonical node identity")
    return node


def _require_matching_key(node: str) -> tuple[Ed25519PrivateKey, dict[str, Ed25519PublicKey]]:
    private = _load_private_key()
    keys = _load_verification_keys()
    if not hmac.compare_digest(_public_bytes(private.public_key()), _public_bytes(keys[node])):
        raise PermissionError("node private signing key does not match its pinned public identity")
    return private, keys


def _generate_node_key(node_id: str, confirm: str) -> None:
    actual_node = _node_id()
    if node_id != actual_node or confirm != f"GENERATE_HA_NODE_SIGNING_KEY_{node_id.upper()}":
        raise PermissionError("exact fixed-node signing-key generation confirmation is missing")
    _secure_directory(STATE_ROOT, create=True)
    if SIGNING_KEY_FILE.exists() or SIGNING_KEY_FILE.is_symlink():
        private = _load_private_key()
    else:
        private = Ed25519PrivateKey.generate()
        raw = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        payload = f"CREDENTIAL_REKEY_NODE_SIGNING_KEY={_b64encode(raw)}\n".encode("ascii")
        _atomic_write(SIGNING_KEY_FILE, payload, no_replace=True)
        private = _load_private_key()
    public = _b64encode(_public_bytes(private.public_key()))
    print(f"node_id={node_id}")
    print(f"node_public_verify_key={public}")
    print(f"node_public_verify_key_sha256={_digest(_public_bytes(private.public_key()))}")


def _install_verification_keys(node01_public: str, node02_public: str, confirm: str) -> None:
    supplied = {"node01": node01_public, "node02": node02_public}
    raw_keys: dict[str, bytes] = {}
    try:
        for node, raw in supplied.items():
            decoded = _b64decode(raw)
            if len(decoded) != 32:
                raise ValueError("wrong length")
            Ed25519PublicKey.from_public_bytes(decoded)
            raw_keys[node] = decoded
    except ValueError as exc:
        raise RuntimeError("supplied fixed-node verification key is invalid") from exc
    if hmac.compare_digest(raw_keys["node01"], raw_keys["node02"]):
        raise RuntimeError("fixed nodes must use independent signing keys")
    projection = {node: _b64encode(raw_keys[node]) for node in REQUIRED_NODES}
    digest = _digest(projection)
    if confirm != f"INSTALL_HA_NODE_VERIFICATION_KEYS_{digest[:16].upper()}":
        raise PermissionError("exact two-node verification-key installation confirmation is missing")
    local_node = _node_id()
    private = _load_private_key()
    if not hmac.compare_digest(_public_bytes(private.public_key()), raw_keys[local_node]):
        raise PermissionError("local private key does not match its pinned supplied public key")
    payload = (
        f"CREDENTIAL_REKEY_NODE01_VERIFY_KEY={projection['node01']}\n"
        f"CREDENTIAL_REKEY_NODE02_VERIFY_KEY={projection['node02']}\n"
    ).encode("ascii")
    if VERIFICATION_KEYS_FILE.exists() or VERIFICATION_KEYS_FILE.is_symlink():
        if not hmac.compare_digest(_read_secure(VERIFICATION_KEYS_FILE), payload):
            raise RuntimeError("installed fixed-node verification keys differ; rotation needs a separate transaction")
    else:
        _atomic_write(VERIFICATION_KEYS_FILE, payload, no_replace=True)
    _require_matching_key(local_node)
    print(f"verification_set_sha256={digest}")


def _verification_key_install_plan(node01_public: str, node02_public: str) -> tuple[str, str]:
    projection: dict[str, str] = {}
    decoded_keys: list[bytes] = []
    try:
        for node, raw in (("node01", node01_public), ("node02", node02_public)):
            decoded = _b64decode(raw)
            if len(decoded) != 32:
                raise ValueError("wrong length")
            Ed25519PublicKey.from_public_bytes(decoded)
            decoded_keys.append(decoded)
            projection[node] = _b64encode(decoded)
    except ValueError as exc:
        raise RuntimeError("supplied fixed-node verification key is invalid") from exc
    if hmac.compare_digest(decoded_keys[0], decoded_keys[1]):
        raise RuntimeError("fixed nodes must use independent signing keys")
    digest = _digest(projection)
    return digest, f"INSTALL_HA_NODE_VERIFICATION_KEYS_{digest[:16].upper()}"


def _machine_id_sha256() -> str:
    info = MACHINE_ID_FILE.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise PermissionError("machine identity file is unsafe")
    raw = MACHINE_ID_FILE.read_bytes().strip()
    if len(raw) < 16:
        raise RuntimeError("machine identity is invalid")
    return hashlib.sha256(b"linas-node-machine-id-v1\0" + raw).hexdigest()


def _release_sha() -> str:
    head = _run(["/usr/bin/git", "-C", str(REPO_DIR), "rev-parse", "HEAD"]).stdout.strip()
    if SHA_RE.fullmatch(head) is None:
        raise RuntimeError("canonical release SHA is invalid")
    for args in (("diff", "--quiet", head, "--"), ("diff", "--cached", "--quiet", head, "--")):
        if _run(["/usr/bin/git", "-C", str(REPO_DIR), *args], check=False).returncode:
            raise RuntimeError("canonical release tree is dirty")
    return head


def _assert_no_untracked_runtime() -> None:
    pathspecs = (
        "*.py",
        "*.pyi",
        "*.so",
        "*.pth",
        "*.sh",
        "*.bash",
        "*.zsh",
        "*.yml",
        "*.yaml",
        "*.toml",
        "*.ini",
        "*.cfg",
        "*.conf",
        "*.service",
        "*.js",
        "*.mjs",
        "*.cjs",
        "*.ts",
        "*.tsx",
        "*.jsx",
        "*.html",
        "*.css",
        "*.scss",
        "*.sql",
        ":(exclude)venv/**",
        ":(exclude).venv/**",
        ":(exclude)dashboard/node_modules/**",
        ":(exclude)dashboard/build/**",
        ":(exclude)**/node_modules/**",
        ":(exclude)**/__pycache__/**",
    )
    candidates: set[str] = set()
    for ignored in (False, True):
        argv = ["/usr/bin/git", "-C", str(REPO_DIR), "ls-files", "--others", "-z"]
        if ignored:
            argv.append("--ignored")
        argv.extend(["--exclude-standard", "--", *pathspecs])
        output = _run(argv).stdout
        candidates.update(path for path in output.split("\0") if path)
    for ignored in (False, True):
        argv = ["/usr/bin/git", "-C", str(REPO_DIR), "ls-files", "--others", "-z"]
        if ignored:
            argv.append("--ignored")
        argv.append("--exclude-standard")
        for relative in (path for path in _run(argv).stdout.split("\0") if path):
            if relative.startswith(("venv/", ".venv/", "dashboard/node_modules/", "dashboard/build/")):
                continue
            if "/node_modules/" in relative or "/__pycache__/" in relative:
                continue
            path = REPO_DIR / relative
            if path.is_symlink() or (path.is_file() and os.access(path, os.X_OK)):
                candidates.add(relative)
    if candidates:
        # This is read-only and deliberately leaves every byte in place for the
        # owner to archive/remediate through the deploy transaction.
        raise RuntimeError("untracked importable or executable runtime paths require owner remediation")


def _helper_sha256() -> str:
    if HELPER_PATH.resolve(strict=True) != HELPER_PATH:
        raise RuntimeError("controlled failover helper path is noncanonical")
    return _digest(HELPER_PATH.read_bytes())


def _transaction_dir(transaction_id: str) -> Path:
    if TX_RE.fullmatch(transaction_id) is None:
        raise ValueError("controlled failover transaction ID is invalid")
    return EVIDENCE_ROOT / transaction_id


def _journal_path(transaction_id: str) -> Path:
    return _transaction_dir(transaction_id) / "transaction.json"


def _proof_path(transaction_id: str, phase: str) -> Path:
    if phase not in {"initial", "replay", "closeout"}:
        raise ValueError("controlled failover proof phase is invalid")
    return _transaction_dir(transaction_id) / f"{phase}.json"


def _abort_path(transaction_id: str) -> Path:
    return _transaction_dir(transaction_id) / "abort.json"


def _validate_context(context: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "transaction_id",
        "test_run_id",
        "manifest_sha256",
        "release_sha",
        "initial_node",
        "replay_node",
        "lb_ready_projection_sha256",
        "minimum_drain_seconds",
        "manifest_start",
        "manifest_initial_cutoff",
        "manifest_final_cutoff",
        "helper_sha256",
    }
    if set(context) != expected:
        raise RuntimeError("controlled failover context fields are invalid")
    normalized = dict(context)
    if TX_RE.fullmatch(str(normalized["transaction_id"])) is None:
        raise RuntimeError("controlled failover transaction identity is invalid")
    if RUN_RE.fullmatch(str(normalized["test_run_id"])) is None:
        raise RuntimeError("controlled failover test run identity is invalid")
    for key in ("manifest_sha256", "lb_ready_projection_sha256", "helper_sha256"):
        if DIGEST_RE.fullmatch(str(normalized[key])) is None:
            raise RuntimeError("controlled failover digest is invalid")
    if SHA_RE.fullmatch(str(normalized["release_sha"])) is None:
        raise RuntimeError("controlled failover release SHA is invalid")
    if {normalized["initial_node"], normalized["replay_node"]} != set(REQUIRED_NODES):
        raise RuntimeError("controlled failover node ordering is invalid")
    drain = normalized["minimum_drain_seconds"]
    if isinstance(drain, bool) or not isinstance(drain, int) or not 30 <= drain <= 300:
        raise RuntimeError("controlled failover drain interval is invalid")
    manifest_start = _parse_time(str(normalized["manifest_start"]))
    initial_cutoff = _parse_time(str(normalized["manifest_initial_cutoff"]))
    final_cutoff = _parse_time(str(normalized["manifest_final_cutoff"]))
    if not manifest_start < initial_cutoff < final_cutoff:
        raise RuntimeError("controlled failover manifest cutoffs are invalid")
    return normalized


def _read_manifest(
    path: Path,
    expected_sha256: str,
    *,
    transaction_id: str,
    initial_node: str,
) -> dict[str, Any]:
    if DIGEST_RE.fullmatch(expected_sha256) is None:
        raise ValueError("manifest digest is invalid")
    raw = _read_secure(path)
    if not hmac.compare_digest(_digest(raw), expected_sha256):
        raise RuntimeError("controlled evidence manifest digest changed")
    try:
        manifest = parse_controlled_manifest(raw)
    except ControlledEvidenceError as exc:
        raise RuntimeError(f"controlled evidence manifest is invalid: {exc}") from exc
    replay_node = "node02" if initial_node == "node01" else "node01"
    if (
        manifest.failover_transaction_id != transaction_id
        or manifest.initial_node != initial_node
        or manifest.replay_node != replay_node
    ):
        raise RuntimeError("controlled evidence manifest topology differs from the requested failover")
    return {
        "test_run_id": manifest.test_run_id,
        "release_sha": manifest.release_sha,
        "replay_node": replay_node,
        "start": manifest.start.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "initial_cutoff": manifest.initial_cutoff.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "final_cutoff": manifest.final_cutoff.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def _read_lb_attestation(
    path: Path,
    *,
    transaction_id: str,
    manifest_sha256: str,
    phase: str,
    observation: str,
    manifest_start: str,
    manifest_initial_cutoff: str,
    manifest_final_cutoff: str,
    require_fresh: bool,
) -> tuple[str, int, str, str]:
    raw = _read_secure(path)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("protected LB readiness attestation is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("protected LB readiness attestation is not an object")
    digest = str(payload.get("ready_mutable_sha256") or "")
    if DIGEST_RE.fullmatch(digest) is None:
        raise RuntimeError("protected LB readiness projection digest is invalid")
    _validate_lb_failover_attestation(
        payload,
        transaction_id=transaction_id,
        manifest_sha256=manifest_sha256,
        ready_sha256=digest,
        phase=phase,
        observation=observation,
    )
    expected_path = _lb_failover_attestation_path_for(transaction_id, manifest_sha256, phase, observation, STATE_ROOT)
    if path != expected_path or path.resolve(strict=True) != expected_path:
        raise PermissionError("LB readiness attestation path is not the exact transaction-bound canonical path")
    observed_at = _parse_time(str(payload["observed_at"]))
    start = _parse_time(manifest_start)
    initial_cutoff = _parse_time(manifest_initial_cutoff)
    final_cutoff = _parse_time(manifest_final_cutoff)
    now = datetime.now(UTC)
    if phase == "initial":
        if observed_at > start or (start - observed_at).total_seconds() > 600:
            raise RuntimeError("LB readiness observation is outside the manifest initial-proof window")
    elif phase == "replay":
        if not initial_cutoff <= observed_at < final_cutoff:
            raise RuntimeError("LB readiness observation is outside the manifest replay-proof window")
    elif phase == "closeout":
        if observed_at < final_cutoff:
            raise RuntimeError("LB readiness observation predates the manifest closeout window")
    else:
        raise RuntimeError("LB readiness attestation phase is invalid")
    if require_fresh and (observed_at > now + timedelta(seconds=30) or (now - observed_at).total_seconds() > 300):
        raise RuntimeError("LB readiness observation is not fresh enough for a live failover plan")
    base = payload["ready_attestation"]
    health = base["health_check"]
    if health != {
        "protocol": "http",
        "port": 8003,
        "path": "/api/ready",
        "check_interval_seconds": 5,
        "response_timeout_seconds": 3,
        "healthy_threshold": 2,
        "unhealthy_threshold": 3,
    }:
        raise RuntimeError("protected LB readiness attestation health contract is invalid")
    minimum_drain = max(30, int(health["check_interval_seconds"]) * int(health["unhealthy_threshold"]) + 10)
    return digest, minimum_drain, _digest(raw), str(payload["observed_at"])


def _assert_context_lb_attestation(
    context: Mapping[str, Any],
    phase: str = "initial",
    observation: str = "pre",
    *,
    require_fresh: bool = False,
) -> tuple[str, str]:
    digest = str(context["lb_ready_projection_sha256"])
    path = _lb_failover_attestation_path_for(
        str(context["transaction_id"]),
        str(context["manifest_sha256"]),
        phase,
        observation,
        STATE_ROOT,
    )
    observed_digest, minimum_drain, artifact_sha256, observed_at = _read_lb_attestation(
        path,
        transaction_id=str(context["transaction_id"]),
        manifest_sha256=str(context["manifest_sha256"]),
        phase=phase,
        observation=observation,
        manifest_start=str(context["manifest_start"]),
        manifest_initial_cutoff=str(context["manifest_initial_cutoff"]),
        manifest_final_cutoff=str(context["manifest_final_cutoff"]),
        require_fresh=require_fresh,
    )
    if not hmac.compare_digest(observed_digest, digest) or minimum_drain != context["minimum_drain_seconds"]:
        raise RuntimeError("protected LB readiness attestation differs from the failover context")
    return artifact_sha256, observed_at


def _assert_supplied_phase_lb_attestation(
    context: Mapping[str, Any],
    path: Path,
    phase: str,
    observation: str,
) -> tuple[str, str]:
    expected = _lb_failover_attestation_path_for(
        str(context["transaction_id"]),
        str(context["manifest_sha256"]),
        phase,
        observation,
        STATE_ROOT,
    )
    if path != expected:
        raise PermissionError("phase LB readiness attestation path is not canonical")
    return _assert_context_lb_attestation(context, phase, observation, require_fresh=True)


def _post_transition_lb_binding(
    context: Mapping[str, Any],
    phase: str,
    topology_transition_at: str,
) -> tuple[str, str]:
    transition = _parse_time(topology_transition_at)
    try:
        artifact_sha256, observed_at = _assert_context_lb_attestation(context, phase, "post", require_fresh=True)
    except FileNotFoundError as exc:
        raise AwaitingPostLBAttestation(f"fresh {phase} post-transition LB attestation is required") from exc
    except RuntimeError as exc:
        if "not fresh enough" in str(exc):
            raise AwaitingPostLBAttestation(f"fresh {phase} post-transition LB attestation is required") from exc
        raise
    if _parse_time(observed_at) <= transition:
        raise AwaitingPostLBAttestation(
            f"{phase} post-transition LB attestation does not strictly follow the durable topology transition"
        )
    return artifact_sha256, observed_at


def _install_lb_attestation(
    expected_digest: str,
    expected_attestation_sha256: str,
    transaction_id: str,
    manifest_sha256: str,
    phase: str,
    observation: str,
    manifest_start: str,
    manifest_initial_cutoff: str,
    manifest_final_cutoff: str,
    confirm: str,
) -> None:
    if DIGEST_RE.fullmatch(expected_digest) is None:
        raise ValueError("expected LB readiness projection digest is invalid")
    if DIGEST_RE.fullmatch(expected_attestation_sha256) is None:
        raise ValueError("expected LB readiness attestation digest is invalid")
    if TX_RE.fullmatch(transaction_id) is None or DIGEST_RE.fullmatch(manifest_sha256) is None:
        raise ValueError("LB readiness attestation manifest/transaction binding is invalid")
    if phase not in LB_ATTESTATION_PHASES:
        raise ValueError("LB readiness attestation phase is invalid")
    if observation not in LB_ATTESTATION_OBSERVATIONS:
        raise ValueError("LB readiness attestation observation is invalid")
    _parse_time(manifest_start)
    _parse_time(manifest_initial_cutoff)
    _parse_time(manifest_final_cutoff)
    expected_confirm = (
        f"INSTALL_LB_FAILOVER_{phase.upper()}_{observation.upper()}_ATTESTATION_"
        f"{expected_attestation_sha256[:16].upper()}_{expected_digest[:16].upper()}_"
        f"{manifest_sha256[:8].upper()}_{transaction_id[-8:].upper()}"
    )
    if confirm != expected_confirm:
        raise PermissionError("exact LB readiness attestation installation confirmation is missing")
    raw = sys.stdin.buffer.read(65_537)
    if not raw or len(raw) > 65_536 or sys.stdin.buffer.read(1):
        raise RuntimeError("LB readiness attestation input size is invalid")
    if not hmac.compare_digest(_digest(raw), expected_attestation_sha256):
        raise RuntimeError("LB readiness attestation input digest changed")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("LB readiness attestation input is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("LB readiness attestation input is not an object")
    _validate_lb_failover_attestation(
        payload,
        transaction_id=transaction_id,
        manifest_sha256=manifest_sha256,
        ready_sha256=expected_digest,
        phase=phase,
        observation=observation,
    )
    base = payload.get("ready_attestation")
    health = base.get("health_check") if isinstance(base, dict) else None
    if health != {
        "protocol": "http",
        "port": 8003,
        "path": "/api/ready",
        "check_interval_seconds": 5,
        "response_timeout_seconds": 3,
        "healthy_threshold": 2,
        "unhealthy_threshold": 3,
    }:
        raise RuntimeError("LB readiness attestation input has the wrong health contract")
    destination = _lb_failover_attestation_path_for(transaction_id, manifest_sha256, phase, observation, STATE_ROOT)
    encoded = _canonical(payload) + b"\n"
    if destination.exists() or destination.is_symlink():
        current = _read_secure(destination)
        if not hmac.compare_digest(current, encoded):
            # A fresh provider observation for the same phase may replace only
            # this exact canonical artifact under a new digest-bound confirmation.
            _atomic_write(destination, encoded)
    else:
        _atomic_write(destination, encoded, no_replace=True)
    _read_lb_attestation(
        destination,
        transaction_id=transaction_id,
        manifest_sha256=manifest_sha256,
        phase=phase,
        observation=observation,
        manifest_start=manifest_start,
        manifest_initial_cutoff=manifest_initial_cutoff,
        manifest_final_cutoff=manifest_final_cutoff,
        require_fresh=True,
    )
    print(f"lb_ready_attestation={destination}")
    print(f"phase={phase}")
    print(f"observation={observation}")
    print(f"lb_attestation_sha256={expected_attestation_sha256}")
    print(f"lb_ready_projection_sha256={expected_digest}")


def _context_b64(context: Mapping[str, Any]) -> str:
    return _b64encode(_canonical(context))


def _context_from_b64(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(_b64decode(raw))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("controlled failover context transport is invalid") from exc
    if not isinstance(value, dict):
        raise RuntimeError("controlled failover context transport is invalid")
    return _validate_context(value)


def _assert_no_collision(context: Mapping[str, Any] | None = None) -> None:
    _secure_directory(STATE_ROOT)
    for path in COLLISION_PATHS:
        if path.exists() or path.is_symlink():
            raise RuntimeError("another Meta HA transaction is active or requires recovery")
    if NODE_SENTINEL.exists() or NODE_SENTINEL.is_symlink():
        if context is None:
            raise RuntimeError("a controlled failover transaction already requires recovery")
        existing = json.loads(_read_secure(NODE_SENTINEL))
        if existing != context:
            raise RuntimeError("controlled failover sentinel belongs to another transaction")
    elif context is not None and (
        PERSISTENT_MAINTENANCE.exists()
        or PERSISTENT_MAINTENANCE.is_symlink()
        or VOLATILE_MAINTENANCE.exists()
        or VOLATILE_MAINTENANCE.is_symlink()
    ):
        raise RuntimeError("maintenance exists without the controlled failover sentinel")
    if RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink():
        if context is None or not (NODE_SENTINEL.exists() or NODE_SENTINEL.is_symlink()):
            raise RuntimeError("controlled failover runtime guard exists without its exact transaction")
        _read_runtime_guard(context)


def _arm_sentinel(context: Mapping[str, Any]) -> None:
    _assert_no_collision(context)
    if NODE_SENTINEL.exists():
        return
    _atomic_write(NODE_SENTINEL, _canonical(context) + b"\n", no_replace=True)


def _service_state_path(context: Mapping[str, Any]) -> Path:
    return _transaction_dir(str(context["transaction_id"])) / "service-state.json"


def _admission_state_path(context: Mapping[str, Any]) -> Path:
    return _transaction_dir(str(context["transaction_id"])) / "node-admission.json"


def _read_admission_state(context: Mapping[str, Any]) -> str:
    path = _admission_state_path(context)
    if not (path.exists() or path.is_symlink()):
        return ""
    payload = json.loads(_read_secure(path))
    expected = {
        "schema": 1,
        "transaction_id": context["transaction_id"],
        "context_sha256": _digest(context),
        "node_id": _node_id(),
    }
    if not isinstance(payload, dict) or {key: payload.get(key) for key in expected} != expected:
        raise RuntimeError("controlled failover node admission state is invalid")
    status = str(payload.get("status") or "")
    if set(payload) != set(expected) | {"status"} or status not in {"processes-proved", "enabled"}:
        raise RuntimeError("controlled failover node admission status is invalid")
    return status


def _write_admission_state(context: Mapping[str, Any], status: str) -> None:
    if status not in {"processes-proved", "enabled"}:
        raise ValueError("controlled failover node admission status is invalid")
    current = _read_admission_state(context)
    if current == "enabled" and status == "processes-proved":
        return
    payload = {
        "schema": 1,
        "transaction_id": context["transaction_id"],
        "context_sha256": _digest(context),
        "node_id": _node_id(),
        "status": status,
    }
    _atomic_write(_admission_state_path(context), _canonical(payload) + b"\n")


def _capture_service_state(context: Mapping[str, Any]) -> None:
    path = _service_state_path(context)
    if path.exists() or path.is_symlink():
        states = json.loads(_read_secure(path))
        if (
            not isinstance(states, dict)
            or set(states) != set(ALL_UNITS)
            or any(state != {"active": "active", "enabled": "enabled"} for state in states.values())
        ):
            raise RuntimeError("controlled failover saved service state is invalid")
        return
    states = {
        unit: {
            "active": _run(["/usr/bin/systemctl", "is-active", unit], check=False).stdout.strip(),
            "enabled": _run(["/usr/bin/systemctl", "is-enabled", unit], check=False).stdout.strip(),
        }
        for unit in ALL_UNITS
    }
    if any(state != {"active": "active", "enabled": "enabled"} for state in states.values()):
        raise RuntimeError("controlled failover requires API and all four workers active and enabled")
    _atomic_write(path, _canonical(states) + b"\n", no_replace=True)


def _read_static_guard(path: Path) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o644
        or before.st_nlink != 1
    ):
        raise PermissionError("controlled failover static guard is not root:root mode 0644")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise RuntimeError("controlled failover static guard changed while opening")
        payload = os.read(fd, 4097)
        if len(payload) > 4096 or os.read(fd, 1):
            raise RuntimeError("controlled failover static guard is too large")
        return payload
    finally:
        os.close(fd)


def _assert_static_guard_contract() -> None:
    """Require the permanent two-unit reboot guard installed by HA bootstrap.

    A failover transaction never creates or removes these drop-ins.  Requiring
    both exact, already-loaded files avoids every partial multi-file install
    prefix during a live topology transition.
    """

    for path in STATIC_GUARD_PATHS:
        if _read_static_guard(path) != STATIC_GUARD:
            raise RuntimeError("controlled failover static guard changed")
    for unit in ALL_UNITS:
        if _run(["/usr/bin/systemctl", "show", unit, "--property=NeedDaemonReload", "--value"]).stdout.strip() != "no":
            raise RuntimeError("controlled failover static guard is not loaded")


def _runtime_guard_payload(context: Mapping[str, Any]) -> bytes:
    return (
        _canonical(
            {
                "schema": 1,
                "transaction_id": context["transaction_id"],
                "context_sha256": _digest(context),
                "node_id": _node_id(),
                "status": "drain-intent",
            }
        )
        + b"\n"
    )


def _read_runtime_guard(context: Mapping[str, Any]) -> None:
    if _read_secure(RUNTIME_GUARD) != _runtime_guard_payload(context):
        raise RuntimeError("controlled failover runtime guard belongs to another transaction")


def _arm_runtime_guard(context: Mapping[str, Any]) -> None:
    payload = _runtime_guard_payload(context)
    if RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink():
        _read_runtime_guard(context)
        return
    _atomic_write(RUNTIME_GUARD, payload, no_replace=True)


def _unlink_runtime_guard(context: Mapping[str, Any]) -> None:
    if not (RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink()):
        return
    _read_runtime_guard(context)
    _unlink_durable(RUNTIME_GUARD)


def _arm_marker(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _secure_file(path)
        return
    _atomic_write(path, b"controlled-meta-failover\n", no_replace=True)


def _assert_ready_payload(payload: Any, status: int, *, public: bool = False) -> None:
    if not isinstance(payload, dict) or set(payload) != {"ok", "role", "checks"}:
        raise RuntimeError("readiness payload has an invalid closed schema")
    if status == 503:
        if public or payload != {
            "ok": False,
            "role": "readiness",
            "checks": {"maintenance": {"ok": False}},
        }:
            raise RuntimeError("maintenance readiness payload is invalid")
        return
    checks = payload.get("checks")
    if (
        status != 200
        or payload.get("ok") is not True
        or payload.get("role") != "readiness"
        or not isinstance(checks, dict)
        or not checks
        or any(not isinstance(check, dict) or check.get("ok") is not True for check in checks.values())
    ):
        raise RuntimeError("healthy readiness payload is invalid")


def _direct_ready_status() -> int:
    request = urllib.request.Request("http://127.0.0.1:8003/api/ready", headers={"User-Agent": "meta-ha-proof/1"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
            _assert_ready_payload(payload, response.status)
            return int(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            try:
                payload = json.loads(exc.read())
            except (UnicodeDecodeError, json.JSONDecodeError) as parse_exc:
                raise RuntimeError("direct maintenance readiness payload is invalid") from parse_exc
            try:
                _assert_ready_payload(payload, exc.code)
            except RuntimeError as payload_exc:
                raise payload_exc from exc
            return int(exc.code)
        raise RuntimeError("direct readiness returned an unexpected status") from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise RuntimeError("direct readiness is unavailable") from exc


def _public_ready_status() -> int:
    request = urllib.request.Request("https://linasaibot.com/api/ready", headers={"User-Agent": "meta-ha-proof/1"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
            _assert_ready_payload(payload, response.status, public=True)
            return int(response.status)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise RuntimeError("public readiness is unavailable") from exc


def _assert_processes_ready() -> None:
    node = _node_id()
    env_expected = _assert_ha_env_contract(node)
    env_expected.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PATH": f"{REPO_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin",
        }
    )
    specs: dict[str, tuple[list[str], str | None]] = {
        API_UNIT: ([str(REPO_DIR / "venv/bin/python"), "main.py"], None),
    }
    for queue, unit in zip(WORKER_QUEUES, WORKER_UNITS, strict=True):
        specs[unit] = (
            [str(REPO_DIR / "venv/bin/python"), "scripts/run_queue_worker.py", "--queue", queue],
            queue,
        )
    for unit, (expected_argv, expected_queue) in specs.items():
        if _run(["/usr/bin/systemctl", "is-active", unit], check=False).returncode:
            raise RuntimeError("controlled failover canonical process is inactive: " + unit)
        working_directory = _run(
            ["/usr/bin/systemctl", "show", unit, "--property=WorkingDirectory", "--value"]
        ).stdout.strip()
        if working_directory != str(REPO_DIR):
            raise RuntimeError("controlled failover canonical unit WorkingDirectory is invalid")
        environment_files = _run(
            ["/usr/bin/systemctl", "show", unit, "--property=EnvironmentFiles", "--value"]
        ).stdout.strip()
        if environment_files != f"{ENV_PATH} (ignore_errors=yes)":
            raise RuntimeError("controlled failover canonical unit EnvironmentFile is invalid")
        exec_start = _run(["/usr/bin/systemctl", "show", unit, "--property=ExecStart", "--value"]).stdout.strip()
        argv_match = re.search(r"(?:^|; )argv\[\]=(.+?) ;", exec_start)
        if argv_match is None or shlex.split(argv_match.group(1)) != expected_argv:
            raise RuntimeError("controlled failover canonical unit ExecStart/queue is invalid")
        if _run(["/usr/bin/systemctl", "show", unit, "--property=NeedDaemonReload", "--value"]).stdout.strip() != "no":
            raise RuntimeError("controlled failover canonical unit has an unloaded disk change")
        pid = _run(["/usr/bin/systemctl", "show", unit, "--property=MainPID", "--value"]).stdout.strip()
        if not pid.isdigit() or int(pid) <= 0:
            raise RuntimeError("controlled failover canonical process has no MainPID")
        proc = PROC_ROOT / pid
        argv = [part.decode("utf-8", errors="strict") for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
        if argv != expected_argv:
            raise RuntimeError("controlled failover canonical process argv/queue identity is invalid")
        cwd = Path(os.path.realpath(proc / "cwd"))
        if cwd != REPO_DIR:
            raise RuntimeError("controlled failover canonical process cwd is invalid")
        process_values: dict[str, str] = {}
        for entry in (proc / "environ").read_bytes().split(b"\0"):
            if not entry:
                continue
            if b"=" not in entry:
                raise RuntimeError("controlled failover canonical process environment is malformed")
            key, value = entry.split(b"=", 1)
            decoded_key = key.decode(errors="strict")
            if decoded_key in process_values:
                raise RuntimeError("controlled failover canonical process environment has a duplicate key")
            process_values[decoded_key] = value.decode(errors="strict")
        live_forbidden = FORBIDDEN_EXECUTION_ENV_KEYS - {"PATH"}
        if any(key in live_forbidden or key.startswith(FORBIDDEN_EXECUTION_ENV_PREFIXES) for key in process_values):
            raise RuntimeError("controlled failover canonical process has an execution-control key")
        expected = dict(env_expected)
        if expected_queue is not None:
            expected["LINAS_WORKER_QUEUE"] = expected_queue
        if any(process_values.get(key) != value for key, value in expected.items()):
            raise RuntimeError("controlled failover canonical process environment is stale")
        stable_pid = _run(["/usr/bin/systemctl", "show", unit, "--property=MainPID", "--value"]).stdout.strip()
        if stable_pid != pid or _run(["/usr/bin/systemctl", "is-active", unit], check=False).returncode:
            raise RuntimeError("controlled failover canonical process changed during verification")
    request = urllib.request.Request(
        "http://127.0.0.1:8003/api/queue/ready",
        headers={"User-Agent": "meta-ha-proof/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise RuntimeError("controlled failover queue readiness is unavailable") from exc
    if payload != {
        "ok": True,
        "role": "queue_readiness",
        "backend": "redis",
        "production_ready": True,
        "redis_required": True,
        "redis_configured": True,
    }:
        raise RuntimeError("controlled failover durable queue readiness payload is invalid")


def _node_arm(context: Mapping[str, Any]) -> None:
    _assert_no_collision(context)
    if _release_sha() != context["release_sha"] or _helper_sha256() != context["helper_sha256"]:
        raise RuntimeError("controlled failover node release/helper differs from its manifest")
    node = _node_id()
    _assert_ha_env_contract(node)
    _assert_context_lb_attestation(context)
    _assert_no_untracked_runtime()
    _require_matching_key(node)
    _assert_static_guard_contract()
    _capture_service_state(context)
    _arm_sentinel(context)


def _node_preflight(context: Mapping[str, Any]) -> dict[str, Any]:
    _assert_no_collision()
    node = _node_id()
    release = _release_sha()
    helper = _helper_sha256()
    if release != context["release_sha"] or helper != context["helper_sha256"]:
        raise RuntimeError("controlled failover node release/helper differs from its manifest")
    _assert_ha_env_contract(node)
    _assert_context_lb_attestation(context)
    _assert_no_untracked_runtime()
    _require_matching_key(node)
    _assert_static_guard_contract()
    if _direct_ready_status() != 200:
        raise RuntimeError("controlled failover preflight requires direct readiness 200")
    _assert_processes_ready()
    for unit in ALL_UNITS:
        if _run(["/usr/bin/systemctl", "is-enabled", unit], check=False).returncode:
            raise RuntimeError("controlled failover preflight requires every canonical unit enabled")
    return {
        "node_id": node,
        "release_sha": release,
        "helper_sha256": helper,
        "machine_id_sha256": _machine_id_sha256(),
    }


def _node_drain(context: Mapping[str, Any]) -> None:
    _node_arm(context)
    # The permanent API+worker drop-ins were installed and daemon-reloaded by
    # the one-time HA bootstrap.  One exact, transaction-bound marker therefore
    # makes every reboot fail closed atomically; this command never writes a
    # partial pair of live systemd drop-ins.
    _arm_runtime_guard(context)
    _arm_marker(PERSISTENT_MAINTENANCE)
    _arm_marker(VOLATILE_MAINTENANCE)
    if _direct_ready_status() != 503:
        raise RuntimeError("drained node did not return direct readiness 503 before process mutation")
    _run(["/usr/bin/systemctl", "disable", *ALL_UNITS])
    for unit in ALL_UNITS:
        if _run(["/usr/bin/systemctl", "is-enabled", unit], check=False).returncode == 0:
            raise RuntimeError("canonical unit remained enabled before failover drain")
    for unit in WORKER_UNITS:
        _run(["/usr/bin/systemctl", "stop", unit])
    # Recovery after a reboot intentionally starts only the marker-aware API
    # while disabled, then reinstalls the sentinel guard. Workers never run on
    # a drained node.
    if _run(["/usr/bin/systemctl", "is-active", API_UNIT], check=False).returncode:
        _unlink_runtime_guard(context)
        _run(["/usr/bin/systemctl", "start", API_UNIT])
    _arm_runtime_guard(context)
    if _direct_ready_status() != 503:
        raise RuntimeError("drained node did not return direct readiness 503")
    for unit in WORKER_UNITS:
        if _run(["/usr/bin/systemctl", "is-active", unit], check=False).returncode == 0:
            raise RuntimeError("queue worker remained active on the drained failover node")


def _node_admit(context: Mapping[str, Any]) -> None:
    _node_arm(context)
    if not (PERSISTENT_MAINTENANCE.exists() or PERSISTENT_MAINTENANCE.is_symlink()):
        # Already admitted is an idempotent recovery state.
        try:
            ready = _direct_ready_status() == 200
        except RuntimeError:
            ready = False
        if ready:
            _assert_processes_ready()
            _unlink_runtime_guard(context)
            _run(["/usr/bin/systemctl", "enable", *ALL_UNITS])
            for unit in ALL_UNITS:
                if _run(["/usr/bin/systemctl", "is-enabled", unit], check=False).returncode:
                    raise RuntimeError("recovered admitted canonical unit was not enabled")
            _write_admission_state(context, "enabled")
            return
        if _read_admission_state(context) not in {"processes-proved", "enabled"} and not (
            RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink()
        ):
            raise RuntimeError("admitted node has neither maintenance, readiness, nor durable recovery authority")
        if RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink():
            _read_runtime_guard(context)
        # A reboot after marker clear but before enable leaves all units safely
        # disabled.  A reboot immediately after publishing drain intent is also
        # authorized by that exact marker. Re-arm maintenance and replay the
        # monotonic admission.
        _arm_marker(PERSISTENT_MAINTENANCE)
        _arm_marker(VOLATILE_MAINTENANCE)
    _run(["/usr/bin/systemctl", "disable", "--now", *ALL_UNITS])
    _unlink_runtime_guard(context)
    _run(["/usr/bin/systemctl", "start", API_UNIT])
    for _ in range(60):
        try:
            if _direct_ready_status() == 503:
                break
        except RuntimeError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("admitting API did not become healthy behind maintenance")
    for unit in WORKER_UNITS:
        _run(["/usr/bin/systemctl", "start", unit])
    _assert_processes_ready()
    _write_admission_state(context, "processes-proved")
    _unlink_durable(VOLATILE_MAINTENANCE)
    _unlink_durable(PERSISTENT_MAINTENANCE)
    if _direct_ready_status() != 200:
        raise RuntimeError("admitted node did not return direct readiness 200")
    _run(["/usr/bin/systemctl", "enable", *ALL_UNITS])
    for unit in ALL_UNITS:
        if _run(["/usr/bin/systemctl", "is-enabled", unit], check=False).returncode:
            raise RuntimeError("admitted canonical unit was not enabled last")
    _assert_processes_ready()
    _write_admission_state(context, "enabled")


def _node_observe(context: Mapping[str, Any], phase: str) -> dict[str, Any]:
    _node_arm(context)
    if phase not in {"initial", "replay", "closeout"}:
        raise ValueError("controlled failover node proof phase is invalid")
    node = _node_id()
    maintenance = PERSISTENT_MAINTENANCE.exists() or PERSISTENT_MAINTENANCE.is_symlink()
    if maintenance:
        _secure_file(PERSISTENT_MAINTENANCE)
        if not (RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink()):
            # Crash after starting the disabled marker-aware API but before
            # re-arming its reboot marker is safe yet not proof-worthy. Replay
            # drain so the signed topology is durable across reboot.
            _node_drain(context)
        _read_runtime_guard(context)
    elif RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink():
        raise RuntimeError("ready controlled failover node still has a runtime guard")
    try:
        status = _direct_ready_status()
    except RuntimeError:
        if not maintenance:
            raise
        # A reboot intentionally keeps the drained API stopped. Replaying the
        # exact drain restores only that marker-aware API while all queue
        # workers remain disabled and stopped.
        _node_drain(context)
        status = _direct_ready_status()
    if maintenance != (status == 503):
        raise RuntimeError("maintenance and direct readiness disagree")
    expected_ready = (
        phase == "closeout"
        or (phase == "initial" and node == context["initial_node"])
        or (phase == "replay" and node == context["replay_node"])
    )
    if status != (200 if expected_ready else 503) or maintenance == expected_ready:
        raise RuntimeError("node does not match the requested controlled failover topology")
    if expected_ready:
        _assert_processes_ready()
        for unit in ALL_UNITS:
            if _run(["/usr/bin/systemctl", "is-enabled", unit], check=False).returncode:
                raise RuntimeError("ready failover node has a reboot-disabled canonical unit")
    else:
        for unit in WORKER_UNITS:
            if _run(["/usr/bin/systemctl", "is-active", unit], check=False).returncode == 0:
                raise RuntimeError("drained controlled failover node still has an active worker")
    body = {
        "node_id": node,
        "phase": phase,
        "transaction_id": context["transaction_id"],
        "release_sha": context["release_sha"],
        "direct_ready_status": status,
        "maintenance": maintenance,
        "observed_at": _now(),
        "machine_id_sha256": _machine_id_sha256(),
    }
    private, _ = _require_matching_key(node)
    return {**body, "node_signature": _b64encode(private.sign(_canonical(body)))}


def _node_release(context: Mapping[str, Any], closeout_sha256: str) -> None:
    _node_arm(context)
    if DIGEST_RE.fullmatch(closeout_sha256) is None:
        raise RuntimeError("closeout release authority digest is invalid")
    if PERSISTENT_MAINTENANCE.exists() or VOLATILE_MAINTENANCE.exists():
        raise RuntimeError("cannot release failover sentinel while node is drained")
    if _direct_ready_status() != 200:
        raise RuntimeError("cannot release failover sentinel before direct readiness")
    if RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink():
        raise RuntimeError("cannot release failover sentinel with a runtime guard armed")
    _assert_static_guard_contract()
    _unlink_durable(NODE_SENTINEL)


def _node_abort_release(context: Mapping[str, Any], abort_authority_b64: str) -> None:
    raw = _b64decode(abort_authority_b64)
    _verify_abort_authority(raw, context)
    _node_admit(context)
    if PERSISTENT_MAINTENANCE.exists() or VOLATILE_MAINTENANCE.exists():
        raise RuntimeError("cannot abort-release a controlled failover node while it is drained")
    if _direct_ready_status() != 200:
        raise RuntimeError("cannot abort-release a controlled failover node before direct readiness")
    _assert_processes_ready()
    for unit in ALL_UNITS:
        if _run(["/usr/bin/systemctl", "is-enabled", unit], check=False).returncode:
            raise RuntimeError("cannot abort-release a reboot-disabled canonical unit")
    if RUNTIME_GUARD.exists() or RUNTIME_GUARD.is_symlink():
        raise RuntimeError("cannot abort-release a controlled failover runtime guard")
    _assert_static_guard_contract()
    _unlink_durable(NODE_SENTINEL)


def _remote(
    context: Mapping[str, Any],
    action: str,
    *,
    phase: str = "",
    closeout_sha256: str = "",
    abort_authority_b64: str = "",
) -> Any:
    args = [
        "/usr/bin/ssh",
        *SSH_OPTIONS,
        f"root@{PEER_HOST}",
        str(REPO_DIR / "venv/bin/python"),
        str(HELPER_PATH),
        "node-phase",
        action,
        "--context-b64",
        _context_b64(context),
    ]
    if phase:
        args.extend(["--phase", phase])
    if closeout_sha256:
        args.extend(["--closeout-sha256", closeout_sha256])
    if abort_authority_b64:
        args.extend(["--abort-authority-b64", abort_authority_b64])
    result = _run(args, timeout=180)
    output = result.stdout.strip()
    return json.loads(output) if output.startswith("{") else output


def _on_node(
    context: Mapping[str, Any],
    node: str,
    action: str,
    *,
    phase: str = "",
    closeout: str = "",
    abort_authority: str = "",
) -> Any:
    if node == "node01":
        functions = {
            "preflight": lambda: _node_preflight(context),
            "arm": lambda: _node_arm(context),
            "drain": lambda: _node_drain(context),
            "admit": lambda: _node_admit(context),
            "observe": lambda: _node_observe(context, phase),
            "release": lambda: _node_release(context, closeout),
            "abort-release": lambda: _node_abort_release(context, abort_authority),
        }
        return functions[action]()
    return _remote(
        context,
        action,
        phase=phase,
        closeout_sha256=closeout,
        abort_authority_b64=abort_authority,
    )


def _verify_node_proof(proof: Mapping[str, Any], context: Mapping[str, Any], phase: str) -> None:
    body_keys = {
        "node_id",
        "phase",
        "transaction_id",
        "release_sha",
        "direct_ready_status",
        "maintenance",
        "observed_at",
        "machine_id_sha256",
    }
    if set(proof) != body_keys | {"node_signature"}:
        raise RuntimeError("controlled failover node proof fields are invalid")
    node = str(proof["node_id"])
    if node not in REQUIRED_NODES or proof["phase"] != phase:
        raise RuntimeError("controlled failover node proof identity is invalid")
    if proof["transaction_id"] != context["transaction_id"] or proof["release_sha"] != context["release_sha"]:
        raise RuntimeError("controlled failover node proof binding is invalid")
    expected_ready = (
        phase == "closeout"
        or (phase == "initial" and node == context["initial_node"])
        or (phase == "replay" and node == context["replay_node"])
    )
    if proof["direct_ready_status"] != (200 if expected_ready else 503) or proof["maintenance"] is not (
        not expected_ready
    ):
        raise RuntimeError("controlled failover node proof topology is invalid")
    if DIGEST_RE.fullmatch(str(proof["machine_id_sha256"])) is None:
        raise RuntimeError("controlled failover machine identity digest is invalid")
    _parse_time(str(proof["observed_at"]))
    keys = _load_verification_keys()
    body = {key: proof[key] for key in body_keys}
    try:
        keys[node].verify(_b64decode(str(proof["node_signature"])), _canonical(body))
    except (InvalidSignature, ValueError) as exc:
        raise PermissionError("controlled failover node signature is invalid") from exc


def _signed_phase_attestation(
    context: Mapping[str, Any],
    phase: str,
    *,
    phase_started_at: str,
    lb_pre_attestation_sha256: str,
    lb_post_attestation_sha256: str,
    lb_post_observed_at: str,
) -> dict[str, Any]:
    if phase not in {"initial", "replay"}:
        raise ValueError("signed failover phase is invalid")
    if (
        DIGEST_RE.fullmatch(lb_pre_attestation_sha256) is None
        or DIGEST_RE.fullmatch(lb_post_attestation_sha256) is None
        or hmac.compare_digest(lb_pre_attestation_sha256, lb_post_attestation_sha256)
    ):
        raise RuntimeError("controlled failover pre/post LB attestation binding is invalid")
    post_observed = _parse_time(lb_post_observed_at)
    proofs = {node: _on_node(context, node, "observe", phase=phase) for node in REQUIRED_NODES}
    for node, proof in proofs.items():
        if not isinstance(proof, dict) or proof.get("node_id") != node:
            raise RuntimeError("controlled failover returned the wrong node proof")
        _verify_node_proof(proof, context, phase)
    if proofs["node01"]["machine_id_sha256"] == proofs["node02"]["machine_id_sha256"]:
        raise RuntimeError("fixed failover nodes reported the same machine identity")
    phase_proved_at = _now()
    elapsed = (_parse_time(phase_proved_at) - _parse_time(phase_started_at)).total_seconds()
    if elapsed < int(context["minimum_drain_seconds"]):
        raise RuntimeError("controlled failover phase proof did not satisfy the LB drain interval")
    if not _parse_time(phase_started_at) < post_observed <= _parse_time(phase_proved_at):
        raise RuntimeError("post-transition LB observation is outside the signed phase")
    body = {
        "schema": SCHEMA,
        "phase": phase,
        "transaction_id": context["transaction_id"],
        "test_run_id": context["test_run_id"],
        "manifest_sha256": context["manifest_sha256"],
        "release_sha": context["release_sha"],
        "initial_node": context["initial_node"],
        "replay_node": context["replay_node"],
        "lb_ready_projection_sha256": context["lb_ready_projection_sha256"],
        "lb_pre_attestation_sha256": lb_pre_attestation_sha256,
        "lb_post_attestation_sha256": lb_post_attestation_sha256,
        "lb_post_observed_at": lb_post_observed_at,
        "phase_started_at": phase_started_at,
        "phase_proved_at": phase_proved_at,
        "minimum_drain_seconds": context["minimum_drain_seconds"],
        "public_ready_status": _public_ready_status(),
        "node_proofs": proofs,
    }
    private, _ = _require_matching_key("node01")
    return {**body, "coordinator_signature": _b64encode(private.sign(_canonical(body)))}


def _verify_phase_attestation(raw: bytes, context: Mapping[str, Any], phase: str) -> dict[str, Any]:
    document = json.loads(raw)
    expected_keys = {
        "schema",
        "phase",
        "transaction_id",
        "test_run_id",
        "manifest_sha256",
        "release_sha",
        "initial_node",
        "replay_node",
        "lb_ready_projection_sha256",
        "lb_pre_attestation_sha256",
        "lb_post_attestation_sha256",
        "lb_post_observed_at",
        "phase_started_at",
        "phase_proved_at",
        "minimum_drain_seconds",
        "public_ready_status",
        "node_proofs",
        "coordinator_signature",
    }
    if not isinstance(document, dict) or set(document) != expected_keys or document.get("schema") != SCHEMA:
        raise RuntimeError("controlled failover attestation schema is invalid")
    for key in (
        "transaction_id",
        "test_run_id",
        "manifest_sha256",
        "release_sha",
        "initial_node",
        "replay_node",
        "lb_ready_projection_sha256",
        "minimum_drain_seconds",
    ):
        if document.get(key) != context.get(key):
            raise RuntimeError("controlled failover attestation binding changed")
    if document.get("phase") != phase or document.get("public_ready_status") != 200:
        raise RuntimeError("controlled failover attestation phase/readiness is invalid")
    pre_lb = str(document["lb_pre_attestation_sha256"])
    post_lb = str(document["lb_post_attestation_sha256"])
    if (
        DIGEST_RE.fullmatch(pre_lb) is None
        or DIGEST_RE.fullmatch(post_lb) is None
        or hmac.compare_digest(pre_lb, post_lb)
    ):
        raise RuntimeError("controlled failover pre/post LB attestation digests are invalid")
    started = _parse_time(str(document["phase_started_at"]))
    proved = _parse_time(str(document["phase_proved_at"]))
    if proved < started or (proved - started).total_seconds() < int(context["minimum_drain_seconds"]):
        raise RuntimeError("controlled failover attestation drain timestamps are invalid")
    post_observed = _parse_time(str(document["lb_post_observed_at"]))
    if not started < post_observed <= proved:
        raise RuntimeError("controlled failover post LB observation is outside its signed phase")
    if phase == "initial":
        manifest_start = _parse_time(str(context["manifest_start"]))
        if proved > manifest_start or (manifest_start - proved).total_seconds() > 600:
            raise RuntimeError("controlled failover initial proof is outside the manifest window")
    else:
        if started < _parse_time(str(context["manifest_initial_cutoff"])) or proved >= _parse_time(
            str(context["manifest_final_cutoff"])
        ):
            raise RuntimeError("controlled failover replay proof is outside the manifest window")
    proofs = document.get("node_proofs")
    if not isinstance(proofs, dict) or set(proofs) != set(REQUIRED_NODES):
        raise RuntimeError("controlled failover attestation node membership is invalid")
    for proof in proofs.values():
        _verify_node_proof(proof, context, phase)
        observed = _parse_time(str(proof["observed_at"]))
        if observed < started or observed > proved:
            raise RuntimeError("controlled failover node observation is outside its signed phase")
    body = {key: value for key, value in document.items() if key != "coordinator_signature"}
    try:
        _load_verification_keys()["node01"].verify(_b64decode(str(document["coordinator_signature"])), _canonical(body))
    except (InvalidSignature, ValueError) as exc:
        raise PermissionError("controlled failover coordinator signature is invalid") from exc
    return document


def _write_once_or_verify(path: Path, payload: Mapping[str, Any], context: Mapping[str, Any], phase: str) -> str:
    encoded = _canonical(payload) + b"\n"
    # Never publish an immutable proof that the evidence evaluator will reject
    # because the manifest window expired during the bounded drain/observation.
    _verify_phase_attestation(encoded, context, phase)
    if path.exists() or path.is_symlink():
        existing = _read_secure(path)
        if existing != encoded:
            raise RuntimeError("immutable controlled failover attestation changed")
    else:
        _atomic_write(path, encoded, no_replace=True)
    _verify_phase_attestation(_read_secure(path), context, phase)
    return _digest(_read_secure(path))


def _read_journal(transaction_id: str, expected_sha256: str = "") -> tuple[dict[str, Any], str]:
    raw = _read_secure(_journal_path(transaction_id))
    digest = _digest(raw)
    if expected_sha256 and not hmac.compare_digest(digest, expected_sha256):
        raise RuntimeError("controlled failover journal digest changed")
    journal = json.loads(raw)
    if (
        not isinstance(journal, dict)
        or set(journal)
        != {
            "schema",
            "context",
            "status",
            "phase_started_at",
            "topology_transition_at",
        }
        or journal.get("schema") != STATE_SCHEMA
    ):
        raise RuntimeError("controlled failover journal schema is invalid")
    journal["context"] = _validate_context(journal.get("context") or {})
    if journal.get("status") not in {
        "preparing-initial",
        "initial-drained",
        "initial-proved",
        "switching-replay",
        "replay-drained",
        "replay-transitioned",
        "replay-proved",
        "restoring",
        "closeout-transitioned",
        "closed",
        "aborting",
        "aborted",
    }:
        raise RuntimeError("controlled failover journal status is invalid")
    _parse_time(str(journal.get("phase_started_at") or ""))
    transition = str(journal.get("topology_transition_at") or "")
    if transition:
        _parse_time(transition)
    return journal, digest


def _write_journal(
    context: Mapping[str, Any],
    status: str,
    phase_started_at: str,
    topology_transition_at: str = "",
) -> None:
    allowed = {
        "preparing-initial",
        "initial-drained",
        "initial-proved",
        "switching-replay",
        "replay-drained",
        "replay-transitioned",
        "replay-proved",
        "restoring",
        "closeout-transitioned",
        "closed",
        "aborting",
        "aborted",
    }
    if status not in allowed:
        raise ValueError("controlled failover journal status is invalid")
    _parse_time(phase_started_at)
    if topology_transition_at:
        _parse_time(topology_transition_at)
    payload = {
        "schema": STATE_SCHEMA,
        "context": dict(context),
        "status": status,
        "phase_started_at": phase_started_at,
        "topology_transition_at": topology_transition_at,
    }
    _atomic_write(_journal_path(str(context["transaction_id"])), _canonical(payload) + b"\n")


def _wait_minimum(started_at: str, seconds: int) -> None:
    remaining = seconds - (datetime.now(UTC) - _parse_time(started_at)).total_seconds()
    if remaining > 0:
        time.sleep(remaining)


def _assert_initial_window(context: Mapping[str, Any]) -> None:
    now = datetime.now(UTC)
    manifest_start = _parse_time(str(context["manifest_start"]))
    remaining = (manifest_start - now).total_seconds()
    if remaining > 600:
        raise RuntimeError("controlled failover initial proof window has not opened")
    if remaining <= int(context["minimum_drain_seconds"]) + 10:
        raise RuntimeError("insufficient manifest window remains for the initial LB drain proof")


def _assert_replay_window(context: Mapping[str, Any]) -> None:
    now = datetime.now(UTC)
    if now < _parse_time(str(context["manifest_initial_cutoff"])):
        raise RuntimeError("replay failover cannot begin before the manifest initial cutoff")
    remaining = (_parse_time(str(context["manifest_final_cutoff"])) - now).total_seconds()
    if remaining <= int(context["minimum_drain_seconds"]) + 10:
        raise RuntimeError("insufficient manifest window remains for the replay LB drain proof")


def _assert_current_phase_topology(context: Mapping[str, Any], phase: str) -> None:
    for node in REQUIRED_NODES:
        proof = _on_node(context, node, "observe", phase=phase)
        if not isinstance(proof, dict) or proof.get("node_id") != node:
            raise RuntimeError("controlled failover current topology returned the wrong node proof")
        _verify_node_proof(proof, context, phase)
    if _public_ready_status() != 200:
        raise RuntimeError("controlled failover public readiness is not healthy")


def _complete_initial(
    context: Mapping[str, Any],
    started_at: str,
    *,
    drain_proved: bool = False,
    topology_transition_at: str = "",
) -> str:
    path = _proof_path(str(context["transaction_id"]), "initial")
    if path.exists() or path.is_symlink():
        raw = _read_secure(path)
        _verify_phase_attestation(raw, context, "initial")
        _assert_current_phase_topology(context, "initial")
        digest = _digest(raw)
        document = json.loads(raw)
        _write_journal(
            context,
            "initial-proved",
            str(document["phase_started_at"]),
            str(document["lb_post_observed_at"]),
        )
        return digest
    _assert_initial_window(context)
    pre_sha256, pre_observed_at = _assert_context_lb_attestation(
        context, "initial", "pre", require_fresh=not drain_proved
    )
    if not drain_proved:
        for node in REQUIRED_NODES:
            _on_node(context, node, "arm")
        _on_node(context, str(context["replay_node"]), "drain")
        started_at = _now()
        topology_transition_at = started_at
        _write_journal(context, "initial-drained", started_at, topology_transition_at)
    if not topology_transition_at:
        topology_transition_at = started_at
    if _parse_time(pre_observed_at) > _parse_time(topology_transition_at):
        raise RuntimeError("initial pre-transition LB observation occurred after the topology transition")
    _wait_minimum(started_at, int(context["minimum_drain_seconds"]))
    post_sha256, post_observed_at = _post_transition_lb_binding(context, "initial", topology_transition_at)
    attestation = _signed_phase_attestation(
        context,
        "initial",
        phase_started_at=started_at,
        lb_pre_attestation_sha256=pre_sha256,
        lb_post_attestation_sha256=post_sha256,
        lb_post_observed_at=post_observed_at,
    )
    digest = _write_once_or_verify(path, attestation, context, "initial")
    _write_journal(context, "initial-proved", started_at, topology_transition_at)
    return digest


def _complete_replay(
    context: Mapping[str, Any],
    started_at: str,
    *,
    drain_proved: bool = False,
    topology_proved: bool = False,
    topology_transition_at: str = "",
) -> str:
    initial_raw = _read_secure(_proof_path(str(context["transaction_id"]), "initial"))
    _verify_phase_attestation(initial_raw, context, "initial")
    path = _proof_path(str(context["transaction_id"]), "replay")
    if path.exists() or path.is_symlink():
        raw = _read_secure(path)
        _verify_phase_attestation(raw, context, "replay")
        _assert_current_phase_topology(context, "replay")
        digest = _digest(raw)
        document = json.loads(raw)
        _write_journal(
            context,
            "replay-proved",
            str(document["phase_started_at"]),
            str(document["lb_post_observed_at"]),
        )
        return digest
    _assert_replay_window(context)
    pre_sha256, pre_observed_at = _assert_context_lb_attestation(
        context, "replay", "pre", require_fresh=not drain_proved
    )
    if not drain_proved:
        _on_node(context, str(context["initial_node"]), "drain")
        started_at = _now()
        _write_journal(context, "replay-drained", started_at)
    if not topology_proved:
        _wait_minimum(started_at, int(context["minimum_drain_seconds"]))
        _on_node(context, str(context["replay_node"]), "admit")
        topology_transition_at = _now()
        _write_journal(context, "replay-transitioned", started_at, topology_transition_at)
    if not topology_transition_at:
        raise RuntimeError("replay durable topology transition timestamp is missing")
    if _parse_time(pre_observed_at) > _parse_time(topology_transition_at):
        raise RuntimeError("replay pre-transition LB observation occurred after the topology transition")
    post_sha256, post_observed_at = _post_transition_lb_binding(context, "replay", topology_transition_at)
    attestation = _signed_phase_attestation(
        context,
        "replay",
        phase_started_at=started_at,
        lb_pre_attestation_sha256=pre_sha256,
        lb_post_attestation_sha256=post_sha256,
        lb_post_observed_at=post_observed_at,
    )
    digest = _write_once_or_verify(path, attestation, context, "replay")
    _write_journal(context, "replay-proved", started_at, topology_transition_at)
    return digest


def _signed_closeout(
    context: Mapping[str, Any],
    initial_digest: str,
    replay_digest: str,
    *,
    lb_pre_attestation_sha256: str,
    lb_post_attestation_sha256: str,
    lb_post_observed_at: str,
) -> dict[str, Any]:
    if (
        DIGEST_RE.fullmatch(lb_pre_attestation_sha256) is None
        or DIGEST_RE.fullmatch(lb_post_attestation_sha256) is None
        or hmac.compare_digest(lb_pre_attestation_sha256, lb_post_attestation_sha256)
    ):
        raise RuntimeError("controlled failover closeout LB attestation binding is invalid")
    _parse_time(lb_post_observed_at)
    proofs = {node: _on_node(context, node, "observe", phase="closeout") for node in REQUIRED_NODES}
    for proof in proofs.values():
        _verify_node_proof(proof, context, "closeout")
    body = {
        "schema": SCHEMA,
        "phase": "closeout",
        "transaction_id": context["transaction_id"],
        "test_run_id": context["test_run_id"],
        "manifest_sha256": context["manifest_sha256"],
        "release_sha": context["release_sha"],
        "initial_node": context["initial_node"],
        "replay_node": context["replay_node"],
        "lb_ready_projection_sha256": context["lb_ready_projection_sha256"],
        "lb_pre_attestation_sha256": lb_pre_attestation_sha256,
        "lb_post_attestation_sha256": lb_post_attestation_sha256,
        "lb_post_observed_at": lb_post_observed_at,
        "public_ready_status": _public_ready_status(),
        "node_proofs": proofs,
        "initial_attestation_sha256": initial_digest,
        "replay_attestation_sha256": replay_digest,
        "closeout_proved_at": _now(),
    }
    private, _ = _require_matching_key("node01")
    return {**body, "coordinator_signature": _b64encode(private.sign(_canonical(body)))}


def _verify_closeout(
    raw: bytes,
    context: Mapping[str, Any],
    initial_digest: str,
    replay_digest: str,
) -> dict[str, Any]:
    document = json.loads(raw)
    expected_keys = {
        "schema",
        "phase",
        "transaction_id",
        "test_run_id",
        "manifest_sha256",
        "release_sha",
        "initial_node",
        "replay_node",
        "lb_ready_projection_sha256",
        "lb_pre_attestation_sha256",
        "lb_post_attestation_sha256",
        "lb_post_observed_at",
        "public_ready_status",
        "node_proofs",
        "initial_attestation_sha256",
        "replay_attestation_sha256",
        "closeout_proved_at",
        "coordinator_signature",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise RuntimeError("controlled failover closeout fields are invalid")
    if document.get("schema") != SCHEMA or document.get("phase") != "closeout":
        raise RuntimeError("controlled failover closeout schema/phase is invalid")
    for key in (
        "transaction_id",
        "test_run_id",
        "manifest_sha256",
        "release_sha",
        "initial_node",
        "replay_node",
        "lb_ready_projection_sha256",
    ):
        if document.get(key) != context.get(key):
            raise RuntimeError("controlled failover closeout binding changed")
    if (
        document.get("public_ready_status") != 200
        or document.get("initial_attestation_sha256") != initial_digest
        or document.get("replay_attestation_sha256") != replay_digest
    ):
        raise RuntimeError("controlled failover closeout readiness/digest binding is invalid")
    closeout_proved = _parse_time(str(document["closeout_proved_at"]))
    post_observed = _parse_time(str(document["lb_post_observed_at"]))
    pre_lb = str(document["lb_pre_attestation_sha256"])
    post_lb = str(document["lb_post_attestation_sha256"])
    if (
        DIGEST_RE.fullmatch(pre_lb) is None
        or DIGEST_RE.fullmatch(post_lb) is None
        or hmac.compare_digest(pre_lb, post_lb)
        or post_observed > closeout_proved
    ):
        raise RuntimeError("controlled failover closeout LB proof is invalid")
    proofs = document.get("node_proofs")
    if not isinstance(proofs, dict) or set(proofs) != set(REQUIRED_NODES):
        raise RuntimeError("controlled failover closeout node membership is invalid")
    for proof in proofs.values():
        _verify_node_proof(proof, context, "closeout")
    body = {key: value for key, value in document.items() if key != "coordinator_signature"}
    try:
        _load_verification_keys()["node01"].verify(_b64decode(str(document["coordinator_signature"])), _canonical(body))
    except (InvalidSignature, ValueError) as exc:
        raise PermissionError("controlled failover closeout coordinator signature is invalid") from exc
    return document


def _signed_abort_authority(context: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "schema": ABORT_SCHEMA,
        "transaction_id": context["transaction_id"],
        "context_sha256": _digest(context),
        "abort_decided_at": _now(),
    }
    private, _ = _require_matching_key("node01")
    return {**body, "coordinator_signature": _b64encode(private.sign(_canonical(body)))}


def _verify_abort_authority(raw: bytes, context: Mapping[str, Any]) -> dict[str, Any]:
    document = json.loads(raw)
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "transaction_id",
        "context_sha256",
        "abort_decided_at",
        "coordinator_signature",
    }:
        raise RuntimeError("controlled failover abort authority fields are invalid")
    if (
        document.get("schema") != ABORT_SCHEMA
        or document.get("transaction_id") != context["transaction_id"]
        or document.get("context_sha256") != _digest(context)
    ):
        raise RuntimeError("controlled failover abort authority binding is invalid")
    _parse_time(str(document["abort_decided_at"]))
    body = {key: value for key, value in document.items() if key != "coordinator_signature"}
    try:
        _load_verification_keys()["node01"].verify(_b64decode(str(document["coordinator_signature"])), _canonical(body))
    except (InvalidSignature, ValueError) as exc:
        raise PermissionError("controlled failover abort authority signature is invalid") from exc
    return document


def _abort_authority(context: Mapping[str, Any]) -> tuple[bytes, str]:
    path = _abort_path(str(context["transaction_id"]))
    if path.exists() or path.is_symlink():
        raw = _read_secure(path)
        _verify_abort_authority(raw, context)
    else:
        payload = _signed_abort_authority(context)
        raw = _canonical(payload) + b"\n"
        _verify_abort_authority(raw, context)
        _atomic_write(path, raw, no_replace=True)
        raw = _read_secure(path)
        _verify_abort_authority(raw, context)
    return raw, _digest(raw)


def _complete_abort(context: Mapping[str, Any], started_at: str) -> str:
    raw, digest = _abort_authority(context)
    authority = _b64encode(raw)
    # Both releases are already exact and equal. Restore both nodes while each
    # remains transaction-bound, prove the all-ready topology, then release the
    # per-node sentinels using the signed, immutable abort authority.
    for node in (str(context["replay_node"]), str(context["initial_node"])):
        _on_node(context, node, "admit")
    _assert_current_phase_topology(context, "closeout")
    for node in ("node02", "node01"):
        _on_node(context, node, "abort-release", abort_authority=authority)
    _write_journal(context, "aborted", started_at)
    return digest


def _publish_abort_and_restore(context: Mapping[str, Any], cause: BaseException) -> NoReturn:
    decided_at = _now()
    _write_journal(context, "aborting", decided_at)
    try:
        _complete_abort(context, decided_at)
    except BaseException as abort_exc:
        raise RuntimeError(
            "controlled failover abort/recovery is uncertain; keep both nodes under the durable transaction"
        ) from abort_exc
    raise RuntimeError("controlled failover phase failed and both nodes were safely restored") from cause


def _complete_closeout(
    context: Mapping[str, Any],
    started_at: str,
    *,
    topology_proved: bool = False,
    topology_transition_at: str = "",
) -> str:
    if datetime.now(UTC) < _parse_time(str(context["manifest_final_cutoff"])):
        raise RuntimeError("closeout cannot restore the initial node before the manifest final cutoff")
    initial_raw = _read_secure(_proof_path(str(context["transaction_id"]), "initial"))
    replay_raw = _read_secure(_proof_path(str(context["transaction_id"]), "replay"))
    _verify_phase_attestation(initial_raw, context, "initial")
    _verify_phase_attestation(replay_raw, context, "replay")
    initial_digest, replay_digest = _digest(initial_raw), _digest(replay_raw)
    path = _proof_path(str(context["transaction_id"]), "closeout")
    if path.exists() or path.is_symlink():
        closeout_raw = _read_secure(path)
        _verify_closeout(closeout_raw, context, initial_digest, replay_digest)
    else:
        pre_sha256, pre_observed_at = _assert_context_lb_attestation(
            context, "closeout", "pre", require_fresh=not topology_proved
        )
        if not topology_proved:
            _on_node(context, str(context["initial_node"]), "admit")
            topology_transition_at = _now()
            _write_journal(context, "closeout-transitioned", started_at, topology_transition_at)
        if not topology_transition_at:
            raise RuntimeError("closeout durable topology transition timestamp is missing")
        if _parse_time(pre_observed_at) > _parse_time(topology_transition_at):
            raise RuntimeError("closeout pre-transition LB observation occurred after the topology transition")
        post_sha256, post_observed_at = _post_transition_lb_binding(context, "closeout", topology_transition_at)
        closeout = _signed_closeout(
            context,
            initial_digest,
            replay_digest,
            lb_pre_attestation_sha256=pre_sha256,
            lb_post_attestation_sha256=post_sha256,
            lb_post_observed_at=post_observed_at,
        )
        encoded = _canonical(closeout) + b"\n"
        _atomic_write(path, encoded, no_replace=True)
        closeout_raw = _read_secure(path)
        _verify_closeout(closeout_raw, context, initial_digest, replay_digest)
    closeout_digest = _digest(closeout_raw)
    if not topology_transition_at:
        topology_transition_at = str(json.loads(closeout_raw)["lb_post_observed_at"])
    # The signed closeout is durable authority before either per-node sentinel
    # is released.  A lost ACK is idempotently replayed by confirmed recovery.
    for node in ("node02", "node01"):
        _on_node(context, node, "release", closeout=closeout_digest)
    _write_journal(context, "closed", started_at, topology_transition_at)
    return closeout_digest


def _plan(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    if args.initial_node not in REQUIRED_NODES:
        raise ValueError("initial node must be node01 or node02")
    manifest = _read_manifest(
        args.manifest,
        args.manifest_sha256,
        transaction_id=args.transaction_id,
        initial_node=args.initial_node,
    )
    lb_digest, minimum_drain, _, _ = _read_lb_attestation(
        args.lb_ready_attestation,
        transaction_id=args.transaction_id,
        manifest_sha256=args.manifest_sha256,
        phase="initial",
        observation="pre",
        manifest_start=manifest["start"],
        manifest_initial_cutoff=manifest["initial_cutoff"],
        manifest_final_cutoff=manifest["final_cutoff"],
        require_fresh=True,
    )
    helper_sha = _helper_sha256()
    context = _validate_context(
        {
            "transaction_id": args.transaction_id,
            "test_run_id": manifest["test_run_id"],
            "manifest_sha256": args.manifest_sha256,
            "release_sha": manifest["release_sha"],
            "initial_node": args.initial_node,
            "replay_node": manifest["replay_node"],
            "lb_ready_projection_sha256": lb_digest,
            "minimum_drain_seconds": minimum_drain,
            "manifest_start": manifest["start"],
            "manifest_initial_cutoff": manifest["initial_cutoff"],
            "manifest_final_cutoff": manifest["final_cutoff"],
            "helper_sha256": helper_sha,
        }
    )
    _assert_initial_window(context)
    local = _node_preflight(context)
    if local["node_id"] != "node01":
        raise RuntimeError("controlled failover coordinator must be fixed node01")
    peer = _remote(context, "preflight")
    if (
        local["release_sha"] != context["release_sha"]
        or not isinstance(peer, dict)
        or peer.get("node_id") != "node02"
        or peer.get("release_sha") != context["release_sha"]
        or peer.get("helper_sha256") != helper_sha
        or peer.get("machine_id_sha256") == local.get("machine_id_sha256")
    ):
        raise RuntimeError("controlled failover plan release proof failed")
    plan = {"context": context, "node01": local, "node02": peer}
    return plan, context


def _prepare_initial(args: argparse.Namespace) -> None:
    plan, context = _plan(args)
    plan_sha = _digest(plan)
    expected = f"PREPARE_META_FAILOVER_{plan_sha[:16].upper()}"
    if args.expected_plan_sha256 != plan_sha or args.confirm != expected:
        raise PermissionError("exact controlled failover initial plan confirmation is missing")
    tx_dir = _transaction_dir(args.transaction_id)
    if tx_dir.exists() or tx_dir.is_symlink():
        raise RuntimeError("controlled failover transaction already exists; use status/recover")
    _secure_directory(EVIDENCE_ROOT, create=True)
    tx_dir.mkdir(mode=0o700)
    _secure_directory(tx_dir)
    started = _now()
    _write_journal(context, "preparing-initial", started)
    try:
        digest = _complete_initial(context, started)
    except AwaitingPostLBAttestation as exc:
        print("status=initial-drained-awaiting-post-lb-attestation")
        print(f"next={exc}")
        return
    except BaseException as exc:
        if _proof_path(args.transaction_id, "initial").exists():
            raise
        _publish_abort_and_restore(context, exc)
    print(f"initial_attestation={_proof_path(args.transaction_id, 'initial')}")
    print(f"initial_attestation_sha256={digest}")


def _status(transaction_id: str) -> None:
    journal, digest = _read_journal(transaction_id)
    context = journal["context"]
    status = journal["status"]
    print(f"journal_sha256={digest}")
    print(f"status={status}")
    if status == "initial-proved":
        initial_digest = _digest(_read_secure(_proof_path(transaction_id, "initial")))
        print(f"switch_confirmation=SWITCH_META_FAILOVER_{initial_digest[:16].upper()}")
    elif status == "replay-proved":
        initial_digest = _digest(_read_secure(_proof_path(transaction_id, "initial")))
        replay_digest = _digest(_read_secure(_proof_path(transaction_id, "replay")))
        print(f"restore_confirmation=RESTORE_META_FAILOVER_{initial_digest[:8].upper()}_{replay_digest[:8].upper()}")
    elif status not in {"closed", "aborted"}:
        print(f"recover_confirmation=RECOVER_META_FAILOVER_{digest[:16].upper()}_{str(status).upper()}")
    print(f"initial_node={context['initial_node']}")
    print(f"replay_node={context['replay_node']}")


def _switch(args: argparse.Namespace) -> None:
    journal, digest = _read_journal(args.transaction_id, args.expected_journal_sha256)
    if journal["status"] != "initial-proved":
        raise RuntimeError("controlled failover is not ready for the replay switch")
    initial_digest = _digest(_read_secure(_proof_path(args.transaction_id, "initial")))
    if args.confirm != f"SWITCH_META_FAILOVER_{initial_digest[:16].upper()}":
        raise PermissionError("exact controlled failover replay confirmation is missing")
    context = journal["context"]
    _assert_supplied_phase_lb_attestation(context, args.lb_ready_attestation, "replay", "pre")
    _assert_replay_window(context)
    started = _now()
    _write_journal(context, "switching-replay", started)
    try:
        replay_digest = _complete_replay(context, started)
    except AwaitingPostLBAttestation as exc:
        print("status=replay-transitioned-awaiting-post-lb-attestation")
        print(f"next={exc}")
        return
    except BaseException as exc:
        if _proof_path(args.transaction_id, "replay").exists():
            raise
        _publish_abort_and_restore(context, exc)
    print(f"replay_attestation={_proof_path(args.transaction_id, 'replay')}")
    print(f"replay_attestation_sha256={replay_digest}")
    print(f"previous_journal_sha256={digest}")


def _restore(args: argparse.Namespace) -> None:
    journal, _ = _read_journal(args.transaction_id, args.expected_journal_sha256)
    if journal["status"] != "replay-proved":
        raise RuntimeError("controlled failover is not ready for closeout")
    initial_digest = _digest(_read_secure(_proof_path(args.transaction_id, "initial")))
    replay_digest = _digest(_read_secure(_proof_path(args.transaction_id, "replay")))
    expected = f"RESTORE_META_FAILOVER_{initial_digest[:8].upper()}_{replay_digest[:8].upper()}"
    if args.confirm != expected:
        raise PermissionError("exact controlled failover restore confirmation is missing")
    context = journal["context"]
    _assert_supplied_phase_lb_attestation(context, args.lb_ready_attestation, "closeout", "pre")
    started = _now()
    _write_journal(context, "restoring", started)
    try:
        closeout_digest = _complete_closeout(context, started)
    except AwaitingPostLBAttestation as exc:
        print("status=closeout-transitioned-awaiting-post-lb-attestation")
        print(f"next={exc}")
        return
    print(f"closeout_attestation={_proof_path(args.transaction_id, 'closeout')}")
    print(f"closeout_attestation_sha256={closeout_digest}")


def _recover(args: argparse.Namespace) -> None:
    journal, digest = _read_journal(args.transaction_id, args.expected_journal_sha256)
    status = str(journal["status"])
    expected = f"RECOVER_META_FAILOVER_{digest[:16].upper()}_{status.upper()}"
    if args.confirm != expected:
        raise PermissionError("exact controlled failover recovery confirmation is missing")
    context = journal["context"]
    started = str(journal["phase_started_at"])
    transition = str(journal.get("topology_transition_at") or "")
    if status in {"preparing-initial", "initial-drained"}:
        if not _proof_path(args.transaction_id, "initial").exists() and args.lb_ready_attestation is not None:
            observation = "pre" if status == "preparing-initial" else "post"
            _assert_supplied_phase_lb_attestation(context, args.lb_ready_attestation, "initial", observation)
        try:
            _complete_initial(
                context,
                started,
                drain_proved=status == "initial-drained",
                topology_transition_at=transition,
            )
        except AwaitingPostLBAttestation:
            return
        except BaseException as exc:
            if _proof_path(args.transaction_id, "initial").exists():
                raise
            _publish_abort_and_restore(context, exc)
    elif status in {"switching-replay", "replay-drained", "replay-transitioned"}:
        if not _proof_path(args.transaction_id, "replay").exists() and args.lb_ready_attestation is not None:
            observation = "post" if status == "replay-transitioned" else "pre"
            _assert_supplied_phase_lb_attestation(context, args.lb_ready_attestation, "replay", observation)
        try:
            _complete_replay(
                context,
                started,
                drain_proved=status in {"replay-drained", "replay-transitioned"},
                topology_proved=status == "replay-transitioned",
                topology_transition_at=transition,
            )
        except AwaitingPostLBAttestation:
            return
        except BaseException as exc:
            if _proof_path(args.transaction_id, "replay").exists():
                raise
            _publish_abort_and_restore(context, exc)
    elif status in {"restoring", "closeout-transitioned"}:
        if not _proof_path(args.transaction_id, "closeout").exists() and args.lb_ready_attestation is not None:
            observation = "post" if status == "closeout-transitioned" else "pre"
            _assert_supplied_phase_lb_attestation(context, args.lb_ready_attestation, "closeout", observation)
        try:
            _complete_closeout(
                context,
                started,
                topology_proved=status == "closeout-transitioned",
                topology_transition_at=transition,
            )
        except AwaitingPostLBAttestation:
            return
    elif status == "aborting":
        _complete_abort(context, started)
    else:
        raise RuntimeError("controlled failover state has no interrupted mutation to recover")


def _node_phase(args: argparse.Namespace) -> None:
    context = _context_from_b64(args.context_b64)
    _require_root()
    with _lock():
        if args.action == "arm":
            _node_arm(context)
        elif args.action == "drain":
            _node_drain(context)
        elif args.action == "admit":
            _node_admit(context)
        elif args.action == "observe":
            print(json.dumps(_node_observe(context, args.phase), sort_keys=True, separators=(",", ":")))
            return
        elif args.action == "release":
            _node_release(context, args.closeout_sha256)
        elif args.action == "abort-release":
            _node_abort_release(context, args.abort_authority_b64)
        else:  # pragma: no cover - argparse closes the set.
            raise ValueError("unknown controlled failover node action")
    print("ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    generate_key = sub.add_parser("generate-node-key")
    generate_key.add_argument("--node-id", choices=REQUIRED_NODES, required=True)
    generate_key.add_argument("--confirm", required=True)
    plan_keys = sub.add_parser("plan-verification-keys")
    plan_keys.add_argument("--node01-public", required=True)
    plan_keys.add_argument("--node02-public", required=True)
    install_keys = sub.add_parser("install-verification-keys")
    install_keys.add_argument("--node01-public", required=True)
    install_keys.add_argument("--node02-public", required=True)
    install_keys.add_argument("--confirm", required=True)
    install_lb = sub.add_parser("install-lb-attestation")
    install_lb.add_argument("--expected-ready-sha256", required=True)
    install_lb.add_argument("--expected-attestation-sha256", required=True)
    install_lb.add_argument("--transaction-id", required=True)
    install_lb.add_argument("--manifest-sha256", required=True)
    install_lb.add_argument("--phase", choices=LB_ATTESTATION_PHASES, required=True)
    install_lb.add_argument("--observation", choices=LB_ATTESTATION_OBSERVATIONS, required=True)
    install_lb.add_argument("--manifest-start", required=True)
    install_lb.add_argument("--manifest-initial-cutoff", required=True)
    install_lb.add_argument("--manifest-final-cutoff", required=True)
    install_lb.add_argument("--confirm", required=True)

    def initial_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--manifest-sha256", required=True)
        command.add_argument("--transaction-id", required=True)
        command.add_argument("--initial-node", choices=REQUIRED_NODES, required=True)
        command.add_argument("--lb-ready-attestation", type=Path, required=True)

    plan = sub.add_parser("plan-initial")
    initial_arguments(plan)
    prepare = sub.add_parser("prepare-initial")
    initial_arguments(prepare)
    prepare.add_argument("--expected-plan-sha256", required=True)
    prepare.add_argument("--confirm", required=True)
    status = sub.add_parser("status")
    status.add_argument("--transaction-id", required=True)
    switch = sub.add_parser("switch-to-replay")
    switch.add_argument("--transaction-id", required=True)
    switch.add_argument("--expected-journal-sha256", required=True)
    switch.add_argument("--lb-ready-attestation", type=Path, required=True)
    switch.add_argument("--confirm", required=True)
    restore = sub.add_parser("restore-closeout")
    restore.add_argument("--transaction-id", required=True)
    restore.add_argument("--expected-journal-sha256", required=True)
    restore.add_argument("--lb-ready-attestation", type=Path, required=True)
    restore.add_argument("--confirm", required=True)
    recover = sub.add_parser("recover")
    recover.add_argument("--transaction-id", required=True)
    recover.add_argument("--expected-journal-sha256", required=True)
    recover.add_argument("--lb-ready-attestation", type=Path)
    recover.add_argument("--confirm", required=True)
    node = sub.add_parser("node-phase")
    node.add_argument("action", choices=("preflight", "arm", "drain", "admit", "observe", "release", "abort-release"))
    node.add_argument("--context-b64", required=True)
    node.add_argument("--phase", choices=("initial", "replay", "closeout"), default="closeout")
    node.add_argument("--closeout-sha256", default="")
    node.add_argument("--abort-authority-b64", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _require_root()
    with _lock():
        if args.command == "generate-node-key":
            _generate_node_key(args.node_id, args.confirm)
        elif args.command == "plan-verification-keys":
            digest, confirmation = _verification_key_install_plan(args.node01_public, args.node02_public)
            print(f"verification_set_sha256={digest}")
            print(f"confirmation={confirmation}")
        elif args.command == "install-verification-keys":
            _install_verification_keys(args.node01_public, args.node02_public, args.confirm)
        elif args.command == "install-lb-attestation":
            _install_lb_attestation(
                args.expected_ready_sha256,
                args.expected_attestation_sha256,
                args.transaction_id,
                args.manifest_sha256,
                args.phase,
                args.observation,
                args.manifest_start,
                args.manifest_initial_cutoff,
                args.manifest_final_cutoff,
                args.confirm,
            )
        elif args.command == "plan-initial":
            plan, _ = _plan(args)
            digest = _digest(plan)
            print(f"plan_sha256={digest}")
            print(f"confirmation=PREPARE_META_FAILOVER_{digest[:16].upper()}")
        elif args.command == "prepare-initial":
            _prepare_initial(args)
        elif args.command == "status":
            _status(args.transaction_id)
        elif args.command == "switch-to-replay":
            _switch(args)
        elif args.command == "restore-closeout":
            _restore(args)
        elif args.command == "recover":
            _recover(args)
        elif args.command == "node-phase":
            # The remote node invocation needs its own lock; avoid nested flock
            # only because main already owns this process's lock.
            if args.action == "preflight":
                print(
                    json.dumps(
                        _node_preflight(_context_from_b64(args.context_b64)),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            elif args.action == "arm":
                _node_arm(_context_from_b64(args.context_b64))
            elif args.action == "drain":
                _node_drain(_context_from_b64(args.context_b64))
            elif args.action == "admit":
                _node_admit(_context_from_b64(args.context_b64))
            elif args.action == "observe":
                print(
                    json.dumps(
                        _node_observe(_context_from_b64(args.context_b64), args.phase),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            elif args.action == "release":
                _node_release(_context_from_b64(args.context_b64), args.closeout_sha256)
            else:
                _node_abort_release(_context_from_b64(args.context_b64), args.abort_authority_b64)
        else:  # pragma: no cover
            raise AssertionError("unreachable controlled failover command")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
