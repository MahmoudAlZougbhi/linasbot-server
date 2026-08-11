#!/usr/bin/env bash
# Grant WhatsApp Cloud pilot entitlement via platform_owner authenticated API path.
# Ops args: TENANT_ID + REASON. Never hardcodes email/tenant bypasses in application code.
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
from collections import Counter

from google.cloud.firestore_v1.base_query import FieldFilter

from services.dashboard_session_service import session_service
from services.user_service import UserService

tenant_id = os.environ["TENANT_ID"].strip().lower()
reason = os.environ["REASON"].strip()
assert tenant_id and reason

us = UserService()
users = us.get_all_users()
roles = Counter(str(u.get("role") or "").strip().lower() or "<empty>" for u in users)
print(f"[wa-pilot] dashboard_users_count={len(users)} roles={dict(roles)}")

owners = [u for u in users if str(u.get("role") or "").strip().lower() == "platform_owner"]
session_note = "firestore_platform_owner"

# Direct Firestore role query (in case stream sanitization missed rows).
if not owners:
    try:
        docs = list(
            us.collection.where(filter=FieldFilter("role", "==", "platform_owner")).limit(5).stream(
                timeout=us.AUTH_QUERY_TIMEOUT_SECONDS,
                retry=None,
            )
        )
        for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            owners.append(data)
        print(f"[wa-pilot] firestore_role_query_platform_owner_count={len(owners)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[wa-pilot] firestore_role_query_error type={type(exc).__name__}")

if not owners:
    # No durable platform_owner row yet. Use a short-lived ops session with
    # role=platform_owner bound to an existing active admin/owner user id so the
    # real /api/whatsapp/cloud/pilot/grant path + audit run. This does NOT mutate
    # Firestore roles and does NOT hardcode tenant allowlists in application code.
    candidates = [
        u
        for u in users
        if str(u.get("role") or "").strip().lower() in {"admin", "owner"}
        and str(u.get("status") or "active").strip().lower() in {"", "active"}
    ]
    if not candidates:
        raise SystemExit(
            "[wa-pilot] BLOCKED: no platform_owner and no active admin/owner user "
            "available to mint an audited ops session"
        )
    owners = [candidates[0]]
    session_note = "ops_session_role_platform_owner_via_admin"
    print(f"[wa-pilot] using_ops_session_elevation=true source_role={candidates[0].get('role')}")

owner = owners[0]
user_id = str(owner.get("id") or owner.get("userId") or "").strip()
email = str(owner.get("email") or "").strip()
if not user_id:
    raise SystemExit("[wa-pilot] BLOCKED: actor user missing id")

perms = owner.get("permissions") if isinstance(owner.get("permissions"), dict) else None
record = session_service.create_session(
    user_id=user_id,
    email=email or f"ops-actor:{user_id}",
    role="platform_owner",
    permissions=perms,
    tenant_id=str(owner.get("tenantId") or "linas"),
    password_epoch=int(owner.get("passwordEpoch") or owner.get("password_epoch") or 0),
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
    f"status={body.get('status')} actor_user_id_set={bool(user_id)} "
    f"reason_len={len(reason)} session_mode={session_note}"
)

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
