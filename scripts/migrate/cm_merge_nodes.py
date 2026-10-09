#!/usr/bin/env python3
"""Dry-run merge of two nodes' published AI Setup trees. Writes nothing unless --apply."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _pointer(tenant_dir: Path) -> dict[str, Any]:
    for name in ("published/pointer.json", "pointer.json", "cm/published/pointer.json"):
        path = tenant_dir / name
        if path.is_file():
            return _read_json(path)
    return {}


def choose_newer(left: dict[str, Any], right: dict[str, Any]) -> str:
    def key(row: dict[str, Any]) -> tuple[str, int]:
        return (str(row.get("published_at") or ""), int(row.get("revision") or 0))

    if key(right) > key(left):
        return "right"
    return "left"


def plan(left_root: Path, right_root: Path) -> list[dict[str, Any]]:
    tenants: set[str] = set()
    for root in (left_root, right_root):
        base = root / "tenants"
        if not base.is_dir():
            continue
        tenants.update(path.name for path in base.iterdir() if path.is_dir())
    report: list[dict[str, Any]] = []
    for tenant in sorted(tenants):
        left = _pointer(left_root / "tenants" / tenant)
        right = _pointer(right_root / "tenants" / tenant)
        winner = choose_newer(left, right)
        differs = left != right and bool(left or right)
        report.append(
            {
                "tenant": tenant,
                "winner": winner,
                "differs": differs,
                "left_revision": left.get("revision"),
                "right_revision": right.get("revision"),
                "manual_review": differs,
            }
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge published CM from two nodes")
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    rows = plan(args.left, args.right)
    print(json.dumps({"dry_run": not args.apply, "tenants": rows}, indent=2))
    if args.apply:
        print("apply is refused until a staging database URL is provided", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
