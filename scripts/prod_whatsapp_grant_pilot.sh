#!/usr/bin/env bash
# Grant WhatsApp Cloud pilot entitlement via platform_owner authenticated API path.
# Ops args: TENANT_ID + REASON. Never hardcodes email bypasses in application code.
# Usage:
#   sudo TENANT_ID=linas REASON=whatsapp_cloud_phase1_internal_pilot \
#     bash scripts/prod_whatsapp_grant_pilot.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
TENANT_ID="$(echo "${TENANT_ID:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
REASON="${REASON:-}"

if [ -z "$TENANT_ID" ] || [ -z "$REASON" ]; then
  echo "[wa-pilot] BLOCKED: TENANT_ID and REASON are required ops arguments"
  exit 2
fi

load_env_file() {
  local f="$1"
  if [ -f "$f" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$f"
    set +a
    echo "[wa-pilot] env_file_loaded=true path=$f"
  fi
}

load_env_file "/opt/linasbot/.env"
load_env_file "$APP_DIR/.env"
load_env_file "/opt/linasbot/linaslaserbot-2.7.22/.env"

PYTHON_CMD="python3"
[ -x "$APP_DIR/venv/bin/python" ] && PYTHON_CMD="$APP_DIR/venv/bin/python"

export TENANT_ID REASON APP_DIR
"$PYTHON_CMD" - <<'PY'
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from services.dashboard_session_service import session_service
from services.user_service import UserService

tenant_id = os.environ["TENANT_ID"].strip().lower()
reason = os.environ["REASON"].strip()
assert tenant_id and reason

users = UserService().get_all_users()
owners = [u for u in users if str(u.get("role") or "").strip().lower() == "platform_owner"]
if not owners:
    raise SystemExit("[wa-pilot] BLOCKED: no platform_owner user found in dashboard_users")

owner = owners[0]
user_id = str(owner.get("id") or owner.get("userId") or "").strip()
email = str(owner.get("email") or "").strip()
if not user_id:
    raise SystemExit("[wa-pilot] BLOCKED: platform_owner missing id")

perms = owner.get("permissions") if isinstance(owner.get("permissions"), dict) else None
record = session_service.create_session(
    user_id=user_id,
    email=email or f"platform-owner:{user_id}",
    role="platform_owner",
    permissions=perms,
    tenant_id=str(owner.get("tenantId") or "linas"),
    password_epoch=int(owner.get("passwordEpoch") or 0),
    ttl_seconds=900,
)
bearer = session_service.cookie_value_for(record)
payload = json.dumps({"tenant_id": tenant_id, "reason": reason}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8003/api/whatsapp/cloud/pilot/grant",
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    },
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        status = resp.status
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")[:400]
    raise SystemExit(f"[wa-pilot] grant_http_fail status={exc.code} detail={detail}") from exc

print(
    f"[wa-pilot] grant_ok http={status} tenant_id={body.get('tenant_id')} "
    f"status={body.get('status')} actor_user_id_set={bool(user_id)} reason_len={len(reason)}"
)

# Verify via list endpoint (still platform_owner).
req2 = urllib.request.Request(
    "http://127.0.0.1:8003/api/whatsapp/cloud/pilot/list",
    method="GET",
    headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json"},
)
with urllib.request.urlopen(req2, timeout=30) as resp:
    listed = json.loads(resp.read().decode("utf-8"))
pilots = listed.get("pilots") or []
match = [p for p in pilots if str(p.get("tenant_id") or "").lower() == tenant_id]
if not match or str(match[0].get("status") or "") != "active":
    raise SystemExit(f"[wa-pilot] BLOCKED: tenant {tenant_id} not active in pilot list")
print(
    f"[wa-pilot] list_ok tenant_id={tenant_id} status=active "
    f"public_availability={listed.get('public_availability')} "
    f"require_pilot_entitlement={listed.get('require_pilot_entitlement')}"
)
cfg = listed.get("config_keys_present") or {}
es = cfg.get("META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID")
print(f"[wa-pilot] embedded_signup_config_present={bool(es)}")
print("[wa-pilot] COMPLETE_OK")
PY
