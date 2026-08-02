#!/usr/bin/env python3
"""Read-only inventory/snapshot helper for CM migration (fixture or local data root)."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def inventory(root: Path) -> dict:
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files.append(
                {
                    "rel": str(p.relative_to(root)),
                    "size": p.stat().st_size,
                    "sha256": _hash_file(p),
                }
            )
    return {
        "root": str(root.resolve()),
        "created_at": datetime.now(UTC).isoformat(),
        "file_count": len(files),
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Directory to inventory (fixture/local copy)")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = inventory(root)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote inventory file_count={data['file_count']} -> {out}")


if __name__ == "__main__":
    main()
