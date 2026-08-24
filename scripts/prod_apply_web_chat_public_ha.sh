#!/usr/bin/env bash
# Two-node HA transaction: enable WEB_CHAT_PUBLIC_AVAILABILITY=true.
set -euo pipefail

if [ "${META_HA_STAGE_ONLY:-}" != "true" ]; then
  echo "[web-chat-ha] refusing non-transactional apply: META_HA_STAGE_ONLY=true is required" >&2
  exit 1
fi
if [ -z "${EXPECTED_RELEASE_SHA:-}" ]; then
  echo "[web-chat-ha] refusing apply without an authorized release" >&2
  exit 1
fi

REPO_DIR="${REPO_DIR:-/opt/linasbot}"
PEER_HOST="${LINAS_HA_PEER_HOST:-10.106.0.4}"
META_HA_STATE_ROOT="${META_HA_STATE_ROOT:-/var/lib/linasbot/meta-ha}"
MAINTENANCE_FILE=/run/linasbot-maintenance
PERSISTENT_MAINTENANCE_FILE="$META_HA_STATE_ROOT/maintenance"
ENV_BACKUP="$META_HA_STATE_ROOT/env.before"
PY="$REPO_DIR/venv/bin/python"

stage_web_chat_public_flag() {
  "$PY" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" \
    --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority
  if [ -f "$REPO_DIR/scripts/prod_stage_web_chat_public_availability.sh" ]; then
    bash "$REPO_DIR/scripts/prod_stage_web_chat_public_availability.sh"
    return 0
  fi
  "$PY" -I - <<'PY'
import hmac
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

env_path = Path("/opt/linasbot/.env")
updates = {"WEB_CHAT_PUBLIC_AVAILABILITY": "true"}
atomic_update_env(env_path, updates)

def read_values(key: str) -> list[str]:
    return [
        line.split("=", 1)[1]
        for line in env_path.read_text(encoding="utf-8", errors="strict").splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]

for key, expected in updates.items():
    values = read_values(key)
    if len(values) != 1 or not hmac.compare_digest(values[0], expected):
        raise SystemExit(f"[web-chat-stage] staged value mismatch: {key}")
    print(f"[web-chat-stage] {key}:match=true")
print("[web-chat-stage] COMPLETE_OK")
PY
}

if [ "${SKIP_MUTATION_LOCK:-}" != "true" ]; then
  test "$(id -u)" -eq 0 && test "$(id -g)" -eq 0
  exec 9>/run/lock/linasbot-meta-live.lock
  flock -x 9
  export LINAS_PRODUCTION_MUTATION_LOCK_FD=9
fi

echo "[web-chat-ha] deployed_release_sha=${EXPECTED_RELEASE_SHA}"
install -d -m 0700 -o root -g root "$META_HA_STATE_ROOT"
install -m 0600 -o root -g root /dev/null "$PERSISTENT_MAINTENANCE_FILE"
install -m 0600 -o root -g root /dev/null "$MAINTENANCE_FILE"
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
  "root@${PEER_HOST}" \
  "install -d -m 0700 -o root -g root '$META_HA_STATE_ROOT' && install -m 0600 -o root -g root /dev/null '$PERSISTENT_MAINTENANCE_FILE' && install -m 0600 -o root -g root /dev/null '/run/linasbot-maintenance'"

DRAIN_SECONDS="$("$PY" -c 'import sys; from dotenv import dotenv_values; value = int(str(dotenv_values(sys.argv[1], interpolate=False).get("META_HA_LB_DRAIN_SECONDS") or "")); sys.exit("invalid HA drain interval") if not 30 <= value <= 300 else print(value)' "$REPO_DIR/.env")"
sleep "$DRAIN_SECONDS"

"$PY" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" \
  --expected-sha "$EXPECTED_RELEASE_SHA" --maintenance-active --recover-only
bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" "$EXPECTED_RELEASE_SHA" cluster-release-only
"$PY" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" \
  --expected-sha "$EXPECTED_RELEASE_SHA" --maintenance-active --register-prestage-backup

stage_web_chat_public_flag
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
  "root@${PEER_HOST}" \
  "export EXPECTED_RELEASE_SHA='$EXPECTED_RELEASE_SHA' META_HA_STAGE_ONLY=true; bash -s" <<'STAGEEOF'
set -euo pipefail
/opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
  --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority
/opt/linasbot/venv/bin/python -I - <<'PY'
import hmac
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

env_path = Path("/opt/linasbot/.env")
updates = {"WEB_CHAT_PUBLIC_AVAILABILITY": "true"}
atomic_update_env(env_path, updates)

def read_values(key: str) -> list[str]:
    return [
        line.split("=", 1)[1]
        for line in env_path.read_text(encoding="utf-8", errors="strict").splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]

for key, expected in updates.items():
    values = read_values(key)
    if len(values) != 1 or not hmac.compare_digest(values[0], expected):
        raise SystemExit(f"[web-chat-stage] staged value mismatch: {key}")
    print(f"[web-chat-stage] {key}:match=true")
print("[web-chat-stage] COMPLETE_OK")
PY
STAGEEOF

"$PY" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" \
  --expected-sha "$EXPECTED_RELEASE_SHA" --maintenance-active \
  --local-prestage-backup "$ENV_BACKUP"
"$PY" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" \
  --expected-sha "$EXPECTED_RELEASE_SHA" --finalize
bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" "$EXPECTED_RELEASE_SHA"

curl -fsS -X POST "https://www.linasaibot.com/api/web-chat/session" \
  -H "Content-Type: application/json" \
  -d '{"widget_key":"probe0000000001"}' >/tmp/web-chat-session-probe.json || true
"$PY" - <<'PY'
import json
from pathlib import Path

raw = Path("/tmp/web-chat-session-probe.json")
if raw.exists():
    body = json.loads(raw.read_text(encoding="utf-8"))
    detail = body.get("detail")
    if isinstance(detail, dict) and detail.get("error") == "WEB_CHAT_UNAVAILABLE":
        raise SystemExit("[web-chat-ha] containment still active after apply")
print("[web-chat-ha] containment_probe=not_unavailable")
PY
echo "[web-chat-ha] COMPLETE_OK"
