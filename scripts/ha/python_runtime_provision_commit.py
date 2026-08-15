#!/usr/bin/env python3
"""Idempotent runtime publication and v2 receipt commit operations."""

from __future__ import annotations

import hashlib
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_contract as contract
from scripts.ha import python_runtime_provision_state as state

ProvisionError = archive.ProvisionError


def _clear_active(paths: state.ProvisionPaths, journal: Mapping[str, Any]) -> None:
    if not (paths.active.exists() or paths.active.is_symlink()):
        return
    expected = state._active_payload(journal["plan"], str(journal["plan_sha256"]), str(journal["node_id"]))
    if state._load_json(paths.active) != expected:
        raise ProvisionError("runtime active sentinel changed before commit cleanup")
    state.boundary("before_active_clear")
    paths.active.unlink()
    archive.fsync_directory(paths.active.parent)
    state.boundary("after_active_clear")


def _preserve_receipt(paths: state.ProvisionPaths, tx_id: str, source: Path, expected: bytes) -> bool:
    if not source.exists() and not source.is_symlink():
        return False
    raw = state._secure_state_file(source)
    if raw == expected:
        return True
    prior = paths.tx_root(tx_id) / "prior"
    archive.secure_directory(prior, mode=0o700, create=True)
    destination = prior / source.name
    if destination.exists() or destination.is_symlink():
        if state._secure_state_file(destination) != raw:
            raise ProvisionError("prior runtime receipt backup conflicts")
    else:
        state._atomic_write(destination, raw, no_replace=True)
    return False


def commit_node(paths: state.ProvisionPaths, tx_id: str) -> tuple[dict[str, Any], str]:
    journal = state.load_journal(paths, tx_id)
    if journal["decision"] != "commit":
        raise ProvisionError("runtime commit lacks a durable commit decision")
    plan = journal["plan"]
    node_id = str(journal["node_id"])
    receipt = contract.node_receipt(plan, str(journal["plan_sha256"]), node_id)
    raw = contract.canonical(receipt)
    digest = hashlib.sha256(raw).hexdigest()
    if journal["phase"] == "committed":
        if state._secure_state_file(paths.local_receipt) != raw:
            raise ProvisionError("committed node receipt changed")
        archive.verify_runtime_before_use(paths.runtime)
        _clear_active(paths, journal)
        return receipt, digest
    candidate = paths.candidate(tx_id, node_id)
    previous = paths.previous(tx_id, node_id)
    if candidate.exists():
        archive.verify_runtime_before_use(candidate)
    if paths.runtime.exists() and candidate.exists() and not previous.exists():
        info = paths.runtime.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ProvisionError("existing runtime is not a preservable directory")
        state.boundary("before_previous_rename")
        archive.rename_durable(paths.runtime, previous)
        state.boundary("after_previous_rename")
    if not paths.runtime.exists():
        if not candidate.exists():
            raise ProvisionError("prepared runtime candidate is missing")
        state.boundary("before_runtime_rename")
        archive.rename_durable(candidate, paths.runtime)
        state.boundary("after_runtime_rename")
    archive.verify_runtime_before_use(paths.runtime)
    if journal["phase"] in {"decision-recorded", "prepared"}:
        journal["phase"] = "runtime-published"
        state._write_journal(paths, journal)
    adopted = _preserve_receipt(paths, tx_id, paths.local_receipt, raw)
    if not adopted:
        state.boundary("before_node_receipt")
        state._atomic_write(paths.local_receipt, raw)
        state.boundary("after_node_receipt")
    journal["phase"] = "node-receipt-published"
    journal["node_receipt_sha256"] = digest
    state._write_journal(paths, journal)
    return receipt, digest


def install_cluster_receipt(paths: state.ProvisionPaths, tx_id: str, receipt: Mapping[str, Any]) -> str:
    journal = state.load_journal(paths, tx_id)
    if journal["decision"] != "commit" or not journal["node_receipt_sha256"]:
        raise ProvisionError("cluster receipt cannot precede the node commit receipt")
    validated = contract.validate_cluster_receipt(receipt, journal["plan"], str(journal["plan_sha256"]))
    node_id = str(journal["node_id"])
    if validated["node_receipt_sha256"][node_id] != journal["node_receipt_sha256"]:
        raise ProvisionError("cluster receipt does not bind this node receipt")
    raw = contract.canonical(validated)
    digest = hashlib.sha256(raw).hexdigest()
    if journal["phase"] == "committed":
        if state._secure_state_file(paths.cluster_receipt) != raw:
            raise ProvisionError("committed cluster receipt changed")
        _clear_active(paths, journal)
        return digest
    adopted = _preserve_receipt(paths, tx_id, paths.cluster_receipt, raw)
    if not adopted:
        state.boundary("before_cluster_receipt")
        state._atomic_write(paths.cluster_receipt, raw)
        state.boundary("after_cluster_receipt")
    journal["phase"] = "committed"
    journal["cluster_receipt_sha256"] = digest
    state.boundary("before_committed_journal")
    state._write_journal(paths, journal)
    state.boundary("after_committed_journal")
    _clear_active(paths, journal)
    return digest
