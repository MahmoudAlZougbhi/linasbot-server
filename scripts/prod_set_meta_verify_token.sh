#!/usr/bin/env bash
# Production-only helper: store META_WEBHOOK_VERIFY_TOKEN and validate webhook.
# Does NOT enable META_SOCIAL_MESSAGING_ENABLED / customer messaging.
set -euo pipefail

if [ -z "${META_WEBHOOK_VERIFY_TOKEN:-}" ]; then
  echo "META_WEBHOOK_VERIFY_TOKEN is empty" >&2
  exit 1
fi

umask 077
TOKEN_PATTERN_FILE="$(mktemp /tmp/linasbot-meta-token-pattern.XXXXXX)"
NGINX_DUMP_FILE="$(mktemp /tmp/linasbot-nginx-config.XXXXXX)"
trap 'rm -f "$TOKEN_PATTERN_FILE" "$NGINX_DUMP_FILE"' EXIT

token_pattern_present_in_logs() {
  local log_path
  while IFS= read -r log_path; do
    if grep -qFf "$TOKEN_PATTERN_FILE" "$log_path" 2>/dev/null; then
      return 0
    fi
  done < <(
    find /var/log/nginx /var/log -maxdepth 2 -type f \
      \( -name '*linasaibot*.log*' -o -name 'access.log*' -o -name 'error.log*' \) 2>/dev/null
  )
  if command -v journalctl >/dev/null 2>&1 && \
    journalctl -u linasbot --no-pager 2>/dev/null | grep -qFf "$TOKEN_PATTERN_FILE"; then
    return 0
  fi
  return 1
}

# Read the retired value in memory only so historical-log exposure can be
# reported as a boolean before replacement. Never print or pass it in argv.
OLD_META_WEBHOOK_VERIFY_TOKEN=""
for ENV_PATH in /opt/linasbot/.env /opt/linasbot/linaslaserbot-2.7.22/.env; do
  if [ -f "$ENV_PATH" ]; then
    while IFS='=' read -r ENV_KEY ENV_VALUE; do
      if [ "$ENV_KEY" = "META_WEBHOOK_VERIFY_TOKEN" ]; then
        OLD_META_WEBHOOK_VERIFY_TOKEN="$ENV_VALUE"
      fi
    done < "$ENV_PATH"
  fi
done

if [ -n "$OLD_META_WEBHOOK_VERIFY_TOKEN" ]; then
  printf '%s' "$OLD_META_WEBHOOK_VERIFY_TOKEN" > "$TOKEN_PATTERN_FILE"
  if token_pattern_present_in_logs; then
    echo "historical_retired_token_present_in_logs=true"
  else
    echo "historical_retired_token_present_in_logs=false"
  fi
fi
OLD_META_WEBHOOK_VERIFY_TOKEN=""
: > "$TOKEN_PATTERN_FILE"

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
  nginx -T > "$NGINX_DUMP_FILE" 2>&1
  grep -q 'log_format linasbot_safe' "$NGINX_DUMP_FILE"
  grep -q 'access_log off;' "$NGINX_DUMP_FILE"
  grep -q 'linasaibot-sensitive.error.log crit;' "$NGINX_DUMP_FILE"
  grep -Eq 'request_method.*uri.*server_protocol' "$NGINX_DUMP_FILE"
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

python3 - <<'PY'
import os
import urllib.error
import urllib.parse
import urllib.request

challenge = "meta_challenge_ok"
token = os.environ["META_WEBHOOK_VERIFY_TOKEN"]

def call(base: str, supplied_token: str) -> tuple[int, str, str]:
    query = urllib.parse.urlencode(
        {
            "hub.mode": "subscribe",
            "hub.verify_token": supplied_token,
            "hub.challenge": challenge,
        }
    )
    request = urllib.request.Request(f"{base}?{query}")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(4096).decode("utf-8", "replace"), response.headers.get_content_type()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096).decode("utf-8", "replace"), exc.headers.get_content_type()

local_ok = call("http://127.0.0.1:8003/webhook/meta-messaging", token)
local_bad = call("http://127.0.0.1:8003/webhook/meta-messaging", "wrong-token")
public_ok = call("https://www.linasaibot.com/webhook/meta-messaging", token)
public_bad = call("https://www.linasaibot.com/webhook/meta-messaging", "wrong-token")

print(f"local_correct_http={local_ok[0]}")
print(f"local_incorrect_http={local_bad[0]}")
print(f"public_correct_http={public_ok[0]}")
print(f"public_incorrect_http={public_bad[0]}")
if local_ok[:2] != (200, challenge):
    raise SystemExit("local correct-token challenge failed")
if public_ok[:2] != (200, challenge):
    raise SystemExit("public correct-token challenge failed")
if local_bad[0] != 403 or public_bad[0] != 403:
    raise SystemExit("wrong-token challenge did not return 403")
if "<!doctype html" in public_bad[1].lower():
    raise SystemExit("public endpoint returned dashboard HTML")
PY

printf '%s' "$META_WEBHOOK_VERIFY_TOKEN" > "$TOKEN_PATTERN_FILE"
if token_pattern_present_in_logs; then
  echo "new_verify_token_present_in_logs=true" >&2
  exit 1
fi
echo "new_verify_token_present_in_logs=false"
: > "$TOKEN_PATTERN_FILE"

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
