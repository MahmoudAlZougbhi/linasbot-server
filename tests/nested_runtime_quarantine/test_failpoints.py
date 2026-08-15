"""Crash failpoint matrix: authority, apply, rollback, mount, and openat."""

from __future__ import annotations

import os
import types
from pathlib import Path

import pytest

from tests.nested_runtime_quarantine.conftest import (
    _authority_payload,
    _build_tree,
    _mountinfo_with_bind,
    _patch_chown,
    _patch_secure_authority,
    quarantine,
    safety,
)


def _assert_redacted_chain(exc: BaseException, secret: str) -> None:
    assert secret not in str(exc)
    chain = exc
    while chain.__cause__ is not None:
        chain = chain.__cause__
        assert secret not in str(chain)


def test_authority_write_retries_twice_after_replace_ack_loss(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_secure_authority(monkeypatch)
    backup = tmp_path / "backup"
    backup.mkdir()
    path = quarantine.authority_path(backup)
    payload = _authority_payload()
    real_replace = os.replace
    injected = False

    def interrupted_replace(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        real_replace(src, dst)
        nonlocal injected
        if not injected:
            injected = True
            raise OSError("injected authority replace acknowledgement loss")

    for target in (quarantine.os, safety.os):
        monkeypatch.setattr(target, "replace", interrupted_replace)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="authority write failed"):
        quarantine.atomic_authority_write(path, payload, authority_name=quarantine.AUTHORITY_NAME)
    quarantine.atomic_authority_write(path, payload, authority_name=quarantine.AUTHORITY_NAME)
    quarantine.atomic_authority_write(path, payload, authority_name=quarantine.AUTHORITY_NAME)
    assert quarantine._read_authority(backup)["tx_id"] == "mb_" + "a" * 28


@pytest.mark.parametrize("failpoint", ("rename", "chown", "chmod"))
def test_apply_quarantine_retries_twice_after_metadata_ack_loss(
    failpoint: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "h" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    expected = _build_tree(repo)
    real_rename = os.rename
    real_chown = quarantine.os.chown
    real_chmod = quarantine.os.chmod
    injected = False

    def interrupted_rename(old: Path, new: Path) -> None:
        real_rename(old, new)
        nonlocal injected
        if failpoint == "rename" and not injected:
            injected = True
            raise OSError("injected rename acknowledgement loss")

    def interrupted_chown(path: Path, uid: int, gid: int, **_kwargs: object) -> None:
        real_chown(path, uid, gid)
        nonlocal injected
        if failpoint == "chown" and not injected:
            injected = True
            raise OSError("injected chown acknowledgement loss")

    def interrupted_chmod(path: Path, mode: int, **_kwargs: object) -> None:
        real_chmod(path, mode)
        nonlocal injected
        if failpoint == "chmod" and not injected:
            injected = True
            raise OSError("injected chmod acknowledgement loss")

    monkeypatch.setattr(quarantine.os, "rename", interrupted_rename)
    monkeypatch.setattr(quarantine.os, "chown", interrupted_chown)
    monkeypatch.setattr(quarantine.os, "chmod", interrupted_chmod)
    with pytest.raises(OSError, match="injected"):
        quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_quarantined(repo, expected, tx_id)


@pytest.mark.parametrize("failpoint", ("rename", "chown", "chmod"))
def test_restore_quarantine_retries_twice_after_metadata_ack_loss(
    failpoint: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "i" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    expected = _build_tree(repo)
    quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_quarantined(repo, expected, tx_id)
    real_rename = os.rename
    real_chown = quarantine.os.chown
    real_chmod = quarantine.os.chmod
    injected = False

    def interrupted_rename(old: Path, new: Path) -> None:
        real_rename(old, new)
        nonlocal injected
        if failpoint == "rename" and not injected:
            injected = True
            raise OSError("injected rollback rename acknowledgement loss")

    def interrupted_chown(path: Path, uid: int, gid: int, **_kwargs: object) -> None:
        real_chown(path, uid, gid)
        nonlocal injected
        if failpoint == "chown" and not injected:
            injected = True
            raise OSError("injected rollback chown acknowledgement loss")

    def interrupted_chmod(path: Path, mode: int, **_kwargs: object) -> None:
        real_chmod(path, mode)
        nonlocal injected
        if failpoint == "chmod" and not injected:
            injected = True
            raise OSError("injected rollback chmod acknowledgement loss")

    monkeypatch.setattr(quarantine.os, "rename", interrupted_rename)
    monkeypatch.setattr(quarantine.os, "chown", interrupted_chown)
    monkeypatch.setattr(quarantine.os, "chmod", interrupted_chmod)
    with pytest.raises(OSError, match="injected"):
        quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_live_matches(repo, expected)


def test_mount_recheck_retries_twice_when_bind_appears_mid_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "j" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    _build_tree(repo)
    expected = quarantine.probe_evidence(repo)
    state = {"phase": "probe", "attempts": 0}

    def _phase_mountinfo(path: Path | None = None) -> str:
        if path is not None:
            return Path(path).read_text(encoding="utf-8")
        if state["phase"] == "probe":
            return safety.read_mountinfo_text(None)
        return _mountinfo_with_bind(quarantine.nested_runtime_path(repo), "bound")

    monkeypatch.setattr(safety, "read_mountinfo_text", _phase_mountinfo)
    state["phase"] = "apply"
    (quarantine.nested_runtime_path(repo) / "bound").mkdir()
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="mount point"):
        quarantine.apply_quarantine(repo, backup, expected, tx_id)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="mount point"):
        quarantine.apply_quarantine(repo, backup, expected, tx_id)


def test_openat_listdir_failure_redacts_whole_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "file").write_bytes(b"x")
    secret = str(nested / "secret-member")
    nested_fd: dict[str, int] = {"value": -1}
    real_listdir = os.listdir
    real_open = os.open

    def capture_open(path: str | os.PathLike[str], flags: int, *args: object, **kwargs: object) -> int:
        descriptor = real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        if Path(path) == nested:
            nested_fd["value"] = descriptor
        return descriptor

    def broken_listdir(fd: int) -> list[str]:
        if fd == nested_fd["value"]:
            raise OSError(13, "permission denied", secret)
        return real_listdir(fd)

    monkeypatch.setattr(safety.os, "open", capture_open)
    monkeypatch.setattr(safety.os, "listdir", broken_listdir)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="unsafe object") as exc_info:
        quarantine.probe_evidence(repo)
    _assert_redacted_chain(exc_info.value, secret)


