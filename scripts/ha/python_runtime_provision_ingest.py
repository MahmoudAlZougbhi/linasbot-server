"""Standalone OS-Python ingest of an exact QG release bundle on a clean node."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Final

from scripts.ha.python_runtime_provision_ingest_contract import (
    CONTROL_MEMBERS,
    FILES,
    RUNTIME_NAME,
    SHA256_RE,
    SHA_RE,
    TREE_DOMAIN,
    IngestError,
    canonical,
    common_lock,
    launcher_receipt,
    manifest_evidence,
    write_launcher_receipt,
)

STATE_ROOT: Final = Path("/var/lib/linasbot/meta-ha")
LAUNCHER_RECEIPTS: Final = STATE_ROOT / "python-runtime-provision-launchers"


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise IngestError("release manifest contains duplicate keys")
        result[key] = value
    return result


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written < 1:
            raise IngestError("release ingest write made no progress")
        view = view[written:]


def _sync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _secure_dir(path: Path, mode: int, *, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=mode)
        os.chown(path, 0, 0, follow_symlinks=False)
        os.chmod(path, mode, follow_symlinks=False)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, 0, mode)
    ):
        raise IngestError("release ingest directory is unsafe")


def _source_evidence(path: Path, source_uid: int, limit: int) -> tuple[str, int]:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != source_uid
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) & 0o022
        or not 1 <= before.st_size <= limit
    ):
        raise IngestError("release ingest source is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ):
            raise IngestError("release ingest source changed while opening")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise IngestError("release ingest source changed while reading")
    finally:
        os.close(descriptor)
    return digest.hexdigest(), before.st_size


def _root_evidence(path: Path, limit: int) -> tuple[str, int]:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink) != (0, 0, 0o600, 1)
    ):
        raise IngestError("installed release file is unsafe")
    return _source_evidence(path, 0, limit)


def _load_manifest(path: Path, expected_sha: str) -> tuple[dict[str, Any], bytes]:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink) != (0, 0, 0o600, 1)
        or not 1 <= info.st_size <= 1024 * 1024
    ):
        raise IngestError("release manifest snapshot is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        raw = b""
        while len(raw) < opened.st_size:
            chunk = os.read(descriptor, opened.st_size - len(raw))
            if not chunk:
                raise IngestError("release manifest snapshot is truncated")
            raw += chunk
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if (
        any(getattr(opened, key) != getattr(after, key) for key in identity)
        or hashlib.sha256(raw).hexdigest() != expected_sha
    ):
        raise IngestError("release manifest differs from owner authority")
    try:
        payload = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IngestError("release manifest is invalid JSON") from exc
    if not isinstance(payload, dict) or canonical(payload) != raw:
        raise IngestError("release manifest is not canonical")
    return payload, raw


def _snapshot_source(
    source: Path,
    destination: Path,
    source_uid: int,
    *,
    extra_files: frozenset[str] = frozenset(),
) -> dict[str, tuple[str, int]]:
    directory_fd = os.open(source, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    before = os.fstat(directory_fd)
    expected_files = FILES | extra_files
    if (
        not stat.S_ISDIR(before.st_mode)
        or before.st_uid != source_uid
        or set(os.listdir(directory_fd)) != expected_files
    ):
        os.close(directory_fd)
        raise IngestError("release ingest source directory is unsafe")
    evidence: dict[str, tuple[str, int]] = {}
    try:
        for name in sorted(FILES):
            limit = (
                1024 * 1024 if name == "release-manifest.json" else (256 * 1024**2 if name == RUNTIME_NAME else 1024**3)
            )
            source_fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != source_uid
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) & 0o022
                or not 1 <= opened.st_size <= limit
            ):
                os.close(source_fd)
                raise IngestError("release ingest source file is unsafe")
            target = destination / name
            temporary = destination / f".{name}.copying"
            temporary.unlink(missing_ok=True)
            target_fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            digest = hashlib.sha256()
            size = 0
            try:
                os.fchmod(target_fd, 0o600)
                os.fchown(target_fd, 0, 0)
                while chunk := os.read(source_fd, 1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    _write_all(target_fd, chunk)
                os.fsync(target_fd)
            finally:
                os.close(target_fd)
            after = os.fstat(source_fd)
            os.close(source_fd)
            identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
            if any(getattr(opened, key) != getattr(after, key) for key in identity) or size != opened.st_size:
                raise IngestError("release ingest source changed during snapshot")
            observed = (digest.hexdigest(), size)
            if target.exists() or target.is_symlink():
                if _root_evidence(target, limit) != observed:
                    raise IngestError("release ingest snapshot conflicts")
                temporary.unlink()
            else:
                os.replace(temporary, target)
            _sync_dir(destination)
            evidence[name] = observed
        after_directory = os.fstat(directory_fd)
        identity = ("st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
        if (
            any(getattr(before, key) != getattr(after_directory, key) for key in identity)
            or set(os.listdir(directory_fd)) != expected_files
        ):
            raise IngestError("release ingest source directory changed during snapshot")
    finally:
        os.close(directory_fd)
    return evidence


def _tree_record(digest: Any, kind: str, name: str, mode: int, size: int, content: str | None) -> None:
    digest.update(json.dumps([kind, name, mode, size, content], separators=(",", ":")).encode() + b"\n")


def _control_tree(root: Path) -> tuple[str, int, int]:
    _secure_dir(root, 0o700)
    entries: list[tuple[str, Path, os.stat_result]] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative not in CONTROL_MEMBERS:
            raise IngestError("trusted control root contains an unexpected path")
        info = path.lstat()
        if info.st_uid != 0 or info.st_gid != 0 or stat.S_ISLNK(info.st_mode):
            raise IngestError("trusted control root ownership or type is unsafe")
        entries.append((relative, path, info))
    if {name for name, _path, _info in entries} != CONTROL_MEMBERS:
        raise IngestError("trusted control root file set is incomplete")
    digest = hashlib.sha256(TREE_DOMAIN)
    count = total = 0
    for name, path, info in sorted(entries, key=lambda item: item[0].encode("utf-8")):
        if stat.S_ISDIR(info.st_mode):
            if stat.S_IMODE(info.st_mode) != 0o755:
                raise IngestError("trusted control directory mode is invalid")
            _tree_record(digest, "dir", name, 0o755, 0, None)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) in {0o644, 0o755}:
            content, size = _source_evidence(path, 0, 8 * 1024**2)
            _tree_record(digest, "file", name, stat.S_IMODE(info.st_mode), size, content)
            count += 1
            total += size
        else:
            raise IngestError("trusted control object is unsafe")
    return digest.hexdigest(), count, total


def _extract_control(archive: Path, destination: Path, payload: dict[str, Any]) -> None:
    expected_tree = payload["tree_sha256"]
    if destination.exists() or destination.is_symlink():
        if _control_tree(destination) != (expected_tree, payload["file_count"], payload["total_size"]):
            raise IngestError("trusted control root differs from manifest")
        return
    temporary = destination.parent / f".{destination.name}.extracting"
    if temporary.exists() or temporary.is_symlink():
        _secure_dir(temporary, 0o700)
        prefix = f".quarantine-control-{destination.name}-"
        counters = sorted(
            int(entry.name.removeprefix(prefix))
            for entry in os.scandir(destination.parent)
            if entry.name.startswith(prefix) and entry.name.removeprefix(prefix).isdigit()
        )
        if counters != list(range(1, len(counters) + 1)):
            raise IngestError("control quarantine sequence is invalid")
        os.rename(temporary, destination.parent / f"{prefix}{len(counters) + 1:06d}")
        _sync_dir(destination.parent)
    temporary.mkdir(mode=0o700)
    os.chown(temporary, 0, 0)
    tree = hashlib.sha256(TREE_DOMAIN)
    seen: set[str] = set()
    count = total = 0
    with tarfile.open(archive, "r:") as bundle:
        previous: bytes | None = None
        for member in bundle:
            name = member.name
            parts = name.split("/")
            if (
                not name
                or name.startswith("/")
                or "\\" in name
                or any(part in {"", ".", ".."} for part in parts)
                or str(PurePosixPath(name)) != name
                or name in seen
                or name not in CONTROL_MEMBERS
            ):
                raise IngestError("control archive path is unsafe")
            ordering = name.encode("utf-8", "strict")
            if previous is not None and ordering <= previous:
                raise IngestError("control archive ordering is invalid")
            previous = ordering
            parent = str(PurePosixPath(name).parent)
            if parent != "." and parent not in seen:
                raise IngestError("control archive omits a parent directory")
            if (
                set(member.pax_headers) - {"path"}
                or ("path" in member.pax_headers and member.pax_headers["path"] != name)
                or member.uid != 0
                or member.gid != 0
                or member.uname != ""
                or member.gname != ""
                or member.mtime != 0
            ):
                raise IngestError("control archive metadata is invalid")
            target = temporary.joinpath(*parts)
            if member.isdir():
                if member.mode != 0o755 or member.size != 0:
                    raise IngestError("control directory metadata is invalid")
                target.mkdir(mode=0o755)
                os.chown(target, 0, 0)
                os.chmod(target, 0o755)
                _tree_record(tree, "dir", name, 0o755, 0, None)
            elif member.isreg() and member.mode in {0o644, 0o755} and member.size <= 8 * 1024**2:
                source = bundle.extractfile(member)
                if source is None:
                    raise IngestError("control file payload is missing")
                descriptor = os.open(
                    target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), member.mode
                )
                content = hashlib.sha256()
                consumed = 0
                try:
                    os.fchmod(descriptor, member.mode)
                    os.fchown(descriptor, 0, 0)
                    while chunk := source.read(1024 * 1024):
                        consumed += len(chunk)
                        content.update(chunk)
                        _write_all(descriptor, chunk)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                if consumed != member.size:
                    raise IngestError("control file payload is truncated")
                _tree_record(tree, "file", name, member.mode, consumed, content.hexdigest())
                count += 1
                total += consumed
            else:
                raise IngestError("control archive object is unsafe")
            seen.add(name)
    if seen != CONTROL_MEMBERS or (tree.hexdigest(), count, total) != (
        expected_tree,
        payload["file_count"],
        payload["total_size"],
    ):
        raise IngestError("control archive differs from manifest authority")
    for path in sorted(
        (item for item in temporary.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True
    ):
        _sync_dir(path)
    _sync_dir(temporary)
    os.rename(temporary, destination)
    _sync_dir(destination.parent)


def _install(
    source: Path,
    source_uid: int,
    artifact_id: int,
    api_sha: str,
    manifest_sha: str,
    run_id: int,
    run_attempt: int,
    target_sha: str,
    *,
    retained_transaction_id: str | None = None,
    emit_ack: bool = True,
) -> int:
    resolved = source.resolve(strict=True)
    if retained_transaction_id is None:
        allowed = re.fullmatch(
            r"/var/lib/linasbot/meta-ha/workflow-uploads/python-runtime-[1-9][0-9]*-[1-9][0-9]*/release",
            str(resolved),
        )
    else:
        allowed = re.fullmatch(r"pyr_[0-9a-f]{32}", retained_transaction_id)
        expected = STATE_ROOT / "python-runtime-transactions" / retained_transaction_id / "authority"
        if source_uid != 0 or resolved != expected:
            allowed = None
    if allowed is None:
        raise IngestError("release ingest source path is outside its fixed staging root")
    source = resolved
    bundle_parent = STATE_ROOT / "release-bundles"
    _secure_dir(STATE_ROOT, 0o700, create=True)
    _secure_dir(bundle_parent, 0o700, create=True)
    key = f"{artifact_id}-{api_sha}"
    bundle = bundle_parent / key
    staging = bundle_parent / f".ingest-{key}"
    if not (bundle.exists() or bundle.is_symlink()):
        _secure_dir(staging, 0o700, create=True)
        observed = _snapshot_source(
            source,
            staging,
            source_uid,
            extra_files=frozenset({"plan.json"}) if retained_transaction_id is not None else frozenset(),
        )
        manifest, _raw = _load_manifest(staging / "release-manifest.json", manifest_sha)
        evidence = manifest_evidence(manifest, artifact_id, run_id, run_attempt, target_sha)
        if manifest["payloads"]["source_bundle"]["target_sha"] != target_sha:
            raise IngestError("release source bundle target differs")
        if any(observed[name][0] != evidence[name][0] for name in FILES):
            raise IngestError("release ingest snapshot differs from its manifest")
        if {entry.name for entry in os.scandir(staging)} != FILES:
            raise IngestError("release ingest staging file set is not closed")
        os.rename(staging, bundle)
        _sync_dir(bundle_parent)
    _secure_dir(bundle, 0o700)
    if {entry.name for entry in os.scandir(bundle)} != FILES:
        raise IngestError("installed release bundle file set is not closed")
    manifest, _raw = _load_manifest(bundle / "release-manifest.json", manifest_sha)
    evidence = manifest_evidence(manifest, artifact_id, run_id, run_attempt, target_sha)
    for name in FILES:
        digest, limit = evidence[name]
        if _root_evidence(bundle / name, limit)[0] != digest:
            raise IngestError("installed release bundle differs from manifest")
    control_parent = STATE_ROOT / "python-runtime-provision-control"
    _secure_dir(control_parent, 0o700, create=True)
    control_root = control_parent / key
    control_payload = manifest["payloads"]["control_plane"]
    _extract_control(bundle / "control-plane.tar", control_root, control_payload)
    launcher_sha, launcher_size = _source_evidence(
        control_root / "scripts/ha/python_runtime_provision_trusted_launcher.py", 0, 8 * 1024**2
    )
    receipt = launcher_receipt(
        artifact_id=artifact_id,
        artifact_api_sha256=api_sha,
        manifest_sha256=manifest_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        target_sha=target_sha,
        bundle_root=bundle,
        control_root=control_root,
        control_archive_sha256=control_payload["archive_sha256"],
        control_tree_sha256=control_payload["tree_sha256"],
        launcher_sha256=launcher_sha,
        launcher_size=launcher_size,
    )
    _secure_dir(LAUNCHER_RECEIPTS, 0o700, create=True)
    write_launcher_receipt(LAUNCHER_RECEIPTS / f"{key}.json", canonical(receipt))
    if emit_ack:
        print(
            json.dumps(
                {"schema": 1, "bundle_root": str(bundle), "control_root": str(control_root)},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    values = sys.argv[1:] if argv is None else argv
    if len(values) != 8:
        raise IngestError("usage: ingest SOURCE UID ARTIFACT_ID API_SHA MANIFEST_SHA RUN_ID ATTEMPT TARGET_SHA")
    source = Path(values[0])
    source_uid, artifact_id, run_id, run_attempt = map(int, (values[1], values[2], values[5], values[6]))
    api_sha, manifest_sha, target_sha = values[3], values[4], values[7]
    if os.geteuid() != 0 or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise IngestError("release ingest requires root OS Python with -B -I -S")
    if any(name.startswith("PYTHON") for name in os.environ):
        raise IngestError("release ingest forbids ambient Python controls")
    if any(SHA256_RE.fullmatch(value) is None or value == "0" * 64 for value in (api_sha, manifest_sha)):
        raise IngestError("release ingest digest authority is invalid")
    if (
        SHA_RE.fullmatch(target_sha) is None
        or target_sha == "0" * 40
        or source_uid < 0
        or min(artifact_id, run_id, run_attempt) < 1
    ):
        raise IngestError("release ingest identity authority is invalid")
    with common_lock(STATE_ROOT):
        return _install(source, source_uid, artifact_id, api_sha, manifest_sha, run_id, run_attempt, target_sha)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (IngestError, OSError, ValueError, tarfile.TarError) as exc:
        print(f"[python-runtime-ingest] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
