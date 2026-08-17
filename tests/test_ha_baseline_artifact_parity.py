"""Steady HA baseline artifacts must name the drifted root and ignore bytecode."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def test_baseline_evidence_skips_bytecode_and_logs_each_root() -> None:
    helper = _helper()
    body = helper[
        helper.index("live_baseline_artifact_evidence() {") : helper.index("capture_baseline_artifact_evidence() {")
    ]
    assert '{"90-meta-ha-maintenance.conf", "__pycache__"}' in body
    assert 'child.suffix in {".pyc", ".pyo"}' in body
    assert "[ha-deploy] baseline-root" in body
    assert "dropin-api" in body
    assert "file=sys.stderr" in body


def test_steady_baseline_mismatch_prints_both_node_evidence() -> None:
    helper = _helper()
    body = helper[
        helper.index("assert_cluster_runtime_env_parity ") : helper.index(
            'die "nodes do not share one approved drain interval"'
        )
    ]
    assert "node01 baseline artifacts:" in body
    assert "node02 baseline artifacts:" in body
    assert "baseline artifact evidence on $expected_node_id" in _helper()
    assert "divergent venv, dashboard, nginx, or systemd bytes" in body
