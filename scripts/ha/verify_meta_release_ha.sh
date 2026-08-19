#!/usr/bin/env bash
# Fail-closed release/runtime proof for privileged Meta production workflows.

set -euo pipefail

EXPECTED_RELEASE_SHA="${1:-${EXPECTED_RELEASE_SHA:-}}"
VERIFY_MODE="${2:-cluster}"
EXPECTED_META_ENV_FINGERPRINT="${3:-}"
EXPECTED_HA_NODE_ID="${4:-}"
REPO_DIR="/opt/linasbot"
PEER_HOST="${LINAS_HA_PEER_HOST:-10.106.0.4}"
WORKER_QUEUES=(high_priority interactive background expensive)

if [ "$(id -u)" -ne 0 ]; then
  echo "[meta-ha-release] verifier requires root privileges" >&2
  exit 1
fi

if [[ ! "$EXPECTED_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "[meta-ha-release] expected release SHA is invalid" >&2
  exit 1
fi
if [ "$VERIFY_MODE" != "cluster" ] && \
   [ "$VERIFY_MODE" != "cluster-release-only" ] && \
   [ "$VERIFY_MODE" != "local-only" ] && \
   [ "$VERIFY_MODE" != "local-release-only" ]; then
  echo "[meta-ha-release] verification mode is invalid" >&2
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1

verify_unit_runtime() {
  local unit="$1"
  local repo_dir="$2"
  local runtime_kind="$3"
  local queue_name="${4:-}"
  local verify_meta_environment="${5:-1}"
  local main_pid working_directory exec_start environment_files

  systemctl is-active --quiet "$unit"
  working_directory="$(systemctl show "$unit" --property=WorkingDirectory --value)"
  exec_start="$(systemctl show "$unit" --property=ExecStart --value)"
  environment_files="$(systemctl show "$unit" --property=EnvironmentFiles --value)"
  main_pid="$(systemctl show "$unit" --property=MainPID --value)"
  if [ "$working_directory" != "$repo_dir" ] || \
     [[ ! "$main_pid" =~ ^[1-9][0-9]*$ ]]; then
    echo "[meta-ha-release] unit runtime contract mismatch: $unit" >&2
    return 1
  fi
  "$repo_dir/venv/bin/python" -B - \
    "$repo_dir" "$runtime_kind" "$queue_name" "$main_pid" \
    "$exec_start" "$environment_files" <<'PY'
import os
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
runtime_kind = sys.argv[2]
queue_name = sys.argv[3]
pid = sys.argv[4]
exec_start = sys.argv[5]
environment_files = sys.argv[6]
expected_python = (repo / "venv/bin/python").resolve()
expected_env = str(repo / ".env")

env_paths = re.findall(r"/[^ ;}()]+", environment_files)
if env_paths != [expected_env]:
    raise SystemExit("systemd EnvironmentFiles contract mismatch")

if runtime_kind == "api":
    expected_script = repo / "main.py"
    expected_tail: list[str] = []
    expected_argv = f"argv[]={repo}/venv/bin/python main.py ;"
elif runtime_kind == "worker" and queue_name:
    expected_script = repo / "scripts/run_queue_worker.py"
    expected_tail = ["--queue", queue_name]
    expected_argv = (
        f"argv[]={repo}/venv/bin/python scripts/run_queue_worker.py --queue {queue_name} ;"
    )
else:
    raise SystemExit("runtime role contract is invalid")
if expected_argv not in exec_start:
    raise SystemExit("systemd ExecStart contract mismatch")

proc = Path("/proc") / pid
if Path(os.readlink(proc / "cwd")).resolve() != repo:
    raise SystemExit("live process cwd mismatch")
if Path(os.readlink(proc / "exe")).resolve() != expected_python:
    raise SystemExit("live process executable mismatch")
argv = [part.decode("utf-8", "strict") for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
if len(argv) < 2 or Path(argv[0]).resolve() != expected_python:
    raise SystemExit("live process interpreter mismatch")
script = Path(argv[1])
if not script.is_absolute():
    script = repo / script
if script.resolve() != expected_script.resolve() or argv[2:] != expected_tail:
    raise SystemExit("live process argv mismatch")
PY
  if [ "$verify_meta_environment" != "1" ]; then
    return 0
  fi
  "$repo_dir/venv/bin/python" -B - "$repo_dir/.env" "/proc/$main_pid/environ" <<'PY'
import sys
from pathlib import Path

from dotenv import dotenv_values

env_path = Path(sys.argv[1])
process_env_path = Path(sys.argv[2])
expected = {
    str(key): "" if value is None else str(value)
    for key, value in dotenv_values(env_path, interpolate=False).items()
    if str(key).startswith("META_")
}
actual = {}
for entry in process_env_path.read_bytes().split(b"\0"):
    if b"=" not in entry:
        continue
    raw_key, raw_value = entry.split(b"=", 1)
    key = raw_key.decode("utf-8", "strict")
    if key.startswith("META_"):
        actual[key] = raw_value.decode("utf-8", "strict")
if not expected or actual != expected:
    raise SystemExit("Meta process environment is stale")
PY
}

verify_local_readiness() {
  local repo_dir="$1"
  local durable_queues_on="$2"

  "$repo_dir/venv/bin/python" -B - "$durable_queues_on" <<'PY'
import json
import sys
import urllib.request

paths = ["/api/ready"]
if sys.argv[1] == "1":
    paths.append("/api/queue/ready")
for path in paths:
    with urllib.request.urlopen("http://127.0.0.1:8003" + path, timeout=5) as response:
        payload = json.load(response)
    if response.status != 200 or payload.get("ok") is not True:
        raise SystemExit(f"local readiness failed: {path}")
PY
}

verify_nginx_contract() {
  local repo_dir="$1"

  systemctl is-active --quiet nginx
  nginx -t >/dev/null 2>&1
  test -f /etc/nginx/sites-available/linasaibot
  test -L /etc/nginx/sites-enabled/linasaibot
  test "$(readlink -f /etc/nginx/sites-enabled/linasaibot)" = \
    "$(readlink -f /etc/nginx/sites-available/linasaibot)"
  cmp -s "$repo_dir/deploy/nginx-linasaibot.conf" /etc/nginx/sites-available/linasaibot
  cmp -s "$repo_dir/deploy/nginx-privacy-log.conf" /etc/nginx/conf.d/linasbot-privacy-log.conf
}

reject_shadow_runtime() {
  if systemctl is-active --quiet linas_ai_bot.service || \
     systemctl is-enabled --quiet linas_ai_bot.service; then
    echo "[meta-ha-release] legacy linas_ai_bot service is still enabled or active" >&2
    return 1
  fi
  if ss -H -ltnp 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:8000([[:space:]]|$)'; then
    echo "[meta-ha-release] legacy port 8000 listener is still active" >&2
    return 1
  fi
}

reject_self_peer() {
  local peer_host="$1"
  local peer_addresses local_addresses

  peer_addresses="$(getent ahostsv4 "$peer_host" | awk '{print $1}' | sort -u)"
  local_addresses="$({ hostname -I 2>/dev/null || true; ip -o -4 addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1; } | tr ' ' '\n' | sed '/^$/d' | sort -u)"
  if [ -z "$peer_addresses" ] || grep -Fxf <(printf '%s\n' "$peer_addresses") \
    <(printf '%s\n' "$local_addresses") >/dev/null; then
    echo "[meta-ha-release] HA peer is unavailable or resolves to this node" >&2
    return 1
  fi
}

meta_env_fingerprint() {
  local repo_dir="$1"
  local expected_sha="$2"

  "$repo_dir/venv/bin/python" -B - "$repo_dir/.env" "$expected_sha" <<'PY'
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2].encode("ascii")
name_re = re.compile(r"^META_[A-Z0-9_]+$")
excluded = {"META_DELETION_NODE_ID"}
values = {}
for raw_line in path.read_text(encoding="utf-8", errors="strict").splitlines():
    if not raw_line or raw_line.lstrip().startswith("#") or "=" not in raw_line:
        continue
    raw_name, value = raw_line.split("=", 1)
    name = raw_name.strip()
    if name_re.fullmatch(name) and name not in excluded:
        values[name] = value
if not values:
    raise SystemExit("canonical Meta environment is empty")
payload = json.dumps(values, separators=(",", ":"), sort_keys=True).encode("utf-8")
print(hmac.new(key, payload, hashlib.sha256).hexdigest())
PY
}

verify_deletion_membership() {
  local repo_dir="$1"
  local expected_node_id="$2"

  "$repo_dir/venv/bin/python" -B - "$repo_dir/.env" "$expected_node_id" <<'PY'
import sys
from pathlib import Path

from dotenv import dotenv_values

values = dotenv_values(Path(sys.argv[1]), interpolate=False)
node_id = str(values.get("META_DELETION_NODE_ID") or "").strip()
required = {
    item.strip()
    for item in str(values.get("META_DELETION_REQUIRED_NODES") or "").split(",")
    if item.strip()
}
if node_id != sys.argv[2] or required != {"node01", "node02"}:
    raise SystemExit("Meta deletion HA membership is invalid")
PY
}

verify_operator_gates() {
  local repo_dir="$1"

  "$repo_dir/venv/bin/python" -B - "$repo_dir" "$repo_dir/.env" "$VERIFY_MODE" <<'PY'
import sys
from pathlib import Path

from dotenv import dotenv_values

sys.path.insert(0, sys.argv[1])
from services.meta_surface_secret_separation import (
    COLLISION_EXIT,
    operator_gate_allows_separation,
)

values = dotenv_values(Path(sys.argv[2]), interpolate=False)
verify_mode = sys.argv[3]
registry_backend = str(values.get("META_REGISTRY_BACKEND") or "").strip().lower()
if registry_backend != "postgres":
    raise SystemExit("Meta app registry backend must be explicit postgres")
lb_ready = str(values.get("META_HA_LB_READY_HEALTHCHECK_APPROVED") or "").strip().lower()
if lb_ready != "true":
    raise SystemExit("LB /api/ready health-check approval is missing")
try:
    drain_seconds = int(str(values.get("META_HA_LB_DRAIN_SECONDS") or ""))
except ValueError as exc:
    raise SystemExit("HA drain interval is invalid") from exc
if not 30 <= drain_seconds <= 300:
    raise SystemExit("HA drain interval is outside the approved range")
coerced = {str(key): str(value or "") for key, value in values.items()}
if not operator_gate_allows_separation(coerced, verify_mode=verify_mode):
    raise SystemExit(COLLISION_EXIT)
PY
}

verify_node() {
  local repo_dir="$1"
  local expected_sha="$2"
  local verify_runtime_state="${3:-1}"
  local deployed_sha queue durable_queues_on untracked_runtime

  test -f "$repo_dir/main.py"
  test -x "$repo_dir/venv/bin/python"
  test -f "$repo_dir/.env"
  test ! -L "$repo_dir/.env"
  if [ "$(stat -c '%u:%g:%a' "$repo_dir/.env")" != "0:0:600" ]; then
    echo "[meta-ha-release] canonical environment ownership or mode is unsafe" >&2
    return 1
  fi
  test -f "$repo_dir/scripts/ha/verify_meta_release_ha.sh"
  if [ -e "$repo_dir/linaslaserbot-2.7.22/main.py" ] || \
     [ -e "$repo_dir/linaslaserbot-2.7.22/venv/bin/python" ]; then
    echo "[meta-ha-release] legacy nested runtime still exists" >&2
    return 1
  fi
  deployed_sha="$(git -C "$repo_dir" rev-parse HEAD)"
  if [ "$deployed_sha" != "$expected_sha" ]; then
    echo "[meta-ha-release] deployed release mismatch" >&2
    return 1
  fi
  if ! git -C "$repo_dir" diff --quiet "$deployed_sha" -- || \
     ! git -C "$repo_dir" diff --cached --quiet "$deployed_sha" --; then
    echo "[meta-ha-release] deployed tracked files differ from release" >&2
    return 1
  fi
  git -C "$repo_dir" ls-files --error-unmatch \
    main.py deploy.sh scripts/ha/verify_meta_release_ha.sh \
    scripts/ha/sync_meta_env_to_peer.py \
    scripts/ha/run_with_canonical_meta_env.py \
    scripts/ha/meta_env_file.py \
    deploy/systemd/linasbot-worker@.service >/dev/null
  untracked_runtime="$(
    git -C "$repo_dir" ls-files --others --exclude-standard -- \
      '*.py' '*.sh' '*.yml' '*.yaml' ':!venv/**' ':!dashboard/node_modules/**'
  )"
  if [ -n "$untracked_runtime" ]; then
    echo "[meta-ha-release] untracked runtime source exists" >&2
    return 1
  fi

  reject_shadow_runtime
  verify_nginx_contract "$repo_dir"
  verify_unit_runtime linasbot "$repo_dir" api "" "$verify_runtime_state"

  durable_queues_on=0
  if grep -Eq '^[[:space:]]*(REDIS_URL|LINAS_REDIS_URL)=' "$repo_dir/.env" \
    && grep -Eq '^[[:space:]]*(LINAS_REQUIRE_REDIS|LINAS_ENABLE_DURABLE_QUEUES)=(1|true|yes|on)' \
      "$repo_dir/.env"; then
    durable_queues_on=1
  fi
  for queue in "${WORKER_QUEUES[@]}"; do
    if [ "$durable_queues_on" = "1" ] || systemctl is-enabled --quiet "linasbot-worker@${queue}.service"; then
      verify_unit_runtime \
        "linasbot-worker@${queue}.service" "$repo_dir" worker "$queue" "$verify_runtime_state"
    elif systemctl is-active --quiet "linasbot-worker@${queue}.service"; then
      verify_unit_runtime \
        "linasbot-worker@${queue}.service" "$repo_dir" worker "$queue" "$verify_runtime_state"
    fi
  done
  if [ "$verify_runtime_state" = "1" ]; then
    verify_local_readiness "$repo_dir" "$durable_queues_on"
  fi
}

VERIFY_RUNTIME_STATE=1
if [ "$VERIFY_MODE" = "cluster-release-only" ] || [ "$VERIFY_MODE" = "local-release-only" ]; then
  VERIFY_RUNTIME_STATE=0
fi
verify_node "$REPO_DIR" "$EXPECTED_RELEASE_SHA" "$VERIFY_RUNTIME_STATE"
LOCAL_META_ENV_FINGERPRINT="$(meta_env_fingerprint "$REPO_DIR" "$EXPECTED_RELEASE_SHA")"

if [ -z "$EXPECTED_HA_NODE_ID" ]; then
  if [ "$VERIFY_MODE" = "local-only" ] || [ "$VERIFY_MODE" = "local-release-only" ]; then
    EXPECTED_HA_NODE_ID=node02
  else
    EXPECTED_HA_NODE_ID=node01
  fi
fi
verify_deletion_membership "$REPO_DIR" "$EXPECTED_HA_NODE_ID"
verify_operator_gates "$REPO_DIR"

if [ "$VERIFY_MODE" = "local-only" ] || [ "$VERIFY_MODE" = "local-release-only" ]; then
  if [ -n "$EXPECTED_META_ENV_FINGERPRINT" ]; then
    if [[ ! "$EXPECTED_META_ENV_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]] || \
       [ "$LOCAL_META_ENV_FINGERPRINT" != "$EXPECTED_META_ENV_FINGERPRINT" ]; then
      echo "[meta-ha-release] cluster Meta environment mismatch" >&2
      exit 1
    fi
  fi
  echo "[meta-ha-release] exact release and canonical local runtime verified"
  exit 0
fi

reject_self_peer "$PEER_HOST"
if [ "$VERIFY_MODE" = "cluster-release-only" ]; then
  ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    PYTHONDONTWRITEBYTECODE=1 \
    bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
      "$EXPECTED_RELEASE_SHA" local-release-only
else
  ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o StrictHostKeyChecking=yes \
    "root@${PEER_HOST}" \
    PYTHONDONTWRITEBYTECODE=1 \
    bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
      "$EXPECTED_RELEASE_SHA" local-only "$LOCAL_META_ENV_FINGERPRINT" node02
fi

echo "[meta-ha-release] exact release and canonical runtime verified on both nodes"