def test_openat_dir_open_failure_redacts_whole_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    subdir = nested / "sub"
    subdir.mkdir()
    secret = str(subdir / "hidden")
    real_open = os.open

    def poisoned_open(
        path: str | os.PathLike[str],
        flags: int,
        *args: object,
        dir_fd: int | None = None,
        **kwargs: object,
    ) -> int:
        if dir_fd is not None and path == "sub":
            raise OSError(13, "permission denied", secret)
        return real_open(path, flags, *args, dir_fd=dir_fd, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(safety.os, "open", poisoned_open)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="unsafe object") as exc_info:
        quarantine.probe_evidence(repo)
    _assert_redacted_chain(exc_info.value, secret)


def test_authenticated_loader_rejects_competing_sys_modules_without_trusting_file(
    tmp_path: Path,
) -> None:
    from scripts.ha import bootstrap_nested_runtime_loader as loader

    ha_dir = Path(__file__).resolve().parents[2] / "scripts/ha"
    real_path = tmp_path / "bootstrap_nested_runtime_safety.py"
    real_path.write_bytes((ha_dir / "bootstrap_nested_runtime_safety.py").read_bytes())
    (tmp_path / "bootstrap_nested_runtime_mount.py").write_bytes(
        (ha_dir / "bootstrap_nested_runtime_mount.py").read_bytes()
    )
    spoof = types.ModuleType("bootstrap_nested_runtime_safety@spoof")
    spoof.__file__ = str(real_path)
    spoof.__nested_runtime_source_sha256__ = "deadbeef"
    digest_name = loader.authenticated_module_name("bootstrap_nested_runtime_safety", real_path)
    loader.sys.modules[digest_name] = spoof
    loaded = loader.load_authenticated_module("bootstrap_nested_runtime_safety", real_path)
    assert loaded is not spoof
    assert getattr(loaded, "__nested_runtime_source_sha256__", "") != "deadbeef"
    assert getattr(loaded, "__file__", None) == str(real_path.resolve())
