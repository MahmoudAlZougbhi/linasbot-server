#!/usr/bin/env bash
# Shared helpers for WhatsApp Phase 1 HA apply.
set -euo pipefail

grant_linas_pilot_if_requested() {
  if [ "${GRANT_PILOT:-true}" != "true" ]; then
    echo "[wa-pilot-grant] skipped=true"
    return 0
  fi
  if [ -x "$REPO_DIR/scripts/prod_grant_whatsapp_pilot.py" ] || [ -f "$REPO_DIR/scripts/prod_grant_whatsapp_pilot.py" ]; then
    "$REPO_DIR/venv/bin/python" -I "$REPO_DIR/scripts/prod_grant_whatsapp_pilot.py" \
      --tenant-id linas \
      --reason "Internal WhatsApp coexistence pilot after Phase 1 flags" \
      --granted-by production_ops
    return 0
  fi
  "$REPO_DIR/venv/bin/python" -I - <<'PY'
import sys

sys.path.insert(0, "/opt/linasbot")
from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from services.whatsapp_cloud.repository import WhatsAppCloudRepository

tenant_id = "linas"
reason = "Internal WhatsApp coexistence pilot after Phase 1 flags"
try:
    with whatsapp_session(require=True) as session:
        repo = WhatsAppCloudRepository(session)
        existing = repo.get_active_pilot(tenant_id)
        if existing is not None:
            print(f"[wa-pilot-grant] already_active=true tenant_id={tenant_id}")
            raise SystemExit(0)
        row = repo.grant_pilot(
            tenant_id=tenant_id,
            granted_by_user_id="production_ops",
            reason=reason,
        )
        repo.add_audit(
            tenant_id=tenant_id,
            actor_user_id="production_ops",
            event_type="pilot_granted",
            detail={"reason": reason, "source": "wa-phase1-ha-inline"},
        )
        print(f"[wa-pilot-grant] granted=true tenant_id={row.tenant_id} status={row.status}")
except WhatsAppDatabaseUnavailable:
    print("[wa-pilot-grant] WHATSAPP_DB_UNAVAILABLE", file=sys.stderr)
    raise SystemExit(3) from None
PY
}
PEER_HOST="${LINAS_HA_PEER_HOST:-10.106.0.4}"
MAINTENANCE_FILE=/run/linasbot-maintenance
META_HA_STATE_ROOT=/var/lib/linasbot/meta-ha
PERSISTENT_MAINTENANCE_FILE="$META_HA_STATE_ROOT/maintenance"
ENV_BACKUP=""
MAINTENANCE_ARMED=false
TRANSACTION_COMPLETE=false
fail_closed_cleanup() {
  status=$?
  trap - EXIT
  if [ "$TRANSACTION_COMPLETE" != "true" ]; then
    status=1
    if [ "$MAINTENANCE_ARMED" = "true" ]; then
      sudo install -d -m 0700 -o root -g root "$META_HA_STATE_ROOT" || true
      sudo install -m 0600 -o root -g root /dev/null "$PERSISTENT_MAINTENANCE_FILE" || true
      install -m 0600 /dev/null "$MAINTENANCE_FILE" || true
      ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
        "root@${PEER_HOST}" \
        "install -d -m 0700 -o root -g root '$META_HA_STATE_ROOT' && install -m 0600 -o root -g root /dev/null '$PERSISTENT_MAINTENANCE_FILE' && install -m 0600 -o root -g root /dev/null '$MAINTENANCE_FILE'" || true
      echo "[wa-phase1-ha] HA maintenance retained after uncertain transaction" >&2
    fi
    if [ -n "$ENV_BACKUP" ]; then
      echo "[wa-phase1-ha] exact pre-stage backup retained at $ENV_BACKUP" >&2
    fi
  else
    sudo rm -f "$ENV_BACKUP"
  fi
  exit "$status"
}
trap fail_closed_cleanup EXIT
commit_staged_non_meta_env_via_restart() {
  local log_prefix="${1:-[wa-phase1-ha]}"
  echo "${log_prefix} commit_via_restart=true"
  "$REPO_DIR/venv/bin/python" -I - <<'PY'
import subprocess

subprocess.run(["systemctl", "restart", "linasbot"], check=True)
PY
  for attempt in $(seq 1 30); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8003/api/ready || true)"
    if [ "$code" = "200" ] || [ "$code" = "503" ]; then
      break
    fi
    sleep 2
  done
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    "$REPO_DIR/venv/bin/python -I -c \"import subprocess; subprocess.run(['systemctl','restart','linasbot'], check=True)\""
  "$REPO_DIR/venv/bin/python" -I - "$EXPECTED_RELEASE_SHA" node01 <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
import scripts.ha.sync_meta_env_to_peer as sync

expected_sha = sys.argv[1]
node_id = sys.argv[2]
state_root = Path("/var/lib/linasbot/meta-ha")
values = sync._read_meta_values(sync.ENV_PATH)
worker_state = sync._load_worker_state(state_root)
authority = sync._load_stage_authority(state_root)
if worker_state is not None and authority is not None:
    try:
        sync._verify_runtime_values(values, expected_node_id=node_id)
        sync._verify_worker_units_restored(
            worker_state,
            values,
            expected_node_id=node_id,
        )
        print(f"[wa-phase1-ha] workers_restored=true node={node_id} resume_skip=true")
        raise SystemExit(0)
    except RuntimeError:
        pass
