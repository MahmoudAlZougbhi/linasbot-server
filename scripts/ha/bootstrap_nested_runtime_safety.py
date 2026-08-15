"""Redacted fail-closed OS helpers for nested-runtime quarantine."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_mount_path = Path(__file__).with_name("bootstrap_nested_runtime_mount.py")
_mount_spec = importlib.util.spec_from_file_location("bootstrap_nested_runtime_mount", _mount_path)
if _mount_spec is None or _mount_spec.loader is None:
    raise RuntimeError("nested runtime mount module is missing")
_mount = importlib.util.module_from_spec(_mount_spec)
_mount_spec.loader.exec_module(_mount)

READ_CHUNK = 1024 * 1024
MAX_SYMLINK_TARGET_BYTES = 4096
MAX_CHILDREN_PER_DIRECTORY = 100_000
MAX_AUTHORITY_BYTES = 1024 * 1024
AUTHORITY_TEMP_SUFFIX = ".authority."
SECURE_AUTHORITY_MODE = 0o600
SECURE_AUTHORITY_OWNER = (0, 0)
AUTHORITY_KEYS = frozenset({"schema", "tx_id", "evidence", "quarantine_name", "evidence_sha256"})
TreeMemberKind = Literal["directory", "file", "symlink"]
NestedRuntimeQuarantineError = _mount.NestedRuntimeQuarantineError


def read_mountinfo_text(path: Path | None = None) -> str:
    result: str = _mount.read_mountinfo_text(path)
    return result


def prepare_mount_context(tree_root: Path, mountinfo_text: str | None = None) -> Any:
    text = (
        read_mountinfo_text()
        if mountinfo_text is None
        else _mount._validated_mountinfo_text(mountinfo_text.encode("utf-8"))
    )
    boundaries = _mount._collect_mount_boundaries(tree_root, text)
    if boundaries:
        raise NestedRuntimeQuarantineError("nested runtime tree contains a mount point")
    return _mount.MountContext(namespace_sha256=_mount.mount_namespace_sha256(boundaries))


def verify_mount_context(tree_root: Path, expected_sha256: str, mountinfo_text: str | None = None) -> None:
    context = prepare_mount_context(tree_root, mountinfo_text)
    if context.namespace_sha256 != expected_sha256:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace changed")


def member_lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from None


def walk_fail_closed(_err: OSError) -> None:
    raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from None


@dataclass
class TreeEnumerateState:
    file_count: int = 0
    symlink_count: int = 0
    directory_count: int = 0
    total_bytes: int = 0
    max_files: int = 500_000
    max_symlinks: int = 100_000
    max_directories: int = 100_000
    max_total_bytes: int = 50 * 1024**3
    max_children_per_directory: int = MAX_CHILDREN_PER_DIRECTORY

    def note_directory(self) -> None:
        self.directory_count += 1
        if self.directory_count > self.max_directories:
            raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")

    def note_symlink(self) -> None:
        self.symlink_count += 1
        if self.symlink_count > self.max_symlinks:
            raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")

    def note_file(self, size: int) -> None:
        self.file_count += 1
        self.total_bytes += size
        if self.file_count > self.max_files or self.total_bytes > self.max_total_bytes:
            raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")


def _open_dir_nofollow(*, name: str | None = None, path: Path | None = None, dir_fd: int | None = None) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        if dir_fd is None:
            if path is None:
                raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
            return os.open(path, flags)
        if name is None:
            raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from None


def _stat_at(name: str, dir_fd: int) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from None


def iter_tree_members(
    root: Path,
    *,
    mount_context: Any | None = None,
    counters: TreeEnumerateState | None = None,
) -> Iterator[tuple[TreeMemberKind, Path, os.stat_result]]:
    """Top-down dir-fd traversal with bounded per-directory enumeration."""
    if mount_context is None:
        mount_context = prepare_mount_context(root)
    state = counters or TreeEnumerateState()
    root_fd = _open_dir_nofollow(path=root)
    root_info = os.fstat(root_fd)
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        os.close(root_fd)
        raise NestedRuntimeQuarantineError("nested runtime root is not a directory")
    root_dev = root_info.st_dev
    stack: list[tuple[int, Path, os.stat_result]] = [(root_fd, root, root_info)]
    try:
        while stack:
            dir_fd, directory, dir_info = stack.pop()
            if dir_info.st_dev != root_dev:
                raise NestedRuntimeQuarantineError("nested runtime tree crosses devices")
            if directory != root:
                state.note_directory()
                yield "directory", directory, dir_info
            pre_scan = os.fstat(dir_fd)
            if (pre_scan.st_dev, pre_scan.st_ino) != (dir_info.st_dev, dir_info.st_ino):
                raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
            if not stat.S_ISDIR(pre_scan.st_mode) or stat.S_ISLNK(pre_scan.st_mode):
                raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
            try:
                child_names = os.listdir(dir_fd)
            except OSError as exc:
                walk_fail_closed(exc)
            if len(child_names) > state.max_children_per_directory:
                raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")
            post_scan = os.fstat(dir_fd)
            if (post_scan.st_dev, post_scan.st_ino) != (pre_scan.st_dev, pre_scan.st_ino):
                raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
            subdirs_to_visit: list[tuple[int, Path, os.stat_result]] = []
            for name in sorted(child_names):
                if name in {".", ".."}:
                    continue
                info = _stat_at(name, dir_fd)
                path = directory / name
                if info.st_dev != root_dev:
                    raise NestedRuntimeQuarantineError("nested runtime tree crosses devices")
                if stat.S_ISLNK(info.st_mode):
                    state.note_symlink()
                    yield "symlink", path, info
                elif stat.S_ISDIR(info.st_mode):
                    child_fd = _open_dir_nofollow(name=name, dir_fd=dir_fd)
                    opened = os.fstat(child_fd)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        os.close(child_fd)
                        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
                    subdirs_to_visit.append((child_fd, path, opened))
                elif stat.S_ISREG(info.st_mode):
                    state.note_file(info.st_size)
                    yield "file", path, info
                else:
                    raise NestedRuntimeQuarantineError("nested runtime tree contains a special file")
            stack.extend(reversed(subdirs_to_visit))
            if directory != root:
                os.close(dir_fd)
    finally:
        os.close(root_fd)


def authority_temp_prefix(authority_name: str) -> str:
    return f".{authority_name}{AUTHORITY_TEMP_SUFFIX}"


def is_known_authority_temp(path: Path, authority_name: str) -> bool:
    return path.name.startswith(authority_temp_prefix(authority_name))


def opaque_symlink_target(path: Path) -> str:
    try:
        target = os.readlink(path)
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from None
    if len(target.encode("utf-8", errors="strict")) > MAX_SYMLINK_TARGET_BYTES:
        raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")
    return target


def hash_regular_file(path: Path, path_info: os.stat_result) -> str:
    if not stat.S_ISREG(path_info.st_mode) or stat.S_ISLNK(path_info.st_mode):
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
    if path_info.st_nlink != 1:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from None
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
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from None
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
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid") from None
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
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid") from None
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _reconcile_authority_temps(path: Path, authority_name: str) -> None:
    prefix = authority_temp_prefix(authority_name)
    for sibling in path.parent.iterdir():
        if not sibling.name.startswith(prefix) or not is_known_authority_temp(sibling, authority_name):
            continue
        try:
            sibling.unlink()
            fsync_path(path.parent)
        except OSError:
            raise NestedRuntimeQuarantineError("nested runtime authority write failed") from None


def atomic_authority_write(path: Path, payload: bytes, *, authority_name: str) -> None:
    if len(payload) > MAX_AUTHORITY_BYTES:
        raise NestedRuntimeQuarantineError("nested runtime authority write failed")
    path.parent.mkdir(parents=True, exist_ok=True)
    _reconcile_authority_temps(path, authority_name)
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise NestedRuntimeQuarantineError("nested runtime authority changed")
        existing = read_authority_bytes(path)
        if existing == payload:
            return
        raise NestedRuntimeQuarantineError("nested runtime authority changed")
    temp_prefix = authority_temp_prefix(authority_name)
    fd, temporary_name = tempfile.mkstemp(prefix=temp_prefix, dir=path.parent)
    temporary = Path(temporary_name)
    if not is_known_authority_temp(temporary, authority_name):
        raise NestedRuntimeQuarantineError("nested runtime authority write failed")
    try:
        os.fchmod(fd, SECURE_AUTHORITY_MODE)
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise NestedRuntimeQuarantineError("nested runtime authority write failed")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = -1
        fsync_path(temporary)
        os.replace(temporary, path)
        fsync_path(path)
        fsync_path(path.parent)
        verify = read_authority_bytes(path)
        if verify != payload:
            raise NestedRuntimeQuarantineError("nested runtime authority readback failed")
        fsync_path(path.parent)
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime authority write failed") from None
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists() and is_known_authority_temp(temporary, authority_name):
            temporary.unlink()


def fsync_path(path: Path) -> None:
    info = member_lstat(path)
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            raise NestedRuntimeQuarantineError("nested runtime authority write failed") from None
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        raise NestedRuntimeQuarantineError("nested runtime authority write failed")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime authority write failed") from None
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
