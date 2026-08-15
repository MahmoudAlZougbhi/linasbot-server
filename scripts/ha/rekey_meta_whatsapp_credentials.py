#!/usr/bin/env python3
"""Offline, transactional rotation of the shared Meta/WhatsApp master key.

``META_CREDENTIAL_ENCRYPTION_KEY`` protects both ``meta_binding_credentials``
and ``whatsapp_credentials``.  This command therefore refuses product-local
rotation.  It inventories, decrypts, re-seals, CAS-updates, and verifies every
credential in one PostgreSQL transaction while both HA nodes are proven offline.

All mutating commands are dry-run unless ``--apply`` and a digest-specific
confirmation token are supplied.  Output is deliberately limited to counts,
digests, booleans, and fixed node labels; secrets, plaintext, ciphertext, AAD,
tenant IDs, connection IDs, and credential IDs are never printed.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import socket
import stat
import subprocess  # nosec B404 - fixed argv only; no shell or operator-controlled executable.
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import select, text, update
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.models.meta_registry import MetaAssetBindingRow, MetaBindingCredentialRow  # noqa: E402
from db.models.whatsapp_cloud import WhatsAppConnection, WhatsAppCredential  # noqa: E402
from services.meta_app_registry_common import MetaCredentialCipher, MetaCredentialError  # noqa: E402

FORMAT = "linas-meta-whatsapp-credential-preimage-v1"
FORMAT_AAD = b"linas-meta-whatsapp-credential-preimage-v1\x00all-credentials"
PROOF_FORMAT = "linas-meta-whatsapp-offline-proof-v1"
ENV_PROOF_FORMAT = "linas-meta-whatsapp-env-proof-v1"
DATABASE_CERTIFICATE_FORMAT = "linas-meta-whatsapp-database-transition-certificate-v1"
GUARD_FORMAT = "linas-meta-whatsapp-runtime-guard-v1"
RELEASE_RECEIPT_FORMAT = "linas-meta-whatsapp-runtime-guard-release-v1"
REQUIRED_NODES = ("node01", "node02")
TX_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
APPLICATION_LOCK = Path("/run/lock/linasbot-meta-live.lock")
PERSISTENT_MAINTENANCE = Path("/var/lib/linasbot/meta-ha/maintenance")
CANONICAL_ENV_PATH = Path("/opt/linasbot/.env")
MACHINE_ID_PATH = Path("/etc/machine-id")
API_UNIT = "linasbot.service"
LEGACY_API_UNIT = "linas_ai_bot.service"
WORKER_UNITS = tuple(
    f"linasbot-worker@{queue}.service" for queue in ("high_priority", "interactive", "background", "expensive")
)
ALL_RUNTIME_UNITS = (API_UNIT, LEGACY_API_UNIT, *WORKER_UNITS)
GUARDED_SYSTEMD_UNITS = (API_UNIT, LEGACY_API_UNIT, "linasbot-worker@.service")
SYSTEMD_UNIT_ROOT = Path("/etc/systemd/system")
GUARD_DROPIN_NAME = "95-linasbot-credential-rekey-guard.conf"
REKEY_GUARD_MARKER = Path("/var/lib/linasbot/meta-ha/rekey/runtime.guard")
REKEY_COLLISION_PATHS = (
    Path("/var/lib/linasbot/meta-ha/bootstrap.active"),
    Path("/var/lib/linasbot/meta-ha/bootstrap.coordinator.json"),
    Path("/var/lib/linasbot/meta-ha/deploy.active"),
    Path("/var/lib/linasbot/meta-ha/deploy-node.active"),
    Path("/var/lib/linasbot/meta-ha/transaction.json"),
    Path("/var/lib/linasbot/meta-ha/env.before"),
    Path("/var/lib/linasbot/meta-ha/controlled-failover.active"),
    Path("/var/lib/linasbot/meta-ha/registry-nfs-retire.active"),
    Path("/var/lib/linasbot/meta-ha/python-runtime-provision.active"),
    Path("/var/lib/linasbot/meta-ha/python-runtime-provision.coordinator.json"),
)
FIXED_NODE_IDENTITIES: dict[str, dict[str, str]] = {
    "node01": {
        "hostname": "ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01",
        "public_ip": "139.59.167.62",
        "private_ip": "10.106.0.3",
    },
    "node02": {
        "hostname": "linas-app-lon1-02",
        "public_ip": "167.99.89.243",
        "private_ip": "10.106.0.4",
    },
}
PROOF_MAX_AGE_SECONDS = 300
REKEY_ADVISORY_LOCK_KEY = 0x4C494E4153524B31  # LINASRK1, signed int64-safe.


@dataclass(frozen=True)
class Inventory:
    meta_bindings: tuple[MetaAssetBindingRow, ...]
    meta_credentials: tuple[MetaBindingCredentialRow, ...]
    whatsapp_connections: tuple[WhatsAppConnection, ...]
    whatsapp_credentials: tuple[WhatsAppCredential, ...]


@dataclass(frozen=True)
class PreparedRekey:
    meta_updates: tuple[tuple[str, str, str, str, str], ...]
    whatsapp_updates: tuple[tuple[str, str, str, str, str, int, Any, str], ...]
    semantic_digest: str


def _require_root() -> None:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise PermissionError("credential rekey operations require root")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _normalized(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"bytes_b64": base64.urlsafe_b64encode(value).decode("ascii")}
    if isinstance(value, Mapping):
        return {str(key): _normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("credential inventory contains an unsupported value")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(_normalized(value))).hexdigest()


def _key_fingerprint(secret: str) -> str:
    return hashlib.sha256(b"linas-key-fingerprint-v1\x00" + secret.encode("utf-8")).hexdigest()


def _require_fresh_rollback_proof_key(proof_secret: str, original_proof_secret: str) -> None:
    if hmac.compare_digest(proof_secret, original_proof_secret):
        raise ValueError("rollback proof key must be freshly generated for this transaction")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if _b64encode(decoded) != raw:
        raise ValueError("non-canonical base64")
    return decoded


def _row_dict(row: Any) -> dict[str, Any]:
    mapper = sqlalchemy_inspect(type(row))
    return {attribute.key: _normalized(getattr(row, attribute.key)) for attribute in mapper.column_attrs}


def _snapshot(inventory: Inventory) -> dict[str, Any]:
    return {
        "format_version": 1,
        "meta_bindings": [_row_dict(row) for row in inventory.meta_bindings],
        "meta_credentials": [_row_dict(row) for row in inventory.meta_credentials],
        "whatsapp_connections": [_row_dict(row) for row in inventory.whatsapp_connections],
        "whatsapp_credentials": [_row_dict(row) for row in inventory.whatsapp_credentials],
    }


def _structural_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    structural = cast(dict[str, Any], json.loads(json.dumps(snapshot)))
    for row in structural.get("meta_credentials", []):
        if isinstance(row, dict):
            row.pop("sealed", None)
    for row in structural.get("whatsapp_credentials", []):
        if isinstance(row, dict):
            row.pop("ciphertext", None)
            row.pop("encryption_key_version", None)
    return structural


def _fingerprint_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "meta_binding_count": len(snapshot.get("meta_bindings", [])),
        "meta_credential_count": len(snapshot.get("meta_credentials", [])),
        "whatsapp_connection_count": len(snapshot.get("whatsapp_connections", [])),
        "whatsapp_credential_count": len(snapshot.get("whatsapp_credentials", [])),
        "structural_sha256": _digest(_structural_snapshot(snapshot)),
        "full_sha256": _digest(snapshot),
    }


def _print_fingerprint(prefix: str, fingerprint: Mapping[str, Any]) -> None:
    print(
        f"{prefix} meta_credentials={fingerprint['meta_credential_count']} "
        f"whatsapp_credentials={fingerprint['whatsapp_credential_count']} "
        f"sha256={fingerprint['full_sha256']}"
    )


def _secure_regular_file(path: Path, *, label: str) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PermissionError(f"{label} must be a regular non-symlink file")
    if info.st_uid != os.geteuid() or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError(f"{label} must be owned by root with mode 0600")
    return info


def _secure_private_parent(path: Path) -> None:
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PermissionError("output parent must be a real directory")
    if info.st_uid != os.geteuid() or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError("output parent must be root-owned and private")


def _read_exact(path: Path, *, label: str) -> bytes:
    path = Path(os.path.abspath(os.fspath(path)))
    before = _secure_regular_file(path, label=label)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise RuntimeError(f"{label} changed while it was opened")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_no_clobber(path: Path, payload: bytes) -> None:
    path = Path(os.path.abspath(os.fspath(path)))
    _secure_private_parent(path)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
        _secure_regular_file(path, label="created protected file")
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _require_output_available(path: Path) -> None:
    path = Path(os.path.abspath(os.fspath(path)))
    _secure_private_parent(path)
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise FileExistsError("protected output path already exists")


def _require_output_available_or_secure_existing(path: Path, *, label: str) -> bool:
    """Preflight a resumable artifact; return True only when it already exists."""

    path = Path(os.path.abspath(os.fspath(path)))
    _secure_private_parent(path)
    try:
        _secure_regular_file(path, label=label)
    except FileNotFoundError:
        return False
    return True


def _copy_no_clobber(source: Path, target: Path) -> str:
    """Create an immutable exact copy, or authenticate an identical prior copy."""

    payload = _read_exact(source, label="canonical environment")
    try:
        existing = _read_exact(target, label="environment backup")
    except FileNotFoundError:
        _write_no_clobber(target, payload)
        existing = _read_exact(target, label="environment backup")
    if not hmac.compare_digest(payload, existing):
        raise RuntimeError("environment backup verification failed")
    return hashlib.sha256(payload).hexdigest()


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _secure_owned_regular_file(path: Path, *, mode: int, label: str) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PermissionError(f"{label} must be a regular non-symlink file")
    if info.st_uid != os.geteuid() or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != mode:
        raise PermissionError(f"{label} has an unsafe owner or mode")
    return info


def _secure_owned_directory(path: Path, *, label: str) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PermissionError(f"{label} must be a real directory")
    if info.st_uid != os.geteuid() or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise PermissionError(f"{label} has an unsafe owner or mode")


def _atomic_replace_private_file(path: Path, payload: bytes) -> None:
    """Atomically create/replace a root-private operational state file."""

    path = Path(os.path.abspath(os.fspath(path)))
    _secure_private_parent(path)
    try:
        _secure_owned_regular_file(path, mode=0o600, label="existing runtime guard")
    except FileNotFoundError:
        pass
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _secure_owned_regular_file(path, mode=0o600, label="runtime guard")
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _guard_dropin_payload(marker_path: Path = REKEY_GUARD_MARKER) -> bytes:
    return (
        f"[Unit]\n# Managed only by rekey_meta_whatsapp_credentials.py.\nConditionPathExists=!{marker_path}\n"
    ).encode()


def _guard_dropin_paths(systemd_root: Path = SYSTEMD_UNIT_ROOT) -> dict[str, Path]:
    return {unit: systemd_root / f"{unit}.d" / GUARD_DROPIN_NAME for unit in GUARDED_SYSTEMD_UNITS}


def _install_guard_dropin(path: Path, payload: bytes) -> None:
    parent = path.parent
    try:
        parent.mkdir(mode=0o755)
    except FileExistsError:
        pass
    _secure_owned_directory(parent, label="systemd guard drop-in directory")
    try:
        existing = path.read_bytes()
    except FileNotFoundError:
        existing = None
    else:
        _secure_owned_regular_file(path, mode=0o644, label="systemd runtime guard")
    if existing is not None:
        if not hmac.compare_digest(existing, payload):
            raise RuntimeError("systemd runtime guard content conflicts with the reviewed contract")
        return

    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
        _secure_owned_regular_file(path, mode=0o644, label="systemd runtime guard")
        _fsync_directory(parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _systemd_daemon_reload() -> None:
    result = subprocess.run(  # nosec B603 - fixed absolute executable and argv.
        ["/usr/bin/systemctl", "daemon-reload"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError("systemd did not accept the credential rekey runtime guard")


def _systemd_guard_loaded(unit: str, dropin_path: Path) -> bool:
    load_state = subprocess.run(  # nosec B603 - unit is from fixed GUARDED_SYSTEMD_UNITS.
        ["/usr/bin/systemctl", "show", "--property=LoadState", "--value", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if load_state.returncode != 0:
        return False
    if load_state.stdout.strip() == "not-found":
        return unit == LEGACY_API_UNIT
    dropins = subprocess.run(  # nosec B603 - unit is from fixed GUARDED_SYSTEMD_UNITS.
        ["/usr/bin/systemctl", "show", "--property=DropInPaths", "--value", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return dropins.returncode == 0 and str(dropin_path) in dropins.stdout.split()


def _canonical_env_identity(env_path: Path) -> None:
    absolute = Path(os.path.abspath(os.fspath(env_path)))
    if absolute != CANONICAL_ENV_PATH or absolute.resolve(strict=True) != CANONICAL_ENV_PATH:
        raise PermissionError("offline attestations require the exact canonical runtime environment path")


def _machine_id_sha256(path: Path = MACHINE_ID_PATH) -> str:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise PermissionError("machine identity file is unsafe")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        value = os.read(fd, 4096).strip()
        if os.read(fd, 1) or len(value) < 16:
            raise RuntimeError("machine identity is invalid")
    finally:
        os.close(fd)
    return hashlib.sha256(b"linas-node-machine-id-v1\x00" + value).hexdigest()


def _interface_addresses() -> set[str]:
    result = subprocess.run(  # nosec B603 - fixed absolute executable and argv.
        ["/usr/sbin/ip", "-o", "-4", "addr", "show", "scope", "global"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("node interface identity cannot be verified")
    addresses: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if "inet" in fields:
            addresses.add(fields[fields.index("inet") + 1].split("/", 1)[0])
    return addresses


def _attest_host_identity(node_id: str) -> dict[str, str]:
    expected = FIXED_NODE_IDENTITIES.get(node_id)
    if expected is None:
        raise ValueError("fixed HA node identity is invalid")
    hostname = socket.gethostname().split(".", 1)[0]
    if hostname != expected["hostname"]:
        raise PermissionError("host does not match the fixed HA node identity")
    addresses = _interface_addresses()
    if expected["public_ip"] not in addresses or expected["private_ip"] not in addresses:
        raise PermissionError("host addresses do not match the fixed HA node identity")
    return {**expected, "machine_id_sha256": _machine_id_sha256()}


def _validate_attested_identity(identity: Any, *, node_id: str) -> dict[str, str]:
    expected = FIXED_NODE_IDENTITIES.get(node_id)
    if not isinstance(identity, dict) or expected is None:
        raise PermissionError("signed HA host identity is invalid")
    normalized = {str(key): str(value) for key, value in identity.items()}
    if set(normalized) != {"hostname", "public_ip", "private_ip", "machine_id_sha256"}:
        raise PermissionError("signed HA host identity is incomplete")
    if any(normalized.get(key) != value for key, value in expected.items()):
        raise PermissionError("signed HA host identity does not match the fixed node")
    if not SHA256_RE.fullmatch(normalized["machine_id_sha256"]):
        raise PermissionError("signed HA machine identity is invalid")
    return normalized


def _guard_body(
    *,
    node_id: str,
    transaction_id: str,
    proof_secret: str,
    host_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if node_id not in REQUIRED_NODES or not TX_RE.fullmatch(transaction_id):
        raise ValueError("runtime guard identity is invalid")
    identity = _validate_attested_identity(
        dict(host_identity) if host_identity is not None else _attest_host_identity(node_id),
        node_id=node_id,
    )
    return {
        "format": GUARD_FORMAT,
        "transaction_id": transaction_id,
        "node_id": node_id,
        "proof_key_fingerprint": _key_fingerprint(proof_secret),
        "host_identity": identity,
    }


def _guard_payload(
    *,
    node_id: str,
    transaction_id: str,
    proof_secret: str,
    host_identity: Mapping[str, str] | None = None,
) -> bytes:
    return (
        _canonical(
            _guard_body(
                node_id=node_id,
                transaction_id=transaction_id,
                proof_secret=proof_secret,
                host_identity=host_identity,
            )
        )
        + b"\n"
    )


def _validate_transaction_guard(
    *,
    node_id: str,
    transaction_id: str,
    proof_secret: str,
    marker_path: Path = REKEY_GUARD_MARKER,
    systemd_root: Path = SYSTEMD_UNIT_ROOT,
    loaded_checker: Any = _systemd_guard_loaded,
    identity_checker: Any = _attest_host_identity,
) -> str:
    identity = identity_checker(node_id)
    expected_marker = _guard_payload(
        node_id=node_id,
        transaction_id=transaction_id,
        proof_secret=proof_secret,
        host_identity=identity,
    )
    actual_marker = _read_exact(marker_path, label="transaction-owned runtime guard")
    if not hmac.compare_digest(actual_marker, expected_marker):
        raise PermissionError("transaction-owned runtime guard does not match this operation")
    _validate_static_guard_contract(
        marker_path=marker_path,
        systemd_root=systemd_root,
        loaded_checker=loaded_checker,
    )
    return hashlib.sha256(expected_marker).hexdigest()


def _validate_static_guard_contract(
    *,
    marker_path: Path = REKEY_GUARD_MARKER,
    systemd_root: Path = SYSTEMD_UNIT_ROOT,
    loaded_checker: Any = _systemd_guard_loaded,
) -> str:
    """Require all pre-provisioned drop-ins before a transaction can arm."""

    dropin_payload = _guard_dropin_payload(marker_path)
    for unit, dropin_path in _guard_dropin_paths(systemd_root).items():
        _secure_owned_regular_file(dropin_path, mode=0o644, label="systemd runtime guard")
        if not hmac.compare_digest(dropin_path.read_bytes(), dropin_payload):
            raise PermissionError("systemd runtime guard was changed")
        if not loaded_checker(unit, dropin_path):
            raise PermissionError("systemd has not loaded every runtime guard")
    return hashlib.sha256(dropin_payload).hexdigest()


def _arm_transaction_guard(
    *,
    node_id: str,
    transaction_id: str,
    proof_secret: str,
    marker_path: Path = REKEY_GUARD_MARKER,
    systemd_root: Path = SYSTEMD_UNIT_ROOT,
    reload_systemd: Any = _systemd_daemon_reload,
    loaded_checker: Any = _systemd_guard_loaded,
    identity_checker: Any = _attest_host_identity,
) -> str:
    # Drop-ins are provisioned and loaded before the maintenance window.  Arm is
    # therefore one atomic marker publication; no reboot can observe a partial
    # per-unit guard installation.
    del reload_systemd  # retained as an injectable compatibility argument.
    identity = identity_checker(node_id)
    _validate_static_guard_contract(
        marker_path=marker_path,
        systemd_root=systemd_root,
        loaded_checker=loaded_checker,
    )
    expected_marker = _guard_payload(
        node_id=node_id,
        transaction_id=transaction_id,
        proof_secret=proof_secret,
        host_identity=identity,
    )
    try:
        existing_marker = _read_exact(marker_path, label="transaction-owned runtime guard")
    except FileNotFoundError:
        _atomic_replace_private_file(marker_path, expected_marker)
    else:
        if not hmac.compare_digest(existing_marker, expected_marker):
            raise PermissionError("another transaction already owns the runtime guard")
    return _validate_transaction_guard(
        node_id=node_id,
        transaction_id=transaction_id,
        proof_secret=proof_secret,
        marker_path=marker_path,
        systemd_root=systemd_root,
        loaded_checker=loaded_checker,
        identity_checker=lambda _node_id: identity,
    )


def _remove_transaction_guard(
    *,
    node_id: str,
    transaction_id: str,
    proof_secret: str,
    marker_path: Path = REKEY_GUARD_MARKER,
    systemd_root: Path = SYSTEMD_UNIT_ROOT,
    reload_systemd: Any = _systemd_daemon_reload,
    loaded_checker: Any = _systemd_guard_loaded,
    identity_checker: Any = _attest_host_identity,
) -> None:
    del reload_systemd  # static drop-ins are deliberately retained across transactions.
    _validate_transaction_guard(
        node_id=node_id,
        transaction_id=transaction_id,
        proof_secret=proof_secret,
        marker_path=marker_path,
        systemd_root=systemd_root,
        loaded_checker=loaded_checker,
        identity_checker=identity_checker,
    )
    marker_path.unlink()
    _fsync_directory(marker_path.parent)
    _validate_static_guard_contract(
        marker_path=marker_path,
        systemd_root=systemd_root,
        loaded_checker=loaded_checker,
    )


def _finalize_transaction_guard_release(
    *,
    node_id: str,
    transaction_id: str,
    proof_secret: str,
    marker_path: Path = REKEY_GUARD_MARKER,
    systemd_root: Path = SYSTEMD_UNIT_ROOT,
    loaded_checker: Any = _systemd_guard_loaded,
    identity_checker: Any = _attest_host_identity,
) -> bool:
    """Idempotently remove only the marker after its receipt is durable.

    The caller must authenticate the transaction-specific release receipt before
    entering this helper.  Returning ``False`` means an earlier invocation
    already removed the marker; the retained static contract is revalidated.
    """

    try:
        marker_path.lstat()
    except FileNotFoundError:
        _validate_static_guard_contract(
            marker_path=marker_path,
            systemd_root=systemd_root,
            loaded_checker=loaded_checker,
        )
        return False
    _remove_transaction_guard(
        node_id=node_id,
        transaction_id=transaction_id,
        proof_secret=proof_secret,
        marker_path=marker_path,
        systemd_root=systemd_root,
        loaded_checker=loaded_checker,
        identity_checker=identity_checker,
    )
    return True


def _parse_env(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    from scripts.ha.meta_env_file import require_secure_env_file

    require_secure_env_file(path)
    raw = dotenv_values(path, interpolate=False)
    return {str(key): str(value) for key, value in raw.items() if value is not None}


def _load_runtime_env(path: Path) -> tuple[dict[str, str], str]:
    values = _parse_env(path)
    if str(values.get("META_REGISTRY_BACKEND") or "").strip().lower() != "postgres":
        raise RuntimeError("file, dual, or implicit Meta registry authority is prohibited")
    primary_dsn = str(values.get("LINAS_WHATSAPP_DATABASE_URL") or "").strip()
    fallback_dsn = str(values.get("DATABASE_URL") or "").strip()
    if primary_dsn and fallback_dsn and primary_dsn != fallback_dsn:
        raise RuntimeError("canonical environment contains conflicting PostgreSQL DSNs")
    effective_dsn = primary_dsn or fallback_dsn
    if not effective_dsn.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise RuntimeError("canonical environment has no explicit PostgreSQL DSN")
    secret = str(values.get("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("canonical environment has no valid credential encryption key")
    allowed = {
        "META_REGISTRY_BACKEND",
        "META_CREDENTIAL_ENCRYPTION_KEY",
        "LINAS_WHATSAPP_DATABASE_URL",
        "DATABASE_URL",
        "LINAS_WHATSAPP_REQUIRE_SSL",
        "LINAS_WHATSAPP_DB_SSLMODE",
        "LINAS_WHATSAPP_DB_POOL_SIZE",
        "LINAS_WHATSAPP_DB_MAX_OVERFLOW",
        "LINAS_WHATSAPP_ALLOW_SQLITE",
    }
    for key in allowed:
        os.environ.pop(key, None)
    for key in allowed:
        if key in values:
            os.environ[key] = values[key]
    return values, secret


def _effective_database_dsn(values: Mapping[str, str]) -> str:
    return str(values.get("LINAS_WHATSAPP_DATABASE_URL") or values.get("DATABASE_URL") or "").strip()


def _load_key(path: Path) -> str:
    secret = str(_parse_env(path).get("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("key file has no valid credential encryption key")
    return secret


def _load_new_runtime_key(path: Path) -> str:
    values = _parse_env(path)
    if set(values) != {"META_CREDENTIAL_ENCRYPTION_KEY"}:
        raise RuntimeError("new runtime key file must contain only the credential encryption key")
    secret = str(values["META_CREDENTIAL_ENCRYPTION_KEY"]).strip()
    if len(secret) < 32:
        raise RuntimeError("new runtime key file has no valid credential encryption key")
    return secret


def _load_recovery_key(path: Path) -> str:
    values = _parse_env(path)
    if set(values) != {"CREDENTIAL_REKEY_RECOVERY_KEY"}:
        raise RuntimeError("recovery key file must contain only the independent recovery key")
    secret = str(values["CREDENTIAL_REKEY_RECOVERY_KEY"]).strip()
    if len(secret) < 32:
        raise RuntimeError("recovery key file has no valid independent recovery key")
    return secret


def _load_proof_key(path: Path) -> str:
    values = _parse_env(path)
    if set(values) != {"CREDENTIAL_REKEY_PROOF_KEY"}:
        raise RuntimeError("proof key file must contain only the independent transaction proof key")
    secret = str(values["CREDENTIAL_REKEY_PROOF_KEY"]).strip()
    if len(secret) < 32:
        raise RuntimeError("proof key file has no valid independent transaction proof key")
    return secret


def _load_node_signing_key(path: Path) -> Ed25519PrivateKey:
    values = _parse_env(path)
    if set(values) != {"CREDENTIAL_REKEY_NODE_SIGNING_KEY"}:
        raise RuntimeError("node signing key file must contain only its Ed25519 private key")
    try:
        raw = _b64decode(str(values["CREDENTIAL_REKEY_NODE_SIGNING_KEY"]))
        if len(raw) != 32:
            raise ValueError("invalid key length")
        return Ed25519PrivateKey.from_private_bytes(raw)
    except Exception as exc:  # noqa: BLE001 - normalize without key-bearing detail.
        raise RuntimeError("node signing key file is invalid") from exc


def _load_node_verification_keys(path: Path) -> dict[str, Ed25519PublicKey]:
    names = {node: f"CREDENTIAL_REKEY_{node.upper()}_VERIFY_KEY" for node in REQUIRED_NODES}
    values = _parse_env(path)
    if set(values) != set(names.values()):
        raise RuntimeError("verification key file must contain exactly both fixed node public keys")
    keys: dict[str, Ed25519PublicKey] = {}
    raw_keys: list[bytes] = []
    try:
        for node, name in names.items():
            raw = _b64decode(str(values[name]))
            if len(raw) != 32:
                raise ValueError("invalid key length")
            raw_keys.append(raw)
            keys[node] = Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:  # noqa: BLE001 - normalize without key-bearing detail.
        raise RuntimeError("fixed node verification key file is invalid") from exc
    if hmac.compare_digest(raw_keys[0], raw_keys[1]):
        raise RuntimeError("fixed HA nodes must have independent signing keys")
    return keys


def _public_key_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _verification_key_fingerprint(key: Ed25519PublicKey) -> str:
    return hashlib.sha256(b"linas-node-verification-key-v1\x00" + _public_key_bytes(key)).hexdigest()


def _verification_set_fingerprint(keys: Mapping[str, Ed25519PublicKey]) -> str:
    return _digest({node: _verification_key_fingerprint(keys[node]) for node in REQUIRED_NODES})


@contextmanager
def _application_lock(path: Path = APPLICATION_LOCK) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        current = os.fstat(fd)
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_uid != os.geteuid()
            or stat.S_IMODE(current.st_mode) != 0o600
        ):
            raise PermissionError("application lock security contract is invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Meta HA operation holds the application lock") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _acquire_database_locks(session: Session, *, apply: bool) -> None:
    bind = session.get_bind()
    dialect = "" if bind is None else bind.dialect.name
    if apply and dialect != "postgresql":
        raise RuntimeError("credential rekey writes require PostgreSQL")
    if dialect != "postgresql":
        return
    acquired = bool(
        session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": REKEY_ADVISORY_LOCK_KEY},
        )
    )
    if not acquired:
        raise RuntimeError("another cross-product credential operation is active")
    from services.meta_app_registry_pg_store import acquire_registry_advisory_lock

    acquire_registry_advisory_lock(session)
    table_lock_mode = "ACCESS EXCLUSIVE" if apply else "SHARE"
    session.execute(
        text(
            "LOCK TABLE meta_asset_bindings, meta_binding_credentials, "
            f"whatsapp_connections, whatsapp_credentials IN {table_lock_mode} MODE NOWAIT"
        )
    )


def load_inventory(session: Session) -> Inventory:
    return Inventory(
        meta_bindings=tuple(
            session.scalars(select(MetaAssetBindingRow).order_by(MetaAssetBindingRow.binding_id)).all()
        ),
        meta_credentials=tuple(
            session.scalars(select(MetaBindingCredentialRow).order_by(MetaBindingCredentialRow.credential_id)).all()
        ),
        whatsapp_connections=tuple(session.scalars(select(WhatsAppConnection).order_by(WhatsAppConnection.id)).all()),
        whatsapp_credentials=tuple(session.scalars(select(WhatsAppCredential).order_by(WhatsAppCredential.id)).all()),
    )


def _is_valid_meta_credentialless_tombstone(binding: MetaAssetBindingRow) -> bool:
    """Accept only the durable shape produced by deauth/data-deletion flows."""

    try:
        generation = int(binding.generation)
        created_at = float(binding.created_at)
        updated_at = float(binding.updated_at)
    except (TypeError, ValueError):
        return False
    return bool(
        binding.status == "disconnected"
        and generation >= 2
        and created_at > 0
        and updated_at >= created_at
        and str(binding.binding_id or "").strip()
        and str(binding.tenant_id or "").strip()
        and str(binding.credential_id or "").strip()
        and binding.channel in {"facebook", "instagram"}
        and str(binding.asset_id or "").strip()
        and str(binding.app_key or "").strip()
        and binding.auth_flow in {"facebook_login", "instagram_login"}
        and re.fullmatch(r"[0-9a-f]{16}", str(binding.authorized_meta_user_id_hash or ""))
    )


def validate_inventory(inventory: Inventory) -> None:
    meta_bindings = {row.binding_id: row for row in inventory.meta_bindings}
    meta_credentials = {row.credential_id: row for row in inventory.meta_credentials}
    if len(meta_bindings) != len(inventory.meta_bindings) or len(meta_credentials) != len(inventory.meta_credentials):
        raise RuntimeError("Meta credential inventory contains duplicate primary identities")
    for binding in inventory.meta_bindings:
        credential = meta_credentials.get(str(binding.credential_id or ""))
        if credential is None:
            if not _is_valid_meta_credentialless_tombstone(binding):
                raise RuntimeError("Meta binding credential inventory is incomplete")
            continue
        if credential.binding_id != binding.binding_id:
            raise RuntimeError("Meta binding credential inventory is incomplete")
    for meta_credential in inventory.meta_credentials:
        owner = meta_bindings.get(meta_credential.binding_id)
        if (
            owner is None
            or str(owner.credential_id or "") != meta_credential.credential_id
            or not str(meta_credential.aad or "")
            or not str(meta_credential.sealed or "").startswith("v1.")
            or not str(meta_credential.aad).startswith(f"{meta_credential.binding_id}:{meta_credential.credential_id}:")
        ):
            raise RuntimeError("Meta credential inventory is invalid or partial")

    wa_connections = {row.id: row for row in inventory.whatsapp_connections}
    wa_credentials = {row.id: row for row in inventory.whatsapp_credentials}
    if len(wa_connections) != len(inventory.whatsapp_connections) or len(wa_credentials) != len(
        inventory.whatsapp_credentials
    ):
        raise RuntimeError("WhatsApp credential inventory contains duplicate primary identities")
    for wa_credential in inventory.whatsapp_credentials:
        connection = wa_connections.get(str(wa_credential.connection_id or ""))
        if (
            connection is None
            or connection.tenant_id != wa_credential.tenant_id
            or str(connection.credential_id or "") != wa_credential.id
            or int(connection.credential_generation) != int(wa_credential.generation)
            or not str(wa_credential.ciphertext or "").startswith("v1.")
            or not KEY_VERSION_RE.fullmatch(str(wa_credential.encryption_key_version or ""))
        ):
            raise RuntimeError("WhatsApp credential inventory is invalid or partial")
    for connection in inventory.whatsapp_connections:
        if not connection.credential_id:
            raise RuntimeError("WhatsApp connection credential inventory is incomplete")
        linked_wa_credential = wa_credentials.get(str(connection.credential_id))
        if (
            linked_wa_credential is None
            or linked_wa_credential.connection_id != connection.id
            or linked_wa_credential.tenant_id != connection.tenant_id
            or int(linked_wa_credential.generation) != int(connection.credential_generation)
        ):
            raise RuntimeError("WhatsApp connection credential inventory is incomplete")


def _semantic_hmac(records: Sequence[Mapping[str, Any]], secret: str) -> str:
    key = hashlib.sha256(b"linas-rekey-semantic-proof-v1\x00" + secret.encode("utf-8")).digest()
    return hmac.new(key, _canonical(_normalized(list(records))), hashlib.sha256).hexdigest()


def _deterministic_rekey_seal(
    payload: Mapping[str, Any],
    *,
    new_secret: str,
    aad: str,
    transaction_id: str,
    product: str,
    source_envelope: str,
) -> str:
    """Produce a retry-stable v1 envelope without ever reusing a nonce context."""

    if not TX_RE.fullmatch(transaction_id) or product not in {"meta", "whatsapp"}:
        raise ValueError("deterministic rekey context is invalid")
    encryption_key = hashlib.sha256(b"linas-meta-registry-v1\x00" + new_secret.encode("utf-8")).digest()
    nonce_key = hashlib.sha256(b"linas-cross-product-rekey-nonce-v1\x00" + new_secret.encode("utf-8")).digest()
    nonce_context = {
        "transaction_id": transaction_id,
        "product": product,
        "aad_sha256": hashlib.sha256(aad.encode("utf-8")).hexdigest(),
        "source_envelope_sha256": hashlib.sha256(source_envelope.encode("utf-8")).hexdigest(),
    }
    nonce = hmac.new(nonce_key, _canonical(nonce_context), hashlib.sha256).digest()[:12]
    plaintext = _canonical(dict(payload))
    ciphertext = AESGCM(encryption_key).encrypt(nonce, plaintext, aad.encode("utf-8"))
    return f"v1.{_b64encode(nonce + ciphertext)}"


def prepare_rekey(
    inventory: Inventory,
    *,
    old_secret: str,
    new_secret: str,
    new_key_version: str,
    transaction_id: str = "",
) -> PreparedRekey:
    validate_inventory(inventory)
    if hmac.compare_digest(old_secret, new_secret):
        raise ValueError("old and new credential encryption keys must differ")
    if not KEY_VERSION_RE.fullmatch(new_key_version):
        raise ValueError("new WhatsApp key version is invalid")
    old_cipher = MetaCredentialCipher(old_secret)
    new_cipher = MetaCredentialCipher(new_secret)
    semantics: list[dict[str, Any]] = []
    meta_updates: list[tuple[str, str, str, str, str]] = []
    wa_updates: list[tuple[str, str, str, str, str, int, Any, str]] = []

    for meta_row in inventory.meta_credentials:
        payload = old_cipher.open(meta_row.sealed, aad=meta_row.aad)
        if not str(payload.get("access_token") or "").strip():
            raise MetaCredentialError("stored Meta credential plaintext is invalid")
        resealed = (
            _deterministic_rekey_seal(
                payload,
                new_secret=new_secret,
                aad=meta_row.aad,
                transaction_id=transaction_id,
                product="meta",
                source_envelope=meta_row.sealed,
            )
            if transaction_id
            else new_cipher.seal(payload, aad=meta_row.aad)
        )
        reopened = new_cipher.open(resealed, aad=meta_row.aad)
        if not hmac.compare_digest(_canonical(payload), _canonical(reopened)):
            raise RuntimeError("Meta credential re-seal verification failed")
        semantics.append({"product": "meta", "aad": meta_row.aad, "payload": payload})
        meta_updates.append((meta_row.credential_id, meta_row.binding_id, meta_row.aad, meta_row.sealed, resealed))
        del payload, reopened

    for wa_row in inventory.whatsapp_credentials:
        if hmac.compare_digest(str(wa_row.encryption_key_version), new_key_version):
            raise ValueError("new WhatsApp key version must advance every current credential")
        aad = f"whatsapp:{wa_row.tenant_id}:{wa_row.connection_id}"
        payload = old_cipher.open(wa_row.ciphertext, aad=aad)
        if not str(payload.get("access_token") or "").strip() or str(payload.get("channel") or "") != "whatsapp":
            raise MetaCredentialError("stored WhatsApp credential plaintext is invalid")
        resealed = (
            _deterministic_rekey_seal(
                payload,
                new_secret=new_secret,
                aad=aad,
                transaction_id=transaction_id,
                product="whatsapp",
                source_envelope=wa_row.ciphertext,
            )
            if transaction_id
            else new_cipher.seal(payload, aad=aad)
        )
        reopened = new_cipher.open(resealed, aad=aad)
        if not hmac.compare_digest(_canonical(payload), _canonical(reopened)):
            raise RuntimeError("WhatsApp credential re-seal verification failed")
        semantics.append({"product": "whatsapp", "aad": aad, "payload": payload})
        wa_updates.append(
            (
                wa_row.id,
                wa_row.tenant_id,
                wa_row.connection_id,
                wa_row.ciphertext,
                str(wa_row.encryption_key_version),
                int(wa_row.generation),
                wa_row.updated_at,
                resealed,
            )
        )
        del payload, reopened

    return PreparedRekey(
        meta_updates=tuple(meta_updates),
        whatsapp_updates=tuple(wa_updates),
        semantic_digest=_semantic_hmac(semantics, old_secret),
    )


def _decryption_semantic_digest(inventory: Inventory, *, secret: str, digest_secret: str) -> str:
    validate_inventory(inventory)
    cipher = MetaCredentialCipher(secret)
    semantics: list[dict[str, Any]] = []
    for meta_row in inventory.meta_credentials:
        payload = cipher.open(meta_row.sealed, aad=meta_row.aad)
        if not str(payload.get("access_token") or "").strip():
            raise MetaCredentialError("stored Meta credential plaintext is invalid")
        semantics.append({"product": "meta", "aad": meta_row.aad, "payload": payload})
    for wa_row in inventory.whatsapp_credentials:
        aad = f"whatsapp:{wa_row.tenant_id}:{wa_row.connection_id}"
        payload = cipher.open(wa_row.ciphertext, aad=aad)
        if not str(payload.get("access_token") or "").strip() or str(payload.get("channel") or "") != "whatsapp":
            raise MetaCredentialError("stored WhatsApp credential plaintext is invalid")
        semantics.append({"product": "whatsapp", "aad": aad, "payload": payload})
    return _semantic_hmac(semantics, digest_secret)


def _target_snapshot_from_prepared(
    source_snapshot: Mapping[str, Any],
    prepared: PreparedRekey,
    *,
    new_key_version: str,
) -> dict[str, Any]:
    target = cast(dict[str, Any], json.loads(_canonical(_normalized(source_snapshot))))
    meta_targets = {credential_id: sealed for credential_id, _binding, _aad, _old, sealed in prepared.meta_updates}
    wa_targets = {credential_id: ciphertext for credential_id, *_rest, ciphertext in prepared.whatsapp_updates}
    for row in target.get("meta_credentials", []):
        row["sealed"] = meta_targets[str(row["credential_id"])]
    for row in target.get("whatsapp_credentials", []):
        row["ciphertext"] = wa_targets[str(row["id"])]
        row["encryption_key_version"] = new_key_version
    return target


def _ensure_preimage(
    path: Path,
    snapshot: Mapping[str, Any],
    *,
    recovery_secret: str,
    label: str,
) -> dict[str, Any]:
    """Create once or authenticate an exact prior crash artifact."""

    try:
        existing = read_preimage(path, recovery_secret=recovery_secret)
    except FileNotFoundError:
        write_preimage(path, snapshot, recovery_secret=recovery_secret)
        existing = read_preimage(path, recovery_secret=recovery_secret)
    if _fingerprint_snapshot(existing) != _fingerprint_snapshot(snapshot):
        raise RuntimeError(f"{label} does not match the certified database source")
    return existing


def apply_rekey_transaction(
    session: Session,
    *,
    old_secret: str,
    new_secret: str,
    new_key_version: str,
    expected_current_sha256: str,
    preimage_path: Path,
    recovery_secret: str,
    transaction_id: str = "",
    certified_target_sha256: str = "",
    before_updates: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None = None,
    fail_after_updates: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply both products atomically; caller owns transaction commit/rollback."""

    if hmac.compare_digest(recovery_secret, old_secret) or hmac.compare_digest(recovery_secret, new_secret):
        raise ValueError("recovery key must be independent from old and new runtime keys")
    _acquire_database_locks(session, apply=True)
    before_inventory = load_inventory(session)
    before_snapshot = _snapshot(before_inventory)
    before_fp = _fingerprint_snapshot(before_snapshot)
    if before_fp["full_sha256"] != expected_current_sha256:
        if not certified_target_sha256 or before_fp["full_sha256"] != certified_target_sha256:
            raise RuntimeError("credential inventory is neither certified source nor target")
        source_snapshot = read_preimage(preimage_path, recovery_secret=recovery_secret)
        source_fp = _fingerprint_snapshot(source_snapshot)
        if (
            source_fp["full_sha256"] != expected_current_sha256
            or source_fp["structural_sha256"] != before_fp["structural_sha256"]
        ):
            raise RuntimeError("certified source preimage does not match the committed target")
        source_semantic = _preimage_decryption_semantic_digest(
            source_snapshot,
            secret=old_secret,
            digest_secret=recovery_secret,
        )
        target_semantic = _decryption_semantic_digest(
            before_inventory,
            secret=new_secret,
            digest_secret=recovery_secret,
        )
        if not hmac.compare_digest(source_semantic, target_semantic):
            raise RuntimeError("certified source and target credential plaintext differ")
        if before_updates is not None:
            before_updates(source_fp, before_fp)
        return source_fp, before_fp
    prepared = prepare_rekey(
        before_inventory,
        old_secret=old_secret,
        new_secret=new_secret,
        new_key_version=new_key_version,
        transaction_id=transaction_id,
    )
    _ensure_preimage(
        preimage_path,
        before_snapshot,
        recovery_secret=recovery_secret,
        label="cross-product preimage",
    )
    target_snapshot = _target_snapshot_from_prepared(
        before_snapshot,
        prepared,
        new_key_version=new_key_version,
    )
    target_fp = _fingerprint_snapshot(target_snapshot)
    if certified_target_sha256 and target_fp["full_sha256"] != certified_target_sha256:
        raise RuntimeError("retry target does not match its durable database certificate")
    if before_updates is not None:
        before_updates(before_fp, target_fp)

    updates_done = 0
    for credential_id, binding_id, aad, old_sealed, new_sealed in prepared.meta_updates:
        result = session.execute(
            update(MetaBindingCredentialRow)
            .where(
                MetaBindingCredentialRow.credential_id == credential_id,
                MetaBindingCredentialRow.binding_id == binding_id,
                MetaBindingCredentialRow.aad == aad,
                MetaBindingCredentialRow.sealed == old_sealed,
            )
            .values(sealed=new_sealed)
        )
        if result.rowcount != 1:
            raise RuntimeError("Meta credential CAS update failed")
        updates_done += 1
        if fail_after_updates is not None and updates_done >= fail_after_updates:
            raise RuntimeError("injected rekey failure")

    for (
        credential_id,
        tenant_id,
        connection_id,
        old_ciphertext,
        old_version,
        generation,
        old_updated_at,
        new_ciphertext,
    ) in prepared.whatsapp_updates:
        result = session.execute(
            update(WhatsAppCredential)
            .where(
                WhatsAppCredential.id == credential_id,
                WhatsAppCredential.tenant_id == tenant_id,
                WhatsAppCredential.connection_id == connection_id,
                WhatsAppCredential.generation == generation,
                WhatsAppCredential.ciphertext == old_ciphertext,
                WhatsAppCredential.encryption_key_version == old_version,
            )
            .values(
                ciphertext=new_ciphertext,
                encryption_key_version=new_key_version,
                updated_at=old_updated_at,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("WhatsApp credential CAS update failed")
        updates_done += 1
        if fail_after_updates is not None and updates_done >= fail_after_updates:
            raise RuntimeError("injected rekey failure")

    session.flush()
    after_inventory = load_inventory(session)
    after_snapshot = _snapshot(after_inventory)
    after_fp = _fingerprint_snapshot(after_snapshot)
    if after_fp != target_fp:
        raise RuntimeError("database result differs from the certified retry-stable target")
    if after_fp["structural_sha256"] != before_fp["structural_sha256"]:
        raise RuntimeError("credential ownership or generation changed during rekey")
    after_semantic = _decryption_semantic_digest(
        after_inventory,
        secret=new_secret,
        digest_secret=old_secret,
    )
    if not hmac.compare_digest(after_semantic, prepared.semantic_digest):
        raise RuntimeError("cross-product plaintext verification failed")
    return before_fp, after_fp


def restore_preimage_transaction(
    session: Session,
    *,
    current_secret: str,
    restored_secret: str,
    expected_current_sha256: str,
    preimage: Mapping[str, Any],
    pre_rollback_path: Path,
    recovery_secret: str,
    certified_target_sha256: str = "",
    before_updates: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None = None,
    fail_after_updates: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """CAS-restore credential ciphertexts only; never insert/delete owner rows."""

    if hmac.compare_digest(recovery_secret, current_secret) or hmac.compare_digest(recovery_secret, restored_secret):
        raise ValueError("recovery key must be independent from runtime keys")
    _acquire_database_locks(session, apply=True)
    current_inventory = load_inventory(session)
    current_snapshot = _snapshot(current_inventory)
    current_fp = _fingerprint_snapshot(current_snapshot)
    desired_fp = _fingerprint_snapshot(preimage)
    if current_fp["full_sha256"] != expected_current_sha256:
        if (
            not certified_target_sha256
            or current_fp["full_sha256"] != certified_target_sha256
            or desired_fp["full_sha256"] != certified_target_sha256
        ):
            raise RuntimeError("rollback inventory is neither certified source nor target")
        source_snapshot = read_preimage(pre_rollback_path, recovery_secret=recovery_secret)
        source_fp = _fingerprint_snapshot(source_snapshot)
        if (
            source_fp["full_sha256"] != expected_current_sha256
            or source_fp["structural_sha256"] != current_fp["structural_sha256"]
        ):
            raise RuntimeError("pre-rollback source does not match the committed target")
        source_semantic = _preimage_decryption_semantic_digest(
            source_snapshot,
            secret=current_secret,
            digest_secret=recovery_secret,
        )
        target_semantic = _decryption_semantic_digest(
            current_inventory,
            secret=restored_secret,
            digest_secret=recovery_secret,
        )
        if not hmac.compare_digest(source_semantic, target_semantic):
            raise RuntimeError("rollback source and target credential plaintext differ")
        if before_updates is not None:
            before_updates(source_fp, current_fp)
        return source_fp, current_fp
    if current_fp["structural_sha256"] != desired_fp["structural_sha256"]:
        raise RuntimeError("preimage ownership inventory no longer matches current PostgreSQL")
    current_semantic = _decryption_semantic_digest(
        current_inventory,
        secret=current_secret,
        digest_secret=recovery_secret,
    )
    desired_semantic = _preimage_decryption_semantic_digest(
        preimage,
        secret=restored_secret,
        digest_secret=recovery_secret,
    )
    if not hmac.compare_digest(current_semantic, desired_semantic):
        raise RuntimeError("rollback would overwrite changed credential plaintext")
    _ensure_preimage(
        pre_rollback_path,
        current_snapshot,
        recovery_secret=recovery_secret,
        label="pre-rollback backup",
    )
    if before_updates is not None:
        before_updates(current_fp, desired_fp)

    desired_meta = {str(row["credential_id"]): row for row in preimage["meta_credentials"]}
    desired_wa = {str(row["id"]): row for row in preimage["whatsapp_credentials"]}
    updates_done = 0
    for meta_row in current_inventory.meta_credentials:
        meta_desired = desired_meta.get(meta_row.credential_id)
        if meta_desired is None:
            raise RuntimeError("Meta preimage inventory is incomplete")
        meta_result = session.execute(
            update(MetaBindingCredentialRow)
            .where(
                MetaBindingCredentialRow.credential_id == meta_row.credential_id,
                MetaBindingCredentialRow.sealed == meta_row.sealed,
                MetaBindingCredentialRow.aad == meta_row.aad,
            )
            .values(sealed=str(meta_desired["sealed"]))
        )
        if meta_result.rowcount != 1:
            raise RuntimeError("Meta preimage CAS restore failed")
        updates_done += 1
        if fail_after_updates is not None and updates_done >= fail_after_updates:
            raise RuntimeError("injected rollback failure")
    for wa_row in current_inventory.whatsapp_credentials:
        wa_desired = desired_wa.get(wa_row.id)
        if wa_desired is None:
            raise RuntimeError("WhatsApp preimage inventory is incomplete")
        wa_result = session.execute(
            update(WhatsAppCredential)
            .where(
                WhatsAppCredential.id == wa_row.id,
                WhatsAppCredential.ciphertext == wa_row.ciphertext,
                WhatsAppCredential.encryption_key_version == wa_row.encryption_key_version,
            )
            .values(
                ciphertext=str(wa_desired["ciphertext"]),
                encryption_key_version=str(wa_desired["encryption_key_version"]),
                updated_at=wa_row.updated_at,
            )
        )
        if wa_result.rowcount != 1:
            raise RuntimeError("WhatsApp preimage CAS restore failed")
        updates_done += 1
        if fail_after_updates is not None and updates_done >= fail_after_updates:
            raise RuntimeError("injected rollback failure")
    session.flush()
    restored_inventory = load_inventory(session)
    restored_fp = _fingerprint_snapshot(_snapshot(restored_inventory))
    if restored_fp != desired_fp:
        raise RuntimeError("cross-product preimage restore verification failed")
    _validate_inventory_decryption(restored_inventory, restored_secret)
    return current_fp, restored_fp


def _preimage_key(recovery_secret: str) -> bytes:
    return hashlib.sha256(b"linas-meta-whatsapp-preimage-key-v1\x00" + recovery_secret.encode("utf-8")).digest()


def encode_preimage(snapshot: Mapping[str, Any], *, recovery_secret: str) -> dict[str, Any]:
    fingerprint = _fingerprint_snapshot(snapshot)
    metadata = {
        "format": FORMAT,
        "created_at": int(time.time()),
        "fingerprint": fingerprint,
    }
    nonce = os.urandom(12)
    plaintext = _canonical(_normalized(snapshot))
    aad = FORMAT_AAD + b"\x00" + _canonical(metadata)
    ciphertext = AESGCM(_preimage_key(recovery_secret)).encrypt(nonce, plaintext, aad)
    return {**metadata, "nonce": _b64encode(nonce), "ciphertext": _b64encode(ciphertext)}


def decode_preimage(envelope: Mapping[str, Any], *, recovery_secret: str) -> dict[str, Any]:
    try:
        if envelope.get("format") != FORMAT:
            raise ValueError("unsupported format")
        metadata = {
            "format": str(envelope["format"]),
            "created_at": int(envelope["created_at"]),
            "fingerprint": envelope["fingerprint"],
        }
        aad = FORMAT_AAD + b"\x00" + _canonical(metadata)
        plaintext = AESGCM(_preimage_key(recovery_secret)).decrypt(
            _b64decode(str(envelope["nonce"])),
            _b64decode(str(envelope["ciphertext"])),
            aad,
        )
        snapshot = json.loads(plaintext)
        if not isinstance(snapshot, dict) or _fingerprint_snapshot(snapshot) != metadata["fingerprint"]:
            raise ValueError("fingerprint mismatch")
        return snapshot
    except Exception as exc:  # noqa: BLE001 - normalize without secret-bearing detail.
        raise ValueError("cross-product preimage authentication failed") from exc


def write_preimage(path: Path, snapshot: Mapping[str, Any], *, recovery_secret: str) -> None:
    envelope = encode_preimage(snapshot, recovery_secret=recovery_secret)
    _write_no_clobber(path, _canonical(envelope) + b"\n")


def read_preimage(path: Path, *, recovery_secret: str) -> dict[str, Any]:
    payload = _read_exact(path, label="cross-product preimage")
    try:
        envelope = json.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("cross-product preimage authentication failed") from exc
    if not isinstance(envelope, dict):
        raise ValueError("cross-product preimage authentication failed")
    return decode_preimage(envelope, recovery_secret=recovery_secret)


def _inventory_from_snapshot(snapshot: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    meta = snapshot.get("meta_credentials")
    wa = snapshot.get("whatsapp_credentials")
    if not isinstance(meta, list) or not isinstance(wa, list):
        raise ValueError("cross-product preimage inventory is invalid")
    if any(not isinstance(row, dict) for row in (*meta, *wa)):
        raise ValueError("cross-product preimage inventory is invalid")
    return list(meta), list(wa)


def _preimage_decryption_semantic_digest(
    snapshot: Mapping[str, Any],
    *,
    secret: str,
    digest_secret: str,
) -> str:
    meta, wa = _inventory_from_snapshot(snapshot)
    cipher = MetaCredentialCipher(secret)
    semantics: list[dict[str, Any]] = []
    for row in meta:
        aad = str(row.get("aad") or "")
        payload = cipher.open(str(row.get("sealed") or ""), aad=aad)
        if not str(payload.get("access_token") or "").strip():
            raise MetaCredentialError("stored Meta credential plaintext is invalid")
        semantics.append({"product": "meta", "aad": aad, "payload": payload})
    for row in wa:
        aad = f"whatsapp:{row.get('tenant_id')}:{row.get('connection_id')}"
        payload = cipher.open(str(row.get("ciphertext") or ""), aad=aad)
        if not str(payload.get("access_token") or "").strip() or str(payload.get("channel") or "") != "whatsapp":
            raise MetaCredentialError("stored WhatsApp credential plaintext is invalid")
        semantics.append({"product": "whatsapp", "aad": aad, "payload": payload})
    return _semantic_hmac(semantics, digest_secret)


def _validate_preimage_decryption(snapshot: Mapping[str, Any], secret: str) -> None:
    _preimage_decryption_semantic_digest(snapshot, secret=secret, digest_secret=secret)


def _validate_inventory_decryption(inventory: Inventory, secret: str) -> None:
    _decryption_semantic_digest(inventory, secret=secret, digest_secret=secret)


def _proof_key(proof_secret: str, *, environment: bool = False) -> bytes:
    domain = b"linas-env-proof-v1\x00" if environment else b"linas-offline-proof-v1\x00"
    return hashlib.sha256(domain + proof_secret.encode("utf-8")).digest()


def _sign_proof(payload: Mapping[str, Any], proof_secret: str, *, environment: bool = False) -> dict[str, Any]:
    body = dict(payload)
    signature = hmac.new(
        _proof_key(proof_secret, environment=environment), _canonical(body), hashlib.sha256
    ).hexdigest()
    return {**body, "signature": signature}


def _attach_node_signature(
    proof: Mapping[str, Any],
    *,
    node_id: str,
    signing_key: Ed25519PrivateKey,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> dict[str, Any]:
    _require_matching_node_signing_key(
        node_id=node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )
    body = {key: value for key, value in proof.items() if key != "node_signature"}
    return {**body, "node_signature": _b64encode(signing_key.sign(_canonical(body)))}


def _require_matching_node_signing_key(
    *,
    node_id: str,
    signing_key: Ed25519PrivateKey,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> None:
    if node_id not in REQUIRED_NODES or set(verification_keys) != set(REQUIRED_NODES):
        raise PermissionError("fixed node signing identity is invalid")
    actual_public = _public_key_bytes(signing_key.public_key())
    expected_public = _public_key_bytes(verification_keys[node_id])
    if not hmac.compare_digest(actual_public, expected_public):
        raise PermissionError("node signing key does not match its pinned verification key")


def _verify_proof_signature(proof: Mapping[str, Any], proof_secret: str, *, environment: bool = False) -> None:
    body = {key: value for key, value in proof.items() if key not in {"signature", "node_signature"}}
    expected = hmac.new(_proof_key(proof_secret, environment=environment), _canonical(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(proof.get("signature") or ""), expected):
        raise PermissionError("HA proof authentication failed")


def _verify_node_signature(proof: Mapping[str, Any], verification_keys: Mapping[str, Ed25519PublicKey]) -> None:
    node_id = str(proof.get("node_id") or "")
    if node_id not in REQUIRED_NODES or set(verification_keys) != set(REQUIRED_NODES):
        raise PermissionError("HA node signature identity is invalid")
    body = {key: value for key, value in proof.items() if key != "node_signature"}
    try:
        verification_keys[node_id].verify(
            _b64decode(str(proof.get("node_signature") or "")),
            _canonical(body),
        )
    except (InvalidSignature, ValueError) as exc:
        raise PermissionError("HA node signature authentication failed") from exc


def _unit_is_offline(unit: str) -> bool:
    result = subprocess.run(  # nosec B603 - unit comes only from fixed ALL_RUNTIME_UNITS.
        ["/usr/bin/systemctl", "is-active", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    state = result.stdout.strip().lower()
    return result.returncode != 0 and state in {"inactive", "failed", "unknown", "not-found"}


def _application_ports_closed() -> bool:
    for port in (8003, 8000):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(0.5)
            if client.connect_ex(("127.0.0.1", port)) == 0:
                return False
    return True


def _validate_maintenance_marker(path: Path = PERSISTENT_MAINTENANCE) -> None:
    _secure_regular_file(path, label="persistent maintenance marker")
    if path.resolve() != PERSISTENT_MAINTENANCE:
        raise RuntimeError("only the canonical persistent maintenance marker is accepted")


def _require_no_conflicting_ha_transaction(paths: tuple[Path, ...] = REKEY_COLLISION_PATHS) -> None:
    if any(path.exists() or path.is_symlink() for path in paths):
        raise RuntimeError("another durable HA transaction requires confirmed recovery")


def inspect_offline_contract(
    *,
    env_path: Path,
    node_id: str,
    transaction_id: str,
    unit_checker: Any = _unit_is_offline,
    port_checker: Any = _application_ports_closed,
    marker_checker: Any = _validate_maintenance_marker,
    collision_checker: Any = _require_no_conflicting_ha_transaction,
    canonical_env_checker: Any = _canonical_env_identity,
    identity_checker: Any = _attest_host_identity,
) -> tuple[dict[str, str], str]:
    if node_id not in REQUIRED_NODES or not TX_RE.fullmatch(transaction_id):
        raise ValueError("HA proof identity is invalid")
    canonical_env_checker(env_path)
    identity_checker(node_id)
    collision_checker()
    values, secret = _load_runtime_env(env_path)
    if str(values.get("META_DELETION_NODE_ID") or "").strip() != node_id:
        raise RuntimeError("canonical environment has the wrong HA node identity")
    membership = tuple(
        sorted(
            item.strip() for item in str(values.get("META_DELETION_REQUIRED_NODES") or "").split(",") if item.strip()
        )
    )
    if membership != REQUIRED_NODES:
        raise RuntimeError("canonical environment does not declare exact two-node membership")
    if str(values.get("META_HA_LB_READY_HEALTHCHECK_APPROVED") or "").strip().lower() != "true":
        raise RuntimeError("the /api/ready load-balancer health check is not owner-approved")
    if str(values.get("LINAS_MAINTENANCE_DRAIN_FILE") or "").strip() != str(PERSISTENT_MAINTENANCE):
        raise RuntimeError("canonical persistent maintenance path is not configured")
    marker_checker()
    if any(not unit_checker(unit) for unit in ALL_RUNTIME_UNITS) or not port_checker():
        raise RuntimeError("API and all Meta/WhatsApp workers must be offline")
    return values, secret


def build_offline_proof(
    *,
    env_path: Path,
    node_id: str,
    transaction_id: str,
    env_backup_path: Path,
    proof_secret: str,
    signing_key: Ed25519PrivateKey,
    verification_keys: Mapping[str, Ed25519PublicKey],
    now: int | None = None,
    unit_checker: Any = _unit_is_offline,
    port_checker: Any = _application_ports_closed,
    marker_checker: Any = _validate_maintenance_marker,
    guard_checker: Any = _validate_transaction_guard,
    canonical_env_checker: Any = _canonical_env_identity,
    identity_checker: Any = _attest_host_identity,
) -> dict[str, Any]:
    _, runtime_secret = inspect_offline_contract(
        env_path=env_path,
        node_id=node_id,
        transaction_id=transaction_id,
        unit_checker=unit_checker,
        port_checker=port_checker,
        marker_checker=marker_checker,
        canonical_env_checker=canonical_env_checker,
        identity_checker=identity_checker,
    )
    if hmac.compare_digest(proof_secret, runtime_secret):
        raise ValueError("transaction proof key must be independent from the runtime key")
    host_identity = identity_checker(node_id)
    guard_sha = guard_checker(
        node_id=node_id,
        transaction_id=transaction_id,
        proof_secret=proof_secret,
    )
    backup_sha = _copy_no_clobber(env_path, env_backup_path)
    created_at = int(now if now is not None else time.time())
    proof = {
        "format": PROOF_FORMAT,
        "transaction_id": transaction_id,
        "node_id": node_id,
        "created_at": created_at,
        "expires_at": created_at + PROOF_MAX_AGE_SECONDS,
        "backend": "postgres",
        "required_nodes": list(REQUIRED_NODES),
        "persistent_maintenance": True,
        "all_runtime_units_offline": True,
        "application_ports_closed": True,
        "lb_health_path": "/api/ready",
        "runtime_guard_path": str(REKEY_GUARD_MARKER),
        "runtime_guard_transaction_id": transaction_id,
        "runtime_guarded_units": list(GUARDED_SYSTEMD_UNITS),
        "runtime_guard_sha256": guard_sha,
        "host_identity": host_identity,
        "verification_set_fingerprint": _verification_set_fingerprint(verification_keys),
        "node_verification_key_fingerprint": _verification_key_fingerprint(verification_keys[node_id]),
        "key_fingerprint": _key_fingerprint(runtime_secret),
        "env_backup_sha256": backup_sha,
    }
    return _attach_node_signature(
        _sign_proof(proof, proof_secret),
        node_id=node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )


def validate_offline_proofs(
    paths: Sequence[Path],
    *,
    proof_secret: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
    runtime_secret: str,
    transaction_id: str,
    now: int | None = None,
    require_fresh: bool = True,
) -> dict[str, dict[str, Any]]:
    if len(paths) != 2 or not TX_RE.fullmatch(transaction_id):
        raise PermissionError("exactly two HA offline proofs are required")
    current_time = int(now if now is not None else time.time())
    found: dict[str, dict[str, Any]] = {}
    for path in paths:
        raw = json.loads(_read_exact(path, label="HA offline proof"))
        if not isinstance(raw, dict):
            raise PermissionError("HA offline proof is invalid")
        _verify_proof_signature(raw, proof_secret)
        _verify_node_signature(raw, verification_keys)
        node = str(raw.get("node_id") or "")
        if node not in REQUIRED_NODES or node in found:
            raise PermissionError("HA offline proof contract is invalid")
        host_identity = _validate_attested_identity(raw.get("host_identity"), node_id=node)
        expected = {
            "format": PROOF_FORMAT,
            "transaction_id": transaction_id,
            "backend": "postgres",
            "required_nodes": list(REQUIRED_NODES),
            "persistent_maintenance": True,
            "all_runtime_units_offline": True,
            "application_ports_closed": True,
            "lb_health_path": "/api/ready",
            "runtime_guard_path": str(REKEY_GUARD_MARKER),
            "runtime_guard_transaction_id": transaction_id,
            "runtime_guarded_units": list(GUARDED_SYSTEMD_UNITS),
            "runtime_guard_sha256": hashlib.sha256(
                _guard_payload(
                    node_id=node,
                    transaction_id=transaction_id,
                    proof_secret=proof_secret,
                    host_identity=host_identity,
                )
            ).hexdigest(),
            "host_identity": host_identity,
            "verification_set_fingerprint": _verification_set_fingerprint(verification_keys),
            "node_verification_key_fingerprint": _verification_key_fingerprint(verification_keys[node]),
            "key_fingerprint": _key_fingerprint(runtime_secret),
        }
        if any(raw.get(key) != value for key, value in expected.items()):
            raise PermissionError("HA offline proof contract is invalid")
        created_at = int(raw.get("created_at") or 0)
        expires_at = int(raw.get("expires_at") or 0)
        invalid_time_contract = expires_at - created_at != PROOF_MAX_AGE_SECONDS or created_at <= 0
        if require_fresh:
            invalid_time_contract = invalid_time_contract or created_at > current_time + 5 or expires_at < current_time
        if invalid_time_contract:
            raise PermissionError("HA offline proof is stale")
        if not SHA256_RE.fullmatch(str(raw.get("env_backup_sha256") or "")):
            raise PermissionError("HA offline proof lacks an environment backup")
        found[node] = dict(raw)
    if tuple(sorted(found)) != REQUIRED_NODES:
        raise PermissionError("offline proofs do not cover both fixed HA nodes")
    machine_ids = {str(proof["host_identity"]["machine_id_sha256"]) for proof in found.values()}
    if len(machine_ids) != len(REQUIRED_NODES):
        raise PermissionError("offline proofs came from the same physical host")
    return found


def _proof_artifact_digests(
    paths: Sequence[Path],
    proofs: Mapping[str, Mapping[str, Any]],
    *,
    label: str,
) -> dict[str, str]:
    """Bind exact protected proof files to fixed node labels."""

    digests: dict[str, str] = {}
    for path in paths:
        payload = _read_exact(path, label=label)
        try:
            raw = json.loads(payload)
        except Exception as exc:  # noqa: BLE001 - normalize without artifact content.
            raise PermissionError(f"{label} is invalid") from exc
        if not isinstance(raw, dict):
            raise PermissionError(f"{label} is invalid")
        node_id = str(raw.get("node_id") or "")
        if node_id not in REQUIRED_NODES or node_id in digests or raw != proofs.get(node_id):
            raise PermissionError(f"{label} changed after validation")
        digests[node_id] = hashlib.sha256(payload).hexdigest()
    if tuple(sorted(digests)) != REQUIRED_NODES:
        raise PermissionError(f"{label} does not cover both fixed HA nodes")
    return digests


def _build_database_transition_certificate(
    *,
    operation: str,
    transaction_id: str,
    source_secret: str,
    target_secret: str,
    source_fingerprint: Mapping[str, Any],
    target_fingerprint: Mapping[str, Any],
    proof_secret: str,
    signing_key: Ed25519PrivateKey,
    verification_keys: Mapping[str, Ed25519PublicKey],
    offline_proofs: Mapping[str, Mapping[str, Any]],
    offline_proof_digests: Mapping[str, str],
    artifact_digests: Mapping[str, str],
) -> dict[str, Any]:
    if operation not in {"rekey", "rollback"} or not TX_RE.fullmatch(transaction_id):
        raise ValueError("database transition certificate identity is invalid")
    if source_fingerprint.get("structural_sha256") != target_fingerprint.get("structural_sha256"):
        raise RuntimeError("database transition changed credential ownership structure")
    if set(offline_proofs) != set(REQUIRED_NODES) or set(offline_proof_digests) != set(REQUIRED_NODES):
        raise PermissionError("database transition certificate lacks both node proofs")
    if not artifact_digests or any(not SHA256_RE.fullmatch(str(value)) for value in artifact_digests.values()):
        raise ValueError("database transition certificate artifact digest is invalid")
    body = {
        "format": DATABASE_CERTIFICATE_FORMAT,
        "operation": operation,
        "transaction_id": transaction_id,
        "node_id": "node01",
        "created_at": int(time.time()),
        "source_database_sha256": str(source_fingerprint["full_sha256"]),
        "target_database_sha256": str(target_fingerprint["full_sha256"]),
        "structural_sha256": str(target_fingerprint["structural_sha256"]),
        "source_key_fingerprint": _key_fingerprint(source_secret),
        "target_key_fingerprint": _key_fingerprint(target_secret),
        "offline_proofs_sha256": dict(offline_proof_digests),
        "env_backups_sha256": {node: str(offline_proofs[node]["env_backup_sha256"]) for node in REQUIRED_NODES},
        "runtime_guards_sha256": {node: str(offline_proofs[node]["runtime_guard_sha256"]) for node in REQUIRED_NODES},
        "artifacts_sha256": dict(sorted(artifact_digests.items())),
        "verification_set_fingerprint": _verification_set_fingerprint(verification_keys),
        "signer_host_identity": offline_proofs["node01"]["host_identity"],
    }
    return _attach_node_signature(
        _sign_proof(body, proof_secret),
        node_id="node01",
        signing_key=signing_key,
        verification_keys=verification_keys,
    )


def _validate_database_certificate_envelope(
    path: Path,
    *,
    proof_secret: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
    target_secret: str,
    transaction_id: str,
    target_database_sha: str,
    operation: str | None = None,
) -> tuple[dict[str, Any], str]:
    payload = _read_exact(path, label="database transition certificate")
    try:
        certificate = json.loads(payload)
    except Exception as exc:  # noqa: BLE001 - normalize without artifact content.
        raise PermissionError("database transition certificate is invalid") from exc
    if not isinstance(certificate, dict):
        raise PermissionError("database transition certificate is invalid")
    _verify_proof_signature(certificate, proof_secret)
    _verify_node_signature(certificate, verification_keys)
    signer_identity = _validate_attested_identity(certificate.get("signer_host_identity"), node_id="node01")
    cert_operation = str(certificate.get("operation") or "")
    offline_digests = certificate.get("offline_proofs_sha256")
    backup_digests = certificate.get("env_backups_sha256")
    guard_digests = certificate.get("runtime_guards_sha256")
    artifact_digests = certificate.get("artifacts_sha256")
    if (
        certificate.get("format") != DATABASE_CERTIFICATE_FORMAT
        or cert_operation not in {"rekey", "rollback"}
        or (operation is not None and cert_operation != operation)
        or certificate.get("transaction_id") != transaction_id
        or certificate.get("node_id") != "node01"
        or int(certificate.get("created_at") or 0) <= 0
        or certificate.get("target_database_sha256") != target_database_sha
        or certificate.get("target_key_fingerprint") != _key_fingerprint(target_secret)
        or certificate.get("verification_set_fingerprint") != _verification_set_fingerprint(verification_keys)
        or certificate.get("signer_host_identity") != signer_identity
        or not SHA256_RE.fullmatch(str(certificate.get("source_database_sha256") or ""))
        or not SHA256_RE.fullmatch(str(certificate.get("structural_sha256") or ""))
        or not SHA256_RE.fullmatch(str(certificate.get("source_key_fingerprint") or ""))
        or not isinstance(offline_digests, dict)
        or set(offline_digests) != set(REQUIRED_NODES)
        or any(not SHA256_RE.fullmatch(str(value)) for value in offline_digests.values())
        or not isinstance(backup_digests, dict)
        or set(backup_digests) != set(REQUIRED_NODES)
        or any(not SHA256_RE.fullmatch(str(value)) for value in backup_digests.values())
        or not isinstance(guard_digests, dict)
        or set(guard_digests) != set(REQUIRED_NODES)
        or any(not SHA256_RE.fullmatch(str(value)) for value in guard_digests.values())
        or not isinstance(artifact_digests, dict)
        or not artifact_digests
        or any(not SHA256_RE.fullmatch(str(value)) for value in artifact_digests.values())
    ):
        raise PermissionError("database transition certificate contract is invalid")
    return certificate, hashlib.sha256(payload).hexdigest()


def validate_database_transition_certificate(
    path: Path,
    *,
    proof_secret: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
    source_secret: str,
    target_secret: str,
    transaction_id: str,
    target_database_sha: str,
    operation: str,
    offline_proof_paths: Sequence[Path],
    source_database_sha: str = "",
) -> tuple[dict[str, dict[str, Any]], str]:
    """Authorize crash-safe continuation using proofs fresh at DB transition time."""

    certificate, certificate_sha = _validate_database_certificate_envelope(
        path,
        proof_secret=proof_secret,
        verification_keys=verification_keys,
        target_secret=target_secret,
        transaction_id=transaction_id,
        target_database_sha=target_database_sha,
        operation=operation,
    )
    if certificate.get("source_key_fingerprint") != _key_fingerprint(source_secret):
        raise PermissionError("database transition certificate source key is invalid")
    if source_database_sha and certificate.get("source_database_sha256") != source_database_sha:
        raise PermissionError("database transition certificate source database is invalid")
    proofs = validate_offline_proofs(
        offline_proof_paths,
        proof_secret=proof_secret,
        verification_keys=verification_keys,
        runtime_secret=source_secret,
        transaction_id=transaction_id,
        require_fresh=False,
    )
    proof_digests = _proof_artifact_digests(
        offline_proof_paths,
        proofs,
        label="HA offline proof",
    )
    if proof_digests != certificate.get("offline_proofs_sha256"):
        raise PermissionError("database transition certificate proof binding is invalid")
    if {node: str(proofs[node]["env_backup_sha256"]) for node in REQUIRED_NODES} != certificate.get(
        "env_backups_sha256"
    ):
        raise PermissionError("database transition certificate backup binding is invalid")
    if {node: str(proofs[node]["runtime_guard_sha256"]) for node in REQUIRED_NODES} != certificate.get(
        "runtime_guards_sha256"
    ):
        raise PermissionError("database transition certificate guard binding is invalid")
    return proofs, certificate_sha


def validate_env_backup_attestation(
    path: Path,
    *,
    proof_secret: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
    runtime_secret: str,
    transaction_id: str,
    node_id: str,
    env_backup_path: Path,
) -> None:
    """Authenticate an original env backup proof without requiring it to be fresh."""

    raw = json.loads(_read_exact(path, label="original HA offline proof"))
    if not isinstance(raw, dict):
        raise PermissionError("original HA offline proof is invalid")
    _verify_proof_signature(raw, proof_secret)
    _verify_node_signature(raw, verification_keys)
    host_identity = _validate_attested_identity(raw.get("host_identity"), node_id=node_id)
    if (
        raw.get("format") != PROOF_FORMAT
        or raw.get("transaction_id") != transaction_id
        or raw.get("node_id") != node_id
        or raw.get("backend") != "postgres"
        or raw.get("required_nodes") != list(REQUIRED_NODES)
        or raw.get("persistent_maintenance") is not True
        or raw.get("all_runtime_units_offline") is not True
        or raw.get("application_ports_closed") is not True
        or raw.get("lb_health_path") != "/api/ready"
        or raw.get("runtime_guard_path") != str(REKEY_GUARD_MARKER)
        or raw.get("runtime_guard_transaction_id") != transaction_id
        or raw.get("runtime_guarded_units") != list(GUARDED_SYSTEMD_UNITS)
        or raw.get("runtime_guard_sha256")
        != hashlib.sha256(
            _guard_payload(
                node_id=node_id,
                transaction_id=transaction_id,
                proof_secret=proof_secret,
                host_identity=host_identity,
            )
        ).hexdigest()
        or raw.get("host_identity") != host_identity
        or raw.get("verification_set_fingerprint") != _verification_set_fingerprint(verification_keys)
        or raw.get("node_verification_key_fingerprint") != _verification_key_fingerprint(verification_keys[node_id])
        or raw.get("key_fingerprint") != _key_fingerprint(runtime_secret)
    ):
        raise PermissionError("original environment backup attestation is invalid")
    backup_sha = hashlib.sha256(_read_exact(env_backup_path, label="original environment backup")).hexdigest()
    if not hmac.compare_digest(backup_sha, str(raw.get("env_backup_sha256") or "")):
        raise PermissionError("original environment backup no longer matches its signed attestation")


def rekey_confirmation(
    current_sha: str,
    new_secret: str,
    recovery_secret: str,
    proof_secret: str,
    transaction_id: str,
    new_key_version: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> str:
    material = _digest(
        {
            "new": _key_fingerprint(new_secret),
            "recovery": _key_fingerprint(recovery_secret),
            "proof": _key_fingerprint(proof_secret),
            "key_version": new_key_version,
            "verification_keys": _verification_set_fingerprint(verification_keys),
        }
    )
    return f"REKEY_META_WHATSAPP_{current_sha[:16].upper()}_{material[:12].upper()}_{transaction_id[:8].upper()}"


def rollback_confirmation(
    current_sha: str,
    desired_sha: str,
    restored_secret: str,
    recovery_secret: str,
    proof_secret: str,
    original_proof_secret: str,
    transaction_id: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> str:
    material = _digest(
        {
            "restored": _key_fingerprint(restored_secret),
            "recovery": _key_fingerprint(recovery_secret),
            "proof": _key_fingerprint(proof_secret),
            "original_proof": _key_fingerprint(original_proof_secret),
            "verification_keys": _verification_set_fingerprint(verification_keys),
        }
    )
    return (
        f"ROLLBACK_META_WHATSAPP_{current_sha[:12].upper()}_{desired_sha[:12].upper()}_"
        f"{material[:8].upper()}_{transaction_id[:8].upper()}"
    )


def _validate_sha(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if not SHA256_RE.fullmatch(normalized):
        raise ValueError(f"{label} SHA-256 is required")
    return normalized


def _plan_rekey(session: Session, old_secret: str, new_secret: str, new_key_version: str) -> dict[str, Any]:
    _acquire_database_locks(session, apply=False)
    inventory = load_inventory(session)
    snapshot = _snapshot(inventory)
    fingerprint = _fingerprint_snapshot(snapshot)
    prepare_rekey(
        inventory,
        old_secret=old_secret,
        new_secret=new_secret,
        new_key_version=new_key_version,
    )
    return fingerprint


def _write_json_no_clobber(path: Path, payload: Mapping[str, Any]) -> None:
    _write_no_clobber(path, _canonical(payload) + b"\n")


def _guard_contract_confirmation(node_id: str, environment_sha: str) -> str:
    material = _digest(
        {
            "node": node_id,
            "environment": environment_sha,
            "dropin": hashlib.sha256(_guard_dropin_payload()).hexdigest(),
            "units": list(GUARDED_SYSTEMD_UNITS),
        }
    )
    return f"INSTALL_REKEY_GUARD_CONTRACT_{node_id.upper()}_{material[:16].upper()}"


def _command_guard_contract(args: argparse.Namespace) -> int:
    """Pre-provision static drop-ins while no transaction marker exists."""

    _require_root()
    _canonical_env_identity(args.env_file)
    values, _ = _load_runtime_env(args.env_file)
    node_id = str(values.get("META_DELETION_NODE_ID") or "").strip()
    if node_id != args.node_id:
        raise RuntimeError("canonical environment has the wrong HA node identity")
    _attest_host_identity(node_id)
    try:
        REKEY_GUARD_MARKER.lstat()
    except FileNotFoundError:
        pass
    else:
        raise PermissionError("static guard contract cannot change while a transaction is armed")
    environment_sha = hashlib.sha256(_read_exact(args.env_file, label="canonical environment")).hexdigest()
    token = _guard_contract_confirmation(node_id, environment_sha)
    if not args.apply and not args.verify_only:
        print(f"DRY-RUN: confirmation={token}")
        return 0
    if args.apply and args.confirm != token:
        raise PermissionError("static guard contract confirmation token is missing or incorrect")
    with _application_lock(args.lock_path):
        try:
            REKEY_GUARD_MARKER.lstat()
        except FileNotFoundError:
            pass
        else:
            raise PermissionError("static guard contract cannot change while a transaction is armed")
        if args.verify_only:
            contract_sha = _validate_static_guard_contract()
            print(f"OK: static runtime guard contract already loaded node={node_id} sha256={contract_sha}")
            return 0
        payload = _guard_dropin_payload()
        for dropin_path in _guard_dropin_paths().values():
            _install_guard_dropin(dropin_path, payload)
        _systemd_daemon_reload()
        contract_sha = _validate_static_guard_contract()
    print(f"OK: static runtime guard contract loaded node={node_id} sha256={contract_sha}")
    return 0


def _guard_confirmation(
    *,
    node_id: str,
    transaction_id: str,
    environment_sha: str,
    runtime_secret: str,
    proof_secret: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> str:
    material = _digest(
        {
            "runtime": _key_fingerprint(runtime_secret),
            "proof": _key_fingerprint(proof_secret),
            "environment": environment_sha,
            "verification_keys": _verification_set_fingerprint(verification_keys),
        }
    )
    return f"ARM_REKEY_GUARD_{node_id.upper()}_{material[:12].upper()}_{transaction_id[:8].upper()}"


def _command_offline_proof(args: argparse.Namespace) -> int:
    _require_root()
    proof_secret = _load_proof_key(args.proof_key_file)
    signing_key = _load_node_signing_key(args.node_signing_key_file)
    verification_keys = _load_node_verification_keys(args.node_verification_keys_file)
    _require_matching_node_signing_key(
        node_id=args.node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )
    with _application_lock(args.lock_path):
        _, runtime_secret = inspect_offline_contract(
            env_path=args.env_file,
            node_id=args.node_id,
            transaction_id=args.transaction_id,
        )
        if hmac.compare_digest(proof_secret, runtime_secret):
            raise ValueError("transaction proof key must be independent from the runtime key")
        environment_sha = hashlib.sha256(_read_exact(args.env_file, label="canonical environment")).hexdigest()
        token = _guard_confirmation(
            node_id=args.node_id,
            transaction_id=args.transaction_id,
            environment_sha=environment_sha,
            runtime_secret=runtime_secret,
            proof_secret=proof_secret,
            verification_keys=verification_keys,
        )
        if not args.apply:
            print(f"DRY-RUN: confirmation={token}")
            return 0
        if args.confirm != token:
            raise PermissionError("runtime guard confirmation token is missing or incorrect")
        _require_output_available_or_secure_existing(args.env_backup, label="environment backup")
        _require_output_available(args.output)
        _arm_transaction_guard(
            node_id=args.node_id,
            transaction_id=args.transaction_id,
            proof_secret=proof_secret,
        )
        proof = build_offline_proof(
            env_path=args.env_file,
            node_id=args.node_id,
            transaction_id=args.transaction_id,
            env_backup_path=args.env_backup,
            proof_secret=proof_secret,
            signing_key=signing_key,
            verification_keys=verification_keys,
        )
        _write_json_no_clobber(args.output, proof)
    print(f"OK: offline proof created node={args.node_id} expires_at={proof['expires_at']}")
    return 0


def _command_rekey(args: argparse.Namespace) -> int:
    from db.session import whatsapp_session

    _canonical_env_identity(args.env_file)
    runtime_values, old_secret = _load_runtime_env(args.env_file)
    new_secret = _load_new_runtime_key(args.new_key_file)
    recovery_secret = _load_recovery_key(args.recovery_key_file)
    proof_secret = _load_proof_key(args.proof_key_file)
    signing_key = _load_node_signing_key(args.node_signing_key_file)
    verification_keys = _load_node_verification_keys(args.node_verification_keys_file)
    _require_matching_node_signing_key(
        node_id="node01",
        signing_key=signing_key,
        verification_keys=verification_keys,
    )
    if hmac.compare_digest(old_secret, new_secret):
        raise ValueError("old and new credential encryption keys must differ")
    if hmac.compare_digest(recovery_secret, old_secret) or hmac.compare_digest(recovery_secret, new_secret):
        raise ValueError("recovery key must be independent from old and new runtime keys")
    if any(hmac.compare_digest(proof_secret, secret) for secret in (old_secret, new_secret, recovery_secret)):
        raise ValueError("transaction proof key must be independent from runtime and recovery keys")
    with _application_lock(args.lock_path):
        if not args.apply:
            with whatsapp_session(require=True) as session:
                fingerprint = _plan_rekey(session, old_secret, new_secret, args.new_key_version)
            _print_fingerprint("current", fingerprint)
            print(
                "DRY-RUN: confirmation="
                + rekey_confirmation(
                    fingerprint["full_sha256"],
                    new_secret,
                    recovery_secret,
                    proof_secret,
                    args.transaction_id,
                    args.new_key_version,
                    verification_keys,
                )
            )
            return 0
        _require_root()
        if str(runtime_values.get("META_DELETION_NODE_ID") or "").strip() != "node01":
            raise RuntimeError("database rekey must run on the fixed node01 coordinator")
        _validate_transaction_guard(
            node_id="node01",
            transaction_id=args.transaction_id,
            proof_secret=proof_secret,
        )
        expected = _validate_sha(args.expected_current_sha256, label="expected current")
        _require_output_available_or_secure_existing(args.preimage, label="cross-product preimage")
        certificate_exists = _require_output_available_or_secure_existing(
            args.database_certificate,
            label="database transition certificate",
        )
        existing_certificate: dict[str, Any] | None = None
        certified_target_sha = ""
        if certificate_exists:
            try:
                raw_certificate = json.loads(
                    _read_exact(args.database_certificate, label="database transition certificate")
                )
            except Exception as exc:  # noqa: BLE001 - normalize without artifact content.
                raise PermissionError("database transition certificate is invalid") from exc
            certified_target_sha = _validate_sha(
                str(raw_certificate.get("target_database_sha256") if isinstance(raw_certificate, dict) else ""),
                label="certified target",
            )
            existing_certificate, _ = _validate_database_certificate_envelope(
                args.database_certificate,
                proof_secret=proof_secret,
                verification_keys=verification_keys,
                target_secret=new_secret,
                transaction_id=args.transaction_id,
                target_database_sha=certified_target_sha,
                operation="rekey",
            )
            proofs, _ = validate_database_transition_certificate(
                args.database_certificate,
                proof_secret=proof_secret,
                verification_keys=verification_keys,
                source_secret=old_secret,
                target_secret=new_secret,
                transaction_id=args.transaction_id,
                source_database_sha=expected,
                target_database_sha=certified_target_sha,
                operation="rekey",
                offline_proof_paths=args.node_proof,
            )
        else:
            proofs = validate_offline_proofs(
                args.node_proof,
                proof_secret=proof_secret,
                verification_keys=verification_keys,
                runtime_secret=old_secret,
                transaction_id=args.transaction_id,
            )
        local_proof = proofs["node01"]
        local_backup_sha = hashlib.sha256(
            _read_exact(args.local_env_backup, label="node01 environment backup")
        ).hexdigest()
        if not hmac.compare_digest(local_backup_sha, str(local_proof["env_backup_sha256"])):
            raise RuntimeError("node01 environment backup does not match its signed proof")
        if args.confirm != rekey_confirmation(
            expected,
            new_secret,
            recovery_secret,
            proof_secret,
            args.transaction_id,
            args.new_key_version,
            verification_keys,
        ):
            raise PermissionError("rekey confirmation token is missing or incorrect")
        proof_digests = _proof_artifact_digests(
            args.node_proof,
            proofs,
            label="HA offline proof",
        )

        def persist_certificate(source_fp: Mapping[str, Any], target_fp: Mapping[str, Any]) -> None:
            artifact_digests = {
                "credential_preimage": hashlib.sha256(
                    _read_exact(args.preimage, label="cross-product preimage")
                ).hexdigest(),
                "whatsapp_key_version_contract": hashlib.sha256(
                    b"linas-whatsapp-key-version-v1\x00" + args.new_key_version.encode("utf-8")
                ).hexdigest(),
            }
            if existing_certificate is not None:
                if (
                    existing_certificate.get("source_database_sha256") != source_fp["full_sha256"]
                    or existing_certificate.get("target_database_sha256") != target_fp["full_sha256"]
                    or existing_certificate.get("structural_sha256") != target_fp["structural_sha256"]
                    or existing_certificate.get("artifacts_sha256") != artifact_digests
                ):
                    raise RuntimeError("prepared database certificate does not match source/target reconciliation")
                return
            certificate = _build_database_transition_certificate(
                operation="rekey",
                transaction_id=args.transaction_id,
                source_secret=old_secret,
                target_secret=new_secret,
                source_fingerprint=source_fp,
                target_fingerprint=target_fp,
                proof_secret=proof_secret,
                signing_key=signing_key,
                verification_keys=verification_keys,
                offline_proofs=proofs,
                offline_proof_digests=proof_digests,
                artifact_digests=artifact_digests,
            )
            # This callback runs after durable preimage verification and before
            # the first SQL update, so every possible committed target has a
            # retry authority and a SIGKILL cannot orphan a prepared file.
            _write_json_no_clobber(args.database_certificate, certificate)

        with whatsapp_session(require=True) as session:
            before_fp, after_fp = apply_rekey_transaction(
                session,
                old_secret=old_secret,
                new_secret=new_secret,
                new_key_version=args.new_key_version,
                expected_current_sha256=expected,
                preimage_path=args.preimage,
                recovery_secret=recovery_secret,
                transaction_id=args.transaction_id,
                certified_target_sha256=certified_target_sha,
                before_updates=persist_certificate,
            )
        _print_fingerprint("preimage-verified", before_fp)
        _print_fingerprint("database-rekeyed", after_fp)
    print("STOP: database uses the new key; keep both nodes offline until both env proofs verify")
    return 0


def _command_rollback(args: argparse.Namespace) -> int:
    from db.session import whatsapp_session

    _canonical_env_identity(args.env_file)
    runtime_values, current_secret = _load_runtime_env(args.env_file)
    restored_secret = _load_key(args.restored_key_file)
    recovery_secret = _load_recovery_key(args.recovery_key_file)
    proof_secret = _load_proof_key(args.proof_key_file)
    original_proof_secret = _load_proof_key(args.original_proof_key_file)
    signing_key = _load_node_signing_key(args.node_signing_key_file)
    verification_keys = _load_node_verification_keys(args.node_verification_keys_file)
    _require_matching_node_signing_key(
        node_id="node01",
        signing_key=signing_key,
        verification_keys=verification_keys,
    )
    if hmac.compare_digest(recovery_secret, current_secret) or hmac.compare_digest(recovery_secret, restored_secret):
        raise ValueError("recovery key must be independent from runtime keys")
    if any(hmac.compare_digest(proof_secret, secret) for secret in (current_secret, restored_secret, recovery_secret)):
        raise ValueError("transaction proof key must be independent from runtime and recovery keys")
    _require_fresh_rollback_proof_key(proof_secret, original_proof_secret)
    validate_env_backup_attestation(
        args.original_node_proof,
        proof_secret=original_proof_secret,
        verification_keys=verification_keys,
        runtime_secret=restored_secret,
        transaction_id=args.original_transaction_id,
        node_id="node01",
        env_backup_path=args.restored_key_file,
    )
    preimage = read_preimage(args.preimage, recovery_secret=recovery_secret)
    desired_fp = _fingerprint_snapshot(preimage)
    with _application_lock(args.lock_path):
        expected = _validate_sha(args.expected_current_sha256, label="expected current") if args.apply else ""
        certificate_exists = False
        existing_certificate: dict[str, Any] | None = None
        certified_target_sha = ""
        if args.apply:
            _require_output_available_or_secure_existing(args.pre_rollback, label="pre-rollback backup")
            certificate_exists = _require_output_available_or_secure_existing(
                args.database_certificate,
                label="database transition certificate",
            )
            if certificate_exists:
                try:
                    raw_certificate = json.loads(
                        _read_exact(args.database_certificate, label="database transition certificate")
                    )
                except Exception as exc:  # noqa: BLE001 - normalize without artifact content.
                    raise PermissionError("database transition certificate is invalid") from exc
                certified_target_sha = _validate_sha(
                    str(raw_certificate.get("target_database_sha256") if isinstance(raw_certificate, dict) else ""),
                    label="certified target",
                )
                existing_certificate, _ = _validate_database_certificate_envelope(
                    args.database_certificate,
                    proof_secret=proof_secret,
                    verification_keys=verification_keys,
                    target_secret=restored_secret,
                    transaction_id=args.transaction_id,
                    target_database_sha=certified_target_sha,
                    operation="rollback",
                )
                if certified_target_sha != desired_fp["full_sha256"]:
                    raise RuntimeError("rollback certificate target differs from the authenticated preimage")
        with whatsapp_session(require=True) as session:
            _acquire_database_locks(session, apply=False)
            current_inventory = load_inventory(session)
            current_fp = _fingerprint_snapshot(_snapshot(current_inventory))
            if args.apply and certificate_exists and current_fp["full_sha256"] == certified_target_sha:
                _validate_inventory_decryption(current_inventory, restored_secret)
            elif not args.apply:
                if current_fp["structural_sha256"] != desired_fp["structural_sha256"]:
                    raise RuntimeError("preimage ownership inventory no longer matches current PostgreSQL")
                current_semantic = _decryption_semantic_digest(
                    current_inventory,
                    secret=current_secret,
                    digest_secret=recovery_secret,
                )
                desired_semantic = _preimage_decryption_semantic_digest(
                    preimage,
                    secret=restored_secret,
                    digest_secret=recovery_secret,
                )
                if not hmac.compare_digest(current_semantic, desired_semantic):
                    raise RuntimeError("rollback would overwrite changed credential plaintext")
            else:
                _validate_inventory_decryption(current_inventory, current_secret)
        _print_fingerprint("current", current_fp)
        _print_fingerprint("rollback-target", desired_fp)
        token = rollback_confirmation(
            expected or current_fp["full_sha256"],
            desired_fp["full_sha256"],
            restored_secret,
            recovery_secret,
            proof_secret,
            original_proof_secret,
            args.transaction_id,
            verification_keys,
        )
        if not args.apply:
            print(f"DRY-RUN: confirmation={token}")
            return 0
        _require_root()
        if str(runtime_values.get("META_DELETION_NODE_ID") or "").strip() != "node01":
            raise RuntimeError("database rollback must run on the fixed node01 coordinator")
        _validate_transaction_guard(
            node_id="node01",
            transaction_id=args.transaction_id,
            proof_secret=proof_secret,
        )
        if current_fp["full_sha256"] not in {expected, certified_target_sha}:
            raise RuntimeError("credential inventory is neither rollback source nor certified target")
        if certificate_exists:
            proofs, _ = validate_database_transition_certificate(
                args.database_certificate,
                proof_secret=proof_secret,
                verification_keys=verification_keys,
                source_secret=current_secret,
                target_secret=restored_secret,
                transaction_id=args.transaction_id,
                source_database_sha=expected,
                target_database_sha=certified_target_sha,
                operation="rollback",
                offline_proof_paths=args.node_proof,
            )
        else:
            proofs = validate_offline_proofs(
                args.node_proof,
                proof_secret=proof_secret,
                verification_keys=verification_keys,
                runtime_secret=current_secret,
                transaction_id=args.transaction_id,
            )
        if args.confirm != token:
            raise PermissionError("rollback confirmation token is missing or incorrect")
        proof_digests = _proof_artifact_digests(args.node_proof, proofs, label="HA offline proof")

        def persist_certificate(source_fp: Mapping[str, Any], target_fp: Mapping[str, Any]) -> None:
            artifact_digests = {
                "restore_preimage": hashlib.sha256(
                    _read_exact(args.preimage, label="cross-product preimage")
                ).hexdigest(),
                "pre_rollback_backup": hashlib.sha256(
                    _read_exact(args.pre_rollback, label="pre-rollback backup")
                ).hexdigest(),
                "original_env_backup": hashlib.sha256(
                    _read_exact(args.restored_key_file, label="original environment backup")
                ).hexdigest(),
                "original_env_proof": hashlib.sha256(
                    _read_exact(args.original_node_proof, label="original HA offline proof")
                ).hexdigest(),
            }
            if existing_certificate is not None:
                if (
                    existing_certificate.get("source_database_sha256") != source_fp["full_sha256"]
                    or existing_certificate.get("target_database_sha256") != target_fp["full_sha256"]
                    or existing_certificate.get("structural_sha256") != target_fp["structural_sha256"]
                    or existing_certificate.get("artifacts_sha256") != artifact_digests
                ):
                    raise RuntimeError("prepared rollback certificate failed source/target reconciliation")
                return
            certificate = _build_database_transition_certificate(
                operation="rollback",
                transaction_id=args.transaction_id,
                source_secret=current_secret,
                target_secret=restored_secret,
                source_fingerprint=source_fp,
                target_fingerprint=target_fp,
                proof_secret=proof_secret,
                signing_key=signing_key,
                verification_keys=verification_keys,
                offline_proofs=proofs,
                offline_proof_digests=proof_digests,
                artifact_digests=artifact_digests,
            )
            _write_json_no_clobber(args.database_certificate, certificate)

        with whatsapp_session(require=True) as session:
            before_fp, after_fp = restore_preimage_transaction(
                session,
                current_secret=current_secret,
                restored_secret=restored_secret,
                expected_current_sha256=expected,
                preimage=preimage,
                pre_rollback_path=args.pre_rollback,
                recovery_secret=recovery_secret,
                certified_target_sha256=certified_target_sha,
                before_updates=persist_certificate,
            )
        _print_fingerprint("pre-rollback-backup-verified", before_fp)
        _print_fingerprint("database-restored", after_fp)
    print("STOP: database uses the restored key; restore both node env backups before restart")
    return 0


def _stage_confirmation(
    node_id: str,
    database_sha: str,
    runtime_secret: str,
    proof_secret: str,
    transaction_id: str,
    backup_sha: str,
    database_certificate_sha: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> str:
    material = _digest(
        {
            "runtime": _key_fingerprint(runtime_secret),
            "proof": _key_fingerprint(proof_secret),
            "backup": backup_sha,
            "database_certificate": database_certificate_sha,
            "verification_keys": _verification_set_fingerprint(verification_keys),
        }
    )
    return (
        f"STAGE_REKEY_ENV_{node_id.upper()}_{database_sha[:16].upper()}_"
        f"{material[:8].upper()}_{transaction_id[:8].upper()}"
    )


def _make_env_proof(
    *,
    node_id: str,
    transaction_id: str,
    database_sha: str,
    env_path: Path,
    runtime_secret: str,
    proof_secret: str,
    database_certificate_sha: str,
    signing_key: Ed25519PrivateKey,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> dict[str, Any]:
    now = int(time.time())
    guard_sha = _validate_transaction_guard(
        node_id=node_id,
        transaction_id=transaction_id,
        proof_secret=proof_secret,
    )
    values = _parse_env(env_path)
    cluster_meta_values = {
        key: value for key, value in values.items() if key.startswith("META_") and key != "META_DELETION_NODE_ID"
    }
    cluster_meta_values["LINAS_EFFECTIVE_POSTGRES_DSN"] = _effective_database_dsn(values)
    cluster_meta_values["LINAS_MAINTENANCE_DRAIN_FILE"] = str(values.get("LINAS_MAINTENANCE_DRAIN_FILE") or "")
    cluster_fingerprint = hmac.new(
        _proof_key(proof_secret, environment=True),
        _canonical(cluster_meta_values),
        hashlib.sha256,
    ).hexdigest()
    proof = _sign_proof(
        {
            "format": ENV_PROOF_FORMAT,
            "transaction_id": transaction_id,
            "node_id": node_id,
            "created_at": now,
            "expires_at": now + PROOF_MAX_AGE_SECONDS,
            "database_sha256": database_sha,
            "database_transition_certificate_sha256": database_certificate_sha,
            "key_fingerprint": _key_fingerprint(runtime_secret),
            "environment_sha256": hashlib.sha256(_read_exact(env_path, label="canonical environment")).hexdigest(),
            "cluster_meta_fingerprint": cluster_fingerprint,
            "persistent_maintenance": True,
            "all_runtime_units_offline": True,
            "runtime_guard_path": str(REKEY_GUARD_MARKER),
            "runtime_guard_transaction_id": transaction_id,
            "runtime_guarded_units": list(GUARDED_SYSTEMD_UNITS),
            "runtime_guard_sha256": guard_sha,
            "host_identity": _attest_host_identity(node_id),
            "verification_set_fingerprint": _verification_set_fingerprint(verification_keys),
            "node_verification_key_fingerprint": _verification_key_fingerprint(verification_keys[node_id]),
        },
        proof_secret,
        environment=True,
    )
    return _attach_node_signature(
        proof,
        node_id=node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )


def _command_stage_env(args: argparse.Namespace) -> int:
    from db.session import whatsapp_session
    from scripts.ha.meta_env_file import atomic_update_env

    _canonical_env_identity(args.env_file)
    backup_values, old_secret = _load_runtime_env(args.env_backup)
    new_secret = _load_new_runtime_key(args.new_key_file)
    proof_secret = _load_proof_key(args.proof_key_file)
    signing_key = _load_node_signing_key(args.node_signing_key_file)
    verification_keys = _load_node_verification_keys(args.node_verification_keys_file)
    _require_matching_node_signing_key(
        node_id=args.node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )
    if hmac.compare_digest(proof_secret, old_secret) or hmac.compare_digest(proof_secret, new_secret):
        raise ValueError("transaction proof key must be independent from runtime keys")
    expected = _validate_sha(args.expected_database_sha256, label="expected database")
    proof_map, database_certificate_sha = validate_database_transition_certificate(
        args.database_certificate,
        proof_secret=proof_secret,
        verification_keys=verification_keys,
        source_secret=old_secret,
        target_secret=new_secret,
        transaction_id=args.transaction_id,
        target_database_sha=expected,
        operation="rekey",
        offline_proof_paths=[args.node_proof, args.peer_node_proof],
    )
    node_proof = proof_map[args.node_id]
    if str(backup_values.get("META_DELETION_NODE_ID") or "").strip() != args.node_id:
        raise RuntimeError("environment backup belongs to another HA node")
    backup_sha = hashlib.sha256(_read_exact(args.env_backup, label="environment backup")).hexdigest()
    if backup_sha != node_proof["env_backup_sha256"]:
        raise RuntimeError("environment backup does not match the signed offline proof")
    with _application_lock(args.lock_path):
        current_values = _parse_env(args.env_file)
        before_without_key = {
            key: value for key, value in current_values.items() if key != "META_CREDENTIAL_ENCRYPTION_KEY"
        }
        backup_without_key = {
            key: value for key, value in backup_values.items() if key != "META_CREDENTIAL_ENCRYPTION_KEY"
        }
        if before_without_key != backup_without_key:
            raise RuntimeError("canonical environment changed after its signed backup")
        _validate_maintenance_marker()
        _validate_transaction_guard(
            node_id=args.node_id,
            transaction_id=args.transaction_id,
            proof_secret=proof_secret,
        )
        if any(not _unit_is_offline(unit) for unit in ALL_RUNTIME_UNITS) or not _application_ports_closed():
            raise RuntimeError("local API and all workers must remain offline during environment staging")
        # Use the backup DSN while the canonical key may already be staged on retry.
        _load_runtime_env(args.env_backup)
        with whatsapp_session(require=True) as session:
            _acquire_database_locks(session, apply=False)
            inventory = load_inventory(session)
            fingerprint = _fingerprint_snapshot(_snapshot(inventory))
            if fingerprint["full_sha256"] != expected:
                raise RuntimeError("database changed before environment staging")
            _validate_inventory_decryption(inventory, new_secret)
        token = _stage_confirmation(
            args.node_id,
            expected,
            new_secret,
            proof_secret,
            args.transaction_id,
            backup_sha,
            database_certificate_sha,
            verification_keys,
        )
        if not args.apply:
            print(f"DRY-RUN: confirmation={token}")
            return 0
        _require_root()
        if args.confirm != token:
            raise PermissionError("environment staging confirmation token is missing or incorrect")
        _require_output_available(args.output)
        marker = str(current_values.get("LINAS_MAINTENANCE_DRAIN_FILE") or "")
        if marker != str(PERSISTENT_MAINTENANCE):
            raise RuntimeError("canonical environment lost the persistent maintenance contract")
        current_key = str(current_values.get("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
        if not (hmac.compare_digest(current_key, old_secret) or hmac.compare_digest(current_key, new_secret)):
            raise RuntimeError("canonical environment key is neither expected preimage nor desired key")
        if not hmac.compare_digest(current_key, new_secret):
            atomic_update_env(args.env_file, {"META_CREDENTIAL_ENCRYPTION_KEY": new_secret})
        staged_values = _parse_env(args.env_file)
        expected_staged_values = {**backup_values, "META_CREDENTIAL_ENCRYPTION_KEY": new_secret}
        if staged_values != expected_staged_values:
            raise RuntimeError("canonical environment key staging verification failed")
        proof = _make_env_proof(
            node_id=args.node_id,
            transaction_id=args.transaction_id,
            database_sha=expected,
            env_path=args.env_file,
            runtime_secret=new_secret,
            proof_secret=proof_secret,
            database_certificate_sha=database_certificate_sha,
            signing_key=signing_key,
            verification_keys=verification_keys,
        )
        _write_json_no_clobber(args.output, proof)
    print(f"OK: new key staged while offline node={args.node_id}; restart remains blocked")
    return 0


def _restore_env_confirmation(
    node_id: str,
    database_sha: str,
    runtime_secret: str,
    proof_secret: str,
    transaction_id: str,
    desired_backup_sha: str,
    current_backup_sha: str,
    original_proof_secret: str,
    original_transaction_id: str,
    database_certificate_sha: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> str:
    material = _digest(
        {
            "runtime": _key_fingerprint(runtime_secret),
            "proof": _key_fingerprint(proof_secret),
            "original_proof": _key_fingerprint(original_proof_secret),
            "desired_backup": desired_backup_sha,
            "current_backup": current_backup_sha,
            "original_transaction": original_transaction_id,
            "database_certificate": database_certificate_sha,
            "verification_keys": _verification_set_fingerprint(verification_keys),
        }
    )
    return (
        f"RESTORE_REKEY_ENV_{node_id.upper()}_{database_sha[:16].upper()}_"
        f"{material[:8].upper()}_{transaction_id[:8].upper()}"
    )


def _atomic_restore_env(source: Path, target: Path) -> None:
    payload = _read_exact(source, label="original environment backup")
    target_info = _secure_regular_file(target, label="canonical environment")
    fd, temporary_name = tempfile.mkstemp(prefix=".env.rekey-restore.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, target_info.st_uid, target_info.st_gid)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _secure_regular_file(target, label="restored canonical environment")
        directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    if not hmac.compare_digest(payload, _read_exact(target, label="restored canonical environment")):
        raise RuntimeError("restored canonical environment verification failed")


def _command_restore_env(args: argparse.Namespace) -> int:
    from db.session import whatsapp_session

    _canonical_env_identity(args.env_file)
    current_values, active_secret = _load_runtime_env(args.env_file)
    source_values, source_secret = _load_runtime_env(args.current_env_backup)
    desired_values, restored_secret = _load_runtime_env(args.desired_env_backup)
    proof_secret = _load_proof_key(args.proof_key_file)
    original_proof_secret = _load_proof_key(args.original_proof_key_file)
    signing_key = _load_node_signing_key(args.node_signing_key_file)
    verification_keys = _load_node_verification_keys(args.node_verification_keys_file)
    _require_matching_node_signing_key(
        node_id=args.node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )
    if hmac.compare_digest(proof_secret, source_secret) or hmac.compare_digest(proof_secret, restored_secret):
        raise ValueError("rollback proof key must be independent from runtime keys")
    _require_fresh_rollback_proof_key(proof_secret, original_proof_secret)
    if hmac.compare_digest(original_proof_secret, source_secret) or hmac.compare_digest(
        original_proof_secret, restored_secret
    ):
        raise ValueError("original proof key must be independent from runtime keys")
    if str(desired_values.get("META_DELETION_NODE_ID") or "").strip() != args.node_id:
        raise RuntimeError("original environment backup belongs to another HA node")
    if str(source_values.get("META_DELETION_NODE_ID") or "").strip() != args.node_id:
        raise RuntimeError("current environment backup belongs to another HA node")
    if not (
        _effective_database_dsn(current_values)
        == _effective_database_dsn(source_values)
        == _effective_database_dsn(desired_values)
    ):
        raise RuntimeError("environment restore cannot change PostgreSQL authority")
    if not (hmac.compare_digest(active_secret, source_secret) or hmac.compare_digest(active_secret, restored_secret)):
        raise RuntimeError("canonical environment key is neither rollback source nor target")
    desired_backup_sha = hashlib.sha256(
        _read_exact(args.desired_env_backup, label="original environment backup")
    ).hexdigest()
    validate_env_backup_attestation(
        args.original_node_proof,
        proof_secret=original_proof_secret,
        verification_keys=verification_keys,
        runtime_secret=restored_secret,
        transaction_id=args.original_transaction_id,
        node_id=args.node_id,
        env_backup_path=args.desired_env_backup,
    )
    expected = _validate_sha(args.expected_database_sha256, label="expected database")
    proof_map, database_certificate_sha = validate_database_transition_certificate(
        args.database_certificate,
        proof_secret=proof_secret,
        verification_keys=verification_keys,
        source_secret=source_secret,
        target_secret=restored_secret,
        transaction_id=args.transaction_id,
        target_database_sha=expected,
        operation="rollback",
        offline_proof_paths=[args.node_proof, args.peer_node_proof],
    )
    current_backup_sha = hashlib.sha256(
        _read_exact(args.current_env_backup, label="current environment backup")
    ).hexdigest()
    if not hmac.compare_digest(current_backup_sha, str(proof_map[args.node_id]["env_backup_sha256"])):
        raise RuntimeError("current environment backup does not match its signed proof")
    with _application_lock(args.lock_path):
        _validate_maintenance_marker()
        _validate_transaction_guard(
            node_id=args.node_id,
            transaction_id=args.transaction_id,
            proof_secret=proof_secret,
        )
        if any(not _unit_is_offline(unit) for unit in ALL_RUNTIME_UNITS) or not _application_ports_closed():
            raise RuntimeError("local API and all workers must remain offline during environment restore")
        # Connect through the current canonical authority; the desired backup is
        # allowed to change the key, never the PostgreSQL target.
        _load_runtime_env(args.env_file)
        with whatsapp_session(require=True) as session:
            _acquire_database_locks(session, apply=False)
            inventory = load_inventory(session)
            fingerprint = _fingerprint_snapshot(_snapshot(inventory))
            if fingerprint["full_sha256"] != expected:
                raise RuntimeError("database changed before environment restore")
            _validate_inventory_decryption(inventory, restored_secret)
        token = _restore_env_confirmation(
            args.node_id,
            expected,
            restored_secret,
            proof_secret,
            args.transaction_id,
            desired_backup_sha,
            current_backup_sha,
            original_proof_secret,
            args.original_transaction_id,
            database_certificate_sha,
            verification_keys,
        )
        if not args.apply:
            print(f"DRY-RUN: confirmation={token}")
            return 0
        _require_root()
        if args.confirm != token:
            raise PermissionError("environment restore confirmation token is missing or incorrect")
        _require_output_available(args.output)
        if current_values != desired_values:
            _atomic_restore_env(args.desired_env_backup, args.env_file)
        restored_values = _parse_env(args.env_file)
        if restored_values != desired_values:
            raise RuntimeError("exact environment restore verification failed")
        proof = _make_env_proof(
            node_id=args.node_id,
            transaction_id=args.transaction_id,
            database_sha=expected,
            env_path=args.env_file,
            runtime_secret=restored_secret,
            proof_secret=proof_secret,
            database_certificate_sha=database_certificate_sha,
            signing_key=signing_key,
            verification_keys=verification_keys,
        )
        _write_json_no_clobber(args.output, proof)
    print(f"OK: original key environment restored while offline node={args.node_id}; restart remains blocked")
    return 0


def validate_env_proofs(
    paths: Sequence[Path],
    *,
    proof_secret: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
    runtime_secret: str,
    transaction_id: str,
    database_sha: str,
    database_certificate_sha: str,
    now: int | None = None,
    require_fresh: bool = True,
) -> dict[str, dict[str, Any]]:
    if len(paths) != 2:
        raise PermissionError("exactly two environment proofs are required")
    current_time = int(now if now is not None else time.time())
    found: dict[str, dict[str, Any]] = {}
    cluster_fingerprint = ""
    for path in paths:
        proof = json.loads(_read_exact(path, label="HA environment proof"))
        if not isinstance(proof, dict):
            raise PermissionError("HA environment proof is invalid")
        _verify_proof_signature(proof, proof_secret, environment=True)
        _verify_node_signature(proof, verification_keys)
        node = str(proof.get("node_id") or "")
        if node not in REQUIRED_NODES or node in found:
            raise PermissionError("HA environment proof contract is invalid")
        host_identity = _validate_attested_identity(proof.get("host_identity"), node_id=node)
        if (
            proof.get("format") != ENV_PROOF_FORMAT
            or proof.get("transaction_id") != transaction_id
            or proof.get("database_sha256") != database_sha
            or proof.get("database_transition_certificate_sha256") != database_certificate_sha
            or proof.get("key_fingerprint") != _key_fingerprint(runtime_secret)
            or proof.get("persistent_maintenance") is not True
            or proof.get("all_runtime_units_offline") is not True
            or proof.get("runtime_guard_path") != str(REKEY_GUARD_MARKER)
            or proof.get("runtime_guard_transaction_id") != transaction_id
            or proof.get("runtime_guarded_units") != list(GUARDED_SYSTEMD_UNITS)
            or proof.get("runtime_guard_sha256")
            != hashlib.sha256(
                _guard_payload(
                    node_id=node,
                    transaction_id=transaction_id,
                    proof_secret=proof_secret,
                    host_identity=host_identity,
                )
            ).hexdigest()
            or proof.get("host_identity") != host_identity
            or proof.get("verification_set_fingerprint") != _verification_set_fingerprint(verification_keys)
            or proof.get("node_verification_key_fingerprint") != _verification_key_fingerprint(verification_keys[node])
            or not SHA256_RE.fullmatch(str(proof.get("environment_sha256") or ""))
            or not SHA256_RE.fullmatch(str(proof.get("cluster_meta_fingerprint") or ""))
        ):
            raise PermissionError("HA environment proof contract is invalid")
        created_at = int(proof.get("created_at") or 0)
        expires_at = int(proof.get("expires_at") or 0)
        invalid_time_contract = expires_at - created_at != PROOF_MAX_AGE_SECONDS or created_at <= 0
        if require_fresh:
            invalid_time_contract = invalid_time_contract or created_at > current_time + 5 or expires_at < current_time
        if invalid_time_contract:
            raise PermissionError("HA environment proof is stale")
        current_cluster_fingerprint = str(proof["cluster_meta_fingerprint"])
        if cluster_fingerprint and not hmac.compare_digest(cluster_fingerprint, current_cluster_fingerprint):
            raise PermissionError("HA node Meta environments are not identical")
        cluster_fingerprint = current_cluster_fingerprint
        found[node] = dict(proof)
    if tuple(sorted(found)) != REQUIRED_NODES:
        raise PermissionError("environment proofs do not cover both fixed HA nodes")
    machine_ids = {str(proof["host_identity"]["machine_id_sha256"]) for proof in found.values()}
    if len(machine_ids) != len(REQUIRED_NODES):
        raise PermissionError("environment proofs came from the same physical host")
    return found


def _validate_local_environment_proof(
    proof: Mapping[str, Any],
    *,
    node_id: str,
    env_path: Path,
) -> None:
    if proof.get("node_id") != node_id:
        raise PermissionError("local environment proof has the wrong node identity")
    current_sha = hashlib.sha256(_read_exact(env_path, label="canonical environment")).hexdigest()
    if not hmac.compare_digest(current_sha, str(proof.get("environment_sha256") or "")):
        raise PermissionError("canonical environment changed after its signed proof")
    if proof.get("host_identity") != _attest_host_identity(node_id):
        raise PermissionError("local environment proof came from another physical host")


def _command_verify_env(args: argparse.Namespace) -> int:
    from db.session import whatsapp_session

    _canonical_env_identity(args.env_file)
    runtime_values, runtime_secret = _load_runtime_env(args.env_file)
    proof_secret = _load_proof_key(args.proof_key_file)
    verification_keys = _load_node_verification_keys(args.node_verification_keys_file)
    if hmac.compare_digest(proof_secret, runtime_secret):
        raise ValueError("transaction proof key must be independent from the runtime key")
    expected = _validate_sha(args.expected_database_sha256, label="expected database")
    _, database_certificate_sha = _validate_database_certificate_envelope(
        args.database_certificate,
        proof_secret=proof_secret,
        verification_keys=verification_keys,
        target_secret=runtime_secret,
        transaction_id=args.transaction_id,
        target_database_sha=expected,
    )
    node_id = str(runtime_values.get("META_DELETION_NODE_ID") or "").strip()
    if node_id not in REQUIRED_NODES:
        raise RuntimeError("canonical environment has no fixed HA node identity")
    with _application_lock(args.lock_path):
        _validate_maintenance_marker()
        _validate_transaction_guard(
            node_id=node_id,
            transaction_id=args.transaction_id,
            proof_secret=proof_secret,
        )
        if any(not _unit_is_offline(unit) for unit in ALL_RUNTIME_UNITS) or not _application_ports_closed():
            raise RuntimeError("local API and all workers must remain offline during environment verification")
        proof_map = validate_env_proofs(
            args.env_proof,
            proof_secret=proof_secret,
            verification_keys=verification_keys,
            runtime_secret=runtime_secret,
            transaction_id=args.transaction_id,
            database_sha=expected,
            database_certificate_sha=database_certificate_sha,
            require_fresh=False,
        )
        _validate_local_environment_proof(proof_map[node_id], node_id=node_id, env_path=args.env_file)
        with whatsapp_session(require=True) as session:
            _acquire_database_locks(session, apply=False)
            inventory = load_inventory(session)
            fingerprint = _fingerprint_snapshot(_snapshot(inventory))
            if fingerprint["full_sha256"] != expected:
                raise RuntimeError("database changed after environment proof")
            _validate_inventory_decryption(inventory, runtime_secret)
    _print_fingerprint("database-and-env-verified", fingerprint)
    print("OK: both offline node environments match the database key; controlled restart is eligible")
    return 0


def _release_guard_confirmation(
    *,
    node_id: str,
    transaction_id: str,
    database_sha: str,
    runtime_secret: str,
    proof_secret: str,
    guard_sha: str,
    env_proofs_sha: str,
    database_certificate_sha: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> str:
    material = _digest(
        {
            "database": database_sha,
            "runtime": _key_fingerprint(runtime_secret),
            "proof": _key_fingerprint(proof_secret),
            "guard": guard_sha,
            "env_proofs": env_proofs_sha,
            "database_certificate": database_certificate_sha,
            "verification_keys": _verification_set_fingerprint(verification_keys),
        }
    )
    return f"RELEASE_REKEY_GUARD_{node_id.upper()}_{material[:12].upper()}_{transaction_id[:8].upper()}"


def _release_receipt_path(node_id: str, transaction_id: str) -> Path:
    if node_id not in REQUIRED_NODES or not TX_RE.fullmatch(transaction_id):
        raise ValueError("runtime guard release receipt identity is invalid")
    return REKEY_GUARD_MARKER.parent / f"runtime.guard.release.{transaction_id}.{node_id}.json"


def _build_release_receipt(
    *,
    node_id: str,
    transaction_id: str,
    database_sha: str,
    runtime_secret: str,
    proof_secret: str,
    guard_sha: str,
    env_proofs_sha: str,
    database_certificate_sha: str,
    confirmation: str,
    signing_key: Ed25519PrivateKey,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> dict[str, Any]:
    body = {
        "format": RELEASE_RECEIPT_FORMAT,
        "node_id": node_id,
        "transaction_id": transaction_id,
        "created_at": int(time.time()),
        "database_sha256": database_sha,
        "runtime_key_fingerprint": _key_fingerprint(runtime_secret),
        "proof_key_fingerprint": _key_fingerprint(proof_secret),
        "guard_sha256": guard_sha,
        "env_proofs_sha256": env_proofs_sha,
        "database_certificate_sha256": database_certificate_sha,
        "confirmation_sha256": hashlib.sha256(confirmation.encode("utf-8")).hexdigest(),
        "verification_set_fingerprint": _verification_set_fingerprint(verification_keys),
        "host_identity": _attest_host_identity(node_id),
    }
    return _attach_node_signature(
        _sign_proof(body, proof_secret, environment=True),
        node_id=node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )


def _validate_release_receipt(
    path: Path,
    *,
    expected: Mapping[str, Any],
    proof_secret: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> dict[str, Any]:
    try:
        receipt = json.loads(_read_exact(path, label="runtime guard release receipt"))
    except Exception as exc:  # noqa: BLE001 - normalize without receipt content.
        raise PermissionError("runtime guard release receipt is invalid") from exc
    if not isinstance(receipt, dict):
        raise PermissionError("runtime guard release receipt is invalid")
    _verify_proof_signature(receipt, proof_secret, environment=True)
    _verify_node_signature(receipt, verification_keys)
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise PermissionError("runtime guard release receipt contract is invalid")
    if (
        receipt.get("format") != RELEASE_RECEIPT_FORMAT
        or int(receipt.get("created_at") or 0) <= 0
        or receipt.get("verification_set_fingerprint") != _verification_set_fingerprint(verification_keys)
        or receipt.get("host_identity") != _attest_host_identity(str(receipt.get("node_id") or ""))
    ):
        raise PermissionError("runtime guard release receipt contract is invalid")
    return receipt


def _command_release_guard(args: argparse.Namespace) -> int:
    """Unarm one node only after cross-node env and database parity is proven."""

    from db.session import whatsapp_session

    _canonical_env_identity(args.env_file)
    runtime_values, runtime_secret = _load_runtime_env(args.env_file)
    proof_secret = _load_proof_key(args.proof_key_file)
    signing_key = _load_node_signing_key(args.node_signing_key_file)
    verification_keys = _load_node_verification_keys(args.node_verification_keys_file)
    if hmac.compare_digest(proof_secret, runtime_secret):
        raise ValueError("transaction proof key must be independent from the runtime key")
    node_id = str(runtime_values.get("META_DELETION_NODE_ID") or "").strip()
    if node_id != args.node_id:
        raise RuntimeError("canonical environment has the wrong HA node identity")
    _require_matching_node_signing_key(
        node_id=node_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
    )
    expected = _validate_sha(args.expected_database_sha256, label="expected database")
    _, database_certificate_sha = _validate_database_certificate_envelope(
        args.database_certificate,
        proof_secret=proof_secret,
        verification_keys=verification_keys,
        target_secret=runtime_secret,
        transaction_id=args.transaction_id,
        target_database_sha=expected,
    )
    receipt_path = _release_receipt_path(node_id, args.transaction_id)
    with _application_lock(args.lock_path):
        _validate_maintenance_marker()
        try:
            REKEY_GUARD_MARKER.lstat()
        except FileNotFoundError:
            marker_active = False
            _validate_static_guard_contract()
            try:
                receipt_preview = json.loads(_read_exact(receipt_path, label="runtime guard release receipt"))
            except Exception as exc:  # noqa: BLE001 - normalize without receipt content.
                raise PermissionError("released guard has no durable authorization receipt") from exc
            guard_sha = _validate_sha(
                str(receipt_preview.get("guard_sha256") if isinstance(receipt_preview, dict) else ""),
                label="released guard",
            )
        else:
            marker_active = True
            guard_sha = _validate_transaction_guard(
                node_id=node_id,
                transaction_id=args.transaction_id,
                proof_secret=proof_secret,
            )
            if any(not _unit_is_offline(unit) for unit in ALL_RUNTIME_UNITS) or not _application_ports_closed():
                raise RuntimeError("local API and all workers must be offline before runtime guard release")
        proof_map = validate_env_proofs(
            args.env_proof,
            proof_secret=proof_secret,
            verification_keys=verification_keys,
            runtime_secret=runtime_secret,
            transaction_id=args.transaction_id,
            database_sha=expected,
            database_certificate_sha=database_certificate_sha,
            require_fresh=False,
        )
        _validate_local_environment_proof(proof_map[node_id], node_id=node_id, env_path=args.env_file)
        proof_digests = sorted(
            hashlib.sha256(_read_exact(path, label="HA environment proof")).hexdigest() for path in args.env_proof
        )
        env_proofs_sha = _digest(proof_digests)
        with whatsapp_session(require=True) as session:
            _acquire_database_locks(session, apply=False)
            inventory = load_inventory(session)
            fingerprint = _fingerprint_snapshot(_snapshot(inventory))
            if fingerprint["full_sha256"] != expected:
                raise RuntimeError("database changed before runtime guard release")
            _validate_inventory_decryption(inventory, runtime_secret)
        token = _release_guard_confirmation(
            node_id=node_id,
            transaction_id=args.transaction_id,
            database_sha=expected,
            runtime_secret=runtime_secret,
            proof_secret=proof_secret,
            guard_sha=guard_sha,
            env_proofs_sha=env_proofs_sha,
            database_certificate_sha=database_certificate_sha,
            verification_keys=verification_keys,
        )
        receipt_expected = {
            "format": RELEASE_RECEIPT_FORMAT,
            "node_id": node_id,
            "transaction_id": args.transaction_id,
            "database_sha256": expected,
            "runtime_key_fingerprint": _key_fingerprint(runtime_secret),
            "proof_key_fingerprint": _key_fingerprint(proof_secret),
            "guard_sha256": guard_sha,
            "env_proofs_sha256": env_proofs_sha,
            "database_certificate_sha256": database_certificate_sha,
            "confirmation_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        }
        try:
            receipt_path.lstat()
        except FileNotFoundError:
            receipt_exists = False
        else:
            receipt_exists = True
            _validate_release_receipt(
                receipt_path,
                expected=receipt_expected,
                proof_secret=proof_secret,
                verification_keys=verification_keys,
            )
        if not args.apply:
            if not marker_active and receipt_exists:
                print(f"OK: runtime guard was already released node={node_id}; durable receipt verified")
                return 0
            print(f"DRY-RUN: confirmation={token}")
            return 0
        _require_root()
        if args.confirm != token:
            raise PermissionError("runtime guard release confirmation token is missing or incorrect")
        if marker_active and not receipt_exists:
            receipt = _build_release_receipt(
                node_id=node_id,
                transaction_id=args.transaction_id,
                database_sha=expected,
                runtime_secret=runtime_secret,
                proof_secret=proof_secret,
                guard_sha=guard_sha,
                env_proofs_sha=env_proofs_sha,
                database_certificate_sha=database_certificate_sha,
                confirmation=token,
                signing_key=signing_key,
                verification_keys=verification_keys,
            )
            _write_json_no_clobber(receipt_path, receipt)
            _validate_release_receipt(
                receipt_path,
                expected=receipt_expected,
                proof_secret=proof_secret,
                verification_keys=verification_keys,
            )
        elif not receipt_exists:
            raise PermissionError("released guard has no durable authorization receipt")
        _finalize_transaction_guard_release(
            node_id=node_id,
            transaction_id=args.transaction_id,
            proof_secret=proof_secret,
        )
    print(f"OK: runtime guard released node={node_id}; persistent LB maintenance remains armed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-path", type=Path, default=APPLICATION_LOCK, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    guard_contract = commands.add_parser(
        "guard-contract",
        help="pre-provision the static systemd boot/start guard before a maintenance window",
    )
    guard_contract.add_argument("--env-file", type=Path, required=True)
    guard_contract.add_argument("--node-id", choices=REQUIRED_NODES, required=True)
    guard_contract.add_argument("--confirm", default="")
    guard_contract_mode = guard_contract.add_mutually_exclusive_group()
    guard_contract_mode.add_argument("--apply", action="store_true")
    guard_contract_mode.add_argument("--verify-only", action="store_true")

    proof = commands.add_parser("offline-proof", help="prove one node offline and back up its exact env")
    proof.add_argument("--env-file", type=Path, required=True)
    proof.add_argument("--proof-key-file", type=Path, required=True)
    proof.add_argument("--node-signing-key-file", type=Path, required=True)
    proof.add_argument("--node-verification-keys-file", type=Path, required=True)
    proof.add_argument("--env-backup", type=Path, required=True)
    proof.add_argument("--output", type=Path, required=True)
    proof.add_argument("--node-id", choices=REQUIRED_NODES, required=True)
    proof.add_argument("--transaction-id", required=True)
    proof.add_argument("--confirm", default="")
    proof.add_argument("--apply", action="store_true")

    rekey = commands.add_parser("rekey", help="plan or atomically rekey both credential products")
    rekey.add_argument("--env-file", type=Path, required=True)
    rekey.add_argument("--new-key-file", type=Path, required=True)
    rekey.add_argument("--recovery-key-file", type=Path, required=True)
    rekey.add_argument("--proof-key-file", type=Path, required=True)
    rekey.add_argument("--node-signing-key-file", type=Path, required=True)
    rekey.add_argument("--node-verification-keys-file", type=Path, required=True)
    rekey.add_argument("--database-certificate", type=Path, required=True)
    rekey.add_argument("--new-key-version", required=True)
    rekey.add_argument("--transaction-id", required=True)
    rekey.add_argument("--node-proof", type=Path, action="append", default=[])
    rekey.add_argument("--local-env-backup", type=Path)
    rekey.add_argument("--preimage", type=Path)
    rekey.add_argument("--expected-current-sha256", default="")
    rekey.add_argument("--confirm", default="")
    rekey.add_argument("--apply", action="store_true")

    rollback = commands.add_parser("rollback", help="plan or transactionally restore a cross-product preimage")
    rollback.add_argument("--env-file", type=Path, required=True)
    rollback.add_argument("--restored-key-file", type=Path, required=True)
    rollback.add_argument("--recovery-key-file", type=Path, required=True)
    rollback.add_argument("--proof-key-file", type=Path, required=True)
    rollback.add_argument("--original-proof-key-file", type=Path, required=True)
    rollback.add_argument("--original-node-proof", type=Path, required=True)
    rollback.add_argument("--node-signing-key-file", type=Path, required=True)
    rollback.add_argument("--node-verification-keys-file", type=Path, required=True)
    rollback.add_argument("--database-certificate", type=Path, required=True)
    rollback.add_argument("--preimage", type=Path, required=True)
    rollback.add_argument("--pre-rollback", type=Path)
    rollback.add_argument("--original-transaction-id", required=True)
    rollback.add_argument("--transaction-id", required=True)
    rollback.add_argument("--node-proof", type=Path, action="append", default=[])
    rollback.add_argument("--expected-current-sha256", default="")
    rollback.add_argument("--confirm", default="")
    rollback.add_argument("--apply", action="store_true")

    stage = commands.add_parser("stage-env", help="stage the already-committed key on one offline node")
    stage.add_argument("--env-file", type=Path, required=True)
    stage.add_argument("--env-backup", type=Path, required=True)
    stage.add_argument("--new-key-file", type=Path, required=True)
    stage.add_argument("--proof-key-file", type=Path, required=True)
    stage.add_argument("--node-signing-key-file", type=Path, required=True)
    stage.add_argument("--node-verification-keys-file", type=Path, required=True)
    stage.add_argument("--database-certificate", type=Path, required=True)
    stage.add_argument("--node-proof", type=Path, required=True)
    stage.add_argument("--peer-node-proof", type=Path, required=True)
    stage.add_argument("--output", type=Path, required=True)
    stage.add_argument("--node-id", choices=REQUIRED_NODES, required=True)
    stage.add_argument("--transaction-id", required=True)
    stage.add_argument("--expected-database-sha256", required=True)
    stage.add_argument("--confirm", default="")
    stage.add_argument("--apply", action="store_true")

    restore_env = commands.add_parser("restore-env", help="restore one node's exact pre-rekey env while offline")
    restore_env.add_argument("--env-file", type=Path, required=True)
    restore_env.add_argument("--desired-env-backup", type=Path, required=True)
    restore_env.add_argument("--current-env-backup", type=Path, required=True)
    restore_env.add_argument("--original-node-proof", type=Path, required=True)
    restore_env.add_argument("--original-proof-key-file", type=Path, required=True)
    restore_env.add_argument("--proof-key-file", type=Path, required=True)
    restore_env.add_argument("--node-signing-key-file", type=Path, required=True)
    restore_env.add_argument("--node-verification-keys-file", type=Path, required=True)
    restore_env.add_argument("--database-certificate", type=Path, required=True)
    restore_env.add_argument("--node-proof", type=Path, required=True)
    restore_env.add_argument("--peer-node-proof", type=Path, required=True)
    restore_env.add_argument("--output", type=Path, required=True)
    restore_env.add_argument("--node-id", choices=REQUIRED_NODES, required=True)
    restore_env.add_argument("--original-transaction-id", required=True)
    restore_env.add_argument("--transaction-id", required=True)
    restore_env.add_argument("--expected-database-sha256", required=True)
    restore_env.add_argument("--confirm", default="")
    restore_env.add_argument("--apply", action="store_true")

    verify = commands.add_parser("verify-env", help="prove both staged envs and all DB ciphertext agree")
    verify.add_argument("--env-file", type=Path, required=True)
    verify.add_argument("--proof-key-file", type=Path, required=True)
    verify.add_argument("--node-verification-keys-file", type=Path, required=True)
    verify.add_argument("--database-certificate", type=Path, required=True)
    verify.add_argument("--env-proof", type=Path, action="append", required=True)
    verify.add_argument("--transaction-id", required=True)
    verify.add_argument("--expected-database-sha256", required=True)

    release = commands.add_parser(
        "release-guard",
        help="unarm one verified node for a controlled restart while LB maintenance stays armed",
    )
    release.add_argument("--env-file", type=Path, required=True)
    release.add_argument("--proof-key-file", type=Path, required=True)
    release.add_argument("--node-signing-key-file", type=Path, required=True)
    release.add_argument("--node-verification-keys-file", type=Path, required=True)
    release.add_argument("--database-certificate", type=Path, required=True)
    release.add_argument("--env-proof", type=Path, action="append", required=True)
    release.add_argument("--node-id", choices=REQUIRED_NODES, required=True)
    release.add_argument("--transaction-id", required=True)
    release.add_argument("--expected-database-sha256", required=True)
    release.add_argument("--confirm", default="")
    release.add_argument("--apply", action="store_true")
    return parser


def _validate_required_paths(args: argparse.Namespace) -> None:
    if args.command == "rekey" and args.apply:
        if len(args.node_proof) != 2 or args.local_env_backup is None or args.preimage is None:
            raise ValueError("rekey --apply requires two proofs, local env backup, and preimage path")
    if args.command == "rollback" and args.apply:
        if len(args.node_proof) != 2 or args.pre_rollback is None:
            raise ValueError("rollback --apply requires two proofs and pre-rollback path")
    if args.command in {
        "rekey",
        "rollback",
        "stage-env",
        "restore-env",
        "verify-env",
        "release-guard",
        "offline-proof",
    }:
        transaction_id = str(getattr(args, "transaction_id", ""))
        if not TX_RE.fullmatch(transaction_id):
            raise ValueError("transaction ID must be exactly 32 lowercase hexadecimal characters")
    if args.command in {"rollback", "restore-env"} and not TX_RE.fullmatch(str(args.original_transaction_id)):
        raise ValueError("original transaction ID must be exactly 32 lowercase hexadecimal characters")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _validate_required_paths(args)
        if args.command == "guard-contract":
            return _command_guard_contract(args)
        if args.command == "offline-proof":
            return _command_offline_proof(args)
        if args.command == "rekey":
            return _command_rekey(args)
        if args.command == "rollback":
            return _command_rollback(args)
        if args.command == "stage-env":
            return _command_stage_env(args)
        if args.command == "restore-env":
            return _command_restore_env(args)
        if args.command == "verify-env":
            return _command_verify_env(args)
        if args.command == "release-guard":
            return _command_release_guard(args)
        raise ValueError("unknown command")
    except Exception as exc:  # noqa: BLE001 - never leak secret-bearing exception text.
        print(f"ERROR: cross-product credential operation failed ({type(exc).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
