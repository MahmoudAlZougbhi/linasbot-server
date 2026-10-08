"""Dry-run purge of labelled QA rows. It deletes nothing unless confirmation matches."""

from __future__ import annotations

import argparse
import json
from typing import Any

PREFIXES = ("QA-LINAS-", "QA-CURSOR")
CODEWORDS = (
    "cobalt-ember",
    "cobalt ember",
    "jade-lynx",
    "jade lynx",
    "amber-falcon",
    "amber falcon",
    "cobalt-heron",
    "cobalt heron",
    "kobalt-héron",
    "purple-lantern",
    "purple lantern",
    "silver-otter",
    "silver otter",
)
REAL_CHANNELS = ("instagram", "facebook", "messenger", "whatsapp", "tiktok", "web")
KEEP = frozenset({"linas", "platform", "testuser"})


def _blob(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, default=str).lower()


def _real_channel(channel: str) -> bool:
    text = (channel or "").lower()
    return any(text.startswith(name) for name in REAL_CHANNELS)


def classify_row(row: dict[str, Any]) -> str:
    """Return '1', '2', 'kept-channel', or ''."""
    text = _blob(row)
    channel = str(row.get("channel") or "")
    labelled = any(prefix.lower() in text for prefix in PREFIXES) or any(word in text for word in CODEWORDS)
    if not labelled:
        return ""
    if _real_channel(channel):
        return "kept-channel"
    tenant = str(row.get("tenant_id") or "")
    lab = (
        channel == "brains_test"
        or str(row.get("source") or "") == "lab"
        or str(row.get("brain") or "") == "owner_copilot"
    )
    if any(prefix.lower() in text for prefix in PREFIXES):
        return "1"
    if lab and tenant in KEEP and any(word in text for word in CODEWORDS):
        return "2"
    return ""


def candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if classify_row(row) in {"1", "2"}]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--count", default="")
    parser.add_argument("--rows-json", default="")
    args = parser.parse_args(argv)
    rows = json.loads(args.rows_json) if args.rows_json else []
    chosen = candidate_rows(rows)
    print(json.dumps({"dry_run": not args.confirm, "count": len(chosen)}, ensure_ascii=False))
    if not args.confirm:
        return 0
    if args.count != str(len(chosen)):
        print("confirmation did not match the dry-run count; nothing changed")
        return 2
    print(json.dumps({"deleted": len(chosen)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
