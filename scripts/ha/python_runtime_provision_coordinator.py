#!/usr/bin/env python3
"""Closed durable coordinator authority for two-node runtime provisioning."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_contract as contract
from scripts.ha import python_runtime_provision_state as state

ProvisionError = archive.ProvisionError
FORMAT: Final = "linas-python-runtime-coordinator-v1"
PHASES: Final = {
    "started",
    "authority-snapshotted",
    "peer-staged",
    "peer-prepared",
    "both-prepared",
    "decision-durable",
    "node-receipts-durable",
    "cluster-receipt-durable",
    "committed",
    "rollback-preflight-durable",
    "rolled-back",
    "compensated-rollback",
}
COMMIT_ORDER: Final = (
    "started",
    "authority-snapshotted",
    "peer-staged",
    "peer-prepared",
    "both-prepared",
    "decision-durable",
    "node-receipts-durable",
    "cluster-receipt-durable",
    "committed",
)
ALLOWED: Final = {
    **{phase: {COMMIT_ORDER[index + 1]} for index, phase in enumerate(COMMIT_ORDER[:-1])},
    "committed": set(),
    "rollback-preflight-durable": {"rolled-back", "compensated-rollback"},
    "rolled-back": set(),
    "compensated-rollback": set(),
}
for _phase in COMMIT_ORDER:
    ALLOWED[_phase].add("rollback-preflight-durable")
KEYS: Final = {
    "schema",
    "format",
    "transaction_id",
    "plan",
    "plan_sha256",
    "phase",
    "decision",
    "node_receipt_sha256",
    "cluster_receipt",
    "cluster_receipt_sha256",
    "rollback_decision",
    "rollback_preflight_sha256",
}
TERMINAL_POINTER = "coordinator-terminal.json"


def template(plan: Mapping[str, Any], plan_sha256: str) -> dict[str, Any]:
    contract.validate_plan(plan, plan_sha256)
    return {
        "schema": 1,
        "format": FORMAT,
        "transaction_id": plan["transaction_id"],
        "plan": dict(plan),
        "plan_sha256": plan_sha256,
        "phase": "started",
        "decision": "undecided",
        "node_receipt_sha256": {node: "" for node in contract.NODES},
        "cluster_receipt": {},
        "cluster_receipt_sha256": "",
        "rollback_decision": "undecided",
        "rollback_preflight_sha256": {node: "" for node in contract.NODES},
    }


def _digest_map(value: Any, *, complete: bool | None = None) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(contract.NODES):
        raise ProvisionError("runtime coordinator node digest map is invalid")
    result: dict[str, str] = {}
    for node in contract.NODES:
        digest = value[node]
        if not isinstance(digest, str) or (digest and contract.SHA256_RE.fullmatch(digest) is None):
            raise ProvisionError("runtime coordinator node digest is invalid")
        result[node] = digest
    if complete is True and any(not digest for digest in result.values()):
        raise ProvisionError("runtime coordinator node digest map is incomplete")
    if complete is False and any(result.values()):
        raise ProvisionError("runtime coordinator node digest map is prematurely populated")
    return result


def validate(payload: Any, raw: bytes | None = None) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != KEYS
        or payload.get("schema") != 1
        or payload.get("format") != FORMAT
        or payload.get("phase") not in PHASES
        or payload.get("decision") not in {"undecided", "commit", "rollback"}
        or payload.get("rollback_decision") not in {"undecided", "rollback"}
    ):
        raise ProvisionError("runtime coordinator schema or state is invalid")
    if raw is not None and contract.canonical(payload) != raw:
        raise ProvisionError("runtime coordinator is not canonical")
    plan_sha = payload.get("plan_sha256")
    if not isinstance(plan_sha, str):
        raise ProvisionError("runtime coordinator plan digest is invalid")
    plan = contract.validate_plan(payload["plan"], plan_sha)
    if payload["transaction_id"] != plan["transaction_id"]:
        raise ProvisionError("runtime coordinator transaction binding is invalid")
    node_hashes = _digest_map(payload["node_receipt_sha256"])
    rollback_hashes = _digest_map(payload["rollback_preflight_sha256"])
    cluster = payload["cluster_receipt"]
    cluster_sha = payload["cluster_receipt_sha256"]
    if cluster_sha:
        if not isinstance(cluster_sha, str) or contract.SHA256_RE.fullmatch(cluster_sha) is None:
            raise ProvisionError("runtime coordinator cluster digest is invalid")
        validated = contract.validate_cluster_receipt(cluster, plan, plan_sha)
        if contract.digest_json(validated) != cluster_sha or validated["node_receipt_sha256"] != node_hashes:
            raise ProvisionError("runtime coordinator cluster receipt binding is invalid")
    elif cluster != {}:
        raise ProvisionError("runtime coordinator has an unbound cluster receipt")
    phase = str(payload["phase"])
    decision = str(payload["decision"])
    rollback_decision = str(payload["rollback_decision"])
    early = set(COMMIT_ORDER[:5])
    if phase in early and (decision != "undecided" or any(node_hashes.values()) or cluster_sha):
        raise ProvisionError("runtime coordinator pre-decision state is inconsistent")
    if phase == "decision-durable" and (decision != "commit" or any(node_hashes.values()) or cluster_sha):
        raise ProvisionError("runtime coordinator decision state is inconsistent")
    if phase == "node-receipts-durable" and (decision != "commit" or not all(node_hashes.values()) or cluster_sha):
        raise ProvisionError("runtime coordinator node receipt state is inconsistent")
    if phase in {"cluster-receipt-durable", "committed"} and (
        decision != "commit" or not all(node_hashes.values()) or not cluster_sha
    ):
        raise ProvisionError("runtime coordinator committed state is inconsistent")
    if phase == "rollback-preflight-durable":
        if (
            rollback_decision != "rollback"
            or not all(rollback_hashes.values())
            or decision not in {"commit", "rollback"}
        ):
            raise ProvisionError("runtime coordinator rollback preflight is inconsistent")
    elif phase in {"rolled-back", "compensated-rollback"}:
        expected = "rollback" if phase == "rolled-back" else "commit"
        if decision != expected or rollback_decision != "rollback" or not all(rollback_hashes.values()):
            raise ProvisionError("runtime coordinator terminal rollback is inconsistent")
    elif rollback_decision != "undecided" or any(rollback_hashes.values()):
        raise ProvisionError("runtime coordinator rollback authority is premature")
    return payload


def load_path(path: Path) -> tuple[dict[str, Any], str]:
    raw = state._secure_state_file(path)
    try:
        payload = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProvisionError("runtime coordinator is invalid JSON") from exc
    return validate(payload, raw), hashlib.sha256(raw).hexdigest()


def load(paths: state.ProvisionPaths) -> tuple[dict[str, Any], str]:
    return load_path(paths.coordinator)


def write(
    paths: state.ProvisionPaths,
    payload: Mapping[str, Any],
    *,
    no_replace: bool = False,
) -> dict[str, Any]:
    validated = validate(dict(payload))
    state.boundary("before_coordinator_publish")
    state._atomic_write(paths.coordinator, contract.canonical(validated), no_replace=no_replace)
    state.boundary("after_coordinator_publish")
    observed, _digest = load(paths)
    if observed != validated:
        raise ProvisionError("runtime coordinator durable readback differs")
    return observed


def update(paths: state.ProvisionPaths, **changes: Any) -> dict[str, Any]:
    current, _digest = load(paths)
    target_phase = str(changes.get("phase", current["phase"]))
    current_phase = str(current["phase"])
    if target_phase != current_phase:
        if target_phase in COMMIT_ORDER and current_phase in COMMIT_ORDER:
            if COMMIT_ORDER.index(target_phase) < COMMIT_ORDER.index(current_phase):
                target_phase = current_phase
            elif target_phase not in ALLOWED[current_phase]:
                raise ProvisionError("runtime coordinator phase skipped a durable boundary")
        elif target_phase not in ALLOWED[current_phase]:
            raise ProvisionError("runtime coordinator phase transition is invalid")
    changes["phase"] = target_phase
    for key in ("decision", "rollback_decision"):
        requested = changes.get(key, current[key])
        if current[key] != "undecided" and requested != current[key]:
            raise ProvisionError(f"durable runtime {key} cannot be reversed")
    for key in (
        "node_receipt_sha256",
        "cluster_receipt",
        "cluster_receipt_sha256",
        "rollback_preflight_sha256",
    ):
        if key in changes and current[key] not in ({}, "", {node: "" for node in contract.NODES}):
            if changes[key] != current[key]:
                raise ProvisionError("durable runtime coordinator evidence cannot change")
    current.update(changes)
    return write(paths, current)


def terminal(paths: state.ProvisionPaths, tx_id: str) -> tuple[dict[str, Any], str] | None:
    tx_root = paths.tx_root(tx_id)
    pointer_path = tx_root / TERMINAL_POINTER
    if not (pointer_path.exists() or pointer_path.is_symlink()):
        return None
    pointer = state._load_json(pointer_path)
    if (
        set(pointer) != {"schema", "format", "transaction_id", "coordinator_sha256", "phase"}
        or pointer.get("schema") != 1
        or pointer.get("format") != "linas-python-runtime-terminal-pointer-v1"
        or pointer.get("transaction_id") != tx_id
        or pointer.get("phase") not in {"committed", "rolled-back", "compensated-rollback"}
        or contract.SHA256_RE.fullmatch(str(pointer.get("coordinator_sha256"))) is None
    ):
        raise ProvisionError("terminal runtime coordinator pointer is invalid")
    digest = str(pointer["coordinator_sha256"])
    final = tx_root / f"coordinator-final-{digest}.json"
    payload, observed = load_path(final)
    if observed != digest or payload["transaction_id"] != tx_id:
        raise ProvisionError("terminal runtime coordinator filename binding is invalid")
    if payload["phase"] != pointer["phase"]:
        raise ProvisionError("archived runtime coordinator is not terminal")
    return payload, digest


def archive_and_clear(paths: state.ProvisionPaths) -> tuple[dict[str, Any], str]:
    current, digest = load(paths)
    if current["phase"] not in {"committed", "rolled-back", "compensated-rollback"}:
        raise ProvisionError("nonterminal runtime coordinator cannot be archived")
    final = paths.tx_root(str(current["transaction_id"])) / f"coordinator-final-{digest}.json"
    state._atomic_write(final, contract.canonical(current), no_replace=True)
    pointer = {
        "schema": 1,
        "format": "linas-python-runtime-terminal-pointer-v1",
        "transaction_id": current["transaction_id"],
        "coordinator_sha256": digest,
        "phase": current["phase"],
    }
    state._atomic_write(paths.tx_root(str(current["transaction_id"])) / TERMINAL_POINTER, contract.canonical(pointer))
    state.boundary("before_coordinator_clear")
    if paths.coordinator.exists() or paths.coordinator.is_symlink():
        observed, observed_digest = load(paths)
        if observed != current or observed_digest != digest:
            raise ProvisionError("runtime coordinator changed before terminal cleanup")
        paths.coordinator.unlink()
        archive.fsync_directory(paths.coordinator.parent)
    state.boundary("after_coordinator_clear")
    terminal_state = terminal(paths, str(current["transaction_id"]))
    if terminal_state != (current, digest):
        raise ProvisionError("terminal runtime coordinator readback failed")
    return current, digest


def restore_terminal(paths: state.ProvisionPaths, tx_id: str, digest: str) -> dict[str, Any]:
    terminal_state = terminal(paths, tx_id)
    if terminal_state is None or terminal_state[1] != digest:
        raise ProvisionError("terminal runtime coordinator authority is unavailable")
    payload, _observed = terminal_state
    state._atomic_write(paths.coordinator, contract.canonical(payload), no_replace=True)
    restored, restored_digest = load(paths)
    if restored != payload or restored_digest != digest:
        raise ProvisionError("terminal runtime coordinator restoration failed")
    return restored
