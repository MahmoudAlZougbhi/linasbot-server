#!/usr/bin/env bash
# Read-only corpus inventory across production data roots + CM backups (metadata only).
# Never prints secrets, PII, or content bodies.
set -euo pipefail

APP_DIR="/opt/linasbot"
DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
APP_DATA="/opt/linasbot/data"
BACKUP_ROOT="${CM_BACKUP_ROOT:-/opt/linasbot_backups/cm}"
OUT_DIR="${CM_INVENTORY_OUT:-/opt/linasbot_backups/cm/inventory}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"
OUT_JSON="${OUT_DIR}/corpus_ledger_${STAMP}.json"

echo "[cm-inventory] host=$(hostname)"
echo "[cm-inventory] deployed_sha=$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "[cm-inventory] data_root=$DATA_ROOT"
echo "[cm-inventory] app_data=$APP_DATA"
echo "[cm-inventory] backup_root=$BACKUP_ROOT"
echo "[cm-inventory] out=$OUT_JSON"

export CM_DEPLOYED_SHA="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
python3 - <<PY
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

data_root = Path(os.environ.get("LINASBOT_DATA_ROOT", "/opt/linasbot_data"))
app_data = Path("/opt/linasbot/data")
backup_root = Path(os.environ.get("CM_BACKUP_ROOT", "/opt/linasbot_backups/cm"))
out = Path("${OUT_JSON}")

CONTENT_GLOBS = ("*.txt", "*.json", "*.jsonl", "*.md", "*.csv")
INTERESTING_DIRS = (
    "qa", "content", "settings", "knowledge_files", "style_files", "price_files",
)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def classify(path: Path) -> str:
    name = path.name.lower()
    parent = path.parent.name.lower()
    if "qa" in name or name.endswith(".jsonl"):
        return "faq"
    if "price" in name or parent == "price_files":
        return "prices"
    if "style" in name or parent == "style_files":
        return "style"
    if "prompt" in name or "system" in name:
        return "ai_basics"
    if "dynamic" in name:
        return "dynamic_messages"
    if parent == "knowledge_files" or "knowledge" in name:
        return "knowledge"
    if "app_settings" in name:
        return "settings"
    return "other"

def collect(root: Path, label: str, files: list, max_depth: int = 8) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path.name
        depth = len(Path(rel).parts)
        if depth > max_depth:
            continue
        rel_s = str(rel).lower()
        if any(skip in rel_s for skip in ("conversation", "firestore", "auth/sessions", "rate_limits", ".pyc")):
            continue
        if path.suffix.lower().lstrip(".") not in {"txt", "json", "jsonl", "md", "csv"} and path.name not in {
            "published_pointer.json", "manifest.json"
        }:
            # Still include CM draft/version json under tenants/*/cm/
            if "/cm/" not in rel_s:
                continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        files.append({
            "source_label": label,
            "filename": path.name,
            "full_path": str(path),
            "sha256": sha256_file(path),
            "size_bytes": size,
            "format": path.suffix.lstrip(".") or "unknown",
            "category": classify(path),
            "ui_visibility": "owner_cm" if "/cm/" in rel_s else "legacy_source",
        })

files: list = []
collect(data_root, "LINASBOT_DATA_ROOT", files)
collect(app_data, "opt_linasbot_data", files)

# Prefer nonempty app_data knowledge corpus listing
for sub in ("knowledge_files", "content/knowledge_files", "style_files", "content/style_files", "price_files", "content/price_files"):
    collect(app_data / sub if not sub.startswith("content/") else app_data / Path(sub), f"opt_linasbot_data/{sub}", files, max_depth=3)
    collect(data_root / sub if "/" not in sub else data_root / Path(sub), f"data_root/{sub}", files, max_depth=3)

