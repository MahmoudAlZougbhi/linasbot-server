#!/usr/bin/env bash
# Apply stable DASHBOARD_AUTH_SECRET + ENVIRONMENT=production.
# Never prints secret values. Never auto-generates a secret (caller must supply).
set -euo pipefail

if [ -z "${DASHBOARD_AUTH_SECRET:-}" ]; then
  echo "[dashboard-auth-apply] missing required env: DASHBOARD_AUTH_SECRET" >&2
  exit 1
fi

SECRET_LEN="${#DASHBOARD_AUTH_SECRET}"
if [ "$SECRET_LEN" -lt 32 ]; then
  echo "[dashboard-auth-apply] refusing DASHBOARD_AUTH_SECRET: length_too_short len=${SECRET_LEN}" >&2
  exit 1
fi

python3 - <<'PY'
import hashlib
import os
import re
from pathlib import Path

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

def upsert(path: Path, updates: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    found = set()
    out = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                found.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in found:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n")
    os.chmod(path, 0o600)

updates = {KEY: value, ENV_KEY: "production"}
fp = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
paths = [Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")]
updated = 0
for path in paths:
    if not path.parent.exists():
        print(f"[dashboard-auth-apply] skip missing dir for {path}")
        continue
    upsert(path, updates)
    text = path.read_text()
    present = False
    file_fp = ""
    env_ok = False
    for line in text.splitlines():
        if line.startswith(KEY + "="):
            present = bool(line.split("=", 1)[1].strip())
            file_fp = hashlib.sha256(line.split("=", 1)[1].strip().encode("utf-8")).hexdigest()[:16]
        if line.startswith(ENV_KEY + "=") and line.split("=", 1)[1].strip() == "production":
            env_ok = True
    print(
        f"[dashboard-auth-apply] updated={path} secret_present={present} "
        f"fp_match={file_fp == fp} environment_production={env_ok}"
    )
    if not present or file_fp != fp or not env_ok:
        raise SystemExit(f"[dashboard-auth-apply] verify failed for {path}")
    updated += 1

if updated < 1:
    raise SystemExit("[dashboard-auth-apply] no .env paths updated")
print(f"[dashboard-auth-apply] secret_fp={fp}")
print(f"[dashboard-auth-apply] secret_len={len(value)}")
print("[dashboard-auth-apply] environment=production")
PY

systemctl restart linasbot
sleep 6
systemctl is-active linasbot

python3 - <<'PY'
import hashlib
import subprocess
from pathlib import Path

KEY = "DASHBOARD_AUTH_SECRET"
ENV_KEY = "ENVIRONMENT"
expected = None
for path in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if not path.exists():
        continue
    for line in path.read_text().splitlines():
        if line.startswith(KEY + "="):
            expected = line.split("=", 1)[1].strip()
            break
    if expected:
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
exp_fp = hashlib.sha256(expected.encode("utf-8")).hexdigest()[:16]
got_fp = hashlib.sha256(loaded.encode("utf-8")).hexdigest()[:16]
print(f"[dashboard-auth-apply] process_pid={pid}")
print(f"[dashboard-auth-apply] process_secret_present=true")
print(f"[dashboard-auth-apply] process_fp_match={exp_fp == got_fp}")
print(f"[dashboard-auth-apply] process_environment_production=true")
if exp_fp != got_fp:
    raise SystemExit("[dashboard-auth-apply] running process secret fingerprint mismatch")
PY

echo "api_health=$(curl -sS --max-time 10 https://www.linasaibot.com/api/health || true)"
echo "[dashboard-auth-apply] SUCCESS"
