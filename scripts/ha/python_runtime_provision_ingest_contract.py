#!/usr/bin/env python3
"""Closed manifest and member contract for clean-host runtime ingest."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

REPOSITORY = "MahmoudAlZougbhi/linasbot-server"
WORKFLOW_REF = f"{REPOSITORY}/.github/workflows/quality-gates.yml@refs/heads/main"
RUNTIME_NAME = "cpython-3.13.15+20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
RUNTIME_SHA256 = "aaca2af2ab4d7b68a712660d1334c0cfd5ec13c0312ccd30c29122d8d0342320"
RUNTIME_TREE_SHA256 = "e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc"
PYTHON_SHA256 = "ce20f82411f2b0ccdf3e2212ca62303519521d73d25178588f1a9c8d4935c866"
LIBPYTHON_SHA256 = "965dcc1afd5934923b5a930e54afcaafc572485394ae33c35d27038bd943dcc5"
FILES = frozenset(
    {
        "release-manifest.json",
        "wheelhouse.tar",
        "dashboard-build.tar",
        "control-plane.tar",
        "source.bundle",
        RUNTIME_NAME,
    }
)
CONTROL_FILES = frozenset(
    {
        "deploy/systemd/95-linasbot-credential-rekey-guard.conf",
        "deploy/systemd/linasbot-worker@.service",
        "deploy/systemd/linasbot.service",
        "requirements.lock",
        "scripts/ha/bootstrap_meta_ha_contract.py",
        "scripts/ha/bootstrap_nested_runtime_quarantine.py",
        "scripts/ha/cluster_runtime_env_contract.py",
        "scripts/ha/deploy_meta_release_ha.sh",
        "scripts/ha/do_lb_ready_contract.py",
        "scripts/ha/manage_do_lb_ready_healthcheck.py",
        "scripts/ha/production_mutation_guard.py",
        "scripts/ha/provision_python_runtime_ha.py",
        "scripts/ha/python_runtime_archive_contract.py",
        "scripts/ha/python_runtime_provision_authority.py",
        "scripts/ha/python_runtime_provision_commit.py",
        "scripts/ha/python_runtime_provision_coordinator.py",
        "scripts/ha/python_runtime_provision_contract.py",
        "scripts/ha/python_runtime_provision_ingest.py",
        "scripts/ha/python_runtime_provision_ingest_contract.py",
        "scripts/ha/python_runtime_provision_peer.py",
        "scripts/ha/python_runtime_provision_rollback.py",
        "scripts/ha/python_runtime_provision_state.py",
        "scripts/ha/python_runtime_provision_trusted_launcher.py",
        "scripts/ha/python_runtime_provision_workflow_bootstrap.py",
        "scripts/ha/release_archive_contract.py",
        "scripts/ha/release_artifact_contract.py",
        "scripts/ha/release_readiness_probe.py",
        "scripts/ha/release_verify_server.py",
        "scripts/ha/verify_meta_release_ha.sh",
    }
)
CONTROL_MEMBERS = frozenset({"deploy", "deploy/systemd", "scripts", "scripts/ha", *CONTROL_FILES})
TREE_DOMAIN = b"linasbot-release-tree-v1\0"
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
LAUNCHER_RECEIPT_FORMAT: Final = "linas-python-runtime-launcher-v1"
LAUNCHER_RECEIPT_KEYS: Final = {
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
LOCK_PATH: Final = Path("/run/lock/linasbot-meta-live.lock")
INGEST_COLLISIONS: Final = (
    "bootstrap.active",
    "bootstrap.coordinator.json",
    "transaction.json",
    "env.before",
    "deploy.active",
    "deploy-node.active",
    "controlled-failover.active",
    "registry-nfs-retire.active",
    "rekey/runtime.guard",
    "python-runtime-provision.active",
    "python-runtime-provision.coordinator.json",
)


class IngestError(RuntimeError):
    pass


def canonical(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def _sync_dir(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _root_read(path: Path, limit: int = 1024 * 1024) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode), before.st_nlink) != (0, 0, 0o600, 1)
        or not 1 <= before.st_size <= limit
    ):
        raise IngestError("runtime launcher receipt is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        consumed = 0
        while consumed < opened.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - consumed))
            if not chunk:
                raise IngestError("runtime launcher receipt is truncated")
            chunks.append(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, key) != getattr(opened, key) for key in identity) or any(
        getattr(opened, key) != getattr(after, key) for key in identity
    ):
        raise IngestError("runtime launcher receipt changed while reading")
    return b"".join(chunks)


def write_launcher_receipt(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        if _root_read(path) != payload:
            raise IngestError("runtime launcher receipt conflicts")
        return
    temporary = path.parent / f".{path.name}.writing"
    if temporary.exists() or temporary.is_symlink():
        info = temporary.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink) != (0, 0, 0o600, 1)
        ):
            raise IngestError("runtime launcher receipt temporary is unsafe")
        temporary.unlink()
        _sync_dir(path.parent)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                raise IngestError("runtime launcher receipt write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _sync_dir(path.parent)
    if path.exists() or path.is_symlink():
        raise IngestError("runtime launcher receipt appeared during publication")
    os.replace(temporary, path)
    _sync_dir(path.parent)


@contextmanager
def common_lock(state_root: Path) -> Iterator[None]:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        LOCK_PATH,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise IngestError("release ingest common lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        for relative in INGEST_COLLISIONS:
            candidate = state_root / relative
            if candidate.exists() or candidate.is_symlink():
                raise IngestError(f"release ingest collides with {relative}")
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def launcher_receipt(
    *,
    artifact_id: int,
    artifact_api_sha256: str,
    manifest_sha256: str,
    run_id: int,
    run_attempt: int,
    target_sha: str,
    bundle_root: Path,
    control_root: Path,
    control_archive_sha256: str,
    control_tree_sha256: str,
    launcher_sha256: str,
    launcher_size: int,
) -> dict[str, Any]:
    payload = {
        "schema": 1,
        "format": LAUNCHER_RECEIPT_FORMAT,
        "artifact_id": artifact_id,
        "artifact_api_sha256": artifact_api_sha256,
        "manifest_sha256": manifest_sha256,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "target_sha": target_sha,
        "bundle_root": str(bundle_root),
        "control_root": str(control_root),
        "control_plane_archive_sha256": control_archive_sha256,
        "control_plane_tree_sha256": control_tree_sha256,
        "launcher_path": str(control_root / "scripts/ha/python_runtime_provision_trusted_launcher.py"),
        "launcher_sha256": launcher_sha256,
        "launcher_size": launcher_size,
    }
    return validate_launcher_receipt(payload)


def validate_launcher_receipt(payload: Any) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != LAUNCHER_RECEIPT_KEYS
        or payload.get("schema") != 1
        or payload.get("format") != LAUNCHER_RECEIPT_FORMAT
        or any(
            type(payload.get(key)) is not int or payload[key] < 1 for key in ("artifact_id", "run_id", "run_attempt")
        )
        or type(payload.get("launcher_size")) is not int
        or not 1 <= payload["launcher_size"] <= 8 * 1024**2
    ):
        raise IngestError("runtime launcher receipt schema is invalid")
    for key in (
        "artifact_api_sha256",
        "manifest_sha256",
        "control_plane_archive_sha256",
        "control_plane_tree_sha256",
        "launcher_sha256",
    ):
        if SHA256_RE.fullmatch(str(payload.get(key))) is None or payload[key] == "0" * 64:
            raise IngestError("runtime launcher receipt digest is invalid")
    if SHA_RE.fullmatch(str(payload.get("target_sha"))) is None or payload["target_sha"] == "0" * 40:
        raise IngestError("runtime launcher receipt target is invalid")
    key = f"{payload['artifact_id']}-{payload['artifact_api_sha256']}"
    expected_bundle = f"/var/lib/linasbot/meta-ha/release-bundles/{key}"
    expected_control = f"/var/lib/linasbot/meta-ha/python-runtime-provision-control/{key}"
    if (
        payload.get("bundle_root") != expected_bundle
        or payload.get("control_root") != expected_control
        or payload.get("launcher_path") != f"{expected_control}/scripts/ha/python_runtime_provision_trusted_launcher.py"
    ):
        raise IngestError("runtime launcher receipt path binding is invalid")
    return payload


def manifest_evidence(
    manifest: dict[str, Any],
    artifact_id: int,
    run_id: int,
    run_attempt: int,
    target_sha: str,
) -> dict[str, tuple[str, int]]:
    if set(manifest) != {
        "schema",
        "repository",
        "workflow_path",
        "workflow_ref",
        "run_id",
        "run_attempt",
        "target_sha",
        "source_locks",
        "toolchains",
        "payloads",
    }:
        raise IngestError("release manifest schema is not closed")
    if (
        manifest.get("schema") != "linasbot-release-manifest-v1"
        or manifest.get("repository") != REPOSITORY
        or manifest.get("workflow_path") != ".github/workflows/quality-gates.yml"
        or manifest.get("workflow_ref") != WORKFLOW_REF
        or manifest.get("run_id") != run_id
        or manifest.get("run_attempt") != run_attempt
        or manifest.get("target_sha") != target_sha
        or artifact_id < 1
    ):
        raise IngestError("release manifest differs from GitHub authority")
    toolchains = manifest.get("toolchains")
    if not isinstance(toolchains, dict):
        raise IngestError("release toolchain authority is invalid")
    python = toolchains.get("python", {})
    expected_python = {
        "runtime_artifact_name": RUNTIME_NAME,
        "runtime_artifact_sha256": RUNTIME_SHA256,
        "runtime_executable_sha256": PYTHON_SHA256,
        "runtime_tree_sha256": RUNTIME_TREE_SHA256,
        "runtime_libpython_sha256": LIBPYTHON_SHA256,
    }
    if not isinstance(python, dict) or any(python.get(key) != value for key, value in expected_python.items()):
        raise IngestError("release Python authority is invalid")
    payloads = manifest.get("payloads")
    if not isinstance(payloads, dict) or set(payloads) != {
        "wheelhouse",
        "dashboard",
        "control_plane",
        "source_bundle",
        "python_runtime",
    }:
        raise IngestError("release payload schema is not closed")
    result: dict[str, tuple[str, int]] = {}
    for key, name in (
        ("wheelhouse", "wheelhouse.tar"),
        ("dashboard", "dashboard-build.tar"),
        ("control_plane", "control-plane.tar"),
    ):
        item = payloads[key]
        if (
            not isinstance(item, dict)
            or set(item) != {"archive", "archive_sha256", "tree_sha256", "file_count", "total_size"}
            or item.get("archive") != name
        ):
            raise IngestError("release archive payload is invalid")
        if any(SHA256_RE.fullmatch(str(item.get(field))) is None for field in ("archive_sha256", "tree_sha256")):
            raise IngestError("release archive payload digest is invalid")
        if any(type(item.get(field)) is not int or item[field] < 1 for field in ("file_count", "total_size")):
            raise IngestError("release archive payload evidence is invalid")
        result[name] = (str(item["archive_sha256"]), 1024**3)
    source = payloads["source_bundle"]
    if (
        not isinstance(source, dict)
        or set(source) != {"file", "sha256", "size", "target_sha", "target_tree_sha", "advertised_ref"}
        or source.get("file") != "source.bundle"
        or source.get("advertised_ref") != "HEAD"
        or source.get("target_sha") != target_sha
        or SHA_RE.fullmatch(str(source.get("target_tree_sha"))) is None
    ):
        raise IngestError("release source bundle payload is invalid")
    runtime = payloads["python_runtime"]
    if runtime != {"file": RUNTIME_NAME, "sha256": RUNTIME_SHA256, "size": runtime.get("size")}:
        raise IngestError("release runtime payload is invalid")
    for item, name, limit in ((source, "source.bundle", 1024**3), (runtime, RUNTIME_NAME, 256 * 1024**2)):
        if SHA256_RE.fullmatch(str(item.get("sha256"))) is None or type(item.get("size")) is not int:
            raise IngestError("release file payload evidence is invalid")
        if not 1 <= item["size"] <= limit:
            raise IngestError("release file payload size is invalid")
        result[name] = (str(item["sha256"]), limit)
    result["release-manifest.json"] = (hashlib.sha256(canonical(manifest)).hexdigest(), 1024 * 1024)
    return result
