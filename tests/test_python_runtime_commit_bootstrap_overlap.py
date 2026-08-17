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


def test_peer_stage_skips_only_commit_bootstrap_markers() -> None:
    assert "skip=commit_bootstrap()" in peer.REMOTE_STAGE
    assert 'if skip and rel in ("bootstrap.active","bootstrap.coordinator.json"): continue' in peer.REMOTE_STAGE
    assert 'payload.get("decision")=="commit"' in peer.REMOTE_STAGE
    assert 'payload.get("status")=="applied"' in peer.REMOTE_STAGE
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
