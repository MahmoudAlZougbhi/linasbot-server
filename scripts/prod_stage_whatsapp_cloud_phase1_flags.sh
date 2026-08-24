#!/usr/bin/env bash
# Stage WhatsApp Cloud Phase 1 operational flags on the canonical production env.
# Activation/restart is owned by scripts/ha/sync_meta_env_to_peer.py --finalize.
# Never prints secret values.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[wa-phase1-stage] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[wa-phase1-stage] refusing stage without an authorized release" >&2
  exit 1
fi

/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority

APP_DIR=/opt/linasbot
ENV_PATH="$APP_DIR/.env"
PYTHON_BIN="$APP_DIR/venv/bin/python"
test -x "$PYTHON_BIN"
test -f "$ENV_PATH"

umask 077
"$PYTHON_BIN" -I - <<'PY'
import hmac
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

ENV_PATH = Path("/opt/linasbot/.env")
updates = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
atomic_update_env(ENV_PATH, updates)


def read_values(key: str) -> list[str]:
    return [
        line.split("=", 1)[1]
        for line in ENV_PATH.read_text(encoding="utf-8", errors="strict").splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]


for key, expected in updates.items():
    values = read_values(key)
    if len(values) != 1 or not hmac.compare_digest(values[0], expected):
        raise SystemExit(f"[wa-phase1-stage] staged value mismatch: {key}")
    print(f"[wa-phase1-stage] {key}:match=true")

print("[wa-phase1-stage] stage_only=true")
print("[wa-phase1-stage] COMPLETE_OK")
PY
