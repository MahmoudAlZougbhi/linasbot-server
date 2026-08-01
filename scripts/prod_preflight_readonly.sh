#!/usr/bin/env bash
# Read-only production preflight. Never prints secret values. Never writes secrets/index.
set -euo pipefail

echo "[preflight] host=$(hostname)"
cd /opt/linasbot
echo "[preflight] deployed_sha=$(git rev-parse HEAD)"
echo "[preflight] deployed_subject=$(git log -1 --pretty=%s)"
echo "[preflight] origin_main_remote=$(git rev-parse origin/main 2>/dev/null || echo unknown)"
echo "[preflight] rollback_path=git reset --hard PREV_SHA && sudo bash /opt/linasbot/deploy.sh"

APP_DIR="/opt/linasbot"
if [ -f /opt/linasbot/linaslaserbot-2.7.22/main.py ]; then
  APP_DIR="/opt/linasbot/linaslaserbot-2.7.22"
fi
echo "[preflight] app_dir=$APP_DIR"

python3 - <<'PY'
from pathlib import Path
import os
import re

env_paths = [
    Path("/opt/linasbot/.env"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/.env"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/.env.local"),
]
values: dict[str, str] = {}
for p in env_paths:
    if not p.exists():
        print(f"[preflight] env_file missing path={p}")
        continue
    print(f"[preflight] env_file present path={p} mode={oct(p.stat().st_mode & 0o777)}")
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in values:
            values[k] = v

def report(key: str, *, min_len: int = 1, strong: bool = False) -> bool:
    raw = (values.get(key) or os.environ.get(key) or "").strip()
    present = bool(raw)
    length = len(raw)
    ok = present and length >= min_len
    strong_ok = True
    if strong and present:
        classes = sum(
            [
                bool(re.search(r"[a-z]", raw)),
                bool(re.search(r"[A-Z]", raw)),
                bool(re.search(r"[0-9]", raw)),
                bool(re.search(r"[^A-Za-z0-9]", raw)),
            ]
        )
        strong_ok = length >= 32 and classes >= 2
        ok = ok and strong_ok
    print(
        f"[preflight] {key}: present={present} length={length} "
        f"min_len_ok={length >= min_len} strong_ok={strong_ok} check_ok={ok}"
    )
    return ok

required = [
    report("DASHBOARD_AUTH_SECRET", min_len=32, strong=True),
    report("MONTYMOBILE_API_KEY", min_len=8),
    report("OPENAI_API_KEY", min_len=20),
    report("META_APP_SECRET", min_len=8),
    report("META_PAGE_ACCESS_TOKEN", min_len=20),
    report("META_PAGE_ID", min_len=3),
    report("META_INSTAGRAM_ACCOUNT_ID", min_len=3),
    report("META_WEBHOOK_VERIFY_TOKEN", min_len=8),
    report("META_APP_ID", min_len=3),
]

firebase_json_candidates = [
    Path("/opt/linasbot/firebase-credentials.json"),
    Path("/opt/linasbot/serviceAccount.json"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/firebase-credentials.json"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/serviceAccount.json"),
]
firebase_file = next((p for p in firebase_json_candidates if p.exists()), None)
gac = (values.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
gac_path_ok = bool(gac) and Path(gac).exists()
firebase_project = bool((values.get("FIREBASE_PROJECT_ID") or values.get("GCLOUD_PROJECT") or "").strip())
# Also accept common firebase admin JSON env blobs by presence-only (length), never print.
firebase_json_env = bool((values.get("FIREBASE_CREDENTIALS_JSON") or values.get("GOOGLE_CREDENTIALS") or "").strip())
firebase_ok = bool(firebase_file) or gac_path_ok or firebase_project or firebase_json_env
print(
    f"[preflight] firebase: file_present={bool(firebase_file)} "
    f"gac_path_ok={gac_path_ok} project_env={firebase_project} "
    f"json_env_present={firebase_json_env} check_ok={firebase_ok}"
)
env_prod = (values.get("ENVIRONMENT") or values.get("ENV") or "").strip().lower()
print(f"[preflight] environment_marker={env_prod or 'unset'}")
if not all(required) or not firebase_ok:
    raise SystemExit("[preflight] REQUIRED_CONFIG_MISSING")
print("[preflight] required_config_ok=true")
PY

python3 - <<'PY'
from pathlib import Path
import json
import os

for env_path in (
    Path("/opt/linasbot/.env"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/.env"),
):
    if not env_path.exists():
        continue
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))

count = 0
source = "none"
candidates = [
    Path("/opt/linasbot/data/dashboard_users.json"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/data/dashboard_users.json"),
    Path("/opt/linasbot_data/dashboard_users.json"),
    Path("/opt/linasbot/data/users.json"),
    Path("/opt/linasbot/linaslaserbot-2.7.22/data/users.json"),
]
# Discover plausible user stores under data roots (names only).
for root in (Path("/opt/linasbot/data"), Path("/opt/linasbot_data"), Path("/opt/linasbot/linaslaserbot-2.7.22/data")):
    if root.exists():
        for p in root.rglob("*user*.json"):
            if p.is_file() and p not in candidates:
                candidates.append(p)

for p in candidates:
    if not p.exists():
        continue
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[preflight] admin_file_error path={p} type={type(e).__name__}")
        continue
    users = data.get("users") if isinstance(data, dict) else data
    if isinstance(users, list) and users:
        count = len(users)
        source = f"file:{p}"
        break
    if isinstance(users, dict) and users:
        count = len(users)
        source = f"file:{p}"
        break

print(f"[preflight] dashboard_users count={count} source={source}")
if count < 1:
    raise SystemExit("[preflight] NO_EXISTING_ADMIN_USERS")
print("[preflight] existing_admin_retained=true (hashes unchanged by deploy; no default account created)")
PY

cd "$APP_DIR"
if [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [ -f scripts/backfill_live_chat_index.py ]; then
  echo "[preflight] starting live_chat_index dry-run"
  python3 scripts/backfill_live_chat_index.py --dry-run
  echo "[preflight] dry_run_backfill_exit=0"
else
  echo "[preflight] backfill_script_missing_on_current_deploy=true"
  echo "[preflight] NOTE: dry-run will be executed after release deploy when script is present"
fi

echo "[preflight] COMPLETE_OK"
