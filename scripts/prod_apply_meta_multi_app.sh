#!/usr/bin/env bash
# Stage/enable the encrypted two-app registry without printing any credential.
set -euo pipefail

required=(
  META_APP_ID
  META_APP_SECRET
  META_PAGE_ID
  META_PAGE_ACCESS_TOKEN
  META_INSTAGRAM_ACCOUNT_ID
  META_WEBHOOK_VERIFY_TOKEN
  META_GRAPH_API_VERSION
  META_CREDENTIAL_ENCRYPTION_KEY
)
for key in "${required[@]}"; do
  if [ -z "${!key:-}" ]; then
    echo "[meta-multi-app] missing required environment variable: $key" >&2
    exit 1
  fi
done

if [ "$META_APP_ID" != "2963733803971681" ]; then
  echo "[meta-multi-app] refusing unexpected App A ID" >&2
  exit 1
fi
if [ "$META_PAGE_ID" != "378696005334409" ] || [ "$META_INSTAGRAM_ACCOUNT_ID" != "17841413184256533" ]; then
  echo "[meta-multi-app] refusing unexpected Lina asset identity" >&2
  exit 1
fi
if [ "$META_GRAPH_API_VERSION" != "v24.0" ]; then
  echo "[meta-multi-app] refusing unexpected Graph API version" >&2
  exit 1
fi
if [ "${#META_CREDENTIAL_ENCRYPTION_KEY}" -lt 32 ]; then
  echo "[meta-multi-app] credential encryption key is too short" >&2
  exit 1
fi

app_b_present=0
app_b_missing=0
for key in META_APP_B_ID META_APP_B_SECRET META_APP_B_WEBHOOK_VERIFY_TOKEN META_APP_B_LOGIN_CONFIG_ID; do
  if [ -n "${!key:-}" ]; then
    app_b_present=$((app_b_present + 1))
  else
    app_b_missing=$((app_b_missing + 1))
  fi
done
if [ "$app_b_present" -gt 0 ] && [ "$app_b_missing" -gt 0 ]; then
  echo "[meta-multi-app] App B configuration is partial; refusing apply" >&2
  exit 1
fi

umask 077
PATTERN_FILE="$(mktemp /tmp/linasbot-meta-multi-pattern.XXXXXX)"
trap 'rm -f "$PATTERN_FILE"' EXIT

python3 - <<'PY'
import os
from pathlib import Path

required = {
    "META_APP_ID": os.environ["META_APP_ID"].strip(),
    "META_APP_SECRET": os.environ["META_APP_SECRET"].strip(),
    "META_PAGE_ID": os.environ["META_PAGE_ID"].strip(),
    "META_PAGE_ACCESS_TOKEN": os.environ["META_PAGE_ACCESS_TOKEN"].strip(),
    "META_INSTAGRAM_ACCOUNT_ID": os.environ["META_INSTAGRAM_ACCOUNT_ID"].strip(),
    "META_WEBHOOK_VERIFY_TOKEN": os.environ["META_WEBHOOK_VERIFY_TOKEN"].strip(),
    "META_GRAPH_API_VERSION": os.environ["META_GRAPH_API_VERSION"].strip(),
    "META_CREDENTIAL_ENCRYPTION_KEY": os.environ["META_CREDENTIAL_ENCRYPTION_KEY"].strip(),
}
updates = dict(required)
updates.update(
    {
        "META_APP_A_ID": required["META_APP_ID"],
        "META_APP_A_SECRET": required["META_APP_SECRET"],
        "META_APP_A_WEBHOOK_VERIFY_TOKEN": required["META_WEBHOOK_VERIFY_TOKEN"],
        "META_APP_A_ADVANCED_ACCESS_APPROVED": (os.getenv("META_APP_A_ADVANCED_ACCESS_APPROVED") or "false").strip(),
        "META_OAUTH_REDIRECT_URI": "https://www.linasaibot.com/oauth/meta/callback",
        "META_MULTI_APP_REGISTRY_ENABLED": "false",
        "META_APP_B_ADVANCED_ACCESS_APPROVED": (os.getenv("META_APP_B_ADVANCED_ACCESS_APPROVED") or "false").strip(),
        "META_APP_B_LINAS_CUTOVER_APPROVED": "false",
    }
)
for key in (
    "META_APP_A_LOGIN_CONFIG_ID",
    "META_APP_B_ID",
    "META_APP_B_SECRET",
    "META_APP_B_WEBHOOK_VERIFY_TOKEN",
    "META_APP_B_LOGIN_CONFIG_ID",
):
    value = (os.getenv(key) or "").strip()
    if value:
        updates[key] = value

def upsert(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found: set[str] = set()
    output: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                found.add(key)
                continue
        output.append(line)
    for key, value in updates.items():
        if key not in found:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"[meta-multi-app] environment_updated={path}")

for candidate in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if candidate.parent.exists():
        upsert(candidate)
PY

