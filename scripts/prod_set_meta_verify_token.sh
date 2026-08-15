#!/usr/bin/env bash
# Stage META_WEBHOOK_VERIFY_TOKEN in the canonical environment.
# Runtime and Nginx verification are owned by the HA sync/verifier workflow.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[meta-verify-token] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[meta-verify-token] refusing stage without an authorized release" >&2
  exit 1
fi
/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority
if [ -z "${META_WEBHOOK_VERIFY_TOKEN:-}" ] || \
   [ "${#META_WEBHOOK_VERIFY_TOKEN}" -lt 16 ]; then
  echo "[meta-verify-token] META_WEBHOOK_VERIFY_TOKEN is missing or too short" >&2
  exit 1
fi

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
text_before = ENV_PATH.read_text(encoding="utf-8", errors="strict")
messaging_values = [
    line.split("=", 1)[1]
    for line in text_before.splitlines()
    if "=" in line
    and not line.lstrip().startswith("#")
    and line.split("=", 1)[0].strip() == "META_SOCIAL_MESSAGING_ENABLED"
]
updates = {"META_WEBHOOK_VERIFY_TOKEN": os.environ["META_WEBHOOK_VERIFY_TOKEN"].strip()}
if not messaging_values:
    updates["META_SOCIAL_MESSAGING_ENABLED"] = "false"
elif len(messaging_values) > 1:
    updates["META_SOCIAL_MESSAGING_ENABLED"] = messaging_values[-1]

require_separated_meta_surface_secrets_for_update(ENV_PATH, updates)
atomic_update_env(ENV_PATH, updates)
text_after = ENV_PATH.read_text(encoding="utf-8", errors="strict")


def read_exact(key: str) -> str:
    values = [
        line.split("=", 1)[1]
        for line in text_after.splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]
    if len(values) != 1:
        raise SystemExit(f"[meta-verify-token] staged key count invalid: {key}")
    return values[0]


if not hmac.compare_digest(
    read_exact("META_WEBHOOK_VERIFY_TOKEN"),
    updates["META_WEBHOOK_VERIFY_TOKEN"],
):
    raise SystemExit("[meta-verify-token] staged verify token mismatch")
messaging_enabled = read_exact("META_SOCIAL_MESSAGING_ENABLED")
if messaging_enabled not in {"false", "true"}:
    raise SystemExit("[meta-verify-token] staged messaging decision is invalid")

print("[meta-verify-token] verify_token_match=true")
print(f"[meta-verify-token] messaging_enabled={messaging_enabled}")
print("[meta-verify-token] nginx_mutation_deferred_to_tracked_release=true")
print("[meta-verify-token] stage_only=true")
print("[meta-verify-token] static_environment_valid=true")
PY
