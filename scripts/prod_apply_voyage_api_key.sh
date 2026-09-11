#!/usr/bin/env bash
# Atomically upsert production VOYAGE_API_KEY. Never prints secret values.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_apply_voyage_api_key.sh"

if [ -z "${VOYAGE_API_KEY:-}" ]; then
  echo "[voyage-apply] missing required env: VOYAGE_API_KEY" >&2
  exit 1
fi

KEY_LEN="${#VOYAGE_API_KEY}"
if [ "$KEY_LEN" -lt 20 ]; then
  echo "[voyage-apply] refusing VOYAGE_API_KEY: length_too_short len=${KEY_LEN}" >&2
  exit 1
fi

PYTHONPATH=/opt/linasbot /opt/linasbot/venv/bin/python - <<'PY'
import hashlib
import os
from pathlib import Path

from scripts.ha.production_env_cas import atomic_update_canonical_env

KEY = "VOYAGE_API_KEY"
value = os.environ[KEY].strip()
if not value:
    raise SystemExit(f"[voyage-apply] empty {KEY}")

updates = {KEY: value}
fp = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
path = Path("/opt/linasbot/.env")
atomic_update_canonical_env(updates)
text = path.read_text(encoding="utf-8", errors="strict")
values = [line.split("=", 1)[1] for line in text.splitlines() if line.startswith(KEY + "=")]
if len(values) != 1 or hashlib.sha256(values[0].encode("utf-8")).hexdigest()[:16] != fp:
    raise SystemExit("[voyage-apply] canonical environment verification failed")
print("[voyage-apply] canonical_env_updated=true fp_match=true")
print(f"[voyage-apply] key_fp={fp}")
print(f"[voyage-apply] key_len={len(value)}")
PY

systemctl restart linasbot
sleep 6
systemctl is-active linasbot

/opt/linasbot/venv/bin/python - <<'PY'
import hashlib
import subprocess
from pathlib import Path

KEY = "VOYAGE_API_KEY"
expected = None
for line in Path("/opt/linasbot/.env").read_text(encoding="utf-8", errors="strict").splitlines():
    if line.startswith(KEY + "="):
        expected = line.split("=", 1)[1]
        break
if not expected:
    raise SystemExit("[voyage-apply] could not read expected key from .env")

pid = subprocess.check_output(["systemctl", "show", "-p", "MainPID", "--value", "linasbot"], text=True).strip()
if not pid or pid == "0":
    raise SystemExit("[voyage-apply] linasbot MainPID unavailable")
raw = Path(f"/proc/{pid}/environ").read_bytes()
env_map = {}
for item in raw.split(b"\0"):
    if b"=" in item:
        k, v = item.split(b"=", 1)
        env_map[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
loaded = env_map.get(KEY, "")
if not loaded:
    raise SystemExit("[voyage-apply] running process missing VOYAGE_API_KEY")
exp_fp = hashlib.sha256(expected.encode("utf-8")).hexdigest()[:16]
got_fp = hashlib.sha256(loaded.encode("utf-8")).hexdigest()[:16]
if exp_fp != got_fp:
    raise SystemExit("[voyage-apply] process env fingerprint mismatch")
print("[voyage-apply] process_env_match=true")
print("[voyage-apply] COMPLETE_OK")
PY
