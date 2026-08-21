"""Pre-drain staging defers the runtime-tree proof; post-drain proof fails closed."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.ha.release_artifact_contract import python_runtime_tree_sha256

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
PIN = "e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _lock_hashable_modes(root: Path) -> None:
    os.chmod(root, 0o755)
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir():
            os.chmod(path, 0o755)
        elif path.is_file():
            executable = bool(path.stat().st_mode & 0o111)
            os.chmod(path, 0o755 if executable else 0o644)


def _runtime_tree(tmp_path: Path) -> Path:
    runtime = tmp_path / "cpython-3.13.15"
    stdlib = runtime / "lib" / "python3.13"
    stdlib.mkdir(parents=True)
    (stdlib / "os.py").write_text("pass\n", encoding="utf-8")
    _lock_hashable_modes(runtime)
    return runtime


def test_stage_manifest_defers_tree_proof_until_restore() -> None:
    source = _helper()
    manifest = source[source.index("stage_manifest_tool() {") : source.index("publish_stage_manifest() {")]
    assert (
        'assert_python_runtime_contract "$(configured_node_id)" deferred-until-restore' in manifest
    )
    assert 'assert_python_runtime_contract "$(configured_node_id)")' not in manifest


def test_steady_deploy_requires_tree_proof_after_drain_before_activation() -> None:
    source = _helper()
    apply = source[source.index("apply_cpython_runtime_immutability() {") : source.index("require_root() {")]
    assert "deferred-until-restore" not in apply
    assert "node_assert_runtime_drained" in apply
    assert apply.index("node_assert_runtime_drained") < apply.index(
        "rematerialize_python_runtime_from_durable_bundle"
    )
    assert apply.index("rematerialize_python_runtime_from_durable_bundle") < apply.index(
        'assert_python_runtime_contract "$(configured_node_id)"'
    )
    assert "PYTHON_RUNTIME_TREE_SHA256=" + PIN in source
    assert source.count("canonical Python runtime tree differs from the reviewed pristine artifact") >= 1

    start = source.index('log "withdrawing node01 before any target activation or database migration"')
    activate = source.index('log "activating exact target on drained peer"')
    window = source[start:activate]
    assert "apply_cpython_runtime_immutability" in window
    assert window.index("sleep") < window.index("apply_cpython_runtime_immutability")
    assert "peer-activate-started" not in window


def test_live_drift_changes_runtime_tree_and_required_proof_stays_fail_closed(tmp_path: Path) -> None:
    runtime = _runtime_tree(tmp_path)
    before = python_runtime_tree_sha256(runtime)
    cache = runtime / "lib" / "python3.13" / "__pycache__"
    cache.mkdir()
    (cache / "os.cpython-313.pyc").write_bytes(b"live-drift")
    _lock_hashable_modes(runtime)
    drifted = python_runtime_tree_sha256(runtime)
    assert drifted != before
    assert drifted != PIN

    source = _helper()
    tree = source[
        source.index("assert_python_runtime_tree_pristine_os() {") : source.index(
            "restore_generated_python_bytecode() {"
        )
    ]
    assert "__pycache__" not in tree
    assert "*.pyc" not in tree
    apply = source[source.index("apply_cpython_runtime_immutability() {") : source.index("require_root() {")]
    assert "deferred-until-restore" not in apply
    assert 'test "$digest" = "$PYTHON_RUNTIME_TREE_SHA256"' in tree
