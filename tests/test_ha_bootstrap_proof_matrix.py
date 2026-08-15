"""Legacy v2 vs v3 bootstrap commit proof compatibility matrix."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_ha_deploy_transaction import _embedded_python
from tests.test_meta_ha_bootstrap_transaction import _load

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts" / "ha" / "bootstrap_meta_ha_contract.py"
bootstrap = _load(BOOTSTRAP_PATH, "bootstrap_proof_matrix_test")


def _deploy_verify_code() -> str:
    code = _embedded_python("read_bootstrap_commit_proof")
    code = code.replace("info.st_uid != 0", "info.st_uid != os.getuid()")
    return code.replace("info.st_gid != 0", "info.st_gid != os.getgid()")


def _digest_keys() -> set[str]:
    return {
        "runtime_plan_sha256",
        "runtime_shared_sha256",
        "runtime_launcher_receipt_sha256",
        "qg_manifest_sha256",
        "control_plane_archive_sha256",
        "control_plane_tree_sha256",
        "wheelhouse_archive_sha256",
        "wheelhouse_tree_sha256",
        "requirements_lock_sha256",
        "runtime_tree_sha256",
        "target_unit_contract_sha256",
        "legacy_bytecode_manifest_sha256",
    }


def _v3_payload(plan_sha: str, runtime_cluster_sha: str) -> dict[str, object]:
    return {
        "schema": 3,
        "format": "linas-meta-ha-bootstrap-node-v3",
        "tx_id": "a" * 32,
        "plan_sha256": plan_sha,
        "node_id": "node01",
        "status": "committed",
        "runtime_transaction_id": "pyr_" + "d" * 32,
        "runtime_cluster_receipt_sha256": runtime_cluster_sha,
        "wheelhouse_file_count": 78,
        "wheelhouse_total_size": 1024,
        "repo_bytecode_absent": True,
        "nested_runtime_present": False,
        "nested_runtime_evidence_sha256": "f" * 64,
        "nested_runtime_quarantined": False,
        "nested_runtime_authority_sha256": "a" * 64,
        **{key: "e" * 64 for key in _digest_keys()},
    }


def _run_deploy_consumer(
    proof_path: Path,
    candidate: dict[str, object],
    plan_sha: str,
    runtime_cluster_sha: str,
) -> subprocess.CompletedProcess[str]:
    proof_path.write_bytes(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    proof_path.chmod(0o600)
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-c",
            _deploy_verify_code(),
            str(proof_path),
            "node01",
            plan_sha,
            runtime_cluster_sha,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("label", "mutator", "pattern"),
    [
        (
            "legacy-v2-schema",
            lambda payload: {**payload, "schema": 2, "format": "linas-meta-ha-bootstrap-node-v2"},
            "not committed",
        ),
        (
            "legacy-v2-format-only",
            lambda payload: {**payload, "format": "linas-meta-ha-bootstrap-node-v2"},
            "not committed",
        ),
        (
            "missing-nested-runtime-fields",
            lambda payload: {key: value for key, value in payload.items() if not key.startswith("nested_runtime")},
            "schema is invalid",
        ),
        (
            "present-without-quarantine",
            lambda payload: {**payload, "nested_runtime_present": True, "nested_runtime_quarantined": False},
            "truth table",
        ),
        (
            "quarantine-without-present",
            lambda payload: {**payload, "nested_runtime_present": False, "nested_runtime_quarantined": True},
            "truth table",
        ),
        (
            "non-boolean-present-flag",
            lambda payload: {**payload, "nested_runtime_present": 1},
            "flag is invalid",
        ),
    ],
)
def test_deploy_consumer_rejects_legacy_and_inconsistent_proof_shapes(
    label: str,
    mutator: object,
    pattern: str,
    tmp_path: Path,
) -> None:
    plan_sha = "b" * 64
    runtime_cluster_sha = "c" * 64
    proof_path = tmp_path / f"{label}.json"
    candidate = mutator(_v3_payload(plan_sha, runtime_cluster_sha))  # type: ignore[operator]
    result = _run_deploy_consumer(proof_path, candidate, plan_sha, runtime_cluster_sha)
    assert result.returncode != 0
    assert pattern in result.stderr


def test_deploy_consumer_accepts_exact_v3_proof(tmp_path: Path) -> None:
    plan_sha = "b" * 64
    runtime_cluster_sha = "c" * 64
    proof_path = tmp_path / "v3-valid.json"
    result = _run_deploy_consumer(proof_path, _v3_payload(plan_sha, runtime_cluster_sha), plan_sha, runtime_cluster_sha)
    assert result.returncode == 0, result.stderr


def test_bootstrap_producer_emits_only_v3_with_quarantined_equals_present(
    tmp_path: Path,
) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    absent_fields = bootstrap._nested_commit_proof_fields(
        backup,
        {"schema": 1, "present": False},
        tx_id="mb_" + "l" * 28,
    )
    assert absent_fields["nested_runtime_present"] is False
    assert absent_fields["nested_runtime_quarantined"] is False

    probe = {
        "runtime_authority": {
            "shared": {
                "transaction_id": "pyr_" + "m" * 32,
                "plan_sha256": "n" * 64,
                "cluster_receipt_sha256": "o" * 64,
                "launcher_receipt_sha256": "p" * 64,
                "manifest_sha256": "q" * 64,
                "control_plane_archive_sha256": "r" * 64,
                "control_plane_tree_sha256": "s" * 64,
                "wheelhouse_archive_sha256": "t" * 64,
                "wheelhouse_tree_sha256": "u" * 64,
                "wheelhouse_file_count": 78,
                "wheelhouse_total_size": 1024,
                "requirements_lock_sha256": "v" * 64,
                "runtime_tree_sha256": "w" * 64,
            },
            "shared_sha256": "x" * 64,
        },
        "target_units": [],
        "repo_bytecode": [],
        "nested_runtime": {"schema": 1, "present": False},
        "git_metadata": {"sha256": "y" * 64, "entry_count": 0},
    }
    payload = bootstrap._bootstrap_commit_proof_payload(
        probe,
        backup=backup,
        tx_id="mb_" + "l" * 28,
        plan_sha256="z" * 64,
        node_id="node01",
    )
    assert payload["schema"] == 3
    assert payload["format"] == "linas-meta-ha-bootstrap-node-v3"
    assert payload["nested_runtime_present"] == payload["nested_runtime_quarantined"]
