"""Focused contracts for bootstrap nested-runtime quarantine."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "ha" / "bootstrap_nested_runtime_quarantine.py"
EVIDENCE_PATH = ROOT / "scripts" / "ha" / "bootstrap_nested_runtime_evidence.py"
BOOTSTRAP_PATH = ROOT / "scripts" / "ha" / "bootstrap_meta_ha_contract.py"


def _load(path: Path, name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quarantine = _load(MODULE_PATH, "bootstrap_nested_runtime_quarantine_test")
evidence = _load(EVIDENCE_PATH, "bootstrap_nested_runtime_evidence_test")
bootstrap = _load(BOOTSTRAP_PATH, "bootstrap_meta_ha_contract_nested_test")


def _patch_chown(monkeypatch: pytest.MonkeyPatch) -> None:
    owners: dict[Path, tuple[int, int]] = {}

    def fake_chown(path: os.PathLike[str] | str, uid: int, gid: int, **_kwargs: object) -> None:
        owners[Path(path)] = (uid, gid)

    real_lstat = os.lstat

    def fake_lstat(path: os.PathLike[str] | str, *args: object, **kwargs: object) -> os.stat_result:
        result = real_lstat(path, *args, **kwargs)  # type: ignore[arg-type]
        owner = owners.get(Path(path))
        if owner is not None:
            return os.stat_result(
                (
                    result.st_mode,
                    result.st_ino,
                    result.st_dev,
                    result.st_nlink,
                    owner[0],
                    owner[1],
                    result.st_size,
                    result.st_atime,
                    result.st_mtime,
                    result.st_ctime,
                )
            )
        return result

    monkeypatch.setattr(quarantine.os, "chown", fake_chown)
    monkeypatch.setattr(quarantine.os, "lstat", fake_lstat)
    monkeypatch.setattr(quarantine.Path, "lstat", lambda self, *args, **kwargs: fake_lstat(self, *args, **kwargs))


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


def test_absent_tree_binds_absence_without_member_names(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = quarantine.probe_evidence(repo)
    backup = tmp_path / "backup"
    backup.mkdir()
    quarantine.apply_quarantine(repo, backup, evidence, "mb_" + "a" * 28)
    quarantine.assert_absent(repo)
    assert evidence == {"schema": 1, "present": False}
    assert quarantine.digest_evidence(evidence) == quarantine.digest_evidence(quarantine.absent_evidence())
    plan_blob = json.dumps(evidence, sort_keys=True)
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
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="cross devices"):
        quarantine.apply_quarantine(repo, backup, evidence, tx_id)


def test_unsafe_absolute_symlink_rejects_probe_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = quarantine.nested_runtime_path(repo)
    nested.mkdir()
    (nested / "main.py").write_text("print('legacy')\n", encoding="utf-8")
    os.symlink("/etc/passwd", nested / "escape")
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="not relocatable"):
        quarantine.probe_evidence(repo)

    shutil.rmtree(nested)
    nested.mkdir()
    (nested / "main.py").write_text("print('legacy')\n", encoding="utf-8")
    os.symlink("../outside", nested / "relative-escape")
    (repo / "outside").mkdir()
    with pytest.raises(quarantine.NestedRuntimeQuarantineError, match="escapes"):
        quarantine.probe_evidence(repo)


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
    expected = _build_tree(repo)
    quarantine.publish_authority(repo, backup, expected, tx_id)
    quarantine.restore_quarantine(repo, backup, expected, tx_id)
    quarantine.assert_live_matches(repo, expected)


def test_authority_write_replays_after_partial_prefix(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    payload = evidence._canonical({"schema": 1, "tx_id": "mb_" + "a" * 28, "evidence": {"present": False}}) + b"\n"
    path = quarantine.authority_path(backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload[: len(payload) // 2])
    quarantine._atomic_authority_write(path, payload)
    assert path.read_bytes() == payload


def test_repo_bytecode_manifest_excludes_nested_runtime_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    nested_cache = repository / quarantine.NESTED_RUNTIME_NAME / "pkg" / "__pycache__"
    nested_cache.mkdir(parents=True)
    (nested_cache / "legacy.cpython-313.pyc").write_bytes(b"nested")
    top_cache = repository / "pkg" / "__pycache__"
    top_cache.mkdir(parents=True)
    (top_cache / "live.cpython-313.pyc").write_bytes(b"live")
    monkeypatch.setattr(bootstrap, "REPO_DIR", repository)
    manifest = bootstrap._repo_bytecode_manifest()
    paths = {entry["path"] for entry in manifest if entry["type"] == "file"}
    assert "pkg/__pycache__/live.cpython-313.pyc" in paths
    assert not any(str(path).startswith(f"{quarantine.NESTED_RUNTIME_NAME}/") for path in paths)


def test_bootstrap_wires_nested_runtime_authority() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    prepare = source[source.index("def _node_prepare") : source.index("def _node_abort_prepare")]
    drain = source[source.index("def _node_drain") : source.index("def _transition_historical_env")]
    combined = source[source.index("def _combined_plan") : source.index("def _confirmation")]
    verify = source[source.index("def _node_verify") : source.index("def _quiesce_and_disable_units")]
    rollback = source[source.index("def _node_rollback") : source.index("def _node_admit_rollback")]
    commit = source[source.index("def _bootstrap_commit_proof_payload") : source.index("def _read_bootstrap_commit_proof")]
    assert "_nested.publish_authority(" in prepare
    assert "_nested.apply_quarantine(" in drain
    assert "portable_content_identity(" in combined
    assert "_nested_evidence" in source
    assert "_nested.assert_quarantined(" in verify
    assert "_nested.restore_quarantine(" in rollback
    assert '"nested_runtime_present"' in commit
    assert '"nested_runtime_evidence_sha256"' in commit
    assert '"nested_runtime_quarantined"' in commit
    assert "nested_runtime = _nested.probe_evidence(REPO_DIR)" in source
