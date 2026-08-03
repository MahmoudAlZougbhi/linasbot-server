#!/usr/bin/env bash
# Recoverable timestamped backup of production CM-relevant data. Never prints secrets/PII contents.
set -euo pipefail

APP_DIR="/opt/linasbot"
DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="${CM_BACKUP_ROOT:-/opt/linasbot_backups/cm}"
DEST="${BACKUP_ROOT}/cm_snapshot_${STAMP}"

mkdir -p "$DEST"
echo "[cm-backup] host=$(hostname)"
echo "[cm-backup] deployed_sha=$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "[cm-backup] data_root=$DATA_ROOT"
echo "[cm-backup] dest=$DEST"

python3 - <<PY
import hashlib, json, os, shutil
from pathlib import Path

data_root = Path(os.environ.get("LINASBOT_DATA_ROOT", "/opt/linasbot_data"))
dest = Path("${DEST}")
include = [
    "qa", "content", "settings", "tenants",
]
# Also copy flat legacy project data content if present (non-customer).
extra_files = [
    Path("/opt/linasbot/data/qa_pairs.jsonl"),
    Path("/opt/linasbot/data/price_list.txt"),
    Path("/opt/linasbot/data/knowledge_base.txt"),
    Path("/opt/linasbot/data/style_guide.txt"),
    Path("/opt/linasbot/data/system_prompt_template.txt"),
    Path("/opt/linasbot/data/app_settings.json"),
]

manifest = {"schema": "cm_backup_v1", "data_root": str(data_root), "entries": [], "extras": []}

def add_file(src: Path, rel: str, bucket: list) -> None:
    if not src.is_file():
        return
    out = dest / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    data = src.read_bytes()
    bucket.append({
        "rel": rel,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    })

if data_root.is_dir():
    for name in include:
        src_dir = data_root / name
        if not src_dir.exists():
            continue
        for path in src_dir.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(data_root))
                # Skip conversation/customer history stores if any under tenants.
                if "conversation" in rel.lower() or "firestore" in rel.lower():
                    continue
                add_file(path, f"data_root/{rel}", manifest["entries"])

for path in extra_files:
    add_file(path, f"opt_linasbot_data_flat/{path.name}", manifest["extras"])

# Env key presence only (no values)
env_path = Path("/opt/linasbot/.env")
env_keys = []
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        env_keys.append(s.split("=", 1)[0].strip())
manifest["env_keys_present"] = sorted(set(env_keys))
manifest["cm_flags"] = {
    "CM_RUNTIME_MODE": "present" if "CM_RUNTIME_MODE" in env_keys else "absent",
    "CM_PUBLISH_ENABLED": "present" if "CM_PUBLISH_ENABLED" in env_keys else "absent",
}

(dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\\n", encoding="utf-8")
print(f"[cm-backup] entries={len(manifest['entries'])} extras={len(manifest['extras'])}")
print(f"[cm-backup] manifest={dest / 'MANIFEST.json'}")

# Verify checksums
bad = 0
for entry in manifest["entries"] + manifest["extras"]:
    p = dest / entry["rel"]
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        bad += 1
print(f"[cm-backup] checksum_mismatches={bad}")
if bad:
    raise SystemExit(1)
print("[cm-backup] COMPLETE_OK")
print(f"[cm-backup] recovery=rsync -a {dest}/data_root/ {data_root}/   # after owner approval; never auto-restore in cutover")
PY

# Persist pointer for later phases
echo "$DEST" > /opt/linasbot_backups/cm/LATEST_SNAPSHOT_PATH
echo "[cm-backup] latest_pointer=/opt/linasbot_backups/cm/LATEST_SNAPSHOT_PATH"
