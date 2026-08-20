"""Steady HA baseline artifacts must name drift and require an explicit replace confirm."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"

_TARGET = "a" * 40
_PREVIOUS = "b" * 40
_OTHER_PREVIOUS = "c" * 40
_WHEELHOUSE = "e" * 64
_BASELINE_01 = "1" * 64
_BASELINE_02 = "2" * 64


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _stage_parity_python() -> str:
    source = _helper()
    start = source.index("assert_stage_artifact_parity() {")
    end = source.index("\nactivation_state_tool() {", start)
    chunk = source[start:end]
    python_start = chunk.index("import json\n")
    python_end = chunk.index("\nPY\n")
    return chunk[python_start:python_end]


def _evidence(*, wheelhouse: str, baseline: str, target: str = _TARGET) -> str:
    payload: dict[str, Any] = {
        "baseline_artifacts": {
            "artifact_projection_sha256": baseline,
            "schema": 1,
        },
        "control_plane_sha256": "c" * 64,
        "dashboard_build_sha256": "d" * 64,
        "deploy_version": "1",
        "release_bundle": {"artifact_id": "9339909286"},
        "schema": 1,
        "target_sha": target,
        "toolchain": {"python": "3.13"},
        "wheelhouse_sha256": wheelhouse,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _run_stage_parity(
    node01: str,
    node02: str,
    previous01: str,
    previous02: str,
    confirm: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-c",
            _stage_parity_python(),
            node01,
            node02,
            previous01,
            previous02,
            confirm,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_baseline_evidence_skips_bytecode_and_logs_each_root() -> None:
    helper = _helper()
    body = helper[
        helper.index("live_baseline_artifact_evidence() {") : helper.index("capture_baseline_artifact_evidence() {")
    ]
    assert '{"90-meta-ha-maintenance.conf", "__pycache__"}' in body
    assert 'child.suffix in {".pyc", ".pyo"}' in body
    assert "[ha-deploy] baseline-artifact" in body
    assert "dropin-api" in body
    assert "file=sys.stderr" in body


def test_assert_baseline_evidence_hashes_live_trees_after_production_restore() -> None:
    helper = _helper()
    capture = helper[
        helper.index("capture_baseline_artifact_evidence() {") : helper.index(
            "assert_baseline_artifact_evidence_restored() {"
        )
    ]
    assert 'evidence="$(live_baseline_artifact_evidence "$tx_dir")"' in capture
    assert_fn = helper[
        helper.index("assert_baseline_artifact_evidence_restored() {") : helper.index(
            "backup_live_node() {"
        )
    ]
    assert 'actual="$(live_baseline_artifact_evidence)"' in assert_fn
    assert 'live_baseline_artifact_evidence "$tx_dir"' not in assert_fn


def test_capture_uses_saved_production_nginx_after_peer_drain() -> None:
    helper = _helper()
    live = helper[
        helper.index("live_baseline_artifact_evidence() {") : helper.index(
            "capture_baseline_artifact_evidence() {"
        )
    ]
    capture = helper[
        helper.index("capture_baseline_artifact_evidence() {") : helper.index(
            "assert_baseline_artifact_evidence_restored() {"
        )
    ]
    backup = helper[helper.index("backup_live_node() {") : helper.index("prepare_retry_stage() {")]
    archive = helper[
        helper.index("archive_nginx_rollback_authority() {") : helper.index("verify_archive() {")
    ]
    assert 'nginx_source="$tx_dir/maintenance-nginx.conf"' in live
    assert 'evidence="$(live_baseline_artifact_evidence "$tx_dir")"' in capture
    assert 'archive_nginx_rollback_authority "$tx_dir"' in backup
    assert "archive_path \"$tx_dir/nginx.tar\"" not in backup
    assert "--transform 's,^maintenance-nginx.conf$,etc/nginx/sites-available/linasaibot,'" in archive
    assert 'linasbot-ha-maintenance-override' not in archive


def test_rollback_measures_tar_restored_nginx_before_maintenance_override() -> None:
    helper = _helper()
    body = helper[helper.index("rollback_impl() {") : helper.index("\nnode_activate() {")]
    rolled = body[body.index('if [ "$phase" = "rolled-back" ]; then') : body.index('test -f "$MAINTENANCE_FILE"')]
    assert rolled.index('tar --numeric-owner -C / -xpf "$tx_dir/nginx.tar"') < rolled.index(
        "assert_baseline_artifact_evidence_restored"
    )
    restored_tail = body[body.index("phase=restored") :]
    assert restored_tail.index("assert_baseline_artifact_evidence_restored") < restored_tail.index(
        "node_ensure_maintenance"
    )


def test_steady_baseline_mismatch_requires_hash_bound_replace_confirm() -> None:
    helper = _helper()
    workflow = WORKFLOW.read_text(encoding="utf-8")
    body = helper[
        helper.index("assert_cluster_runtime_env_parity ") : helper.index(
            'die "nodes do not share one approved drain interval"'
        )
    ]
    assert "node01 baseline artifacts:" in body
    assert "node02 baseline artifacts:" in body
    assert "REPLACE_DIVERGENT_BASELINE_" in body
    assert "WITH_RELEASE_" in body
    assert "required divergent-baseline confirm:" in body
    assert "divergent-baseline confirm is only valid when live artifacts differ" in body
    assert "DIVERGENT_BASELINE_CONFIRM=" in workflow
    assert "DIVERGENT_BASELINE_CONFIRM: ${{ inputs.DIVERGENT_BASELINE_CONFIRM }}" in workflow
    assert "baseline artifact evidence on $expected_node_id" in helper


def test_stage_parity_reads_owner_divergent_confirm() -> None:
    body = _helper()
    start = body.index("assert_stage_artifact_parity() {")
    end = body.index("\nactivation_state_tool() {", start)
    chunk = body[start:end]
    assert '"${DIVERGENT_BASELINE_CONFIRM:-}"' in chunk
    assert "divergent_confirm" in chunk
    assert "target stage artifacts differ between HA nodes" in chunk
    assert "divergent-baseline confirm does not bind the staged target SHA" in chunk


def test_stage_parity_equal_baselines_pass_without_confirm() -> None:
    evidence = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_01)
    result = _run_stage_parity(evidence, evidence, _PREVIOUS, _PREVIOUS, "")
    assert result.returncode == 0, result.stderr


def test_stage_parity_rejects_divergent_baselines_without_confirm() -> None:
    node01 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_01)
    node02 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_02)
    result = _run_stage_parity(node01, node02, _PREVIOUS, _PREVIOUS, "")
    assert result.returncode == 1
    assert "steady rollback baseline artifacts differ between HA nodes" in result.stderr


def test_stage_parity_allows_divergent_baselines_with_target_bound_confirm() -> None:
    node01 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_01)
    node02 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_02)
    confirm = f"REPLACE_DIVERGENT_BASELINE_{_BASELINE_01[:16]}_{_BASELINE_02[:16]}_WITH_RELEASE_{_TARGET}"
    result = _run_stage_parity(node01, node02, _PREVIOUS, _PREVIOUS, confirm)
    assert result.returncode == 0, result.stderr


def test_stage_parity_rejects_confirm_bound_to_a_different_target() -> None:
    node01 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_01)
    node02 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_02)
    confirm = f"REPLACE_DIVERGENT_BASELINE_{_BASELINE_01[:16]}_{_BASELINE_02[:16]}_WITH_RELEASE_{_PREVIOUS}"
    result = _run_stage_parity(node01, node02, _PREVIOUS, _PREVIOUS, confirm)
    assert result.returncode == 1
    assert "divergent-baseline confirm does not bind the staged target SHA" in result.stderr


def test_stage_parity_still_rejects_mismatched_target_payload() -> None:
    node01 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_01)
    node02 = _evidence(wheelhouse="f" * 64, baseline=_BASELINE_02)
    confirm = f"REPLACE_DIVERGENT_BASELINE_{_BASELINE_01[:16]}_{_BASELINE_02[:16]}_WITH_RELEASE_{_TARGET}"
    result = _run_stage_parity(node01, node02, _PREVIOUS, _PREVIOUS, confirm)
    assert result.returncode == 1
    assert "target stage artifacts differ between HA nodes: wheelhouse_sha256" in result.stderr


def test_stage_parity_distinct_previous_shas_may_keep_distinct_baselines() -> None:
    node01 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_01)
    node02 = _evidence(wheelhouse=_WHEELHOUSE, baseline=_BASELINE_02)
    result = _run_stage_parity(node01, node02, _PREVIOUS, _OTHER_PREVIOUS, "")
    assert result.returncode == 0, result.stderr
