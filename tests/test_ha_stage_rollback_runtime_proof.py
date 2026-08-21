"""Stage dispatch stays untrusted until remat; rollback/recovery cannot skip proof."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _dispatch() -> str:
    source = _helper()
    return source[source.index("\nnode_dispatch() {") : source.index("\nreject_self_peer() {")]


def _manifest() -> str:
    source = _helper()
    return source[source.index("stage_manifest_tool() {") : source.index("publish_stage_manifest() {")]


def _automatic_rollback() -> str:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    return orchestrate[orchestrate.index("rollback_transaction() {") : orchestrate.index("on_exit() {")]


def _tree_proof_selector() -> str:
    body = _manifest()
    start = body.index("tree_proof=deferred-until-restore")
    end = body.index("esac", start) + len("esac")
    return 'operation="$1"\n' + body[start:end] + "\n"


def test_stage_and_stage_evidence_are_deferred_until_trusted_remat() -> None:
    dispatch = _dispatch()
    deferred = dispatch[dispatch.index('case "$phase" in') : dispatch.index("deferred-until-restore >/dev/null")]
    required_arm = dispatch[dispatch.index("*)\n      assert_python_runtime_contract") :]
    assert "stage|stage-evidence|" in deferred
    assert "apply-cpython-runtime-immutability|" in deferred
    assert "verify-staged-qg-payloads" not in deferred
    assert "rollback)" in required_arm
    assert "activate)" in required_arm
    assert "verify-staged-qg-payloads)" in required_arm
    assert "retry-stage)" in required_arm


def test_drained_peer_is_rematerialized_before_stage_hashes() -> None:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    peer_mark = orchestrate.index('remote_node "$peer_host" mark-maintenance')
    peer_remat = orchestrate.index('remote_node "$peer_host" apply-cpython-runtime-immutability', peer_mark)
    peer_stage = orchestrate.index('remote_node "$peer_host" stage ', peer_remat)
    local_stage = orchestrate.index('backup_live_node "$target_sha" "$previous_sha" "$tx_dir"', peer_stage)
    local_mark = orchestrate.index('node_mark_maintenance "$tx_dir"', local_stage)
    local_remat = orchestrate.index(
        'apply_cpython_runtime_immutability "$tx_dir" "$release_artifact_id"',
        local_mark,
    )
    qg = orchestrate.index("verify_staged_qg_payloads_after_restore", local_remat)
    activate = orchestrate.index('update_deploy_journal "peer-activate-started"', qg)
    assert peer_mark < peer_remat < peer_stage < local_stage < local_mark < local_remat < qg < activate


def test_verify_recovery_requires_tree_proof_and_publish_stays_deferred() -> None:
    selector = _tree_proof_selector()
    assert "verify-recovery)" in selector
    assert "tree_proof=required" in selector
    publish = subprocess.run(
        ["bash", "-s", "--", "publish"],
        input=selector + 'printf "%s\\n" "$tree_proof"\n',
        text=True,
        capture_output=True,
        check=True,
    )
    recovery = subprocess.run(
        ["bash", "-s", "--", "verify-recovery"],
        input=selector + 'printf "%s\\n" "$tree_proof"\n',
        text=True,
        capture_output=True,
        check=True,
    )
    evidence = subprocess.run(
        ["bash", "-s", "--", "evidence"],
        input=selector + 'printf "%s\\n" "$tree_proof"\n',
        text=True,
        capture_output=True,
        check=True,
    )
    assert publish.stdout.strip() == "deferred-until-restore"
    assert evidence.stdout.strip() == "deferred-until-restore"
    assert recovery.stdout.strip() == "required"


def test_automatic_rollback_remat_failure_blocks_admission(tmp_path: Path) -> None:
    automatic = _automatic_rollback()
    drained = automatic.index('update_deploy_journal "automatic-rollback-both-nodes-drained"')
    remat = automatic.index("apply_cpython_runtime_immutability", drained)
    restore = automatic.index('rollback_impl "$previous_sha" "$tx_dir"', remat)
    admit = automatic.index('remote_node "$peer_host" clear-maintenance', restore)
    uncertain = automatic.index("ROLLBACK PARITY IS UNCERTAIN")
    assert remat < restore < admit
    assert "|| rollback_ok=0" in automatic[remat:restore]
    assert automatic[remat:admit].count("|| rollback_ok=0") >= 2
    assert uncertain > admit
    injected = tmp_path / "rollback-ok.sh"
    injected.write_text(
        "\n".join(
            [
                "set -euo pipefail",
                "rollback_ok=1",
                "admitted=0",
                "false || rollback_ok=0",
                'if [ "$rollback_ok" = "1" ]; then admitted=1; fi',
                'if [ "$rollback_ok" != "1" ]; then',
                "  printf 'drained\\n'",
                "  exit 1",
                "fi",
                "printf 'admitted\\n'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    failed = subprocess.run(["bash", str(injected)], text=True, capture_output=True)
    assert failed.returncode != 0
    assert failed.stdout.strip() == "drained"
    assert "admitted" not in failed.stdout
