#!/usr/bin/env bash
# Single-entry WhatsApp Phase 1 ops for drone-ssh (script_stop-safe).
# Usage:
#   MODE=APPLY_WHATSAPP_CLOUD_PHASE1_FLAGS_ONLY bash scripts/prod_whatsapp_cloud_phase1_ops.sh
#   MODE=APPLY_WHATSAPP_CLOUD_PHASE1 bash scripts/prod_whatsapp_cloud_phase1_ops.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
MODE="${MODE:-}"

echo "[wa-ops] deployed_sha=$(git rev-parse HEAD)"
echo "[wa-ops] mode=${MODE}"

chmod +x scripts/prod_whatsapp_cloud_migrate.sh scripts/prod_apply_whatsapp_cloud_phase1_flags.sh || true

if [ "$MODE" = "APPLY_WHATSAPP_CLOUD_PHASE1" ]; then
  echo "[wa-ops] running migrate"
  sudo bash scripts/prod_whatsapp_cloud_migrate.sh
elif [ "$MODE" = "APPLY_WHATSAPP_CLOUD_PHASE1_FLAGS_ONLY" ]; then
  echo "[wa-ops] skipping migrate (FLAGS_ONLY)"
else
  echo "[wa-ops] BLOCKED: unknown mode=${MODE}"
  exit 2
fi

echo "[wa-ops] applying phase1 flags"
sudo bash scripts/prod_apply_whatsapp_cloud_phase1_flags.sh

curl -fsS https://linasaibot.com/api/ready >/tmp/ready.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/ready.json"))
assert d.get("ok") is True, d
jq=d.get("checks",{}).get("job_queue",{})
assert jq.get("redis_required") is not True, jq
print("[wa-ops] ready ok; redis_required=", jq.get("redis_required"))
PY
echo "[wa-ops] COMPLETE_OK"
