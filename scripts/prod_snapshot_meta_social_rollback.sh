#!/usr/bin/env bash
# Create a root-owned encrypted snapshot of the active old Meta app configuration.
set -euo pipefail
umask 077

OLD_APP_ID="1784792718776344"
ROLLBACK_DIR="/opt/linasbot/.meta-social-rollback"

if [ -z "${META_ROLLBACK_ENCRYPTION_KEY:-}" ]; then
  echo "[meta-snapshot] rollback encryption key missing" >&2
  exit 1
fi
if [ "${#META_ROLLBACK_ENCRYPTION_KEY}" -lt 32 ]; then
  echo "[meta-snapshot] rollback encryption key too short" >&2
  exit 1
fi

install -d -m 700 "$ROLLBACK_DIR"
snapshot_plain="$(mktemp /tmp/linas-meta-old.XXXXXX.json)"
cleanup() {
  if [ -f "$snapshot_plain" ]; then
    if command -v shred >/dev/null 2>&1; then
      shred -u "$snapshot_plain"
    else
      rm -f "$snapshot_plain"
    fi
  fi
}
trap cleanup EXIT

SNAPSHOT_PLAIN="$snapshot_plain" OLD_APP_ID="$OLD_APP_ID" python3 - <<'PY'
import json
import os
from datetime import UTC, datetime
from pathlib import Path

keys = (
    "META_APP_ID",
    "META_APP_SECRET",
    "META_PAGE_ID",
    "META_PAGE_ACCESS_TOKEN",
    "META_INSTAGRAM_ACCOUNT_ID",
    "META_WEBHOOK_VERIFY_TOKEN",
    "META_GRAPH_API_VERSION",
    "META_SOCIAL_MESSAGING_ENABLED",
)
approved_paths = (
    Path("/opt/linasbot/.env"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/.env"),
)

def read_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in keys:
            values[key] = value.strip()
    return values

payload_paths: dict[str, dict[str, str]] = {}
for path in approved_paths:
    values = read_values(path)
    if values:
        payload_paths[str(path)] = values

if not payload_paths:
    raise SystemExit("[meta-snapshot] no production Meta environment found")
for path, values in payload_paths.items():
    missing = [key for key in keys[:-1] if not values.get(key)]
    if missing:
        raise SystemExit(f"[meta-snapshot] incomplete Meta environment path={path} missing_names={missing}")
    if values["META_APP_ID"] != os.environ["OLD_APP_ID"]:
        raise SystemExit(f"[meta-snapshot] refusing non-old app environment path={path}")

payload = {
    "schema": 1,
    "created_at": datetime.now(UTC).isoformat(),
    "old_app_id": os.environ["OLD_APP_ID"],
    "paths": payload_paths,
}
output = Path(os.environ["SNAPSHOT_PLAIN"])
output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
os.chmod(output, 0o600)
print(f"[meta-snapshot] source_paths={len(payload_paths)}")
print("[meta-snapshot] old_app_id_match=true")
PY

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive_name="meta-social-old-${OLD_APP_ID}-${timestamp}.json.enc"
archive_path="$ROLLBACK_DIR/$archive_name"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 310000 \
  -pass env:META_ROLLBACK_ENCRYPTION_KEY \
  -in "$snapshot_plain" -out "$archive_path"
chmod 600 "$archive_path"

archive_sha="$(sha256sum "$archive_path" | awk '{print $1}')"
ln -sfn "$archive_name" "$ROLLBACK_DIR/LATEST"
echo "[meta-snapshot] archive=$archive_name"
echo "[meta-snapshot] sha256=$archive_sha"
echo "[meta-snapshot] encrypted=true"
echo "[meta-snapshot] SUCCESS"
