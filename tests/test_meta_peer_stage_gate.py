from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha import meta_peer_stage_gate as gate
from scripts.ha import sync_meta_env_to_peer as sync

SHA = "a" * 40


def _state_root(tmp_path: Path) -> Path:
    root = tmp_path / "meta-ha"
    root.mkdir(mode=0o700, parents=True)
    return root


def _arm_maintenance(state_root: Path, volatile: Path) -> None:
    sync._arm_marker(state_root / sync.PERSISTENT_MAINTENANCE_NAME)
    sync._arm_marker(volatile)


def test_require_peer_stage_authority_accepts_quiesced_peer_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("LINAS_NODE_ID=node02\nMETA_APP_ID=app\n", encoding="utf-8")
    state_root = _state_root(tmp_path / "state")
    volatile = tmp_path / "run-maintenance"
    _arm_maintenance(state_root, volatile)
    monkeypatch.setattr(sync, "ENV_PATH", env_path)
    monkeypatch.setattr(sync, "PEER_NODE_ID", "node02")
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(sync, "_verify_release", lambda _sha: None)
    worker_state = sync._worker_state_payload(
        tx_id="b" * 32,
        role="peer",
        expected_sha=SHA,
        old_fingerprint=sync._meta_fingerprint({"META_APP_ID": "app"}, SHA),
        units={unit: {"enabled": False, "active": False} for unit in sync.WORKER_UNITS},
        status="quiesced",
    )
    sync._write_worker_state(state_root, worker_state)
    monkeypatch.setattr(sync, "_worker_unit_state", lambda unit: {"enabled": False, "active": False})

    result = gate.require_peer_stage_authority(state_root, expected_sha=SHA)

    assert result["tx_id"] == "b" * 32


def test_require_peer_stage_authority_rejects_coordinator_role(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("LINAS_NODE_ID=node02\n", encoding="utf-8")
    state_root = _state_root(tmp_path / "state")
    volatile = tmp_path / "run-maintenance"
    _arm_maintenance(state_root, volatile)
    monkeypatch.setattr(sync, "ENV_PATH", env_path)
    monkeypatch.setattr(sync, "PEER_NODE_ID", "node02")
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(sync, "_verify_release", lambda _sha: None)
    worker_state = sync._worker_state_payload(
        tx_id="c" * 32,
        role="coordinator",
        expected_sha=SHA,
        old_fingerprint="d" * 64,
        units={},
        status="quiesced",
    )
    sync._write_worker_state(state_root, worker_state)
    monkeypatch.setattr(sync, "_worker_unit_state", lambda unit: {"enabled": False, "active": False})

    with pytest.raises(RuntimeError, match="does not match durable authority"):
        gate.require_peer_stage_authority(state_root, expected_sha=SHA)
