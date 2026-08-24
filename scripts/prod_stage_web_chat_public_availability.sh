#!/usr/bin/env bash
# Stage WEB_CHAT_PUBLIC_AVAILABILITY=true on the canonical production env.
# Activation/restart is owned by scripts/ha/sync_meta_env_to_peer.py --finalize.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[web-chat-stage] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[web-chat-stage] refusing stage without an authorized release" >&2
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
    "WEB_CHAT_PUBLIC_AVAILABILITY": "true",
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
        raise SystemExit(f"[web-chat-stage] staged value mismatch: {key}")
    print(f"[web-chat-stage] {key}:match=true")

print("[web-chat-stage] stage_only=true")
print("[web-chat-stage] COMPLETE_OK")
PY