systemctl restart linasbot
sleep 5
systemctl is-active --quiet linasbot
echo "[meta-multi-app] legacy_router_healthy=true"

APP_DIR="/opt/linasbot"
if [ -f /opt/linasbot/linaslaserbot-2.7.22/main.py ]; then
  APP_DIR="/opt/linasbot/linaslaserbot-2.7.22"
fi
if [ ! -f "$APP_DIR/main.py" ]; then
  echo "[meta-multi-app] application directory unavailable" >&2
  exit 1
fi

REGISTRY_DIR="/opt/linasbot_data/meta_registry"
if [ -f "$REGISTRY_DIR/registry.json" ]; then
  BACKUP_DIR="$REGISTRY_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$BACKUP_DIR"
  cp -p "$REGISTRY_DIR/registry.json" "$BACKUP_DIR/registry.json"
  if [ -f "$REGISTRY_DIR/audit.jsonl" ]; then
    cp -p "$REGISTRY_DIR/audit.jsonl" "$BACKUP_DIR/audit.jsonl"
  fi
  chmod -R go-rwx "$BACKUP_DIR"
  echo "[meta-multi-app] encrypted_registry_backup_created=true"
fi

cd "$APP_DIR"
if [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
python3 -m scripts.seed_meta_app_a_registry

enable_requested="${APPLY_META_MULTI_APP_REGISTRY_ENABLED:-false}"
if [ "$enable_requested" = "true" ]; then
  python3 - <<'PY'
from pathlib import Path

for path in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if not path.exists():
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = []
    found = False
    for line in lines:
        if line.startswith("META_MULTI_APP_REGISTRY_ENABLED="):
            updated.append("META_MULTI_APP_REGISTRY_ENABLED=true")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append("META_MULTI_APP_REGISTRY_ENABLED=true")
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    path.chmod(0o600)
PY
  systemctl restart linasbot
  sleep 5
  if ! systemctl is-active --quiet linasbot; then
    echo "[meta-multi-app] registry service activation failed; restoring legacy router" >&2
    enable_requested="rollback"
  else
    if ! python3 - <<'PY'
import json
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=15) as response:
        payload = json.loads(response.read(100000))
except Exception:
    raise SystemExit(1)
if payload.get("ok") is not True:
    raise SystemExit(1)
print("[meta-multi-app] api_ready=true")
PY
    then
      echo "[meta-multi-app] registry readiness failed; restoring legacy router" >&2
      enable_requested="rollback"
    fi
  fi
fi

if [ "$enable_requested" = "rollback" ]; then
  python3 - <<'PY'
from pathlib import Path

for path in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    text = text.replace("META_MULTI_APP_REGISTRY_ENABLED=true", "META_MULTI_APP_REGISTRY_ENABLED=false")
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
PY
  systemctl restart linasbot
  sleep 5
  systemctl is-active --quiet linasbot
  exit 1
fi

python3 - <<'PY'
import os
import urllib.error
import urllib.parse
import urllib.request

tokens = [os.environ["META_WEBHOOK_VERIFY_TOKEN"]]
app_b_token = (os.getenv("META_APP_B_WEBHOOK_VERIFY_TOKEN") or "").strip()
if app_b_token:
    tokens.append(app_b_token)

def request(token: str) -> int:
    query = urllib.parse.urlencode(
        {"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "multi_app_challenge"}
    )
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:8003/webhook/meta-messaging?{query}", timeout=15
        ) as response:
            body = response.read(4096).decode("utf-8", "replace")
            if body != "multi_app_challenge":
                raise SystemExit("webhook challenge mismatch")
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code

for token in tokens:
    if request(token) != 200:
        raise SystemExit("configured webhook verification token failed")
if request("definitely-wrong-token") != 403:
    raise SystemExit("wrong webhook verification token was not rejected")
print(f"[meta-multi-app] verified_webhook_tokens={len(tokens)}")
print("[meta-multi-app] wrong_webhook_token_http=403")
PY

{
  printf '%s\n' "$META_WEBHOOK_VERIFY_TOKEN"
  if [ -n "${META_APP_B_WEBHOOK_VERIFY_TOKEN:-}" ]; then
    printf '%s\n' "$META_APP_B_WEBHOOK_VERIFY_TOKEN"
  fi
} > "$PATTERN_FILE"
if grep -qFf "$PATTERN_FILE" /var/log/nginx/*linasaibot*.log* 2>/dev/null; then
  echo "[meta-multi-app] verification credential appeared in Nginx logs" >&2
  exit 1
fi
if journalctl -u linasbot --no-pager 2>/dev/null | grep -qFf "$PATTERN_FILE"; then
  echo "[meta-multi-app] verification credential appeared in service logs" >&2
  exit 1
fi
: > "$PATTERN_FILE"
echo "[meta-multi-app] sensitive_credentials_in_logs=false"
echo "[meta-multi-app] registry_enabled=$([ "$enable_requested" = "true" ] && echo true || echo false)"
echo "[meta-multi-app] SUCCESS"
