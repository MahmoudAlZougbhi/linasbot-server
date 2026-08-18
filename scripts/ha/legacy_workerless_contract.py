"""Fail-closed cluster decision for one-time HA worker-template migration.

The production helper inlines the same closed strings. This module is the
unit-testable contract: absence is never inferred from NeedDaemonReload=no.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SCHEMA = "linas-ha-legacy-workerless-v1"
QUEUES = ("high_priority", "interactive", "background", "expensive")
TEMPLATE_PATH = "/etc/systemd/system/linasbot-worker@.service"
SYSTEMD_QUEUE_WORKER_CGROUP = re.compile(
    r"(?:^|/)"
    r"linasbot-worker@(?:high_priority|interactive|background|expensive)\.service"
    r"(?:/|$)"
)
LOADED = "loaded"
LEGACY_ABSENT = "legacy-absent"
PRESENT = "template-present"
MIGRATE = "legacy-absent-migration"
# One-time migration live SHA. Future steady deploys must already be loaded.
AUTHORIZED_WORKERLESS_LIVE_SHA = "bca167fcd2f08fa1b1bc461226fffb42febb31e5"
ENABLED_BLOCKERS = frozenset({"enabled", "enabled-runtime", "linked", "alias"})
ACTIVE_BLOCKERS = frozenset({"active", "activating", "deactivating", "reloading"})
ABSENT_LOAD = frozenset({"not-found", "bad-setting", "error", "masked", ""})
ABSENT_ENABLED = frozenset({"disabled", "not-found", "invalid", "bad", "indirect", ""})
ABSENT_ACTIVE = frozenset({"inactive", "dead", "failed", "unknown", "not-found", ""})


class WorkerlessContractError(ValueError):
    """Closed fail-closed decision error."""


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise WorkerlessContractError("worker template probe field is not a string")
    return value.strip()


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise WorkerlessContractError(f"worker template probe {label} is not a boolean")
    return value


def cgroup_is_systemd_queue_worker(cgroup_text: str) -> bool:
    """True only when the process cgroup is a concrete linasbot-worker@ queue unit."""
    if not isinstance(cgroup_text, str):
        raise WorkerlessContractError("worker cgroup text is not a string")
    return SYSTEMD_QUEUE_WORKER_CGROUP.search(cgroup_text) is not None


def classify_probe(probe: Mapping[str, Any]) -> str:
    if not isinstance(probe, dict) or probe.get("schema") != SCHEMA:
        raise WorkerlessContractError("worker template probe schema is invalid")
    worker_template_required = _bool(probe.get("worker_template_required"), "worker_template_required")
    # Redis/durable flags mean workers should exist. Missing systemd units are
    # still a fail-closed migration, not a skip of the maintenance guard.
    _bool(probe.get("durable_queues_required"), "durable_queues_required")
    stray = probe.get("stray_worker_pids")
    if not isinstance(stray, list) or any(not isinstance(item, str) or not item for item in stray):
        raise WorkerlessContractError("worker template probe stray pid list is invalid")
    if stray:
        raise WorkerlessContractError("worker processes are running outside systemd: " + ",".join(stray))
    listed = probe.get("listed_worker_units")
    if not isinstance(listed, list) or any(not isinstance(item, str) for item in listed):
        raise WorkerlessContractError("worker template probe unit list is invalid")
    instances = probe.get("instances")
    if not isinstance(instances, dict) or set(instances) != set(QUEUES):
        raise WorkerlessContractError("worker template probe instances are incomplete")
    loaded_count = 0
    enabled_hits: list[str] = []
    active_hits: list[str] = []
    for queue in QUEUES:
        inst = instances[queue]
        if not isinstance(inst, dict):
            raise WorkerlessContractError("worker template probe instance is invalid")
        load_state = _text(inst.get("load_state"))
        enabled = _text(inst.get("unit_file_state"))
        active = _text(inst.get("active_state"))
        if enabled in ENABLED_BLOCKERS:
            enabled_hits.append(queue)
        elif enabled not in ABSENT_ENABLED:
            raise WorkerlessContractError(f"linasbot-worker@{queue} enablement is outside the closed schema")
        if active in ACTIVE_BLOCKERS:
            active_hits.append(queue)
        elif active not in ABSENT_ACTIVE:
            raise WorkerlessContractError(f"linasbot-worker@{queue} activity is outside the closed schema")
        if load_state == LOADED:
            fragment = _text(inst.get("fragment_path"))
            if fragment != TEMPLATE_PATH:
                raise WorkerlessContractError("loaded worker instance fragment path is not canonical")
            loaded_count += 1
        elif load_state not in ABSENT_LOAD:
            raise WorkerlessContractError(f"linasbot-worker@{queue} load state is outside the closed schema")
    template_exists = _bool(probe.get("template_file_exists"), "template_file_exists")
    template_symlink = _bool(probe.get("template_is_symlink"), "template_is_symlink")
    if template_symlink:
        raise WorkerlessContractError("canonical worker template is a symlink")
    if loaded_count == len(QUEUES):
        if not template_exists:
            raise WorkerlessContractError("worker instances are loaded without a template file")
        return LOADED
    if listed:
        raise WorkerlessContractError("linasbot-worker@ units are enabled or active on this node")
    if enabled_hits:
        raise WorkerlessContractError(f"linasbot-worker@{enabled_hits[0]} is enabled")
    if active_hits:
        raise WorkerlessContractError(f"linasbot-worker@{active_hits[0]} is active")
    if loaded_count:
        raise WorkerlessContractError("worker template file exists but instances are not fully loaded")
    # File may exist from a prior failed recover; not actually loaded.
    if worker_template_required:
        raise WorkerlessContractError(
            "legacy workerless migration is not allowed after the worker template became required"
        )
    return LEGACY_ABSENT


def decide_cluster(node01: Mapping[str, Any], node02: Mapping[str, Any]) -> str:
    try:
        class_01 = classify_probe(node01)
    except WorkerlessContractError as exc:
        raise WorkerlessContractError(f"node01: {exc}") from None
    try:
        class_02 = classify_probe(node02)
    except WorkerlessContractError as exc:
        raise WorkerlessContractError(f"node02: {exc}") from None
    if class_01 != class_02:
        raise WorkerlessContractError("node01 and node02 worker template states disagree")
    target_01 = _text(node01.get("target_sha"))
    target_02 = _text(node02.get("target_sha"))
    live_01 = _text(node01.get("live_head"))
    live_02 = _text(node02.get("live_head"))
    if target_01 != target_02 or len(target_01) != 40:
        raise WorkerlessContractError("worker template probes do not share one target SHA")
    if class_01 == LOADED:
        return PRESENT
    if live_01 != AUTHORIZED_WORKERLESS_LIVE_SHA or live_02 != AUTHORIZED_WORKERLESS_LIVE_SHA:
        raise WorkerlessContractError("legacy workerless migration is not allowed after cutover")
    if live_01 == target_01 or live_02 == target_02:
        raise WorkerlessContractError("legacy workerless migration is not allowed after cutover")
    return MIGRATE
