#!/usr/bin/env bash
# Verify Meta webhook challenge using local .env token; never prints the token.
set -euo pipefail
ENV_FILE=/opt/linasbot/.env
TOKEN=$(python3 - <<'PY'
from pathlib import Path
for p in (Path('/opt/linasbot/.env'), Path('/opt/linasbot/linaslaserbot-2.7.22/.env')):
    if not p.exists():
        continue
    for line in p.read_text().splitlines():
        if line.startswith('META_WEBHOOK_VERIFY_TOKEN='):
            print(line.split('=',1)[1].strip().strip('"').strip("'"), end='')
            raise SystemExit
raise SystemExit('missing META_WEBHOOK_VERIFY_TOKEN')
PY
)
CHAL="challenge-$(date +%s)"
RESP=$(curl -sS --max-time 10 "http://127.0.0.1:8003/webhook?hub.mode=subscribe&hub.verify_token=${TOKEN}&hub.challenge=${CHAL}")
BAD=$(curl -sS -o /tmp/wh_bad.txt -w '%{http_code}' --max-time 10 "http://127.0.0.1:8003/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=${CHAL}" || true)
if [ "$RESP" != "$CHAL" ]; then
  echo "[webhook-verify] FAIL good_token_challenge_mismatch len_resp=${#RESP} len_chal=${#CHAL}"
  exit 1
fi
echo "[webhook-verify] good_token_challenge_ok=true"
echo "[webhook-verify] bad_token_http=${BAD}"
if [ "$BAD" != "403" ]; then
  echo "[webhook-verify] FAIL expected 403 for bad token"
  exit 1
fi
echo "[webhook-verify] SUCCESS"
