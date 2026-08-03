#!/usr/bin/env bash
# Read-only provenance ledger for price sources on production.
# Never prints file bodies, prices, phones, or PII — only paths, sizes, checksums, counts, key shapes.
set -euo pipefail

APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"

echo "[price-ledger] deployed_sha=$(git rev-parse HEAD)"
echo "[price-ledger] data_root=$LINASBOT_DATA_ROOT tenant=$TENANT_ID"

/opt/linasbot/venv/bin/python - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get("LINASBOT_DATA_ROOT", "/opt/linasbot_data"))
APP_DATA = Path("/opt/linasbot/data")
TENANT = os.environ.get("LINASBOT_TENANT_ID", "linas")
BACKUP_ROOT = Path("/opt/linasbot_backups/cm")

AMOUNT_KEYS = ("amount", "price", "unit_price", "base_price", "cost", "final_price", "discounted_price")
NAME_KEYS = ("name", "title", "label", "body_part", "service", "item", "area", "body_area", "part")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def extract_rows(obj: Any) -> tuple[int, set[str]]:
    rows = 0
    key_hits: set[str] = set()

    def walk(node: Any) -> None:
        nonlocal rows
        if isinstance(node, dict):
            amount = None
            amount_key = None
            for key in AMOUNT_KEYS:
                if key in node:
                    amount = as_float(node.get(key))
                    if amount is not None:
                        amount_key = key
                        break
            name = None
            name_key = None
            for key in NAME_KEYS:
                if key in node and str(node.get(key) or "").strip():
                    name = str(node.get(key)).strip()
                    name_key = key
                    break
            if amount is not None and name:
                rows += 1
                if amount_key:
                    key_hits.add(f"amount:{amount_key}")
                if name_key:
                    key_hits.add(f"name:{name_key}")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(obj)
    return rows, key_hits


def top_keys(obj: Any) -> list[str]:
    if isinstance(obj, dict):
        return sorted(str(k) for k in list(obj.keys())[:40])
    if isinstance(obj, list):
        return [f"list[{len(obj)}]"]
    return [type(obj).__name__]


def scan_file(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
        "sha256_16": sha256_file(path) if path.exists() and path.is_file() else None,
    }
    if not path.is_file():
        return info
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            rows, hits = extract_rows(obj)
            info.update(
                {
                    "kind": "json",
                    "top_keys": top_keys(obj),
                    "extractable_rows": rows,
                    "key_hits": sorted(hits),
                    "parse_ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            info.update({"kind": "json", "parse_ok": False, "error_type": type(exc).__name__})
    elif suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        # Count lines that look like "Name .... 12" or "Name: 12 USD" without printing them.
        line_hits = 0
        for line in text.splitlines():
            if re.search(r"[A-Za-z\u0600-\u06FF].{0,80}\d+(?:\.\d+)?", line) and re.search(
                r"\b\d+(?:\.\d+)?\b", line
            ):
                # Skip pure rule lines without a plausible name+amount pair structure
                if any(tok in line.lower() for tok in ("do not", "selector", "pricing rules", "----")):
                    continue
                line_hits += 1
        info.update(
            {
                "kind": "text",
                "line_count": len(text.splitlines()),
                "candidate_priced_lines": line_hits,
                "nonempty": bool(text.strip()),
            }
        )
    else:
        info["kind"] = suffix or "unknown"
    return info


roots = [
    DATA_ROOT / "content" / "price_files",
    DATA_ROOT / "price_files",
    APP_DATA / "price_files",
    APP_DATA / "content" / "price_files",
    DATA_ROOT / "content",
    DATA_ROOT,
    APP_DATA,
    APP_DATA / "content",
]

files: list[Path] = []
for root in roots:
    if root.is_dir() and root.name == "price_files":
        files.extend(sorted(root.glob("*.json")))
        files.extend(sorted(root.glob("*.txt")))
    for name in ("price_list.txt", "prices.json"):
        candidate = root / name
        if candidate.is_file():
            files.append(candidate)

# CM drafts / published versions (metadata counts only)
cm_root = DATA_ROOT / "tenants" / TENANT / "cm"
cm_targets = [
    cm_root / "draft" / "prices.json",
    cm_root / "published" / "pointer.json",
]
if (cm_root / "versions").is_dir():
    for version_dir in sorted((cm_root / "versions").iterdir())[-5:]:
        prices = version_dir / "content" / "prices.json"
        if prices.is_file():
            cm_targets.append(prices)

# Recent backups (names only + whether price_files exist)
backup_hits: list[dict[str, Any]] = []
if BACKUP_ROOT.is_dir():
    for snap in sorted(BACKUP_ROOT.glob("cm_snapshot_*"))[-5:]:
        pf = list(snap.rglob("price_files/*.json"))
        pl = list(snap.rglob("price_list.txt"))
        draft = list(snap.rglob("tenants/*/cm/draft/prices.json"))
        backup_hits.append(
            {
                "snapshot": snap.name,
                "price_json_files": len(pf),
                "price_list_txt": len(pl),
                "draft_prices_json": len(draft),
            }
        )

# Dedupe files
seen: set[str] = set()
unique_files: list[Path] = []
for path in files + cm_targets:
    key = str(path.resolve()) if path.exists() else str(path)
    if key in seen:
        continue
    seen.add(key)
    unique_files.append(path)

ledger = {
    "files": [scan_file(path) for path in unique_files],
    "backups": backup_hits,
    "totals": {
        "files_scanned": len(unique_files),
        "json_extractable_rows": 0,
        "text_candidate_lines": 0,
    },
}
for entry in ledger["files"]:
    ledger["totals"]["json_extractable_rows"] += int(entry.get("extractable_rows") or 0)
    ledger["totals"]["text_candidate_lines"] += int(entry.get("candidate_priced_lines") or 0)

# Pointer summary without secrets
pointer_path = cm_root / "published" / "pointer.json"
if pointer_path.is_file():
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        ledger["published_pointer"] = {
            "content_version_id": pointer.get("content_version_id"),
            "index_version_id": pointer.get("index_version_id"),
        }
    except Exception as exc:  # noqa: BLE001
        ledger["published_pointer"] = {"error_type": type(exc).__name__}

print(json.dumps(ledger, indent=2, ensure_ascii=False))
print("[price-ledger] COMPLETE_OK")
PY
