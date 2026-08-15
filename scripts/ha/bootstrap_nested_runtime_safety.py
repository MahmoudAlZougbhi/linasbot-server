"""Redacted fail-closed OS helpers for nested-runtime quarantine."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

READ_CHUNK = 1024 * 1024
MAX_SYMLINK_CHAIN = 40
MAX_AUTHORITY_BYTES = 1024 * 1024
AUTHORITY_TEMP_SUFFIX = ".authority."
SECURE_AUTHORITY_MODE = 0o600
SECURE_AUTHORITY_OWNER = (0, 0)
AUTHORITY_KEYS = frozenset({"schema", "tx_id", "evidence", "quarantine_name", "evidence_sha256"})


class NestedRuntimeQuarantineError(RuntimeError):
    """Fixed-message failure; member paths and secrets are never echoed."""


def member_lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc


def walk_fail_closed(_err: OSError) -> None:
    raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from _err


def is_mount_safe(path: Path) -> bool:
    try:
        return os.path.ismount(path)
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc


def authority_temp_prefix(authority_name: str) -> str:
    return f".{authority_name}{AUTHORITY_TEMP_SUFFIX}"


def is_known_authority_temp(path: Path, authority_name: str) -> bool:
    return path.name.startswith(authority_temp_prefix(authority_name))


def safe_symlink_target(root: Path, path: Path) -> str:
    try:
        target = os.readlink(path)
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    if target.startswith("/"):
        raise NestedRuntimeQuarantineError("nested runtime symlink is not relocatable")
    _assert_symlink_resolves_under_root(root, path)
    return target


def _assert_symlink_resolves_under_root(root: Path, link: Path) -> None:
    root_real = root.resolve()
    seen: set[tuple[int, int]] = set()
    current = link
    for _ in range(MAX_SYMLINK_CHAIN):
        info = member_lstat(current)
        if not stat.S_ISLNK(info.st_mode):
            try:
                current.resolve(strict=False).relative_to(root_real)
            except ValueError as exc:
                raise NestedRuntimeQuarantineError("nested runtime symlink escapes its root") from exc
            return
        identity = (info.st_dev, info.st_ino)
        if identity in seen:
            raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
        seen.add(identity)
        target = os.readlink(current)
        if target.startswith("/"):
            raise NestedRuntimeQuarantineError("nested runtime symlink is not relocatable")
        current = current.parent / target
    raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")


def hash_regular_file(path: Path, path_info: os.stat_result) -> str:
    if not stat.S_ISREG(path_info.st_mode) or stat.S_ISLNK(path_info.st_mode):
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
    if path_info.st_nlink != 1:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    hasher = hashlib.sha256()
    expected_size = path_info.st_size
    try:
        opened = os.fstat(descriptor)
        if not _same_file_identity(path_info, opened):
            raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
        if opened.st_size != expected_size:
            raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
        remaining = expected_size
        while remaining > 0:
            chunk = os.read(descriptor, min(READ_CHUNK, remaining))
            if not chunk:
                break
            hasher.update(chunk)
            remaining -= len(chunk)
        after_fd = os.fstat(descriptor)
        if (after_fd.st_dev, after_fd.st_ino, after_fd.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
        after_path = member_lstat(path)
        if (
            after_path.st_dev,
            after_path.st_ino,
            after_path.st_size,
            after_path.st_mtime_ns,
        ) != (
            path_info.st_dev,
            path_info.st_ino,
            expected_size,
            path_info.st_mtime_ns,
        ):
            raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    finally:
        os.close(descriptor)
    if remaining != 0:
        raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
    return hasher.hexdigest()


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
        and stat.S_IMODE(left.st_mode) == stat.S_IMODE(right.st_mode)
        and left.st_uid == right.st_uid
        and left.st_gid == right.st_gid
    )


def read_authority_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
    before = member_lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != SECURE_AUTHORITY_OWNER[0]
        or before.st_gid != SECURE_AUTHORITY_OWNER[1]
        or stat.S_IMODE(before.st_mode) != SECURE_AUTHORITY_MODE
        or before.st_nlink != 1
        or not 1 <= before.st_size <= MAX_AUTHORITY_BYTES
    ):
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid") from exc
    chunks: list[bytes] = []
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
        consumed = 0
        while consumed < opened.st_size:
            chunk = os.read(descriptor, min(READ_CHUNK, opened.st_size - consumed))
            if not chunk:
                raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
            chunks.append(chunk)
            consumed += len(chunk)
        after_fd = os.fstat(descriptor)
        if (after_fd.st_dev, after_fd.st_ino, after_fd.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
        after_path = member_lstat(path)
        if (after_path.st_dev, after_path.st_ino, after_path.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid") from exc
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def fsync_path(path: Path) -> None:
    info = member_lstat(path)
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError as exc:
            raise NestedRuntimeQuarantineError("nested runtime authority write failed") from exc
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        raise NestedRuntimeQuarantineError("nested runtime authority write failed")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime authority write failed") from exc
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
