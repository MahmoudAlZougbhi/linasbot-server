#!/usr/bin/env python3
"""Closed release manifest plus shared deterministic archive contract."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import sys
import sysconfig
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.ha.release_archive_contract import (
    ArchiveEvidence,
    ContractError,
    copy_regular,
    create_archive,
    extract_archive,
    file_evidence,
    read_regular,
    sha256_file,
    tree_evidence,
    verify_archive,
)

MANIFEST_SCHEMA = "linasbot-release-manifest-v1"
WORKFLOW_PATH = ".github/workflows/quality-gates.yml"
PYTHON_VERSION = "3.13.15"
PIP_VERSION = "26.2.1"
PYTHON_CACHE_TAG = "cpython-313"
PYTHON_PLATFORM = "linux-x86_64"
PYTHON_MACHINE = "x86_64"
PYTHON_RUNTIME_NAME = "cpython-3.13.15+20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_RUNTIME_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/20260814/"
    "cpython-3.13.15%2B20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
)
PYTHON_RUNTIME_SHA256 = "aaca2af2ab4d7b68a712660d1334c0cfd5ec13c0312ccd30c29122d8d0342320"
PYTHON_EXECUTABLE_SHA256 = "ce20f82411f2b0ccdf3e2212ca62303519521d73d25178588f1a9c8d4935c866"
PYTHON_RUNTIME_TREE_SHA256 = "e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc"
PYTHON_LIBPYTHON_NAME = "lib/libpython3.13.so.1.0"
PYTHON_LIBPYTHON_SHA256 = "965dcc1afd5934923b5a930e54afcaafc572485394ae33c35d27038bd943dcc5"
NODE_VERSION = "v22.23.2"
NPM_VERSION = "10.9.8"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
TARGET_SHA_RE = re.compile(r"[0-9a-f]{40}")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
CONTROL_PLANE_FILES = (
    "deploy/systemd/95-linasbot-credential-rekey-guard.conf",
    "deploy/systemd/linasbot-worker@.service",
    "deploy/systemd/linasbot.service",
    "requirements.lock",
    "scripts/ha/bootstrap_meta_ha_contract.py",
    "scripts/ha/cluster_runtime_env_contract.py",
    "scripts/ha/deploy_meta_release_ha.sh",
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
)
CONTROL_PLANE_MEMBERS = frozenset({"deploy", "deploy/systemd", "scripts", "scripts/ha", *CONTROL_PLANE_FILES})
FINAL_FILES = frozenset(
    {
        "release-manifest.json",
        "wheelhouse.tar",
        "dashboard-build.tar",
        "control-plane.tar",
        "source.bundle",
        PYTHON_RUNTIME_NAME,
    }
)
MAX_SOURCE_BUNDLE_SIZE = 1024**3
MAX_PYTHON_RUNTIME_SIZE = 256 * 1024**2

__all__ = [
    "ArchiveEvidence",
    "ContractError",
    "copy_regular",
    "create_archive",
    "extract_archive",
    "file_evidence",
    "read_regular",
    "sha256_file",
    "tree_evidence",
    "verify_archive",
]


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ContractError("release JSON is not canonicalizable") from exc


def _exact_keys(payload: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ContractError(f"{label} schema is not closed")
    return payload


def _digest(value: Any) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ContractError("release digest is invalid")
    return value


def validate_python_identity(payload: Mapping[str, Any]) -> None:
    keys = {
        "implementation",
        "version",
        "pip_version",
        "cache_tag",
        "platform",
        "machine",
        "runtime_artifact_name",
        "runtime_artifact_url",
        "runtime_artifact_sha256",
        "runtime_executable_name",
        "runtime_executable_sha256",
        "runtime_tree_sha256",
        "runtime_libpython_name",
        "runtime_libpython_sha256",
    }
    _exact_keys(payload, keys, "Python toolchain")
    authority = {
        "implementation": "CPython",
        "version": PYTHON_VERSION,
        "pip_version": PIP_VERSION,
        "cache_tag": PYTHON_CACHE_TAG,
        "platform": PYTHON_PLATFORM,
        "machine": PYTHON_MACHINE,
        "runtime_artifact_name": PYTHON_RUNTIME_NAME,
        "runtime_artifact_url": PYTHON_RUNTIME_URL,
        "runtime_artifact_sha256": PYTHON_RUNTIME_SHA256,
        "runtime_executable_name": "python3.13",
        "runtime_executable_sha256": PYTHON_EXECUTABLE_SHA256,
        "runtime_tree_sha256": PYTHON_RUNTIME_TREE_SHA256,
        "runtime_libpython_name": PYTHON_LIBPYTHON_NAME,
        "runtime_libpython_sha256": PYTHON_LIBPYTHON_SHA256,
    }
    if any(payload.get(key) != value for key, value in authority.items()):
        raise ContractError("Python toolchain differs from the reviewed authority")


def validate_manifest(
    payload: Mapping[str, Any],
    *,
    expected_repository: str | None = None,
    expected_workflow_ref: str | None = None,
    expected_run_id: int | None = None,
    expected_run_attempt: int | None = None,
    expected_target_sha: str | None = None,
) -> dict[str, Any]:
    """Validate a closed v1 manifest and optional GitHub/deploy context."""
    _exact_keys(
        payload,
        {
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
        },
        "release manifest",
    )
    repository = payload.get("repository")
    workflow_ref = payload.get("workflow_ref")
    if payload.get("schema") != MANIFEST_SCHEMA or payload.get("workflow_path") != WORKFLOW_PATH:
        raise ContractError("release manifest identity is invalid")
    if not isinstance(repository, str) or REPOSITORY_RE.fullmatch(repository) is None:
        raise ContractError("release repository identity is invalid")
    prefix = f"{repository}/{WORKFLOW_PATH}@refs/"
    if not isinstance(workflow_ref, str) or not workflow_ref.startswith(prefix) or len(workflow_ref) > 512:
        raise ContractError("release workflow ref is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in workflow_ref):
        raise ContractError("release workflow ref contains control characters")
    run_id = payload.get("run_id")
    run_attempt = payload.get("run_attempt")
    target_sha = payload.get("target_sha")
    if type(run_id) is not int or run_id < 1 or type(run_attempt) is not int or run_attempt < 1:
        raise ContractError("release run identity is invalid")
    if not isinstance(target_sha, str) or TARGET_SHA_RE.fullmatch(target_sha) is None:
        raise ContractError("release target SHA is invalid")
    locks = _exact_keys(
        payload.get("source_locks"),
        {
            "requirements_lock_sha256",
            "requirements_dev_lock_sha256",
            "dashboard_package_lock_sha256",
        },
        "source lock",
    )
    for value in locks.values():
        _digest(value)
    toolchains = _exact_keys(payload.get("toolchains"), {"python", "node", "npm"}, "toolchain")
    validate_python_identity(toolchains["python"])
    node = _exact_keys(toolchains["node"], {"version"}, "Node toolchain")
    npm = _exact_keys(toolchains["npm"], {"version"}, "npm toolchain")
    if node["version"] != NODE_VERSION or npm["version"] != NPM_VERSION:
        raise ContractError("frontend toolchain differs from the reviewed authority")
    artifact_payloads = _exact_keys(
        payload.get("payloads"),
        {"wheelhouse", "dashboard", "control_plane", "source_bundle", "python_runtime"},
        "release payload",
    )
    payload_names = (
        ("wheelhouse", "wheelhouse.tar"),
        ("dashboard", "dashboard-build.tar"),
        ("control_plane", "control-plane.tar"),
    )
    for key, filename in payload_names:
        item = _exact_keys(
            artifact_payloads[key],
            {"archive", "archive_sha256", "tree_sha256", "file_count", "total_size"},
            f"{key} payload",
        )
        if item.get("archive") != filename:
            raise ContractError("release payload filename is invalid")
        _digest(item.get("archive_sha256"))
        _digest(item.get("tree_sha256"))
        if type(item.get("file_count")) is not int or item["file_count"] < 1:
            raise ContractError("release payload file count is invalid")
        if type(item.get("total_size")) is not int or item["total_size"] < 1:
            raise ContractError("release payload total size is invalid")
    source_bundle = _exact_keys(
        artifact_payloads["source_bundle"],
        {"file", "sha256", "size", "target_sha", "target_tree_sha", "advertised_ref"},
        "source bundle payload",
    )
    if (
        source_bundle.get("file") != "source.bundle"
        or source_bundle.get("advertised_ref") != "HEAD"
        or source_bundle.get("target_sha") != target_sha
        or not isinstance(source_bundle.get("target_tree_sha"), str)
        or TARGET_SHA_RE.fullmatch(source_bundle["target_tree_sha"]) is None
        or type(source_bundle.get("size")) is not int
        or source_bundle["size"] < 1
        or source_bundle["size"] > MAX_SOURCE_BUNDLE_SIZE
    ):
        raise ContractError("source bundle identity is invalid")
    _digest(source_bundle.get("sha256"))
    python_runtime = _exact_keys(
        artifact_payloads["python_runtime"],
        {"file", "sha256", "size"},
        "Python runtime payload",
    )
    if (
        python_runtime.get("file") != PYTHON_RUNTIME_NAME
        or python_runtime.get("sha256") != PYTHON_RUNTIME_SHA256
        or type(python_runtime.get("size")) is not int
        or python_runtime["size"] < 1
        or python_runtime["size"] > MAX_PYTHON_RUNTIME_SIZE
    ):
        raise ContractError("Python runtime payload identity is invalid")
    expected = (
        (repository, expected_repository),
        (workflow_ref, expected_workflow_ref),
        (run_id, expected_run_id),
        (run_attempt, expected_run_attempt),
        (target_sha, expected_target_sha),
    )
    if any(wanted is not None and actual != wanted for actual, wanted in expected):
        raise ContractError("release manifest does not match the expected GitHub context")
    return dict(payload)


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ContractError("release output already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o644)


def write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    validate_manifest(payload)
    _write_new(path, canonical_json(payload))


def load_manifest(path: Path, **expected: Any) -> dict[str, Any]:
    try:
        raw = read_regular(path, max_bytes=1024 * 1024)
        payload = json.loads(raw.decode("utf-8", "strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("release manifest could not be decoded") from exc
    if not isinstance(payload, dict) or canonical_json(payload) != raw:
        raise ContractError("release manifest is not canonical JSON")
    return validate_manifest(payload, **expected)


def verify_release_bundle(directory: Path, **expected: Any) -> dict[str, Any]:
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        raise ContractError("release bundle directory could not be read") from exc
    if {entry.name for entry in entries} != FINAL_FILES or any(
        not entry.is_file(follow_symlinks=False) for entry in entries
    ):
        raise ContractError("release bundle file set is not closed")
    manifest = load_manifest(directory / "release-manifest.json", **expected)
    for key in ("wheelhouse", "dashboard", "control_plane"):
        item = manifest["payloads"][key]
        evidence = verify_archive(
            directory / item["archive"],
            item["archive_sha256"],
            item["tree_sha256"],
            expected_paths=CONTROL_PLANE_MEMBERS if key == "control_plane" else None,
        )
        if evidence.file_count != item["file_count"] or evidence.total_size != item["total_size"]:
            raise ContractError("release payload size evidence does not match the manifest")
    source_bundle = manifest["payloads"]["source_bundle"]
    source_path = directory / source_bundle["file"]
    source_sha256, source_size = file_evidence(source_path, max_bytes=MAX_SOURCE_BUNDLE_SIZE)
    if source_sha256 != source_bundle["sha256"] or source_size != source_bundle["size"]:
        raise ContractError("source bundle bytes differ from the manifest")
    python_runtime = manifest["payloads"]["python_runtime"]
    runtime_sha256, runtime_size = file_evidence(
        directory / python_runtime["file"],
        max_bytes=MAX_PYTHON_RUNTIME_SIZE,
    )
    if runtime_sha256 != PYTHON_RUNTIME_SHA256 or runtime_size != python_runtime["size"]:
        raise ContractError("Python runtime archive bytes differ from the manifest")
    return manifest


def current_python_identity(runtime_executable: Path) -> dict[str, str]:
    if (
        platform.python_implementation() != "CPython"
        or platform.python_version() != PYTHON_VERSION
        or sys.implementation.cache_tag != PYTHON_CACHE_TAG
        or sysconfig.get_platform() != PYTHON_PLATFORM
        or platform.machine() != PYTHON_MACHINE
    ):
        raise ContractError("artifact producer is not the exact reviewed Python runtime")
    if runtime_executable.name != "python3.13":
        raise ContractError("runtime executable name is invalid")
    runtime_root = runtime_executable.parent.parent
    executable_sha256 = sha256_file(runtime_executable)
    libpython_sha256 = sha256_file(runtime_root / PYTHON_LIBPYTHON_NAME)
    runtime_tree_sha256 = python_runtime_tree_sha256(runtime_root)
    if (
        executable_sha256 != PYTHON_EXECUTABLE_SHA256
        or libpython_sha256 != PYTHON_LIBPYTHON_SHA256
        or runtime_tree_sha256 != PYTHON_RUNTIME_TREE_SHA256
    ):
        raise ContractError("Python runtime bytes differ from the reviewed immutable artifact")
    return {
        "implementation": "CPython",
        "version": PYTHON_VERSION,
        "pip_version": PIP_VERSION,
        "cache_tag": PYTHON_CACHE_TAG,
        "platform": PYTHON_PLATFORM,
        "machine": PYTHON_MACHINE,
        "runtime_artifact_name": PYTHON_RUNTIME_NAME,
        "runtime_artifact_url": PYTHON_RUNTIME_URL,
        "runtime_artifact_sha256": PYTHON_RUNTIME_SHA256,
        "runtime_executable_name": "python3.13",
        "runtime_executable_sha256": executable_sha256,
        "runtime_tree_sha256": runtime_tree_sha256,
        "runtime_libpython_name": PYTHON_LIBPYTHON_NAME,
        "runtime_libpython_sha256": libpython_sha256,
    }


def python_runtime_tree_sha256(root: Path) -> str:
    """Project the portable runtime with the deploy verifier's reviewed algorithm."""
    root_info = root.lstat()
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or stat.S_ISLNK(root_info.st_mode)
        or stat.S_IMODE(root_info.st_mode) != 0o755
    ):
        raise ContractError("Python runtime root mode is invalid")
    digest = hashlib.sha256()

    def update(record: dict[str, object]) -> None:
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big") + encoded)

    update({"path": ".", "type": "directory", "mode": stat.S_IMODE(root_info.st_mode)})
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in [*dirnames, *filenames]:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            record: dict[str, object] = {"path": relative, "mode": stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                try:
                    path.resolve(strict=True).relative_to(root)
                except (OSError, ValueError) as exc:
                    raise ContractError("Python runtime symlink escapes its root") from exc
                record.update({"type": "symlink", "target": target})
            elif stat.S_ISDIR(info.st_mode):
                if stat.S_IMODE(info.st_mode) & 0o022:
                    raise ContractError("Python runtime directory is writable by group or world")
                record["type"] = "directory"
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if stat.S_IMODE(info.st_mode) & 0o022:
                    raise ContractError("Python runtime file is writable by group or world")
                record.update({"type": "file", "size": info.st_size, "sha256": sha256_file(path)})
            else:
                raise ContractError("Python runtime tree contains an unsupported object")
            update(record)
    return digest.hexdigest()
