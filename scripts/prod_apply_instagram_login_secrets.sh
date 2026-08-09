#!/usr/bin/env bash
# Apply Instagram Direct Login secrets on production. Never prints secret values.
set -euo pipefail

if [ -z "${META_INSTAGRAM_LOGIN_APP_SECRET:-}" ]; then
  echo "[instagram-login-apply] missing required env: META_INSTAGRAM_LOGIN_APP_SECRET" >&2
  exit 1
fi

if [ "${#META_INSTAGRAM_LOGIN_APP_SECRET}" -lt 16 ]; then
  echo "[instagram-login-apply] refusing META_INSTAGRAM_LOGIN_APP_SECRET: length_too_short" >&2
  exit 1
fi

export META_INSTAGRAM_LOGIN_APP_SECRET
export META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN

python3 - <<'PY'
import hmac
import os
import secrets
from pathlib import Path

APP_SECRET_KEY = "META_INSTAGRAM_LOGIN_APP_SECRET"
VERIFY_KEY = "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN"
APP_ID_KEY = "META_INSTAGRAM_LOGIN_APP_ID"
DEFAULT_APP_ID = "1035856539045307"

app_secret = os.environ[APP_SECRET_KEY].strip()
if not app_secret:
    raise SystemExit("[instagram-login-apply] empty app secret")
verify_token = (os.environ.get(VERIFY_KEY) or "").strip()
generated_verify = False
if not verify_token:
    verify_token = secrets.token_urlsafe(32)
    generated_verify = True
if len(verify_token) < 16:
    raise SystemExit("[instagram-login-apply] verify token too short")

updates = {
    APP_ID_KEY: DEFAULT_APP_ID,
    APP_SECRET_KEY: app_secret,
    VERIFY_KEY: verify_token,
}


def upsert(path: Path, values: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    found: set[str] = set()
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in values:
                out.append(f"{key}={values[key]}")
                found.add(key)
                continue
        out.append(line)
    for key, value in values.items():
        if key not in found:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")
    os.chmod(path, 0o600)


paths = [Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")]
updated = 0
for path in paths:
    if not path.parent.exists():
        print(f"[instagram-login-apply] skip missing dir for {path}")
        continue
    upsert(path, updates)
    text = path.read_text()
    file_secret = ""
    file_verify = ""
    for line in text.splitlines():
        if line.startswith(APP_SECRET_KEY + "="):
            file_secret = line.split("=", 1)[1].strip()
        if line.startswith(VERIFY_KEY + "="):
            file_verify = line.split("=", 1)[1].strip()
    print(f"[instagram-login-apply] updated={path}")
    print(f"[instagram-login-apply] app_secret_present={bool(file_secret)}")
    print(
        f"[instagram-login-apply] app_secret_match={hmac.compare_digest(file_secret, app_secret)}"
    )
    print(f"[instagram-login-apply] verify_token_present={bool(file_verify)}")
    print(
        f"[instagram-login-apply] verify_token_match={hmac.compare_digest(file_verify, verify_token)}"
    )
    if not file_secret or not hmac.compare_digest(file_secret, app_secret):
        raise SystemExit(f"[instagram-login-apply] app secret verify failed for {path}")
    if not file_verify or not hmac.compare_digest(file_verify, verify_token):
        raise SystemExit(f"[instagram-login-apply] verify token verify failed for {path}")
    updated += 1

if updated < 1:
    raise SystemExit("[instagram-login-apply] no .env paths updated")

if generated_verify:
    note = Path("/root/.linasbot-instagram-login-verify-token-once")
    note.write_text(
        "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN for Meta Developer webhook setup.\n"
        "Read once on the server, configure Meta, then delete this file.\n"
        f"{VERIFY_KEY}={verify_token}\n",
        encoding="utf-8",
    )
    os.chmod(note, 0o600)
    print(f"[instagram-login-apply] generated_verify_token=true note_path={note}")
else:
    print("[instagram-login-apply] generated_verify_token=false")

print("[instagram-login-apply] secrets_validated=true")
PY

systemctl restart linasbot
sleep 6
systemctl is-active linasbot

python3 - <<'PY'
import os
import urllib.error
import urllib.parse
import urllib.request

wrong = "instagram_login_probe_wrong_token"
challenge = "instagram_login_probe_challenge"
query = urllib.parse.urlencode(
    {
        "hub.mode": "subscribe",
        "hub.verify_token": wrong,
        "hub.challenge": challenge,
    }
)
url = f"http://127.0.0.1:8003/webhook/instagram-login?{query}"
try:
    with urllib.request.urlopen(url, timeout=15) as response:
        code = response.status
except urllib.error.HTTPError as exc:
    code = exc.code
else:
    code = 200
print(f"[instagram-login-apply] local_webhook_probe_http={code}")
if code == 503:
    raise SystemExit("[instagram-login-apply] webhook still not configured (503)")
if code != 403:
    raise SystemExit(f"[instagram-login-apply] unexpected webhook probe status {code}")
print("[instagram-login-apply] SUCCESS")
PY
