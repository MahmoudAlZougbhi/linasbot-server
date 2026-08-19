"""Interrupted activation may leave non-root live sibling trees."""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"

ALLOWED = re.compile(
    r"(?:live-(?:venv|dashboard-build)|"
    r"failed-(?:venv|dashboard-build|data)-g[0-9]{4}|"
    r"partial-(?:venv|dashboard-build|data)-g[0-9]{4}-[1-9][0-9]*)"
)


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _stage_manifest_python() -> str:
    source = _helper()
    start = source.index("stage_manifest_tool() {")
    end = source.index("publish_stage_manifest() {")
    return source[start:end]


def _tree_digest_python() -> str:
    source = _helper()
    start = source.index("def tree_digest(path: Path) -> str:")
    end = source.index("def sibling_artifacts() -> dict[str, str]:")
    return source[start:end]


def test_recovery_keep_fail_closed_names_and_parent_root_but_not_child_uid() -> None:
    python = _stage_manifest_python()
    assert 'raise SystemExit("stage sibling rollback directory is unsafe")' in python
    assert "sibling_info.st_uid != 0" in python
    assert "sibling_info.st_gid != 0" in python
    assert "stat.S_IMODE(sibling_info.st_mode) != 0o700" in python
    child = python[python.index('if operation in {"verify-recovery", "evidence"}:') : python.index("trees = {")]
    assert "allowed.fullmatch(entry.name)" in child
    assert "stat.S_ISDIR(info.st_mode)" in child
    assert "stat.S_ISLNK(info.st_mode)" in child
    assert "info.st_dev != sibling_info.st_dev" in child
    assert "info.st_uid != 0" not in child
    assert "info.st_gid != 0" not in child
    assert 'raise SystemExit("stage sibling rollback generation is unsafe")' in child
    assert ALLOWED.pattern in child.replace("\n", "") or "live-(?:venv|dashboard-build)" in child


def test_activation_tree_digest_hashes_non_root_live_trees(tmp_path: Path) -> None:
    digest_src = _tree_digest_python()
    assert "root_info.st_uid != 0" not in digest_src
    assert "root_info.st_gid != 0" not in digest_src
    assert 'raise SystemExit("activation sibling artifact is unsafe")' in digest_src
    script = (
        textwrap.dedent(
            """
        import hashlib, os, stat, sys
        from pathlib import Path
        """
        )
        + digest_src
        + textwrap.dedent(
            """
        path = Path(sys.argv[1])
        print(tree_digest(path))
        """
        )
    )
    live = tmp_path / "live-dashboard-build"
    live.mkdir()
    (live / "index.html").write_text("ok\n", encoding="utf-8")
    live.chmod(0o755)
    result = subprocess.run(
        [sys.executable, "-B", "-I", "-S", "-c", script, str(live)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"[0-9a-f]{64}", result.stdout.strip())

    link = tmp_path / "live-venv"
    link.symlink_to(live)
    denied = subprocess.run(
        [sys.executable, "-B", "-I", "-S", "-c", script, str(link)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert denied.returncode != 0
    assert "activation sibling artifact is unsafe" in denied.stderr


def test_allowlist_rejects_unknown_generation_names() -> None:
    assert ALLOWED.fullmatch("live-venv")
    assert ALLOWED.fullmatch("live-dashboard-build")
    assert ALLOWED.fullmatch("failed-data-g0001")
    assert ALLOWED.fullmatch("partial-venv-g0001-1")
    assert ALLOWED.fullmatch("unknown-venv") is None
    assert ALLOWED.fullmatch("live-dashboard-build-extra") is None
    assert ALLOWED.fullmatch("failed-venv-g1") is None
    python = _stage_manifest_python()
    assert "live-(?:venv|dashboard-build)" in python
    assert "failed-(?:venv|dashboard-build|data)-g[0-9]{4}" in python
