#!/usr/bin/env bash
# Apply Phase 1 WhatsApp Cloud operational flags on production.
# Keeps WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false (internal pilot only).
# Never prints secret values. Does not touch Meta Console / Redis-required.
#
# Usage: sudo bash scripts/prod_apply_whatsapp_cloud_phase1_flags.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILES=("$APP_DIR/.env")
if [ -f "/opt/linasbot/.env" ]; then
  ENV_FILES+=("/opt/linasbot/.env")
fi
if [ -f "/opt/linasbot/linaslaserbot-2.7.22/.env" ]; then
  ENV_FILES+=("/opt/linasbot/linaslaserbot-2.7.22/.env")
fi

upsert() {
  local file="$1" key="$2" value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
text = path.read_text(encoding="utf-8") if path.exists() else ""
pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
line = f"{key}={value}"
if pattern.search(text):
    text = pattern.sub(line, text)
else:
    if text and not text.endswith("\n"):
        text += "\n"
    text += line + "\n"
path.write_text(text, encoding="utf-8")
print(f"[wa-phase1] upserted path={path} key={key}")
PY
}

KEYS=(
  WHATSAPP_CLOUD_CONNECTION_UI_ENABLED=true
  WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED=true
  WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED=true
  WHATSAPP_CLOUD_AI_REPLIES_ENABLED=true
  WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED=false
  WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT=true
  WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false
)

for envf in "${ENV_FILES[@]}"; do
  [ -f "$envf" ] || continue
  for pair in "${KEYS[@]}"; do
    k="${pair%%=*}"
    v="${pair#*=}"
    upsert "$envf" "$k" "$v"
  done
done

systemctl restart linasbot
sleep 3
systemctl is-active --quiet linasbot
echo "[wa-phase1] service_active=true"
echo "[wa-phase1] public_availability=false (Phase 1 internal pilot only)"
echo "[wa-phase1] COMPLETE_OK"
