"""Portable nested-runtime evidence collection (content identity only)."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

SCHEMA = 1
NESTED_RUNTIME_NAME = "linaslaserbot-2.7.22"
READ_CHUNK = 1024 * 1024
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


class NestedRuntimeQuarantineError(RuntimeError):
    """Fixed-message failure; member paths and secrets are never echoed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _digest_bytes(_canonical(value))


def portable_content_identity(evidence: dict[str, Any]) -> dict[str, Any]:
    return {key: evidence[key] for key in _CONTENT_KEYS}


def _safe_symlink_target(root: Path, path: Path) -> str:
    try:
        target = os.readlink(path)
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    if target.startswith("/"):
        raise NestedRuntimeQuarantineError("nested runtime symlink is not relocatable")
    try:
        (path.parent / target).resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise NestedRuntimeQuarantineError("nested runtime symlink escapes its root") from exc
    return target


def _hash_regular_file(path: Path, expected_size: int) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    hasher = hashlib.sha256()
    remaining = expected_size
    try:
        before = os.fstat(descriptor)
        if before.st_size != expected_size:
            raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
        while remaining > 0:
            chunk = os.read(descriptor, min(READ_CHUNK, remaining))
            if not chunk:
                break
            hasher.update(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if after.st_ino != before.st_ino or after.st_dev != before.st_dev or after.st_size != expected_size:
            raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    finally:
        os.close(descriptor)
    if remaining != 0:
        raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
    return hasher.hexdigest()


def collect_present(root: Path) -> dict[str, Any]:
    if root.is_symlink():
        raise NestedRuntimeQuarantineError("nested runtime root is a symlink")
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode):
        raise NestedRuntimeQuarantineError("nested runtime root is not a directory")
    if os.path.ismount(root):
        raise NestedRuntimeQuarantineError("nested runtime root is a mount point")
    root_dev = root_info.st_dev
    member_digests: list[str] = []
    file_count = 0
    symlink_count = 0
    directory_count = 0
    total_bytes = 0
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory = Path(current)
        if directory != root and os.path.ismount(directory):
            raise NestedRuntimeQuarantineError("nested runtime tree contains a mount point")
        dir_info = directory.lstat()
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
            info = path.lstat()
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
                                "target": _safe_symlink_target(root, path),
                            }
                        )
                    )
                )
                dirnames.remove(name)
            elif not stat.S_ISDIR(info.st_mode):
                raise NestedRuntimeQuarantineError("nested runtime tree contains a special file")
        for name in sorted(filenames):
            path = directory / name
            info = path.lstat()
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
                                "target": _safe_symlink_target(root, path),
                            }
                        )
                    )
                )
                continue
            if not stat.S_ISREG(info.st_mode):
                raise NestedRuntimeQuarantineError("nested runtime tree contains a special file")
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
                            "sha256": _hash_regular_file(path, info.st_size),
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
