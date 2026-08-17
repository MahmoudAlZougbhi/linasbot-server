"""The OS runtime-tree verifier must import hashlib before hashing."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _os_tree_verifier_python() -> str:
    source = HELPER.read_text(encoding="utf-8")
    start = source.index("assert_python_runtime_tree_pristine_os() {")
    marker = "<<'PY'\n"
    python_start = source.index(marker, start) + len(marker)
    python_end = source.index("\nPY\n", python_start)
    return source[python_start:python_end]


def test_os_runtime_tree_verifier_imports_hashlib() -> None:
    body = _os_tree_verifier_python()
    tree = ast.parse(body)
    imported = {alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names}
    assert "hashlib" in imported
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "hashlib" in names
    ast.parse(body)
