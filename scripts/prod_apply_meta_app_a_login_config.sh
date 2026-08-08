#!/usr/bin/env bash
# Apply App A Facebook Login for Business configuration only.
# Does not re-seed bindings, disconnect accounts, or rotate Page tokens.
set -euo pipefail

LOGIN_CONFIG_ID="${META_APP_A_LOGIN_CONFIG_ID:-}"
if [ -z "$LOGIN_CONFIG_ID" ]; then
  echo "[meta-login-config] META_APP_A_LOGIN_CONFIG_ID is required" >&2
  exit 1
fi
if ! [[ "$LOGIN_CONFIG_ID" =~ ^[0-9]{8,32}$ ]]; then
  echo "[meta-login-config] META_APP_A_LOGIN_CONFIG_ID format is invalid" >&2
  exit 1
fi

REDIRECT_URI="${META_OAUTH_REDIRECT_URI:-https://www.linasaibot.com/oauth/meta/callback}"
if [ "$REDIRECT_URI" != "https://www.linasaibot.com/oauth/meta/callback" ]; then
  echo "[meta-login-config] refusing unexpected redirect URI" >&2
  exit 1
fi

umask 077
python3 - <<'PY'
import os
from pathlib import Path

login_config_id = os.environ["META_APP_A_LOGIN_CONFIG_ID"].strip()
redirect_uri = os.environ.get("META_OAUTH_REDIRECT_URI", "https://www.linasaibot.com/oauth/meta/callback").strip()
updates = {
    "META_APP_A_LOGIN_CONFIG_ID": login_config_id,
    "META_OAUTH_REDIRECT_URI": redirect_uri,
}

def upsert(path: Path) -> None:
    if not path.parent.exists():
        return
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
    path.chmod(0o600)
    print(f"[meta-login-config] environment_updated={path}")

for candidate in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    upsert(candidate)
PY

systemctl restart linasbot
sleep 5
systemctl is-active --quiet linasbot

APP_DIR="/opt/linasbot"
if [ -f /opt/linasbot/linaslaserbot-2.7.22/main.py ]; then
  APP_DIR="/opt/linasbot/linaslaserbot-2.7.22"
fi
cd "$APP_DIR"
if [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
python3 - <<'PY'
import os

from urllib.parse import parse_qs, urlparse

from services.meta_app_registry import APP_A_KEY, get_meta_app_configs
from services.meta_oauth import begin_meta_business_login, meta_oauth_redirect_uri

app = get_meta_app_configs()[APP_A_KEY]
if not app.enabled:
    raise SystemExit("App A is not enabled")
if app.oauth_config_id != os.environ["META_APP_A_LOGIN_CONFIG_ID"].strip():
    raise SystemExit("App A login config id mismatch after apply")
redirect = meta_oauth_redirect_uri()
if redirect != "https://www.linasaibot.com/oauth/meta/callback":
    raise SystemExit("redirect URI mismatch")
url = begin_meta_business_login(tenant_id="linas", channel="facebook", actor_id="login-config-verify")
query = parse_qs(urlparse(url).query)
if query.get("client_id") != ["2963733803971681"]:
    raise SystemExit("OAuth URL missing App A client_id")
if query.get("config_id") != [app.oauth_config_id]:
    raise SystemExit("OAuth URL missing config_id")
if query.get("redirect_uri") != [redirect]:
    raise SystemExit("OAuth URL missing redirect_uri")
if not query.get("state"):
    raise SystemExit("OAuth URL missing state nonce")
print("[meta-login-config] oauth_url_shape_ok=true")
print(f"[meta-login-config] redirect_uri={redirect}")
print("[meta-login-config] SUCCESS")
PY
