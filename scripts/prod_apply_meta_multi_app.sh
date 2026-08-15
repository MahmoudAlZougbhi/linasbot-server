#!/usr/bin/env bash
# Stage the encrypted Meta multi-app configuration in the canonical environment.
# Runtime activation is owned by scripts/ha/sync_meta_env_to_peer.py.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[meta-multi-app] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[meta-multi-app] refusing stage without an authorized release" >&2
  exit 1
fi
/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority

required=(
  META_APP_ID
  META_APP_SECRET
  META_PAGE_ID
  META_PAGE_ACCESS_TOKEN
  META_INSTAGRAM_ACCOUNT_ID
  META_WEBHOOK_VERIFY_TOKEN
  META_GRAPH_API_VERSION
  META_CREDENTIAL_ENCRYPTION_KEY
)
for key in "${required[@]}"; do
  if [ -z "${!key:-}" ]; then
    echo "[meta-multi-app] missing required environment variable: $key" >&2
    exit 1
  fi
done

if [ "$META_APP_ID" != "2963733803971681" ]; then
  echo "[meta-multi-app] refusing unexpected App A ID" >&2
  exit 1
fi
if [ "$META_PAGE_ID" != "378696005334409" ] || \
   [ "$META_INSTAGRAM_ACCOUNT_ID" != "17841413184256533" ]; then
  echo "[meta-multi-app] refusing unexpected Lina asset identity" >&2
  exit 1
fi
if [ "$META_GRAPH_API_VERSION" != "v24.0" ]; then
  echo "[meta-multi-app] refusing unexpected Graph API version" >&2
  exit 1
fi
if [ "${#META_CREDENTIAL_ENCRYPTION_KEY}" -lt 32 ]; then
  echo "[meta-multi-app] credential encryption key is too short" >&2
  exit 1
fi

app_b_present=0
app_b_missing=0
for key in META_APP_B_ID META_APP_B_SECRET META_APP_B_WEBHOOK_VERIFY_TOKEN META_APP_B_LOGIN_CONFIG_ID; do
  if [ -n "${!key:-}" ]; then
    app_b_present=$((app_b_present + 1))
  else
    app_b_missing=$((app_b_missing + 1))
  fi
done
if [ "$app_b_present" -gt 0 ] && [ "$app_b_missing" -gt 0 ]; then
  echo "[meta-multi-app] App B configuration is partial; refusing apply" >&2
  exit 1
fi

for key in META_APP_A_ADVANCED_ACCESS_APPROVED META_APP_B_ADVANCED_ACCESS_APPROVED; do
  value="${!key:-false}"
  case "$value" in
    false|true) ;;
    *) echo "[meta-multi-app] $key must be true or false" >&2; exit 1 ;;
  esac
done
enable_requested="${APPLY_META_MULTI_APP_REGISTRY_ENABLED:-false}"
case "$enable_requested" in
  false|true) ;;
  *) echo "[meta-multi-app] registry enable decision must be true or false" >&2; exit 1 ;;
esac
export META_APP_A_ADVANCED_ACCESS_APPROVED="${META_APP_A_ADVANCED_ACCESS_APPROVED:-false}"
export META_APP_B_ADVANCED_ACCESS_APPROVED="${META_APP_B_ADVANCED_ACCESS_APPROVED:-false}"
export APPLY_META_MULTI_APP_REGISTRY_ENABLED="$enable_requested"

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
from services.meta_surface_secret_separation import (
    require_separated_meta_surface_secrets_for_update,
)

ENV_PATH = Path("/opt/linasbot/.env")
required = {
    "META_APP_ID": os.environ["META_APP_ID"].strip(),
    "META_APP_SECRET": os.environ["META_APP_SECRET"].strip(),
    "META_PAGE_ID": os.environ["META_PAGE_ID"].strip(),
    "META_PAGE_ACCESS_TOKEN": os.environ["META_PAGE_ACCESS_TOKEN"].strip(),
    "META_INSTAGRAM_ACCOUNT_ID": os.environ["META_INSTAGRAM_ACCOUNT_ID"].strip(),
    "META_WEBHOOK_VERIFY_TOKEN": os.environ["META_WEBHOOK_VERIFY_TOKEN"].strip(),
    "META_GRAPH_API_VERSION": os.environ["META_GRAPH_API_VERSION"].strip(),
    "META_CREDENTIAL_ENCRYPTION_KEY": os.environ["META_CREDENTIAL_ENCRYPTION_KEY"].strip(),
}
updates = {
    **required,
    "META_APP_A_ID": required["META_APP_ID"],
    "META_APP_A_SECRET": required["META_APP_SECRET"],
    "META_APP_A_WEBHOOK_VERIFY_TOKEN": required["META_WEBHOOK_VERIFY_TOKEN"],
    "META_APP_A_ADVANCED_ACCESS_APPROVED": os.environ[
        "META_APP_A_ADVANCED_ACCESS_APPROVED"
    ],
    "META_OAUTH_REDIRECT_URI": "https://www.linasaibot.com/oauth/meta/callback",
    "META_MULTI_APP_REGISTRY_ENABLED": os.environ[
        "APPLY_META_MULTI_APP_REGISTRY_ENABLED"
    ],
    "META_APP_B_ADVANCED_ACCESS_APPROVED": os.environ[
        "META_APP_B_ADVANCED_ACCESS_APPROVED"
    ],
    "META_APP_B_LINAS_CUTOVER_APPROVED": "false",
}
for key in (
    "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID",
    "META_APP_B_ID",
    "META_APP_B_SECRET",
    "META_APP_B_WEBHOOK_VERIFY_TOKEN",
    "META_APP_B_LOGIN_CONFIG_ID",
):
    value = (os.environ.get(key) or "").strip()
    if value:
        updates[key] = value

require_separated_meta_surface_secrets_for_update(ENV_PATH, updates)
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
        raise SystemExit(f"[meta-multi-app] staged key count invalid: {key}")
    return values[0]


for key, expected in updates.items():
    if not hmac.compare_digest(read_exact(key), expected):
        raise SystemExit(f"[meta-multi-app] staged value mismatch: {key}")
    print(f"[meta-multi-app] {key}:match=true")

print("[meta-multi-app] direct_instagram_binding_seeded=false")
print("[meta-multi-app] registry_activation_deferred_to_ha_sync=true")
print("[meta-multi-app] stage_only=true")
print("[meta-multi-app] static_environment_valid=true")
PY
