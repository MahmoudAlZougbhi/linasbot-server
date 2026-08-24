#!/usr/bin/env bash
# Remote WhatsApp Cloud Phase 1 + web chat HA apply (fetched by workflow).

set -euo pipefail
test "$(id -u)" -eq 0 && test "$(id -g)" -eq 0
exec 9>/run/lock/linasbot-meta-live.lock
flock -x 9
export LINAS_PRODUCTION_MUTATION_LOCK_FD=9
REPO_DIR=/opt/linasbot
PEER_HOST="${LINAS_HA_PEER_HOST:-10.106.0.4}"
DEPLOYED_RELEASE_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"
export EXPECTED_RELEASE_SHA="$DEPLOYED_RELEASE_SHA"
echo "[wa-phase1-ha] deployed_release_sha=${DEPLOYED_RELEASE_SHA}"
"$REPO_DIR/venv/bin/python" -I - <<'PY'
import subprocess
import sys
from pathlib import Path

repo = Path("/opt/linasbot")
sha = subprocess.check_output(
    ["git", "-C", str(repo), "rev-parse", "HEAD"],
    text=True,
).strip()
changed = subprocess.check_output(
    ["git", "-C", str(repo), "diff", "--name-only", sha],
    text=True,
).splitlines()
if changed:
    print(
        f"[wa-phase1-ha] deployed_tree_drift=true restoring={len(changed)} paths",
        flush=True,
    )
    for relative in changed:
        blob = subprocess.check_output(
            ["git", "-C", str(repo), "cat-file", "-p", f"{sha}:{relative}"],
        )
        destination = repo.joinpath(*Path(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(blob)
    subprocess.run(["git", "-C", str(repo), "add", "-u"], check=True)
if subprocess.run(
    ["git", "-C", str(repo), "diff", "--quiet", sha],
    check=False,
).returncode or subprocess.run(
    ["git", "-C", str(repo), "diff", "--cached", "--quiet", sha],
    check=False,
).returncode:
    dirty = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "--name-only", sha],
        text=True,
    )
    print(f"[wa-phase1-ha] deployed_tree_still_dirty={dirty!r}", file=sys.stderr)
    raise SystemExit(1)
script = "scripts/ha/sync_meta_env_to_peer.py"
live = (repo / script).read_bytes()
blob = subprocess.check_output(
    ["git", "-C", str(repo), "cat-file", "-p", f"{sha}:{script}"],
)
if live != blob:
    print("[wa-phase1-ha] Meta HA script pin failed", file=sys.stderr)
    raise SystemExit(1)
print("[wa-phase1-ha] release_script_pin_ok=true")
PY
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
  "root@${PEER_HOST}" \
  "$REPO_DIR/venv/bin/python -I -" <<'PY'
import subprocess
import sys
from pathlib import Path

repo = Path("/opt/linasbot")
sha = subprocess.check_output(
    ["git", "-C", str(repo), "rev-parse", "HEAD"],
    text=True,
).strip()
changed = subprocess.check_output(
    ["git", "-C", str(repo), "diff", "--name-only", sha],
    text=True,
).splitlines()
if changed:
    print(
        f"[wa-phase1-ha] peer_deployed_tree_drift=true restoring={len(changed)} paths",
        flush=True,
    )
    for relative in changed:
        blob = subprocess.check_output(
            ["git", "-C", str(repo), "cat-file", "-p", f"{sha}:{relative}"],
        )
        destination = repo.joinpath(*Path(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(blob)
    subprocess.run(["git", "-C", str(repo), "add", "-u"], check=True)
if subprocess.run(
    ["git", "-C", str(repo), "diff", "--quiet", sha],
    check=False,
).returncode or subprocess.run(
    ["git", "-C", str(repo), "diff", "--cached", "--quiet", sha],
    check=False,
).returncode:
    dirty = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "--name-only", sha],
        text=True,
    )
    print(f"[wa-phase1-ha] peer_deployed_tree_still_dirty={dirty!r}", file=sys.stderr)
    raise SystemExit(1)
script = "scripts/ha/sync_meta_env_to_peer.py"
live = (repo / script).read_bytes()
blob = subprocess.check_output(
    ["git", "-C", str(repo), "cat-file", "-p", f"{sha}:{script}"],
)
if live != blob:
    print("[wa-phase1-ha] peer Meta HA script pin failed", file=sys.stderr)
    raise SystemExit(1)
print("[wa-phase1-ha] peer_release_script_pin_ok=true")
PY
if [ -z "${WORKFLOW_SCRIPT_SHA:-}" ]; then
  echo "[wa-phase1-ha] WORKFLOW_SCRIPT_SHA is required" >&2
  exit 1
