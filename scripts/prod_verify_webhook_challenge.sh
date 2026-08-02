#!/usr/bin/env bash
# Verify webhook challenges without placing tokens in argv, output, or logs.
set -euo pipefail
umask 077

MARKER_FILE="$(mktemp /tmp/linas-webhook-log-marker.XXXXXX)"
NGINX_DUMP="$(mktemp /tmp/linas-nginx-dump.XXXXXX)"
START_EPOCH="$(date +%s)"
trap 'rm -f "$MARKER_FILE" "$NGINX_DUMP"' EXIT

MARKER_FILE="$MARKER_FILE" python3 - <<'PY'
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (
        Path("/opt/linasbot/.env"),
        Path("/opt/linasbot/linaslaserbot-2.7.22/.env"),
    ):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def call(base: str, token: str, challenge: str) -> tuple[int, str]:
    query = urllib.parse.urlencode(
        {
            "hub.mode": "subscribe",
            "hub.verify_token": token,
            "hub.challenge": challenge,
        }
    )
    request = urllib.request.Request(f"{base}?{query}")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096).decode("utf-8", "replace")


values = read_env()
meta_token = values.get("META_WEBHOOK_VERIFY_TOKEN", "")
if not meta_token:
    raise SystemExit("[webhook-verify] missing META_WEBHOOK_VERIFY_TOKEN")

challenge = "meta-" + secrets.token_urlsafe(18)
wrong_marker = "reject-" + secrets.token_urlsafe(32)
marker_path = Path(os.environ["MARKER_FILE"])
marker_path.write_text(wrong_marker, encoding="utf-8")
os.chmod(marker_path, 0o600)

for label, base in (
    ("local", "http://127.0.0.1:8003/webhook/meta-messaging"),
    ("public", "https://www.linasaibot.com/webhook/meta-messaging"),
):
    good = call(base, meta_token, challenge)
    bad = call(base, wrong_marker, challenge)
    print(f"[webhook-verify] meta_{label}_good_http={good[0]}")
    print(f"[webhook-verify] meta_{label}_bad_http={bad[0]}")
    if good != (200, challenge):
        raise SystemExit(f"[webhook-verify] {label} correct-token challenge failed")
    if bad[0] != 403:
        raise SystemExit(f"[webhook-verify] {label} wrong-token challenge did not return 403")

wa_token = values.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
if wa_token and wa_token != "YOUR_SECURE_VERIFY_TOKEN":
    wa_challenge = str(secrets.randbelow(900_000_000) + 100_000_000)
    good = call("http://127.0.0.1:8003/webhook", wa_token, wa_challenge)
    bad = call("http://127.0.0.1:8003/webhook", wrong_marker, wa_challenge)
    print(f"[webhook-verify] wa_local_good_http={good[0]}")
    print(f"[webhook-verify] wa_local_bad_http={bad[0]}")
    if good != (200, wa_challenge) or bad[0] != 403:
        raise SystemExit("[webhook-verify] WhatsApp challenge verification failed")
else:
    print("[webhook-verify] wa_verify_token_configured=false skipped=true")
PY

# Fail if the unique probe appears anywhere it could have been persisted.
while IFS= read -r log_path; do
  if grep -qFf "$MARKER_FILE" "$log_path" 2>/dev/null; then
    echo "[webhook-verify] sensitive_probe_present_in_file_logs=true" >&2
    exit 1
  fi
done < <(
  find /var/log/nginx /var/log -maxdepth 2 -type f \
    \( -name '*linasaibot*.log*' -o -name 'access.log*' -o -name 'error.log*' \) \
    2>/dev/null
)
if command -v journalctl >/dev/null 2>&1 && \
  journalctl -u linasbot --since "@$START_EPOCH" --no-pager 2>/dev/null | grep -qFf "$MARKER_FILE"; then
  echo "[webhook-verify] sensitive_probe_present_in_backend_journal=true" >&2
  exit 1
fi
echo "[webhook-verify] sensitive_probe_present_in_logs=false"

if command -v nginx >/dev/null 2>&1; then
  nginx -t
  nginx -T > "$NGINX_DUMP" 2>&1
  grep -q 'log_format linasbot_safe' "$NGINX_DUMP"
  grep -q 'access_log off;' "$NGINX_DUMP"
  grep -q 'linasaibot-sensitive.error.log crit;' "$NGINX_DUMP"
  echo "[webhook-verify] nginx_query_log_hardening=true"
fi

echo "[webhook-verify] SUCCESS"
