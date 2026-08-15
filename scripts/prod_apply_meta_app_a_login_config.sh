#!/usr/bin/env bash
# Stage App A Facebook-only Login for Business configuration.
# Runtime activation is owned by scripts/ha/sync_meta_env_to_peer.py.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[meta-login-config] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[meta-login-config] refusing stage without an authorized release" >&2
  exit 1
fi
/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority

FACEBOOK_LOGIN_CONFIG_ID="${META_APP_A_FACEBOOK_LOGIN_CONFIG_ID:-}"
if [ -z "$FACEBOOK_LOGIN_CONFIG_ID" ]; then
  echo "[meta-login-config] META_APP_A_FACEBOOK_LOGIN_CONFIG_ID is required" >&2
  exit 1
fi
if ! [[ "$FACEBOOK_LOGIN_CONFIG_ID" =~ ^[0-9]{8,32}$ ]]; then
  echo "[meta-login-config] META_APP_A_FACEBOOK_LOGIN_CONFIG_ID format is invalid" >&2
  exit 1
fi

REDIRECT_URI="${META_OAUTH_REDIRECT_URI:-https://www.linasaibot.com/oauth/meta/callback}"
if [ "$REDIRECT_URI" != "https://www.linasaibot.com/oauth/meta/callback" ]; then
  echo "[meta-login-config] refusing unexpected redirect URI" >&2
  exit 1
fi
export META_OAUTH_REDIRECT_URI="$REDIRECT_URI"

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
updates = {
    "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID": os.environ[
        "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID"
    ].strip(),
    "META_OAUTH_REDIRECT_URI": os.environ["META_OAUTH_REDIRECT_URI"].strip(),
}
remove_keys = frozenset({"META_APP_A_LOGIN_CONFIG_ID"})
atomic_update_env(ENV_PATH, updates, remove_keys=remove_keys)


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
        raise SystemExit(f"[meta-login-config] staged value mismatch: {key}")
    print(f"[meta-login-config] {key}:match=true")
if read_values("META_APP_A_LOGIN_CONFIG_ID"):
    raise SystemExit("[meta-login-config] obsolete mixed login config remains staged")

print("[meta-login-config] obsolete_mixed_config_absent=true")
print("[meta-login-config] stage_only=true")
print("[meta-login-config] static_environment_valid=true")
PY
