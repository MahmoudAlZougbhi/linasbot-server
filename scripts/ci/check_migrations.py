#!/usr/bin/env python3
"""Reject contract changes in a migration upgrade. Downgrades may drop tables."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "alembic" / "versions"
# Revisions already on main before this check. New files must stay expand-only.
BASELINE = ROOT / "scripts" / "ci" / "migration_baseline.txt"
FORBIDDEN = {"drop_column", "drop_table", "rename_table", "alter_column"}


def _upgrade_function(tree: ast.AST) -> ast.FunctionDef | None:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    return None


def violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    upgrade = _upgrade_function(tree)
    if upgrade is None:
        return []
    found: list[str] = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else ""
        if name in FORBIDDEN:
            found.append(f"{path.name}:{node.lineno}:{name}")
        if name == "create_index":
            keywords = {kw.arg: kw.value for kw in node.keywords}
            concurrent = keywords.get("postgresql_concurrently")
            if not (isinstance(concurrent, ast.Constant) and concurrent.value is True):
                found.append(f"{path.name}:{node.lineno}:create_index without CONCURRENTLY")
    return found


def baseline_names() -> set[str]:
    if not BASELINE.is_file():
        return set()
    return {line.strip() for line in BASELINE.read_text(encoding="utf-8").splitlines() if line.strip()}


def main() -> int:
    grandfathered = baseline_names()
    problems: list[str] = []
    for path in sorted(VERSIONS.glob("*.py")):
        if path.name in grandfathered:
            continue
        problems.extend(violations(path))
    if problems:
        print("\n".join(problems))
        return 1
    print("migration safety ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
