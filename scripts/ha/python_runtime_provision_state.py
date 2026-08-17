#!/usr/bin/env python3
"""Durable per-node state machine for the portable CPython HA transaction."""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_authority as authority_io
from scripts.ha import python_runtime_provision_contract as contract

ProvisionError = archive.ProvisionError
STATE_ROOT: Final = Path("/var/lib/linasbot/meta-ha")
RUNTIME_PATH: Final = Path("/opt/linasbot-runtime/cpython-3.13.15")
LOCK_PATH: Final = Path("/run/lock/linasbot-meta-live.lock")
ACTIVE_NAME: Final = "python-runtime-provision.active"
COORDINATOR_NAME: Final = "python-runtime-provision.coordinator.json"
LOCAL_RECEIPT_NAME: Final = "python-runtime-provisioned.json"
CLUSTER_RECEIPT_NAME: Final = "python-runtime-cluster.json"
TRANSACTIONS_NAME: Final = "python-runtime-transactions"
JOURNAL_FORMAT: Final = "linas-python-runtime-node-journal-v1"
ACTIVE_FORMAT: Final = "linas-python-runtime-active-v1"
COLLISION_NAMES: Final = (
    "bootstrap.active",
    "bootstrap.coordinator.json",
    "transaction.json",
    "env.before",
    "deploy.active",
    "deploy-node.active",
    "controlled-failover.active",
    "registry-nfs-retire.active",
    "rekey/runtime.guard",
)
CONSUMER_NAMES: Final = ("bootstrap.active", "bootstrap.coordinator.json", "deploy.active", "deploy-node.active")
BOOTSTRAP_COMMIT_OVERLAP: Final = ("bootstrap.active", "bootstrap.coordinator.json")
_SNAPSHOT_MARKERS: Final = (
    "manifest_snapshot",
    "control_snapshot",
    "wheelhouse_snapshot",
    "dashboard_snapshot",
    "source_bundle_snapshot",
    "runtime_snapshot",
)
CRASH_BOUNDARIES: Final = (
    "before_active_publish",
    "after_active_publish",
    "before_plan_snapshot",
    "after_plan_snapshot",
    "before_manifest_snapshot",
    "after_manifest_snapshot",
    "before_control_snapshot",
    "after_control_snapshot",
    "before_wheelhouse_snapshot",
    "after_wheelhouse_snapshot",
    "before_dashboard_snapshot",
    "after_dashboard_snapshot",
    "before_source_bundle_snapshot",
    "after_source_bundle_snapshot",
    "before_runtime_snapshot",
    "after_runtime_snapshot",
    *(
        f"after_{marker}_{step}"
        for marker in _SNAPSHOT_MARKERS
        for step in ("temp_create", "chunk_write", "file_fsync", "temp_dir_fsync", "publish")
    ),
    "before_candidate_rename",
    "after_candidate_rename",
    "before_prepared_journal",
    "after_prepared_journal",
    "before_decision_publish",
    "after_decision_publish",
    "before_previous_rename",
    "after_previous_rename",
    "before_runtime_rename",
    "after_runtime_rename",
    "before_node_receipt",
    "after_node_receipt",
    "before_cluster_receipt",
    "after_cluster_receipt",
    "before_committed_journal",
    "after_committed_journal",
    "before_rollback_runtime_rename",
    "after_rollback_runtime_rename",
    "before_rollback_runtime_journal",
    "after_rollback_runtime_journal",
    "before_rollback_baseline_rename",
    "after_rollback_baseline_rename",
    "before_rollback_baseline_journal",
    "after_rollback_baseline_journal",
    "before_rollback_receipt_snapshot",
    "after_rollback_receipt_snapshot",
    "before_rollback_receipt_clear",
    "after_rollback_receipt_clear",
    "before_rollback_receipt_restore",
    "after_rollback_receipt_restore",
    "before_rollback_terminal_journal",
    "after_rollback_terminal_journal",
    "before_active_clear",
    "after_active_clear",
    "before_coordinator_publish",
    "after_coordinator_publish",
    "before_coordinator_clear",
    "after_coordinator_clear",
)
JOURNAL_PHASES: Final = {
    "initiated",
    "prepared",
    "decision-recorded",
    "runtime-published",
    "node-receipt-published",
    "committed",
    "rollback-runtime-quarantined",
    "rollback-baseline-restored",
    "rolled-back",
    "compensated-rollback",
}
COMMIT_PHASES: Final = {
    "decision-recorded",
    "runtime-published",
    "node-receipt-published",
    "committed",
}
ROLLBACK_PHASES: Final = {
    "rollback-runtime-quarantined",
    "rollback-baseline-restored",
    "rolled-back",
    "compensated-rollback",
}
_FAILPOINT_HOOK: Callable[[str], None] | None = None


