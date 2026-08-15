"""Bootstrap-owned authority for optional legacy nested-runtime quarantine."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

SCHEMA = 1
NESTED_RUNTIME_NAME = "linaslaserbot-2.7.22"
MAX_FILE_COUNT = 500_000
MAX_SYMLINK_COUNT = 100_000
MAX_DIRECTORY_COUNT = 100_000
MAX_TOTAL_BYTES = 50 * 1024**3
SECURE_ROOT_MODE = 0o700
SECURE_ROOT_OWNER = (0, 0)
_CONTENT_KEYS = (
    "schema",
    "present",
    "file_count",
    "symlink_count",
    "directory_count",
    "total_bytes",
    "root_dev",
    "root_ino",
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


def _content_identity(evidence: dict[str, Any]) -> dict[str, Any]:
    return {key: evidence[key] for key in _CONTENT_KEYS}


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    directories: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory = Path(current)
        directories.append(directory)
        for name in filenames:
            _fsync_regular(directory / name)
        for name in dirnames:
            if stat.S_ISLNK((directory / name).lstat().st_mode):
                raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe link")
    for directory in reversed(directories):
        _fsync_dir(directory)


def nested_runtime_path(repo_dir: Path) -> Path:
    return repo_dir / NESTED_RUNTIME_NAME


def quarantine_destination(repo_dir: Path, tx_id: str) -> Path:
    return repo_dir.parent / f".quarantine-nested-runtime-{tx_id}"


def authority_path(backup: Path) -> Path:
    return backup / "nested-runtime.authority.json"


def absent_evidence() -> dict[str, Any]:
    return {"schema": SCHEMA, "present": False}


def digest_evidence(evidence: dict[str, Any]) -> str:
    if evidence.get("present") is False:
        return _digest(absent_evidence())
    return _digest(evidence)


def _safe_symlink_target(root: Path, path: Path) -> str:
    target = os.readlink(path)
    if target.startswith("/"):
        resolved = Path(target)
    else:
        resolved = (path.parent / target).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise NestedRuntimeQuarantineError("nested runtime symlink escapes its root") from exc
    return target


def _collect_present(root: Path) -> dict[str, Any]:
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
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                payload = os.read(descriptor, info.st_size + 1)
            finally:
                os.close(descriptor)
            if len(payload) != info.st_size:
                raise NestedRuntimeQuarantineError("nested runtime tree changed during evidence collection")
            member_digests.append(
                _digest_bytes(
                    _canonical(
                        {
                            "kind": "file",
                            "relative": path.relative_to(root).as_posix(),
                            "sha256": _digest_bytes(payload),
                            "size": info.st_size,
                            "mode": stat.S_IMODE(info.st_mode),
                            "uid": info.st_uid,
                            "gid": info.st_gid,
                        }
                    )
                )
            )
    if symlink_count > MAX_SYMLINK_COUNT or directory_count > MAX_DIRECTORY_COUNT:
        raise NestedRuntimeQuarantineError("nested runtime tree exceeds the safety limit")
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


def _assert_content_matches(root: Path, expected: dict[str, Any]) -> None:
    observed = _collect_present(root)
    if _content_identity(observed) != _content_identity(expected):
        raise NestedRuntimeQuarantineError("nested runtime evidence changed")


def probe_evidence(repo_dir: Path) -> dict[str, Any]:
    live = nested_runtime_path(repo_dir)
    if not live.exists() and not live.is_symlink():
        return absent_evidence()
    return _collect_present(live)


def assert_matches(repo_dir: Path, expected: dict[str, Any]) -> None:
    if not expected.get("present"):
        assert_absent(repo_dir)
        return
    observed = probe_evidence(repo_dir)
    if observed != expected:
        raise NestedRuntimeQuarantineError("nested runtime evidence changed")


def assert_absent(repo_dir: Path) -> None:
    live = nested_runtime_path(repo_dir)
    if live.exists() or live.is_symlink():
        raise NestedRuntimeQuarantineError("nested runtime remains at the live repository path")


def assert_live_matches(repo_dir: Path, expected: dict[str, Any]) -> None:
    assert_matches(repo_dir, expected)


def _read_authority(backup: Path) -> dict[str, Any]:
    path = authority_path(backup)
    document = json.loads(path.read_bytes())
    if not isinstance(document, dict):
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
    return document


def _write_authority(backup: Path, *, tx_id: str, evidence: dict[str, Any], destination_name: str) -> None:
    path = authority_path(backup)
    payload = {
        "schema": SCHEMA,
        "tx_id": tx_id,
        "evidence": evidence,
        "quarantine_name": destination_name,
        "evidence_sha256": digest_evidence(evidence),
    }
    encoded = _canonical(payload) + b"\n"
    if path.exists() or path.is_symlink():
        if path.read_bytes() != encoded:
            raise NestedRuntimeQuarantineError("nested runtime authority changed")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    path.chmod(0o600)
    _fsync_dir(path.parent)


def _transition_root_metadata(
    path: Path,
    *,
    evidence: dict[str, Any],
    source_owner: tuple[int, int],
    source_mode: int,
    target_owner: tuple[int, int],
    target_mode: int,
    direction: str,
) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise NestedRuntimeQuarantineError(f"nested runtime {direction} root is unsafe")
    if info.st_dev != int(evidence["root_dev"]) or info.st_ino != int(evidence["root_ino"]):
        raise NestedRuntimeQuarantineError(f"nested runtime {direction} root identity changed")
    current_owner = (info.st_uid, info.st_gid)
    current_mode = stat.S_IMODE(info.st_mode)
    if current_owner == source_owner and current_mode == source_mode:
        os.chown(path, target_owner[0], target_owner[1])
        os.chmod(path, target_mode)
    elif current_owner != target_owner or current_mode != target_mode:
        raise NestedRuntimeQuarantineError(f"nested runtime {direction} partial root metadata is invalid")
    final = path.lstat()
    if (final.st_uid, final.st_gid) != target_owner or stat.S_IMODE(final.st_mode) != target_mode:
        raise NestedRuntimeQuarantineError(f"nested runtime {direction} root metadata is not exact")
    _fsync_dir(path)


def _rename_quarantine(
    *,
    live: Path,
    quarantine: Path,
    evidence: dict[str, Any],
    direction: str,
) -> Path:
    live_exists = live.exists() or live.is_symlink()
    quarantine_exists = quarantine.exists() or quarantine.is_symlink()
    if live_exists == quarantine_exists:
        raise NestedRuntimeQuarantineError(f"nested runtime {direction} location is ambiguous")
    if live_exists:
        _assert_content_matches(live, evidence)
        if live.stat().st_dev != quarantine.parent.stat().st_dev:
            raise NestedRuntimeQuarantineError(f"nested runtime {direction} would cross devices")
        _fsync_tree(live)
        os.rename(live, quarantine)
        _fsync_dir(live.parent)
        _fsync_dir(quarantine.parent)
        return quarantine
    _assert_content_matches(quarantine, evidence)
    return quarantine


def apply_quarantine(repo_dir: Path, backup: Path, expected: dict[str, Any], tx_id: str) -> None:
    if not expected.get("present"):
        assert_absent(repo_dir)
        return
    live = nested_runtime_path(repo_dir)
    quarantine = quarantine_destination(repo_dir, tx_id)
    if (live.exists() or live.is_symlink()) and (quarantine.exists() or quarantine.is_symlink()):
        raise NestedRuntimeQuarantineError("nested runtime quarantine collides with the live tree")
    _write_authority(backup, tx_id=tx_id, evidence=expected, destination_name=quarantine.name)
    current = _rename_quarantine(live=live, quarantine=quarantine, evidence=expected, direction="quarantine")
    _transition_root_metadata(
        current,
        evidence=expected,
        source_owner=(int(expected["root_uid"]), int(expected["root_gid"])),
        source_mode=int(expected["root_mode"]),
        target_owner=SECURE_ROOT_OWNER,
        target_mode=SECURE_ROOT_MODE,
        direction="quarantine",
    )
    assert_absent(repo_dir)
    assert_quarantined(repo_dir, expected, tx_id)


def restore_quarantine(repo_dir: Path, backup: Path, expected: dict[str, Any], tx_id: str) -> None:
    if not expected.get("present"):
        assert_absent(repo_dir)
        return
    authority = _read_authority(backup)
    if authority.get("tx_id") != tx_id or authority.get("evidence") != expected:
        raise NestedRuntimeQuarantineError("nested runtime rollback authority is invalid")
    live = nested_runtime_path(repo_dir)
    quarantine = quarantine_destination(repo_dir, tx_id)
    if quarantine.name != authority.get("quarantine_name"):
        raise NestedRuntimeQuarantineError("nested runtime rollback quarantine name is invalid")
    live_exists = live.exists() or live.is_symlink()
    quarantine_exists = quarantine.exists() or quarantine.is_symlink()
    if live_exists and quarantine_exists:
        raise NestedRuntimeQuarantineError("nested runtime rollback location is ambiguous")
    if quarantine_exists:
        _transition_root_metadata(
            quarantine,
            evidence=expected,
            source_owner=SECURE_ROOT_OWNER,
            source_mode=SECURE_ROOT_MODE,
            target_owner=(int(expected["root_uid"]), int(expected["root_gid"])),
            target_mode=int(expected["root_mode"]),
            direction="rollback",
        )
        _fsync_tree(quarantine)
        os.rename(quarantine, live)
        _fsync_dir(quarantine.parent)
        _fsync_dir(live.parent)
    assert_live_matches(repo_dir, expected)


def assert_quarantined(repo_dir: Path, expected: dict[str, Any], tx_id: str) -> None:
    if not expected.get("present"):
        assert_absent(repo_dir)
        return
    live = nested_runtime_path(repo_dir)
    quarantine = quarantine_destination(repo_dir, tx_id)
    if live.exists() or live.is_symlink():
        raise NestedRuntimeQuarantineError("nested runtime was not quarantined")
    if not quarantine.exists() and not quarantine.is_symlink():
        raise NestedRuntimeQuarantineError("nested runtime quarantine is missing")
    _assert_content_matches(quarantine, expected)
    info = quarantine.lstat()
    if (info.st_uid, info.st_gid) != SECURE_ROOT_OWNER or stat.S_IMODE(info.st_mode) != SECURE_ROOT_MODE:
        raise NestedRuntimeQuarantineError("nested runtime quarantine root metadata is invalid")
