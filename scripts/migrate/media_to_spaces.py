#!/usr/bin/env python3
"""Plan a media move. Default is dry-run. Same id with a different hash is flagged."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def plan(roots: list[Path]) -> dict[str, object]:
    by_id: dict[str, list[dict[str, str]]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".bin", ".png", ".jpg", ".webp", ".mp3"}:
                continue
            media_id = path.stem
            by_id.setdefault(media_id, []).append({"path": str(path), "sha256": _sha256(path)})
    flagged = []
    for media_id, copies in by_id.items():
        hashes = {item["sha256"] for item in copies}
        if len(hashes) > 1:
            flagged.append({"media_id": media_id, "hashes": sorted(hashes)})
    return {"files": sum(len(items) for items in by_id.values()), "flagged": flagged}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run media migration")
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    report = plan(args.roots)
    print(json.dumps({"dry_run": not args.apply, **report}, indent=2))
    if args.apply:
        print("apply needs LINAS_SPACES_* and is not run from this prompt", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
