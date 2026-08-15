#!/usr/bin/env bash
# Dual-node Resend secret sync for Linas HA. Never prints secret values.
# Loads sending-only + webhook from a local gitignored env file, scp apply script,
# exports required envs over SSH, runs scripts/prod_apply_resend_secrets.sh on each node.
set -euo pipefail

echo "[resend-dual] BLOCKED: retired; use a reviewed two-node env transaction" >&2
exit 2

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NODE01="${NODE01:-139.59.167.62}"
NODE02="${NODE02:-167.99.89.243}"
LOCAL_ENV="${RESEND_LOCAL_ENV:-$ROOT/.env.local}"
APPLY_SCRIPT="$ROOT/scripts/prod_apply_resend_secrets.sh"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=12)

if [ ! -f "$LOCAL_ENV" ]; then
  echo "[resend-dual] BLOCKED_OWNER_ACTION — missing ${LOCAL_ENV}" >&2
  echo "[resend-dual] Need secret name: RESEND_API_KEY (SENDING_ONLY) and RESEND_WEBHOOK_SECRET" >&2
  echo "[resend-dual] Provide via Cursor secrets or server .env — do not paste in chat." >&2
  exit 2
fi
if [ ! -f "$APPLY_SCRIPT" ]; then
  echo "[resend-dual] missing apply script" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
# shellcheck source=/dev/null
source "$LOCAL_ENV"
set +a

# Prefer explicit sending-only key for runtime.
if [ -n "${RESEND_API_KEY_SENDING:-}" ]; then
  export RESEND_API_KEY="$RESEND_API_KEY_SENDING"
fi
if [ -z "${RESEND_API_KEY:-}" ] || [ -z "${RESEND_WEBHOOK_SECRET:-}" ]; then
  echo "BLOCKED_OWNER_ACTION — RESEND_API_KEY (SENDING_ONLY) and/or RESEND_WEBHOOK_SECRET unavailable" >&2
  exit 2
fi
if [ -n "${RESEND_API_KEY_FULL:-}" ] && [ "$RESEND_API_KEY" = "$RESEND_API_KEY_FULL" ]; then
  echo "[resend-dual] refusing: runtime key equals Full Access key" >&2
  exit 1
fi

export RESEND_FROM_EMAIL="${RESEND_FROM_EMAIL:-no-reply@linasaibot.com}"
export RESEND_FROM_NAME="${RESEND_FROM_NAME:-Linas AI}"
export RESEND_REPLY_TO="${RESEND_REPLY_TO:-support@linasaibot.com}"
# If local file only has RESEND_FROM, keep it; else compose.
if [ -z "${RESEND_FROM:-}" ]; then
  export RESEND_FROM="${RESEND_FROM_NAME} <${RESEND_FROM_EMAIL}>"
fi

# Drop Full Access from this shell so it cannot leak to remote apply.
unset RESEND_API_KEY_FULL RESEND_API_KEY_SENDING || true

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/linas_resend_stage.XXXXXX")"
chmod 700 "$STAGE_DIR"
cleanup_stage() { rm -rf "$STAGE_DIR"; }
trap cleanup_stage EXIT

# Stage secrets for scp (never cat/echo values). Quote for safe `source`.
python3 - <<'PY' >"$STAGE_DIR/payload.env"
import os
keys = [
    "RESEND_API_KEY",
    "RESEND_WEBHOOK_SECRET",
    "RESEND_FROM_EMAIL",
    "RESEND_FROM_NAME",
    "RESEND_REPLY_TO",
    "RESEND_FROM",
]
for key in keys:
    value = os.environ[key]
    # Single-quote shell-safe encoding
    escaped = value.replace("'", "'\"'\"'")
    print(f"{key}='{escaped}'")
PY
chmod 600 "$STAGE_DIR/payload.env"
cp "$APPLY_SCRIPT" "$STAGE_DIR/prod_apply_resend_secrets.sh"
chmod 700 "$STAGE_DIR/prod_apply_resend_secrets.sh"

apply_node() {
  local host="$1"
  local label="$2"
  echo "[resend-dual] === ${label} (${host}) ==="
  scp -o BatchMode=yes -o ConnectTimeout=12 \
    "$STAGE_DIR/prod_apply_resend_secrets.sh" "$STAGE_DIR/payload.env" \
    "root@${host}:/tmp/" >/dev/null
  "${SSH[@]}" "root@${host}" 'set -euo pipefail
    chmod 700 /tmp/prod_apply_resend_secrets.sh
    chmod 600 /tmp/payload.env
    set -a
    # shellcheck disable=SC1091
    source /tmp/payload.env
    set +a
    bash /tmp/prod_apply_resend_secrets.sh
    shred -u /tmp/payload.env /tmp/prod_apply_resend_secrets.sh 2>/dev/null \
      || rm -f /tmp/payload.env /tmp/prod_apply_resend_secrets.sh
  '
  echo "[resend-dual] ${label} apply_done"
}

apply_node "$NODE01" "node01"
apply_node "$NODE02" "node02"

# Presence verification both nodes (no values).
for pair in "node01:$NODE01" "node02:$NODE02"; do
  label="${pair%%:*}"
  host="${pair##*:}"
  echo "[resend-dual] verify ${label}"
  "${SSH[@]}" "root@${host}" 'python3 - <<"PY"
import hashlib
from pathlib import Path
path = Path("/opt/linasbot/.env")
env = {}
for line in path.read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
need = ["RESEND_API_KEY","RESEND_WEBHOOK_SECRET","RESEND_FROM_EMAIL","RESEND_FROM_NAME","RESEND_REPLY_TO","RESEND_FROM"]
for k in need:
    v = env.get(k, "")
    print(f"present_{k}={bool(v)} len={len(v)}")
print("full_access_absent=", "RESEND_API_KEY_FULL" not in env)
print("mode=", oct(path.stat().st_mode & 0o777))
if env.get("RESEND_API_KEY"):
    print("api_key_fp=", hashlib.sha256(env["RESEND_API_KEY"].encode()).hexdigest()[:16])
if env.get("RESEND_WEBHOOK_SECRET"):
    print("webhook_fp=", hashlib.sha256(env["RESEND_WEBHOOK_SECRET"].encode()).hexdigest()[:16])
PY'
done

echo "[resend-dual] SUCCESS"
