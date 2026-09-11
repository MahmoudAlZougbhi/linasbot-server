#!/usr/bin/env python3
"""Read-only, redacted diagnostics and correlated Meta controlled-test proof."""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["scripts.prod_meta_comment_runtime_probe"] = sys.modules[__name__]
    __package__ = "scripts"

from scripts.prod_meta_comment_runtime_probe_journal import (
    _diagnostic_journal_command,
    _phase_cutoff,
    _read_controlled_journal,
    _read_release_sha,
    _read_shared_outbound_attempts,
    _read_tail,
    _run_command,
    evaluate_controlled_attempt_documents,
    evaluate_controlled_markers,
)
from scripts.prod_meta_comment_runtime_probe_manifest import (
    load_node_verification_keys,
    parse_controlled_manifest,
    parse_failover_attestation,
    read_controlled_manifest,
    read_failover_attestation,
)
from scripts.prod_meta_comment_runtime_probe_types import (
    _MANIFEST_SHA_RE,
    _PEER_RE,
    _RELEASE_SHA_RE,
    CONTROLLED_SCHEMA,
    CONTROLLED_SURFACES,
    FAILOVER_SCHEMA,
    MAX_CHECK_DELAY_SECONDS,
    NODE_VERIFICATION_KEYS_FILE,
    PATTERNS,
    REQUIRED_EVIDENCE,
    REQUIRED_NODES,
    ControlledEvidenceError,
    ControlledManifest,
    ControlledMarker,
    FailoverAttestation,
    _canonical_json,
    missing_required_evidence,
    scan_evidence,
)

__all__ = [
    "CONTROLLED_SCHEMA",
    "CONTROLLED_SURFACES",
    "ControlledEvidenceError",
    "ControlledManifest",
    "ControlledMarker",
    "FAILOVER_SCHEMA",
    "FailoverAttestation",
    "MAX_CHECK_DELAY_SECONDS",
    "NODE_VERIFICATION_KEYS_FILE",
    "PATTERNS",
    "REQUIRED_EVIDENCE",
    "REQUIRED_NODES",
    "_canonical_json",
    "_parse_args",
    "_phase_cutoff",
    "_read_controlled_journal",
    "_read_release_sha",
    "_read_shared_outbound_attempts",
    "_run_command",
    "_run_controlled_gate",
    "evaluate_controlled_attempt_documents",
    "evaluate_controlled_markers",
    "load_node_verification_keys",
    "main",
    "missing_required_evidence",
    "os",
    "parse_controlled_manifest",
    "parse_failover_attestation",
    "read_controlled_manifest",
    "read_failover_attestation",
    "scan_evidence",
    "subprocess",
]


