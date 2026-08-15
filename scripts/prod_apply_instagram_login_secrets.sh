#!/usr/bin/env bash
# Stage Instagram Direct Login settings in the canonical environment.
# Runtime activation is owned by scripts/ha/sync_meta_env_to_peer.py.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[instagram-login-apply] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[instagram-login-apply] refusing stage without an authorized release" >&2
  exit 1
fi
/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority

if [ -z "${META_INSTAGRAM_LOGIN_APP_SECRET:-}" ]; then
  echo "[instagram-login-apply] missing required env: META_INSTAGRAM_LOGIN_APP_SECRET" >&2
  exit 1
fi
if [ "${#META_INSTAGRAM_LOGIN_APP_SECRET}" -lt 16 ]; then
  echo "[instagram-login-apply] refusing META_INSTAGRAM_LOGIN_APP_SECRET: length_too_short" >&2
  exit 1
fi
if [ -z "${META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN:-}" ] || \
   [ "${#META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN}" -lt 16 ]; then
  echo "[instagram-login-apply] missing or short Instagram webhook verify token" >&2
  exit 1
fi
if [ -n "${META_INSTAGRAM_LOGIN_APP_ID:-}" ] && \
   [ "$META_INSTAGRAM_LOGIN_APP_ID" != "1035856539045307" ]; then
  echo "[instagram-login-apply] refusing unexpected Instagram product ID" >&2
  exit 1
fi

META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED="${META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED:-false}"
case "$META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED" in
  false|true) ;;
  *)
    echo "[instagram-login-apply] refusing advanced access decision: expected true or false" >&2
    exit 1
    ;;
esac
if [ "$META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED" = "true" ] && \
   [ "${META_INSTAGRAM_LOGIN_APPROVAL_CONFIRM:-}" != "CONFIRM_DIRECT_IG_META_APPROVAL" ]; then
  echo "[instagram-login-apply] refusing approval=true without exact confirmation" >&2
  exit 1
fi
export META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED

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

APP_SECRET_KEY = "META_INSTAGRAM_LOGIN_APP_SECRET"
VERIFY_KEY = "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN"
APP_ID_KEY = "META_INSTAGRAM_LOGIN_APP_ID"
ADVANCED_ACCESS_KEY = "META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED"
ENV_PATH = Path("/opt/linasbot/.env")

updates = {
    APP_ID_KEY: "1035856539045307",
    APP_SECRET_KEY: os.environ[APP_SECRET_KEY].strip(),
    VERIFY_KEY: os.environ[VERIFY_KEY].strip(),
    ADVANCED_ACCESS_KEY: os.environ[ADVANCED_ACCESS_KEY],
}
atomic_update_env(ENV_PATH, updates)


def read_exact(key: str) -> str:
    values = [
        line.split("=", 1)[1]
        for line in ENV_PATH.read_text(encoding="utf-8", errors="strict").splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]
    if len(values) != 1:
        raise SystemExit(f"[instagram-login-apply] staged key count invalid: {key}")
    return values[0]


for key, expected in updates.items():
    if not hmac.compare_digest(read_exact(key), expected):
        raise SystemExit(f"[instagram-login-apply] staged value mismatch: {key}")
    print(f"[instagram-login-apply] {key}:match=true")

print("[instagram-login-apply] stage_only=true")
print("[instagram-login-apply] static_environment_valid=true")
PY
