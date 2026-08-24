#!/usr/bin/env bash
# Web chat public availability HA apply (inline block).
set -euo pipefail

apply_web_chat_public_ha() {
  export META_HA_STAGE_ONLY=true SKIP_MUTATION_LOCK=true
set -euo pipefail
REPO_DIR=/opt/linasbot
PEER_HOST="${LINAS_HA_PEER_HOST:-10.106.0.4}"
META_HA_STATE_ROOT=/var/lib/linasbot/meta-ha
ENV_BACKUP="$META_HA_STATE_ROOT/env.before"
PY="$REPO_DIR/venv/bin/python"
install -d -m 0700 -o root -g root "$META_HA_STATE_ROOT"
install -m 0600 -o root -g root /dev/null "$META_HA_STATE_ROOT/maintenance"
install -m 0600 -o root -g root /dev/null /run/linasbot-maintenance
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes "root@${PEER_HOST}" \
  "install -d -m 0700 -o root -g root '$META_HA_STATE_ROOT' && install -m 0600 -o root -g root /dev/null '$META_HA_STATE_ROOT/maintenance' && install -m 0600 -o root -g root /dev/null '/run/linasbot-maintenance'"
DRAIN_SECONDS="$("$PY" -c 'import sys; from dotenv import dotenv_values; value = int(str(dotenv_values(sys.argv[1], interpolate=False).get("META_HA_LB_DRAIN_SECONDS") or "")); sys.exit("invalid HA drain interval") if not 30 <= value <= 300 else print(value)' "$REPO_DIR/.env")"
sleep "$DRAIN_SECONDS"
"$PY" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" --expected-sha "$EXPECTED_RELEASE_SHA" --maintenance-active --recover-only
bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" "$EXPECTED_RELEASE_SHA" cluster-release-only
"$PY" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" --expected-sha "$EXPECTED_RELEASE_SHA" --maintenance-active --register-prestage-backup
"$PY" -I - <<'PY'
import hmac, sys
from pathlib import Path
sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env
env_path = Path("/opt/linasbot/.env")
updates = {"WEB_CHAT_PUBLIC_AVAILABILITY": "true"}
atomic_update_env(env_path, updates)
for key, expected in updates.items():
    values = [line.split("=", 1)[1] for line in env_path.read_text(encoding="utf-8").splitlines() if "=" in line and line.split("=",1)[0].strip()==key]
    if len(values)!=1 or not hmac.compare_digest(values[0], expected):
        raise SystemExit(f"[web-chat-stage] staged value mismatch: {key}")
    print(f"[web-chat-stage] {key}:match=true")
print("[web-chat-stage] COMPLETE_OK")
PY
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes "root@${PEER_HOST}" "export EXPECTED_RELEASE_SHA='$EXPECTED_RELEASE_SHA' META_HA_STAGE_ONLY=true; bash -s" <<'WEBPEERSTAGEEOF'
set -euo pipefail
/opt/linasbot/venv/bin/python -I - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, "/opt/linasbot")
import scripts.ha.sync_meta_env_to_peer as sync
expected_sha = os.environ["EXPECTED_RELEASE_SHA"]
state_root = Path("/var/lib/linasbot/meta-ha")
sync._refuse_conflicting_ha_transaction(state_root)
sync._require_node_identity(sync.ENV_PATH, sync.PEER_NODE_ID)
if sync._load_journal(state_root) is not None:
    raise SystemExit("[web-chat-stage] peer journal present")
sync._ensure_maintenance_armed(state_root)
worker_state = sync._load_worker_state(state_root)
if (
    worker_state is None
    or worker_state["role"] != "peer"
    or worker_state["expected_sha"] != expected_sha
    or worker_state["status"] != "quiesced"
):
    raise SystemExit("[web-chat-stage] peer worker state invalid")
current_fingerprint = sync._meta_fingerprint(
    sync._read_meta_values(sync.ENV_PATH),
    expected_sha,
)
if current_fingerprint != worker_state["old_fingerprint"]:
    raise SystemExit("[web-chat-stage] peer env fingerprint drift")
sync._verify_worker_units_quiesced()
print("[web-chat-stage] peer_stage_authority_verified=true")
PY
/opt/linasbot/venv/bin/python -I - <<'PY'
import hmac, sys
from pathlib import Path
sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env
env_path = Path("/opt/linasbot/.env")
updates = {"WEB_CHAT_PUBLIC_AVAILABILITY": "true"}
atomic_update_env(env_path, updates)
for key, expected in updates.items():
    values = [line.split("=", 1)[1] for line in env_path.read_text(encoding="utf-8").splitlines() if "=" in line and line.split("=",1)[0].strip()==key]
    if len(values)!=1 or not hmac.compare_digest(values[0], expected):
        raise SystemExit(f"[web-chat-stage] staged value mismatch: {key}")
    print(f"[web-chat-stage] {key}:match=true")
print("[web-chat-stage] COMPLETE_OK")
PY
WEBPEERSTAGEEOF
commit_staged_non_meta_env_via_restart "[web-chat-ha]"
bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
  "$EXPECTED_RELEASE_SHA" cluster-release-only
echo "[web-chat-ha] COMPLETE_OK"
}
