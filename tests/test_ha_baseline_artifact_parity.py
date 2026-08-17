"""Steady HA baseline artifacts must name drift and require an explicit replace confirm."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


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
