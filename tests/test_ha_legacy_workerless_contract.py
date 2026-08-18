"""Fail-closed cluster decision for the one-time workerless HA migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ha.legacy_workerless_contract import (
    AUTHORIZED_WORKERLESS_LIVE_SHA,
    LEGACY_ABSENT,
    LOADED,
    MIGRATE,
    PRESENT,
    SCHEMA,
    WorkerlessContractError,
    classify_probe,
    decide_cluster,
)

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"

OLD = AUTHORIZED_WORKERLESS_LIVE_SHA
TARGET = "c" * 40


def _instance(*, load: str, enabled: str = "disabled", active: str = "inactive") -> dict[str, str]:
    fragment = "/etc/systemd/system/linasbot-worker@.service" if load == "loaded" else ""
    return {
        "load_state": load,
        "unit_file_state": enabled,
        "active_state": active,
        "fragment_path": fragment,
    }


def _probe(*, load: str, live: str = OLD, target: str = TARGET, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "live_head": live,
        "target_sha": target,
        "template_file_exists": load == "loaded",
        "template_is_symlink": False,
        "durable_queues_required": False,
        "stray_worker_pids": [],
        "listed_worker_units": [],
        "instances": {
            queue: _instance(load=load) for queue in ("high_priority", "interactive", "background", "expensive")
        },
    }
    payload.update(overrides)
    return payload


def test_absent_probes_authorize_migration_only_before_cutover() -> None:
    assert classify_probe(_probe(load="not-found", **{"template_file_exists": False})) == LEGACY_ABSENT
    assert classify_probe(_probe(load="not-found", **{"template_file_exists": True})) == LEGACY_ABSENT
    assert decide_cluster(_probe(load="not-found"), _probe(load="not-found")) == MIGRATE
    assert (
        decide_cluster(
            _probe(load="not-found", **{"template_file_exists": True}),
            _probe(load="not-found", **{"template_file_exists": True}),
        )
        == MIGRATE
    )


def test_partially_loaded_instances_fail_closed() -> None:
    mixed = _probe(load="not-found", **{"template_file_exists": True})
    mixed["instances"]["high_priority"] = _instance(load="loaded")
    with pytest.raises(WorkerlessContractError, match="not fully loaded"):
        classify_probe(mixed)


def test_loaded_probes_keep_the_steady_contract() -> None:
    loaded = _probe(load="loaded", live=TARGET)
    assert classify_probe(loaded) == LOADED
    assert decide_cluster(loaded, loaded) == PRESENT


def test_need_daemon_reload_is_not_part_of_the_absence_decision() -> None:
    payload = _probe(load="not-found")
    assert "need_daemon_reload" not in json.dumps(payload)


def test_disagreeing_nodes_fail_closed() -> None:
    with pytest.raises(WorkerlessContractError, match="disagree"):
        decide_cluster(_probe(load="not-found"), _probe(load="loaded"))


def test_cutover_live_cannot_use_legacy_workerless_migration() -> None:
    with pytest.raises(WorkerlessContractError, match="not allowed after cutover"):
        decide_cluster(_probe(load="not-found", live=TARGET), _probe(load="not-found", live=TARGET))
    other = "d" * 40
    with pytest.raises(WorkerlessContractError, match="not allowed after cutover"):
        decide_cluster(_probe(load="not-found", live=other), _probe(load="not-found", live=other))


def test_enabled_or_active_or_stray_workers_fail_closed() -> None:
    enabled = _probe(load="not-found")
    enabled["instances"]["high_priority"] = _instance(load="not-found", enabled="enabled")
    with pytest.raises(WorkerlessContractError, match="enabled"):
        classify_probe(enabled)
    active = _probe(load="not-found")
    active["instances"]["high_priority"] = _instance(load="not-found", active="active")
    with pytest.raises(WorkerlessContractError, match="active"):
        classify_probe(active)
    with pytest.raises(WorkerlessContractError, match="outside systemd"):
        classify_probe(_probe(load="not-found", stray_worker_pids=["4321"]))
    with pytest.raises(WorkerlessContractError, match="required"):
        classify_probe(_probe(load="not-found", durable_queues_required=True))
    with pytest.raises(WorkerlessContractError, match="enabled or active"):
        classify_probe(_probe(load="not-found", listed_worker_units=["linasbot-worker@high_priority.service"]))


def test_helper_embeds_the_fail_closed_workerless_contract() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "worker_instances_are_positively_loaded() {" in source
    assert 'test "$load_state" = "loaded"' in source
    assert "ensure_worker_template_before_maintenance_guard() {" in source
    assert "legacy-absent-migration" in source
    assert "legacy workerless migration is not allowed after cutover" in source
    assert AUTHORIZED_WORKERLESS_LIVE_SHA in source
    assert "NeedDaemonReload=no is not proof" in source
    assert "list-unit-files --state=enabled" in source
    assert "linasbot-worker@ units are enabled or active on this node" in source
    assert "publish_cluster_worker_template_decision() {" in source
    assert "install_trusted_worker_template_from_target() {" in source
    assert "from scripts.ha.legacy_workerless_contract" not in source
    assert "I_UNDERSTAND_SKIPPING_GATES" not in source
    assert "--skip" not in source
    install = source[
        source.index("install_maintenance_boot_guard() {") : source.index("assert_maintenance_boot_guard_loaded() {")
    ]
    assert "ensure_worker_template_before_maintenance_guard" in install
    assert "worker_instances_are_positively_loaded" in install
    assert "worker_instances_maintenance_guard_readback" in install
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    started = recover.index('update_recovery_journal "recovery-started"')
    assert recover.index("publish_cluster_worker_template_decision", started) < recover.index(
        'node_ensure_maintenance "$tx_dir"', started
    )
    orchestrate = source[source.index("orchestrate() {") :]
    assert orchestrate.index("publish_cluster_worker_template_decision") < orchestrate.index(
        "withdrawing peer before peer-first staging"
    )
