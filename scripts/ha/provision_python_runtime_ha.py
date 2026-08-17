#!/usr/bin/env python3
"""Manual, confirmation-gated coordinator for exact CPython HA provisioning."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_commit as commit
from scripts.ha import python_runtime_provision_contract as contract
from scripts.ha import python_runtime_provision_coordinator as coordinator
from scripts.ha import python_runtime_provision_peer as peer
from scripts.ha import python_runtime_provision_rollback as rollback
from scripts.ha import python_runtime_provision_state as state

ProvisionError = archive.ProvisionError
FORBIDDEN_ENV_KEYS: Final = {
    "BASHOPTS",
    "BASH_ENV",
    "CDPATH",
    "ENV",
    "GCONV_PATH",
    "GLOBIGNORE",
    "GLIBC_TUNABLES",
    "IFS",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "NODE_OPTIONS",
    "NODE_PATH",
    "PERL5LIB",
    "PERL5OPT",
    "PYTHONBREAKPOINT",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONPYCACHEPREFIX",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "PYTHONWARNINGS",
    "RUBYLIB",
    "RUBYOPT",
    "SHELLOPTS",
}
FORBIDDEN_ENV_PREFIXES: Final = ("BASH_FUNC_", "DYLD_", "GIT_CONFIG_", "LD_", "PYTHON")


def _require_control_process() -> None:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise ProvisionError("Python runtime provisioning requires root")
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ProvisionError("provisioner requires /usr/bin/python3 -B -I -S")
    resolved = Path(sys.executable).resolve(strict=True)
    if re.fullmatch(r"/usr/bin/python3(?:\.[0-9]{1,2})?", str(resolved)) is None:
        raise ProvisionError("provisioner is not anchored to the OS-maintained Python")
    if os.environ.get("PATH") not in {None, "/usr/sbin:/usr/bin:/sbin:/bin"}:
        raise ProvisionError("ambient PATH differs from the fixed control path")
    for name in os.environ:
        if name in FORBIDDEN_ENV_KEYS or name.startswith(FORBIDDEN_ENV_PREFIXES):
            raise ProvisionError(f"ambient execution-control variable is forbidden: {name}")


def _assert_node_identity(node_id: str) -> None:
    expected_hostname, expected_ip = {
        "node01": ("ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01", "10.106.0.3"),
        "node02": ("linas-app-lon1-02", "10.106.0.4"),
    }[node_id]
    if socket.gethostname() != expected_hostname:
        raise ProvisionError("fixed HA hostname identity is wrong")
    result = subprocess.run(
        ["/usr/sbin/ip", "-o", "-4", "addr", "show"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=10,
        env={"HOME": "/nonexistent", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    addresses = {token.split("/", 1)[0] for token in result.stdout.decode("ascii", "strict").split() if "/" in token}
    if result.returncode or expected_ip not in addresses:
        raise ProvisionError("fixed HA private address identity is wrong")


def _load_durable_plan(paths: state.ProvisionPaths, tx_id: str, plan_sha256: str) -> dict[str, Any]:
    plan = state._load_json(paths.tx_root(tx_id) / "authority" / "plan.json")
    return contract.validate_plan(plan, plan_sha256)


def _peer_control_root(tx_id: str) -> Path:
    return Path("/var/lib/linasbot/meta-ha") / state.TRANSACTIONS_NAME / tx_id / "control"


def _participant(arguments: argparse.Namespace, paths: state.ProvisionPaths) -> dict[str, Any]:
    _assert_node_identity("node02")
    plan = _load_durable_plan(paths, arguments.transaction_id, arguments.plan_sha256)
    with state.common_lock(paths):
        if arguments.command == "_peer-prepare":
            journal = state.prepare_node(paths, plan, arguments.plan_sha256, "node02")
            return {"schema": 1, "status": journal["phase"], "transaction_id": arguments.transaction_id}
        if arguments.command == "_peer-commit":
            state.record_decision(paths, arguments.transaction_id, "commit")
            _receipt, digest = commit.commit_node(paths, arguments.transaction_id)
            return {"schema": 1, "status": "node-receipt-published", "node_receipt_sha256": digest}
        if arguments.command == "_peer-cluster":
            raw = sys.stdin.buffer.read(65537)
            if len(raw) > 65536:
                raise ProvisionError("cluster receipt input is oversized")
            try:
                receipt = json.loads(raw.decode("utf-8", "strict"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ProvisionError("cluster receipt input is invalid") from exc
            digest = commit.install_cluster_receipt(paths, arguments.transaction_id, receipt)
            return {"schema": 1, "status": "committed", "cluster_receipt_sha256": digest}
        if arguments.command == "_peer-rollback-preflight":
            evidence, digest = rollback.staged_preflight(paths, plan, arguments.plan_sha256, "node02")
            return {
                "schema": 1,
                "status": "rollback-preflight",
                "preflight_sha256": digest,
                "evidence": evidence,
            }
        if arguments.command == "_peer-abort-stage":
            return rollback.abort_staged(paths, plan, arguments.plan_sha256, "node02")
        if arguments.command == "_peer-rollback":
            if arguments.authority_decision not in {"commit", "rollback"}:
                raise ProvisionError("peer rollback decision authority is invalid")
            journal_path = paths.journal(arguments.transaction_id)
            if not (journal_path.exists() or journal_path.is_symlink()):
                result = rollback.abort_staged(paths, plan, arguments.plan_sha256, "node02")
                return result
            journal = state.load_journal(paths, arguments.transaction_id)
            if journal["phase"] not in state.ROLLBACK_PHASES:
                _evidence, observed = rollback.rollback_preflight(paths, arguments.transaction_id)
                if observed != arguments.preflight_sha256:
                    raise ProvisionError("peer rollback preflight authority changed")
            if journal["phase"] == "initiated":
                journal = rollback.abort_initiated(paths, arguments.transaction_id, arguments.authority_decision)
            else:
                if journal["decision"] == "undecided":
                    state.record_decision(paths, arguments.transaction_id, arguments.authority_decision)
                elif journal["decision"] != arguments.authority_decision:
                    raise ProvisionError("peer journal differs from coordinator decision")
                journal = rollback.rollback_node(paths, arguments.transaction_id)
            return {"schema": 1, "status": journal["phase"], "transaction_id": arguments.transaction_id}
    raise ProvisionError("unsupported peer operation")


def _continue_commit(paths: state.ProvisionPaths, plan: dict[str, Any], plan_sha256: str) -> dict[str, Any]:
    tx_id = str(plan["transaction_id"])
    control_root = peer.stage_peer(paths, plan, plan_sha256)
    coordinator.update(paths, phase="peer-staged")
    prepared = peer.call_peer(control_root, ["_peer-prepare", tx_id, plan_sha256])
    if (
        prepared.get("schema") != 1
        or prepared.get("transaction_id") != tx_id
        or prepared.get("status")
        not in {"prepared", "decision-recorded", "runtime-published", "node-receipt-published", "committed"}
    ):
        raise ProvisionError("peer prepare acknowledgement is invalid")
    coordinator.update(paths, phase="peer-prepared")
    state.prepare_node(paths, plan, plan_sha256, "node01")
    coordinator.update(paths, phase="both-prepared")
    authority, _digest = coordinator.load(paths)
    if authority["decision"] == "undecided":
        authority = coordinator.update(paths, phase="decision-durable", decision="commit")
    if authority["decision"] != "commit":
        raise ProvisionError("runtime recovery authority is not commit")
    peer_result = peer.call_peer(control_root, ["_peer-commit", tx_id, plan_sha256])
    peer_digest = str(peer_result.get("node_receipt_sha256", ""))
    if contract.SHA256_RE.fullmatch(peer_digest) is None:
        raise ProvisionError("peer node receipt acknowledgement is invalid")
    state.record_decision(paths, tx_id, "commit")
    _local_receipt, local_digest = commit.commit_node(paths, tx_id)
    node_hashes = {"node01": local_digest, "node02": peer_digest}
    cluster = contract.cluster_receipt(plan, plan_sha256, node_hashes)
    cluster_raw = contract.canonical(cluster)
    cluster_sha = hashlib.sha256(cluster_raw).hexdigest()
    coordinator.update(
        paths,
        phase="node-receipts-durable",
        node_receipt_sha256=node_hashes,
    )
    coordinator.update(
        paths,
        phase="cluster-receipt-durable",
        cluster_receipt=cluster,
        cluster_receipt_sha256=cluster_sha,
    )
    peer_cluster = peer.call_peer(
        control_root,
        ["_peer-cluster", tx_id, plan_sha256],
        input_payload=cluster_raw,
    )
    if peer_cluster.get("cluster_receipt_sha256") != cluster_sha:
        raise ProvisionError("peer cluster receipt acknowledgement is invalid")
    if commit.install_cluster_receipt(paths, tx_id, cluster) != cluster_sha:
        raise ProvisionError("local cluster receipt digest is invalid")
    coordinator.update(paths, phase="committed")
    coordinator.archive_and_clear(paths)
    return {"schema": 1, "status": "committed", "transaction_id": tx_id, "cluster_receipt_sha256": cluster_sha}


def _new_apply(arguments: argparse.Namespace, paths: state.ProvisionPaths) -> dict[str, Any]:
    authority = _authority(arguments)
    bundle = authority.bundle_path(paths.state_root)
    plan, plan_sha256 = contract.build_plan(authority, bundle, enforce_path=False)
    if arguments.plan_sha256 != plan_sha256:
        raise ProvisionError("apply plan digest differs from the read-only plan")
    expected = f"APPLY_PYTHON_RUNTIME_{plan_sha256.upper()}"
    if arguments.confirm != expected:
        raise ProvisionError("exact Python runtime apply confirmation is missing")
    tx_id = str(plan["transaction_id"])
    with state.common_lock(paths):
        state._ensure_roots(paths, tx_id)
        terminal = coordinator.terminal(paths, tx_id)
        if terminal is not None:
            payload, _digest = terminal
            if payload["plan_sha256"] != plan_sha256:
                raise ProvisionError("terminal runtime transaction differs from this plan")
            if not _clear_exact_terminal_remnant(paths, terminal):
                raise ProvisionError("live runtime coordinator diverges from the terminal transaction")
            return _terminal_result(payload)
        coordinator.abort_foreign_undecided_snapshot(paths, tx_id)
        state.assert_no_collisions(paths)
        state.snapshot_authority(paths, plan, plan_sha256, bundle)
        initial = coordinator.template(plan, plan_sha256)
        initial["phase"] = "authority-snapshotted"
        coordinator.write(paths, initial, no_replace=True)
        return _continue_commit(paths, plan, plan_sha256)


def _terminal_result(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": 1,
        "status": payload["phase"],
        "transaction_id": payload["transaction_id"],
    }
    if payload["cluster_receipt_sha256"]:
        result["cluster_receipt_sha256"] = payload["cluster_receipt_sha256"]
    return result


def _clear_exact_terminal_remnant(paths: state.ProvisionPaths, terminal: tuple[dict[str, Any], str]) -> bool:
    if not (paths.coordinator.exists() or paths.coordinator.is_symlink()):
        return True
    if coordinator.load(paths) != terminal:
        return False
    coordinator.archive_and_clear(paths)
    return True


def _local_rollback(
    paths: state.ProvisionPaths,
    plan: dict[str, Any],
    plan_sha256: str,
    authority_decision: str,
    preflight_sha256: str,
) -> dict[str, Any]:
    tx_id = str(plan["transaction_id"])
    journal_path = paths.journal(tx_id)
    if not (journal_path.exists() or journal_path.is_symlink()):
        return rollback.abort_staged(paths, plan, plan_sha256, "node01")
    journal = state.load_journal(paths, tx_id)
    if journal["phase"] not in state.ROLLBACK_PHASES:
        _evidence, observed = rollback.rollback_preflight(paths, tx_id)
        if observed != preflight_sha256:
            raise ProvisionError("local rollback preflight authority changed")
    if journal["phase"] == "initiated":
        return rollback.abort_initiated(paths, tx_id, authority_decision)
    if journal["decision"] == "undecided":
        state.record_decision(paths, tx_id, authority_decision)
    elif journal["decision"] != authority_decision:
        raise ProvisionError("local journal differs from coordinator decision")
    return rollback.rollback_node(paths, tx_id)


def _continue_rollback(
    paths: state.ProvisionPaths,
    plan: dict[str, Any],
    plan_sha256: str,
) -> dict[str, Any]:
    tx_id = str(plan["transaction_id"])
    authority, _digest = coordinator.load(paths)
    if authority["phase"] in {"rolled-back", "compensated-rollback"}:
        coordinator.archive_and_clear(paths)
        return {"schema": 1, "status": authority["phase"], "transaction_id": tx_id}
    if authority["phase"] == "rollback-preflight-durable":
        preflight = dict(authority["rollback_preflight_sha256"])
        authority_decision = str(authority["decision"])
        control_root = peer.stage_peer(paths, plan, plan_sha256)
    else:
        _local_evidence, local_preflight = rollback.staged_preflight(paths, plan, plan_sha256, "node01")
        control_root = peer.stage_peer(paths, plan, plan_sha256)
        peer_result = peer.call_peer(control_root, ["_peer-rollback-preflight", tx_id, plan_sha256])
        peer_preflight = str(peer_result.get("preflight_sha256", ""))
        if contract.SHA256_RE.fullmatch(peer_preflight) is None:
            raise ProvisionError("peer rollback preflight acknowledgement is invalid")
        authority_decision = "commit" if authority["decision"] == "commit" else "rollback"
        preflight = {"node01": local_preflight, "node02": peer_preflight}
        authority = coordinator.update(
            paths,
            phase="rollback-preflight-durable",
            decision=authority_decision,
            rollback_decision="rollback",
            rollback_preflight_sha256=preflight,
        )
    peer_result = peer.call_peer(
        control_root,
        [
            "_peer-rollback",
            tx_id,
            plan_sha256,
            authority_decision,
            preflight["node02"],
        ],
    )
    expected_phase = "compensated-rollback" if authority_decision == "commit" else "rolled-back"
    if peer_result.get("status") not in {expected_phase, "staged-aborted"}:
        raise ProvisionError("peer rollback acknowledgement is invalid")
    local = _local_rollback(paths, plan, plan_sha256, authority_decision, preflight["node01"])
    if local.get("phase", local.get("status")) not in {expected_phase, "staged-aborted"}:
        raise ProvisionError("local rollback outcome is invalid")
    coordinator.update(paths, phase=expected_phase)
    coordinator.archive_and_clear(paths)
    return {"schema": 1, "status": expected_phase, "transaction_id": tx_id}


def _recovery(
    arguments: argparse.Namespace, paths: state.ProvisionPaths, *, rollback_requested: bool
) -> dict[str, Any]:
    with state.common_lock(paths):
        terminal = coordinator.terminal(paths, arguments.transaction_id)
        if paths.coordinator.exists() or paths.coordinator.is_symlink():
            authority, digest = coordinator.load(paths)
            if terminal == (authority, digest):
                coordinator.archive_and_clear(paths)
            else:
                terminal = None
        else:
            if terminal is None:
                raise ProvisionError("runtime recovery coordinator authority is missing")
            authority, digest = terminal
        if digest != arguments.journal_sha256 or authority["transaction_id"] != arguments.transaction_id:
            raise ProvisionError("recovery journal differs from owner-confirmed authority")
        tx_id = arguments.transaction_id
        decision = str(authority["decision"])
        rollback_durable = authority["rollback_decision"] == "rollback"
        action = "ROLLBACK" if rollback_requested or rollback_durable or decision != "commit" else "COMMIT"
        prefix = "ROLLBACK_COMMITTED" if rollback_requested and decision == "commit" else "RECOVER"
        expected = f"{prefix}_PYTHON_RUNTIME_{tx_id.upper()}_{digest.upper()}_{action}"
        if arguments.confirm != expected:
            raise ProvisionError("exact Python runtime recovery confirmation is missing")
        if terminal is not None:
            if not rollback_requested or authority["phase"] != "committed":
                return _terminal_result(authority)
            authority = coordinator.restore_terminal(paths, tx_id, digest)
        plan_sha256 = str(authority["plan_sha256"])
        plan = _load_durable_plan(paths, tx_id, plan_sha256)
        if action == "COMMIT":
            return _continue_commit(paths, plan, plan_sha256)
        return _continue_rollback(paths, plan, plan_sha256)


def _authority(arguments: argparse.Namespace) -> contract.Authority:
    return contract.Authority.build(
        arguments.artifact_id,
        arguments.artifact_api_sha256,
        arguments.manifest_sha256,
        arguments.run_id,
        arguments.run_attempt,
        arguments.target_sha,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "dry-run", "apply"):
        command = subparsers.add_parser(name)
        command.add_argument("artifact_id")
        command.add_argument("artifact_api_sha256")
        command.add_argument("manifest_sha256")
        command.add_argument("run_id")
        command.add_argument("run_attempt")
        command.add_argument("target_sha")
        if name == "apply":
            command.add_argument("plan_sha256")
            command.add_argument("confirm")
    status = subparsers.add_parser("status")
    status.add_argument("transaction_id")
    for name in ("recover", "rollback"):
        command = subparsers.add_parser(name)
        command.add_argument("transaction_id")
        command.add_argument("journal_sha256")
        command.add_argument("confirm")
    for name in (
        "_peer-prepare",
        "_peer-commit",
        "_peer-cluster",
        "_peer-rollback-preflight",
        "_peer-abort-stage",
    ):
        command = subparsers.add_parser(name)
        command.add_argument("transaction_id")
        command.add_argument("plan_sha256")
    peer_rollback = subparsers.add_parser("_peer-rollback")
    peer_rollback.add_argument("transaction_id")
    peer_rollback.add_argument("plan_sha256")
    peer_rollback.add_argument("authority_decision")
    peer_rollback.add_argument("preflight_sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    _require_control_process()
    arguments = build_parser().parse_args(argv)
    paths = state.ProvisionPaths()
    if arguments.command.startswith("_peer-"):
        result = _participant(arguments, paths)
    else:
        _assert_node_identity("node01")
        if arguments.command in {"plan", "dry-run"}:
            qg_authority = _authority(arguments)
            plan, digest = contract.build_plan(qg_authority, qg_authority.bundle_path(paths.state_root))
            result = {
                "schema": 1,
                "status": "read-only-plan",
                "plan": plan,
                "plan_sha256": digest,
                "apply_confirmation": f"APPLY_PYTHON_RUNTIME_{digest.upper()}",
            }
        elif arguments.command == "apply":
            result = _new_apply(arguments, paths)
        elif arguments.command == "status":
            if paths.coordinator.exists() or paths.coordinator.is_symlink():
                coordinator_state, digest = coordinator.load(paths)
            else:
                terminal = coordinator.terminal(paths, arguments.transaction_id)
                if terminal is None:
                    raise ProvisionError("runtime status authority is missing")
                coordinator_state, digest = terminal
            if arguments.transaction_id != coordinator_state["transaction_id"]:
                raise ProvisionError("status transaction authority is wrong")
            decision = str(coordinator_state["decision"])
            action = (
                "ROLLBACK" if coordinator_state["rollback_decision"] == "rollback" or decision != "commit" else "COMMIT"
            )
            result = {
                "schema": 1,
                "status": coordinator_state["phase"],
                "decision": decision,
                "journal_sha256": digest,
                "recovery_confirmation": (
                    f"RECOVER_PYTHON_RUNTIME_{arguments.transaction_id.upper()}_{digest.upper()}_{action}"
                ),
            }
            if decision == "commit":
                result["rollback_confirmation"] = (
                    f"ROLLBACK_COMMITTED_PYTHON_RUNTIME_{arguments.transaction_id.upper()}_{digest.upper()}_ROLLBACK"
                )
        elif arguments.command == "recover":
            result = _recovery(arguments, paths, rollback_requested=False)
        else:
            result = _recovery(arguments, paths, rollback_requested=True)
    print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisionError as exc:
        print(f"[python-runtime-ha] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
