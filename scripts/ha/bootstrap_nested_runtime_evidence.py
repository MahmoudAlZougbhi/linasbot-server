"""Portable nested-runtime evidence collection (content identity only)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
from pathlib import Path
from typing import Any

_loader_path = Path(__file__).with_name("bootstrap_nested_runtime_loader.py")
_loader_spec = importlib.util.spec_from_file_location(
    f"bootstrap_nested_runtime_loader@{hashlib.sha256(str(_loader_path.resolve()).encode()).hexdigest()}",
    _loader_path,
)
if _loader_spec is None or _loader_spec.loader is None:
    raise RuntimeError("nested runtime loader module is missing")
_loader = importlib.util.module_from_spec(_loader_spec)
_loader_spec.loader.exec_module(_loader)

_safety = _loader.load_authenticated_module(
    "bootstrap_nested_runtime_safety",
    Path(__file__).with_name("bootstrap_nested_runtime_safety.py"),
)

NestedRuntimeQuarantineError = _safety.NestedRuntimeQuarantineError
member_lstat = _safety.member_lstat
opaque_symlink_target = _safety.opaque_symlink_target
hash_regular_file = _safety.hash_regular_file
prepare_mount_context = _safety.prepare_mount_context
iter_tree_members = _safety.iter_tree_members
TreeEnumerateState = _safety.TreeEnumerateState

SCHEMA = 1
NESTED_RUNTIME_NAME = "linaslaserbot-2.7.22"
MAX_FILE_COUNT = 500_000
MAX_SYMLINK_COUNT = 100_000
MAX_DIRECTORY_COUNT = 100_000
MAX_TOTAL_BYTES = 50 * 1024**3
_CONTENT_KEYS = (
    "schema",
    "present",
    "file_count",
    "symlink_count",
    "directory_count",
    "total_bytes",
    "aggregate_sha256",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _digest_bytes(_canonical(value))


def portable_content_identity(evidence: dict[str, Any]) -> dict[str, Any]:
    if evidence.get("present") is False:
        return {
            "schema": SCHEMA,
            "present": False,
            "file_count": 0,
            "symlink_count": 0,
            "directory_count": 0,
            "total_bytes": 0,
            "aggregate_sha256": _digest_bytes(_canonical([])),
        }
    return {key: evidence[key] for key in _CONTENT_KEYS}


def collect_present(root: Path) -> dict[str, Any]:
    if root.is_symlink():
        raise NestedRuntimeQuarantineError("nested runtime root is a symlink")
    mount_context = prepare_mount_context(root)
    root_info = member_lstat(root)
    if not stat.S_ISDIR(root_info.st_mode):
        raise NestedRuntimeQuarantineError("nested runtime root is not a directory")
    root_dev = root_info.st_dev
    counters = TreeEnumerateState(
        max_files=MAX_FILE_COUNT,
        max_symlinks=MAX_SYMLINK_COUNT,
        max_directories=MAX_DIRECTORY_COUNT,
        max_total_bytes=MAX_TOTAL_BYTES,
    )
    member_digests: list[str] = []
    for kind, path, info in iter_tree_members(root, mount_context=mount_context, counters=counters):
        if kind == "directory":
            member_digests.append(
                _digest_bytes(
                    _canonical(
                        {
                            "kind": "directory",
                            "relative": path.relative_to(root).as_posix(),
                            "mode": stat.S_IMODE(info.st_mode),
                            "uid": info.st_uid,
                            "gid": info.st_gid,
                        }
                    )
                )
            )
            continue
        if kind == "symlink":
            member_digests.append(
                _digest_bytes(
                    _canonical(
                        {
                            "kind": "symlink",
                            "relative": path.relative_to(root).as_posix(),
                            "target": opaque_symlink_target(path),
                        }
                    )
                )
            )
            continue
        if info.st_nlink != 1:
            raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
        member_digests.append(
            _digest_bytes(
                _canonical(
                    {
                        "kind": "file",
                        "relative": path.relative_to(root).as_posix(),
                        "sha256": hash_regular_file(path, info),
                        "size": info.st_size,
                        "mode": stat.S_IMODE(info.st_mode),
                        "uid": info.st_uid,
                        "gid": info.st_gid,
                    }
                )
            )
        )
    return {
        "schema": SCHEMA,
        "present": True,
        "file_count": counters.file_count,
        "symlink_count": counters.symlink_count,
        "directory_count": counters.directory_count,
        "total_bytes": counters.total_bytes,
        "root_dev": root_dev,
        "root_ino": root_info.st_ino,
        "root_uid": root_info.st_uid,
        "root_gid": root_info.st_gid,
        "root_mode": stat.S_IMODE(root_info.st_mode),
        "mount_namespace_sha256": mount_context.namespace_sha256,
        "aggregate_sha256": _digest_bytes(_canonical(sorted(member_digests))),
    }


def assert_content_matches(root: Path, expected: dict[str, Any]) -> None:
    observed = collect_present(root)
    if portable_content_identity(observed) != portable_content_identity(expected):
        raise NestedRuntimeQuarantineError("nested runtime evidence changed")


def nested_runtime_path(repo_dir: Path) -> Path:
    return repo_dir / NESTED_RUNTIME_NAME
