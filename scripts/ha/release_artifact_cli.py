#!/usr/bin/env python3
"""Quality-gate producer for the closed Linas release artifact."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.ha.release_artifact_contract import (
    CONTROL_PLANE_FILES,
    MANIFEST_SCHEMA,
    MAX_PYTHON_RUNTIME_SIZE,
    NODE_VERSION,
    NPM_VERSION,
    PIP_VERSION,
    PYTHON_RUNTIME_NAME,
    PYTHON_RUNTIME_SHA256,
    WORKFLOW_PATH,
    ArchiveEvidence,
    ContractError,
    canonical_json,
    copy_regular,
    create_archive,
    current_python_identity,
    file_evidence,
    read_regular,
    sha256_file,
    validate_python_identity,
    verify_archive,
    verify_release_bundle,
    write_manifest,
)
from scripts.ha.release_source_bundle import (
    assert_clean_checkout as _assert_clean_checkout,
)
from scripts.ha.release_source_bundle import (
    create_source_bundle as _create_source_bundle,
)
from scripts.ha.release_source_bundle import (
    target_regular_file_authority as _target_regular_file_authority,
)

BACKEND_SCHEMA = "linasbot-backend-release-intermediate-v1"
FRONTEND_SCHEMA = "linasbot-frontend-release-intermediate-v1"
TARGET_SHA_RE = re.compile(r"[0-9a-f]{40}")
INTERMEDIATE_MAX_BYTES = 1024 * 1024


def _target_sha(value: str) -> str:
    if TARGET_SHA_RE.fullmatch(value) is None:
        raise ContractError("intermediate target SHA is invalid")
    return value


def _positive_decimal(value: str) -> int:
    if re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise argparse.ArgumentTypeError("value must be a canonical positive decimal")
    return int(value)


def _exact_keys(payload: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ContractError(f"{label} schema is not closed")
    return payload


def _write_document(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ContractError("intermediate output already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json(payload))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o644)


def _load_document(path: Path) -> dict[str, Any]:
    try:
        raw = read_regular(path, max_bytes=INTERMEDIATE_MAX_BYTES)
        payload = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("intermediate JSON could not be decoded") from exc
    if not isinstance(payload, dict) or canonical_json(payload) != raw:
        raise ContractError("intermediate JSON is not canonical")
    return payload


def _payload(filename: str, evidence: ArchiveEvidence) -> dict[str, Any]:
    if evidence.file_count < 1 or evidence.total_size < 1:
        raise ContractError("release payload must contain non-empty regular files")
    return {
        "archive": filename,
        "archive_sha256": evidence.archive_sha256,
        "tree_sha256": evidence.tree_sha256,
        "file_count": evidence.file_count,
        "total_size": evidence.total_size,
    }


def _verify_payload(payload: Any, archive: Path, filename: str) -> ArchiveEvidence:
    item = _exact_keys(
        payload,
        {"archive", "archive_sha256", "tree_sha256", "file_count", "total_size"},
        "intermediate payload",
    )
    if item.get("archive") != filename:
        raise ContractError("intermediate archive name is invalid")
    if type(item.get("file_count")) is not int or item["file_count"] < 1:
        raise ContractError("intermediate file count is invalid")
    if type(item.get("total_size")) is not int or item["total_size"] < 1:
        raise ContractError("intermediate total size is invalid")
    evidence = verify_archive(archive, item.get("archive_sha256"), item.get("tree_sha256"))
    if evidence.file_count != item["file_count"] or evidence.total_size != item["total_size"]:
        raise ContractError("intermediate size evidence changed")
    return evidence


def _assert_directory_files(directory: Path, expected: set[str]) -> None:
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        raise ContractError("intermediate directory could not be read") from exc
    if {entry.name for entry in entries} != expected or any(
        not entry.is_file(follow_symlinks=False) for entry in entries
    ):
        raise ContractError("intermediate artifact file set is not closed")


def command_pack(args: argparse.Namespace) -> None:
    evidence = create_archive(Path(args.source), Path(args.archive))
    print(
        f"archive_sha256={evidence.archive_sha256} tree_sha256={evidence.tree_sha256} "
        f"file_count={evidence.file_count} total_size={evidence.total_size}"
    )


def command_backend(args: argparse.Namespace) -> None:
    if args.pip_version != PIP_VERSION:
        raise ContractError("backend pip version differs from the reviewed authority")
    archive = Path(args.archive)
    if archive.name != "wheelhouse.tar":
        raise ContractError("backend archive filename is invalid")
    evidence = verify_archive(archive)
    output = Path(args.output)
    runtime_sha256, runtime_size = copy_regular(
        Path(args.runtime_archive),
        output.parent / PYTHON_RUNTIME_NAME,
        expected_sha256=PYTHON_RUNTIME_SHA256,
        executable=False,
    )
    if runtime_sha256 != PYTHON_RUNTIME_SHA256:
        raise ContractError("Python runtime archive differs from the reviewed authority")
    payload = {
        "schema": BACKEND_SCHEMA,
        "target_sha": _target_sha(args.target_sha),
        "source_locks": {
            "requirements_lock_sha256": sha256_file(Path(args.requirements_lock)),
            "requirements_dev_lock_sha256": sha256_file(Path(args.requirements_dev_lock)),
        },
        "python": current_python_identity(Path(args.runtime_executable)),
        "python_runtime": {
            "file": PYTHON_RUNTIME_NAME,
            "sha256": runtime_sha256,
            "size": runtime_size,
        },
        "wheelhouse": _payload(archive.name, evidence),
    }
    _write_document(output, payload)


def command_frontend(args: argparse.Namespace) -> None:
    if args.node_version != NODE_VERSION or args.npm_version != NPM_VERSION:
        raise ContractError("frontend toolchain differs from the reviewed authority")
    archive = Path(args.archive)
    if archive.name != "dashboard-build.tar":
        raise ContractError("frontend archive filename is invalid")
    evidence = verify_archive(archive)
    payload = {
        "schema": FRONTEND_SCHEMA,
        "target_sha": _target_sha(args.target_sha),
        "dashboard_package_lock_sha256": sha256_file(Path(args.package_lock)),
        "node": {"version": args.node_version},
        "npm": {"version": args.npm_version},
        "dashboard": _payload(archive.name, evidence),
    }
    _write_document(Path(args.output), payload)


def _load_backend(directory: Path, target_sha: str) -> dict[str, Any]:
    _assert_directory_files(
        directory,
        {"wheelhouse.tar", "backend-intermediate.json", PYTHON_RUNTIME_NAME},
    )
    payload = _load_document(directory / "backend-intermediate.json")
    _exact_keys(
        payload,
        {"schema", "target_sha", "source_locks", "python", "python_runtime", "wheelhouse"},
        "backend",
    )
    if payload["schema"] != BACKEND_SCHEMA or payload["target_sha"] != target_sha:
        raise ContractError("backend intermediate identity is invalid")
    _exact_keys(
        payload["source_locks"],
        {"requirements_lock_sha256", "requirements_dev_lock_sha256"},
        "backend lock",
    )
    validate_python_identity(payload["python"])
    _exact_keys(payload["python_runtime"], {"file", "sha256", "size"}, "Python runtime")
    runtime_sha256, runtime_size = file_evidence(
        directory / PYTHON_RUNTIME_NAME,
        max_bytes=MAX_PYTHON_RUNTIME_SIZE,
    )
    if (
        payload["python_runtime"]
        != {
            "file": PYTHON_RUNTIME_NAME,
            "sha256": runtime_sha256,
            "size": runtime_size,
        }
        or runtime_sha256 != PYTHON_RUNTIME_SHA256
    ):
        raise ContractError("backend Python runtime payload is invalid")
    _verify_payload(payload["wheelhouse"], directory / "wheelhouse.tar", "wheelhouse.tar")
    return payload


def _load_frontend(directory: Path, target_sha: str) -> dict[str, Any]:
    _assert_directory_files(directory, {"dashboard-build.tar", "frontend-intermediate.json"})
    payload = _load_document(directory / "frontend-intermediate.json")
    expected = {
        "schema",
        "target_sha",
        "dashboard_package_lock_sha256",
        "node",
        "npm",
        "dashboard",
    }
    _exact_keys(payload, expected, "frontend")
    if payload["schema"] != FRONTEND_SCHEMA or payload["target_sha"] != target_sha:
        raise ContractError("frontend intermediate identity is invalid")
    _exact_keys(payload["node"], {"version"}, "Node")
    _exact_keys(payload["npm"], {"version"}, "npm")
    if payload["node"]["version"] != NODE_VERSION or payload["npm"]["version"] != NPM_VERSION:
        raise ContractError("frontend intermediate toolchain is invalid")
    _verify_payload(
        payload["dashboard"],
        directory / "dashboard-build.tar",
        "dashboard-build.tar",
    )
    return payload


def _copy_control_plane(
    repository: Path,
    destination: Path,
    authority: Mapping[str, tuple[str, bool]],
) -> None:
    if set(authority) != set(CONTROL_PLANE_FILES):
        raise ContractError("control-plane target authority is incomplete")
    for relative in CONTROL_PLANE_FILES:
        source = repository / relative
        target = destination / relative
        expected_sha256, executable = authority[relative]
        copy_regular(
            source,
            target,
            expected_sha256=expected_sha256,
            executable=executable,
        )


def _copy_archive(source: Path, destination: Path, expected_sha256: str) -> None:
    copy_regular(source, destination, expected_sha256=expected_sha256, executable=False)


def command_assemble(args: argparse.Namespace) -> None:
    target_sha = _target_sha(args.target_sha)
    backend_dir = Path(args.backend_dir)
    frontend_dir = Path(args.frontend_dir)
    repository_root = Path(args.repository_root)
    _assert_clean_checkout(repository_root, Path(args.output_dir).parent, target_sha)
    control_authority = _target_regular_file_authority(
        repository_root,
        Path(args.output_dir).parent,
        target_sha,
        CONTROL_PLANE_FILES,
    )
    backend = _load_backend(backend_dir, target_sha)
    frontend = _load_frontend(frontend_dir, target_sha)
    locks = {
        "requirements_lock_sha256": sha256_file(Path(args.requirements_lock)),
        "requirements_dev_lock_sha256": sha256_file(Path(args.requirements_dev_lock)),
        "dashboard_package_lock_sha256": sha256_file(Path(args.package_lock)),
    }
    if backend["source_locks"] != {key: locks[key] for key in backend["source_locks"]}:
        raise ContractError("backend source locks differ from the target checkout")
    if frontend["dashboard_package_lock_sha256"] != locks["dashboard_package_lock_sha256"]:
        raise ContractError("frontend package lock differs from the target checkout")
    output = Path(args.output_dir)
    if output.exists() or output.is_symlink():
        raise ContractError("final release output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        _copy_archive(
            backend_dir / "wheelhouse.tar",
            temporary / "wheelhouse.tar",
            backend["wheelhouse"]["archive_sha256"],
        )
        copy_regular(
            backend_dir / PYTHON_RUNTIME_NAME,
            temporary / PYTHON_RUNTIME_NAME,
            expected_sha256=PYTHON_RUNTIME_SHA256,
            executable=False,
        )
        _copy_archive(
            frontend_dir / "dashboard-build.tar",
            temporary / "dashboard-build.tar",
            frontend["dashboard"]["archive_sha256"],
        )
        with tempfile.TemporaryDirectory(prefix="linas-control-plane-", dir=output.parent) as staging:
            _copy_control_plane(repository_root, Path(staging), control_authority)
            control_evidence = create_archive(Path(staging), temporary / "control-plane.tar")
        source_bundle = _create_source_bundle(
            repository_root,
            temporary / "source.bundle",
            target_sha,
        )
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "repository": args.repository,
            "workflow_path": WORKFLOW_PATH,
            "workflow_ref": args.workflow_ref,
            "run_id": int(args.run_id),
            "run_attempt": int(args.run_attempt),
            "target_sha": target_sha,
            "source_locks": locks,
            "toolchains": {
                "python": backend["python"],
                "node": frontend["node"],
                "npm": frontend["npm"],
            },
            "payloads": {
                "wheelhouse": backend["wheelhouse"],
                "dashboard": frontend["dashboard"],
                "control_plane": _payload("control-plane.tar", control_evidence),
                "source_bundle": source_bundle,
                "python_runtime": backend["python_runtime"],
            },
        }
        write_manifest(temporary / "release-manifest.json", manifest)
        _assert_clean_checkout(repository_root, output.parent, target_sha)
        if (
            _target_regular_file_authority(
                repository_root,
                output.parent,
                target_sha,
                CONTROL_PLANE_FILES,
            )
            != control_authority
        ):
            raise ContractError("control-plane target authority changed during assembly")
        verify_release_bundle(
            temporary,
            expected_repository=args.repository,
            expected_workflow_ref=args.workflow_ref,
            expected_run_id=int(args.run_id),
            expected_run_attempt=int(args.run_attempt),
            expected_target_sha=target_sha,
        )
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("--source", required=True)
    pack.add_argument("--archive", required=True)
    pack.set_defaults(handler=command_pack)
    backend = commands.add_parser("backend-attestation")
    backend.add_argument("--archive", required=True)
    backend.add_argument("--output", required=True)
    backend.add_argument("--target-sha", required=True)
    backend.add_argument("--requirements-lock", required=True)
    backend.add_argument("--requirements-dev-lock", required=True)
    backend.add_argument("--runtime-executable", required=True)
    backend.add_argument("--runtime-archive", required=True)
    backend.add_argument("--pip-version", required=True)
    backend.set_defaults(handler=command_backend)
    frontend = commands.add_parser("frontend-attestation")
    frontend.add_argument("--archive", required=True)
    frontend.add_argument("--output", required=True)
    frontend.add_argument("--target-sha", required=True)
    frontend.add_argument("--package-lock", required=True)
    frontend.add_argument("--node-version", required=True)
    frontend.add_argument("--npm-version", required=True)
    frontend.set_defaults(handler=command_frontend)
    assemble = commands.add_parser("assemble")
    for name in (
        "backend-dir",
        "frontend-dir",
        "repository-root",
        "repository",
        "workflow-ref",
        "target-sha",
        "requirements-lock",
        "requirements-dev-lock",
        "package-lock",
        "output-dir",
    ):
        assemble.add_argument(f"--{name}", required=True)
    assemble.add_argument("--run-id", required=True, type=_positive_decimal)
    assemble.add_argument("--run-attempt", required=True, type=_positive_decimal)
    assemble.set_defaults(handler=command_assemble)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        args.handler(args)
    except (ContractError, OSError, ValueError) as exc:
        print(f"[release-artifact] blocked={type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
