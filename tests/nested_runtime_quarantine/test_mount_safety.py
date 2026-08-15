"""Nested-runtime mount and traversal safety tests."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

from tests.nested_runtime_quarantine.conftest import (
    _DEFAULT_MOUNTINFO,
    _build_tree,
    _mountinfo_with_bind,
    _patch_chown,
    _patch_mountinfo,
    _patch_secure_authority,
    quarantine,
    safety,
)

ROOT = Path(__file__).resolve().parents[2]
SAFETY_PATH = ROOT / "scripts" / "ha" / "bootstrap_nested_runtime_safety.py"


def test_walk_scan_error_fails_closed_without_path_leak(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "file").write_bytes(b"x")
    secret = str(nested / "secret-member")
    real_listdir = os.listdir

    def broken_listdir(fd: int) -> list[str]:
        if fd == nested_fd["value"]:
            raise OSError(13, "permission denied", secret)
        return real_listdir(fd)

    nested_fd: dict[str, int] = {"value": -1}
    real_open = os.open

    def capture_open(path: str | os.PathLike[str], flags: int, *args: object, **kwargs: object) -> int:
        descriptor = real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        if Path(path) == nested:
            nested_fd["value"] = descriptor
        return descriptor

    monkeypatch.setattr(safety.os, "open", capture_open)
    monkeypatch.setattr(safety.os, "listdir", broken_listdir)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="unsafe object") as exc:
        quarantine.probe_evidence(repo)
    assert secret not in str(exc.value)


def test_same_size_replacement_fails_during_hash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    target = nested / "file"
    target.write_bytes(b"aaaa")
    path_info = safety.member_lstat(target)
    real_read = os.read

    def poisoned_read(fd: int, size: int) -> bytes:
        target.write_bytes(b"bbbb")
        return real_read(fd, size)

    monkeypatch.setattr(safety.os, "read", poisoned_read)
    with pytest.raises(RuntimeError, match="changed during evidence collection"):
        safety.hash_regular_file(target, path_info)


def test_hardlinked_member_rejects_probe(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    primary = nested / "primary"
    primary.write_bytes(b"x")
    os.link(primary, nested / "alias")
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="unsafe object"):
        quarantine.probe_evidence(repo)


def test_bind_mount_same_st_dev_rejects_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "main.py").write_text("legacy\n", encoding="utf-8")
    bound = nested / "bound"
    bound.mkdir()
    _patch_mountinfo(monkeypatch, _mountinfo_with_bind(nested, "bound"))
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="mount point"):
        quarantine.probe_evidence(repo)


def test_bind_mount_on_root_rejects_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "main.py").write_text("legacy\n", encoding="utf-8")
    _patch_mountinfo(monkeypatch, _mountinfo_with_bind(nested, "."))
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="mount point"):
        quarantine.probe_evidence(repo)


def test_unreadable_mountinfo_fails_closed(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="mount namespace is invalid"):
        safety.prepare_mount_context(nested, mountinfo_text="")


def test_malformed_mountinfo_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    _patch_mountinfo(monkeypatch, "not-a-valid-mountinfo-line\n")
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="mount namespace is invalid"):
        quarantine.probe_evidence(repo)


def test_mountinfo_boundary_escape_is_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "main.py").write_text("legacy\n", encoding="utf-8")
    escaped = f"{nested}/sub/../../outside"
    mountinfo = f"101 1 0:1 / {escaped} rw - bind /tmp/outside bind rw\n{_DEFAULT_MOUNTINFO}"
    _patch_mountinfo(monkeypatch, mountinfo)
    observed = quarantine.probe_evidence(repo)
    assert observed["present"] is True


def test_rename_rechecks_mount_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "8" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    _build_tree(repo)
    state = {"phase": "probe"}

    def _phase_mountinfo(path: Path | None = None) -> str:
        if path is not None:
            return Path(path).read_text(encoding="utf-8")
        if state["phase"] == "probe":
            return _DEFAULT_MOUNTINFO
        return _mountinfo_with_bind(quarantine.nested_runtime_path(repo), "bound")

    monkeypatch.setattr(safety, "read_mountinfo_text", _phase_mountinfo)
    expected = quarantine.probe_evidence(repo)
    state["phase"] = "rename"
    (quarantine.nested_runtime_path(repo) / "bound").mkdir()
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="mount point"):
        quarantine.apply_quarantine(repo, backup, expected, tx_id)


def test_authenticated_module_loader_rejects_spoofed_file_attribute(tmp_path: Path) -> None:

    from scripts.ha import bootstrap_nested_runtime_loader as loader

    real_path = SAFETY_PATH
    spoof = types.ModuleType("bootstrap_nested_runtime_safety@spoof")
    spoof.__file__ = str(real_path)
    spoof.__nested_runtime_source_sha256__ = "deadbeef"
    sys.modules[loader.authenticated_module_name("bootstrap_nested_runtime_safety", real_path)] = spoof
    loaded = loader.load_authenticated_module("bootstrap_nested_runtime_safety", real_path)
    assert loaded is not spoof
    assert getattr(loaded, "__nested_runtime_source_sha256__", "") != "deadbeef"


def test_incremental_directory_child_limit_fails_before_full_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    sentinel = {"materialized": 0}
    real_listdir = os.listdir
    limit = safety.MAX_CHILDREN_PER_DIRECTORY
    nested_fd: dict[str, int] = {"value": -1}
    real_open = os.open

    def capture_open(path: str | os.PathLike[str], flags: int, *args: object, **kwargs: object) -> int:
        descriptor = real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        if Path(path) == nested:
            nested_fd["value"] = descriptor
        return descriptor

    def bounded_listdir(fd: int) -> list[str]:
        if fd == nested_fd["value"]:
            return [f"child-{index:06d}" for index in range(limit + 1)]
        return real_listdir(fd)

    monkeypatch.setattr(safety.os, "open", capture_open)
    monkeypatch.setattr(safety.os, "listdir", bounded_listdir)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="safety limit"):
        quarantine.probe_evidence(repo)
    assert sentinel["materialized"] == 0


def test_directory_symlink_swap_between_stat_and_open_rejects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    subdir = nested / "sub"
    subdir.mkdir()
    (subdir / "file").write_bytes(b"x")
    real_open = os.open

    def swapping_open(
        path: str | os.PathLike[str],
        flags: int,
        *args: object,
        dir_fd: int | None = None,
        **kwargs: object,
    ) -> int:
        if dir_fd is not None and path == "sub":
            subdir.unlink()
            os.symlink("file", subdir)
        return real_open(path, flags, *args, dir_fd=dir_fd, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(safety.os, "open", swapping_open)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="unsafe object"):
        quarantine.probe_evidence(repo)
