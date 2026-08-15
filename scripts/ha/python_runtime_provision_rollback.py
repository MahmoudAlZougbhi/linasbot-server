#!/usr/bin/env python3
"""Fail-closed, crash-replayable rollback for the CPython HA transaction."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_contract as contract
from scripts.ha import python_runtime_provision_state as state

ProvisionError = archive.ProvisionError
CONSUMER_PROOFS = ("bootstrap.last-committed.json",)


def assert_unconsumed(paths: state.ProvisionPaths, tx_id: str) -> None:
    for name in (*state.CONSUMER_NAMES, *CONSUMER_PROOFS):
        candidate = paths.state_root / name
        if candidate.exists() or candidate.is_symlink():
            raise ProvisionError(f"runtime rollback is consumed by {name}")
    probes = (
        Path("/opt/linasbot/venv/pyvenv.cfg"),
        Path("/etc/systemd/system/linasbot.service"),
        Path("/etc/systemd/system/linasbot-worker@.service"),
    )
    for probe in probes:
        if not (probe.exists() or probe.is_symlink()):
            continue
        info = probe.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_size > 1024 * 1024:
            raise ProvisionError("runtime consumer probe is unsafe")
        if str(paths.runtime).encode() in archive.read_regular(probe, max_bytes=1024 * 1024):
            raise ProvisionError(f"runtime rollback is consumed by {probe}")
    if state.load_journal(paths, tx_id)["transaction_id"] != tx_id:
        raise ProvisionError("runtime rollback journal identity changed")


def _receipt_payload(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProvisionError("runtime rollback receipt is invalid JSON") from exc
    if not isinstance(payload, dict) or contract.canonical(payload) != raw:
        raise ProvisionError("runtime rollback receipt is not canonical")
    return payload


def _target_receipt(raw: bytes, journal: dict[str, Any], *, cluster: bool) -> bool:
    payload = _receipt_payload(raw)
    try:
        if cluster:
            contract.validate_cluster_receipt(payload, journal["plan"], str(journal["plan_sha256"]))
        else:
            contract.validate_node_receipt(payload, journal["plan"], str(journal["plan_sha256"]))
    except ProvisionError:
        return False
    return True


def _target_quarantine(paths: state.ProvisionPaths, tx_id: str, node_id: str) -> Path | None:
    matched: list[Path] = []
    for candidate in state.quarantine_paths(paths, tx_id, node_id, "runtime"):
        try:
            archive.verify_runtime_before_use(candidate)
        except ProvisionError:
            continue
        matched.append(candidate)
    if len(matched) > 1:
        raise ProvisionError("multiple authenticated target runtimes are quarantined")
    return matched[0] if matched else None


def rollback_preflight(paths: state.ProvisionPaths, tx_id: str) -> tuple[dict[str, Any], str]:
    journal = state.load_journal(paths, tx_id)
    assert_unconsumed(paths, tx_id)
    node_id = str(journal["node_id"])
    state.claim_active(paths, journal["plan"], str(journal["plan_sha256"]), node_id)
    evidence: dict[str, Any] = {
        "schema": 1,
        "transaction_id": tx_id,
        "node_id": node_id,
        "plan_sha256": journal["plan_sha256"],
        "journal_sha256": hashlib.sha256(contract.canonical(journal)).hexdigest(),
        "phase": journal["phase"],
        "decision": journal["decision"],
        "candidate": paths.candidate(tx_id, node_id).exists(),
        "previous": paths.previous(tx_id, node_id).exists(),
        "target_quarantine": _target_quarantine(paths, tx_id, node_id) is not None,
        "runtime": paths.runtime.exists(),
        "active_guard": True,
        "local_receipt_sha256": "",
        "cluster_receipt_sha256": "",
    }
    for key, path in (
        ("local_receipt_sha256", paths.local_receipt),
        ("cluster_receipt_sha256", paths.cluster_receipt),
    ):
        if path.exists() or path.is_symlink():
            evidence[key] = hashlib.sha256(state._secure_state_file(path)).hexdigest()
    return evidence, contract.digest_json(evidence)


def staged_preflight(
    paths: state.ProvisionPaths,
    plan: dict[str, Any],
    plan_sha256: str,
    node_id: str,
) -> tuple[dict[str, Any], str]:
    tx_id = str(plan["transaction_id"])
    if paths.journal(tx_id).exists() or paths.journal(tx_id).is_symlink():
        return rollback_preflight(paths, tx_id)
    active = False
    if paths.active.exists() or paths.active.is_symlink():
        if state._load_json(paths.active) != state._active_payload(plan, plan_sha256, node_id):
            raise ProvisionError("staged rollback sentinel authority changed")
        active = True
    for candidate in (paths.candidate(tx_id, node_id), candidate_extracting(paths, tx_id, node_id)):
        if candidate.exists() or candidate.is_symlink():
            raise ProvisionError("staged rollback found an unjournaled runtime mutation")
    evidence: dict[str, Any] = {
        "schema": 1,
        "transaction_id": tx_id,
        "node_id": node_id,
        "plan_sha256": plan_sha256,
        "phase": "staged" if active else "absent",
    }
    return evidence, contract.digest_json(evidence)


def abort_staged(
    paths: state.ProvisionPaths,
    plan: dict[str, Any],
    plan_sha256: str,
    node_id: str,
) -> dict[str, Any]:
    tx_id = str(plan["transaction_id"])
    journal = paths.journal(tx_id)
    if journal.exists() or journal.is_symlink():
        raise ProvisionError("staged abort cannot replace a participant journal")
    for candidate in (paths.candidate(tx_id, node_id), candidate_extracting(paths, tx_id, node_id)):
        if candidate.exists() or candidate.is_symlink():
            raise ProvisionError("staged abort found unexpected runtime mutation state")
    if paths.active.exists() or paths.active.is_symlink():
        if state._load_json(paths.active) != state._active_payload(plan, plan_sha256, node_id):
            raise ProvisionError("staged abort sentinel authority changed")
        state.boundary("before_active_clear")
        paths.active.unlink()
        archive.fsync_directory(paths.active.parent)
        state.boundary("after_active_clear")
    return {"schema": 1, "status": "staged-aborted", "transaction_id": tx_id}


def candidate_extracting(paths: state.ProvisionPaths, tx_id: str, node_id: str) -> Path:
    candidate = paths.candidate(tx_id, node_id)
    return candidate.parent / f".{candidate.name}.extracting"


def abort_initiated(paths: state.ProvisionPaths, tx_id: str, authority_decision: str) -> dict[str, Any]:
    journal = state.load_journal(paths, tx_id)
    if journal["phase"] != "initiated" or journal["decision"] != "undecided":
        raise ProvisionError("initiated abort state changed")
    if authority_decision not in {"commit", "rollback"}:
        raise ProvisionError("initiated abort authority is invalid")
    node_id = str(journal["node_id"])
    candidate = paths.candidate(tx_id, node_id)
    partial = candidate_extracting(paths, tx_id, node_id)
    for source in (candidate, partial):
        if not (source.exists() or source.is_symlink()):
            continue
        try:
            archive.verify_runtime_before_use(source)
        except ProvisionError:
            destination = state.next_quarantine_path(paths, tx_id, node_id, "incomplete")
        else:
            destination = state.next_quarantine_path(paths, tx_id, node_id, "runtime")
        state.boundary("before_rollback_runtime_rename")
        archive.rename_durable(source, destination)
        state.boundary("after_rollback_runtime_rename")
    journal["decision"] = authority_decision
    journal["phase"] = "rollback-baseline-restored"
    state._write_journal(paths, journal)
    return rollback_node(paths, tx_id)


def _quarantine_target(paths: state.ProvisionPaths, journal: dict[str, Any]) -> None:
    tx_id = str(journal["transaction_id"])
    node_id = str(journal["node_id"])
    if _target_quarantine(paths, tx_id, node_id) is None:
        candidate = paths.candidate(tx_id, node_id)
        source: Path | None = None
        if candidate.exists() or candidate.is_symlink():
            archive.verify_runtime_before_use(candidate)
            source = candidate
        elif paths.runtime.exists() or paths.runtime.is_symlink():
            archive.verify_runtime_before_use(paths.runtime)
            source = paths.runtime
        if source is not None:
            destination = state.next_quarantine_path(paths, tx_id, node_id, "runtime")
            state.boundary("before_rollback_runtime_rename")
            archive.rename_durable(source, destination)
            state.boundary("after_rollback_runtime_rename")
    journal["phase"] = "rollback-runtime-quarantined"
    state.boundary("before_rollback_runtime_journal")
    state._write_journal(paths, journal)
    state.boundary("after_rollback_runtime_journal")


def _restore_baseline(paths: state.ProvisionPaths, journal: dict[str, Any]) -> None:
    tx_id = str(journal["transaction_id"])
    node_id = str(journal["node_id"])
    previous = paths.previous(tx_id, node_id)
    if previous.exists() or previous.is_symlink():
        if paths.runtime.exists() or paths.runtime.is_symlink():
            raise ProvisionError("runtime baseline and preserved predecessor both exist")
        state.boundary("before_rollback_baseline_rename")
        archive.rename_durable(previous, paths.runtime)
        state.boundary("after_rollback_baseline_rename")
    elif journal["had_previous"] and not (paths.runtime.exists() or paths.runtime.is_symlink()):
        raise ProvisionError("preserved runtime baseline is missing")
    journal["phase"] = "rollback-baseline-restored"
    state.boundary("before_rollback_baseline_journal")
    state._write_journal(paths, journal)
    state.boundary("after_rollback_baseline_journal")


def _restore_receipt(paths: state.ProvisionPaths, journal: dict[str, Any], path: Path, *, cluster: bool) -> None:
    tx_id = str(journal["transaction_id"])
    rolled = paths.tx_root(tx_id) / "rolled-back"
    archive.secure_directory(rolled, mode=0o700, create=True)
    target_snapshot = rolled / path.name
    prior = paths.tx_root(tx_id) / "prior" / path.name
    if target_snapshot.exists() or target_snapshot.is_symlink():
        if not _target_receipt(state._secure_state_file(target_snapshot), journal, cluster=cluster):
            raise ProvisionError("quarantined target runtime receipt is invalid")
    elif path.exists() or path.is_symlink():
        raw = state._secure_state_file(path)
        if _target_receipt(raw, journal, cluster=cluster):
            state.boundary("before_rollback_receipt_snapshot")
            state._atomic_write(target_snapshot, raw, no_replace=True)
            state.boundary("after_rollback_receipt_snapshot")
    if target_snapshot.exists() or target_snapshot.is_symlink():
        if path.exists() or path.is_symlink():
            raw = state._secure_state_file(path)
            if _target_receipt(raw, journal, cluster=cluster):
                state.boundary("before_rollback_receipt_clear")
                path.unlink()
                archive.fsync_directory(path.parent)
                state.boundary("after_rollback_receipt_clear")
    if prior.exists() or prior.is_symlink():
        prior_raw = state._secure_state_file(prior)
        if path.exists() or path.is_symlink():
            if state._secure_state_file(path) != prior_raw:
                raise ProvisionError("restored prior runtime receipt conflicts")
        else:
            state.boundary("before_rollback_receipt_restore")
            state._atomic_write(path, prior_raw)
            state.boundary("after_rollback_receipt_restore")


def rollback_node(paths: state.ProvisionPaths, tx_id: str) -> dict[str, Any]:
    journal = state.load_journal(paths, tx_id)
    if journal["phase"] in {"rolled-back", "compensated-rollback"}:
        if paths.active.exists() or paths.active.is_symlink():
            expected = state._active_payload(journal["plan"], str(journal["plan_sha256"]), str(journal["node_id"]))
            if state._load_json(paths.active) != expected:
                raise ProvisionError("terminal rollback active sentinel changed")
            state.boundary("before_active_clear")
            paths.active.unlink()
            archive.fsync_directory(paths.active.parent)
            state.boundary("after_active_clear")
        return journal
    assert_unconsumed(paths, tx_id)
    original_decision = str(journal["decision"])
    if original_decision not in {"rollback", "commit"}:
        raise ProvisionError("runtime rollback lacks a durable decision")
    if journal["phase"] not in state.ROLLBACK_PHASES:
        _quarantine_target(paths, journal)
    if journal["phase"] == "rollback-runtime-quarantined":
        _restore_baseline(paths, journal)
    _restore_receipt(paths, journal, paths.local_receipt, cluster=False)
    _restore_receipt(paths, journal, paths.cluster_receipt, cluster=True)
    journal["phase"] = "compensated-rollback" if original_decision == "commit" else "rolled-back"
    if original_decision == "rollback":
        journal["node_receipt_sha256"] = ""
        journal["cluster_receipt_sha256"] = ""
    state.boundary("before_rollback_terminal_journal")
    state._write_journal(paths, journal)
    state.boundary("after_rollback_terminal_journal")
    if paths.active.exists() or paths.active.is_symlink():
        expected = state._active_payload(journal["plan"], str(journal["plan_sha256"]), str(journal["node_id"]))
        if state._load_json(paths.active) != expected:
            raise ProvisionError("runtime active sentinel changed before rollback cleanup")
        state.boundary("before_active_clear")
        paths.active.unlink()
        archive.fsync_directory(paths.active.parent)
        state.boundary("after_active_clear")
    return journal
