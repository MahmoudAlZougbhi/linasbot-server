"""Crash, acknowledgement-loss, and security contracts for Meta HA activation."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.ha import sync_meta_env_to_peer as sync

SHA = "a" * 40


def _env(path: Path, *, node: str, app_id: str, secret: str) -> None:
    path.write_text(
        f"ENVIRONMENT=production\nMETA_APP_ID={app_id}\nMETA_APP_SECRET={secret}\nMETA_DELETION_NODE_ID={node}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _state_root(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def _arm(state_root: Path, volatile: Path) -> None:
    sync._arm_marker(state_root / sync.PERSISTENT_MAINTENANCE_NAME)
    sync._arm_marker(volatile)


def _request(
    action: str,
    tx_id: str,
    *,
    values: dict[str, str] | None = None,
    preserve_maintenance: bool | None = None,
) -> dict[str, object]:
    return sync._request_payload(
        action=action,
        expected_sha=SHA,
        tx_id=tx_id,
        maintenance_active=True,
        values=values,
        preserve_maintenance=preserve_maintenance,
    )


def _patch_runtime(monkeypatch: pytest.MonkeyPatch, events: list[str] | None = None) -> None:
    monkeypatch.setattr(sync, "_verify_release", lambda _sha: None)
    monkeypatch.setattr(sync, "_reject_self_peer", lambda _host: None)
    monkeypatch.setattr(
        sync,
        "_capture_worker_units",
        lambda: {unit: {"enabled": True, "active": True} for unit in sync.WORKER_UNITS},
    )
    monkeypatch.setattr(sync, "_quiesce_worker_units", lambda: None)
    monkeypatch.setattr(sync, "_verify_worker_units_quiesced", lambda: None)
    monkeypatch.setattr(sync, "_verify_worker_units_restored", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sync,
        "_systemctl",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sync, "_verify_api_values", lambda _values, **_kwargs: None)
    monkeypatch.setattr(sync, "_verify_runtime_values", lambda _values, **_kwargs: None)

    def _restart(_values: dict[str, str], *, expected_node_id: str, **_kwargs: object) -> None:
        if events is not None:
            events.append(f"restart-{expected_node_id}")

    monkeypatch.setattr(sync, "_restart_api_and_verify", _restart)


def _seed_quiesced_workers(
    state_root: Path,
    env_path: Path,
    *,
    tx_id: str,
    role: str,
) -> dict[str, object]:
    return sync._capture_and_quiesce_workers(
        state_root,
        tx_id=tx_id,
        role=role,
        expected_sha=SHA,
        old_fingerprint=sync._meta_fingerprint(sync._read_meta_values(env_path), SHA),
    )


def _authorize_local_stage(state_root: Path, old_env: Path, *, tx_id: str) -> Path:
    backup = sync._backup_path(state_root)
    sync._install_exact_backup(old_env, backup)
    worker_state = _seed_quiesced_workers(
        state_root,
        old_env,
        tx_id=tx_id,
        role="coordinator",
    )
    old_fingerprint = sync._meta_fingerprint(sync._read_meta_values(old_env), SHA)
    sync._write_stage_authority(
        state_root,
        sync._stage_authority_payload(
            tx_id=tx_id,
            expected_sha=SHA,
            old_fingerprint=old_fingerprint,
            backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
            worker_state_sha256=sync._worker_state_digest(worker_state),
        ),
    )
    return backup


def test_journal_and_backup_are_durable_0600_before_peer_env_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    peer_env = tmp_path / "peer.env"
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(peer_state, volatile)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)
    observed: dict[str, Any] = {}
    real_write = sync._write_meta_values

    def _write(path: Path, values: dict[str, str]) -> None:
        journal = sync._load_journal(peer_state)
        assert journal is not None
        observed["status"] = journal["status"]
        observed["backup_mode"] = sync._backup_path(peer_state).stat().st_mode & 0o777
        observed["backup"] = sync._backup_path(peer_state).read_bytes()
        real_write(path, values)

    monkeypatch.setattr(sync, "_write_meta_values", _write)
    tx_id = "1" * 32
    _seed_quiesced_workers(peer_state, peer_env, tx_id=tx_id, role="peer")
    response = sync._execute_request(
        _request(
            "prepare",
            tx_id,
            values={"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
        ),
        env_path=peer_env,
        lock_path=tmp_path / "peer.lock",
        state_root=peer_state,
    )

    assert response["status"] == "prepared"
    assert observed == {
        "status": "write_started",
        "backup_mode": 0o600,
        "backup": b"ENVIRONMENT=production\nMETA_APP_ID=old\nMETA_APP_SECRET=old-secret\nMETA_DELETION_NODE_ID=node02\n",
    }
    assert sync._journal_path(peer_state).stat().st_mode & 0o777 == 0o600


def test_prepare_sigkill_after_env_write_recovers_old_peer_on_next_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    peer_env = tmp_path / "peer.env"
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    original = peer_env.read_bytes()
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(peer_state, volatile)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)
    real_write = sync._write_meta_values

    def _sigkill_window(path: Path, values: dict[str, str]) -> None:
        real_write(path, values)
        raise KeyboardInterrupt("simulated SIGKILL boundary")

    monkeypatch.setattr(sync, "_write_meta_values", _sigkill_window)
    tx_id = "2" * 32
    _seed_quiesced_workers(peer_state, peer_env, tx_id=tx_id, role="peer")
    with pytest.raises(KeyboardInterrupt):
        sync._execute_request(
            _request(
                "prepare",
                tx_id,
                values={"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
            ),
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        )
    assert sync._load_journal(peer_state)["status"] == "write_started"  # type: ignore[index]

    monkeypatch.setattr(sync, "_write_meta_values", real_write)
    response = sync._execute_request(
        _request("query", tx_id),
        env_path=peer_env,
        lock_path=tmp_path / "peer.lock",
        state_root=peer_state,
    )

    assert response["status"] == "rolled_back"
    assert peer_env.read_bytes() == original
    assert sync._backup_path(peer_state).is_file()
    assert sync._persistent_maintenance_path(peer_state).is_file()


def test_peer_crash_after_backup_before_journal_is_queryable_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    peer_env = tmp_path / "peer.env"
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(peer_state, volatile)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)
    tx_id = "7" * 32
    _seed_quiesced_workers(peer_state, peer_env, tx_id=tx_id, role="peer")
    sync._install_exact_backup(peer_env, sync._backup_path(peer_state))

    query_payload = _request("query", tx_id)
    query = sync._execute_request(
        query_payload,
        env_path=peer_env,
        lock_path=tmp_path / "peer.lock",
        state_root=peer_state,
    )
    assert query["status"] == "quiesced"
    assert query["backup_present"] is True
    monkeypatch.setattr(sync, "_peer_command", lambda _host: ["unused"])
    monkeypatch.setattr(
        sync.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result",
            (),
            {"returncode": 0, "stdout": json.dumps(query).encode("utf-8")},
        )(),
    )
    assert sync._call_peer("10.0.0.2", query_payload)["status"] == "quiesced"

    rolled_back = sync._execute_request(
        _request("rollback", tx_id),
        env_path=peer_env,
        lock_path=tmp_path / "peer.lock",
        state_root=peer_state,
    )
    assert rolled_back["status"] == "absent"
    assert not sync._backup_path(peer_state).exists()
    assert sync._load_worker_state(peer_state) is None


def test_transaction_id_mismatch_is_rejected_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    peer_env = tmp_path / "peer.env"
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(peer_state, volatile)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)
    _seed_quiesced_workers(peer_state, peer_env, tx_id="3" * 32, role="peer")
    sync._execute_request(
        _request(
            "prepare",
            "3" * 32,
            values={"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
        ),
        env_path=peer_env,
        lock_path=tmp_path / "peer.lock",
        state_root=peer_state,
    )

    with pytest.raises(RuntimeError, match="does not match"):
        sync._execute_request(
            _request("query", "4" * 32),
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        )
    assert sync._load_journal(peer_state)["tx_id"] == "3" * 32  # type: ignore[index]


def test_journal_rejects_invalid_role_status_combination(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path / "state")
    invalid = sync._journal_payload(
        tx_id="4" * 32,
        role="peer",
        status="prepared",
        expected_sha=SHA,
        old_fingerprint="1" * 64,
        new_fingerprint="2" * 64,
        maintenance_active=True,
    )
    invalid["role"] = "coordinator"
    sync._journal_path(state_root).write_text(json.dumps(invalid), encoding="utf-8")
    sync._journal_path(state_root).chmod(0o600)

    with pytest.raises(RuntimeError, match="role/status"):
        sync._load_journal(state_root)


@pytest.mark.parametrize("unsafe", [False, True])
def test_normal_sync_refuses_active_identity_bootstrap(tmp_path: Path, unsafe: bool) -> None:
    state_root = _state_root(tmp_path / "state")
    sentinel = sync._bootstrap_active_path(state_root)
    if unsafe:
        target = tmp_path / "bootstrap-target"
        target.write_text("active\n", encoding="utf-8")
        target.chmod(0o600)
        sentinel.symlink_to(target)
        match = "security contract"
    else:
        sentinel.write_text("active\n", encoding="utf-8")
        sentinel.chmod(0o600)
        match = "bootstrap transaction"

    with pytest.raises(RuntimeError, match=match):
        sync._load_journal(state_root)


@pytest.mark.parametrize(
    ("path_factory", "label"),
    [
        (sync._deploy_active_path, "release deploy"),
        (sync._deploy_node_active_path, "node release deploy"),
        (sync._bootstrap_coordinator_path, "bootstrap coordinator"),
        (sync._controlled_failover_active_path, "controlled failover"),
        (sync._nfs_retire_active_path, "registry NFS retirement"),
    ],
)
def test_normal_sync_refuses_other_crash_recovery_transactions(
    tmp_path: Path,
    path_factory: Any,
    label: str,
) -> None:
    state_root = _state_root(tmp_path / "state")
    sentinel = path_factory(state_root)
    sentinel.write_text("active\n", encoding="utf-8")
    sentinel.chmod(0o600)

    with pytest.raises(RuntimeError, match=label):
        sync._load_journal(state_root)


def test_peer_lock_is_held_during_prepare_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    peer_env = tmp_path / "peer.env"
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    peer_state = _state_root(tmp_path / "peer-state")
    lock_path = tmp_path / "peer.lock"
    volatile = tmp_path / "run-maintenance"
    _arm(peer_state, volatile)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)
    real_write = sync._write_meta_values

    def _write(path: Path, values: dict[str, str]) -> None:
        with lock_path.open("rb") as competing:
            with pytest.raises(BlockingIOError):
                fcntl.flock(competing.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        real_write(path, values)

    monkeypatch.setattr(sync, "_write_meta_values", _write)
    _seed_quiesced_workers(peer_state, peer_env, tx_id="5" * 32, role="peer")
    sync._execute_request(
        _request(
            "prepare",
            "5" * 32,
            values={"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
        ),
        env_path=peer_env,
        lock_path=lock_path,
        state_root=peer_state,
    )


def test_lost_commit_ack_queries_journal_and_keeps_both_nodes_committed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    local_backup = tmp_path / "local.before"
    peer_env = tmp_path / "peer.env"
    _env(local_backup, node="node01", app_id="old", secret="old-secret")
    _env(local_env, node="node01", app_id="new", secret="new-secret")
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    local_state = _state_root(tmp_path / "local-state")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(local_state, volatile)
    _arm(peer_state, volatile)
    events: list[str] = []
    _patch_runtime(monkeypatch, events)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(
        sync,
        "_read_runtime_meta_values",
        lambda _node: {"META_APP_ID": "old", "META_APP_SECRET": "old-secret"},
    )
    tx_id = "a" * 32
    durable_backup = _authorize_local_stage(local_state, local_backup, tx_id=tx_id)
    _seed_quiesced_workers(peer_state, peer_env, tx_id=tx_id, role="peer")
    commit_ack_lost = False

    def _call(_host: str, payload: dict[str, object]) -> dict[str, object]:
        nonlocal commit_ack_lost
        action = str(payload["action"])
        events.append(f"peer-{action}")
        result = sync._execute_request(
            payload,
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        )
        if action == "commit" and not commit_ack_lost:
            commit_ack_lost = True
            raise RuntimeError("simulated final ACK loss")
        return result

    monkeypatch.setattr(sync, "_call_peer", _call)

    assert (
        sync._send_to_peer(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            local_prestage_backup=durable_backup,
            state_root=local_state,
        )
        == 0
    )
    assert commit_ack_lost is True
    assert events.index("peer-prepare") < events.index("restart-node01") < events.index("peer-commit")
    assert sync._load_journal(local_state)["status"] == "parity_proven"  # type: ignore[index]
    assert sync._load_journal(peer_state)["status"] == "parity_proven"  # type: ignore[index]
    assert sync._read_meta_values(local_env)["META_APP_ID"] == "new"
    assert sync._read_meta_values(peer_env)["META_APP_ID"] == "new"
    assert sync._backup_path(local_state).is_file()
    assert sync._backup_path(peer_state).is_file()


def test_uncertain_peer_never_rolls_local_and_retains_fail_closed_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    local_backup = tmp_path / "local.before"
    _env(local_backup, node="node01", app_id="old", secret="old-secret")
    _env(local_env, node="node01", app_id="new", secret="new-secret")
    local_state = _state_root(tmp_path / "local-state")
    volatile = tmp_path / "run-maintenance"
    _arm(local_state, volatile)
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(
        sync,
        "_read_runtime_meta_values",
        lambda _node: {"META_APP_ID": "old", "META_APP_SECRET": "old-secret"},
    )
    monkeypatch.setattr(
        sync,
        "_call_peer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("peer unreachable")),
    )
    durable_backup = _authorize_local_stage(local_state, local_backup, tx_id="b" * 32)

    with pytest.raises(RuntimeError, match="durable maintenance state retained"):
        sync._send_to_peer(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            local_prestage_backup=durable_backup,
            state_root=local_state,
        )

    assert sync._read_meta_values(local_env)["META_APP_ID"] == "new"
    assert sync._load_journal(local_state) is not None
    assert sync._backup_path(local_state).is_file()
    assert sync._persistent_maintenance_path(local_state).is_file()
    assert volatile.is_file()


def test_coordinator_crash_before_commit_recovers_peer_then_local_rollback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    local_backup = tmp_path / "local.before"
    peer_env = tmp_path / "peer.env"
    _env(local_backup, node="node01", app_id="old", secret="old-secret")
    _env(local_env, node="node01", app_id="new", secret="new-secret")
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    local_state = _state_root(tmp_path / "local-state")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(local_state, volatile)
    _arm(peer_state, volatile)
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(
        sync,
        "_read_runtime_meta_values",
        lambda _node: {"META_APP_ID": "old", "META_APP_SECRET": "old-secret"},
    )
    tx_id = "c" * 32
    durable_backup = _authorize_local_stage(local_state, local_backup, tx_id=tx_id)
    _seed_quiesced_workers(peer_state, peer_env, tx_id=tx_id, role="peer")
    journal, new_values = sync._create_coordinator_transaction(
        expected_sha=SHA,
        local_prestage_backup=durable_backup,
        maintenance_active=True,
        state_root=local_state,
    )
    journal = sync._set_journal_status(local_state, journal, "peer_prepare_started")
    prepare = sync._execute_request(
        _request("prepare", str(journal["tx_id"]), values=new_values),
        env_path=peer_env,
        lock_path=tmp_path / "peer.lock",
        state_root=peer_state,
    )
    assert prepare["status"] == "prepared"
    sync._set_journal_status(local_state, journal, "peer_prepared")

    monkeypatch.setattr(
        sync,
        "_call_peer",
        lambda _host, payload: sync._execute_request(
            payload,
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        ),
    )
    assert (
        sync._recover_only(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            state_root=local_state,
        )
        == 0
    )
    assert sync._read_meta_values(local_env)["META_APP_ID"] == "old"
    assert sync._read_meta_values(peer_env)["META_APP_ID"] == "old"
    assert sync._load_journal(local_state) is None
    assert sync._load_journal(peer_state) is None
    assert sync._persistent_maintenance_path(local_state).is_file()
    assert sync._persistent_maintenance_path(peer_state).is_file()


def test_coordinator_crash_after_stage_before_journal_recovers_registered_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    peer_env = tmp_path / "peer.env"
    _env(local_env, node="node01", app_id="old", secret="old-secret")
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    local_state = _state_root(tmp_path / "local-state")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(local_state, volatile)
    _arm(peer_state, volatile)
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(
        sync,
        "_read_runtime_meta_values",
        lambda _node: {"META_APP_ID": "old", "META_APP_SECRET": "old-secret"},
    )
    monkeypatch.setattr(
        sync,
        "_call_peer",
        lambda _host, payload: sync._execute_request(
            payload,
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        ),
    )
    assert (
        sync._register_prestage_backup(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            state_root=local_state,
        )
        == 0
    )
    sync._write_meta_values(
        local_env,
        {"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
    )
    assert sync._load_journal(local_state) is None

    assert (
        sync._recover_only(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            state_root=local_state,
        )
        == 0
    )
    assert sync._read_meta_values(local_env)["META_APP_ID"] == "old"
    assert not sync._backup_path(local_state).exists()
    assert sync._persistent_maintenance_path(local_state).is_file()


def test_reboot_recreates_volatile_marker_from_persistent_transaction_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path / "state")
    volatile = tmp_path / "run-maintenance"
    sync._arm_marker(sync._persistent_maintenance_path(state_root))
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)

    sync._ensure_maintenance_armed(state_root)

    assert volatile.is_file()
    assert volatile.stat().st_mode & 0o777 == 0o600
    assert sync._persistent_maintenance_path(state_root).is_file()


def test_finalize_clears_backups_journals_and_both_markers_only_after_parity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    local_backup = tmp_path / "local.before"
    peer_env = tmp_path / "peer.env"
    _env(local_backup, node="node01", app_id="old", secret="old-secret")
    _env(local_env, node="node01", app_id="new", secret="new-secret")
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    local_state = _state_root(tmp_path / "local-state")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(local_state, volatile)
    _arm(peer_state, volatile)
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(
        sync,
        "_read_runtime_meta_values",
        lambda _node: {"META_APP_ID": "old", "META_APP_SECRET": "old-secret"},
    )
    tx_id = "d" * 32
    durable_backup = _authorize_local_stage(local_state, local_backup, tx_id=tx_id)
    _seed_quiesced_workers(peer_state, peer_env, tx_id=tx_id, role="peer")
    monkeypatch.setattr(
        sync,
        "_call_peer",
        lambda _host, payload: sync._execute_request(
            payload,
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        ),
    )
    sync._send_to_peer(
        expected_sha=SHA,
        peer_host="10.0.0.2",
        maintenance_active=True,
        local_prestage_backup=durable_backup,
        state_root=local_state,
    )

    cleanup_events: list[tuple[str, Path]] = []
    real_restore_workers = sync._restore_worker_units
    real_unlink = sync._durable_unlink

    def _record_restore(state_root: Path, *args: object, **kwargs: object) -> dict[str, object]:
        cleanup_events.append(("restore-workers", state_root))
        return real_restore_workers(state_root, *args, **kwargs)  # type: ignore[arg-type]

    def _record_unlink(path: Path) -> None:
        cleanup_events.append(("unlink", path))
        real_unlink(path)

    monkeypatch.setattr(sync, "_restore_worker_units", _record_restore)
    monkeypatch.setattr(sync, "_durable_unlink", _record_unlink)
    finalize_ack_lost = False

    def _call_with_final_ack_loss(_host: str, payload: dict[str, object]) -> dict[str, object]:
        nonlocal finalize_ack_lost
        result = sync._execute_request(
            payload,
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        )
        if payload["action"] == "finalize" and not finalize_ack_lost:
            finalize_ack_lost = True
            raise RuntimeError("simulated finalize ACK loss")
        return result

    monkeypatch.setattr(sync, "_call_peer", _call_with_final_ack_loss)

    assert sync._finalize_transaction(expected_sha=SHA, peer_host="10.0.0.2", state_root=local_state) == 0
    assert finalize_ack_lost is True
    for state in (local_state, peer_state):
        assert sync._load_journal(state) is None
        assert not sync._backup_path(state).exists()
        assert not sync._worker_state_path(state).exists()
        assert not sync._persistent_maintenance_path(state).exists()
    assert not volatile.exists()
    local_restore = cleanup_events.index(("restore-workers", local_state))
    assert local_restore < cleanup_events.index(("unlink", sync._backup_path(local_state)))
    assert local_restore < cleanup_events.index(("unlink", sync._journal_path(local_state)))
    assert cleanup_events.index(("unlink", sync._journal_path(local_state))) < cleanup_events.index(
        ("unlink", sync._worker_state_path(local_state))
    )


def test_finalizing_peer_journal_recovers_when_markers_were_cleared_before_crash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    peer_env = tmp_path / "peer.env"
    _env(peer_env, node="node02", app_id="new", secret="new-secret")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)
    values = sync._read_meta_values(peer_env)
    journal = sync._journal_payload(
        tx_id="8" * 32,
        role="peer",
        status="finalizing_committed",
        expected_sha=SHA,
        old_fingerprint="1" * 64,
        new_fingerprint=sync._meta_fingerprint(values, SHA),
        maintenance_active=True,
    )
    sync._write_journal(peer_state, journal)
    sync._write_worker_state(
        peer_state,
        sync._worker_state_payload(
            tx_id="8" * 32,
            role="peer",
            expected_sha=SHA,
            old_fingerprint="1" * 64,
            units={unit: {"enabled": True, "active": True} for unit in sync.WORKER_UNITS},
            status="quiesced",
        ),
    )
    armed: list[Path] = []
    real_arm = sync._arm_marker

    def _record_arm(path: Path) -> None:
        armed.append(path)
        real_arm(path)

    monkeypatch.setattr(sync, "_arm_marker", _record_arm)
    response = sync._execute_request(
        _request("query", "8" * 32),
        env_path=peer_env,
        lock_path=tmp_path / "peer.lock",
        state_root=peer_state,
    )

    assert response["status"] == "finalized"
    assert sync._persistent_maintenance_path(peer_state) in armed
    assert volatile in armed
    assert sync._load_journal(peer_state) is None
    assert not sync._persistent_maintenance_path(peer_state).exists()
    assert not volatile.exists()


def test_finalizing_coordinator_recovery_needs_no_deleted_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    _env(local_env, node="node01", app_id="old", secret="old-secret")
    local_state = _state_root(tmp_path / "local-state")
    volatile = tmp_path / "run-maintenance"
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)
    old_fingerprint = sync._meta_fingerprint(sync._read_meta_values(local_env), SHA)
    journal = sync._journal_payload(
        tx_id="9" * 32,
        role="coordinator",
        status="finalizing_rolled_back",
        expected_sha=SHA,
        old_fingerprint=old_fingerprint,
        new_fingerprint="2" * 64,
        maintenance_active=True,
        preserve_maintenance=True,
    )
    sync._write_journal(local_state, journal)
    sync._write_worker_state(
        local_state,
        sync._worker_state_payload(
            tx_id="9" * 32,
            role="coordinator",
            expected_sha=SHA,
            old_fingerprint=old_fingerprint,
            units={unit: {"enabled": True, "active": True} for unit in sync.WORKER_UNITS},
            status="restored",
            terminal_fingerprint=old_fingerprint,
        ),
    )
    monkeypatch.setattr(
        sync,
        "_call_peer",
        lambda _host, _payload: {
            "schema": sync.PROTOCOL_SCHEMA,
            "tx_id": "",
            "status": "absent",
            "fingerprint": old_fingerprint,
            "journal_present": False,
            "backup_present": False,
        },
    )

    assert (
        sync._recover_only(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            state_root=local_state,
        )
        == 0
    )
    assert sync._load_journal(local_state) is None
    assert not sync._backup_path(local_state).exists()
    assert sync._persistent_maintenance_path(local_state).is_file()
    assert volatile.is_file()


def test_secret_values_never_enter_ssh_argv_or_journal(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path / "state")
    secret = "stdin-only-super-secret"
    journal = sync._journal_payload(
        tx_id="6" * 32,
        role="coordinator",
        status="coordinator_created",
        expected_sha=SHA,
        old_fingerprint="1" * 64,
        new_fingerprint="2" * 64,
        maintenance_active=True,
    )
    sync._write_journal(state_root, journal)
    request = _request(
        "prepare",
        "6" * 32,
        values={"META_APP_ID": "new", "META_APP_SECRET": secret},
    )

    assert secret not in " ".join(sync._peer_command("10.0.0.2"))
    assert secret not in sync._journal_path(state_root).read_text(encoding="utf-8")
    assert secret in json.dumps(request)


def test_peer_refuses_node01_identity_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    wrong_env = tmp_path / "wrong.env"
    _env(wrong_env, node="node01", app_id="old", secret="old-secret")
    state_root = _state_root(tmp_path / "state")
    volatile = tmp_path / "run-maintenance"
    _arm(state_root, volatile)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)

    with pytest.raises(RuntimeError, match="wrong HA node"):
        sync._execute_request(
            _request(
                "prepare",
                "7" * 32,
                values={"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
            ),
            env_path=wrong_env,
            lock_path=tmp_path / "peer.lock",
            state_root=state_root,
        )
    assert sync._load_journal(state_root) is None


def test_maintenance_mode_requires_liveness_and_expected_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[str] = []

    def _probe(path: str) -> tuple[int, object]:
        probes.append(path)
        if path == "/api/health":
            return 200, {"ok": True, "role": "liveness"}
        return 503, {
            "ok": False,
            "role": "readiness",
            "checks": {"maintenance": {"ok": False}},
        }

    monkeypatch.setattr(sync, "_http_json", _probe)
    sync._wait_for_ready(maintenance_active=True)
    assert probes == ["/api/health", "/api/ready"]


def test_secure_contract_rejects_symlinked_external_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    target = tmp_path / "target.before"
    link = tmp_path / "link.before"
    _env(local_env, node="node01", app_id="new", secret="new-secret")
    _env(target, node="node01", app_id="old", secret="old-secret")
    link.symlink_to(target)
    state_root = _state_root(tmp_path / "state")
    volatile = tmp_path / "run-maintenance"
    _arm(state_root, volatile)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    _patch_runtime(monkeypatch)

    with pytest.raises(RuntimeError, match="security contract"):
        sync._create_coordinator_transaction(
            expected_sha=SHA,
            local_prestage_backup=link,
            maintenance_active=True,
            state_root=state_root,
        )


def test_atomic_writer_cleans_secure_temporary_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    _env(env_path, node="node01", app_id="old", secret="old-secret")

    def _fail_replace(_source: os.PathLike[str], _target: os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(sync.os, "replace", _fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        sync._atomic_write_bytes(env_path, b"META_APP_SECRET=never-logged\n")
    assert sync._read_meta_values(env_path)["META_APP_ID"] == "old"
    assert not list(tmp_path.glob("..env.atomic.*"))


def test_worker_inventory_is_durable_before_disable_and_survives_reboot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path / "state")
    original = {unit: {"enabled": index % 2 == 0, "active": index < 3} for index, unit in enumerate(sync.WORKER_UNITS)}
    runtime = {unit: dict(value) for unit, value in original.items()}
    first_disable = True

    monkeypatch.setattr(sync, "_capture_worker_units", lambda: {unit: dict(value) for unit, value in original.items()})
    monkeypatch.setattr(sync, "_worker_unit_state", lambda unit: dict(runtime[unit]))

    def _systemctl(*args: str, **_kwargs: object) -> object:
        nonlocal first_disable
        command = args[0]
        unit = args[-1]
        if command == "disable" and "--now" in args:
            if first_disable:
                first_disable = False
                durable = sync._load_worker_state(state_root)
                assert durable is not None
                assert durable["status"] == "captured"
                assert durable["units"] == original
            runtime[unit] = {"enabled": False, "active": False}
        elif command == "enable":
            runtime[unit]["enabled"] = True
        elif command == "disable":
            runtime[unit]["enabled"] = False
        elif command == "start":
            runtime[unit]["active"] = True
        elif command == "stop":
            runtime[unit]["active"] = False
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(sync, "_systemctl", _systemctl)
    monkeypatch.setattr(
        sync,
        "_read_unit_runtime_meta_values",
        lambda _unit, _node: {"META_APP_ID": "old", "META_APP_SECRET": "old-secret"},
    )
    worker_state = sync._capture_and_quiesce_workers(
        state_root,
        tx_id="e" * 32,
        role="coordinator",
        expected_sha=SHA,
        old_fingerprint="1" * 64,
    )
    assert all(state == {"enabled": False, "active": False} for state in runtime.values())
    assert worker_state["status"] == "quiesced"

    # Simulated reboot: disabled units remain stopped and the durable receipt
    # still contains the exact pre-transaction enable/active inventory.
    for state in runtime.values():
        if not state["enabled"]:
            state["active"] = False
    sync._verify_worker_units_quiesced()
    assert sync._load_worker_state(state_root)["units"] == original  # type: ignore[index]

    restored = sync._restore_worker_units(
        state_root,
        worker_state,
        terminal_fingerprint="2" * 64,
        expected_values={"META_APP_ID": "old", "META_APP_SECRET": "old-secret"},
        expected_node_id="node01",
    )
    assert restored["status"] == "restored"
    assert runtime == original


def test_lost_peer_quiesce_ack_never_authorizes_stage_and_recovery_restores_both_nodes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    peer_env = tmp_path / "peer.env"
    _env(local_env, node="node01", app_id="old", secret="old-secret")
    _env(peer_env, node="node02", app_id="old", secret="old-secret")
    local_state = _state_root(tmp_path / "local-state")
    peer_state = _state_root(tmp_path / "peer-state")
    volatile = tmp_path / "run-maintenance"
    _arm(local_state, volatile)
    _arm(peer_state, volatile)
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    monkeypatch.setattr(sync, "VOLATILE_MAINTENANCE_PATH", volatile)
    monkeypatch.setattr(sync, "_read_runtime_meta_values", lambda _node: sync._read_meta_values(local_env))
    ack_lost = False

    def _call(_host: str, payload: dict[str, object]) -> dict[str, object]:
        nonlocal ack_lost
        response = sync._execute_request(
            payload,
            env_path=peer_env,
            lock_path=tmp_path / "peer.lock",
            state_root=peer_state,
        )
        if payload["action"] == "quiesce" and not ack_lost:
            ack_lost = True
            raise RuntimeError("simulated delayed/lost peer acknowledgement")
        return response

    monkeypatch.setattr(sync, "_call_peer", _call)
    with pytest.raises(RuntimeError, match="delayed/lost"):
        sync._register_prestage_backup(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            state_root=local_state,
        )
    assert local_env.read_text(encoding="utf-8") == peer_env.read_text(encoding="utf-8").replace("node02", "node01")
    assert sync._load_worker_state(local_state)["status"] == "quiesced"  # type: ignore[index]
    assert sync._load_worker_state(peer_state)["status"] == "quiesced"  # type: ignore[index]
    assert sync._load_stage_authority(local_state) is None
    assert sync._load_journal(local_state) is None
    assert sync._load_journal(peer_state) is None

    assert (
        sync._recover_only(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=True,
            state_root=local_state,
        )
        == 0
    )
    assert sync._load_worker_state(local_state) is None
    assert sync._load_worker_state(peer_state) is None
    assert sync._load_stage_authority(local_state) is None


def test_stage_authority_rejects_stale_preimage_and_mismatched_worker_tx(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / "local.env"
    _env(env_path, node="node01", app_id="old", secret="old-secret")
    state_root = _state_root(tmp_path / "state")
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(sync, "ENV_PATH", env_path)
    _authorize_local_stage(state_root, env_path, tx_id="f" * 32)

    sync._write_meta_values(env_path, {"META_APP_ID": "new", "META_APP_SECRET": "new-secret"})
    with pytest.raises(RuntimeError, match="changed after pre-stage"):
        sync._require_stage_authority(state_root, expected_sha=SHA, require_preimage=True)

    sync._restore_exact_backup(env_path, sync._backup_path(state_root))
    authority = sync._load_stage_authority(state_root)
    assert authority is not None
    authority["tx_id"] = "1" * 32
    sync._write_stage_authority(state_root, authority)
    with pytest.raises(RuntimeError, match="does not match durable state"):
        sync._require_stage_authority(state_root, expected_sha=SHA, require_preimage=True)


def test_direct_root_stage_flag_without_inherited_lock_is_rejected_for_every_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sync.os, "getegid", lambda: 0)
    monkeypatch.delenv("LINAS_PRODUCTION_MUTATION_LOCK_FD", raising=False)
    with pytest.raises(RuntimeError, match="Inherited common Meta mutation lock is absent"):
        sync._require_coordinator_mutation_lock()

    writers = (
        "scripts/prod_apply_meta_social_secrets.sh",
        "scripts/prod_apply_meta_multi_app.sh",
        "scripts/prod_apply_instagram_login_secrets.sh",
        "scripts/prod_apply_meta_app_a_login_config.sh",
        "scripts/prod_set_meta_verify_token.sh",
    )
    root = Path(__file__).resolve().parents[1]
    for relative in writers:
        source = (root / relative).read_text(encoding="utf-8")
        authority = source.index("--verify-stage-authority")
        mutation = source.index("atomic_update_env")
        assert "META_HA_STAGE_ONLY" in source
        assert authority < mutation


@pytest.mark.parametrize("failure_index", range(len(sync.WORKER_UNITS) * 2))
def test_worker_restore_resumes_after_crash_at_every_systemd_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_index: int,
) -> None:
    state_root = _state_root(tmp_path / "state")
    original = {
        unit: {"enabled": index % 2 == 0, "active": index % 3 != 0} for index, unit in enumerate(sync.WORKER_UNITS)
    }
    runtime = {unit: {"enabled": False, "active": False} for unit in sync.WORKER_UNITS}
    worker_state = sync._worker_state_payload(
        tx_id="2" * 32,
        role="coordinator",
        expected_sha=SHA,
        old_fingerprint="3" * 64,
        units=original,
        status="quiesced",
    )
    sync._write_worker_state(state_root, worker_state)
    calls = 0
    fail = True

    monkeypatch.setattr(sync, "_worker_unit_state", lambda unit: dict(runtime[unit]))
    monkeypatch.setattr(
        sync,
        "_read_unit_runtime_meta_values",
        lambda _unit, _node: {"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
    )

    def _systemctl(*args: str, **_kwargs: object) -> object:
        nonlocal calls
        command = args[0]
        unit = args[-1]
        current_call = calls
        calls += 1
        if fail and current_call == failure_index:
            raise KeyboardInterrupt("simulated process death")
        if command == "enable":
            runtime[unit]["enabled"] = True
        elif command == "disable":
            runtime[unit]["enabled"] = False
        elif command == "start":
            runtime[unit]["active"] = True
        elif command == "stop":
            runtime[unit]["active"] = False
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(sync, "_systemctl", _systemctl)
    with pytest.raises(KeyboardInterrupt, match="simulated process death"):
        sync._restore_worker_units(
            state_root,
            worker_state,
            terminal_fingerprint="4" * 64,
            expected_values={"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
            expected_node_id="node01",
        )
    durable = sync._load_worker_state(state_root)
    assert durable is not None
    assert durable["status"] == "restoring"
    assert durable["terminal_fingerprint"] == "4" * 64

    fail = False
    restored = sync._restore_worker_units(
        state_root,
        durable,
        terminal_fingerprint="4" * 64,
        expected_values={"META_APP_ID": "new", "META_APP_SECRET": "new-secret"},
        expected_node_id="node01",
    )
    assert restored["status"] == "restored"
    assert runtime == original


def test_recovery_finishes_orphaned_local_worker_receipt_after_journal_unlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / "local.env"
    _env(local_env, node="node01", app_id="new", secret="new-secret")
    state_root = _state_root(tmp_path / "state")
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(sync, "ENV_PATH", local_env)
    values = sync._read_meta_values(local_env)
    terminal = sync._meta_fingerprint(values, SHA)
    sync._write_worker_state(
        state_root,
        sync._worker_state_payload(
            tx_id="5" * 32,
            role="coordinator",
            expected_sha=SHA,
            old_fingerprint="6" * 64,
            units={unit: {"enabled": True, "active": True} for unit in sync.WORKER_UNITS},
            status="restored",
            terminal_fingerprint=terminal,
        ),
    )

    assert (
        sync._recover_only(
            expected_sha=SHA,
            peer_host="10.0.0.2",
            maintenance_active=False,
            state_root=state_root,
        )
        == 0
    )
    assert sync._load_worker_state(state_root) is None
