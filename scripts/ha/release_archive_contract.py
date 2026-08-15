"""Safe deterministic tar and tree-digest primitives for release artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

TREE_DOMAIN = b"linasbot-release-tree-v1\0"
MAX_MEMBERS = 100_000
MAX_MEMBER_SIZE = 2 * 1024**3
MAX_TOTAL_SIZE = 4 * 1024**3


class ContractError(RuntimeError):
    """A release input violates the reviewed artifact contract."""


@dataclass(frozen=True)
class ArchiveEvidence:
    archive_sha256: str
    tree_sha256: str
    file_count: int
    total_size: int


@contextmanager
def _open_regular(path: Path) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("release artifact path is not a regular file")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        handle = os.fdopen(descriptor, "rb")
    except OSError as exc:
        raise ContractError("release artifact file could not be opened safely") from exc
    try:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ContractError("release artifact changed while opening")
        yield handle, opened
    finally:
        handle.close()


def _assert_unchanged(handle: BinaryIO, before: os.stat_result, message: str) -> None:
    after = os.fstat(handle.fileno())
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(after, key) != getattr(before, key) for key in identity):
        raise ContractError(message)


def file_evidence(path: Path, *, max_bytes: int | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    with _open_regular(path) as (handle, before):
        if max_bytes is not None and (max_bytes < 1 or before.st_size > max_bytes):
            raise ContractError("release file exceeds the reviewed size limit")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        _assert_unchanged(handle, before, "file changed while hashing")
    return digest.hexdigest(), before.st_size


def sha256_file(path: Path) -> str:
    return file_evidence(path)[0]


def copy_regular(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str | None = None,
    executable: bool | None = None,
) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise ContractError("release copy destination already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        with _open_regular(source) as (input_file, before):
            descriptor = os.open(destination, flags, 0o600)
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(descriptor, "wb") as output:
                for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            _assert_unchanged(input_file, before, "release copy source changed while reading")
        actual_sha256 = digest.hexdigest()
        if size != before.st_size or (expected_sha256 is not None and actual_sha256 != expected_sha256):
            raise ContractError("release copy differs from its source authority")
        is_executable = bool(before.st_mode & 0o111) if executable is None else executable
        os.chmod(destination, 0o755 if is_executable else 0o644)
        return actual_sha256, size
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def read_regular(path: Path, *, max_bytes: int) -> bytes:
    if max_bytes < 1:
        raise ContractError("secure read size limit is invalid")
    with _open_regular(path) as (handle, before):
        if before.st_size > max_bytes:
            raise ContractError("release metadata exceeds the reviewed size limit")
        payload = handle.read(max_bytes + 1)
        if len(payload) != before.st_size or len(payload) > max_bytes:
            raise ContractError("release metadata size changed while reading")
        _assert_unchanged(handle, before, "release metadata changed while reading")
    return payload


def _fsync_directory(path: Path) -> None:
    try:
        before = path.lstat()
        if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
            raise ContractError("release directory is not a real directory")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ContractError("release directory changed while opening")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ContractError("release directory could not be authenticated") from exc


def _safe_relative(name: str) -> str:
    try:
        encoded = name.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise ContractError("release tree path is not strict UTF-8") from exc
    parts = name.split("/")
    if (
        not name
        or len(encoded) > 4096
        or name.startswith("/")
        or "\\" in name
        or any(part in {"", ".", ".."} for part in parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
        or str(PurePosixPath(name)) != name
    ):
        raise ContractError("release tree contains an unsafe path")
    return name


def _inventory(root: Path) -> list[tuple[str, Path, os.stat_result]]:
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise ContractError("release tree root is missing") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise ContractError("release tree root must be a real directory")
    records: list[tuple[str, Path, os.stat_result]] = []
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise ContractError("release tree could not be enumerated") from exc
        for entry in entries:
            relative = _safe_relative(f"{prefix}/{entry.name}".lstrip("/"))
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ContractError("release tree entry changed while enumerating") from exc
            if stat.S_ISLNK(entry_stat.st_mode) or not (
                stat.S_ISDIR(entry_stat.st_mode) or stat.S_ISREG(entry_stat.st_mode)
            ):
                raise ContractError("release tree contains a link or special object")
            records.append((relative, Path(entry.path), entry_stat))
            if stat.S_ISDIR(entry_stat.st_mode):
                pending.append((Path(entry.path), relative))
            if len(records) > MAX_MEMBERS:
                raise ContractError("release tree contains too many entries")
    if not records:
        raise ContractError("release tree is empty")
    return sorted(records, key=lambda item: item[0].encode("utf-8"))


def _normalized_mode(mode: int, *, directory: bool) -> int:
    if directory:
        return 0o755
    return 0o755 if mode & 0o111 else 0o644


def _update_tree(
    digest: Any,
    kind: str,
    name: str,
    mode: int,
    size: int,
    content_sha256: str | None,
) -> None:
    record = [kind, name, mode, size, content_sha256]
    digest.update(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\n")


class _HashingReader:
    def __init__(self, raw: BinaryIO) -> None:
        self.raw = raw
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, amount: int = -1) -> bytes:
        payload = self.raw.read(amount)
        self.digest.update(payload)
        self.size += len(payload)
        return payload


def _tar_info(name: str, mode: int, *, size: int = 0, directory: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = mode
    info.size = size
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def create_archive(source: Path, archive: Path) -> ArchiveEvidence:
    """Create a byte-deterministic uncompressed tar and return its authenticated tree."""
    inventory = _inventory(source)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() or archive.is_symlink():
        raise ContractError("release archive output already exists")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{archive.name}.", dir=archive.parent)
    temporary = Path(temporary_name)
    tree = hashlib.sha256(TREE_DOMAIN)
    file_count = 0
    total_size = 0
    try:
        with os.fdopen(descriptor, "w+b") as output:
            with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as bundle:
                for name, path, observed in inventory:
                    if stat.S_ISDIR(observed.st_mode):
                        mode = _normalized_mode(observed.st_mode, directory=True)
                        bundle.addfile(_tar_info(name, mode, directory=True))
                        _update_tree(tree, "dir", name, mode, 0, None)
                        continue
                    if observed.st_size > MAX_MEMBER_SIZE or total_size + observed.st_size > MAX_TOTAL_SIZE:
                        raise ContractError("release tree exceeds the reviewed size limit")
                    with _open_regular(path) as (raw, opened):
                        if (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino):
                            raise ContractError("release tree entry changed while opening")
                        mode = _normalized_mode(opened.st_mode, directory=False)
                        reader = _HashingReader(raw)
                        bundle.addfile(_tar_info(name, mode, size=opened.st_size), reader)
                        if reader.size != opened.st_size:
                            raise ContractError("release tree file was truncated while archiving")
                        _assert_unchanged(raw, opened, "release tree file changed while archiving")
                    _update_tree(tree, "file", name, mode, reader.size, reader.digest.hexdigest())
                    file_count += 1
                    total_size += reader.size
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, archive)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return ArchiveEvidence(sha256_file(archive), tree.hexdigest(), file_count, total_size)


def _validate_member(member: tarfile.TarInfo, seen: set[str]) -> tuple[str, str, int]:
    name = _safe_relative(member.name)
    if name in seen:
        raise ContractError("release archive contains a duplicate path")
    seen.add(name)
    if set(member.pax_headers) - {"path"} or ("path" in member.pax_headers and member.pax_headers["path"] != name):
        raise ContractError("release archive contains unauthorized PAX metadata")
    if member.uid != 0 or member.gid != 0 or member.uname != "" or member.gname != "" or member.mtime != 0:
        raise ContractError("release archive metadata is not normalized")
    if member.isdir():
        if member.mode != 0o755 or member.size != 0:
            raise ContractError("release archive directory metadata is invalid")
        return name, "dir", member.mode
    if not member.isreg() or member.mode not in {0o644, 0o755}:
        raise ContractError("release archive contains an unsafe object")
    if member.size > MAX_MEMBER_SIZE:
        raise ContractError("release archive member exceeds the reviewed size limit")
    return name, "file", member.mode


def _digest(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ContractError("release digest is invalid")
    return value


def verify_archive(
    archive: Path,
    expected_archive_sha256: str | None = None,
    expected_tree_sha256: str | None = None,
    *,
    expected_paths: frozenset[str] | None = None,
) -> ArchiveEvidence:
    """Verify safety, normalization, ordering, and the canonical tree projection."""
    actual_archive_sha256 = sha256_file(archive)
    if expected_archive_sha256 is not None and actual_archive_sha256 != _digest(expected_archive_sha256):
        raise ContractError("release archive digest does not match its authority")
    tree = hashlib.sha256(TREE_DOMAIN)
    seen: set[str] = set()
    previous: bytes | None = None
    file_count = 0
    total_size = 0
    try:
        with _open_regular(archive) as (raw, before):
            with tarfile.open(fileobj=raw, mode="r:") as bundle:
                for member in bundle:
                    if len(seen) >= MAX_MEMBERS:
                        raise ContractError("release archive contains too many entries")
                    name, kind, mode = _validate_member(member, seen)
                    ordering = name.encode("utf-8")
                    if previous is not None and ordering <= previous:
                        raise ContractError("release archive members are not canonically ordered")
                    previous = ordering
                    parent = PurePosixPath(name).parent
                    if parent != PurePosixPath(".") and str(parent) not in seen:
                        raise ContractError("release archive omits a parent directory")
                    if kind == "dir":
                        _update_tree(tree, kind, name, mode, 0, None)
                        continue
                    total_size += member.size
                    if total_size > MAX_TOTAL_SIZE:
                        raise ContractError("release archive exceeds the reviewed size limit")
                    extracted = bundle.extractfile(member)
                    if extracted is None:
                        raise ContractError("release archive file payload is missing")
                    content = hashlib.sha256()
                    consumed = 0
                    while chunk := extracted.read(1024 * 1024):
                        consumed += len(chunk)
                        content.update(chunk)
                    if consumed != member.size:
                        raise ContractError("release archive file payload is truncated")
                    _update_tree(tree, kind, name, mode, consumed, content.hexdigest())
                    file_count += 1
            _assert_unchanged(raw, before, "release archive changed while verifying")
    except (OSError, tarfile.TarError) as exc:
        raise ContractError("release archive is not a valid tar") from exc
    if not seen:
        raise ContractError("release archive is empty")
    if expected_paths is not None and seen != expected_paths:
        raise ContractError("release archive path set differs from the closed allowlist")
    evidence = ArchiveEvidence(actual_archive_sha256, tree.hexdigest(), file_count, total_size)
    if expected_tree_sha256 is not None and evidence.tree_sha256 != _digest(expected_tree_sha256):
        raise ContractError("release tree digest does not match its authority")
    return evidence


def extract_archive(
    archive: Path,
    destination: Path,
    expected_archive_sha256: str,
    expected_tree_sha256: str,
    *,
    expected_paths: frozenset[str] | None = None,
) -> ArchiveEvidence:
    """Verify first, then extract without tarfile.extract into a private sibling."""
    evidence = verify_archive(
        archive,
        expected_archive_sha256,
        expected_tree_sha256,
        expected_paths=expected_paths,
    )
    if destination.exists() or destination.is_symlink():
        raise ContractError("release extraction destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _fsync_directory(destination.parent)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    seen: set[str] = set()
    try:
        with _open_regular(archive) as (raw, before):
            with tarfile.open(fileobj=raw, mode="r:") as bundle:
                for member in bundle:
                    name, kind, mode = _validate_member(member, seen)
                    target = temporary.joinpath(*PurePosixPath(name).parts)
                    if kind == "dir":
                        target.mkdir(mode=mode)
                        os.chmod(target, mode)
                        continue
                    parent_stat = target.parent.lstat()
                    if not stat.S_ISDIR(parent_stat.st_mode) or stat.S_ISLNK(parent_stat.st_mode):
                        raise ContractError("release extraction parent is missing")
                    source = bundle.extractfile(member)
                    if source is None:
                        raise ContractError("release extraction payload is missing")
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                    descriptor = os.open(target, flags, mode)
                    with os.fdopen(descriptor, "wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                        output.flush()
                        os.fsync(output.fileno())
                    os.chmod(target, mode)
            _assert_unchanged(raw, before, "release archive changed while extracting")
        extracted = tree_evidence(temporary)
        if extracted.tree_sha256 != evidence.tree_sha256:
            raise ContractError("extracted release tree differs from the archive")
        directories = [path for path in temporary.rglob("*") if path.is_dir()]
        for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
            _fsync_directory(directory)
        _fsync_directory(temporary)
        _fsync_directory(destination.parent)
        os.replace(temporary, destination)
        _fsync_directory(destination)
        _fsync_directory(destination.parent)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return evidence


def tree_evidence(source: Path) -> ArchiveEvidence:
    tree = hashlib.sha256(TREE_DOMAIN)
    file_count = 0
    total_size = 0
    for name, path, observed in _inventory(source):
        directory = stat.S_ISDIR(observed.st_mode)
        mode = _normalized_mode(observed.st_mode, directory=directory)
        if directory:
            _update_tree(tree, "dir", name, mode, 0, None)
            continue
        content = sha256_file(path)
        _update_tree(tree, "file", name, mode, observed.st_size, content)
        file_count += 1
        total_size += observed.st_size
    return ArchiveEvidence("", tree.hexdigest(), file_count, total_size)