fi
SCRIPT_BASE="https://raw.githubusercontent.com/MahmoudAlZougbhi/linasbot-server/${WORKFLOW_SCRIPT_SHA}"
LIB_TMP="$(mktemp)"
WEB_TMP="$(mktemp)"
trap 'rm -f "$LIB_TMP" "$WEB_TMP"' EXIT
curl -fsSL "$SCRIPT_BASE/scripts/ha/whatsapp_phase1_apply_lib.sh" -o "$LIB_TMP"
curl -fsSL "$SCRIPT_BASE/scripts/ha/whatsapp_phase1_web_chat_apply.sh" -o "$WEB_TMP"
# shellcheck source=/dev/null
source "$LIB_TMP"
export WHATSAPP_PHASE1_WEB_CHAT_LIB="$WEB_TMP"
stage_whatsapp_phase1_flags() {
  export EXPECTED_RELEASE_SHA META_HA_STAGE_ONLY
  /opt/linasbot/venv/bin/python -I /opt/linasbot/scripts/ha/sync_meta_env_to_peer.py \
    --expected-sha "$EXPECTED_RELEASE_SHA" --verify-stage-authority
  /opt/linasbot/venv/bin/python -I - <<'PY'
import hmac
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

env_path = Path("/opt/linasbot/.env")
updates = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
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
        raise SystemExit(f"[wa-phase1-stage] staged value mismatch: {key}")
    print(f"[wa-phase1-stage] {key}:match=true")
print("[wa-phase1-stage] COMPLETE_OK")
PY
}
phase1_flags_already_live() {
  "$REPO_DIR/venv/bin/python" -I - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
import scripts.ha.sync_meta_env_to_peer as sync

expected = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
state_root = Path("/var/lib/linasbot/meta-ha")
if sync._load_journal(state_root) is not None:
    raise SystemExit(1)
worker_state = sync._load_worker_state(state_root)
if worker_state is not None and worker_state.get("status") == "quiesced":
    raise SystemExit(1)
values = sync._read_meta_values(sync.ENV_PATH)
for key, want in expected.items():
    if values.get(key) != want:
        raise SystemExit(1)
print("[wa-phase1-ha] coordinator_flags_live=true")
PY
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    "$REPO_DIR/venv/bin/python -I -" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
import scripts.ha.sync_meta_env_to_peer as sync

expected = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
state_root = Path("/var/lib/linasbot/meta-ha")
if sync._load_journal(state_root) is not None:
    raise SystemExit(1)
worker_state = sync._load_worker_state(state_root)
if worker_state is not None and worker_state.get("status") == "quiesced":
    raise SystemExit(1)
values = sync._read_meta_values(sync.ENV_PATH)
for key, want in expected.items():
    if values.get(key) != want:
        raise SystemExit(1)
print("[wa-phase1-ha] peer_flags_live=true")
PY
}
if phase1_flags_already_live; then
  echo "[wa-phase1-ha] flags_already_live=true"
  rm -f "$META_HA_STATE_ROOT/env.before"
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    "rm -f '$META_HA_STATE_ROOT/env.before'" || true
  TRANSACTION_COMPLETE=true
  MAINTENANCE_ARMED=false
  grant_linas_pilot_if_requested || true
  ready_ok=false
  for attempt in $(seq 1 24); do
    if curl -fsS http://127.0.0.1:8003/api/ready >/tmp/wa-ready.json; then
      ready_ok=true
      break
    fi
    sleep 5
  done
  if [ "$ready_ok" != "true" ]; then
    echo "[wa-phase1-ha] public_ready_timeout=true" >&2
    exit 1
  fi
  "$REPO_DIR/venv/bin/python" - <<'PY'
import json
data = json.load(open("/tmp/wa-ready.json"))
assert data.get("ok") is True, data
checks = data.get("checks") or {}
wa_db = ((checks.get("tiktok_business") or {}).get("config_keys_present") or {}).get("LINAS_WHATSAPP_DATABASE_URL")
assert wa_db is True, checks
print("[wa-phase1-ha] ready_ok=true whatsapp_db_present=true")
PY
  echo "[wa-phase1-ha] COMPLETE_OK"
else
MAINTENANCE_ARMED=true
sudo install -d -m 0700 -o root -g root "$META_HA_STATE_ROOT"
sudo install -m 0600 -o root -g root /dev/null "$PERSISTENT_MAINTENANCE_FILE"
sudo install -m 0600 -o root -g root /dev/null "$MAINTENANCE_FILE"
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
  "root@${PEER_HOST}" \
  "install -d -m 0700 -o root -g root '$META_HA_STATE_ROOT' && install -m 0600 -o root -g root /dev/null '$PERSISTENT_MAINTENANCE_FILE' && install -m 0600 -o root -g root /dev/null '$MAINTENANCE_FILE'"
test "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
  http://127.0.0.1:8003/api/ready || true)" = "503"
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
  "root@${PEER_HOST}" \
  "test \"\$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8003/api/ready || true)\" = \"503\""
