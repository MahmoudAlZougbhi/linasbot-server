"""Commit-decided bootstrap journals may overlap a QG helper refresh."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha import python_runtime_provision_ingest_contract as ingest_contract
from scripts.ha import python_runtime_provision_peer as peer
from scripts.ha import python_runtime_provision_state as state
from scripts.ha.python_runtime_archive_contract import ProvisionError


def test_runtime_collisions_allow_only_commit_decided_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = state.ProvisionPaths(state_root=tmp_path, runtime=tmp_path / "runtime", lock_path=tmp_path / "lock")
    (tmp_path / "bootstrap.active").write_text("active\n", encoding="utf-8")
    (tmp_path / "bootstrap.coordinator.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(state, "_load_json", lambda _path: {"schema": 2, "decision": "rollback"})
    with pytest.raises(ProvisionError, match="bootstrap.active"):
        state.assert_no_collisions(paths)

    monkeypatch.setattr(state, "_load_json", lambda _path: {"schema": 2, "decision": "commit"})
    state.assert_no_collisions(paths)

    (tmp_path / "deploy.active").write_text("deploy\n", encoding="utf-8")
    with pytest.raises(ProvisionError, match="deploy.active"):
        state.assert_no_collisions(paths)


def test_runtime_overlap_allows_admitted_bootstrap_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tx_id = "ab" * 16
    paths = state.ProvisionPaths(
        state_root=tmp_path, runtime=tmp_path / "runtime", lock_path=tmp_path / "lock"
    )
    (tmp_path / "bootstrap.active").write_text("{}\n", encoding="utf-8")
    journal = tmp_path / "journal.json"
    journal.write_text("{}\n", encoding="utf-8")
    real_path = state.Path

    def fake_path(*args: object, **kwargs: object) -> Path:
        if args and "linasbot-meta-bootstrap-" in str(args[0]):
            return journal
        return real_path(*args, **kwargs)

    def fake_load(path: Path) -> dict[str, object]:
        if path == tmp_path / "bootstrap.active":
            return {"tx_id": tx_id}
        if path == journal:
            return {"status": "admitted", "tx_id": tx_id}
        raise AssertionError(path)

    monkeypatch.setattr(state, "Path", fake_path)
    monkeypatch.setattr(state, "_load_json", fake_load)
    state.assert_no_collisions(paths)

    def fake_prepared(path: Path) -> dict[str, object]:
        if path == tmp_path / "bootstrap.active":
            return {"tx_id": tx_id}
        if path == journal:
            return {"status": "prepared", "tx_id": tx_id}
        raise AssertionError(path)

    monkeypatch.setattr(state, "_load_json", fake_prepared)
    with pytest.raises(ProvisionError, match="bootstrap.active"):
        state.assert_no_collisions(paths)


def test_peer_stage_skips_only_commit_bootstrap_markers() -> None:
    assert "skip=commit_bootstrap()" in peer.REMOTE_STAGE
    assert 'if skip and rel in ("bootstrap.active","bootstrap.coordinator.json"): continue' in peer.REMOTE_STAGE
    assert 'payload.get("decision")=="commit"' in peer.REMOTE_STAGE
    assert 'payload.get("status") in {"applied","admitted","commit_proved","committed"}' in peer.REMOTE_STAGE
    assert "/opt/.linasbot-meta-bootstrap-" in peer.REMOTE_STAGE


def test_ingest_skips_only_commit_bootstrap_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    (state_root / "bootstrap.active").write_bytes(b"active")
    (state_root / "bootstrap.coordinator.json").write_bytes(b"{}")
    monkeypatch.setattr(ingest_contract, "LOCK_PATH", tmp_path / "common.lock")
    monkeypatch.setattr(ingest_contract.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(ingest_contract, "_commit_decided_bootstrap", lambda _root: False)
    with pytest.raises(ingest_contract.IngestError, match="bootstrap.active"):
        with ingest_contract.common_lock(state_root):
            pytest.fail("rollback journal must still collide")
    monkeypatch.setattr(ingest_contract, "_commit_decided_bootstrap", lambda _root: True)
    with ingest_contract.common_lock(state_root):
        pass
    (state_root / "deploy.active").write_bytes(b"deploy")
    with pytest.raises(ingest_contract.IngestError, match="deploy.active"):
        with ingest_contract.common_lock(state_root):
            pytest.fail("deploy overlap must still collide")


def test_ingest_skips_undecided_runtime_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    (state_root / "python-runtime-provision.coordinator.json").write_bytes(b"{}")
    monkeypatch.setattr(ingest_contract, "LOCK_PATH", tmp_path / "common.lock")
    monkeypatch.setattr(ingest_contract.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(ingest_contract, "_incomplete_runtime_snapshot", lambda _root: False)
    with pytest.raises(ingest_contract.IngestError, match="python-runtime-provision.coordinator.json"):
        with ingest_contract.common_lock(state_root):
            pytest.fail("decided runtime coordinator must still collide")
    monkeypatch.setattr(ingest_contract, "_incomplete_runtime_snapshot", lambda _root: True)
    with ingest_contract.common_lock(state_root):
        pass
