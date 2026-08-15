"""Alembic metadata has one head after the no-op SFU/Meta credential merge."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"
MERGE_ID = "20260815_merge_sfu_meta_cred"
PARENTS = frozenset(
    {
        "20260813_sfu_channels_enabled",
        "20260814_meta_credential_archived_at",
    }
)
MERGE_PATH = VERSIONS / "20260815_merge_sfu_meta_cred.py"
ALEMBIC_VERSION_NUM_MAX = 32
LIVE_LONG_REVISION_ID = "20260814_meta_credential_archived_at"
WIDEN_ID = "20260814_widen_ver_num"
WIDEN_PATH = VERSIONS / "20260814_widen_ver_num.py"


def _constant_strings(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Constant) and node.value is None:
        return ()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, (ast.Tuple, ast.List)):
        values: list[str] = []
        for element in node.elts:
            values.extend(_constant_strings(element))
        return tuple(values)
    raise AssertionError(f"unsupported down_revision node: {type(node).__name__}")


def _revisions() -> dict[str, tuple[str, ...]]:
    mapping: dict[str, tuple[str, ...]] = {}
    for path in VERSIONS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = ""
        parents: tuple[str, ...] = ()
        for node in tree.body:
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name) or node.value is None:
                continue
            if node.target.id == "revision":
                strings = _constant_strings(node.value)
                assert len(strings) == 1, path.name
                revision = strings[0]
            elif node.target.id == "down_revision":
                parents = _constant_strings(node.value)
        assert revision, path.name
        mapping[revision] = parents
    return mapping


def test_alembic_has_exactly_one_head() -> None:
    revisions = _revisions()
    referenced = {parent for parents in revisions.values() for parent in parents}
    heads = sorted(revision for revision in revisions if revision not in referenced)
    assert heads == [MERGE_ID]


def test_every_path_to_the_long_revision_goes_through_the_short_widen() -> None:
    revisions = _revisions()
    assert revisions[WIDEN_ID] == ("20260812_meta_app_registry",)
    assert len(WIDEN_ID) <= ALEMBIC_VERSION_NUM_MAX
    assert revisions[LIVE_LONG_REVISION_ID] == (WIDEN_ID,)
    assert len(LIVE_LONG_REVISION_ID) == 36
    long_ids = sorted(revision for revision in revisions if len(revision) > ALEMBIC_VERSION_NUM_MAX)
    assert long_ids == [LIVE_LONG_REVISION_ID]
    assert revisions["20260812_ha_billing_auth"] == ("20260812_meta_app_registry",)


def test_widen_revision_alters_version_num_to_varchar_64() -> None:
    source = WIDEN_PATH.read_text(encoding="utf-8")
    assert "VARCHAR(64)" in source
    assert "ALTER TABLE alembic_version" in source
    assert "cannot shrink alembic_version.version_num while a long revision is stamped" in source


def test_merge_revision_joins_both_previous_heads() -> None:
    revisions = _revisions()
    assert frozenset(revisions[MERGE_ID]) == PARENTS
    for parent_id in PARENTS:
        children = [child for child, parents in revisions.items() if parent_id in parents]
        assert children == [MERGE_ID]


def test_both_parent_paths_are_ancestors_of_the_merge_head() -> None:
    revisions = _revisions()
    ancestors: set[str] = set()
    stack = [MERGE_ID]
    while stack:
        current = stack.pop()
        if current in ancestors:
            continue
        ancestors.add(current)
        stack.extend(revisions[current])
    assert PARENTS <= ancestors
    assert "20260811_whatsapp_cloud" in ancestors
    assert "20260812_meta_app_registry" in ancestors


def test_merge_upgrade_and_downgrade_are_schema_noops() -> None:
    source = MERGE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    bodies: dict[str, list[ast.stmt]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"upgrade", "downgrade"}:
            statements = list(node.body)
            if statements and isinstance(statements[0], ast.Expr) and isinstance(statements[0].value, ast.Constant):
                statements = statements[1:]
            bodies[node.name] = statements
    assert set(bodies) == {"upgrade", "downgrade"}
    for statements in bodies.values():
        assert len(statements) == 1
        assert isinstance(statements[0], ast.Pass)
