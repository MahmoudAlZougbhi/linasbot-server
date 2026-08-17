"""Deploy preflight uses QG source authority and successor runtime overlap."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tests.test_ha_deploy_transaction import _embedded_python, _helper

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _assert_target_object() -> str:
    source = _helper()
    start = source.index("assert_target_object() {")
    end = source.index("\ncheck_canonical_env_security() {", start)
    return source[start:end]


def _proof_code() -> str:
    code = _embedded_python("read_bootstrap_commit_proof")
    code = code.replace("info.st_uid != 0", "info.st_uid != os.getuid()")
    code = code.replace("info.st_gid != 0", "info.st_gid != os.getgid()")
    code = code.replace("live_info.st_uid != 0", "live_info.st_uid != os.getuid()")
    return code.replace("live_info.st_gid != 0", "live_info.st_gid != os.getgid()")


def _v3_payload(plan_sha: str, runtime_cluster_sha: str) -> dict[str, object]:
    digest_keys = {
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
        **{key: "e" * 64 for key in digest_keys},
    }


def _live_cluster(*, tx_suffix: str) -> tuple[bytes, str]:
    payload = {
        "decision": "commit",
        "format": "linas-python-runtime-cluster-v2",
        "qg_target_sha": "1" * 40,
        "status": "committed",
        "transaction_id": "pyr_" + tx_suffix * 32,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    return raw, hashlib.sha256(raw).hexdigest()


def test_assert_target_object_uses_imported_quality_gates_ref() -> None:
    body = _assert_target_object()
    assert 'imported_ref="refs/linasbot-release-artifacts/$target_sha"' in body
    assert "imported Quality Gates source authority" in body
    assert "fetch --no-tags origin main" not in body
    assert "merge-base --is-ancestor" not in body
    assert "origin/main" not in body
    helper = HELPER.read_text(encoding="utf-8")
    assert helper.count("fetch --no-tags origin main") == 0


def test_read_bootstrap_commit_proof_passes_live_cluster_receipt() -> None:
    source = _helper()
    start = source.index("read_bootstrap_commit_proof() {")
    end = source.index("\nvalidate_tx_dir() {", start)
    body = source[start:end]
    assert '"$PYTHON_RUNTIME_CLUSTER_RECEIPT"' in body
    assert "bootstrap proof runtime is not a successor of the live committed certificate" in body


def test_bootstrap_proof_accepts_successor_live_runtime(tmp_path: Path) -> None:
    plan_sha = "b" * 64
    planned_runtime = "c" * 64
    proof_path = tmp_path / "bootstrap.last-committed.json"
    live_path = tmp_path / "python-runtime-cluster.json"
    live_raw, live_digest = _live_cluster(tx_suffix="e")
    assert live_digest != planned_runtime
    proof_path.write_bytes(
        json.dumps(_v3_payload(plan_sha, planned_runtime), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    proof_path.chmod(0o600)
    live_path.write_bytes(live_raw)
    live_path.chmod(0o600)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-c",
            _proof_code(),
            str(proof_path),
            "node01",
            plan_sha,
            live_digest,
            str(live_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == plan_sha


def test_bootstrap_proof_rejects_same_transaction_live_runtime(tmp_path: Path) -> None:
    plan_sha = "b" * 64
    planned_runtime = "c" * 64
    proof_path = tmp_path / "bootstrap.last-committed.json"
    live_path = tmp_path / "python-runtime-cluster.json"
    live_raw, live_digest = _live_cluster(tx_suffix="d")
    proof_path.write_bytes(
        json.dumps(_v3_payload(plan_sha, planned_runtime), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    proof_path.chmod(0o600)
    live_path.write_bytes(live_raw)
    live_path.chmod(0o600)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-c",
            _proof_code(),
            str(proof_path),
            "node01",
            plan_sha,
            live_digest,
            str(live_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "not a successor" in result.stderr
