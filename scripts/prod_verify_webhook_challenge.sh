#!/usr/bin/env bash
# Verify Meta (+ optional WhatsApp) webhook challenges using local .env tokens.
# Never prints token or challenge response bodies beyond length/fingerprint checks.
set -euo pipefail

read_env_var() {
  local key="$1"
  python3 - <<PY
from pathlib import Path
key = "${key}"
for p in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if not p.exists():
        continue
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(key + "="):
            print(line.split("=", 1)[1].strip().strip('"').strip("'"), end="")
            raise SystemExit
raise SystemExit(f"missing {key}")
PY
}

BASE="http://127.0.0.1:8003"
META_TOKEN="$(read_env_var META_WEBHOOK_VERIFY_TOKEN)"
CHAL="challenge-$(date +%s)"

META_RESP="$(curl -sS --max-time 10 \
  "${BASE}/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=${META_TOKEN}&hub.challenge=${CHAL}")"
META_BAD_HTTP="$(curl -sS -o /tmp/wh_meta_bad.txt -w '%{http_code}' --max-time 10 \
  "${BASE}/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=${CHAL}" || true)"

if [ "${META_RESP}" != "${CHAL}" ]; then
  echo "[webhook-verify] FAIL meta_good_token_challenge_mismatch len_resp=${#META_RESP} len_chal=${#CHAL}"
  exit 1
fi
echo "[webhook-verify] meta_good_token_challenge_ok=true"
echo "[webhook-verify] meta_bad_token_http=${META_BAD_HTTP}"
if [ "${META_BAD_HTTP}" != "403" ]; then
  echo "[webhook-verify] FAIL meta expected 403 for bad token"
  exit 1
fi

# WhatsApp verify token is optional in some installs; when present, prove numeric challenge.
if python3 - <<'PY'
from pathlib import Path
import sys
for p in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if not p.exists():
        continue
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("WHATSAPP_WEBHOOK_VERIFY_TOKEN="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v and v != "YOUR_SECURE_VERIFY_TOKEN":
                sys.exit(0)
sys.exit(1)
PY
then
  WA_TOKEN="$(read_env_var WHATSAPP_WEBHOOK_VERIFY_TOKEN)"
  WA_CHAL="$(date +%s)"
  WA_RESP="$(curl -sS --max-time 10 \
    "${BASE}/webhook?hub.mode=subscribe&hub.verify_token=${WA_TOKEN}&hub.challenge=${WA_CHAL}")"
  WA_BAD_HTTP="$(curl -sS -o /tmp/wh_wa_bad.txt -w '%{http_code}' --max-time 10 \
    "${BASE}/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=${WA_CHAL}" || true)"
  # Handler returns JSON integer for numeric challenges.
  if [ "${WA_RESP}" != "${WA_CHAL}" ]; then
    echo "[webhook-verify] FAIL wa_good_token_challenge_mismatch len_resp=${#WA_RESP} len_chal=${#WA_CHAL}"
    exit 1
  fi
  echo "[webhook-verify] wa_good_token_challenge_ok=true"
  echo "[webhook-verify] wa_bad_token_http=${WA_BAD_HTTP}"
  if [ "${WA_BAD_HTTP}" != "403" ]; then
    echo "[webhook-verify] FAIL wa expected 403 for bad token"
    exit 1
  fi
else
  echo "[webhook-verify] wa_verify_token_absent_or_placeholder=true skipped=true"
fi

echo "[webhook-verify] SUCCESS"