def _run_controlled_gate(args: argparse.Namespace) -> int:
    try:
        manifest, manifest_sha = read_controlled_manifest(args.controlled_manifest, args.manifest_sha256)
        if args.expected_release_sha != manifest.release_sha:
            raise ControlledEvidenceError("workflow_release_manifest_mismatch")
        now = datetime.now(UTC)
        cutoff = _phase_cutoff(manifest, phase=args.phase, now=now)
        local_release = _read_release_sha(repo_dir=args.repo_dir, peer_host=None)
        peer_release = _read_release_sha(repo_dir=args.repo_dir, peer_host=args.peer_host)
        if local_release != manifest.release_sha:
            raise ControlledEvidenceError("local_release_mismatch")
        if peer_release != manifest.release_sha:
            raise ControlledEvidenceError("peer_release_mismatch")
        verification_keys = load_node_verification_keys(args.node_verification_keys_file)
        initial_attestation, initial_attestation_sha = read_failover_attestation(
            args.initial_attestation,
            args.initial_attestation_sha256,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            verification_keys=verification_keys,
        )
        if initial_attestation.phase != "initial":
            raise ControlledEvidenceError("failover_initial_phase_invalid")
        replay_attestation: FailoverAttestation | None = None
        replay_attestation_sha: str | None = None
        if args.phase == "final":
            replay_attestation, replay_attestation_sha = read_failover_attestation(
                args.replay_attestation,
                args.replay_attestation_sha256,
                manifest=manifest,
                manifest_sha256=manifest_sha,
                verification_keys=verification_keys,
            )
            if replay_attestation.phase != "replay":
                raise ControlledEvidenceError("failover_replay_phase_invalid")
            if replay_attestation.lb_ready_projection_sha256 != initial_attestation.lb_ready_projection_sha256:
                raise ControlledEvidenceError("failover_lb_projection_changed")
        markers = _read_controlled_journal(
            node="node01",
            start=manifest.start,
            cutoff=cutoff,
            peer_host=None,
        )
        markers.extend(
            _read_controlled_journal(
                node="node02",
                start=manifest.start,
                cutoff=cutoff,
                peer_host=args.peer_host,
            )
        )
        passed, summary, reasons = evaluate_controlled_markers(
            manifest,
            markers,
            replay_after=replay_attestation.phase_proved_at if replay_attestation is not None else None,
        )
        attempts = _read_shared_outbound_attempts(manifest)
        attempts_passed, attempt_summary, attempt_reasons = evaluate_controlled_attempt_documents(
            manifest,
            attempts,
        )
        passed = passed and attempts_passed
        reasons.extend(attempt_reasons)
    except ControlledEvidenceError as exc:
        print(f"[controlled-evidence] GATE_FAILED reason={exc}")
        return 2

    print(
        f"[controlled-evidence] phase={args.phase} test_run_id={manifest.test_run_id} "
        f"manifest_sha256={manifest_sha} release_sha={manifest.release_sha} "
        f"initial_node={manifest.initial_node} replay_node={manifest.replay_node} "
        f"initial_attestation_sha256={initial_attestation_sha}"
    )
    if replay_attestation_sha is not None:
        print(f"[controlled-evidence] replay_attestation_sha256={replay_attestation_sha}")
    for surface in CONTROLLED_SURFACES:
        item = summary[surface]
        nodes = ",".join(item["nodes"]) or "none"
        replay_nodes = ",".join(item["post_initial_replay_nodes"]) or "none"
        print(
            f"[controlled-evidence] surface={surface} provider_accepted={item['provider_accepted']} "
            f"forbidden={item['forbidden']} duplicate_suppressed={item['duplicate_suppressed']} "
            f"dedicated_auth={item['instagram_login_authenticated']} "
            f"nodes={nodes} replay_nodes={replay_nodes}"
        )
        attempt = attempt_summary[surface]
        print(
            f"[controlled-evidence] surface={surface} shared_status={attempt['status']} "
            f"shared_attempt_sequence={attempt['attempt_sequence']} "
            f"shared_provider_hash={str(attempt['provider_id_hash_present']).lower()}"
        )
    if not passed:
        print(f"[controlled-evidence] GATE_FAILED reasons={','.join(sorted(set(reasons)))}")
        return 2
    print(f"[controlled-evidence] GATE_PASSED phase={args.phase}")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="Require coarse, uncorrelated diagnostic coverage (not valid as final controlled-test proof).",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=30,
        help="Only inspect journal entries from this many recent minutes in diagnostic mode (default: 30).",
    )
    parser.add_argument(
        "--include-file-tails",
        action="store_true",
        help="Also inspect undated log-file tails in diagnostic mode; forbidden with coarse evidence requirements.",
    )
    parser.add_argument(
        "--include-ha-peer",
        action="store_true",
        help="Aggregate the diagnostic window from the required HA peer.",
    )
    parser.add_argument(
        "--peer-host",
        default="10.106.0.4",
        help="Internal HA peer hostname or address (default: 10.106.0.4).",
    )
    parser.add_argument(
        "--controlled-manifest",
        help="Root-owned 0600 manifest path, or '-' to read the manifest from stdin.",
    )
    parser.add_argument("--manifest-sha256", help="Expected SHA-256 of the exact controlled manifest bytes.")
    parser.add_argument("--initial-attestation", help="Root-owned initial-routing attestation path.")
    parser.add_argument("--initial-attestation-sha256", help="Expected SHA-256 of the initial attestation.")
    parser.add_argument("--replay-attestation", help="Root-owned post-failover routing attestation path.")
    parser.add_argument("--replay-attestation-sha256", help="Expected SHA-256 of the replay attestation.")
    parser.add_argument(
        "--node-verification-keys-file",
        default=NODE_VERIFICATION_KEYS_FILE,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--phase", choices=("initial", "final"), help="Controlled proof phase.")
    parser.add_argument("--expected-release-sha", help="Exact deployed release required by the workflow.")
    parser.add_argument("--repo-dir", default="/opt/linasbot", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.window_minutes < 1 or args.window_minutes > 10_080:
        parser.error("--window-minutes must be between 1 and 10080")
    if args.require_evidence and args.window_minutes > 60:
        parser.error("coarse evidence requires --window-minutes between 1 and 60")
    if args.require_evidence and args.include_file_tails:
        parser.error("--include-file-tails cannot be used as bounded coarse evidence")
    if _PEER_RE.fullmatch(str(args.peer_host)) is None:
        parser.error("--peer-host is invalid")
    controlled_args = (
        args.controlled_manifest,
        args.manifest_sha256,
        args.phase,
        args.expected_release_sha,
        args.initial_attestation,
        args.initial_attestation_sha256,
    )
    if args.controlled_manifest:
        if not all(controlled_args):
            parser.error("controlled mode requires manifest, failover attestation, hashes, phase, and release SHA")
        for value, label in (
            (args.manifest_sha256, "--manifest-sha256"),
            (args.initial_attestation_sha256, "--initial-attestation-sha256"),
        ):
            if _MANIFEST_SHA_RE.fullmatch(str(value)) is None:
                parser.error(f"{label} must be 64 lowercase hexadecimal characters")
        if _RELEASE_SHA_RE.fullmatch(str(args.expected_release_sha)) is None:
            parser.error("--expected-release-sha must be 40 lowercase hexadecimal characters")
        if args.phase == "final":
            if not args.replay_attestation or _MANIFEST_SHA_RE.fullmatch(str(args.replay_attestation_sha256)) is None:
                parser.error("final controlled mode requires replay attestation and exact SHA-256")
        elif args.replay_attestation or args.replay_attestation_sha256:
            parser.error("replay attestation is valid only for the final controlled phase")
        if args.require_evidence or args.include_file_tails or args.include_ha_peer:
            parser.error("controlled mode is separate from diagnostic evidence options")
    elif any((*controlled_args[1:], args.replay_attestation, args.replay_attestation_sha256)):
        parser.error("--controlled-manifest is required with controlled-mode options")
    return args


def _run_diagnostic(args: argparse.Namespace) -> int:
    journal = _run_command(_diagnostic_journal_command(window_minutes=args.window_minutes, peer_host=None))
    lines = journal.stdout.splitlines()
    peer_journal_returncode: int | None = None
    peer_line_count = 0
    if args.include_ha_peer:
        peer_journal = _run_command(
            _diagnostic_journal_command(window_minutes=args.window_minutes, peer_host=args.peer_host)
        )
        peer_journal_returncode = int(peer_journal.returncode)
        peer_lines = peer_journal.stdout.splitlines()
        peer_line_count = len(peer_lines)
        lines.extend(peer_lines)
    if args.include_file_tails:
        for pattern in (
            "/var/log/linasbot.log",
            "/var/log/linasbot.error.log",
            "/var/log/nginx/access.log",
            "/var/log/nginx/error.log",
            "/opt/linasbot/logs/*",
        ):
            for raw in glob.glob(pattern):
                path = Path(raw)
                if path.is_file():
                    lines.extend(_read_tail(path))

    counts = scan_evidence(lines)
    print(
        f"[comment-probe] journal_exit={journal.returncode} window_minutes={args.window_minutes} "
        f"file_tails={str(args.include_file_tails).lower()} ha_peer={str(args.include_ha_peer).lower()} "
        f"peer_journal_exit={peer_journal_returncode} peer_scanned_lines={peer_line_count} "
        f"scanned_lines={len(lines)}"
    )
    for name in sorted(PATTERNS):
        print(f"[comment-probe] {name}={counts[name]}")

    status_reasons: Counter[str] = Counter()
    for line in lines:
        match = re.search(
            r"\[meta-comment\] event_processing_completed channel=(\w+) status=(\w+) reason=([^\s]+)",
            line,
        )
        if match:
            status_reasons[f"{match.group(1)}:{match.group(2)}:{match.group(3)}"] += 1
        drop = re.search(
            r"\[meta-comment\] events_dropped object=(\w+) raw=(\d+) resolved=0 bindings=(\d+) reasons=(\{.*\})",
            line,
        )
        if drop:
            print(
                f"[comment-probe] drop object={drop.group(1)} raw={drop.group(2)} "
                f"bindings={drop.group(3)} reasons={drop.group(4)}"
            )
        ig = re.search(
            r"\[instagram-login\] webhook_authenticated object=(\w+) parsed=(\d+) "
            r"accepted=(\d+) duplicates=(\d+) comments=(\d+)",
            line,
        )
        if ig and int(ig.group(5)) > 0:
            print(
                f"[comment-probe] ig_login_comments object={ig.group(1)} "
                f"parsed={ig.group(2)} accepted={ig.group(3)} comments={ig.group(5)}"
            )
        mc = re.search(
            r"\[meta-comment\] webhook_authenticated object=(\w+) raw=(\d+) "
            r"parsed=(\d+) accepted=(\d+) duplicates=(\d+)",
            line,
        )
        if mc:
            print(
                f"[comment-probe] meta_comment_auth object={mc.group(1)} raw={mc.group(2)} "
                f"parsed={mc.group(3)} accepted={mc.group(4)}"
            )

    print(f"[comment-probe] completed_status_variants={len(status_reasons)}")
    for key, count in sorted(status_reasons.items()):
        print(f"[comment-probe] completed {key} occurrences={count}")
    if args.require_evidence:
        if journal.returncode != 0 or (args.include_ha_peer and peer_journal_returncode != 0):
            print("[comment-probe] COARSE_EVIDENCE_FAILED reason=journal_read_failed")
            return 2
        missing = missing_required_evidence(counts)
        for label, counter_name in REQUIRED_EVIDENCE.items():
            state = "PASS" if counts[counter_name] > 0 else "FAIL"
            print(f"[comment-probe] coarse {label}={state} count={counts[counter_name]}")
        if missing:
            print(f"[comment-probe] COARSE_EVIDENCE_FAILED missing={','.join(missing)}")
            return 2
        print("[comment-probe] COARSE_EVIDENCE_PASSED")
    print("[comment-probe] SUCCESS")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.controlled_manifest:
        return _run_controlled_gate(args)
    return _run_diagnostic(args)


if __name__ == "__main__":
    raise SystemExit(main())
