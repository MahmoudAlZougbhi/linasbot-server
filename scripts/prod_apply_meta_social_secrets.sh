#!/usr/bin/env bash
# Apply Meta social-messaging secrets on production. Never prints secret values.
# Keeps META_SOCIAL_MESSAGING_ENABLED=false unless APPLY_ENABLE_MESSAGING=true AND readiness passes.
set -euo pipefail

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

if [ "$META_APP_ID" != "1784792718776344" ]; then
  echo "[meta-apply] refusing unexpected META_APP_ID" >&2
  exit 1
fi

python3 - <<'PY'
import os
from pathlib import Path

KEYS_ALWAYS = [
    "META_APP_ID",
    "META_APP_SECRET",
    "META_PAGE_ID",
    "META_PAGE_ACCESS_TOKEN",
    "META_INSTAGRAM_ACCOUNT_ID",
    "META_WEBHOOK_VERIFY_TOKEN",
    "META_GRAPH_API_VERSION",
]
OPTIONAL = []

def upsert(path: Path, updates: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    found = set()
    out = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                found.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in found:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")
    os.chmod(path, 0o600)

updates = {k: os.environ[k].strip() for k in KEYS_ALWAYS}
for key in OPTIONAL:
    value = (os.environ.get(key) or "").strip()
    if value:
        updates[key] = value

# Never auto-enable here unless explicitly requested after readiness.
enable_requested = (os.environ.get("APPLY_ENABLE_MESSAGING") or "").strip().lower() in {"1", "true", "yes"}
app_secret = (os.environ.get("META_APP_SECRET") or "").strip()
iga = (os.environ.get("META_INSTAGRAM_ACCOUNT_ID") or "").strip()
ready = bool(app_secret and iga and updates.get("META_PAGE_ACCESS_TOKEN"))

if enable_requested and ready:
    updates["META_SOCIAL_MESSAGING_ENABLED"] = "true"
else:
    updates["META_SOCIAL_MESSAGING_ENABLED"] = "false"

paths = [Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")]
for path in paths:
    if not path.parent.exists():
        print(f"[meta-apply] skip missing dir for {path}")
        continue
    upsert(path, updates)
    text = path.read_text()
    def present(key: str) -> bool:
        return any(line.startswith(key + "=") and line.split("=", 1)[1].strip() for line in text.splitlines())
    print(f"[meta-apply] updated={path}")
    for key in [
        "META_APP_ID",
        "META_APP_SECRET",
        "META_PAGE_ID",
        "META_PAGE_ACCESS_TOKEN",
        "META_INSTAGRAM_ACCOUNT_ID",
        "META_WEBHOOK_VERIFY_TOKEN",
        "META_GRAPH_API_VERSION",
        "META_SOCIAL_MESSAGING_ENABLED",
    ]:
        print(f"[meta-apply] {key}:present={present(key)}")

print(f"[meta-apply] readiness_app_secret={bool(app_secret)}")
print(f"[meta-apply] readiness_instagram_account_id={bool(iga)}")
print(f"[meta-apply] readiness_complete={ready}")
print(f"[meta-apply] messaging_enabled={updates['META_SOCIAL_MESSAGING_ENABLED']}")
if enable_requested and not ready:
    print("[meta-apply] enable requested but readiness incomplete; left disabled")
PY

# Nginx: keep ^~ /webhook
if [ -f /etc/nginx/sites-enabled/linasaibot ]; then
  NGINX_SITE=/etc/nginx/sites-enabled/linasaibot
elif [ -f /etc/nginx/sites-available/linasaibot ]; then
  NGINX_SITE=/etc/nginx/sites-available/linasaibot
else
  NGINX_SITE=""
fi

if [ -n "$NGINX_SITE" ]; then
  if ! grep -qE 'location[[:space:]]+\^~[[:space:]]+/webhook' "$NGINX_SITE"; then
    cp -a "$NGINX_SITE" "${NGINX_SITE}.bak.meta-social"
    sed -i -E 's/location[[:space:]]+=[[:space:]]+\/webhook/location ^~ \/webhook/; s/location[[:space:]]+\/webhook/location ^~ \/webhook/' "$NGINX_SITE"
  fi
  nginx -t
  systemctl reload nginx
  echo "[meta-apply] nginx_ok=true"
else
  echo "[meta-apply] nginx_ok=false"
  exit 1
fi

systemctl restart linasbot
sleep 5
systemctl is-active linasbot

CHALLENGE=meta_apply_challenge
CODE_OK="$(curl -sS -o /tmp/meta_ok_body -w '%{http_code}' --max-time 10 \
  "http://127.0.0.1:8003/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=${META_WEBHOOK_VERIFY_TOKEN}&hub.challenge=${CHALLENGE}" || true)"
BODY_OK="$(cat /tmp/meta_ok_body 2>/dev/null || true)"
echo "local_correct_http=$CODE_OK"
test "$CODE_OK" = "200"
test "$BODY_OK" = "$CHALLENGE"

CODE_BAD="$(curl -sS -o /tmp/meta_bad_body -w '%{http_code}' --max-time 10 \
  "http://127.0.0.1:8003/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=wrong-token&hub.challenge=${CHALLENGE}" || true)"
echo "local_incorrect_http=$CODE_BAD"
test "$CODE_BAD" != "200"

# Invalid signature POST must be rejected whenever App Secret is configured.
POST_CODE="$(curl -sS -o /tmp/meta_post_body -w '%{http_code}' --max-time 10 \
  -X POST "http://127.0.0.1:8003/webhook/meta-messaging" \
  -H 'Content-Type: application/json' \
  -H 'X-Hub-Signature-256: sha256=deadbeef' \
  -d '{"object":"page","entry":[]}' || true)"
POST_BODY="$(cat /tmp/meta_post_body 2>/dev/null || true)"
echo "local_invalid_sig_http=$POST_CODE"
echo "local_invalid_sig_body=$POST_BODY"
test "$POST_CODE" = "401"

# Existing WhatsApp provider webhook must not invoke AI.
WA_CODE="$(curl -sS -o /tmp/wa_inbound_body -w '%{http_code}' --max-time 10 \
  -X POST "http://127.0.0.1:8003/webhook" \
  -H 'Content-Type: application/json' \
  -d '{"object":"whatsapp_business_account","entry":[]}' || true)"
WA_BODY="$(cat /tmp/wa_inbound_body 2>/dev/null || true)"
echo "local_whatsapp_inbound_http=$WA_CODE"
echo "local_whatsapp_inbound_body=$WA_BODY"
test "$WA_CODE" = "200"
printf '%s' "$WA_BODY" | grep -q 'whatsapp_inbound_ai_disabled'

PUB_OK="$(curl -sS -o /tmp/pub_ok -w '%{http_code}' --max-time 15 \
  "https://www.linasaibot.com/webhook/meta-messaging?hub.mode=subscribe&hub.verify_token=${META_WEBHOOK_VERIFY_TOKEN}&hub.challenge=${CHALLENGE}" || true)"
echo "public_correct_http=$PUB_OK"
test "$PUB_OK" = "200"
test "$(cat /tmp/pub_ok)" = "$CHALLENGE"

if head -c 80 /tmp/pub_ok | grep -qi '<!doctype html'; then
  echo "public still HTML" >&2
  exit 1
fi

echo "api_health=$(curl -sS --max-time 10 https://www.linasaibot.com/api/health || true)"
echo "[meta-apply] SUCCESS"
