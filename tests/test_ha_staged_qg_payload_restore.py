"""After remat, QG provenance of staged bytes must fail closed before activation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.ha.release_artifact_contract import tree_evidence

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _verify_fn() -> str:
    source = _helper()
    return source[
        source.index("verify_staged_qg_payloads_after_restore() {") : source.index("assert_stage_artifact_parity() {")
    ]


def _tree_python() -> str:
    body = _verify_fn()
    marker = "from scripts.ha.release_artifact_contract import tree_evidence"
    start = body.rindex("import json", 0, body.index(marker))
    return body[start : body.index("\nPY\n", start)]


def _payload(tree: Path) -> dict[str, object]:
    evidence = tree_evidence(tree)
    return {
        "archive": tree.name + ".tar",
        "archive_sha256": "a" * 64,
        "tree_sha256": evidence.tree_sha256,
        "file_count": evidence.file_count,
        "total_size": evidence.total_size,
    }


def _stage(tmp_path: Path) -> Path:
    stage = tmp_path / "stage"
    wheels = stage / "wheels"
    dashboard = stage / "repo" / "dashboard" / "build"
    control = stage / "control-plane"
    wheels.mkdir(parents=True)
    dashboard.mkdir(parents=True)
    control.mkdir(parents=True)
    (wheels / "pkg-1.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
    (dashboard / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (control / "deploy").mkdir()
    (control / "deploy" / "helper.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    os.chmod(control / "deploy" / "helper.sh", 0o755)
    return stage


def _summary(stage: Path) -> str:
    return json.dumps(
        {
            "payloads": {
                "wheelhouse": _payload(stage / "wheels"),
                "dashboard": _payload(stage / "repo" / "dashboard" / "build"),
                "control_plane": _payload(stage / "control-plane"),
            }
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _run_tree_python(stage: Path, summary: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-I", "-S", "-", str(ROOT), str(stage), summary],
        input=_tree_python(),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
    )


def test_restore_verifier_rebinds_qg_bundle_and_actual_staged_trees() -> None:
    body = _verify_fn()
    assert "deferred-until-restore" not in body
    assert 'assert_python_runtime_contract "$(configured_node_id)"' in body
    assert "assert_release_bundle" in body
    assert "tree_evidence" in body
    assert 'stage / "wheels"' in body
    assert 'stage / "repo/dashboard/build"' in body
    assert 'stage / "control-plane"' in body
    assert "verify_stage_manifest" not in body
    assert "write_activation_phase" not in body
    assert "peer-activate-started" not in body
    assert "recover-admit" not in body
    assert "staged Quality Gates payload trees differ from the reviewed release after restore" in body


def test_both_nodes_reverify_qg_staged_bytes_before_activate_or_admit() -> None:
    source = _helper()
    verify = _verify_fn()
    dispatch = source[source.index("node_dispatch() {") : source.index("reject_self_peer() {")]
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    retry = source[source.index("retry_distinct_reconciliation() {") : source.index("deployment_recovery_status() {")]
    commit = source[source.index("commit_target_deployment() {") : source.index("orchestrate() {")]
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    activate = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    peer_call = 'remote_node "$peer_host" verify-staged-qg-payloads'
    local_call = 'verify_staged_qg_payloads_after_restore "$tx_dir" "$target_sha" "$previous_sha"'
    remat = orchestrate.index("apply_cpython_runtime_immutability")
    local_verify = orchestrate.index(local_call, remat)
    peer_verify = orchestrate.index(peer_call, local_verify)
    activate_start = orchestrate.index('update_deploy_journal "peer-activate-started"', peer_verify)
    assert remat < local_verify < peer_verify < activate_start
    assert orchestrate.index('remote_node "$peer_host" activate', activate_start) > peer_verify
    retry_verify = retry.index(local_call)
    retry_peer = retry.index(peer_call, retry_verify)
    assert retry.index('update_retry_journal "retry-both-nodes-drained-before-activation"') < retry_verify
    assert retry_peer < retry.index('update_retry_journal "retry-peer-activate"', retry_peer)
    commit_verify = commit.index(local_call)
    commit_peer = commit.index(peer_call, commit_verify)
    assert commit.index("apply_cpython_runtime_immutability") < commit_verify
    assert commit_peer < commit.index('update_commit_journal "peer-admit-started" commit')
    recover_commit = recover[
        recover.index('update_recovery_journal "commit-recovery-parity"') : recover.index(
            'update_recovery_journal "rollback-restoring"'
        )
    ]
    assert local_call in recover_commit
    assert peer_call in recover_commit
    assert recover_commit.index(local_call) < recover_commit.index(peer_call)
    assert recover_commit.index(peer_call) < recover_commit.index("expired before commit admission")
    assert recover_commit.index("expired before commit admission") < recover_commit.index(
        'update_recovery_journal "commit-peer-admit"'
    )
    assert recover_commit.index(peer_call) < recover_commit.index('remote_node "$peer_host" recover-admit')
    rollback = recover[
        recover.index('update_recovery_journal "rollback-restoring"') : recover.index(
            'update_recovery_journal "rollback-peer-admit"'
        )
    ]
    assert local_call not in rollback
    assert activate.index(local_call) < activate.index("verify_stage_manifest")
    assert activate.index(local_call) < activate.index("write_activation_phase")
    assert "verify-staged-qg-payloads)" in dispatch
    deferred = dispatch[dispatch.index('case "$phase" in') : dispatch.index("deferred-until-restore >/dev/null")]
    assert "verify-staged-qg-payloads" not in deferred
    assert "deferred-until-restore" not in verify


def test_tampered_staged_bytes_fail_qg_tree_and_cannot_self_admit(tmp_path: Path) -> None:
    stage = _stage(tmp_path)
    expected = _summary(stage)
    authentic = _run_tree_python(stage, expected)
    assert authentic.returncode == 0, authentic.stderr

    wheel = stage / "wheels" / "pkg-1.0-py3-none-any.whl"
    before = wheel.read_bytes()
    wheel.write_bytes(before + b"\ntampered")
    tampered_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
    published_hash = hashlib.sha256(before).hexdigest()
    assert tampered_hash != published_hash

    # stage.complete self-consistency would hash the live staged bytes and
    # accept a manifest written by the same unproven interpreter.
    live_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert live_digest == tampered_hash

    blocked = _run_tree_python(stage, expected)
    assert blocked.returncode != 0
    assert "staged wheelhouse tree differs from Quality Gates authority" in blocked.stderr
    assert "write_activation_phase" not in _verify_fn()
    assert "recover-admit" not in _verify_fn()
