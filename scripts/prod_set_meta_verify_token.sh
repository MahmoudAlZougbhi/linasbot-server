#!/usr/bin/env bash
# Production-only helper: store META_WEBHOOK_VERIFY_TOKEN and validate webhook.
# Does NOT enable META_SOCIAL_MESSAGING_ENABLED / customer messaging.
set -euo pipefail

if [ -z "${META_WEBHOOK_VERIFY_TOKEN:-}" ]; then
  echo "META_WEBHOOK_VERIFY_TOKEN is empty" >&2
  exit 1
fi

if [ -f /etc/nginx/sites-enabled/linasaibot ]; then
  NGINX_SITE=/etc/nginx/sites-enabled/linasaibot
elif [ -f /etc/nginx/sites-available/linasaibot ]; then
  NGINX_SITE=/etc/nginx/sites-available/linasaibot
else
  NGINX_SITE=""
fi

if [ -n "$NGINX_SITE" ]; then
  echo "[setup] Using nginx site: $NGINX_SITE"
  if grep -qE 'location[[:space:]]+\^~[[:space:]]+/webhook' "$NGINX_SITE"; then
    echo "[setup] ^~ /webhook already present"
  else
    echo "[setup] Hardening webhook location to ^~ /webhook"
    cp -a "$NGINX_SITE" "${NGINX_SITE}.bak.meta-webhook"
    sed -i -E 's/location[[:space:]]+=[[:space:]]+\/webhook/location ^~ \/webhook/; s/location[[:space:]]+\/webhook/location ^~ \/webhook/' "$NGINX_SITE"
  fi
  nginx -t
  systemctl reload nginx
else
  echo "[setup] WARNING: linasaibot nginx site not found"
fi

python3 - <<'PY'
import os
from pathlib import Path

token = os.environ["META_WEBHOOK_VERIFY_TOKEN"].strip()
if not token:
    raise SystemExit("empty META_WEBHOOK_VERIFY_TOKEN")

paths = [
    Path("/opt/linasbot/.env"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/.env"),
]

def upsert(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    out = []
    found = False
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")
    os.chmod(path, 0o600)
    print(f"[setup] upserted {key} in {path}")

for path in paths:
    if not path.parent.exists():
        print(f"[setup] skip missing dir for {path}")
        continue
    upsert(path, "META_WEBHOOK_VERIFY_TOKEN", token)
    text = path.read_text() if path.exists() else ""
    if "META_SOCIAL_MESSAGING_ENABLED=" in text:
        current = [
            line.split("=", 1)[1]
            for line in text.splitlines()
            if line.startswith("META_SOCIAL_MESSAGING_ENABLED=")
        ][-1]
        print(f"[setup] META_SOCIAL_MESSAGING_ENABLED remains: {current}")
    else:
        upsert(path, "META_SOCIAL_MESSAGING_ENABLED", "false")
PY

echo "[setup] Restarting linasbot to load verify token"
systemctl restart linasbot
sleep 6
systemctl is-active linasbot

CHALLENGE=meta_challenge_ok
CODE_OK="$(curl -sS -o /tmp/meta_ok_body -w '%{http_code}' --max-time 10 \
  "http://127.0.0.1:8003/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=${META_WEBHOOK_VERIFY_TOKEN}&hub.challenge=${CHALLENGE}" || true)"
BODY_OK="$(cat /tmp/meta_ok_body 2>/dev/null || true)"
echo "local_correct_http=$CODE_OK"
echo "local_correct_body=$BODY_OK"
test "$CODE_OK" = "200"
test "$BODY_OK" = "$CHALLENGE"

CODE_BAD="$(curl -sS -o /tmp/meta_bad_body -w '%{http_code}' --max-time 10 \
  "http://127.0.0.1:8003/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=wrong-token&hub.challenge=${CHALLENGE}" || true)"
echo "local_incorrect_http=$CODE_BAD"
test "$CODE_BAD" != "200"

PUB_BAD_CODE="$(curl -sS -D /tmp/meta_pub_headers -o /tmp/meta_pub_body --max-time 15 \
  "https://www.linasaibot.com/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=wrong-token&hub.challenge=${CHALLENGE}" \
  -w '%{http_code}' || true)"
echo "public_incorrect_http=$PUB_BAD_CODE"
grep -i '^content-type:' /tmp/meta_pub_headers | tr -d '\r' || true
if head -c 120 /tmp/meta_pub_body | grep -qi '<!doctype html'; then
  echo "Public endpoint still returning dashboard HTML" >&2
  exit 1
fi

PUB_OK_CODE="$(curl -sS -o /tmp/meta_pub_ok_body -w '%{http_code}' --max-time 15 \
  "https://www.linasaibot.com/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=${META_WEBHOOK_VERIFY_TOKEN}&hub.challenge=${CHALLENGE}" || true)"
PUB_OK_BODY="$(cat /tmp/meta_pub_ok_body 2>/dev/null || true)"
echo "public_correct_http=$PUB_OK_CODE"
echo "public_correct_body=$PUB_OK_BODY"
test "$PUB_OK_CODE" = "200"
test "$PUB_OK_BODY" = "$CHALLENGE"

WA_CODE="$(curl -sS -o /tmp/wa_body -w '%{http_code}' --max-time 10 https://www.linasaibot.com/webhook || true)"
echo "whatsapp_webhook_http=$WA_CODE"
if head -c 80 /tmp/wa_body | grep -qi '<!doctype html'; then
  echo "WhatsApp /webhook unexpectedly returned HTML" >&2
  exit 1
fi

echo "api_health=$(curl -sS --max-time 10 https://www.linasaibot.com/api/health || true)"
echo "[setup] SUCCESS"
echo "customer_messaging_not_enabled=true"
echo "whatsapp_preserved=true"
