"""Cluster env compare must unlink each evidence file; GNU unlink takes one path."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def test_cluster_env_compare_unlinks_each_evidence_file() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    body = helper[
        helper.index("compare_cluster_runtime_env_evidence() {") : helper.index(
            "assert_cluster_runtime_env_parity() {"
        )
    ]
    assert 'unlink "$node01_path" "$node02_path"' not in body
    assert 'unlink "$node01_path"' in body
    assert 'unlink "$node02_path"' in body
    assert "cluster environment comparison cleanup failed closed" in body
