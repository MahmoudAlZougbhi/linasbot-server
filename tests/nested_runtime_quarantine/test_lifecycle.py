"""Nested-runtime quarantine lifecycle tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.nested_runtime_quarantine.conftest import (
    _build_tree,
    _patch_chown,
    _patch_secure_authority,
    evidence,
    quarantine,
)


def test_absent_tree_binds_absence_without_member_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_secure_authority(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    observed = quarantine.probe_evidence(repo)
    backup = tmp_path / "backup"
    backup.mkdir()
    quarantine.apply_quarantine(repo, backup, observed, "mb_" + "a" * 28)
    quarantine.assert_absent(repo)
    assert observed == {"schema": 1, "present": False}
    assert quarantine.digest_evidence(observed) == quarantine.digest_evidence(quarantine.absent_evidence())
    plan_blob = json.dumps(observed, sort_keys=True)
    assert quarantine.NESTED_RUNTIME_NAME not in plan_blob
    assert "main.py" not in plan_blob


def test_synthetic_tree_quarantine_commit_and_rollback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "b" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    expected = _build_tree(repo)
    assert expected["present"] is True
    assert expected["file_count"] == 3
    assert expected["symlink_count"] == 1
    assert "main.py" not in json.dumps(expected, sort_keys=True)

    quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_quarantined(repo, expected, tx_id)
    quarantine.assert_absent(repo)

    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_live_matches(repo, expected)
    assert not quarantine.quarantine_destination(repo, tx_id).exists()


@pytest.mark.parametrize("failpoint", ("rename", "chown", "chmod"))
def test_quarantine_replays_rename_and_metadata_ack_loss(
    failpoint: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "c" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    expected = _build_tree(repo)
    real_rename = os.rename
    real_chown = quarantine.os.chown
    real_chmod = quarantine.os.chmod
    injected = False

    def interrupted_rename(old: Path, new: Path) -> None:
        nonlocal injected
        real_rename(old, new)
        if failpoint == "rename" and not injected:
            injected = True
            raise OSError("injected rename acknowledgement loss")

    def interrupted_chown(path: Path, uid: int, gid: int, **_kwargs: object) -> None:
        nonlocal injected
        real_chown(path, uid, gid)
        if failpoint == "chown" and not injected:
            injected = True
            raise OSError("injected chown acknowledgement loss")

    def interrupted_chmod(path: Path, mode: int, **_kwargs: object) -> None:
        nonlocal injected
        real_chmod(path, mode)
        if failpoint == "chmod" and not injected:
            injected = True
            raise OSError("injected chmod acknowledgement loss")

    monkeypatch.setattr(quarantine.os, "rename", interrupted_rename)
    monkeypatch.setattr(quarantine.os, "chown", interrupted_chown)
    monkeypatch.setattr(quarantine.os, "chmod", interrupted_chmod)
    with pytest.raises(OSError, match="injected"):
        quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_quarantined(repo, expected, tx_id)
    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_live_matches(repo, expected)


def test_mutation_during_transaction_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "d" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    expected = _build_tree(repo)
    (quarantine.nested_runtime_path(repo) / "main.py").write_text("mutated\n", encoding="utf-8")
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="evidence changed"):
        quarantine.apply_quarantine(repo, backup, expected, tx_id)


def test_special_file_and_cross_device_and_collision_reject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    fifo = nested / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="special file"):
        quarantine.probe_evidence(repo)

    fifo.unlink()
    (nested / "file").write_bytes(b"x")
    evidence = quarantine.probe_evidence(repo)
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "e" * 28
    quar = quarantine.quarantine_destination(repo, tx_id)
    quar.mkdir()
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="collides"):
        quarantine.apply_quarantine(repo, backup, evidence, tx_id)

    quar.rmdir()
    other_parent = tmp_path / "other-parent"
    other_parent.mkdir()

    def fake_destination(_repo_dir: Path, bound_tx_id: str) -> Path:
        return other_parent / f".quarantine-nested-runtime-{bound_tx_id}"

    monkeypatch.setattr(quarantine, "quarantine_destination", fake_destination)
    live = quarantine.nested_runtime_path(repo)
    real_stat = os.stat

    def fake_stat(path: os.PathLike[str] | str, *args: object, **kwargs: object) -> os.stat_result:
        result = real_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        if Path(path) == live:
            return os.stat_result(
                (
                    result.st_mode,
                    result.st_ino,
                    result.st_dev + 1,
                    result.st_nlink,
                    result.st_uid,
                    result.st_gid,
                    result.st_size,
                    result.st_atime,
                    result.st_mtime,
                    result.st_ctime,
                )
            )
        return result

    monkeypatch.setattr(quarantine.os, "stat", fake_stat)
    _patch_secure_authority(monkeypatch)
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="cross devices"):
        quarantine.apply_quarantine(repo, backup, evidence, tx_id)


def test_opaque_absolute_and_cyclic_symlinks_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "g" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "main.py").write_text("print('legacy')\n", encoding="utf-8")
    venv_bin = nested / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    os.symlink("/usr/bin/python3.13", venv_bin / "python")
    os.symlink("loop", nested / "loop")
    expected = quarantine.probe_evidence(repo)
    assert expected["symlink_count"] == 2
    # absolute venv python link preserved as opaque bytes
    quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_quarantined(repo, expected, tx_id)
    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_live_matches(repo, expected)


def test_internal_directory_symlink_apply_and_rollback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "f" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "main.py").write_text("print('legacy')\n", encoding="utf-8")
    subdir = nested / "links"
    subdir.mkdir()
    os.symlink("../main.py", subdir / "up.py")
    os.symlink("up.py", subdir / "alias.py")
    expected = quarantine.probe_evidence(repo)
    assert expected["symlink_count"] == 2

    quarantine.apply_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_quarantined(repo, expected, tx_id)
    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_live_matches(repo, expected)


def test_portable_content_identity_ignores_node_local_root_metadata(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    for repo in (repo_a, repo_b):
        nested = repo / quarantine.NESTED_RUNTIME_NAME
        nested.mkdir()
        (nested / "main.py").write_text("print('legacy')\n", encoding="utf-8")
    left = quarantine.probe_evidence(repo_a)
    right = quarantine.probe_evidence(repo_b)
    assert left != right
    assert evidence.portable_content_identity(left) == evidence.portable_content_identity(right)


def test_publish_authority_before_drain_allows_safe_rollback_without_quarantine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "9" * 28
    _patch_chown(monkeypatch)
    _patch_secure_authority(monkeypatch)
    expected = _build_tree(repo)
    quarantine.publish_authority(repo, backup, expected, tx_id)
    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_live_matches(repo, expected)


def test_authority_partial_prefix_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_secure_authority(monkeypatch)
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "a" * 28
    evidence_doc = {"schema": 1, "present": False}
    payload = (
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
    path = quarantine.authority_path(backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload[: len(payload) // 2])
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="authority changed"):
        quarantine.atomic_authority_write(path, payload, authority_name=quarantine.AUTHORITY_NAME)


def test_authority_write_replays_after_exact_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_secure_authority(monkeypatch)
    backup = tmp_path / "backup"
    backup.mkdir()
    tx_id = "mb_" + "a" * 28
    evidence_doc = {"schema": 1, "present": False}
    payload = (
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
    path = quarantine.authority_path(backup)
    quarantine.atomic_authority_write(path, payload, authority_name=quarantine.AUTHORITY_NAME)
    quarantine.atomic_authority_write(path, payload, authority_name=quarantine.AUTHORITY_NAME)
    assert quarantine._read_authority(backup)["tx_id"] == tx_id


def test_cyclic_symlink_is_preserved_opaque(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    os.symlink("loop", nested / "loop")
    observed = quarantine.probe_evidence(repo)
    assert observed["symlink_count"] == 1
    assert observed["present"] is True
