"""Peer staging completed after pip; node01 failed while serving. Separate those causes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.ha.cpython_runtime_pycache_contract import bytecode_inside
from scripts.ha.release_artifact_contract import python_runtime_tree_sha256

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
PIN = "e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc"
PIP_RUNNER = """import runpy
from importlib.machinery import PathFinder
from os.path import dirname
import sys

PIP_SOURCES_ROOT = dirname(dirname(__file__))


class PipImportRedirectingFinder:
    @classmethod
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "pip":
            return None
        spec = PathFinder.find_spec(fullname, [PIP_SOURCES_ROOT], target)
        assert spec, (PIP_SOURCES_ROOT, fullname)
        return spec


sys.meta_path.insert(0, PipImportRedirectingFinder())
runpy.run_module("pip", run_name="__main__", alter_sys=True)
"""


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


def _copy_runtime(src: Path, dest: Path) -> Path:
    shutil.copytree(src, dest, symlinks=True)
    _lock_hashable_modes(dest)
    return dest


def _hashed_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "cpython-3.13.15"
    pip_root = runtime / "lib" / "python3.13" / "site-packages" / "pip"
    pip_root.mkdir(parents=True)
    (pip_root / "__init__.py").write_text("marker = 1\n", encoding="utf-8")
    (pip_root / "__main__.py").write_text("from pip import marker\nprint(marker)\n", encoding="utf-8")
    (pip_root / "__pip-runner__.py").write_text(PIP_RUNNER, encoding="utf-8")
    _lock_hashable_modes(runtime)
    return runtime


def _pip_reexec(runtime: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    runner = runtime / "lib" / "python3.13" / "site-packages" / "pip" / "__pip-runner__.py"
    merged = {"PATH": os.environ.get("PATH", ""), **env}
    return subprocess.run([sys.executable, str(runner)], env=merged, text=True, capture_output=True)


def _ha_pip_env(cache: Path) -> dict[str, str]:
    return {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(cache),
        "PIP_CONFIG_FILE": "/dev/null",
        "HOME": str(cache / "home"),
    }


def test_helper_keeps_required_proof_and_does_not_rewrite_pip() -> None:
    source = _helper()
    portable = source[source.index("run_portable_pip() {") : source.index("acquire_meta_live_lock() {")]
    stage = source[source.index("backup_live_node() {") : source.index("normalize_prequiesced_activation_prefix() {")]
    manifest = source[source.index("stage_manifest_tool() {") : source.index("publish_stage_manifest() {")]
    apply = source[source.index("apply_cpython_runtime_immutability() {") : source.index("require_root() {")]
    assert '"$SYSTEM_PYTHON" -X "pycache_prefix=$PYTHON_CONTROL_PYCACHE_ROOT" -B -I -m pip' in portable
    assert ' --python "$tx_dir/stage/verify-venv/bin/python" install' in stage
    assert ' --python "$tx_dir/stage/verify-venv/bin/python" check' in stage
    assert 'log "node stage and recoverable backups complete"' in stage
    assert stage.index("run_portable_pip") < stage.index("publish_stage_manifest")
    assert "deferred-until-restore" in manifest
    assert "deferred-until-restore" not in apply
    assert 'assert_python_runtime_contract "$(configured_node_id)"' in apply


def test_ha_pip_reexec_does_not_mutate_hashed_tree_when_child_inherits_dontwritebytecode(
    tmp_path: Path,
) -> None:
    runtime = _hashed_runtime(tmp_path)
    before = python_runtime_tree_sha256(runtime)
    cache = tmp_path / "control-pycache"
    cache.mkdir()
    result = _pip_reexec(runtime, _ha_pip_env(cache))
    assert result.returncode == 0, result.stderr
    assert python_runtime_tree_sha256(runtime) == before
    assert bytecode_inside(runtime) == []


def test_serving_live_drift_mutates_hashed_tree_after_identical_pip_reexec(tmp_path: Path) -> None:
    baseline = _hashed_runtime(tmp_path / "src")
    cache = tmp_path / "control-pycache"
    cache.mkdir()
    peer = _copy_runtime(baseline, tmp_path / "node02")
    node01 = _copy_runtime(baseline, tmp_path / "node01")
    before = python_runtime_tree_sha256(peer)
    assert python_runtime_tree_sha256(node01) == before

    ha_env = _ha_pip_env(cache)
    peer_pip = _pip_reexec(peer, ha_env)
    node01_pip = _pip_reexec(node01, ha_env)
    assert peer_pip.returncode == 0, peer_pip.stderr
    assert node01_pip.returncode == 0, node01_pip.stderr
    assert python_runtime_tree_sha256(peer) == before
    assert python_runtime_tree_sha256(node01) == before

    live = _pip_reexec(node01, {"HOME": str(tmp_path / "live-home")})
    assert live.returncode == 0, live.stderr
    assert python_runtime_tree_sha256(peer) == before
    drifted = python_runtime_tree_sha256(node01)
    assert drifted != before
    assert drifted != PIN
    assert any(path.endswith(".pyc") for path in bytecode_inside(node01))
    assert bytecode_inside(peer) == []


def test_steady_deploy_requires_tree_proof_after_drain_before_activation() -> None:
    source = _helper()
    apply = source[source.index("apply_cpython_runtime_immutability() {") : source.index("require_root() {")]
    tree = source[
        source.index("assert_python_runtime_tree_pristine_os() {") : source.index(
            "restore_generated_python_bytecode() {"
        )
    ]
    assert "deferred-until-restore" not in apply
    assert "node_assert_runtime_drained" in apply
    assert apply.index("rematerialize_python_runtime_from_durable_bundle") < apply.index(
        'assert_python_runtime_contract "$(configured_node_id)"'
    )
    assert "__pycache__" not in tree
    assert "*.pyc" not in tree
    assert 'test "$digest" = "$PYTHON_RUNTIME_TREE_SHA256"' in tree
    assert "PYTHON_RUNTIME_TREE_SHA256=" + PIN in source
    start = source.index('log "withdrawing node01 before any target activation or database migration"')
    activate = source.index('log "activating exact target on drained peer"')
    window = source[start:activate]
    assert window.index("sleep") < window.index("apply_cpython_runtime_immutability")
    assert "peer-activate-started" not in window
