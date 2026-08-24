from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha import meta_peer_stage_gate as gate
from scripts.ha import sync_meta_env_to_peer as sync

SHA = "a" * 40


def _env(path: Path, *, node: str, app_id: str, secret: str) -> None:
    path.write_text(
        f"ENVIRONMENT=production\nMETA_APP_ID={app_id}\nMETA_APP_SECRET={secret}\nMETA_DELETION_NODE_ID={node}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _state_root(tmp_path: Path) -> Path:
    root = tmp_path / "meta-ha"
    root.mkdir(mode=0o700, parents=True)
    return root


def _arm_maintenance(state_root: Path, volatile: Path) -> None:
    sync._arm_marker(state_root / sync.PERSISTENT_MAINTENANCE_NAME)
    sync._arm_marker(volatile)


def _patch_peer_gate(monkeypatch: pytest.MonkeyPatch, volatile: Path) -> None:
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(sync, "_verify_worker_units_quiesced", lambda: None)


def test_require_peer_stage_authority_accepts_quiesced_peer_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    _env(env_path, node="node02", app_id="app", secret="secret")
    state_root = _state_root(tmp_path / "state")
    volatile = tmp_path / "run-maintenance"
    _arm_maintenance(state_root, volatile)
    _patch_peer_gate(monkeypatch, volatile)
    monkeypatch.setattr(sync, "ENV_PATH", env_path)
    worker_state = sync._worker_state_payload(
        tx_id="b" * 32,
        role="peer",
        expected_sha=SHA,
        old_fingerprint=sync._meta_fingerprint({"META_APP_ID": "app", "META_APP_SECRET": "secret"}, SHA),
        units={unit: {"enabled": False, "active": False} for unit in sync.WORKER_UNITS},
        status="quiesced",
    )
    sync._write_worker_state(state_root, worker_state)

    result = gate.require_peer_stage_authority(state_root, expected_sha=SHA)

    assert result["tx_id"] == "b" * 32


def test_require_peer_stage_authority_rejects_coordinator_role(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    _env(env_path, node="node02", app_id="app", secret="secret")
    state_root = _state_root(tmp_path / "state")
    volatile = tmp_path / "run-maintenance"
    _arm_maintenance(state_root, volatile)
    _patch_peer_gate(monkeypatch, volatile)
    monkeypatch.setattr(sync, "ENV_PATH", env_path)
    worker_state = sync._worker_state_payload(
        tx_id="c" * 32,
        role="coordinator",
        expected_sha=SHA,
        old_fingerprint=sync._meta_fingerprint({"META_APP_ID": "app", "META_APP_SECRET": "secret"}, SHA),
        units={unit: {"enabled": False, "active": False} for unit in sync.WORKER_UNITS},
        status="quiesced",
    )
    sync._write_worker_state(state_root, worker_state)

    with pytest.raises(RuntimeError, match="does not match durable authority"):
        gate.require_peer_stage_authority(state_root, expected_sha=SHA)
