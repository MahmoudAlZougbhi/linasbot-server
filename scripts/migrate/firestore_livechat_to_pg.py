#!/usr/bin/env python3
"""Idempotent live-chat import from a JSON export. Dry-run unless --apply."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def checksum(rows: list[dict[str, Any]]) -> str:
    body = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def load_export(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("messages") or []
    return [row for row in value if isinstance(row, dict)]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_tenant: dict[str, int] = {}
    for row in rows:
        tenant = str(row.get("tenant_id") or "")
        by_tenant[tenant] = by_tenant.get(tenant, 0) + 1
    return {"messages": len(rows), "by_tenant": by_tenant, "checksum": checksum(rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a live-chat JSON export")
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    report = summarize(load_export(args.export))
    print(json.dumps({"dry_run": not args.apply, **report}, indent=2))
    if args.apply:
        print("apply needs a staging database and is not run here", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
