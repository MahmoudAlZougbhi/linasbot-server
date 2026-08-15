"""Bootstrap-owned authority for optional legacy nested-runtime quarantine."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

_evidence_spec = importlib.util.spec_from_file_location(
    "bootstrap_nested_runtime_evidence",
    Path(__file__).with_name("bootstrap_nested_runtime_evidence.py"),
)
if _evidence_spec is None or _evidence_spec.loader is None:
    raise RuntimeError("nested runtime evidence module is missing")
_evidence = importlib.util.module_from_spec(_evidence_spec)
_evidence_spec.loader.exec_module(_evidence)

NestedRuntimeQuarantineError = _evidence.NestedRuntimeQuarantineError
NESTED_RUNTIME_NAME = _evidence.NESTED_RUNTIME_NAME
SCHEMA = _evidence.SCHEMA
portable_content_identity = _evidence.portable_content_identity
nested_runtime_path = _evidence.nested_runtime_path

SECURE_ROOT_MODE = 0o700
SECURE_ROOT_OWNER = (0, 0)


def _canonical(value: Any) -> bytes:
    return _evidence._canonical(value)


def _digest(value: Any) -> str:
    return _evidence._digest(value)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object") from exc
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    directories: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory = Path(current)
        directories.append(directory)
        for name in list(dirnames):
            path = directory / name
            if stat.S_ISLNK(path.lstat().st_mode):
                _evidence._safe_symlink_target(root, path)
                dirnames.remove(name)
        for name in filenames:
            path = directory / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                _evidence._safe_symlink_target(root, path)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise NestedRuntimeQuarantineError("nested runtime tree contains an unsafe object")
            _fsync_regular(path)
    for directory in reversed(directories):
        _fsync_dir(directory)


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


def probe_evidence(repo_dir: Path) -> dict[str, Any]:
    live = nested_runtime_path(repo_dir)
    if not live.exists() and not live.is_symlink():
        return absent_evidence()
    return _evidence.collect_present(live)


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
    try:
        document = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid") from exc
    if not isinstance(document, dict):
        raise NestedRuntimeQuarantineError("nested runtime authority is invalid")
    return document


def _atomic_authority_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.authority.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise NestedRuntimeQuarantineError("nested runtime authority write failed")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = -1
        if path.exists() or path.is_symlink():
            existing = path.read_bytes()
            if existing == payload:
                temporary.unlink()
                return
            if len(existing) < len(payload) and payload.startswith(existing):
                path.unlink()
                _fsync_dir(path.parent)
            else:
                raise NestedRuntimeQuarantineError("nested runtime authority changed")
        os.link(temporary, path, follow_symlinks=False)
        _fsync_dir(path.parent)
        temporary.unlink()
        verify_fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            read_back = bytearray()
            while True:
                chunk = os.read(verify_fd, 65536)
                if not chunk:
                    break
                read_back.extend(chunk)
        finally:
            os.close(verify_fd)
        if bytes(read_back) != payload:
            raise NestedRuntimeQuarantineError("nested runtime authority readback failed")
        _fsync_dir(path.parent)
    except OSError as exc:
        raise NestedRuntimeQuarantineError("nested runtime authority write failed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_authority(backup: Path, *, tx_id: str, evidence: dict[str, Any], destination_name: str) -> None:
    payload = _canonical(
        {
            "schema": SCHEMA,
            "tx_id": tx_id,
            "evidence": evidence,
            "quarantine_name": destination_name,
            "evidence_sha256": digest_evidence(evidence),
        }
    ) + b"\n"
    _atomic_authority_write(authority_path(backup), payload)


def publish_authority(repo_dir: Path, backup: Path, expected: dict[str, Any], tx_id: str) -> None:
    _write_authority(
        backup,
        tx_id=tx_id,
        evidence=expected,
        destination_name=quarantine_destination(repo_dir, tx_id).name,
    )


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
    if current_owner not in {source_owner, target_owner} or current_mode not in {source_mode, target_mode}:
        raise NestedRuntimeQuarantineError(f"nested runtime {direction} partial root metadata is invalid")
    if current_owner != target_owner:
        os.chown(path, target_owner[0], target_owner[1])
    if current_mode != target_mode:
        os.chmod(path, target_mode)
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
        _evidence.assert_content_matches(live, evidence)
        try:
            if live.stat().st_dev != quarantine.parent.stat().st_dev:
                raise NestedRuntimeQuarantineError(f"nested runtime {direction} would cross devices")
        except OSError as exc:
            raise NestedRuntimeQuarantineError(f"nested runtime {direction} would cross devices") from exc
        _fsync_tree(live)
        os.rename(live, quarantine)
        _fsync_dir(live.parent)
        _fsync_dir(quarantine.parent)
        return quarantine
    _evidence.assert_content_matches(quarantine, evidence)
    return quarantine


def apply_quarantine(repo_dir: Path, backup: Path, expected: dict[str, Any], tx_id: str) -> None:
    if not expected.get("present"):
        assert_absent(repo_dir)
        publish_authority(repo_dir, backup, expected, tx_id)
        return
    live = nested_runtime_path(repo_dir)
    quarantine = quarantine_destination(repo_dir, tx_id)
    if (live.exists() or live.is_symlink()) and (quarantine.exists() or quarantine.is_symlink()):
        raise NestedRuntimeQuarantineError("nested runtime quarantine collides with the live tree")
    publish_authority(repo_dir, backup, expected, tx_id)
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
    authority_file = authority_path(backup)
    if not authority_file.exists() and not authority_file.is_symlink():
        assert_live_matches(repo_dir, expected)
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
    _evidence.assert_content_matches(quarantine, expected)
    info = quarantine.lstat()
    if (info.st_uid, info.st_gid) != SECURE_ROOT_OWNER or stat.S_IMODE(info.st_mode) != SECURE_ROOT_MODE:
        raise NestedRuntimeQuarantineError("nested runtime quarantine root metadata is invalid")