# Backups (metadata only) — list snapshot roots + key manifests
snapshots = []
if backup_root.is_dir():
    for snap in sorted(backup_root.glob("cm_snapshot_*")):
        if not snap.is_dir():
            continue
        manifest = snap / "manifest.json"
        entry = {"path": str(snap), "has_manifest": manifest.is_file()}
        if manifest.is_file():
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
                entry["entry_count"] = len(m.get("entries") or [])
                entry["extra_count"] = len(m.get("extras") or [])
            except json.JSONDecodeError:
                entry["entry_count"] = None
        snapshots.append(entry)
        # Inventory backup content files (no bodies)
        collect(snap, f"backup:{snap.name}", files, max_depth=10)

# Published pointer summary (ids only)
pointer_info = {}
for candidate in (
    data_root / "tenants" / "linas" / "cm" / "published_pointer.json",
    data_root / "tenants" / "linas" / "cm" / "published" / "pointer.json",
):
    if candidate.is_file():
        try:
            pointer_info = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pointer_info = {"path": str(candidate), "parse_error": True}
        break

# Deduplicate by sha256+filename
seen = set()
unique = []
for f in files:
    key = (f["sha256"], f["filename"])
    if key in seen:
        continue
    seen.add(key)
    unique.append(f)

# CM draft article metadata (titles/status/source only — never bodies)
cm_articles = []
draft_root = data_root / "tenants" / "linas" / "cm" / "draft"
for section in ("knowledge", "care", "faq"):
    path = draft_root / f"{section}.json"
    if not path.is_file():
        continue
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        continue
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        continue
    for item in items:
        if not isinstance(item, dict):
            continue
        if section == "faq":
            cm_articles.append({
                "section": section,
                "id": item.get("qa_group_id"),
                "status": item.get("status"),
                "tags": item.get("tags") or [],
                "variant_languages": [
                    str(v.get("language")) for v in (item.get("variants") or []) if isinstance(v, dict)
                ],
            })
        else:
            cm_articles.append({
                "section": section,
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "source_filename": item.get("source_filename"),
                "source_checksum": item.get("source_checksum"),
                "tags": item.get("tags") or [],
            })

restricted_topics = []
restricted_path = draft_root / "restricted.json"
if restricted_path.is_file():
    try:
        restricted_payload = json.loads(restricted_path.read_text(encoding="utf-8"))
        for topic in (restricted_payload.get("topics") or []):
            if isinstance(topic, dict):
                restricted_topics.append({"id": topic.get("id"), "active": topic.get("active")})
    except json.JSONDecodeError:
        pass

ledger = {
    "schema": "cm_corpus_ledger_v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "deployed_sha": os.environ.get("CM_DEPLOYED_SHA", "unknown"),
    "data_root": str(data_root),
    "app_data": str(app_data),
    "file_count_unique": len(unique),
    "file_count_raw": len(files),
    "snapshots": snapshots,
    "published_pointer_keys": sorted(pointer_info.keys()) if isinstance(pointer_info, dict) else [],
    "content_version_id": pointer_info.get("content_version_id") if isinstance(pointer_info, dict) else None,
    "index_version_id": pointer_info.get("index_version_id") if isinstance(pointer_info, dict) else None,
    "cm_draft_articles": cm_articles,
    "restricted_topics": restricted_topics,
    "files": unique,
}
out.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({
    "out": str(out),
    "file_count_unique": len(unique),
    "file_count_raw": len(files),
    "snapshot_count": len(snapshots),
    "content_version_id": ledger.get("content_version_id"),
    "index_version_id": ledger.get("index_version_id"),
    "restricted_topics": restricted_topics,
    "knowledge_titles": [
        {"title": a.get("title"), "status": a.get("status"), "source_filename": a.get("source_filename")}
        for a in cm_articles if a.get("section") == "knowledge"
    ],
    "faq_status_counts": {},
    "sample_filenames": [f["filename"] for f in unique[:60]],
}, indent=2))
# FAQ status summary
faq_counts = {}
for a in cm_articles:
    if a.get("section") != "faq":
        continue
    st = str(a.get("status") or "unknown")
    faq_counts[st] = faq_counts.get(st, 0) + 1
print(json.dumps({"faq_status_counts": faq_counts, "cm_article_count": len(cm_articles)}, indent=2))
print("[cm-inventory] COMPLETE_OK")
PY
