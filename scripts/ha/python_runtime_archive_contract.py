#!/usr/bin/env python3
"""OS-verifiable safe extraction and pristine-tree contract for portable CPython."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat
import subprocess
import tarfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Final

RUNTIME_NAME: Final = "cpython-3.13.15+20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
RUNTIME_SHA256: Final = "aaca2af2ab4d7b68a712660d1334c0cfd5ec13c0312ccd30c29122d8d0342320"
RUNTIME_TREE_SHA256: Final = "e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc"
PYTHON_SHA256: Final = "ce20f82411f2b0ccdf3e2212ca62303519521d73d25178588f1a9c8d4935c866"
LIBPYTHON_SHA256: Final = "965dcc1afd5934923b5a930e54afcaafc572485394ae33c35d27038bd943dcc5"
PIP_VERSION: Final = "26.2.1"
MAX_ARCHIVE_BYTES: Final = 256 * 1024**2
MAX_MEMBER_BYTES: Final = 2 * 1024**3
MAX_TOTAL_BYTES: Final = 4 * 1024**3
MAX_MEMBERS: Final = 100_000
EXPECTED_UID = 0
EXPECTED_GID = 0


class ProvisionError(RuntimeError):
    """Runtime artifact or durable state cannot be authenticated safely."""


def write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written < 1:
            raise ProvisionError("durable runtime write made no progress")
        remaining = remaining[written:]


@contextmanager
def open_regular(
    path: Path,
    *,
    max_bytes: int,
    min_bytes: int = 1,
) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    if not 0 <= min_bytes <= max_bytes:
        raise ProvisionError("authenticated file size bounds are invalid")
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != EXPECTED_UID
            or before.st_gid != EXPECTED_GID
            or before.st_nlink != 1
            or before.st_size < min_bytes
            or before.st_size > max_bytes
        ):
            raise ProvisionError(f"unsafe root-owned regular file: {path}")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        handle = os.fdopen(descriptor, "rb")
    except OSError as exc:
        raise ProvisionError(f"could not open authenticated file: {path}") from exc
    try:
        opened = os.fstat(handle.fileno())
        identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        if any(getattr(before, key) != getattr(opened, key) for key in identity):
            raise ProvisionError("authenticated file changed while opening")
        yield handle, opened
        after = os.fstat(handle.fileno())
        if any(getattr(opened, key) != getattr(after, key) for key in identity):
            raise ProvisionError("authenticated file changed while reading")
    finally:
        handle.close()


def read_regular(path: Path, *, max_bytes: int) -> bytes:
    with open_regular(path, max_bytes=max_bytes) as (handle, before):
        payload = handle.read(max_bytes + 1)
        if len(payload) != before.st_size or len(payload) > max_bytes:
            raise ProvisionError("authenticated file size changed while reading")
        return payload


def file_evidence(path: Path, *, max_bytes: int, min_bytes: int = 1) -> tuple[str, int]:
    digest = hashlib.sha256()
    with open_regular(path, max_bytes=max_bytes, min_bytes=min_bytes) as (handle, before):
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest(), before.st_size


def secure_directory(path: Path, *, mode: int, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, mode=mode, exist_ok=True)
        os.chmod(path, mode, follow_symlinks=False)
        os.chown(path, EXPECTED_UID, EXPECTED_GID, follow_symlinks=False)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != EXPECTED_UID
        or info.st_gid != EXPECTED_GID
        or stat.S_IMODE(info.st_mode) != mode
    ):
        raise ProvisionError(f"unsafe runtime directory: {path}")


def fsync_directory(path: Path) -> None:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != EXPECTED_UID
        or info.st_gid != EXPECTED_GID
    ):
        raise ProvisionError(f"unsafe durable directory: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ProvisionError("durable directory changed while opening")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def rename_durable(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ProvisionError(f"durable rename destination exists: {destination}")
    if source.parent != destination.parent:
        raise ProvisionError("runtime rename must remain on one filesystem and parent")
    fsync_directory(source.parent)
    os.rename(source, destination)
    fsync_directory(destination.parent)


def _safe_name(name: str) -> str:
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or len(name.encode("utf-8", "strict")) > 4096
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ProvisionError("runtime archive contains an unsafe path")
    parts = name.rstrip("/").split("/")
    if any(part in {"", ".", ".."} for part in parts) or str(PurePosixPath(*parts)) != "/".join(parts):
        raise ProvisionError("runtime archive path is not canonical")
    canonical = "/".join(parts)
    if canonical != "python" and not canonical.startswith("python/"):
        raise ProvisionError("runtime archive escapes its fixed top-level root")
    return canonical


def _safe_link(member_name: str, target: str) -> str:
    if (
        not target
        or target.startswith("/")
        or "\\" in target
        or any(ord(character) < 32 or ord(character) == 127 for character in target)
    ):
        raise ProvisionError("runtime archive symlink target is unsafe")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(member_name), target))
    if resolved != "python" and not resolved.startswith("python/"):
        raise ProvisionError("runtime archive symlink escapes its root")
    return target


def _members(bundle: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    kinds: dict[str, str] = {}
    total = 0
    for member in bundle:
        name = _safe_name(member.name)
        if name in kinds:
            raise ProvisionError("runtime archive contains duplicate members")
        if member.islnk() or member.ischr() or member.isblk() or member.isfifo() or member.isdev():
            raise ProvisionError("runtime archive contains a hardlink or device")
        if member.isdir():
            kind = "directory"
            if member.size:
                raise ProvisionError("runtime directory member has content")
        elif member.isfile():
            kind = "file"
            if not 0 <= member.size <= MAX_MEMBER_BYTES:
                raise ProvisionError("runtime member exceeds its size bound")
            total += member.size
        elif member.issym():
            kind = "symlink"
            _safe_link(name, member.linkname)
        else:
            raise ProvisionError("runtime archive contains an unsupported object")
        if member.uid != 0 or member.gid != 0 or member.mtime < 0 or member.mode & ~0o7777:
            raise ProvisionError("runtime member metadata is invalid")
        kinds[name] = kind
        members.append(member)
        if len(members) > MAX_MEMBERS or total > MAX_TOTAL_BYTES:
            raise ProvisionError("runtime archive exceeds reviewed resource bounds")
    if not members:
        raise ProvisionError("runtime archive is empty")
    if kinds.get("python") not in {None, "directory"}:
        raise ProvisionError("runtime archive fixed root is not a directory")
    for name in kinds:
        parent = posixpath.dirname(name)
        while parent and parent != "python":
            if kinds.get(parent, "directory") != "directory":
                raise ProvisionError("runtime archive places a member beneath a link or file")
            parent = posixpath.dirname(parent)
    return members


def verify_runtime_archive_layout(path: Path) -> tuple[int, int]:
    """Validate the provider archive layout without claiming root-owned file authority."""

    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_ARCHIVE_BYTES
        ):
            raise ProvisionError("runtime archive layout input is unsafe")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        with os.fdopen(descriptor, "rb") as raw:
            opened = os.fstat(raw.fileno())
            identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
            if any(getattr(before, key) != getattr(opened, key) for key in identity):
                raise ProvisionError("runtime archive changed while opening")
            with tarfile.open(fileobj=raw, mode="r:gz") as bundle:
                members = _members(bundle)
            after = os.fstat(raw.fileno())
            if any(getattr(opened, key) != getattr(after, key) for key in identity):
                raise ProvisionError("runtime archive changed while inspecting")
    except (OSError, tarfile.TarError) as exc:
        raise ProvisionError("runtime archive layout cannot be inspected") from exc
    return len(members), sum(member.size for member in members if member.isfile())


def _mode(member: tarfile.TarInfo) -> int:
    normalized = stat.S_IMODE(member.mode) & ~0o022
    if member.isdir():
        return normalized or 0o755
    if member.isfile():
        return normalized or 0o644
    return 0o777


def _open_parent(root_fd: int, parts: tuple[str, ...]) -> int:
    descriptor = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_fd
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _normalize_directory(descriptor: int, *, mode: int) -> None:
    """Set and read back exact metadata on a newly controlled directory."""

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISDIR(before.st_mode):
            raise ProvisionError("runtime extraction directory is not a directory")
        os.fchown(descriptor, EXPECTED_UID, EXPECTED_GID)
        os.fchmod(descriptor, mode)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise ProvisionError("runtime extraction directory metadata cannot be secured") from exc
    if (
        (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or not stat.S_ISDIR(after.st_mode)
        or after.st_uid != EXPECTED_UID
        or after.st_gid != EXPECTED_GID
        or stat.S_IMODE(after.st_mode) != mode
    ):
        raise ProvisionError("runtime extraction directory metadata is unsafe")


def extract_runtime_archive(
    archive: Path,
    destination: Path,
    *,
    boundary: Callable[[str], None] = lambda _name: None,
) -> None:
    if file_evidence(archive, max_bytes=MAX_ARCHIVE_BYTES)[0] != RUNTIME_SHA256:
        raise ProvisionError("runtime archive differs from the reviewed QG payload")
    if destination.exists() or destination.is_symlink():
        raise ProvisionError("runtime extraction destination already exists")
    secure_directory(destination.parent, mode=0o755)
    temporary = destination.parent / f".{destination.name}.extracting"
    if temporary.exists() or temporary.is_symlink():
        raise ProvisionError("interrupted runtime extraction requires recovery")
    temporary.mkdir(mode=0o755)
    root_fd = os.open(temporary, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        _normalize_directory(root_fd, mode=0o755)
        directories: set[tuple[str, ...]] = {()}
        with open_regular(archive, max_bytes=MAX_ARCHIVE_BYTES) as (raw, _before):
            with tarfile.open(fileobj=raw, mode="r:gz") as bundle:
                for member in _members(bundle):
                    name = _safe_name(member.name)
                    relative = name.removeprefix("python/") if name != "python" else ""
                    if not relative:
                        continue
                    parts = tuple(relative.split("/"))
                    for length in range(1, len(parts)):
                        parent_parts = parts[:length]
                        if parent_parts in directories:
                            continue
                        parent_fd = _open_parent(root_fd, parent_parts[:-1])
                        try:
                            try:
                                os.mkdir(parent_parts[-1], 0o755, dir_fd=parent_fd)
                            except FileExistsError as exc:
                                raise ProvisionError("runtime implicit directory already exists") from exc
                            implicit_fd = os.open(
                                parent_parts[-1],
                                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                                dir_fd=parent_fd,
                            )
                            try:
                                _normalize_directory(implicit_fd, mode=0o755)
                            finally:
                                os.close(implicit_fd)
                        finally:
                            os.close(parent_fd)
                        directories.add(parent_parts)
                    parent_fd = _open_parent(root_fd, parts[:-1])
                    try:
                        leaf = parts[-1]
                        mode = _mode(member)
                        if member.isdir():
                            try:
                                os.mkdir(leaf, mode, dir_fd=parent_fd)
                            except FileExistsError:
                                pass
                            os.chown(leaf, EXPECTED_UID, EXPECTED_GID, dir_fd=parent_fd, follow_symlinks=False)
                            os.chmod(leaf, mode, dir_fd=parent_fd, follow_symlinks=False)
                            directories.add(parts)
                        elif member.isfile():
                            source = bundle.extractfile(member)
                            if source is None:
                                raise ProvisionError("runtime archive member cannot be read")
                            descriptor = os.open(
                                leaf,
                                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                                mode,
                                dir_fd=parent_fd,
                            )
                            consumed = 0
                            try:
                                os.fchmod(descriptor, mode)
                                os.fchown(descriptor, EXPECTED_UID, EXPECTED_GID)
                                while True:
                                    chunk = source.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    consumed += len(chunk)
                                    write_all(descriptor, chunk)
                                if consumed != member.size:
                                    raise ProvisionError("runtime archive member changed while extracting")
                                os.fsync(descriptor)
                            finally:
                                os.close(descriptor)
                        else:
                            os.symlink(_safe_link(name, member.linkname), leaf, dir_fd=parent_fd)
                            os.chown(leaf, EXPECTED_UID, EXPECTED_GID, dir_fd=parent_fd, follow_symlinks=False)
                    finally:
                        os.close(parent_fd)
        for parts in sorted(directories, key=len, reverse=True):
            descriptor = _open_parent(root_fd, parts)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    fsync_directory(temporary)
    boundary("before_candidate_rename")
    rename_durable(temporary, destination)
    boundary("after_candidate_rename")


def runtime_tree_evidence(root: Path) -> tuple[str, int]:
    root_info = root.lstat()
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or stat.S_ISLNK(root_info.st_mode)
        or root_info.st_uid != EXPECTED_UID
        or root_info.st_gid != EXPECTED_GID
        or stat.S_IMODE(root_info.st_mode) != 0o755
    ):
        raise ProvisionError("runtime root is unsafe")
    digest = hashlib.sha256()
    count = 1

    def update(record: Mapping[str, object]) -> None:
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big") + encoded)

    update({"path": ".", "type": "directory", "mode": 0o755})
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in [*dirnames, *filenames]:
            path = current_path / name
            info = path.lstat()
            if info.st_uid != EXPECTED_UID or info.st_gid != EXPECTED_GID:
                raise ProvisionError("runtime tree ownership is unsafe")
            record: dict[str, object] = {
                "path": path.relative_to(root).as_posix(),
                "mode": stat.S_IMODE(info.st_mode),
            }
            if stat.S_ISLNK(info.st_mode):
                try:
                    path.resolve(strict=True).relative_to(root)
                except (OSError, ValueError) as exc:
                    raise ProvisionError("runtime symlink escapes the immutable root") from exc
                record.update({"type": "symlink", "target": os.readlink(path)})
            elif stat.S_ISDIR(info.st_mode):
                if stat.S_IMODE(info.st_mode) & 0o022:
                    raise ProvisionError("runtime directory is group/world writable")
                record["type"] = "directory"
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if stat.S_IMODE(info.st_mode) & 0o022:
                    raise ProvisionError("runtime file is group/world writable")
                file_sha, size = file_evidence(path, max_bytes=MAX_MEMBER_BYTES, min_bytes=0)
                record.update({"type": "file", "size": size, "sha256": file_sha})
            else:
                raise ProvisionError("runtime tree contains a hardlink or special object")
            update(record)
            count += 1
            if count > MAX_MEMBERS:
                raise ProvisionError("runtime tree exceeds the member bound")
    return digest.hexdigest(), count


def verify_runtime_before_use(root: Path, *, execute_self_check: bool = True) -> tuple[str, int]:
    tree_before, count_before = runtime_tree_evidence(root)
    if tree_before != RUNTIME_TREE_SHA256:
        raise ProvisionError("runtime tree differs from the pristine reviewed artifact")
    executable = root / "bin/python3.13"
    libpython = root / "lib/libpython3.13.so.1.0"
    if file_evidence(executable, max_bytes=64 * 1024**2)[0] != PYTHON_SHA256:
        raise ProvisionError("runtime executable differs from the reviewed artifact")
    if file_evidence(libpython, max_bytes=64 * 1024**2)[0] != LIBPYTHON_SHA256:
        raise ProvisionError("runtime libpython differs from the reviewed artifact")
    metadata = list(root.glob(f"lib/python3.13/site-packages/pip-{PIP_VERSION}.dist-info/METADATA"))
    if len(metadata) != 1 or f"\nVersion: {PIP_VERSION}\n" not in (
        "\n" + read_regular(metadata[0], max_bytes=4 * 1024**2).decode("utf-8", "strict")
    ):
        raise ProvisionError("runtime pip metadata is invalid")
    if execute_self_check:
        check = (
            "import os,platform,sys,sysconfig;"
            "assert platform.python_version()=='3.13.15';"
            "assert sys.implementation.name=='cpython';"
            "assert sys.implementation.cache_tag=='cpython-313';"
            "assert sysconfig.get_config_var('SOABI')=='cpython-313-x86_64-linux-gnu';"
            "assert sys.platform=='linux' and os.uname().machine=='x86_64'"
        )
        result = subprocess.run(
            [str(executable), "-B", "-I", "-S", "-c", check],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"HOME": "/nonexistent", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            check=False,
            timeout=30,
        )
        if result.returncode:
            raise ProvisionError("runtime ABI self-check failed")
        if runtime_tree_evidence(root) != (tree_before, count_before):
            raise ProvisionError("runtime self-check mutated the pristine tree")
    return tree_before, count_before
