"""Portable nested-runtime evidence collection (content identity only)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from typing import Any

_safety_spec = importlib.util.spec_from_file_location(
    "bootstrap_nested_runtime_safety",
    Path(__file__).with_name("bootstrap_nested_runtime_safety.py"),
)
if _safety_spec is None or _safety_spec.loader is None:
    raise RuntimeError("nested runtime safety module is missing")
_safety = importlib.util.module_from_spec(_safety_spec)
_safety_spec.loader.exec_module(_safety)

NestedRuntimeQuarantineError = _safety.NestedRuntimeQuarantineError
member_lstat = _safety.member_lstat
walk_fail_closed = _safety.walk_fail_closed
is_mount_safe = _safety.is_mount_safe
safe_symlink_target = _safety.safe_symlink_target
hash_regular_file = _safety.hash_regular_file

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
    root_info = member_lstat(root)
    if not stat.S_ISDIR(root_info.st_mode):
        raise NestedRuntimeQuarantineError("nested runtime root is not a directory")
    if is_mount_safe(root):
        raise NestedRuntimeQuarantineError("nested runtime root is a mount point")
    root_dev = root_info.st_dev
    member_digests: list[str] = []
    file_count = 0
    symlink_count = 0
    directory_count = 0
    total_bytes = 0
    for current, dirnames, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=walk_fail_closed,
    ):
        directory = Path(current)
        if directory != root and is_mount_safe(directory):
            raise NestedRuntimeQuarantineError("nested runtime tree contains a mount point")
        dir_info = member_lstat(directory)
        if dir_info.st_dev != root_dev:
            raise NestedRuntimeQuarantineError("nested runtime tree crosses devices")
        if directory != root:
            directory_count += 1
            if directory_count > MAX_DIRECTORY_COUNT:
                raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")
            member_digests.append(
                _digest_bytes(
                    _canonical(
                        {
                            "kind": "directory",
                            "relative": directory.relative_to(root).as_posix(),
                            "mode": stat.S_IMODE(dir_info.st_mode),
                            "uid": dir_info.st_uid,
                            "gid": dir_info.st_gid,
                        }
                    )
                )
            )
        dirnames[:] = sorted(name for name in dirnames if name not in {".", ".."})
        for name in sorted(dirnames):
            path = directory / name
            info = member_lstat(path)
            if info.st_dev != root_dev:
                raise NestedRuntimeQuarantineError("nested runtime tree crosses devices")
            if stat.S_ISLNK(info.st_mode):
                symlink_count += 1
                if symlink_count > MAX_SYMLINK_COUNT:
                    raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")
                member_digests.append(
                    _digest_bytes(
                        _canonical(
                            {
                                "kind": "symlink",
                                "relative": path.relative_to(root).as_posix(),
                                "target": safe_symlink_target(root, path),
                            }
                        )
                    )
                )
                dirnames.remove(name)
            elif not stat.S_ISDIR(info.st_mode):
                raise NestedRuntimeQuarantineError("nested runtime tree contains a special file")
        for name in sorted(filenames):
            path = directory / name
            info = member_lstat(path)
            if info.st_dev != root_dev:
                raise NestedRuntimeQuarantineError("nested runtime tree crosses devices")
            if stat.S_ISLNK(info.st_mode):
                symlink_count += 1
                if symlink_count > MAX_SYMLINK_COUNT:
                    raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")
                member_digests.append(
                    _digest_bytes(
                        _canonical(
                            {
                                "kind": "symlink",
                                "relative": path.relative_to(root).as_posix(),
                                "target": safe_symlink_target(root, path),
                            }
                        )
                    )
                )
                continue
            if not stat.S_ISREG(info.st_mode):
                raise NestedRuntimeQuarantineError("nested runtime tree contains a special file")
            if info.st_nlink != 1:
                raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
            file_count += 1
            total_bytes += info.st_size
            if file_count > MAX_FILE_COUNT or total_bytes > MAX_TOTAL_BYTES:
                raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")
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
        "file_count": file_count,
        "symlink_count": symlink_count,
        "directory_count": directory_count,
        "total_bytes": total_bytes,
        "root_dev": root_dev,
        "root_ino": root_info.st_ino,
        "root_uid": root_info.st_uid,
        "root_gid": root_info.st_gid,
        "root_mode": stat.S_IMODE(root_info.st_mode),
        "aggregate_sha256": _digest_bytes(_canonical(sorted(member_digests))),
    }


def assert_content_matches(root: Path, expected: dict[str, Any]) -> None:
    observed = collect_present(root)
    if portable_content_identity(observed) != portable_content_identity(expected):
        raise NestedRuntimeQuarantineError("nested runtime evidence changed")


def nested_runtime_path(repo_dir: Path) -> Path:
    return repo_dir / NESTED_RUNTIME_NAME
