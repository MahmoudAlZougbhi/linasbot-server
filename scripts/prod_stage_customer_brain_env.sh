#!/usr/bin/env bash
# Stage VOYAGE_API_KEY + Customer Brain lab flags on the canonical production env.
# node01: requires Meta HA stage authority.
# node02: peer-safe staging under the same maintenance transaction (no node01 identity).
# Activation/restart is owned by commit_staged_non_meta_env_via_restart.
# Never prints secret values.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[brain-env-stage] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[brain-env-stage] refusing stage without an authorized release" >&2
  exit 1
fi
if [ -z "${VOYAGE_API_KEY:-}" ] || [ "${#VOYAGE_API_KEY}" -lt 20 ]; then
  echo "[brain-env-stage] VOYAGE_API_KEY missing or too short" >&2
  exit 1
fi

APP_DIR=/opt/linasbot
ENV_PATH="$APP_DIR/.env"
PYTHON_BIN="$APP_DIR/venv/bin/python"
META_HA_STATE_ROOT=/var/lib/linasbot/meta-ha
MAINTENANCE_FILE=/run/linasbot-maintenance
PERSISTENT_MAINTENANCE_FILE="$META_HA_STATE_ROOT/maintenance"
test -x "$PYTHON_BIN"
test -f "$ENV_PATH"

NODE_ID="$("$PYTHON_BIN" -I - <<'PY'
from pathlib import Path

identities = []
for raw in Path("/opt/linasbot/.env").read_text(encoding="utf-8").splitlines():
    if not raw or raw.lstrip().startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    if key.strip() != "META_DELETION_NODE_ID":
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    identities.append(value)
if len(identities) != 1 or identities[0] not in {"node01", "node02"}:
    raise SystemExit("invalid META_DELETION_NODE_ID")
print(identities[0])
PY
)"

DEPLOYED_SHA="$(git -C "$APP_DIR" rev-parse HEAD)"
if [ "$DEPLOYED_SHA" != "$EXPECTED_RELEASE_SHA" ]; then
  echo "[brain-env-stage] release SHA mismatch deployed=${DEPLOYED_SHA}" >&2
  exit 1
fi
if [ ! -f "$MAINTENANCE_FILE" ] || [ ! -f "$PERSISTENT_MAINTENANCE_FILE" ]; then
  echo "[brain-env-stage] maintenance not armed" >&2
  exit 1
fi

if [ "$NODE_ID" = "node01" ]; then
  "$PYTHON_BIN" -I "$APP_DIR/scripts/ha/sync_meta_env_to_peer.py" \
    --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority
elif [ "$NODE_ID" = "node02" ]; then
  if [ -z "${LINAS_PRODUCTION_MUTATION_LOCK_FD:-}" ]; then
    echo "[brain-env-stage] peer missing mutation lock fd" >&2
    exit 1
  fi
  "$PYTHON_BIN" -I - <<'PY'
import fcntl
import os
from pathlib import Path

raw_fd = os.environ.get("LINAS_PRODUCTION_MUTATION_LOCK_FD", "")
if not raw_fd.isdigit():
    raise SystemExit("[brain-env-stage] peer lock fd invalid")
fd = int(raw_fd)
lock_path = Path("/run/lock/linasbot-meta-live.lock")
if not lock_path.is_file():
    raise SystemExit("[brain-env-stage] peer lock file missing")
# Confirm the inherited fd is a live descriptor for this process.
try:
    os.fstat(fd)
except OSError as exc:
    raise SystemExit(f"[brain-env-stage] peer lock fd invalid: {exc}") from exc
# Re-assert exclusive ownership without releasing the outer flock -x.
fcntl.flock(fd, fcntl.LOCK_EX)
print("[brain-env-stage] peer_lock_held=true")
PY
else
  echo "[brain-env-stage] unsupported node identity" >&2
  exit 1
fi

umask 077
"$PYTHON_BIN" -I - <<'PY'
import hashlib
import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

voyage = os.environ["VOYAGE_API_KEY"].strip()
if len(voyage) < 20:
    raise SystemExit("[brain-env-stage] voyage length_too_short")
updates = {
    "VOYAGE_API_KEY": voyage,
    "LINAS_CUSTOMER_AI_LAB": "true",
    "EMERGENCY_LEGACY_REPLY_ENABLED": "false",
    "MESSAGE_BILLING_CUTOVER": "false",
    "MESSAGE_BILLING_ENABLED": "false",
}
atomic_update_env(Path("/opt/linasbot/.env"), updates)
text = Path("/opt/linasbot/.env").read_text(encoding="utf-8").splitlines()
for key, expected in updates.items():
    values = [
        line.split("=", 1)[1]
        for line in text
        if line.startswith(key + "=")
    ]
    if len(values) != 1 or not hmac.compare_digest(values[0], expected):
        raise SystemExit(f"[brain-env-stage] mismatch:{key}")
    if key == "VOYAGE_API_KEY":
        fp = hashlib.sha256(expected.encode()).hexdigest()[:16]
        print(f"[brain-env-stage] VOYAGE_API_KEY:fp={fp} len={len(expected)}")
    else:
        print(f"[brain-env-stage] {key}:match=true")
print("[brain-env-stage] COMPLETE_OK")
PY
