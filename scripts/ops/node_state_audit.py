#!/usr/bin/env python3
"""Read-only inventory of node-local state. Prints JSON and never writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Category -> inventory rows in the P03 state list. Unknown files use "other".
CATEGORY_ROWS = {
    "cm": "1-4",
    "product_media": "5",
    "owner_copilot": "6,13,14",
    "live_chat": "9-11",
    "static_audio": "7",
    "smart_messaging": "31",
    "qa": "31",
    "content": "31",
    "settings": "32",
    "auth": "26",
    "billing": "27",
    "meta": "29",
    "logs": "34",
    "release": "36",
    "scratch": "37",
    "other": "31,37",
}


def categorize(relative: str) -> str:
    path = relative.replace("\\", "/")
    if path.startswith("tenants/") and "/cm/" in f"/{path}/":
        return "cm"
    if path.startswith("tenants/") and "/products/" in f"/{path}/":
        return "product_media"
    if "owner_" in path or path.startswith("owner"):
        return "owner_copilot"
    if path.startswith("static/audio") or "/static/audio/" in f"/{path}":
        return "static_audio"
    if "live_chat" in path or path.startswith("inbox"):
        return "live_chat"
    if path.startswith("smart_messaging"):
        return "smart_messaging"
    if path.startswith("qa"):
        return "qa"
    if path.startswith("content"):
        return "content"
    if path.startswith("settings"):
        return "settings"
    if path.startswith("auth"):
        return "auth"
    if path.startswith("billing") or "ledger" in path:
        return "billing"
    if path.startswith("meta") or "/meta/" in f"/{path}":
        return "meta"
    if path.endswith(".log") or path.startswith("logs"):
        return "logs"
    if path.startswith("tmp") or path.startswith("scratch"):
        return "scratch"
    if path.startswith("static"):
        return "release"
    return "other"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not root.exists():
        return rows
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if not Path(dirpath, name).is_symlink()]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = str(path.relative_to(root))
            stat = path.stat()
            rows.append(
                {
                    "path": relative,
                    "size": stat.st_size,
                    "sha256": _sha256(path),
                    "mtime": int(stat.st_mtime),
                    "category": categorize(relative),
                }
            )
    return rows


def summary(rows: list[dict[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {key: 0 for key in CATEGORY_ROWS}
    bytes_by: dict[str, int] = {key: 0 for key in CATEGORY_ROWS}
    for row in rows:
        category = str(row["category"])
        counts[category] = counts.get(category, 0) + 1
        bytes_by[category] = bytes_by.get(category, 0) + int(row["size"])
    unmapped = sorted(key for key in counts if key not in CATEGORY_ROWS)
    return {"files": len(rows), "counts": counts, "bytes": bytes_by, "unmapped": unmapped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only node-local state audit")
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args(argv)
    roots = args.roots or [Path(os.getenv("LINASBOT_DATA_ROOT") or "/opt/linasbot_data")]
    combined: list[dict[str, object]] = []
    for root in roots:
        for row in scan(root):
            row["root"] = str(root)
            combined.append(row)
    report = summary(combined)
    if not args.summary_only:
        for row in combined:
            print(json.dumps(row, separators=(",", ":")))
    print(json.dumps({"summary": report}, separators=(",", ":")))
    return 1 if report["unmapped"] else 0


if __name__ == "__main__":
    sys.exit(main())
