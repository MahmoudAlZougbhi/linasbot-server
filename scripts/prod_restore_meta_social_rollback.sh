#!/usr/bin/env bash
# Restore the retired app's single-secret production configuration from the
# encrypted rollback archive. The compromised historical verify token is never
# restored; the current rotated canonical token is required instead.
set -euo pipefail
umask 077

OLD_APP_ID="1784792718776344"
ROLLBACK_DIR="/opt/linasbot/.meta-social-rollback"

if [ -z "${META_ROLLBACK_ENCRYPTION_KEY:-}" ] || [ "${#META_ROLLBACK_ENCRYPTION_KEY}" -lt 32 ]; then
  echo "[meta-restore] rollback encryption key missing or too short" >&2
  exit 1
fi
if [ -z "${META_WEBHOOK_VERIFY_TOKEN:-}" ] || [ "${#META_WEBHOOK_VERIFY_TOKEN}" -lt 16 ]; then
  echo "[meta-restore] rotated canonical verify token missing or too short" >&2
  exit 1
fi

archive_name="${META_ROLLBACK_ARCHIVE:-LATEST}"
if [ "$archive_name" = "LATEST" ]; then
  archive_path="$ROLLBACK_DIR/LATEST"
else
  case "$archive_name" in
    meta-social-old-1784792718776344-*.json.enc) ;;
    *) echo "[meta-restore] refusing unexpected archive name" >&2; exit 1 ;;
  esac
  archive_path="$ROLLBACK_DIR/$archive_name"
fi

resolved_archive="$(readlink -f "$archive_path")"
case "$resolved_archive" in
  "$ROLLBACK_DIR"/meta-social-old-1784792718776344-*.json.enc) ;;
  *) echo "[meta-restore] archive resolved outside approved rollback directory" >&2; exit 1 ;;
esac
test -f "$resolved_archive"

plain_snapshot="$(mktemp /tmp/linas-meta-restore.XXXXXX.json)"
cleanup() {
  if [ -f "$plain_snapshot" ]; then
    if command -v shred >/dev/null 2>&1; then
      shred -u "$plain_snapshot"
    else
      rm -f "$plain_snapshot"
    fi
  fi
}
trap cleanup EXIT

openssl enc -d -aes-256-cbc -pbkdf2 -iter 310000 \
  -pass env:META_ROLLBACK_ENCRYPTION_KEY \
  -in "$resolved_archive" -out "$plain_snapshot"
chmod 600 "$plain_snapshot"

SNAPSHOT_PLAIN="$plain_snapshot" OLD_APP_ID="$OLD_APP_ID" python3 - <<'PY'
import json
import os
from pathlib import Path

snapshot = json.loads(Path(os.environ["SNAPSHOT_PLAIN"]).read_text(encoding="utf-8"))
if snapshot.get("schema") != 1 or snapshot.get("old_app_id") != os.environ["OLD_APP_ID"]:
    raise SystemExit("[meta-restore] invalid snapshot schema or app identity")

approved = {
    "/opt/linasbot/.env",
    "/opt/linasbot/linaslaserbot-2.7.22/.env",
}
required = {
    "META_APP_ID",
    "META_APP_SECRET",
    "META_PAGE_ID",
    "META_PAGE_ACCESS_TOKEN",
    "META_INSTAGRAM_ACCOUNT_ID",
    "META_GRAPH_API_VERSION",
}
enable = (os.environ.get("ROLLBACK_ENABLE_MESSAGING") or "false").lower() in {"1", "true", "yes"}
rotated_verify_token = os.environ["META_WEBHOOK_VERIFY_TOKEN"].strip()

for raw_path, values in snapshot.get("paths", {}).items():
    if raw_path not in approved or not isinstance(values, dict):
        raise SystemExit("[meta-restore] snapshot contains an unexpected environment path")
    if not required.issubset({key for key, value in values.items() if str(value).strip()}):
        raise SystemExit("[meta-restore] snapshot is missing required old-app values")
    if str(values.get("META_APP_ID")) != os.environ["OLD_APP_ID"]:
        raise SystemExit("[meta-restore] snapshot does not belong to the retired app")
    if str(values.get("META_PAGE_ID")) != "378696005334409":
        raise SystemExit("[meta-restore] snapshot Page identity mismatch")
    if str(values.get("META_INSTAGRAM_ACCOUNT_ID")) != "17841413184256533":
        raise SystemExit("[meta-restore] snapshot Instagram identity mismatch")

    updates = {key: str(values[key]).strip() for key in required}
    updates.update(
        {
            "META_WEBHOOK_VERIFY_TOKEN": rotated_verify_token,
            "META_SOCIAL_MESSAGING_ENABLED": "true" if enable else "false",
            "META_SOCIAL_ROLLBACK_ACTIVE": "true",
            "META_SOCIAL_NEW_APP_REQUIRED": "true",
        }
    )
    path = Path(raw_path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output = []
    seen = set()
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates and not line.lstrip().startswith("#"):
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    temporary = path.with_suffix(path.suffix + ".meta-restore.tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
    print(f"[meta-restore] updated={path}")

print("[meta-restore] retired_app_restored=true")
print(f"[meta-restore] messaging_enabled={enable}")
print("[meta-restore] compromised_verify_token_restored=false")
PY

systemctl restart linasbot
sleep 6
systemctl is-active --quiet linasbot
python3 - <<'PY'
import json
import urllib.request

for path in ("/api/health", "/api/ready"):
    with urllib.request.urlopen("https://www.linasaibot.com" + path, timeout=15) as response:
        payload = json.load(response)
        if response.status != 200 or payload.get("ok") is not True:
            raise SystemExit(f"[meta-restore] health failure at {path}")
        print(f"[meta-restore] {path}=ok")
PY
echo "[meta-restore] SUCCESS"
