#!/usr/bin/env bash
# Atomically replace production OPENAI_API_KEY. Never prints secret values.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_apply_openai_api_key.sh"

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

PYTHONPATH=/opt/linasbot /opt/linasbot/venv/bin/python - <<'PY'
import hashlib
import os
from pathlib import Path

from scripts.ha.production_env_cas import atomic_update_canonical_env

KEY = "OPENAI_API_KEY"
value = os.environ[KEY].strip()
if not value:
    raise SystemExit(f"[openai-apply] empty {KEY}")

updates = {KEY: value}
fp = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
path = Path("/opt/linasbot/.env")
atomic_update_canonical_env(updates)
text = path.read_text(encoding="utf-8", errors="strict")
values = [line.split("=", 1)[1] for line in text.splitlines() if line.startswith(KEY + "=")]
if len(values) != 1 or hashlib.sha256(values[0].encode("utf-8")).hexdigest()[:16] != fp:
    raise SystemExit("[openai-apply] canonical environment verification failed")
print("[openai-apply] canonical_env_updated=true fp_match=true")
print(f"[openai-apply] key_fp={fp}")
print(f"[openai-apply] key_len={len(value)}")
PY

systemctl restart linasbot
sleep 6
systemctl is-active linasbot

/opt/linasbot/venv/bin/python - <<'PY'
import hashlib
import os
import subprocess
from pathlib import Path

KEY = "OPENAI_API_KEY"
expected = None
for line in Path("/opt/linasbot/.env").read_text(encoding="utf-8", errors="strict").splitlines():
    if line.startswith(KEY + "="):
        expected = line.split("=", 1)[1]
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
bash /opt/linasbot/scripts/prod_verify_canonical_social_ai.sh
echo "[openai-apply] SUCCESS"