@dataclass(frozen=True)
class ProvisionPaths:
    state_root: Path = STATE_ROOT
    runtime: Path = RUNTIME_PATH
    lock_path: Path = LOCK_PATH

    @property
    def runtime_parent(self) -> Path:
        return self.runtime.parent

    @property
    def active(self) -> Path:
        return self.state_root / ACTIVE_NAME

    @property
    def coordinator(self) -> Path:
        return self.state_root / COORDINATOR_NAME

    @property
    def local_receipt(self) -> Path:
        return self.state_root / LOCAL_RECEIPT_NAME

    @property
    def cluster_receipt(self) -> Path:
        return self.state_root / CLUSTER_RECEIPT_NAME

    def tx_root(self, tx_id: str) -> Path:
        if contract.TX_RE.fullmatch(tx_id) is None:
            raise ProvisionError("runtime transaction ID is invalid")
        return self.state_root / TRANSACTIONS_NAME / tx_id

    def journal(self, tx_id: str) -> Path:
        return self.tx_root(tx_id) / "node-journal.json"

    def candidate(self, tx_id: str, node_id: str) -> Path:
        _node(node_id)
        return self.runtime_parent / f".candidate-{tx_id}-{node_id}"

    def previous(self, tx_id: str, node_id: str) -> Path:
        _node(node_id)
        return self.runtime_parent / f".previous-{tx_id}-{node_id}"

    def quarantine(self, tx_id: str, node_id: str) -> Path:
        _node(node_id)
        return self.runtime_parent / f".quarantine-{tx_id}-{node_id}"


def _node(node_id: str) -> str:
    if node_id not in contract.NODES:
        raise ProvisionError("runtime node identity is invalid")
    return node_id


def set_failpoint_hook(hook: Callable[[str], None] | None) -> None:
    global _FAILPOINT_HOOK
    _FAILPOINT_HOOK = hook


def boundary(name: str) -> None:
    if name not in CRASH_BOUNDARIES:
        raise AssertionError(f"unreviewed crash boundary: {name}")
    if _FAILPOINT_HOOK is not None:
        _FAILPOINT_HOOK(name)


_secure_state_file = authority_io.secure_state_file
_load_json = authority_io.load_json
_atomic_write = authority_io.atomic_write


def _ensure_roots(paths: ProvisionPaths, tx_id: str) -> None:
    archive.secure_directory(paths.state_root, mode=0o700, create=True)
    archive.secure_directory(paths.runtime_parent, mode=0o755, create=True)
    transactions = paths.state_root / TRANSACTIONS_NAME
    archive.secure_directory(transactions, mode=0o700, create=True)
    archive.secure_directory(paths.tx_root(tx_id), mode=0o700, create=True)


