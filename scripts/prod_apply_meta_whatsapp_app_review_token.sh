#!/usr/bin/env bash
# Stage the temporary WhatsApp App Review bind token and exact WABA allowlist.
# Runtime activation is owned by scripts/ha/sync_meta_env_to_peer.py.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[wa-app-review-token] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[wa-app-review-token] refusing stage without an authorized release" >&2
  exit 1
fi
/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority

ACTION="${META_WHATSAPP_APP_REVIEW_TOKEN_ACTION:-}"
CONFIRM="${META_WHATSAPP_APP_REVIEW_TOKEN_CONFIRM:-}"
EXPECTED_WABA_ID="1409769574350248"
APP_REVIEW_TOKEN="${META_WHATSAPP_APP_REVIEW_BIND_TOKEN:-}"

case "$ACTION" in
  install)
    [ "$CONFIRM" = "INSTALL_META_WHATSAPP_APP_REVIEW_TOKEN" ] || {
      echo "[wa-app-review-token] install confirmation mismatch" >&2
      exit 1
    }
    [ "${META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS:-}" = "$EXPECTED_WABA_ID" ] || {
      echo "[wa-app-review-token] refusing non-test WABA allowlist" >&2
      exit 1
    }
    [ "${#APP_REVIEW_TOKEN}" -ge 20 ] || {
      echo "[wa-app-review-token] missing or invalid GitHub bind token secret" >&2
      exit 1
    }
    ;;
  remove)
    [ "$CONFIRM" = "REMOVE_META_WHATSAPP_APP_REVIEW_TOKEN" ] || {
      echo "[wa-app-review-token] remove confirmation mismatch" >&2
      exit 1
    }
    ;;
  *)
    echo "[wa-app-review-token] action must be install or remove" >&2
    exit 1
    ;;
esac

APP_DIR=/opt/linasbot
ENV_PATH="$APP_DIR/.env"
PYTHON_BIN="$APP_DIR/venv/bin/python"
test -x "$PYTHON_BIN"
test -f "$ENV_PATH"

umask 077
"$PYTHON_BIN" -I - <<'PY'
import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

ENV_PATH = Path("/opt/linasbot/.env")
TOKEN_KEY = "META_WHATSAPP_APP_REVIEW_BIND_TOKEN"
ALLOWLIST_KEY = "META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS"
action = os.environ["META_WHATSAPP_APP_REVIEW_TOKEN_ACTION"].strip()

if action == "install":
    updates = {
        TOKEN_KEY: os.environ[TOKEN_KEY].strip(),
        ALLOWLIST_KEY: os.environ[ALLOWLIST_KEY].strip(),
    }
    remove_keys: frozenset[str] = frozenset()
else:
    updates = {}
    remove_keys = frozenset({TOKEN_KEY, ALLOWLIST_KEY})

atomic_update_env(ENV_PATH, updates, remove_keys=remove_keys)


def read_values(key: str) -> list[str]:
    return [
        line.split("=", 1)[1]
        for line in ENV_PATH.read_text(encoding="utf-8", errors="strict").splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]


if action == "install":
    for key, expected in updates.items():
        values = read_values(key)
        if len(values) != 1 or not hmac.compare_digest(values[0], expected):
            raise SystemExit(f"[wa-app-review-token] staged value mismatch: {key}")
        print(f"[wa-app-review-token] {key}:match=true")
else:
    for key in remove_keys:
        if read_values(key):
            raise SystemExit(f"[wa-app-review-token] staged removal mismatch: {key}")
        print(f"[wa-app-review-token] {key}:absent=true")

print(f"[wa-app-review-token] action={action}")
print("[wa-app-review-token] stage_only=true")
print("[wa-app-review-token] static_environment_valid=true")
PY
