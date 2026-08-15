#!/usr/bin/env bash
# Apply stable DASHBOARD_AUTH_SECRET + ENVIRONMENT=production.
# Never prints secret values. Never auto-generates a secret (caller must supply).
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_apply_dashboard_auth.sh"

if [ -z "${DASHBOARD_AUTH_SECRET:-}" ]; then
  echo "[dashboard-auth-apply] missing required env: DASHBOARD_AUTH_SECRET" >&2
  exit 1
fi

SECRET_LEN="${#DASHBOARD_AUTH_SECRET}"
if [ "$SECRET_LEN" -lt 32 ]; then
  echo "[dashboard-auth-apply] refusing DASHBOARD_AUTH_SECRET: length_too_short" >&2
  exit 1
fi

PYTHONPATH=/opt/linasbot /opt/linasbot/venv/bin/python - <<'PY'
import hmac
import os
import re
from pathlib import Path

from scripts.ha.production_env_cas import atomic_update_canonical_env

KEY = "DASHBOARD_AUTH_SECRET"
ENV_KEY = "ENVIRONMENT"
value = os.environ[KEY].strip()
if not value:
    raise SystemExit(f"[dashboard-auth-apply] empty {KEY}")
if len(value) < 32:
    raise SystemExit(f"[dashboard-auth-apply] refusing {KEY}: length_too_short")
classes = sum(
    [
        bool(re.search(r"[a-z]", value)),
        bool(re.search(r"[A-Z]", value)),
        bool(re.search(r"[0-9]", value)),
        bool(re.search(r"[^A-Za-z0-9]", value)),
    ]
)
if classes < 2:
    raise SystemExit(f"[dashboard-auth-apply] refusing {KEY}: weak_charset")

updates = {KEY: value, ENV_KEY: "production"}
path = Path("/opt/linasbot/.env")
atomic_update_canonical_env(updates)
mapping = {}
for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, raw = line.split("=", 1)
        mapping.setdefault(key.strip(), []).append(raw)
if (
    len(mapping.get(KEY, [])) != 1
    or not hmac.compare_digest(mapping[KEY][0], value)
    or mapping.get(ENV_KEY) != ["production"]
):
    raise SystemExit("[dashboard-auth-apply] canonical environment verification failed")
print("[dashboard-auth-apply] canonical_env_updated=true secret_match=true")
print("[dashboard-auth-apply] secret_validated=true")
print("[dashboard-auth-apply] environment=production")
PY

systemctl restart linasbot
sleep 6
systemctl is-active linasbot

/opt/linasbot/venv/bin/python - <<'PY'
import hmac
import subprocess
from pathlib import Path

KEY = "DASHBOARD_AUTH_SECRET"
ENV_KEY = "ENVIRONMENT"
expected = None
for line in Path("/opt/linasbot/.env").read_text(encoding="utf-8", errors="strict").splitlines():
    if line.startswith(KEY + "="):
        expected = line.split("=", 1)[1]
        break
if not expected:
    raise SystemExit("[dashboard-auth-apply] could not read expected secret from .env")

pid = subprocess.check_output(["systemctl", "show", "-p", "MainPID", "--value", "linasbot"], text=True).strip()
if not pid or pid == "0":
    raise SystemExit("[dashboard-auth-apply] linasbot MainPID unavailable")
environ_path = Path(f"/proc/{pid}/environ")
env_map = {}
for item in environ_path.read_bytes().split(b"\0"):
    if b"=" in item:
        k, v = item.split(b"=", 1)
        env_map[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
loaded = env_map.get(KEY, "")
env_val = (env_map.get(ENV_KEY) or env_map.get("ENV") or "").strip().lower()
if not loaded:
    raise SystemExit("[dashboard-auth-apply] running process missing DASHBOARD_AUTH_SECRET")
if env_val != "production":
    raise SystemExit(f"[dashboard-auth-apply] running process ENVIRONMENT not production (got_marker_set={bool(env_val)})")
print(f"[dashboard-auth-apply] process_pid={pid}")
print(f"[dashboard-auth-apply] process_secret_present=true")
print(f"[dashboard-auth-apply] process_secret_match={hmac.compare_digest(expected, loaded)}")
print(f"[dashboard-auth-apply] process_environment_production=true")
if not hmac.compare_digest(expected, loaded):
    raise SystemExit("[dashboard-auth-apply] running process secret fingerprint mismatch")
PY

echo "api_health=$(curl -sS --max-time 10 https://www.linasaibot.com/api/health || true)"
echo "[dashboard-auth-apply] SUCCESS"
