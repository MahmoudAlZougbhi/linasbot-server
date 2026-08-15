"""Nested-runtime authority and bootstrap wiring tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.nested_runtime_quarantine.conftest import (
    BOOTSTRAP_PATH,
    _authority_payload,
    _patch_secure_authority,
    bootstrap,
    evidence,
    quarantine,
)


def test_repo_bytecode_manifest_excludes_nested_runtime_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    nested_cache = repository / quarantine.NESTED_RUNTIME_NAME / "pkg" / "__pycache__"
    nested_cache.mkdir(parents=True)
    (nested_cache / "legacy.cpython-313.pyc").write_bytes(b"nested")
    top_cache = repository / "pkg" / "__pycache__"
    top_cache.mkdir(parents=True)
    (top_cache / "live.cpython-313.pyc").write_bytes(b"live")
    monkeypatch.setattr(bootstrap, "REPO_DIR", repository)
    manifest = bootstrap._repo_bytecode_manifest()
    paths = {entry["path"] for entry in manifest if entry["type"] == "file"}
    assert "pkg/__pycache__/live.cpython-313.pyc" in paths
    assert not any(str(path).startswith(f"{quarantine.NESTED_RUNTIME_NAME}/") for path in paths)


def test_bootstrap_wires_nested_runtime_authority() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    prepare = source[source.index("def _node_prepare") : source.index("def _node_abort_prepare")]
    drain = source[source.index("def _node_drain") : source.index("def _transition_historical_env")]
    combined = source[source.index("def _combined_plan") : source.index("def _confirmation")]
    verify = source[source.index("def _node_verify") : source.index("def _quiesce_and_disable_units")]
    rollback = source[source.index("def _node_rollback") : source.index("def _node_admit_rollback")]
    commit = source[
        source.index("def _nested_commit_proof_fields") : source.index("def _bootstrap_commit_proof_payload")
    ]
    assert "_nested.publish_authority(" in prepare
    assert "_nested.apply_quarantine(" in drain
    assert "portable_content_identity(" in combined
    assert "_nested_evidence" in source
    assert "_nested.assert_quarantined(" in verify
    assert "_nested.restore_quarantine(" in rollback
    assert '"nested_runtime_present"' in commit
    assert '"nested_runtime_evidence_sha256"' in commit
    assert '"nested_runtime_quarantined"' in commit
    assert '"nested_runtime_authority_sha256"' in commit
    assert "nested_runtime = _nested.probe_evidence(REPO_DIR)" in source


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        ("symlink", "invalid"),
        ("mode", "invalid"),
        ("nlink", "invalid"),
        ("extra_key", "invalid"),
        ("mutated_key", "invalid"),
    ],
)
def test_authority_closedness_rejects_unsafe_files(
    mutator: str,
    match: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if mutator in {"extra_key", "mutated_key"}:
        _patch_secure_authority(monkeypatch)
    backup = tmp_path / "backup"
    backup.mkdir()
    path = quarantine.authority_path(backup)
    payload = _authority_payload()
    if mutator == "symlink":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to("elsewhere")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.loads(payload.decode("utf-8"))
        if mutator == "extra_key":
            body["extra"] = True
        elif mutator == "mutated_key":
            body["tx_id"] = "mutated"
            body["evidence_sha256"] = "0" * 64
        path.write_bytes((evidence._canonical(body) + b"\n") if mutator in {"extra_key", "mutated_key"} else payload)
        if mutator == "mode":
            os.chmod(path, 0o644)
        elif mutator == "nlink":
            os.link(path, path.parent / "authority.alias")
    with pytest.raises(RuntimeError, match=match):
        quarantine._read_authority(backup)
