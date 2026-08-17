"""Commit-proof may finish a bound COMMIT journal after a successor runtime."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts" / "ha" / "bootstrap_meta_ha_contract.py"


def _load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("bootstrap_meta_ha_contract", BOOTSTRAP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load()


def _runtime(tx_suffix: str, receipt_char: str, qg_char: str) -> dict[str, object]:
    return {
        "shared": {
            "transaction_id": f"pyr_{tx_suffix * 32}",
            "cluster_receipt_sha256": receipt_char * 64,
            "qg_target_sha": qg_char * 40,
        }
    }


def test_successor_committed_runtime_requires_distinct_committed_receipts() -> None:
    planned = _runtime("a", "b", "c")
    live = _runtime("d", "e", "f")
    assert bootstrap._successor_committed_runtime(planned, live) is True
    assert bootstrap._successor_committed_runtime(planned, planned) is False
    same_tx = _runtime("a", "e", "f")
    assert bootstrap._successor_committed_runtime(planned, same_tx) is False
    same_receipt = _runtime("d", "b", "f")
    assert bootstrap._successor_committed_runtime(planned, same_receipt) is False
    assert bootstrap._successor_committed_runtime({"shared": "bad"}, live) is False


def test_commit_proof_source_allows_successor_runtime_without_dropping_drift_gate() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    proof = source[source.index("def _node_commit_proof") : source.index("def _node_finalize")]
    assert "_successor_committed_runtime(" in proof
    assert "Python runtime authority changed before bootstrap commit proof" in proof
    admit = source[source.index("def _node_admit(") : source.index("def _node_redrain")]
    assert "_normalize_git_metadata(backup, probe[\"git_metadata\"])" in admit
    recovery = source[source.index("def _orchestrate_decided_recovery") : source.index("def _decided_recovery_status")]
    assert "durable coordinator journal retained: {exc}" in recovery