authority, worker_state = sync._require_stage_authority(
    state_root,
    expected_sha=expected_sha,
    require_preimage=False,
)
values = sync._read_meta_values(sync.ENV_PATH)
sync._restore_worker_units(
    state_root,
    worker_state,
    terminal_fingerprint=str(authority["old_fingerprint"]),
    expected_values=values,
    expected_node_id=node_id,
)
sync._verify_runtime_values(values, expected_node_id=node_id)
print(f"[wa-phase1-ha] workers_restored=true node={node_id}")
PY
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    "$REPO_DIR/venv/bin/python -I - '$EXPECTED_RELEASE_SHA' node02" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/opt/linasbot")
import scripts.ha.sync_meta_env_to_peer as sync

expected_sha = sys.argv[1]
node_id = sys.argv[2]
state_root = Path("/var/lib/linasbot/meta-ha")
worker_state = sync._load_worker_state(state_root)
if (
    worker_state is None
    or worker_state["role"] != "peer"
    or worker_state["expected_sha"] != expected_sha
    or worker_state["status"] != "quiesced"
):
    raise SystemExit("[wa-phase1-ha] peer worker state invalid for commit")
values = sync._read_meta_values(sync.ENV_PATH)
sync._restore_worker_units(
    state_root,
    worker_state,
    terminal_fingerprint=str(worker_state["old_fingerprint"]),
    expected_values=values,
    expected_node_id=node_id,
)
sync._verify_runtime_values(values, expected_node_id=node_id)
print(f"[wa-phase1-ha] workers_restored=true node={node_id}")
PY
  rm -f "$MAINTENANCE_FILE" "$PERSISTENT_MAINTENANCE_FILE"
  rm -f "$META_HA_STATE_ROOT/env.before" "$META_HA_STATE_ROOT/prestage.authority.json" "$META_HA_STATE_ROOT/workers.before.json"
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    "rm -f /run/linasbot-maintenance '$META_HA_STATE_ROOT/maintenance' '$META_HA_STATE_ROOT/env.before' '$META_HA_STATE_ROOT/prestage.authority.json' '$META_HA_STATE_ROOT/workers.before.json'"
  bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
    "$EXPECTED_RELEASE_SHA" cluster-release-only
  echo "${log_prefix} commit_via_restart COMPLETE_OK"
}
staged_phase1_commit_ready() {
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
backup = state_root / "env.before"
authority = sync._load_stage_authority(state_root)
if authority is None or not backup.exists():
    raise SystemExit(1)
if sync.ENV_PATH.read_bytes() == backup.read_bytes():
    raise SystemExit(1)
values = sync._read_meta_values(sync.ENV_PATH)
for key, want in expected.items():
    if values.get(key) != want:
        raise SystemExit(1)
print("[wa-phase1-ha] staged_phase1_commit_ready=true")
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
values = sync._read_meta_values(sync.ENV_PATH)
for key, want in expected.items():
    if values.get(key) != want:
        raise SystemExit(1)
print("[wa-phase1-ha] peer_staged_phase1_commit_ready=true")
PY
}
finalize_staged_phase1_transaction() {
  ENV_BACKUP="$META_HA_STATE_ROOT/env.before"
  "$REPO_DIR/venv/bin/python" -I - <<'PY'
import os
import traceback
from pathlib import Path

import sys

sys.path.insert(0, "/opt/linasbot")
import scripts.ha.sync_meta_env_to_peer as sync

state_root = Path("/var/lib/linasbot/meta-ha")
backup = state_root / "env.before"
expected_sha = os.environ["EXPECTED_RELEASE_SHA"]
probe = state_root / ".commit_probe"

def _preflight_stage_authority(
    state_root: Path,
    *,
    expected_sha: str,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        return sync._require_stage_authority(
            state_root,
            expected_sha=expected_sha,
            require_preimage=False,
        )
    except RuntimeError as exc:
        message = str(exc)
        if (
            "must remain disabled" not in message
            and "does not match durable state" not in message
        ):
            raise
        authority = sync._load_stage_authority(state_root)
        worker_state = sync._load_worker_state(state_root)
        if authority is None or worker_state is None:
            raise
        values = sync._read_meta_values(sync.ENV_PATH)
        sync._verify_runtime_values(values, expected_node_id=sync.LOCAL_NODE_ID)
        sync._verify_worker_units_restored(
            worker_state,
            values,
            expected_node_id=sync.LOCAL_NODE_ID,
        )
        return authority, worker_state

checks = {
    "backup_exists": lambda: backup.exists(),
    "backup_read": lambda: backup.read_bytes(),
    "runtime_meta": lambda: sync._read_runtime_meta_values(sync.LOCAL_NODE_ID),
    "backup_meta": lambda: sync._read_meta_values(backup),
    "samefile_self": lambda: backup.samefile(backup),
    "journal_absent": lambda: sync._load_journal(state_root),
    "atomic_write_probe": lambda: sync._atomic_write_bytes(probe, b"ok\n"),
    "stage_authority": lambda: _preflight_stage_authority(
        state_root,
        expected_sha=expected_sha,
    ),
}
for name, fn in checks.items():
    try:
        result = fn()
        if name == "journal_absent":
            print(f"[wa-phase1-commit-preflight] {name}={result is None}", flush=True)
        else:
            print(f"[wa-phase1-commit-preflight] {name}=ok", flush=True)
    except Exception as exc:
        print(
            f"[wa-phase1-commit-preflight] {name}={type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        traceback.print_exc()
        raise SystemExit(1) from exc
probe.unlink(missing_ok=True)
print("[wa-phase1-commit-preflight] COMPLETE_OK", flush=True)
PY
  commit_staged_non_meta_env_via_restart "[wa-phase1-ha]"
  TRANSACTION_COMPLETE=true
  MAINTENANCE_ARMED=false
  bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
    "$EXPECTED_RELEASE_SHA" cluster-release-only
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
}