@contextmanager
def common_lock(paths: ProvisionPaths) -> Iterator[None]:
    paths.lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        paths.lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, archive.EXPECTED_UID, archive.EXPECTED_GID)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProvisionError("common production lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _active_payload(plan: Mapping[str, Any], plan_sha256: str, node_id: str) -> dict[str, Any]:
    return {
        "schema": 1,
        "format": ACTIVE_FORMAT,
        "transaction_id": plan["transaction_id"],
        "node_id": _node(node_id),
        "plan_sha256": plan_sha256,
    }


def claim_active(paths: ProvisionPaths, plan: Mapping[str, Any], plan_sha256: str, node_id: str) -> None:
    expected = _active_payload(plan, plan_sha256, node_id)
    if paths.active.exists() or paths.active.is_symlink():
        if _load_json(paths.active) != expected:
            raise ProvisionError("runtime provision sentinel belongs to another transaction")
        return
    boundary("before_active_publish")
    _atomic_write(paths.active, contract.canonical(expected), no_replace=True)
    boundary("after_active_publish")


def _commit_decided_bootstrap(paths: ProvisionPaths) -> bool:
    coordinator = paths.state_root / "bootstrap.coordinator.json"
    if coordinator.exists() or coordinator.is_symlink():
        payload = _load_json(coordinator)
        if payload.get("schema") == 2 and payload.get("decision") == "commit":
            return True
    active = paths.state_root / "bootstrap.active"
    if not (active.exists() or active.is_symlink()):
        return False
    sent = _load_json(active)
    tx_id = sent.get("tx_id")
    if not isinstance(tx_id, str) or len(tx_id) != 32 or any(char not in "0123456789abcdef" for char in tx_id):
        return False
    journal = Path(f"/opt/.linasbot-meta-bootstrap-{tx_id}/journal.json")
    if not (journal.exists() or journal.is_symlink()):
        return False
    payload = _load_json(journal)
    return payload.get("status") == "applied" and payload.get("tx_id") == tx_id


def assert_no_collisions(paths: ProvisionPaths, tx_id: str | None = None) -> None:
    allow_commit = _commit_decided_bootstrap(paths)
    for relative in COLLISION_NAMES:
        if allow_commit and relative in BOOTSTRAP_COMMIT_OVERLAP:
            continue
        candidate = paths.state_root / relative
        if candidate.exists() or candidate.is_symlink():
            raise ProvisionError(f"conflicting production transaction exists: {relative}")
    if paths.coordinator.exists() or paths.coordinator.is_symlink():
        payload = _load_json(paths.coordinator)
        if tx_id is None or payload.get("transaction_id") != tx_id:
            raise ProvisionError("another Python runtime coordinator is active")


def snapshot_authority(paths: ProvisionPaths, plan: Mapping[str, Any], plan_sha256: str, bundle: Path) -> Path:
    return authority_io.snapshot_authority(paths, plan, plan_sha256, bundle, boundary=boundary)


def _journal_template(plan: Mapping[str, Any], plan_sha256: str, node_id: str, had_previous: bool) -> dict[str, Any]:
    return {
        "schema": 1,
        "format": JOURNAL_FORMAT,
        "transaction_id": plan["transaction_id"],
        "node_id": _node(node_id),
        "plan": dict(plan),
        "plan_sha256": plan_sha256,
        "phase": "initiated",
        "decision": "undecided",
        "had_previous": had_previous,
        "node_receipt_sha256": "",
        "cluster_receipt_sha256": "",
    }


def load_journal(paths: ProvisionPaths, tx_id: str) -> dict[str, Any]:
    payload = _load_json(paths.journal(tx_id))
    expected_keys = {
        "schema",
        "format",
        "transaction_id",
        "node_id",
        "plan",
        "plan_sha256",
        "phase",
        "decision",
        "had_previous",
        "node_receipt_sha256",
        "cluster_receipt_sha256",
    }
    if (
        set(payload) != expected_keys
        or payload.get("schema") != 1
        or payload.get("format") != JOURNAL_FORMAT
        or payload.get("transaction_id") != tx_id
        or payload.get("node_id") not in contract.NODES
        or type(payload.get("had_previous")) is not bool
        or payload.get("phase") not in JOURNAL_PHASES
    ):
        raise ProvisionError("node runtime journal schema is invalid")
    plan_sha256 = payload.get("plan_sha256")
    if not isinstance(plan_sha256, str) or contract.SHA256_RE.fullmatch(plan_sha256) is None:
        raise ProvisionError("node runtime journal plan digest is invalid")
    plan = contract.validate_plan(payload["plan"], plan_sha256)
    if plan["transaction_id"] != tx_id:
        raise ProvisionError("node runtime journal plan binding is invalid")
    decision = payload.get("decision")
    phase = str(payload["phase"])
    node_digest = payload.get("node_receipt_sha256")
    cluster_digest = payload.get("cluster_receipt_sha256")
    if decision not in {"undecided", "commit", "rollback"}:
        raise ProvisionError("node runtime decision is invalid")
    if any(
        not isinstance(value, str) or (value != "" and contract.SHA256_RE.fullmatch(value) is None)
        for value in (node_digest, cluster_digest)
    ) or (cluster_digest and not node_digest):
        raise ProvisionError("node runtime receipt journal digest is invalid")
    if phase in {"initiated", "prepared"} and (decision != "undecided" or node_digest or cluster_digest):
        raise ProvisionError("node runtime pre-decision journal is inconsistent")
    if phase == "decision-recorded" and (decision not in {"commit", "rollback"} or node_digest or cluster_digest):
        raise ProvisionError("node runtime decision journal is inconsistent")
    if phase == "runtime-published" and (decision != "commit" or node_digest or cluster_digest):
        raise ProvisionError("node runtime publication journal is inconsistent")
    if phase == "node-receipt-published" and (decision != "commit" or not node_digest or cluster_digest):
        raise ProvisionError("node runtime receipt journal is inconsistent")
    if phase == "committed" and (decision != "commit" or not node_digest or not cluster_digest):
        raise ProvisionError("node runtime committed journal is inconsistent")
    if phase == "rolled-back" and (decision != "rollback" or node_digest or cluster_digest):
        raise ProvisionError("node runtime rollback journal is inconsistent")
    if phase == "compensated-rollback" and decision != "commit":
        raise ProvisionError("node runtime compensating rollback journal is inconsistent")
    if phase in {"rollback-runtime-quarantined", "rollback-baseline-restored"} and decision not in {
        "commit",
        "rollback",
    }:
        raise ProvisionError("node runtime rollback subphase is inconsistent")
    return payload


def _write_journal(paths: ProvisionPaths, payload: Mapping[str, Any]) -> None:
    _atomic_write(paths.journal(str(payload["transaction_id"])), contract.canonical(payload))
    if load_journal(paths, str(payload["transaction_id"])) != payload:
        raise ProvisionError("node runtime journal durable readback failed")


def prepare_node(
    paths: ProvisionPaths,
    plan: Mapping[str, Any],
    plan_sha256: str,
    node_id: str,
    *,
    bundle: Path | None = None,
) -> dict[str, Any]:
    plan = contract.validate_plan(plan, plan_sha256)
    tx_id = str(plan["transaction_id"])
    _ensure_roots(paths, tx_id)
    assert_no_collisions(paths, tx_id)
    claim_active(paths, plan, plan_sha256, node_id)
    authority_root = paths.tx_root(tx_id) / "authority"
    if bundle is not None:
        authority_root = snapshot_authority(paths, plan, plan_sha256, bundle)
    archive.secure_directory(authority_root, mode=0o700)
    runtime_archive = authority_root / str(plan["artifact_name"])
    if archive.file_evidence(runtime_archive, max_bytes=archive.MAX_ARCHIVE_BYTES) != (
        plan["artifact_sha256"],
        plan["runtime_archive_size"],
    ):
        raise ProvisionError("durable runtime authority differs from the plan")
    journal_path = paths.journal(tx_id)
    if journal_path.exists() or journal_path.is_symlink():
        journal = load_journal(paths, tx_id)
        if journal["plan_sha256"] != plan_sha256 or journal["node_id"] != node_id:
            raise ProvisionError("node runtime recovery authority conflicts")
    else:
        journal = _journal_template(
            plan, plan_sha256, node_id, paths.runtime.exists() or paths.previous(tx_id, node_id).exists()
        )
        _write_journal(paths, journal)
    if journal["phase"] in COMMIT_PHASES:
        if journal["phase"] == "decision-recorded" and paths.candidate(tx_id, node_id).exists():
            archive.verify_runtime_before_use(paths.candidate(tx_id, node_id))
        elif journal["phase"] != "decision-recorded":
            archive.verify_runtime_before_use(paths.runtime)
        return journal
    if journal["phase"] in ROLLBACK_PHASES:
        return journal
    candidate = paths.candidate(tx_id, node_id)
    partial = candidate.parent / f".{candidate.name}.extracting"
    if partial.exists() or partial.is_symlink():
        try:
            archive.verify_runtime_before_use(partial)
        except ProvisionError:
            incomplete = next_quarantine_path(paths, tx_id, node_id, "incomplete")
            archive.rename_durable(partial, incomplete)
        else:
            boundary("before_candidate_rename")
            archive.rename_durable(partial, candidate)
            boundary("after_candidate_rename")
    if not candidate.exists():
        archive.extract_runtime_archive(runtime_archive, candidate, boundary=boundary)
    archive.verify_runtime_before_use(candidate)
    if journal["phase"] == "initiated":
        journal["phase"] = "prepared"
        boundary("before_prepared_journal")
        _write_journal(paths, journal)
        boundary("after_prepared_journal")
    return journal


def record_decision(paths: ProvisionPaths, tx_id: str, decision: str) -> dict[str, Any]:
    if decision not in {"commit", "rollback"}:
        raise ProvisionError("runtime durable decision is invalid")
    journal = load_journal(paths, tx_id)
    if journal["decision"] == decision and journal["phase"] != "prepared":
        return journal
    if journal["phase"] != "prepared" or journal["decision"] != "undecided":
        raise ProvisionError("runtime node is not prepared for a decision")
    if journal["decision"] not in {"undecided", decision}:
        raise ProvisionError("runtime durable decision cannot be reversed")
    journal["decision"] = decision
    journal["phase"] = "decision-recorded"
    boundary("before_decision_publish")
    _write_journal(paths, journal)
    boundary("after_decision_publish")
    return journal


def quarantine_paths(paths: ProvisionPaths, tx_id: str, node_id: str, kind: str) -> tuple[Path, ...]:
    _node(node_id)
    if kind not in {"incomplete", "runtime"}:
        raise ProvisionError("runtime quarantine kind is invalid")
    prefix = f".quarantine-{kind}-{tx_id}-{node_id}-"
    entries: list[tuple[int, Path]] = []
    for entry in os.scandir(paths.runtime_parent):
        if not entry.name.startswith(prefix):
            continue
        suffix = entry.name.removeprefix(prefix)
        if len(suffix) != 6 or not suffix.isdecimal():
            raise ProvisionError("runtime quarantine counter is invalid")
        info = entry.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != archive.EXPECTED_UID
            or info.st_gid != archive.EXPECTED_GID
        ):
            raise ProvisionError("runtime quarantine object is unsafe")
        entries.append((int(suffix), Path(entry.path)))
    entries.sort()
    counters = [counter for counter, _path in entries]
    if counters != list(range(1, len(counters) + 1)) or len(counters) >= 999999:
        raise ProvisionError("runtime quarantine sequence is not monotonic")
    return tuple(path for _counter, path in entries)


def next_quarantine_path(paths: ProvisionPaths, tx_id: str, node_id: str, kind: str) -> Path:
    existing = quarantine_paths(paths, tx_id, node_id, kind)
    prefix = f".quarantine-{kind}-{tx_id}-{node_id}-"
    return paths.runtime_parent / f"{prefix}{len(existing) + 1:06d}"
