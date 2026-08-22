"""Pre-restore peer drain may defer tree proof; later drain stays required."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
_TREE_DRIFT = "canonical Python runtime tree differs from the reviewed pristine artifact"
_SHA = "a" * 40
_TX = "/var/lib/linasbot/meta-ha/tx-test"
_GENERIC_REMOTE = re.compile(r'remote_node "\$[^"]+" assert-drained(?:\s|\\)')
_DEFERRED_REMOTE = re.compile(r'remote_node "\$[^"]+" assert-drained-deferred(?:\s|\\)')
_DEFERRED_CALL = 'remote_node "$peer_host" assert-drained-deferred "$peer_previous_sha" "$tx_dir"'


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def _orchestrate() -> str:
    return _slice(_helper(), "orchestrate() {", 'case "${1:-}" in')


def _dispatch() -> str:
    return _slice(_helper(), "\nnode_dispatch() {", "\nreject_self_peer() {")


def _proof_classifier() -> str:
    dispatch = _dispatch()
    proof_end = dispatch.index('esac\n  case "$phase" in')
    return dispatch[dispatch.index('case "$phase" in') : proof_end + 4]


def _drained_work_cases() -> str:
    dispatch = _dispatch()
    work = dispatch[dispatch.index('esac\n  case "$phase" in') :]
    return work[work.index("    assert-drained)\n") : work.index("    assert-ready)\n")]


def _dispatch_proof_mode(phase: str) -> str:
    script = (
        "set -euo pipefail\n"
        'phase="$1"\n'
        'runtime_expected_node=""\n'
        'assert_python_runtime_contract() { printf "%s\\n" "${2:-required}" >&2; }\n'
        f"{_proof_classifier()}\n"
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


def _run_drained_work(phase: str, *args: str) -> subprocess.CompletedProcess[str]:
    script = (
        "set -euo pipefail\n"
        f'phase="{phase}"\n'
        'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
        'validate_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "invalid SHA"; }\n'
        'validate_tx_dir() { [[ "$1" == /var/lib/linasbot/meta-ha/* ]] || die "invalid tx"; }\n'
        'node_assert_release_drained() { printf "drained %s %s\\n" "$1" "$2"; }\n'
        'case "$phase" in\n'
        f"{_drained_work_cases()}"
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


def _contract_tree_proof_snippets() -> tuple[str, str]:
    source = _helper()
    contract_start = source.index("\nassert_python_runtime_contract() {")
    selector_start = source.index('  case "$tree_proof" in\n', contract_start)
    selector = source[selector_start : source.index("\n  esac\n", selector_start) + 8]
    gate_start = source.index('  if [ "$tree_proof" = required ]; then\n', contract_start)
    gate = source[gate_start : source.index("\n  fi\n", gate_start) + 5]
    assert "required|deferred-until-restore) ;;" in selector
    assert "assert_python_runtime_tree_pristine_os" in gate
    return selector, gate


def _run_tree_proof(mode: str) -> subprocess.CompletedProcess[str]:
    selector, gate = _contract_tree_proof_snippets()
    script = (
        "set -euo pipefail\n"
        f'tree_proof="{mode}"\n'
        'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
        f'assert_python_runtime_tree_pristine_os() {{ die "{_TREE_DRIFT}"; }}\n'
        f"{selector}\n"
        f"{gate}\n"
        'printf "tree-proof-passed\\n"\n'
    )
    return subprocess.run(
        ["bash", "-s"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )


def test_outer_dispatch_defers_only_the_distinct_assert_drained_phase() -> None:
    assert _dispatch_proof_mode("assert-drained-deferred") == "deferred-until-restore"
    assert _dispatch_proof_mode("assert-drained") == "required"
    assert _dispatch_proof_mode("activate") == "required"
    assert _dispatch_proof_mode("verify-staged-qg-payloads") == "required"
    assert _dispatch_proof_mode("rollback") == "required"
    proof = _proof_classifier()
    assert "|assert-drained-deferred|" in proof
    assert "|assert-drained|" not in proof
    assert "assert-drained)" not in proof.split("deferred-until-restore", 1)[0]


def test_both_drain_work_phases_validate_and_run_the_same_release_drain() -> None:
    expected = f"drained {_SHA} {_TX}\n"
    for phase in ("assert-drained", "assert-drained-deferred"):
        ran = _run_drained_work(phase, _SHA, _TX)
        assert ran.returncode == 0, ran.stderr
        assert ran.stdout == expected
    missing = _run_drained_work("assert-drained-deferred")
    assert missing.returncode != 0
    unknown = _run_drained_work("assert-drained-optional", _SHA, _TX)
    assert unknown.returncode != 0
    assert "unknown node phase: assert-drained-optional" in unknown.stderr
    cases = _drained_work_cases()
    assert cases.count("validate_sha") == 2
    assert cases.count("validate_tx_dir") == 2
    assert cases.count('node_assert_release_drained "$1" "$2"') == 2


def test_required_tree_proof_reproduces_pre_restore_bytecode_drift_failure() -> None:
    required = _run_tree_proof("required")
    deferred = _run_tree_proof("deferred-until-restore")
    invalid = _run_tree_proof("optional")
    assert required.returncode != 0
    assert _TREE_DRIFT in required.stderr
    assert "tree-proof-passed" not in required.stdout
    assert deferred.returncode == 0, deferred.stderr
    assert deferred.stdout.strip() == "tree-proof-passed"
    assert _TREE_DRIFT not in deferred.stderr
    assert invalid.returncode != 0
    assert "Python runtime tree proof mode is invalid" in invalid.stderr


def test_orchestrate_defers_exactly_one_pre_restore_peer_drain() -> None:
    source = _helper()
    orchestrate = _orchestrate()
    assert source.count("assert-drained-deferred") == 3
    assert _DEFERRED_REMOTE.findall(source) == [_DEFERRED_CALL.rsplit(" ", 2)[0] + " "]
    assert orchestrate.count(_DEFERRED_CALL) == 1
    marked = orchestrate.index('update_deploy_journal "peer-marked"')
    drain = orchestrate.index('sleep "$drain_seconds"', marked)
    deferred = orchestrate.index(_DEFERRED_CALL, drain)
    staging = orchestrate.index('log "staging peer first with recoverable mode-600 backup archives"', deferred)
    peer_stage = orchestrate.index('remote_node "$peer_host" stage ', staging)
    remat = orchestrate.index("apply_cpython_runtime_immutability", peer_stage)
    assert marked < drain < deferred < staging < peer_stage < remat
    between_mark_and_stage = orchestrate[marked:staging]
    assert "apply_cpython_runtime_immutability" not in between_mark_and_stage
    assert "apply-cpython-runtime-immutability" not in between_mark_and_stage
    assert 'remote_node "$peer_host" assert-drained "' not in between_mark_and_stage
    drained = _slice(source, "node_assert_release_drained() {", "node_assert_serving_contract() {")
    assert 'test "$(current_head)" = "$expected_sha"' in drained
    assert 'git -C "$REPO_DIR" diff --quiet "$expected_sha" --' in drained
    assert 'audit_untracked_runtime "$tx_dir" "precommit-drained"' in drained
    assert "node_assert_runtime_drained" in drained


def test_later_assert_drained_calls_stay_generic_and_required() -> None:
    source = _helper()
    orchestrate = _orchestrate()
    recover = _slice(source, "recover_deployment() {", "retry_distinct_reconciliation() {")
    retry = _slice(source, "retry_distinct_reconciliation() {", "print_deploy_journal_identity() {")
    commit = _slice(source, "commit_target_deployment() {", "orchestrate() {")
    rollback = orchestrate[orchestrate.index("rollback_transaction() {") : orchestrate.index("on_exit() {")]
    deferred = orchestrate.index(_DEFERRED_CALL)
    staging = orchestrate.index('log "staging peer first with recoverable mode-600 backup archives"', deferred)
    peer_stage = orchestrate.index('remote_node "$peer_host" stage ', staging)
    remat = orchestrate.index("apply_cpython_runtime_immutability", peer_stage)
    after_remat = orchestrate[remat:]
    first_generic_after_remat = orchestrate.index(
        'remote_node "$peer_host" assert-drained "$peer_previous_sha" "$tx_dir"', remat
    )
    assert deferred < staging < peer_stage < remat < first_generic_after_remat
    windows = {
        "recover": recover,
        "retry": retry,
        "commit": commit,
        "rollback": rollback,
        "after-remat": after_remat,
    }
    for name, window in windows.items():
        assert "assert-drained-deferred" not in window, name
        assert _GENERIC_REMOTE.search(window), name
    assert len(_GENERIC_REMOTE.findall(source)) == 12
    assert len(_GENERIC_REMOTE.findall(after_remat)) == 3
    assert after_remat.index(
        'remote_node "$peer_host" assert-drained "$peer_previous_sha" "$tx_dir"'
    ) < after_remat.index('update_deploy_journal "both-nodes-drained-before-activation"')
    activate = after_remat.index('update_deploy_journal "peer-activated"')
    assert after_remat.index('remote_node "$peer_host" assert-drained "$target_sha" "$tx_dir"', activate) > activate
    assert _dispatch_proof_mode("assert-drained") == "required"
    apply = _slice(source, "apply_cpython_runtime_immutability() {", "require_root() {")
    assert 'assert_python_runtime_contract "$(configured_node_id)"' in apply
    assert "deferred-until-restore" not in apply
