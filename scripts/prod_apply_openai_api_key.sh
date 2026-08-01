#!/usr/bin/env bash
# Atomically replace production OPENAI_API_KEY. Never prints secret values.
set -euo pipefail

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "[openai-apply] missing required env: OPENAI_API_KEY" >&2
  exit 1
fi

# Reject empty / clearly truncated values without printing the secret.
KEY_LEN="${#OPENAI_API_KEY}"
if [ "$KEY_LEN" -lt 40 ]; then
  echo "[openai-apply] refusing OPENAI_API_KEY: length_too_short len=${KEY_LEN}" >&2
  exit 1
fi

python3 - <<'PY'
import hashlib
import os
from pathlib import Path

KEY = "OPENAI_API_KEY"
value = os.environ[KEY].strip()
if not value:
    raise SystemExit(f"[openai-apply] empty {KEY}")

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

updates = {KEY: value}
fp = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
paths = [Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")]
updated = 0
for path in paths:
    if not path.parent.exists():
        print(f"[openai-apply] skip missing dir for {path}")
        continue
    upsert(path, updates)
    text = path.read_text()
    present = any(
        line.startswith(KEY + "=") and line.split("=", 1)[1].strip()
        for line in text.splitlines()
    )
    file_fp = ""
    for line in text.splitlines():
        if line.startswith(KEY + "="):
            file_fp = hashlib.sha256(line.split("=", 1)[1].strip().encode("utf-8")).hexdigest()[:16]
            break
    print(f"[openai-apply] updated={path} present={present} fp_match={file_fp == fp}")
    if not present or file_fp != fp:
        raise SystemExit(f"[openai-apply] verify failed for {path}")
    updated += 1

if updated < 1:
    raise SystemExit("[openai-apply] no .env paths updated")
print(f"[openai-apply] key_fp={fp}")
print(f"[openai-apply] key_len={len(value)}")
PY

systemctl restart linasbot
sleep 6
systemctl is-active linasbot

python3 - <<'PY'
import hashlib
import os
import subprocess
from pathlib import Path

KEY = "OPENAI_API_KEY"
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
    raise SystemExit("[openai-apply] could not read expected key from .env")

# Prove the running systemd service loaded EnvironmentFile without printing secrets.
pid = subprocess.check_output(["systemctl", "show", "-p", "MainPID", "--value", "linasbot"], text=True).strip()
if not pid or pid == "0":
    raise SystemExit("[openai-apply] linasbot MainPID unavailable")
environ_path = Path(f"/proc/{pid}/environ")
raw = environ_path.read_bytes()
env_map = {}
for item in raw.split(b"\0"):
    if b"=" in item:
        k, v = item.split(b"=", 1)
        env_map[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
loaded = env_map.get(KEY, "")
if not loaded:
    raise SystemExit("[openai-apply] running process missing OPENAI_API_KEY")
exp_fp = hashlib.sha256(expected.encode("utf-8")).hexdigest()[:16]
got_fp = hashlib.sha256(loaded.encode("utf-8")).hexdigest()[:16]
print(f"[openai-apply] process_pid={pid}")
print(f"[openai-apply] process_key_present=true")
print(f"[openai-apply] process_fp_match={exp_fp == got_fp}")
if exp_fp != got_fp:
    raise SystemExit("[openai-apply] running process key fingerprint mismatch")
PY

echo "api_health=$(curl -sS --max-time 10 https://www.linasaibot.com/api/health || true)"
echo "[openai-apply] SUCCESS"
