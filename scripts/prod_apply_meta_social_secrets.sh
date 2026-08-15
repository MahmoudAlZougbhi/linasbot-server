#!/usr/bin/env bash
# Stage Meta social-messaging settings in the canonical environment.
# Runtime activation is owned by scripts/ha/sync_meta_env_to_peer.py.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[meta-apply] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[meta-apply] refusing stage without an authorized release" >&2
  exit 1
fi
/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority

required_nonempty=(
  META_APP_ID
  META_APP_SECRET
  META_PAGE_ID
  META_PAGE_ACCESS_TOKEN
  META_INSTAGRAM_ACCOUNT_ID
  META_WEBHOOK_VERIFY_TOKEN
  META_GRAPH_API_VERSION
)
for key in "${required_nonempty[@]}"; do
  if [ -z "${!key:-}" ]; then
    echo "[meta-apply] missing required env: $key" >&2
    exit 1
  fi
done

if [ "$META_PAGE_ID" != "378696005334409" ]; then
  echo "[meta-apply] refusing unexpected META_PAGE_ID" >&2
  exit 1
fi
if [ "$META_INSTAGRAM_ACCOUNT_ID" != "17841413184256533" ]; then
  echo "[meta-apply] refusing unexpected META_INSTAGRAM_ACCOUNT_ID" >&2
  exit 1
fi
if [ "$META_APP_ID" = "1784792718776344" ] || ! [[ "$META_APP_ID" =~ ^[0-9]+$ ]]; then
  echo "[meta-apply] refusing old or malformed META_APP_ID for new-app cutover" >&2
  exit 1
fi
if [ "$META_GRAPH_API_VERSION" != "v24.0" ]; then
  echo "[meta-apply] refusing unexpected META_GRAPH_API_VERSION" >&2
  exit 1
fi

enable_requested="${APPLY_ENABLE_MESSAGING:-false}"
case "$enable_requested" in
  false|true) ;;
  *) echo "[meta-apply] messaging enable decision must be true or false" >&2; exit 1 ;;
esac
export APPLY_ENABLE_MESSAGING="$enable_requested"

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
keys = (
    "META_APP_ID",
    "META_APP_SECRET",
    "META_PAGE_ID",
    "META_PAGE_ACCESS_TOKEN",
    "META_INSTAGRAM_ACCOUNT_ID",
    "META_WEBHOOK_VERIFY_TOKEN",
    "META_GRAPH_API_VERSION",
)
updates = {key: os.environ[key].strip() for key in keys}
updates.update(
    {
        "META_SOCIAL_MESSAGING_ENABLED": os.environ["APPLY_ENABLE_MESSAGING"],
        "META_SOCIAL_ROLLBACK_ACTIVE": "false",
        "META_SOCIAL_NEW_APP_REQUIRED": "true",
    }
)
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
        raise SystemExit(f"[meta-apply] staged key count invalid: {key}")
    return values[0]


for key, expected in updates.items():
    if not hmac.compare_digest(read_exact(key), expected):
        raise SystemExit(f"[meta-apply] staged value mismatch: {key}")
    print(f"[meta-apply] {key}:match=true")

print("[meta-apply] runtime_activation_deferred_to_ha_sync=true")
print("[meta-apply] stage_only=true")
print("[meta-apply] static_environment_valid=true")
PY
