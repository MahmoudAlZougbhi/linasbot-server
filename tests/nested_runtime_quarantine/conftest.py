"""Shared fixtures for nested-runtime quarantine tests."""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ha" / "bootstrap_nested_runtime_quarantine.py"
BOOTSTRAP_PATH = ROOT / "scripts" / "ha" / "bootstrap_meta_ha_contract.py"


def _load(path: Path, name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quarantine = _load(MODULE_PATH, "bootstrap_nested_runtime_quarantine_test")
safety = quarantine._safety
evidence = quarantine._evidence
bootstrap = _load(BOOTSTRAP_PATH, "bootstrap_meta_ha_contract_nested_test")

_DEFAULT_MOUNTINFO = "1 0 0:0 / / rw shared:1 - rootfs root rw\n"


@pytest.fixture(autouse=True)
def _default_mountinfo(monkeypatch: pytest.MonkeyPatch) -> None:
    real_read = safety.read_mountinfo_text

    def _read(path: Path | None = None) -> str:
        if path is not None:
            return Path(path).read_text(encoding="utf-8")
        try:
            return real_read(None)
        except RuntimeError:
            return _DEFAULT_MOUNTINFO

    monkeypatch.setattr(safety, "read_mountinfo_text", _read)


def _patch_secure_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    real_lstat = os.lstat

    def fake_lstat(path: os.PathLike[str] | str, *args: object, **kwargs: object) -> os.stat_result:
        result = real_lstat(path, *args, **kwargs)  # type: ignore[arg-type]
        if Path(path).name == quarantine.AUTHORITY_NAME:
            mode = stat.S_IFREG | 0o600
            return os.stat_result(
                (
                    mode,
                    result.st_ino,
                    result.st_dev,
                    result.st_nlink,
                    0,
                    0,
                    result.st_size,
                    result.st_atime,
                    result.st_mtime,
                    result.st_ctime,
                )
            )
        return result

    monkeypatch.setattr(safety.os, "lstat", fake_lstat)
    monkeypatch.setattr(quarantine._safety, "member_lstat", lambda path: fake_lstat(path))


def _patch_chown(monkeypatch: pytest.MonkeyPatch) -> None:
    owners: dict[Path, tuple[int, int]] = {}
    owners_by_ino: dict[tuple[int, int], tuple[int, int]] = {}
    modes: dict[Path, int] = {}
    modes_by_ino: dict[tuple[int, int], int] = {}

    def fake_chown(path: os.PathLike[str] | str, uid: int, gid: int, **_kwargs: object) -> None:
        resolved = Path(path)
        result = os.lstat(resolved)
        owners[resolved] = (uid, gid)
        owners_by_ino[(result.st_dev, result.st_ino)] = (uid, gid)

    def fake_chmod(path: os.PathLike[str] | str, mode: int, **_kwargs: object) -> None:
        resolved = Path(path)
        result = os.lstat(resolved)
        modes[resolved] = mode
        modes_by_ino[(result.st_dev, result.st_ino)] = mode

    real_lstat = os.lstat

    def fake_lstat(path: os.PathLike[str] | str, *args: object, **kwargs: object) -> os.stat_result:
        result = real_lstat(path, *args, **kwargs)  # type: ignore[arg-type]
        resolved = Path(path)
        owner = owners.get(resolved) or owners_by_ino.get((result.st_dev, result.st_ino))
        mode = (
            modes.get(resolved) if modes.get(resolved) is not None else modes_by_ino.get((result.st_dev, result.st_ino))
        )
        if owner is None and mode is None:
            return result
        st_mode = result.st_mode
        if mode is not None:
            if stat.S_ISDIR(st_mode):
                st_mode = stat.S_IFDIR | mode
            elif stat.S_ISREG(st_mode):
                st_mode = stat.S_IFREG | mode
            elif stat.S_ISLNK(st_mode):
                st_mode = stat.S_IFLNK | mode
        return os.stat_result(
            (
                st_mode,
                result.st_ino,
                result.st_dev,
                result.st_nlink,
                owner[0] if owner is not None else result.st_uid,
                owner[1] if owner is not None else result.st_gid,
                result.st_size,
                result.st_atime,
                result.st_mtime,
                result.st_ctime,
            )
        )

    for target in (quarantine.os, safety.os):
        monkeypatch.setattr(target, "chown", fake_chown)
        monkeypatch.setattr(target, "chmod", fake_chmod)
        monkeypatch.setattr(target, "lstat", fake_lstat)
    monkeypatch.setattr(quarantine.Path, "lstat", lambda self, *args, **kwargs: fake_lstat(self, *args, **kwargs))
    monkeypatch.setattr(safety, "member_lstat", fake_lstat)
    monkeypatch.setattr(evidence, "member_lstat", fake_lstat)


def _build_tree(repo: Path) -> dict[str, object]:
    nested = repo / quarantine.NESTED_RUNTIME_NAME
    nested.mkdir(parents=True)
    (nested / "main.py").write_text("print('legacy')\n", encoding="utf-8")
    (nested / "venv").mkdir()
    (nested / "venv" / "bin").mkdir(parents=True)
    (nested / "venv" / "bin" / "python").write_bytes(b"#!/bin/sh\necho py\n")
    cache = nested / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-313.pyc").write_bytes(b"bytecode")
    os.symlink("main.py", nested / "alias.py")
    nested.chmod(0o755)
    return quarantine.probe_evidence(repo)


def _authority_payload(tx_id: str = "mb_" + "a" * 28) -> bytes:
    evidence_doc = {"schema": 1, "present": False}
    return (
        evidence._canonical(
            {
                "schema": 1,
                "tx_id": tx_id,
                "evidence": evidence_doc,
                "quarantine_name": f".quarantine-nested-runtime-{tx_id}",
                "evidence_sha256": quarantine.digest_evidence(evidence_doc),
            }
        )
        + b"\n"
    )


def _mountinfo_with_bind(root: Path, relative: str) -> str:
    mount_point = root if relative == "." else root / relative
    return f"100 1 0:1 / {mount_point.resolve()} rw shared:1 - bind /tmp/bind bind rw\n{_DEFAULT_MOUNTINFO}"


def _patch_mountinfo(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    def _read(path: Path | None = None) -> str:
        if path is not None:
            return Path(path).read_text(encoding="utf-8")
        return text

    monkeypatch.setattr(safety, "read_mountinfo_text", _read)
