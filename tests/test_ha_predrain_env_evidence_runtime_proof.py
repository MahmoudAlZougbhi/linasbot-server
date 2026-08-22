"""Pre-drain cluster env evidence may defer tree proof; later parity stays required."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
_TARGET = "a" * 40
_SOURCE = "b" * 40
_PARITY_CALL = re.compile(r'assert_cluster_runtime_env_parity "\$peer_host" "\$[^"]+" "\$[^"]+"([^\n]*)')


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def _orchestrate() -> str:
    return _slice(_helper(), "orchestrate() {", 'case "${1:-}" in')


def _dispatch() -> str:
    return _slice(_helper(), "\nnode_dispatch() {", "\nreject_self_peer() {")


def _parity_fn() -> str:
    return _slice(_helper(), "assert_cluster_runtime_env_parity() {", "\nassert_git_repository_trust() {")


def _parity_modes(text: str) -> list[str]:
    modes: list[str] = []
    for match in _PARITY_CALL.finditer(text):
        rest = match.group(1).strip()
        if rest.startswith("deferred-until-restore"):
            modes.append("deferred-until-restore")
        else:
            modes.append("required")
    return modes


def _run_parity(*args: str) -> subprocess.CompletedProcess[str]:
    script = (
        "set -euo pipefail\n"
        'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
        'cluster_runtime_env_evidence() { printf "local\\n"; }\n'
        "remote_node() { printf '%s\\n' \"$2\" >&2; printf 'peer\\n'; }\n"
        "compare_cluster_runtime_env_evidence() { return 0; }\n"
        f"{_parity_fn()}\n"
        'assert_cluster_runtime_env_parity peer-host "$@"\n'
    )
    return subprocess.run(
        ["bash", "-s", "--", *args],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_env_evidence_work(phase: str, *args: str) -> subprocess.CompletedProcess[str]:
    dispatch = _dispatch()
    work = dispatch[dispatch.index('esac\n  case "$phase" in') :]
    cases = work[work.index("    env-evidence)\n") : work.index("    stage)\n")]
    script = (
        "set -euo pipefail\n"
        f'phase="{phase}"\n'
        'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
        'validate_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "invalid SHA"; }\n'
        'cluster_runtime_env_evidence() { printf "evidence %s %s %s\\n" "$1" "$2" "$3"; }\n'
        'case "$phase" in\n'
        f"{cases}"
        '    *) die "unknown node phase: $phase" ;;\n'
        "esac\n"
    )
    return subprocess.run(
        ["bash", "-s", "--", *args],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )


def _dispatch_proof_mode(phase: str) -> str:
    dispatch = _dispatch()
    proof_end = dispatch.index('esac\n  case "$phase" in')
    proof = dispatch[dispatch.index('case "$phase" in') : proof_end + 4]
    script = (
        "set -euo pipefail\n"
        'phase="$1"\n'
        'runtime_expected_node=""\n'
        'assert_python_runtime_contract() { printf "%s\\n" "${2:-required}" >&2; }\n'
        f"{proof}\n"
    )
    ran = subprocess.run(
        ["bash", "-s", "--", phase],
        input=script,
        text=True,
        capture_output=True,
        check=True,
    )
    assert ran.stdout == ""
    return ran.stderr.strip()


def test_parity_helper_defaults_to_required_env_evidence_phase() -> None:
    required = _run_parity(_TARGET, _SOURCE)
    omitted = _run_parity(_TARGET, _SOURCE, "required")
    assert required.returncode == 0, required.stderr
    assert omitted.returncode == 0, omitted.stderr
    assert required.stderr.strip() == "env-evidence"
    assert omitted.stderr.strip() == "env-evidence"


def test_parity_helper_selects_distinct_deferred_phase_only_when_explicit() -> None:
    deferred = _run_parity(_TARGET, _SOURCE, "deferred-until-restore")
    assert deferred.returncode == 0, deferred.stderr
    assert deferred.stderr.strip() == "env-evidence-deferred"
    invalid = _run_parity(_TARGET, _SOURCE, "optional")
    assert invalid.returncode != 0
    assert "cluster runtime env parity proof mode is invalid" in invalid.stderr
    assert "env-evidence" not in invalid.stdout


def test_outer_dispatch_defers_only_the_distinct_env_evidence_phase() -> None:
    assert _dispatch_proof_mode("env-evidence-deferred") == "deferred-until-restore"
    assert _dispatch_proof_mode("env-evidence") == "required"
    assert _dispatch_proof_mode("verify-staged-qg-payloads") == "required"
    assert _dispatch_proof_mode("activate") == "required"
    dispatch = _dispatch()
    proof_end = dispatch.index('esac\n  case "$phase" in')
    proof = dispatch[dispatch.index('case "$phase" in') : proof_end]
    assert "|env-evidence-deferred)" in proof or proof.strip().endswith("env-evidence-deferred")
    assert "|env-evidence|" not in proof
    assert "verify-staged-qg-payloads" not in proof


def test_env_evidence_work_phases_validate_args_and_collect_the_same_evidence() -> None:
    expected = f"evidence {_SOURCE} {_TARGET} node02\n"
    for phase in ("env-evidence", "env-evidence-deferred"):
        ran = _run_env_evidence_work(phase, _TARGET, _SOURCE, "node02")
        assert ran.returncode == 0, ran.stderr
        assert ran.stdout == expected
    missing = _run_env_evidence_work("env-evidence-deferred")
    assert missing.returncode != 0
    unknown = _run_env_evidence_work("env-evidence-optional", _TARGET, _SOURCE, "node02")
    assert unknown.returncode != 0
    assert "unknown node phase: env-evidence-optional" in unknown.stderr


def test_orchestrate_defers_only_the_pre_transaction_parity_call() -> None:
    orchestrate = _orchestrate()
    initial = 'assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha" deferred-until-restore'
    assert orchestrate.count(initial) == 1
    pre = orchestrate[: orchestrate.index(initial)]
    post = orchestrate[orchestrate.index(initial) + len(initial) :]
    assert _parity_modes(orchestrate) == [
        "deferred-until-restore",
        "required",
        "required",
        "required",
    ]
    assert _parity_modes(post) == ["required", "required", "required"]
    assert 'assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"\n' in post
    assert 'assert_cluster_runtime_env_parity "$peer_host" "$previous_sha" "$target_sha"' in post
    assert "peer_phase=env-evidence\n" in _parity_fn()
    assert "peer_phase=env-evidence-deferred\n" in _parity_fn()
    assert "update_deploy_journal" not in pre
    assert "write_deploy_journal" not in pre
    assert "transaction_started=1" not in pre
    assert "node_mark_maintenance" not in pre
    assert "mark-maintenance" not in pre
    assert "ensure-maintenance" not in pre
    assert "backup_live_node" not in pre
    assert "apply_cpython_runtime_immutability" not in pre
    assert "apply-cpython-runtime-immutability" not in pre
    assert 'sleep "$drain_seconds"' not in pre
    both_preflights = pre.index('if [ "$local_preflight_rc" -ne 0 ]')
    assert "BASELINE_ARTIFACT_EVIDENCE" in pre[both_preflights:]


def test_later_parity_paths_keep_default_required_proof() -> None:
    source = _helper()
    recover = _slice(source, "recover_deployment() {", "retry_distinct_reconciliation() {")
    retry = _slice(source, "retry_distinct_reconciliation() {", "print_deploy_journal_identity() {")
    commit = _slice(source, "commit_target_deployment() {", "orchestrate() {")
    assert _parity_modes(recover) == ["required"] * 4
    assert _parity_modes(retry) == ["required"]
    assert _parity_modes(commit) == ["required"] * 2
    assert _parity_modes(source).count("deferred-until-restore") == 1
    apply = _slice(source, "apply_cpython_runtime_immutability() {", "require_root() {")
    verify = _slice(
        source,
        "verify_staged_qg_payloads_after_restore() {",
        "assert_stage_artifact_parity() {",
    )
    assert 'assert_python_runtime_contract "$(configured_node_id)"' in apply
    assert "deferred-until-restore" not in apply
    assert 'assert_python_runtime_contract "$(configured_node_id)"' in verify
    assert "deferred-until-restore" not in verify