DRAIN_SECONDS="$("$REPO_DIR/venv/bin/python" -c 'import sys; from dotenv import dotenv_values; value = int(str(dotenv_values(sys.argv[1], interpolate=False).get("META_HA_LB_DRAIN_SECONDS") or "")); sys.exit("invalid HA drain interval") if not 30 <= value <= 300 else print(value)' "$REPO_DIR/.env")"
sleep "$DRAIN_SECONDS"
if [ -f "$META_HA_STATE_ROOT/env.before" ] && [ -f "$META_HA_STATE_ROOT/prestage.authority.json" ]; then
  if staged_phase1_commit_ready; then
    echo "[wa-phase1-ha] resume_staged_commit=true"
  else
    echo "[wa-phase1-ha] restage_existing_prestage=true"
    "$REPO_DIR/venv/bin/python" -I - <<'PY'
import hmac
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

env_path = Path("/opt/linasbot/.env")
updates = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
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
        raise SystemExit(f"[wa-phase1-stage] staged value mismatch: {key}")
    print(f"[wa-phase1-stage] {key}:match=true")
print("[wa-phase1-stage] COMPLETE_OK")
PY
    ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
      "root@${PEER_HOST}" \
      "export EXPECTED_RELEASE_SHA='$EXPECTED_RELEASE_SHA' META_HA_STAGE_ONLY=true; bash -s" <<'PEERRESTAGEEOF'
set -euo pipefail
/opt/linasbot/venv/bin/python -I - <<'PY'
import hmac, sys
from pathlib import Path
sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env
env_path = Path("/opt/linasbot/.env")
updates = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
atomic_update_env(env_path, updates)
for key, expected in updates.items():
    values = [
        line.split("=", 1)[1]
        for line in env_path.read_text(encoding="utf-8", errors="strict").splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]
    if len(values) != 1 or not hmac.compare_digest(values[0], expected):
        raise SystemExit(f"[wa-phase1-stage] staged value mismatch: {key}")
    print(f"[wa-phase1-stage] {key}:match=true")
print("[wa-phase1-stage] COMPLETE_OK")
PY
PEERRESTAGEEOF
  fi
else
  "$REPO_DIR/venv/bin/python" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" \
    --expected-sha "$EXPECTED_RELEASE_SHA" --maintenance-active --recover-only
  bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
    "$EXPECTED_RELEASE_SHA" cluster-release-only
  "$REPO_DIR/venv/bin/python" -I "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py" \
    --expected-sha "$EXPECTED_RELEASE_SHA" --maintenance-active --register-prestage-backup
  if [ -f "$REPO_DIR/scripts/prod_stage_whatsapp_cloud_phase1_flags.sh" ]; then
    bash "$REPO_DIR/scripts/prod_stage_whatsapp_cloud_phase1_flags.sh"
  else
    stage_whatsapp_phase1_flags
  fi
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    "export EXPECTED_RELEASE_SHA='$EXPECTED_RELEASE_SHA' META_HA_STAGE_ONLY=true; bash -s" <<'PEERSTAGEEOF'
set -euo pipefail
/opt/linasbot/venv/bin/python -I - <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
import scripts.ha.sync_meta_env_to_peer as sync

expected_sha = os.environ["EXPECTED_RELEASE_SHA"]
state_root = Path("/var/lib/linasbot/meta-ha")
sync._refuse_conflicting_ha_transaction(state_root)
sync._require_node_identity(sync.ENV_PATH, sync.PEER_NODE_ID)
if sync._load_journal(state_root) is not None:
    raise SystemExit("[wa-phase1-stage] peer journal present")
sync._ensure_maintenance_armed(state_root)
worker_state = sync._load_worker_state(state_root)
if (
    worker_state is None
    or worker_state["role"] != "peer"
    or worker_state["expected_sha"] != expected_sha
    or worker_state["status"] != "quiesced"
):
    raise SystemExit("[wa-phase1-stage] peer worker state invalid")
current_fingerprint = sync._meta_fingerprint(
    sync._read_meta_values(sync.ENV_PATH),
    expected_sha,
)
if current_fingerprint != worker_state["old_fingerprint"]:
    raise SystemExit("[wa-phase1-stage] peer env fingerprint drift")
sync._verify_worker_units_quiesced()
print("[wa-phase1-stage] peer_stage_authority_verified=true")
PY
/opt/linasbot/venv/bin/python -I - <<'PY'
import hmac
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
from scripts.ha.meta_env_file import atomic_update_env

env_path = Path("/opt/linasbot/.env")
updates = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
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
        raise SystemExit(f"[wa-phase1-stage] staged value mismatch: {key}")
    print(f"[wa-phase1-stage] {key}:match=true")
print("[wa-phase1-stage] COMPLETE_OK")
PY
PEERSTAGEEOF
fi
finalize_staged_phase1_transaction
fi
if [ "${ENABLE_WEB_CHAT:-true}" = "true" ]; then
  # shellcheck source=/dev/null
  source "${WHATSAPP_PHASE1_WEB_CHAT_LIB:?WHATSAPP_PHASE1_WEB_CHAT_LIB is required}"
  apply_web_chat_public_ha
fi
echo "[prod-social-enable] COMPLETE_OK"
