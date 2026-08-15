#!/bin/bash
# Transactional, fail-closed two-node production release deployment.
#
# This file is executed from the exact authorized Git object by deploy.yml.  It
# deliberately keeps every changed node out of the load balancer, then keeps
# both nodes drained once target parity is reached and until a separately
# confirmed commit admits them. The load balancer owner must first attest that
# its health check is exactly /api/ready.

set -euo pipefail
umask 077
while IFS='=' read -r -d '' ambient_name _; do
  case "$ambient_name" in
    PYTHON* | BASH_FUNC_* | BASH_ENV | ENV | CDPATH | GLOBIGNORE | IFS | SHELLOPTS | BASHOPTS | \
      LD_* | DYLD_* | GIT_* | NODE_OPTIONS | NODE_PATH | PERL5LIB | PERL5OPT | \
      RUBYLIB | RUBYOPT | GCONV_PATH | GLIBC_TUNABLES | LOCPATH | NLSPATH | \
      MALLOC_TRACE | SSLKEYLOGFILE)
      printf '[ha-deploy] ERROR: ambient execution-control variable is forbidden: %s\n' \
        "$ambient_name" >&2
      exit 1
      ;;
  esac
done < <(/usr/bin/env -0)
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONDONTWRITEBYTECODE=1

git() {
  /usr/bin/env -i \
    HOME=/nonexistent \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    GIT_NO_REPLACE_OBJECTS=1 \
    GIT_ATTR_NOSYSTEM=1 \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null \
    /usr/bin/git --no-replace-objects -c core.hooksPath=/dev/null "$@"
}

REPO_DIR=/opt/linasbot
META_HA_STATE_ROOT=/var/lib/linasbot/meta-ha
MAINTENANCE_FILE=$META_HA_STATE_ROOT/maintenance
VOLATILE_MAINTENANCE_FILE=/run/linasbot-maintenance
BOOTSTRAP_ACTIVE_FILE=$META_HA_STATE_ROOT/bootstrap.active
BOOTSTRAP_COORDINATOR_FILE=$META_HA_STATE_ROOT/bootstrap.coordinator.json
SYNC_JOURNAL_FILE=$META_HA_STATE_ROOT/transaction.json
SYNC_ENV_BACKUP_FILE=$META_HA_STATE_ROOT/env.before
BOOTSTRAP_COMMIT_PROOF_FILE=$META_HA_STATE_ROOT/bootstrap.last-committed.json
DEPLOY_ACTIVE_FILE=$META_HA_STATE_ROOT/deploy.active
DEPLOY_NODE_ACTIVE_FILE=$META_HA_STATE_ROOT/deploy-node.active
PYTHON_RUNTIME_PROVISION_ACTIVE_FILE=$META_HA_STATE_ROOT/python-runtime-provision.active
PYTHON_RUNTIME_PROVISION_COORDINATOR_FILE=$META_HA_STATE_ROOT/python-runtime-provision.coordinator.json
CONTROLLED_FAILOVER_ACTIVE_FILE=$META_HA_STATE_ROOT/controlled-failover.active
CONTROLLED_FAILOVER_RUNTIME_GUARD_FILE=$META_HA_STATE_ROOT/controlled-failover.runtime.guard
BOOTSTRAP_RUNTIME_GUARD_FILE=$META_HA_STATE_ROOT/bootstrap.runtime.guard
REGISTRY_NFS_RETIRE_ACTIVE_FILE=$META_HA_STATE_ROOT/registry-nfs-retire.active
LEGACY_RETIREMENT_MARKER=$META_HA_STATE_ROOT/legacy-linas-ai-bot-retired
LEGACY_RETIREMENT_GUARD=/etc/systemd/system/linas_ai_bot.service.d/90-linasbot-retired.conf
LOCK_FILE=/run/lock/linasbot-meta-live.lock
BACKUP_ROOT=/var/backups/linasbot-ha
HELPER_REPO_PATH=scripts/ha/deploy_meta_release_ha.sh
CLUSTER_ENV_HELPER_REPO_PATH=scripts/ha/cluster_runtime_env_contract.py
PRODUCTION_GUARD_REPO_PATH=scripts/ha/production_mutation_guard.py
RELEASE_VERIFY_REPO_PATH=scripts/ha/release_verify_server.py
RELEASE_READINESS_REPO_PATH=scripts/ha/release_readiness_probe.py
RELEASE_ALEMBIC_MIGRATE_REPO_PATH=scripts/ha/release_alembic_migrate.py
LB_MANAGER_REPO_PATH=scripts/ha/manage_do_lb_ready_healthcheck.py
LB_CONTRACT_REPO_PATH=scripts/ha/do_lb_ready_contract.py
RELEASE_ARTIFACT_CONTRACT_REPO_PATH=scripts/ha/release_artifact_contract.py
RELEASE_ARCHIVE_CONTRACT_REPO_PATH=scripts/ha/release_archive_contract.py
REQUIREMENTS_LOCK_REPO_PATH=requirements.lock
LB_ATTESTATION_PREFIX=$META_HA_STATE_ROOT/lb-ready-deploy-
RELEASE_BUNDLE_ROOT=$META_HA_STATE_ROOT/release-bundles
RELEASE_BUNDLE_RECEIPT_ROOT=$META_HA_STATE_ROOT/release-bundle-receipts
RELEASE_IMPORT_INTENT_ROOT=$META_HA_STATE_ROOT/release-import-intents
RELEASE_INCOMING_PREFIX=/run/linasbot-release-import.
EXPECTED_GITHUB_REPOSITORY=MahmoudAlZougbhi/linasbot-server
EXPECTED_QG_WORKFLOW_REF=$EXPECTED_GITHUB_REPOSITORY/.github/workflows/quality-gates.yml@refs/heads/main
PYTHON_RUNTIME_ROOT=/opt/linasbot-runtime/cpython-3.13.15
SYSTEM_PYTHON=$PYTHON_RUNTIME_ROOT/bin/python3.13
REQUIRED_PYTHON_VERSION=3.13.15
REQUIRED_PYTHON_CACHE_TAG=cpython-313
REQUIRED_PYTHON_SOABI=cpython-313-x86_64-linux-gnu
REQUIRED_PYTHON_MACHINE=x86_64
PYTHON_RUNTIME_LOCAL_RECEIPT=$META_HA_STATE_ROOT/python-runtime-provisioned.json
PYTHON_RUNTIME_CLUSTER_RECEIPT=$META_HA_STATE_ROOT/python-runtime-cluster.json
PYTHON_RUNTIME_ARTIFACT=cpython-3.13.15+20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz
PYTHON_RUNTIME_ARTIFACT_SHA256=aaca2af2ab4d7b68a712660d1334c0cfd5ec13c0312ccd30c29122d8d0342320
PYTHON_RUNTIME_SOURCE_SHA256=1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76
PYTHON_EXECUTABLE_SHA256=ce20f82411f2b0ccdf3e2212ca62303519521d73d25178588f1a9c8d4935c866
PYTHON_RUNTIME_TREE_SHA256=e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc
PYTHON_LIBPYTHON=$PYTHON_RUNTIME_ROOT/lib/libpython3.13.so.1.0
PYTHON_LIBPYTHON_SHA256=965dcc1afd5934923b5a930e54afcaafc572485394ae33c35d27038bd943dcc5
REQUIRED_PIP_VERSION=26.2.1
DEFAULT_PEER_HOST=10.106.0.4
# Protocol fence for coordinator-to-node RPC. This is deliberately not a
# secret and is not a security boundary against root; it prevents legacy or
# accidental direct use of the helper's single-node implementation phases.
INTERNAL_NODE_DISPATCH_CONFIRM=LINAS_HA_COORDINATOR_INTERNAL_NODE_RPC_V1
VERIFY_API_UNIT=linasbot-ha-verify.service
VERIFY_READINESS_UNIT=linasbot-ha-readiness-probe.service
WORKER_QUEUES=(high_priority interactive background expensive)
SSH_OPTIONS=(
  -o BatchMode=yes
  -o ConnectTimeout=8
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=3
  -o StrictHostKeyChecking=yes
)

log() {
  printf '[ha-deploy] %s\n' "$*"
}

die() {
  printf '[ha-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

require_internal_node_dispatch() {
  test "${1:-}" = "$INTERNAL_NODE_DISPATCH_CONFIRM" || \
    die "single-node release phases are internal-only; use a two-node coordinator operation"
}

run_system_python_control() {
  /usr/bin/env -i \
    HOME=/nonexistent \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    GIT_NO_REPLACE_OBJECTS=1 \
    GIT_ATTR_NOSYSTEM=1 \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null \
    "$SYSTEM_PYTHON" -B -I -S "$@"
}

assert_os_python_verifier_anchor() {
  local path resolved
  for path in /usr /usr/bin; do
    test -d "$path" && test ! -L "$path" || \
      die "OS verifier path component is missing or symlinked: $path"
    test "$(/usr/bin/stat -c '%F:%u:%g:%a' "$path")" = "directory:0:0:755" || \
      die "OS verifier path component is unsafe: $path"
    test "$(/usr/bin/realpath -e "$path")" = "$path" || \
      die "OS verifier path component is aliased: $path"
  done
  test -L /usr/bin/python3 || die "OS-maintained Python verifier link is missing"
  test "$(/usr/bin/stat -c '%u:%g' /usr/bin/python3)" = "0:0" || \
    die "OS-maintained Python verifier link is not root-owned"
  case "$(/usr/bin/readlink /usr/bin/python3)" in
    python3.[0-9] | python3.[0-9][0-9]) ;;
    *) die "OS-maintained Python verifier link target is unexpected" ;;
  esac
  resolved="$(/usr/bin/realpath -e /usr/bin/python3)"
  case "$resolved" in
    /usr/bin/python3.[0-9] | /usr/bin/python3.[0-9][0-9]) ;;
    *) die "OS-maintained Python verifier resolves outside /usr/bin" ;;
  esac
  test "$(/usr/bin/stat -c '%F:%u:%g:%a:%h' "$resolved")" = \
    "regular file:0:0:755:1" || die "OS-maintained Python verifier target is unsafe"
}

run_os_python_receipt_verifier() {
  assert_os_python_verifier_anchor
  /usr/bin/env -i \
    HOME=/nonexistent \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    GIT_NO_REPLACE_OBJECTS=1 \
    GIT_ATTR_NOSYSTEM=1 \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null \
    /usr/bin/python3 -B -I -S "$@"
}

assert_python_runtime_tree_pristine_os() {
  local digest
  digest="$(run_os_python_receipt_verifier - "$PYTHON_RUNTIME_ROOT" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
root_info = root.lstat()
if (
    not stat.S_ISDIR(root_info.st_mode)
    or stat.S_ISLNK(root_info.st_mode)
    or root_info.st_uid != 0
    or root_info.st_gid != 0
    or stat.S_IMODE(root_info.st_mode) != 0o755
):
    raise SystemExit("Python runtime root is unsafe")
digest = hashlib.sha256()


def update(record: dict[str, object]) -> None:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big") + encoded)


update({"path": ".", "type": "directory", "mode": stat.S_IMODE(root_info.st_mode)})
for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
    current_path = Path(current)
    dirnames.sort()
    filenames.sort()
    for name in [*dirnames, *filenames]:
        path = current_path / name
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if info.st_uid != 0 or info.st_gid != 0:
            raise SystemExit("Python runtime tree ownership is unsafe")
        record: dict[str, object] = {"path": relative, "mode": stat.S_IMODE(info.st_mode)}
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            try:
                path.resolve(strict=True).relative_to(root)
            except (OSError, ValueError) as exc:
                raise SystemExit("Python runtime symlink escapes its immutable root") from exc
            record.update({"type": "symlink", "target": target})
        elif stat.S_ISDIR(info.st_mode):
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise SystemExit("Python runtime directory is group/world writable")
            record["type"] = "directory"
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise SystemExit("Python runtime file is group/world writable")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(descriptor)
                if (info.st_dev, info.st_ino, info.st_size) != (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                ):
                    raise SystemExit("Python runtime file changed while opening")
                file_digest = hashlib.sha256()
                consumed = 0
                while True:
                    chunk = os.read(descriptor, 1 << 20)
                    if not chunk:
                        break
                    consumed += len(chunk)
                    file_digest.update(chunk)
                if consumed != opened.st_size:
                    raise SystemExit("Python runtime file changed while hashing")
            finally:
                os.close(descriptor)
            record.update({"type": "file", "size": info.st_size, "sha256": file_digest.hexdigest()})
        else:
            raise SystemExit("Python runtime tree contains an unsupported object")
        update(record)
print(digest.hexdigest())
PY
  )"
  test "$digest" = "$PYTHON_RUNTIME_TREE_SHA256" || \
    die "canonical Python runtime tree differs from the reviewed pristine artifact"
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    die "root privileges are required"
  fi
}

ensure_meta_ha_state_root() {
  if [ -e "$META_HA_STATE_ROOT" ] || [ -L "$META_HA_STATE_ROOT" ]; then
    test -d "$META_HA_STATE_ROOT" && test ! -L "$META_HA_STATE_ROOT" || \
      die "Meta HA state root is not a safe directory"
  else
    install -d -o root -g root -m 0700 "$META_HA_STATE_ROOT"
  fi
  test "$(stat -c '%u:%g:%a' "$META_HA_STATE_ROOT")" = "0:0:700" || \
    die "Meta HA state root ownership or mode is unsafe"
}

assert_path_absent() {
  local path="$1"
  local label="$2"
  if [ -e "$path" ] || [ -L "$path" ]; then
    die "$label"
  fi
}

assert_no_other_meta_transaction() {
  ensure_meta_ha_state_root
  assert_path_absent "$BOOTSTRAP_ACTIVE_FILE" "Meta HA bootstrap transaction is active or unsafe"
  assert_path_absent "$BOOTSTRAP_COORDINATOR_FILE" \
    "interrupted Meta HA bootstrap coordinator decision requires confirmed recovery"
  assert_path_absent "$BOOTSTRAP_RUNTIME_GUARD_FILE" \
    "interrupted Meta HA bootstrap runtime guard requires confirmed recovery"
  assert_path_absent "$SYNC_JOURNAL_FILE" "Meta environment synchronization journal is active or unsafe"
  assert_path_absent "$SYNC_ENV_BACKUP_FILE" "Meta environment synchronization backup is active or unsafe"
  assert_path_absent "$DEPLOY_ACTIVE_FILE" "interrupted HA release transaction requires confirmed recovery"
  assert_path_absent "$DEPLOY_NODE_ACTIVE_FILE" "interrupted per-node HA release transaction requires recovery"
  assert_path_absent "$PYTHON_RUNTIME_PROVISION_ACTIVE_FILE" \
    "Python runtime provisioning transaction is active or unsafe"
  assert_path_absent "$PYTHON_RUNTIME_PROVISION_COORDINATOR_FILE" \
    "Python runtime provisioning coordinator requires confirmed recovery"
  assert_path_absent "$CONTROLLED_FAILOVER_ACTIVE_FILE" \
    "controlled Meta failover evidence transaction is active or unsafe"
  assert_path_absent "$REGISTRY_NFS_RETIRE_ACTIVE_FILE" \
    "Meta registry NFS retirement transaction is active or unsafe"
}

write_deploy_journal() {
  local tx_id="$1"
  local target_sha="$2"
  local previous_sha="$3"
  local peer_previous_sha="$4"
  local peer_host="$5"
  local tx_dir="$6"
  local deploy_mode="$7"
  local bootstrap_plan="$8"
  local drain_seconds="$9"
  local phase="${10}"
  local decision="${11}"
  local helper_hash="${12}"
  local python_runtime_cluster_sha="${13}"
  local lb_attestation_sha="${14}"
  local lb_ready_projection_sha="${15}"
  local lb_observed_at="${16}"
  local release_artifact_id="${17}"
  local release_artifact_api_sha="${18}"
  local release_manifest_sha="${19}"
  local release_run_id="${20}"
  local release_run_attempt="${21}"
  local release_target_tree_sha="${22}"
  run_system_python_control - "$DEPLOY_ACTIVE_FILE" "$tx_id" "$target_sha" "$previous_sha" \
    "$peer_previous_sha" "$peer_host" "$tx_dir" "$deploy_mode" "$bootstrap_plan" \
    "$drain_seconds" "$phase" "$decision" "$helper_hash" \
    "$python_runtime_cluster_sha" "$lb_attestation_sha" \
    "$lb_ready_projection_sha" "$lb_observed_at" \
    "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
    "$release_run_id" "$release_run_attempt" "$release_target_tree_sha" <<'PY'
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

(
    raw_path, tx_id, target, node01_old, node02_old, peer, tx_dir, mode,
    bootstrap, drain, phase, decision, helper_sha, python_runtime_cluster_sha,
    lb_attestation_sha, lb_ready_projection_sha, lb_observed_at,
    release_artifact_id, release_artifact_api_sha, release_manifest_sha,
    release_run_id, release_run_attempt, release_target_tree_sha,
) = sys.argv[1:]
path = Path(raw_path)
if not re.fullmatch(r"[0-9a-f]{32}", tx_id):
    raise SystemExit("deployment transaction ID is invalid")
for value in (target, node01_old, node02_old):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise SystemExit("deployment journal SHA is invalid")
if not re.fullmatch(r"[0-9a-f]{64}", helper_sha):
    raise SystemExit("deployment helper digest is invalid")
if not re.fullmatch(r"[0-9a-f]{64}", python_runtime_cluster_sha):
    raise SystemExit("deployment Python runtime cluster digest is invalid")
for value in (lb_attestation_sha, lb_ready_projection_sha):
    if not re.fullmatch(r"[0-9a-f]{64}", value) or value == "0" * 64:
        raise SystemExit("deployment LB attestation digest is invalid")
if not re.fullmatch(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", lb_observed_at
):
    raise SystemExit("deployment LB attestation observation time is invalid")
if (
    not release_artifact_id.isdigit()
    or int(release_artifact_id) < 1
    or not release_run_id.isdigit()
    or int(release_run_id) < 1
    or not release_run_attempt.isdigit()
    or int(release_run_attempt) < 1
):
    raise SystemExit("deployment release artifact numeric identity is invalid")
for value in (release_artifact_api_sha, release_manifest_sha):
    if not re.fullmatch(r"[0-9a-f]{64}", value) or value == "0" * 64:
        raise SystemExit("deployment release artifact digest is invalid")
if not re.fullmatch(r"[0-9a-f]{40}", release_target_tree_sha):
    raise SystemExit("deployment release target tree is invalid")
if not re.fullmatch(r"[0-9a-f]{64}", bootstrap):
    raise SystemExit("deployment bootstrap digest is required")
if mode == "steady-confirmed":
    if node01_old != node02_old:
        raise SystemExit("steady deployment journal contract is invalid")
elif node01_old == node02_old:
    raise SystemExit("reconciliation deployment journal contract is invalid")
if peer != "10.106.0.4" or not re.fullmatch(
    rf"/var/backups/linasbot-ha/{target}-[0-9]{{14}}-[0-9]+", tx_dir
):
    raise SystemExit("deployment journal topology is invalid")
if mode not in {"steady-confirmed", "reconcile"} or decision not in {"rollback", "commit"}:
    raise SystemExit("deployment journal state is invalid")
if not re.fullmatch(r"[a-z0-9-]{3,64}", phase) or not 30 <= int(drain) <= 300:
    raise SystemExit("deployment journal phase or drain is invalid")
payload = {
    "schema": 1,
    "tx_id": tx_id,
    "target_sha": target,
    "node01_previous_sha": node01_old,
    "node02_previous_sha": node02_old,
    "peer_host": peer,
    "tx_dir": tx_dir,
    "deploy_mode": mode,
    "bootstrap_plan_sha256": bootstrap,
    "drain_seconds": int(drain),
    "phase": phase,
    "decision": decision,
    "helper_sha256": helper_sha,
    "python_runtime_cluster_sha256": python_runtime_cluster_sha,
    "lb_attestation_sha256": lb_attestation_sha,
    "lb_ready_projection_sha256": lb_ready_projection_sha,
    "lb_observed_at": lb_observed_at,
    "release_artifact_id": int(release_artifact_id),
    "release_artifact_api_sha256": release_artifact_api_sha,
    "release_manifest_sha256": release_manifest_sha,
    "release_run_id": int(release_run_id),
    "release_run_attempt": int(release_run_attempt),
    "release_target_tree_sha": release_target_tree_sha,
}
parent = path.parent
parent_info = os.lstat(parent)
if (
    not stat.S_ISDIR(parent_info.st_mode)
    or stat.S_ISLNK(parent_info.st_mode)
    or parent_info.st_uid != 0
    or parent_info.st_gid != 0
    or stat.S_IMODE(parent_info.st_mode) != 0o700
):
    raise SystemExit("deployment journal parent is unsafe")
if path.exists() or path.is_symlink():
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o600
    ):
        raise SystemExit("deployment journal is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise SystemExit("deployment journal changed while opened")
        current = json.loads(os.read(fd, 65536))
    finally:
        os.close(fd)
    immutable = set(payload) - {
        "phase", "decision", "lb_attestation_sha256",
        "lb_ready_projection_sha256", "lb_observed_at",
    }
    if set(current) != set(payload) or any(current.get(key) != payload[key] for key in immutable):
        raise SystemExit("deployment journal immutable contract changed")
    if current.get("decision") == "commit" and payload.get("decision") != "commit":
        raise SystemExit("durable deployment commit decision cannot be reversed")
    changed_lb = any(
        current.get(key) != payload[key]
        for key in (
            "lb_attestation_sha256", "lb_ready_projection_sha256", "lb_observed_at"
        )
    )
    if changed_lb and phase not in {
        "recovery-lb-attested", "retry-lb-attested", "commit-lb-attested"
    }:
        raise SystemExit("deployment LB attestation can change only at a confirmed recovery boundary")
elif phase != "preflight-proven" or decision != "rollback":
    raise SystemExit("deployment journal must begin before the first mutation")
fd, temporary_name = tempfile.mkstemp(prefix=".deploy.active.", dir=parent)
temporary = Path(temporary_name)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        fd = -1
        json.dump(payload, handle, allow_nan=False, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    os.chown(path, 0, 0, follow_symlinks=False)
    os.chmod(path, 0o600, follow_symlinks=False)
    directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    if fd >= 0:
        os.close(fd)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY
}

deploy_journal_digest() {
  test -f "$DEPLOY_ACTIVE_FILE" && test ! -L "$DEPLOY_ACTIVE_FILE" || \
    die "deployment recovery journal is missing or unsafe"
  test "$(stat -c '%u:%g:%a' "$DEPLOY_ACTIVE_FILE")" = "0:0:600" || \
    die "deployment recovery journal ownership or mode is unsafe"
  sha256sum "$DEPLOY_ACTIVE_FILE" | awk '{print $1}'
}

clear_deploy_journal() {
  local expected_digest="$1"
  test "$(deploy_journal_digest)" = "$expected_digest" || \
    die "deployment journal changed before final cleanup"
  unlink "$DEPLOY_ACTIVE_FILE"
  run_system_python_control - "$META_HA_STATE_ROOT" <<'PY'
import os, sys
fd = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

assert_secure_maintenance_marker() {
  local marker="$1"
  test -f "$marker" && test ! -L "$marker" || die "maintenance marker is not a safe regular file"
  test "$(stat -c '%u:%g:%a' "$marker")" = "0:0:600" || \
    die "maintenance marker ownership or mode is unsafe"
}

arm_maintenance_markers() {
  ensure_meta_ha_state_root
  if [ -L "$MAINTENANCE_FILE" ]; then
    die "persistent maintenance marker is an unsafe symlink"
  elif [ ! -e "$MAINTENANCE_FILE" ]; then
    write_private_state "$MAINTENANCE_FILE" ""
  fi
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  if [ -L "$VOLATILE_MAINTENANCE_FILE" ]; then
    die "volatile maintenance marker is an unsafe symlink"
  elif [ ! -e "$VOLATILE_MAINTENANCE_FILE" ]; then
    write_private_state "$VOLATILE_MAINTENANCE_FILE" ""
  fi
  assert_secure_maintenance_marker "$VOLATILE_MAINTENANCE_FILE"
  # The persistent marker is part of the reboot authority.  The volatile
  # compatibility marker is also fsynced so a successful mark ACK never races
  # an unflushed file on filesystems that support directory durability.
  fsync_path_and_parents \
    "$MAINTENANCE_FILE" "$META_HA_STATE_ROOT" \
    "$VOLATILE_MAINTENANCE_FILE" /run
}

assert_deploy_node_sentinel() {
  local tx_dir="$1"
  test -f "$DEPLOY_NODE_ACTIVE_FILE" && test ! -L "$DEPLOY_NODE_ACTIVE_FILE" || \
    die "per-node deploy sentinel is missing or unsafe"
  test "$(stat -c '%u:%g:%a' "$DEPLOY_NODE_ACTIVE_FILE")" = "0:0:600" || \
    die "per-node deploy sentinel ownership or mode is unsafe"
  test "$(stat -c '%h' "$DEPLOY_NODE_ACTIVE_FILE")" = "1" || \
    die "per-node deploy sentinel has an unsafe link count"
  test "$(<"$DEPLOY_NODE_ACTIVE_FILE")" = "$tx_dir" || \
    die "per-node deploy sentinel belongs to another transaction"
}

arm_deploy_node_sentinel() {
  local tx_dir="$1"
  validate_tx_dir "$tx_dir"
  ensure_meta_ha_state_root
  if [ -e "$DEPLOY_NODE_ACTIVE_FILE" ] || [ -L "$DEPLOY_NODE_ACTIVE_FILE" ]; then
    assert_deploy_node_sentinel "$tx_dir"
    return 0
  fi
  run_system_python_control - "$DEPLOY_NODE_ACTIVE_FILE" "$tx_dir" <<'PY'
import os, sys, tempfile
path, tx_dir = sys.argv[1:]
parent = os.path.dirname(path)
fd, temporary = tempfile.mkstemp(prefix=".deploy-node.active.", dir=parent)
try:
    os.fchmod(fd, 0o600)
    os.fchown(fd, 0, 0)
    os.write(fd, (tx_dir + "\n").encode("ascii"))
    os.fsync(fd)
    os.close(fd)
    fd = -1
    if os.path.lexists(path):
        raise SystemExit("per-node deploy sentinel destination raced")
    os.replace(temporary, path)
    directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    if fd >= 0:
        os.close(fd)
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
  assert_deploy_node_sentinel "$tx_dir"
}

clear_deploy_node_sentinel() {
  local tx_dir="$1"
  assert_deploy_node_sentinel "$tx_dir"
  unlink "$DEPLOY_NODE_ACTIVE_FILE"
  run_system_python_control - "$META_HA_STATE_ROOT" <<'PY'
import os, sys
fd = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

admission_proof_is_exact() {
  local tx_dir="$1"
  local expected_sha="$2"
  local proof="$tx_dir/admission.complete"
  validate_tx_dir "$tx_dir"
  validate_sha "$expected_sha"
  test -f "$proof" && test ! -L "$proof" || return 1
  test "$(stat -c '%u:%g:%a' "$proof")" = "0:0:600" || return 1
  test "$(<"$proof")" = "$expected_sha"
}

write_exact_sha_proof() {
  local tx_dir="$1"
  local expected_sha="$2"
  local proof_name="$3"
  local proof="$tx_dir/$proof_name"
  validate_tx_dir "$tx_dir"
  validate_sha "$expected_sha"
  case "$proof_name" in
    pre-admission.complete | admission.complete) ;;
    *) die "admission proof name is invalid" ;;
  esac
  if [ -e "$proof" ] || [ -L "$proof" ]; then
    test -f "$proof" && test ! -L "$proof" && \
      test "$(stat -c '%u:%g:%a' "$proof")" = "0:0:600" && \
      test "$(<"$proof")" = "$expected_sha" || \
      die "existing admission proof is unsafe or belongs to another release"
    return 0
  fi
  run_system_python_control - "$proof" "$expected_sha" <<'PY'
import os
import re
import sys
import tempfile

path, expected_sha = sys.argv[1:]
parent = os.path.dirname(path)
fd, temporary = tempfile.mkstemp(prefix=".admission.complete.", dir=parent)
try:
    os.fchmod(fd, 0o600)
    os.fchown(fd, 0, 0)
    os.write(fd, (expected_sha + "\n").encode("ascii"))
    os.fsync(fd)
    os.close(fd)
    fd = -1
    os.replace(temporary, path)
    directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    if fd >= 0:
        os.close(fd)
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
  test -f "$proof" && test ! -L "$proof" && \
    test "$(stat -c '%u:%g:%a' "$proof")" = "0:0:600" && \
    test "$(<"$proof")" = "$expected_sha" || \
    die "durable admission proof readback failed"
}

write_pre_admission_proof() {
  write_exact_sha_proof "$1" "$2" pre-admission.complete
}

write_admission_proof() {
  write_exact_sha_proof "$1" "$2" admission.complete
  admission_proof_is_exact "$1" "$2" || die "final admission proof readback failed"
}

validate_sha() {
  [[ "${1:-}" =~ ^[0-9a-f]{40}$ ]] || die "release SHA is invalid"
}

validate_digest() {
  [[ "${1:-}" =~ ^[0-9a-f]{64}$ ]] || die "SHA-256 digest is invalid"
}

assert_python_runtime_binary_anchor() {
  local path kind mode owner links digest
  for path in /opt /opt/linasbot-runtime "$PYTHON_RUNTIME_ROOT"; do
    test -d "$path" && test ! -L "$path" || \
      die "canonical Python runtime path component is missing or symlinked: $path"
    test "$(/usr/bin/stat -c '%F:%u:%g:%a' "$path")" = "directory:0:0:755" || \
      die "canonical Python runtime path component is unsafe: $path"
    test "$(/usr/bin/realpath -e "$path")" = "$path" || \
      die "canonical Python runtime path component is aliased: $path"
  done
  for path in "$SYSTEM_PYTHON" "$PYTHON_LIBPYTHON"; do
    test -e "$path" && test ! -L "$path" || \
      die "canonical Python runtime anchor is missing or symlinked: $path"
    kind="$(/usr/bin/stat -c '%F' "$path")"
    mode="$(/usr/bin/stat -c '%a' "$path")"
    owner="$(/usr/bin/stat -c '%u:%g' "$path")"
    links="$(/usr/bin/stat -c '%h' "$path")"
    test "$kind" = "regular file" || die "Python runtime anchor is not a regular file: $path"
    test "$mode" = "755" || die "Python runtime anchor mode is not exact: $path"
    test "$owner" = "0:0" || die "Python runtime anchor ownership is not root:root: $path"
    test "$links" = "1" || die "Python runtime anchor has unsafe hard links: $path"
    test "$(/usr/bin/realpath -e "$path")" = "$path" || \
      die "Python runtime anchor path is not canonical: $path"
  done
  digest="$(/usr/bin/sha256sum "$SYSTEM_PYTHON" | /usr/bin/awk '{print $1}')"
  test "$digest" = "$PYTHON_EXECUTABLE_SHA256" || \
    die "canonical Python executable differs from the reviewed immutable artifact"
  digest="$(/usr/bin/sha256sum "$PYTHON_LIBPYTHON" | /usr/bin/awk '{print $1}')"
  test "$digest" = "$PYTHON_LIBPYTHON_SHA256" || \
    die "canonical libpython differs from the reviewed immutable artifact"
}

assert_python_runtime_contract() {
  local expected_node_id="${1:-}"
  local cluster_digest pip_version_output
  case "$expected_node_id" in
    "" | node01 | node02) ;;
    *) die "Python runtime validation received an invalid node identity" ;;
  esac
  assert_python_runtime_binary_anchor
  assert_python_runtime_tree_pristine_os
  for receipt in "$PYTHON_RUNTIME_LOCAL_RECEIPT" "$PYTHON_RUNTIME_CLUSTER_RECEIPT"; do
    test -f "$receipt" && test ! -L "$receipt" || \
      die "committed Python runtime receipt is missing or unsafe: $receipt"
    test "$(/usr/bin/stat -c '%F:%u:%g:%a:%h' "$receipt")" = \
      "regular file:0:0:600:1" || die "Python runtime receipt security is invalid: $receipt"
    test "$(/usr/bin/realpath -e "$receipt")" = "$receipt" || \
      die "Python runtime receipt path is not canonical: $receipt"
  done
  # The portable interpreter's executable and libpython bytes are first bound
  # with OS coreutils.  An OS-maintained isolated interpreter then authenticates
  # the complete receipt and runtime tree, so a modified portable stdlib cannot
  # forge its own tree proof.  Only after that proof may the portable runtime
  # execute its ABI self-check.
  cluster_digest="$(
    run_os_python_receipt_verifier - \
      "$PYTHON_RUNTIME_LOCAL_RECEIPT" \
      "$PYTHON_RUNTIME_CLUSTER_RECEIPT" \
      "$expected_node_id" \
      "$PYTHON_RUNTIME_ROOT" \
      "$SYSTEM_PYTHON" \
      "$REQUIRED_PYTHON_VERSION" \
      "$REQUIRED_PYTHON_CACHE_TAG" \
      "$REQUIRED_PYTHON_SOABI" \
      "$REQUIRED_PYTHON_MACHINE" \
      "$REQUIRED_PIP_VERSION" \
      "$PYTHON_RUNTIME_ARTIFACT" \
      "$PYTHON_RUNTIME_ARTIFACT_SHA256" \
      "$PYTHON_RUNTIME_SOURCE_SHA256" \
      "$PYTHON_EXECUTABLE_SHA256" \
      "$PYTHON_RUNTIME_TREE_SHA256" \
      "$META_HA_STATE_ROOT" <<'PY'
import hashlib
import json
import os
import platform
import re
import stat
import sys
import sysconfig
from pathlib import Path

(
    local_raw,
    cluster_raw,
    expected_node,
    runtime_raw,
    executable_raw,
    required_version,
    required_cache_tag,
    required_soabi,
    required_machine,
    required_pip,
    artifact_name,
    artifact_sha256,
    source_sha256,
    executable_sha256,
    expected_runtime_tree_sha256,
    state_root_raw,
) = sys.argv[1:]
local_path = Path(local_raw)
cluster_path = Path(cluster_raw)
runtime = Path(runtime_raw)
executable = Path(executable_raw)
state_root = Path(state_root_raw)
digest_re = re.compile(r"[0-9a-f]{64}")
transaction_re = re.compile(r"pyr_[0-9a-f]{32}")


def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def secure_read(path: Path, label: str) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or before.st_size > (1 << 20)
    ):
        raise SystemExit(f"{label} is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit(f"{label} changed while opening")
        payload = os.read(descriptor, (1 << 20) + 1)
        if len(payload) > (1 << 20) or os.read(descriptor, 1):
            raise SystemExit(f"{label} is oversized")
        return payload
    finally:
        os.close(descriptor)


def parse(raw: bytes, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw, object_pairs_hook=no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} is not a JSON object")
    return payload


def canonical(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


local_bytes = secure_read(local_path, "node Python runtime receipt")
cluster_bytes = secure_read(cluster_path, "cluster Python runtime receipt")
local = parse(local_bytes, "node Python runtime receipt")
cluster = parse(cluster_bytes, "cluster Python runtime receipt")
if local_bytes != canonical(local) or cluster_bytes != canonical(cluster):
    raise SystemExit("Python runtime receipt is not canonical JSON")
node_keys = {
    "schema", "format", "transaction_id", "decision", "status", "node_id",
    "required_nodes", "runtime_path", "python_executable", "python_version",
    "implementation", "cache_tag", "soabi", "platform_system", "machine",
    "pip_version", "artifact_repository", "artifact_release", "artifact_name",
    "artifact_sha256", "cpython_source_sha256", "runtime_tree_sha256",
    "wheelhouse_archive_sha256", "wheelhouse_tree_sha256",
    "wheelhouse_file_count", "wheelhouse_total_size",
    "python_executable_sha256", "plan_sha256", "qg_repository",
    "qg_workflow_ref", "qg_run_id", "qg_run_attempt", "qg_target_sha",
    "qg_artifact_id", "qg_artifact_api_sha256", "qg_manifest_sha256",
}
cluster_keys = (node_keys - {"node_id", "python_executable_sha256"}) | {
    "node_receipt_sha256"
}
if set(local) != node_keys or set(cluster) != cluster_keys:
    raise SystemExit("Python runtime receipt schema is not closed")
node_id = local.get("node_id")
if expected_node and node_id != expected_node:
    raise SystemExit("Python runtime receipt node identity is wrong")
if node_id not in {"node01", "node02"}:
    raise SystemExit("Python runtime receipt node identity is invalid")
fixed = {
    "schema": 2,
    "format": "linas-python-runtime-node-v2",
    "decision": "commit",
    "status": "committed",
    "required_nodes": ["node01", "node02"],
    "runtime_path": str(runtime),
    "python_executable": str(executable),
    "python_version": required_version,
    "implementation": "cpython",
    "cache_tag": required_cache_tag,
    "soabi": required_soabi,
    "platform_system": "Linux",
    "machine": required_machine,
    "pip_version": required_pip,
    "artifact_repository": "astral-sh/python-build-standalone",
    "artifact_release": "20260814",
    "artifact_name": artifact_name,
    "artifact_sha256": artifact_sha256,
    "cpython_source_sha256": source_sha256,
    "python_executable_sha256": executable_sha256,
    "qg_repository": "MahmoudAlZougbhi/linasbot-server",
    "qg_workflow_ref": (
        "MahmoudAlZougbhi/linasbot-server/.github/workflows/"
        "quality-gates.yml@refs/heads/main"
    ),
}
for key, value in fixed.items():
    if local.get(key) != value:
        raise SystemExit(f"node Python runtime receipt field is wrong: {key}")
cluster_fixed = {**fixed, "format": "linas-python-runtime-cluster-v2"}
cluster_fixed.pop("python_executable_sha256")
for key, value in cluster_fixed.items():
    if cluster.get(key) != value:
        raise SystemExit(f"cluster Python runtime receipt field is wrong: {key}")
for key in (
    "transaction_id", "runtime_tree_sha256", "plan_sha256", "artifact_sha256",
    "cpython_source_sha256", "qg_repository", "qg_workflow_ref", "qg_run_id",
    "qg_run_attempt", "qg_target_sha", "qg_artifact_id",
    "qg_artifact_api_sha256", "qg_manifest_sha256",
    "wheelhouse_archive_sha256", "wheelhouse_tree_sha256",
    "wheelhouse_file_count", "wheelhouse_total_size",
):
    if local.get(key) != cluster.get(key) or type(local.get(key)) is not type(cluster.get(key)):
        raise SystemExit(f"Python runtime receipts disagree: {key}")
if (
    local.get("runtime_tree_sha256") != expected_runtime_tree_sha256
    or cluster.get("runtime_tree_sha256") != expected_runtime_tree_sha256
):
    raise SystemExit("Python runtime receipt does not bind the reviewed artifact tree")
if not transaction_re.fullmatch(str(local.get("transaction_id") or "")):
    raise SystemExit("Python runtime transaction ID is invalid")
for payload in (local, cluster):
    if (
        type(payload.get("wheelhouse_file_count")) is not int
        or not 1 <= payload["wheelhouse_file_count"] <= 100_000
        or type(payload.get("wheelhouse_total_size")) is not int
        or not 1 <= payload["wheelhouse_total_size"] <= 4 * 1024**3
    ):
        raise SystemExit("Python runtime receipt wheelhouse evidence is invalid")
if (
    type(local.get("qg_run_id")) is not int
    or local["qg_run_id"] < 1
    or type(local.get("qg_run_attempt")) is not int
    or local["qg_run_attempt"] < 1
    or type(local.get("qg_artifact_id")) is not int
    or local["qg_artifact_id"] < 1
    or re.fullmatch(r"[0-9a-f]{40}", str(local.get("qg_target_sha") or "")) is None
):
    raise SystemExit("Python runtime Quality Gates numeric or target identity is invalid")
for payload, keys in (
    (
        local,
        (
            "runtime_tree_sha256", "python_executable_sha256", "plan_sha256",
            "qg_artifact_api_sha256", "qg_manifest_sha256",
            "wheelhouse_archive_sha256", "wheelhouse_tree_sha256",
        ),
    ),
    (
        cluster,
        (
            "runtime_tree_sha256", "plan_sha256", "qg_artifact_api_sha256",
            "qg_manifest_sha256", "wheelhouse_archive_sha256",
            "wheelhouse_tree_sha256",
        ),
    ),
):
    for key in keys:
        if not digest_re.fullmatch(str(payload.get(key) or "")):
            raise SystemExit(f"Python runtime receipt digest is invalid: {key}")
        if payload[key] == "0" * 64:
            raise SystemExit(f"Python runtime receipt digest is all-zero: {key}")
receipt_map = cluster.get("node_receipt_sha256")
if (
    not isinstance(receipt_map, dict)
    or set(receipt_map) != {"node01", "node02"}
    or any(not digest_re.fullmatch(str(value or "")) for value in receipt_map.values())
    or receipt_map[node_id] != hashlib.sha256(local_bytes).hexdigest()
):
    raise SystemExit("cluster Python runtime node receipt binding is invalid")

transaction_id = str(local["transaction_id"])
transaction_root = state_root / "python-runtime-transactions" / transaction_id
authority_root = transaction_root / "authority"
for directory in (
    state_root,
    state_root / "python-runtime-transactions",
    transaction_root,
    authority_root,
):
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise SystemExit("Python runtime retained authority directory is unsafe")

plan_bytes = secure_read(authority_root / "plan.json", "retained Python runtime plan")
manifest_bytes = secure_read(
    authority_root / "release-manifest.json",
    "retained Python runtime release manifest",
)
plan = parse(plan_bytes, "retained Python runtime plan")
manifest = parse(manifest_bytes, "retained Python runtime release manifest")
if plan_bytes != canonical(plan) or manifest_bytes != canonical(manifest):
    raise SystemExit("Python runtime retained authority is not canonical JSON")
if hashlib.sha256(plan_bytes).hexdigest() != local["plan_sha256"]:
    raise SystemExit("retained Python runtime plan digest differs from its receipt")
if hashlib.sha256(manifest_bytes).hexdigest() != local["qg_manifest_sha256"]:
    raise SystemExit("retained Python runtime manifest digest differs from its receipt")
plan_keys = {
    "schema", "format", "transaction_id", "required_nodes", "runtime_path",
    "artifact_name", "artifact_sha256", "runtime_tree_sha256",
    "python_executable_sha256", "libpython_sha256",
    "control_plane_archive_sha256", "control_plane_tree_sha256",
    "wheelhouse_archive_sha256", "wheelhouse_tree_sha256",
    "wheelhouse_file_count", "wheelhouse_total_size", "runtime_archive_size",
    "qg_repository", "qg_workflow_ref", "qg_run_id", "qg_run_attempt",
    "qg_target_sha", "qg_artifact_id", "qg_artifact_api_sha256",
    "qg_manifest_sha256",
}
if set(plan) != plan_keys or plan.get("schema") != 1 or plan.get("format") != "linas-python-runtime-plan-v1":
    raise SystemExit("retained Python runtime plan schema is not closed")
seed_plan = dict(plan)
seed_plan["transaction_id"] = ""
expected_transaction_id = f"pyr_{hashlib.sha256(canonical(seed_plan)).hexdigest()[:32]}"
if transaction_id != expected_transaction_id:
    raise SystemExit("retained Python runtime plan transaction identity is invalid")
if (
    plan.get("transaction_id") != transaction_id
    or plan.get("required_nodes") != ["node01", "node02"]
    or plan.get("runtime_path") != str(runtime)
    or plan.get("artifact_name") != artifact_name
    or plan.get("artifact_sha256") != artifact_sha256
    or plan.get("runtime_tree_sha256") != expected_runtime_tree_sha256
    or plan.get("python_executable_sha256") != executable_sha256
):
    raise SystemExit("retained Python runtime plan differs from the reviewed runtime")
for key in (
    "qg_repository", "qg_workflow_ref", "qg_run_id", "qg_run_attempt",
    "qg_target_sha", "qg_artifact_id", "qg_artifact_api_sha256",
    "qg_manifest_sha256", "wheelhouse_archive_sha256",
    "wheelhouse_tree_sha256", "wheelhouse_file_count", "wheelhouse_total_size",
):
    if plan.get(key) != local.get(key) or type(plan.get(key)) is not type(local.get(key)):
        raise SystemExit(f"retained Python runtime plan differs from its receipt: {key}")
manifest_keys = {
    "schema", "repository", "workflow_path", "workflow_ref", "run_id",
    "run_attempt", "target_sha", "source_locks", "toolchains", "payloads",
}
if set(manifest) != manifest_keys or manifest.get("schema") != "linasbot-release-manifest-v1":
    raise SystemExit("retained Python runtime manifest schema is not closed")
manifest_identity = {
    "qg_repository": manifest.get("repository"),
    "qg_workflow_ref": manifest.get("workflow_ref"),
    "qg_run_id": manifest.get("run_id"),
    "qg_run_attempt": manifest.get("run_attempt"),
    "qg_target_sha": manifest.get("target_sha"),
}
for key, value in manifest_identity.items():
    if value != local.get(key) or type(value) is not type(local.get(key)):
        raise SystemExit(f"retained Python runtime manifest differs from its receipt: {key}")
payloads = manifest.get("payloads")
if not isinstance(payloads, dict) or set(payloads) != {
    "wheelhouse", "dashboard", "control_plane", "source_bundle", "python_runtime"
}:
    raise SystemExit("retained Python runtime manifest payload schema is not closed")
wheelhouse = payloads.get("wheelhouse")
if not isinstance(wheelhouse, dict) or set(wheelhouse) != {
    "archive", "archive_sha256", "tree_sha256", "file_count", "total_size"
}:
    raise SystemExit("retained Python runtime wheelhouse schema is not closed")
if wheelhouse.get("archive") != "wheelhouse.tar":
    raise SystemExit("retained Python runtime wheelhouse archive identity is invalid")
wheelhouse_evidence = {
    "wheelhouse_archive_sha256": wheelhouse.get("archive_sha256"),
    "wheelhouse_tree_sha256": wheelhouse.get("tree_sha256"),
    "wheelhouse_file_count": wheelhouse.get("file_count"),
    "wheelhouse_total_size": wheelhouse.get("total_size"),
}
for key, value in wheelhouse_evidence.items():
    if value != local.get(key) or type(value) is not type(local.get(key)):
        raise SystemExit(f"retained provision wheelhouse differs from its receipt: {key}")


def tree_digest(root: Path) -> str:
    root_info = root.lstat()
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or stat.S_ISLNK(root_info.st_mode)
        or root_info.st_uid != 0
        or root_info.st_gid != 0
        or stat.S_IMODE(root_info.st_mode) != 0o755
    ):
        raise SystemExit("Python runtime root is unsafe")
    digest = hashlib.sha256()
    root_record = json.dumps(
        {"path": ".", "type": "directory", "mode": stat.S_IMODE(root_info.st_mode)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest.update(len(root_record).to_bytes(8, "big") + root_record)
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in [*dirnames, *filenames]:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if info.st_uid != 0 or info.st_gid != 0:
                raise SystemExit("Python runtime tree ownership is unsafe")
            record: dict[str, object] = {
                "path": relative,
                "mode": stat.S_IMODE(info.st_mode),
            }
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                resolved = path.resolve(strict=True)
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise SystemExit("Python runtime symlink escapes its immutable root") from exc
                record.update({"type": "symlink", "target": target})
            elif stat.S_ISDIR(info.st_mode):
                if stat.S_IMODE(info.st_mode) & 0o022:
                    raise SystemExit("Python runtime directory is group/world writable")
                record["type"] = "directory"
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if stat.S_IMODE(info.st_mode) & 0o022:
                    raise SystemExit("Python runtime file is group/world writable")
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    opened = os.fstat(descriptor)
                    if (info.st_dev, info.st_ino, info.st_size) != (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_size,
                    ):
                        raise SystemExit("Python runtime file changed while opening")
                    file_digest = hashlib.sha256()
                    consumed = 0
                    while True:
                        chunk = os.read(descriptor, 1 << 20)
                        if not chunk:
                            break
                        consumed += len(chunk)
                        file_digest.update(chunk)
                    if consumed != opened.st_size:
                        raise SystemExit("Python runtime file size changed while hashing")
                finally:
                    os.close(descriptor)
                record.update(
                    {"type": "file", "size": info.st_size, "sha256": file_digest.hexdigest()}
                )
            else:
                raise SystemExit("Python runtime tree contains an unsupported filesystem object")
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big") + encoded)
    return digest.hexdigest()


if hashlib.sha256(executable.read_bytes()).hexdigest() != executable_sha256:
    raise SystemExit("live Python executable hash differs from its receipt")
if tree_digest(runtime) != expected_runtime_tree_sha256:
    raise SystemExit("live Python runtime tree differs from its committed receipt")

pip_metadata = list(runtime.glob(f"lib/python3.13/site-packages/pip-{required_pip}.dist-info/METADATA"))
if len(pip_metadata) != 1:
    raise SystemExit("exact pip distribution metadata is missing from the runtime")
metadata = pip_metadata[0].read_text(encoding="utf-8", errors="strict")
if f"\nVersion: {required_pip}\n" not in f"\n{metadata}":
    raise SystemExit("pip distribution metadata version is wrong")
print(hashlib.sha256(cluster_bytes).hexdigest())
PY
  )"
  validate_digest "$cluster_digest"
  run_system_python_control - \
    "$SYSTEM_PYTHON" "$REQUIRED_PYTHON_VERSION" "$REQUIRED_PYTHON_CACHE_TAG" \
    "$REQUIRED_PYTHON_SOABI" "$REQUIRED_PYTHON_MACHINE" <<'PY'
import os
import platform
import sys
import sysconfig
from pathlib import Path

executable, version, cache_tag, soabi, machine = sys.argv[1:]
if Path(sys.executable) != Path(executable) or Path(os.path.realpath(sys.executable)) != Path(executable):
    raise SystemExit("Python runtime executable path is not exact")
if (
    platform.python_version() != version
    or sys.implementation.name != "cpython"
    or sys.implementation.cache_tag != cache_tag
    or sysconfig.get_config_var("SOABI") != soabi
    or sys.platform != "linux"
    or os.uname().machine != machine
):
    raise SystemExit("live Python runtime ABI differs from the committed receipt")
PY
  pip_version_output="$(
    /usr/bin/env -i \
      HOME=/nonexistent \
      LANG=C.UTF-8 \
      LC_ALL=C.UTF-8 \
      PATH=/usr/sbin:/usr/bin:/sbin:/bin \
      PYTHONDONTWRITEBYTECODE=1 \
      PIP_CONFIG_FILE=/dev/null \
      "$SYSTEM_PYTHON" -B -I -m pip --isolated --disable-pip-version-check --version
  )"
  case "$pip_version_output" in
    "pip $REQUIRED_PIP_VERSION from $PYTHON_RUNTIME_ROOT/lib/python3.13/site-packages/pip"*" (python 3.13)") ;;
    *) die "live portable runtime pip version or path is not exact" ;;
  esac
  assert_python_runtime_tree_pristine_os
  assert_git_repository_trust
  printf '%s\n' "$cluster_digest"
}

run_portable_pip() {
  local state_root="$1"
  shift
  test -n "$state_root" || die "portable pip state root is missing"
  if [ -e "$state_root" ] || [ -L "$state_root" ]; then
    test -d "$state_root" && test ! -L "$state_root" || \
      die "portable pip state root is unsafe"
    test "$(stat -c '%u:%g:%a' "$state_root")" = "0:0:700" || \
      die "portable pip state root ownership or mode is unsafe"
  else
    install -d -o root -g root -m 0700 "$state_root"
  fi
  install -d -o root -g root -m 0700 "$state_root/home" "$state_root/cache"
  /usr/bin/env -i \
    HOME="$state_root/home" \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_CONFIG_FILE=/dev/null \
    "$SYSTEM_PYTHON" -B -I -m pip --isolated --disable-pip-version-check \
      --cache-dir "$state_root/cache" "$@"
}

acquire_meta_live_lock() {
  local path_identity fd_identity
  # The lock itself must be acquired before trusting mutable runtime receipts.
  # Only the two hardcoded, shell-verified portable-runtime anchors may execute
  # this pre-contract helper, isolated from site and environment customization.
  assert_python_runtime_binary_anchor
  run_os_python_receipt_verifier - "$LOCK_FILE" <<'PY'
import os
import stat
import sys

path = sys.argv[1]
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
try:
    fd = os.open(path, flags, 0o600)
except FileExistsError:
    fd = -1
try:
    if fd >= 0:
        os.fchmod(fd, 0o600)
        os.fsync(fd)
finally:
    if fd >= 0:
        os.close(fd)
info = os.lstat(path)
if (
    not stat.S_ISREG(info.st_mode)
    or stat.S_ISLNK(info.st_mode)
    or info.st_uid != 0
    or info.st_gid != 0
    or stat.S_IMODE(info.st_mode) != 0o600
):
    raise SystemExit("Meta HA transaction lock is not root:root mode 0600")
PY
  path_identity="$(stat -Lc '%d:%i' "$LOCK_FILE")"
  exec 9<>"$LOCK_FILE"
  fd_identity="$(stat -Lc '%d:%i' "/proc/$$/fd/9")"
  test "$fd_identity" = "$path_identity" || die "Meta HA transaction lock changed while opening"
  flock -x 9
}

read_bootstrap_commit_proof() {
  local expected_node_id="$1"
  local expected_plan_sha="$2"
  local expected_runtime_cluster_sha="$3"
  run_system_python_control - "$BOOTSTRAP_COMMIT_PROOF_FILE" "$expected_node_id" \
    "$expected_plan_sha" "$expected_runtime_cluster_sha" <<'PY'
import json
import os
import re
import stat
import sys

path, expected_node, expected_plan, expected_runtime_cluster = sys.argv[1:]
info = os.lstat(path)
if (
    not stat.S_ISREG(info.st_mode)
    or stat.S_ISLNK(info.st_mode)
    or info.st_uid != 0
    or info.st_gid != 0
    or stat.S_IMODE(info.st_mode) != 0o600
    or info.st_nlink != 1
    or not 1 <= info.st_size <= 64 * 1024
):
    raise SystemExit("bootstrap commit proof is not root:root mode 0600")
flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(path, flags)
try:
    opened = os.fstat(fd)
    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
        raise SystemExit("bootstrap commit proof changed while opening")
    raw = b""
    while len(raw) < opened.st_size:
        chunk = os.read(fd, opened.st_size - len(raw))
        if not chunk:
            raise SystemExit("bootstrap commit proof is truncated")
        raw += chunk
    after = os.fstat(fd)
finally:
    os.close(fd)
if any(
    getattr(opened, key) != getattr(after, key)
    for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns")
):
    raise SystemExit("bootstrap commit proof changed while reading")
try:
    payload = json.loads(raw)
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit("bootstrap commit proof is invalid JSON") from exc
keys = {
    "schema", "format", "tx_id", "plan_sha256", "node_id", "status",
    "runtime_transaction_id", "runtime_plan_sha256", "runtime_cluster_receipt_sha256",
    "runtime_shared_sha256", "runtime_launcher_receipt_sha256", "qg_manifest_sha256",
    "control_plane_archive_sha256", "control_plane_tree_sha256",
    "wheelhouse_archive_sha256", "wheelhouse_tree_sha256", "wheelhouse_file_count",
    "wheelhouse_total_size", "requirements_lock_sha256", "runtime_tree_sha256",
    "target_unit_contract_sha256", "legacy_bytecode_manifest_sha256",
    "repo_bytecode_absent", "nested_runtime_present", "nested_runtime_evidence_sha256",
    "nested_runtime_quarantined", "nested_runtime_authority_sha256",
}
if not isinstance(payload, dict) or set(payload) != keys:
    raise SystemExit("bootstrap commit proof schema is invalid")
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
if raw != canonical:
    raise SystemExit("bootstrap commit proof is not canonical")
if (
    payload.get("schema") != 3
    or payload.get("format") != "linas-meta-ha-bootstrap-node-v3"
    or payload.get("status") != "committed"
    or payload.get("repo_bytecode_absent") is not True
):
    raise SystemExit("bootstrap commit proof is not committed")
if payload.get("node_id") != expected_node:
    raise SystemExit("bootstrap commit proof belongs to the wrong node")
if payload.get("plan_sha256") != expected_plan:
    raise SystemExit("bootstrap commit proof differs from the owner-authorized plan")
if not re.fullmatch(r"[0-9a-f]{32}", str(payload.get("tx_id") or "")):
    raise SystemExit("bootstrap commit proof transaction ID is invalid")
if not re.fullmatch(r"pyr_[0-9a-f]{32}", str(payload.get("runtime_transaction_id") or "")):
    raise SystemExit("bootstrap runtime transaction ID is invalid")
digest_keys = keys - {
    "schema", "format", "tx_id", "node_id", "status", "runtime_transaction_id",
    "wheelhouse_file_count", "wheelhouse_total_size", "repo_bytecode_absent",
    "nested_runtime_present", "nested_runtime_quarantined",
}
for key in digest_keys:
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get(key) or "")):
        raise SystemExit(f"bootstrap commit proof digest is invalid: {key}")
for key in ("wheelhouse_file_count", "wheelhouse_total_size"):
    if type(payload.get(key)) is not int or payload[key] <= 0:
        raise SystemExit(f"bootstrap commit proof count is invalid: {key}")
for key in ("nested_runtime_present", "nested_runtime_quarantined"):
    if type(payload.get(key)) is not bool:
        raise SystemExit(f"bootstrap commit proof flag is invalid: {key}")
if payload.get("nested_runtime_present") != payload.get("nested_runtime_quarantined"):
    raise SystemExit("bootstrap commit proof nested runtime truth table violated")
if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("nested_runtime_evidence_sha256") or "")):
    raise SystemExit("bootstrap commit proof nested runtime digest is invalid")
if payload.get("runtime_cluster_receipt_sha256") != expected_runtime_cluster:
    raise SystemExit("bootstrap proof runtime certificate differs from the live committed certificate")
print(payload["plan_sha256"])
PY
}

validate_tx_dir() {
  local tx_dir="${1:-}"
  [[ "$tx_dir" =~ ^/var/backups/linasbot-ha/[0-9a-f]{40}-[0-9]{14}-[0-9]+$ ]] || \
    die "transaction directory is invalid"
}

target_sha_from_tx() {
  local tx_dir="$1"
  local target record="$tx_dir/target.sha"
  validate_tx_dir "$tx_dir"
  target="$(basename "$tx_dir")"
  target="${target%%-*}"
  validate_sha "$target"
  if [ -e "$record" ] || [ -L "$record" ]; then
    test -f "$record" && test ! -L "$record" || die "transaction target authority is unsafe"
    test "$(<"$record")" = "$target" || die "transaction path and target authority differ"
  fi
  printf '%s\n' "$target"
}

ensure_transaction_dir_durable() {
  local tx_dir="$1"
  validate_tx_dir "$tx_dir"
  test "$(dirname "$tx_dir")" = "$BACKUP_ROOT" || \
    die "transaction directory parent is not canonical"
  test -d /var/backups && test ! -L /var/backups || \
    die "system backup directory is unsafe"
  test "$(realpath -e /var/backups)" = /var/backups || \
    die "system backup directory is not canonical"
  if [ -e "$BACKUP_ROOT" ] || [ -L "$BACKUP_ROOT" ]; then
    test -d "$BACKUP_ROOT" && test ! -L "$BACKUP_ROOT" || \
      die "HA backup root is unsafe"
  else
    install -d -o root -g root -m 0700 "$BACKUP_ROOT"
  fi
  test "$(stat -c '%u:%g:%a' "$BACKUP_ROOT")" = "0:0:700" || \
    die "HA backup root ownership or mode is unsafe"
  test "$(realpath -e "$BACKUP_ROOT")" = "$BACKUP_ROOT" || \
    die "HA backup root is not canonical"
  if [ -e "$tx_dir" ] || [ -L "$tx_dir" ]; then
    test -d "$tx_dir" && test ! -L "$tx_dir" || \
      die "transaction directory is unsafe"
  else
    install -d -o root -g root -m 0700 "$tx_dir"
  fi
  test "$(stat -c '%u:%g:%a' "$tx_dir")" = "0:0:700" || \
    die "transaction directory ownership or mode is unsafe"
  test "$(realpath -e "$tx_dir")" = "$tx_dir" || \
    die "transaction directory is not canonical"
  run_system_python_control - "$tx_dir" "$BACKUP_ROOT" /var/backups <<'PY'
import os
import stat
import sys

for raw_path, expected_mode in zip(sys.argv[1:], (0o700, 0o700, None), strict=True):
    info = os.lstat(raw_path)
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or (expected_mode is not None and stat.S_IMODE(info.st_mode) != expected_mode)
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise SystemExit("transaction directory durability path is unsafe")
    descriptor = os.open(raw_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
PY
}

python_bin() {
  test -x "$REPO_DIR/venv/bin/python" || die "canonical live Python is missing"
  printf '%s\n' "$REPO_DIR/venv/bin/python"
}

read_ha_contract() {
  local expected_node_id="$1"
  run_system_python_control - "$REPO_DIR/.env" "$expected_node_id" <<'PY'
import ast
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_node = sys.argv[2]
values: dict[str, str] = {}
for raw_line in path.read_text(encoding="utf-8", errors="strict").splitlines():
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    raw_key, separator, raw_value = raw_line.partition("=")
    key = raw_key.strip()
    if not separator or re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None or key in values:
        raise SystemExit("canonical environment is ambiguous")
    value_text = raw_value.strip()
    if value_text[:1] in {"'", '"'}:
        if len(value_text) < 2 or value_text[-1] != value_text[0]:
            raise SystemExit("canonical environment quoting is invalid")
        value = ast.literal_eval(value_text)
        if not isinstance(value, str):
            raise SystemExit("canonical environment value is invalid")
    else:
        value = value_text
    values[key] = value
node = str(values.get("META_DELETION_NODE_ID") or "").strip()
required = sorted(
    item.strip()
    for item in str(values.get("META_DELETION_REQUIRED_NODES") or "").split(",")
    if item.strip()
)
approved = str(values.get("META_HA_LB_READY_HEALTHCHECK_APPROVED") or "").strip().lower()
raw_drain = str(values.get("META_HA_LB_DRAIN_SECONDS") or "").strip()
peer = str(values.get("LINAS_HA_PEER_HOST") or "").strip()
maintenance = str(values.get("LINAS_MAINTENANCE_DRAIN_FILE") or "").strip()
if node != expected_node:
    raise SystemExit("fixed HA node identity is invalid")
if required != ["node01", "node02"]:
    raise SystemExit("fixed HA membership is invalid")
if approved != "true":
    raise SystemExit("owner LB /api/ready health-check approval is missing")
try:
    drain = int(raw_drain)
except ValueError as exc:
    raise SystemExit("HA load-balancer drain interval is invalid") from exc
if not 30 <= drain <= 300:
    raise SystemExit("HA load-balancer drain interval must be between 30 and 300 seconds")
if maintenance != "/var/lib/linasbot/meta-ha/maintenance":
    raise SystemExit("maintenance marker path must be the canonical persistent Meta HA marker")
print(node)
print(drain)
print(peer)
PY
}

materialize_cluster_env_helper() {
  local source_sha="$1"
  local helper_root path destination object object_type actual_object
  validate_sha "$source_sha"
  helper_root="$(mktemp -d -p /run linasbot-cluster-env.XXXXXXXX)"
  test "$(stat -c '%u:%g:%a' "$helper_root")" = "0:0:700" || \
    die "cluster environment helper temporary root is unsafe"
  mkdir -m 0700 "$helper_root/scripts" "$helper_root/scripts/ha"
  for path in "$CLUSTER_ENV_HELPER_REPO_PATH" "$PRODUCTION_GUARD_REPO_PATH"; do
    destination="$helper_root/$path"
    object="$(git -C "$REPO_DIR" rev-parse "$source_sha:$path")"
    object_type="$(git -C "$REPO_DIR" cat-file -t "$object")"
    test "$object_type" = "blob" || die "authorized cluster environment helper object is not a blob"
    run_system_python_control - "$REPO_DIR" "$object" "$destination" <<'PY'
import os
import subprocess
import sys

repo, git_object, path = sys.argv[1:]
descriptor = os.open(
    path,
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
    0o600,
)
try:
    os.fchmod(descriptor, 0o600)
    os.fchown(descriptor, 0, 0)
    result = subprocess.run(
        ["git", "-C", repo, "cat-file", "blob", git_object],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=descriptor,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        raise SystemExit("authorized cluster environment helper blob could not be read")
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
    test -f "$destination" && test ! -L "$destination" || \
      die "materialized cluster environment helper is unsafe"
    test "$(stat -c '%u:%g:%a' "$destination")" = "0:0:600" || \
      die "materialized cluster environment helper ownership or mode is unsafe"
    actual_object="$(git -C "$REPO_DIR" hash-object "$destination")"
    test "$actual_object" = "$object" || \
      die "materialized cluster environment helper differs from the authorized Git blob"
  done
  printf '%s\n' "$helper_root"
}

cleanup_cluster_env_helper() {
  local helper_root="$1"
  [[ "$helper_root" =~ ^/run/linasbot-cluster-env\.[A-Za-z0-9]{8}$ ]] || \
    die "cluster environment helper cleanup path is invalid"
  unlink "$helper_root/$CLUSTER_ENV_HELPER_REPO_PATH"
  unlink "$helper_root/$PRODUCTION_GUARD_REPO_PATH"
  rmdir "$helper_root/scripts/ha" "$helper_root/scripts" "$helper_root"
}

materialize_lb_manager() {
  local source_sha="$1"
  local helper_root destination path object actual_object
  validate_sha "$source_sha"
  helper_root="$(mktemp -d -p /run linasbot-lb-validator.XXXXXXXX)"
  test "$(stat -c '%u:%g:%a' "$helper_root")" = "0:0:700" || \
    die "LB validator temporary root is unsafe"
  mkdir -m 0700 "$helper_root/scripts" "$helper_root/scripts/ha"
  for path in "$LB_MANAGER_REPO_PATH" "$LB_CONTRACT_REPO_PATH"; do
    destination="$helper_root/$path"
    object="$(git -C "$REPO_DIR" rev-parse "$source_sha:$path")"
    test "$(git -C "$REPO_DIR" cat-file -t "$object")" = blob || \
      die "authorized LB validator object is not a blob"
    git -C "$REPO_DIR" cat-file blob "$object" | \
      /usr/bin/dd of="$destination" bs=65536 status=none conv=fsync oflag=excl,nofollow
    chmod 0600 "$destination"
    actual_object="$(git -C "$REPO_DIR" hash-object "$destination")"
    test "$actual_object" = "$object" || \
      die "materialized LB validator differs from the authorized Git blob"
  done
  printf '%s\n' "$helper_root"
}

cleanup_lb_manager() {
  local helper_root="$1"
  [[ "$helper_root" =~ ^/run/linasbot-lb-validator\.[A-Za-z0-9]{8}$ ]] || \
    die "LB validator cleanup path is invalid"
  unlink "$helper_root/scripts/ha/manage_do_lb_ready_healthcheck.py"
  unlink "$helper_root/scripts/ha/do_lb_ready_contract.py"
  rmdir "$helper_root/scripts/ha" "$helper_root/scripts"
  rmdir "$helper_root"
}

materialize_release_artifact_contract() {
  local source_sha="$1"
  local helper_root path destination object actual_object
  validate_sha "$source_sha"
  helper_root="$(mktemp -d -p /run linasbot-release-contract.XXXXXXXX)"
  test "$(stat -c '%u:%g:%a' "$helper_root")" = "0:0:700" || \
    die "release contract temporary root is unsafe"
  mkdir -m 0700 "$helper_root/scripts" "$helper_root/scripts/ha"
  for path in "$RELEASE_ARCHIVE_CONTRACT_REPO_PATH" "$RELEASE_ARTIFACT_CONTRACT_REPO_PATH"; do
    destination="$helper_root/$path"
    object="$(git -C "$REPO_DIR" rev-parse "$source_sha:$path")"
    test "$(git -C "$REPO_DIR" cat-file -t "$object")" = blob || \
      die "authorized release contract object is not a blob"
    git -C "$REPO_DIR" cat-file blob "$object" | \
      /usr/bin/dd of="$destination" bs=65536 status=none conv=fsync oflag=excl,nofollow
    chmod 0600 "$destination"
    actual_object="$(git -C "$REPO_DIR" hash-object "$destination")"
    test "$actual_object" = "$object" || \
      die "materialized release contract differs from the authorized Git blob"
  done
  printf '%s\n' "$helper_root"
}

materialize_release_artifact_contract_from_control_plane() {
  local incoming_dir="$1"
  local expected_control_sha="$2"
  local archive="$incoming_dir/control-plane.tar"
  local helper_root
  validate_digest "$expected_control_sha"
  case "$incoming_dir" in
    "$RELEASE_INCOMING_PREFIX"????????) ;;
    *) die "release import directory is outside the exact volatile namespace" ;;
  esac
  test -d "$incoming_dir" && test ! -L "$incoming_dir" || \
    die "release import directory is missing or unsafe"
  test "$(stat -c '%F:%u:%g:%a' "$incoming_dir")" = "directory:0:0:700" || \
    die "release import directory security is invalid"
  test "$(realpath -e "$incoming_dir")" = "$incoming_dir" || \
    die "release import directory path is aliased"
  test -f "$archive" && test ! -L "$archive" || \
    die "release control-plane archive is missing or unsafe"
  test "$(stat -c '%F:%u:%g:%a:%h' "$archive")" = "regular file:0:0:600:1" || \
    die "release control-plane archive security is invalid"
  test "$(sha256sum "$archive" | awk '{print $1}')" = "$expected_control_sha" || \
    die "release control-plane archive differs from workflow authority"
  helper_root="$(mktemp -d -p /run linasbot-release-contract.XXXXXXXX)"
  test "$(stat -c '%u:%g:%a' "$helper_root")" = "0:0:700" || \
    die "release contract bootstrap root is unsafe"
  if ! run_os_python_receipt_verifier - "$archive" "$helper_root" <<'PY'
import os
import posixpath
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive = Path(sys.argv[1])
root = Path(sys.argv[2])
required = {
    "scripts/ha/release_archive_contract.py",
    "scripts/ha/release_artifact_contract.py",
}
seen: set[str] = set()
captured: dict[str, bytes] = {}


def safe_name(name: str) -> str:
    parts = name.split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or any(part in {"", ".", ".."} for part in parts)
        or str(PurePosixPath(name)) != name
        or posixpath.normpath(name) != name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise SystemExit("release control-plane archive contains an unsafe path")
    return name


with tarfile.open(archive, mode="r:") as bundle:
    for member in bundle:
        name = safe_name(member.name)
        if name in seen:
            raise SystemExit("release control-plane archive contains duplicate members")
        seen.add(name)
        if (
            member.uid != 0
            or member.gid != 0
            or member.uname != ""
            or member.gname != ""
            or member.mtime != 0
            or set(member.pax_headers) - {"path"}
            or ("path" in member.pax_headers and member.pax_headers["path"] != name)
        ):
            raise SystemExit("release control-plane member metadata is invalid")
        if member.isdir():
            if stat.S_IMODE(member.mode) != 0o755 or member.size != 0:
                raise SystemExit("release control-plane directory metadata is invalid")
            continue
        if not member.isfile() or stat.S_IMODE(member.mode) not in {0o644, 0o755}:
            raise SystemExit("release control-plane archive contains a forbidden object")
        if member.size < 1 or member.size > (8 << 20):
            raise SystemExit("release control-plane member size is invalid")
        if name in required:
            source = bundle.extractfile(member)
            if source is None:
                raise SystemExit("release contract member could not be opened")
            payload = source.read((8 << 20) + 1)
            if len(payload) != member.size or len(payload) > (8 << 20):
                raise SystemExit("release contract member changed during extraction")
            captured[name] = payload
if set(captured) != required:
    raise SystemExit("release control-plane archive is missing its contract modules")
for relative, payload in captured.items():
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
for directory in (root / "scripts/ha", root / "scripts", root):
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
PY
  then
    run_os_python_receipt_verifier - "$helper_root" <<'PY'
import shutil
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
info = path.lstat()
if path.parent != Path("/run") or not path.name.startswith("linasbot-release-contract."):
    raise SystemExit("release contract cleanup path is invalid")
if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
    raise SystemExit("release contract cleanup root is unsafe")
shutil.rmtree(path)
PY
    die "release control-plane contract bootstrap failed"
  fi
  printf '%s\n' "$helper_root"
}

cleanup_release_artifact_contract() {
  local helper_root="$1"
  [[ "$helper_root" =~ ^/run/linasbot-release-contract\.[A-Za-z0-9]{8}$ ]] || \
    die "release contract cleanup path is invalid"
  unlink "$helper_root/$RELEASE_ARCHIVE_CONTRACT_REPO_PATH"
  unlink "$helper_root/$RELEASE_ARTIFACT_CONTRACT_REPO_PATH"
  rmdir "$helper_root/scripts/ha" "$helper_root/scripts" "$helper_root"
}

release_bundle_path() {
  local artifact_id="$1"
  local artifact_api_sha="$2"
  [[ "$artifact_id" =~ ^[1-9][0-9]*$ ]] || die "release artifact ID is invalid"
  validate_digest "$artifact_api_sha"
  printf '%s/%s-%s\n' "$RELEASE_BUNDLE_ROOT" "$artifact_id" "$artifact_api_sha"
}

assert_release_bundle() {
  local target_sha="$1"
  local artifact_id="$2"
  local artifact_api_sha="$3"
  local manifest_sha="$4"
  local run_id="$5"
  local run_attempt="$6"
  local bundle_dir helper_root summary rc=0 cleanup_rc=0 cleanup_helper=1
  local source_bundle source_tree_sha temp_git advertised
  validate_sha "$target_sha"
  [[ "$artifact_id" =~ ^[1-9][0-9]*$ ]] || die "release artifact ID is invalid"
  validate_digest "$artifact_api_sha"
  validate_digest "$manifest_sha"
  [[ "$run_id" =~ ^[1-9][0-9]*$ ]] || die "release Quality Gates run ID is invalid"
  [[ "$run_attempt" =~ ^[1-9][0-9]*$ ]] || die "release Quality Gates attempt is invalid"
  bundle_dir="${7:-$(release_bundle_path "$artifact_id" "$artifact_api_sha")}"
  helper_root="${8:-}"
  if [ -z "$helper_root" ]; then
    helper_root="$(materialize_release_artifact_contract "$target_sha")"
  else
    cleanup_helper=0
    case "$helper_root" in
      /run/linasbot-release-contract.????????) ;;
      *) die "preauthenticated release contract root is outside its exact namespace" ;;
    esac
  fi
  case "$bundle_dir" in
    "$RELEASE_BUNDLE_ROOT"/* | "$RELEASE_INCOMING_PREFIX"????????) ;;
    *) die "release bundle directory is outside an authorized namespace" ;;
  esac
  test -d "$(dirname "$bundle_dir")" && test ! -L "$(dirname "$bundle_dir")" || \
    die "release bundle parent directory is unsafe"
  test -d "$bundle_dir" && test ! -L "$bundle_dir" || \
    die "exact release bundle directory is missing or unsafe"
  test "$(stat -c '%F:%u:%g:%a' "$bundle_dir")" = "directory:0:0:700" || \
    die "exact release bundle directory security is invalid"
  test "$(realpath -e "$bundle_dir")" = "$bundle_dir" || \
    die "exact release bundle directory path is aliased"
  if summary="$(
    run_system_python_control - \
      "$helper_root" "$bundle_dir" "$EXPECTED_GITHUB_REPOSITORY" \
      "$EXPECTED_QG_WORKFLOW_REF" "$run_id" "$run_attempt" "$target_sha" \
      "$manifest_sha" "$artifact_id" "$artifact_api_sha" <<'PY'
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

(
    helper_root,
    raw_bundle,
    repository,
    workflow_ref,
    raw_run_id,
    raw_run_attempt,
    target_sha,
    manifest_sha,
    raw_artifact_id,
    artifact_api_sha,
) = sys.argv[1:]
sys.path.insert(0, helper_root)
from scripts.ha import release_artifact_contract as contract

bundle = Path(raw_bundle)
expected_files = {
    "release-manifest.json",
    "wheelhouse.tar",
    "dashboard-build.tar",
    "control-plane.tar",
    "source.bundle",
    contract.PYTHON_RUNTIME_NAME,
}
entries = list(os.scandir(bundle))
if {entry.name for entry in entries} != expected_files:
    raise SystemExit("release bundle file set is not closed")
for entry in entries:
    info = entry.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise SystemExit("release bundle contains an unsafe file")
manifest_path = bundle / "release-manifest.json"
if contract.sha256_file(manifest_path) != manifest_sha:
    raise SystemExit("release manifest digest differs from workflow authority")
manifest = contract.verify_release_bundle(
    bundle,
    expected_repository=repository,
    expected_workflow_ref=workflow_ref,
    expected_run_id=int(raw_run_id),
    expected_run_attempt=int(raw_run_attempt),
    expected_target_sha=target_sha,
)
source = manifest["payloads"]["source_bundle"]
if source.get("target_sha") != target_sha or source.get("advertised_ref") != "HEAD":
    raise SystemExit("release source bundle identity is invalid")
if (bundle / source["file"]).stat().st_size != source["size"]:
    raise SystemExit("release source bundle size differs from the manifest")
summary = {
    "schema": 1,
    "artifact_id": int(raw_artifact_id),
    "artifact_api_sha256": artifact_api_sha,
    "manifest_sha256": manifest_sha,
    "repository": repository,
    "workflow_ref": workflow_ref,
    "run_id": int(raw_run_id),
    "run_attempt": int(raw_run_attempt),
    "target_sha": target_sha,
    "source_bundle": source,
    "source_locks": manifest["source_locks"],
    "toolchains": manifest["toolchains"],
    "payloads": {
        key: manifest["payloads"][key]
        for key in ("wheelhouse", "dashboard", "control_plane", "python_runtime")
    },
}
print(json.dumps(summary, allow_nan=False, separators=(",", ":"), sort_keys=True))
PY
  )"; then
    rc=0
  else
    rc=$?
  fi
  if [ "$cleanup_helper" = 1 ]; then
    cleanup_release_artifact_contract "$helper_root" || cleanup_rc=$?
  fi
  test "$cleanup_rc" = 0 || die "release contract cleanup failed closed"
  test "$rc" = 0 || die "exact Quality Gates release bundle validation failed"
  source_bundle="$bundle_dir/source.bundle"
  source_tree_sha="$(run_system_python_control -c \
    'import json,sys; print(json.loads(sys.argv[1])["source_bundle"]["target_tree_sha"])' \
    "$summary")"
  validate_sha "$source_tree_sha"
  advertised="$(git -C "$REPO_DIR" bundle list-heads "$source_bundle")"
  test "$advertised" = "$target_sha HEAD" || \
    die "release source bundle does not advertise exactly the target HEAD"
  temp_git="$(mktemp -d -p /run linasbot-source-bundle.XXXXXXXX)"
  test "$(stat -c '%u:%g:%a' "$temp_git")" = "0:0:700" || \
    die "source bundle verification root is unsafe"
  git -C "$temp_git" init --bare --quiet
  if ! git -C "$temp_git" bundle verify "$source_bundle" >/dev/null || \
     ! git -C "$temp_git" fetch --quiet --no-tags "$source_bundle" HEAD || \
     [ "$(git -C "$temp_git" rev-parse FETCH_HEAD)" != "$target_sha" ] || \
     [ "$(git -C "$temp_git" rev-parse "FETCH_HEAD^{tree}")" != "$source_tree_sha" ] || \
     [ -n "$(git -C "$temp_git" ls-tree -r FETCH_HEAD | \
       awk '$1 == "120000" || $1 == "160000" {print; exit}')" ] || \
     [ -n "$(git -C "$temp_git" ls-tree -r --name-only FETCH_HEAD | \
       awk '$0 == ".gitattributes" || $0 ~ /\/\.gitattributes$/ || \
            $0 == ".gitmodules" || $0 ~ /\/\.gitmodules$/ {print; exit}')" ]; then
    run_system_python_control - "$temp_git" <<'PY'
import shutil, stat, sys
from pathlib import Path
path = Path(sys.argv[1])
info = path.lstat()
if not path.name.startswith("linasbot-source-bundle.") or path.parent != Path("/run"):
    raise SystemExit("source verification cleanup path is invalid")
if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
    raise SystemExit("source verification cleanup root is unsafe")
shutil.rmtree(path)
PY
    die "release source bundle commit/tree contract is invalid"
  fi
  run_system_python_control - "$temp_git" <<'PY'
import shutil, stat, sys
from pathlib import Path
path = Path(sys.argv[1])
info = path.lstat()
if not path.name.startswith("linasbot-source-bundle.") or path.parent != Path("/run"):
    raise SystemExit("source verification cleanup path is invalid")
if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
    raise SystemExit("source verification cleanup root is unsafe")
shutil.rmtree(path)
PY
  printf '%s\n' "$summary"
}

release_bundle_install_confirmation() {
  local target_sha="$1"
  local artifact_id="$2"
  local artifact_api_sha="$3"
  local manifest_sha="$4"
  local run_id="$5"
  local run_attempt="$6"
  local control_sha="$7"
  local source_sha="$8"
  local target_tree_sha="$9"
  printf 'INSTALL_RELEASE_%s_ARTIFACT_%s_%s_MANIFEST_%s_RUN_%s_ATTEMPT_%s_CONTROL_%s_SOURCE_%s_TREE_%s\n' \
    "${target_sha^^}" "$artifact_id" "${artifact_api_sha^^}" "${manifest_sha^^}" \
    "$run_id" "$run_attempt" "${control_sha^^}" "${source_sha^^}" \
    "${target_tree_sha^^}"
}

recover_release_import_ref_lock() {
  local target_sha="$1"
  local intent_path="$2"
  validate_sha "$target_sha"
  run_system_python_control - \
    "$REPO_DIR" "$LOCK_FILE" "$target_sha" "$intent_path" 9 <<'PY'
import fcntl
import os
import re
import stat
import sys
from pathlib import Path

repo = Path(sys.argv[1])
live_lock = Path(sys.argv[2])
target_sha = sys.argv[3]
intent = Path(sys.argv[4])
lock_fd = int(sys.argv[5])
git_dir = repo / ".git"
if re.fullmatch(r"[0-9a-f]{40}", target_sha) is None:
    raise SystemExit("release import target is invalid")
if intent.parent.name != "release-import-intents":
    raise SystemExit("release import intent path is invalid")
intent_info = intent.lstat()
if (
    not stat.S_ISREG(intent_info.st_mode)
    or stat.S_ISLNK(intent_info.st_mode)
    or intent_info.st_uid != 0
    or intent_info.st_gid != 0
    or intent_info.st_nlink != 1
    or stat.S_IMODE(intent_info.st_mode) != 0o600
):
    raise SystemExit("release import intent is unsafe")
lock_info = live_lock.lstat()
held_info = os.fstat(lock_fd)
if (
    not stat.S_ISREG(lock_info.st_mode)
    or stat.S_ISLNK(lock_info.st_mode)
    or lock_info.st_uid != 0
    or lock_info.st_gid != 0
    or stat.S_IMODE(lock_info.st_mode) != 0o600
    or (lock_info.st_dev, lock_info.st_ino) != (held_info.st_dev, held_info.st_ino)
):
    raise SystemExit("release import does not hold the canonical Meta HA lock")
try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError as exc:
    raise SystemExit("release import does not hold the exclusive Meta HA lock") from exc

ref_parent = git_dir / "refs/linasbot-release-artifacts"
source = ref_parent / f"{target_sha}.lock"
allowed = {source}
unknown = sorted(path for path in git_dir.rglob("*.lock") if path not in allowed)
if unknown:
    raise SystemExit(f"unknown Git lock blocks release import: {unknown[0]}")
if not source.exists() and not source.is_symlink():
    raise SystemExit(0)

proc_root = Path("/proc")
if proc_root.is_dir():
    for process in proc_root.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            executable = Path(os.readlink(process / "exe")).name
            cwd = Path(os.readlink(process / "cwd"))
            command = (process / "cmdline").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        decoded = [item.decode("utf-8", "surrogateescape") for item in command if item]
        if (executable == "git" or executable.startswith("git-")) and (
            cwd == repo
            or repo in cwd.parents
            or any(item == str(repo) or item.startswith(f"{repo}/") for item in decoded)
        ):
            raise SystemExit("a Git mutator still references the release repository")

source_info = source.lstat()
if (
    not stat.S_ISREG(source_info.st_mode)
    or stat.S_ISLNK(source_info.st_mode)
    or source_info.st_uid != 0
    or source_info.st_gid != 0
    or source_info.st_nlink != 1
    or stat.S_IMODE(source_info.st_mode) not in {0o600, 0o644}
    or source_info.st_size > (64 << 20)
):
    raise SystemExit("release import Git lock is unsafe")


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


archive_root = git_dir / "linasbot-release-import-locks"
archive_dir = archive_root / target_sha
parent = git_dir
for directory in (archive_root, archive_dir):
    if directory.exists() or directory.is_symlink():
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise SystemExit("release import lock archive is unsafe")
    else:
        directory.mkdir(mode=0o700)
        os.chown(directory, 0, 0)
        fsync_dir(parent)
    parent = directory
counters: list[int] = []
for child in archive_dir.iterdir():
    match = re.fullmatch(r"ref-([0-9]{4})[.]bin", child.name)
    if match is None:
        raise SystemExit("release import lock archive contains an unknown object")
    info = child.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) not in {0o600, 0o644}
        or info.st_size > (64 << 20)
    ):
        raise SystemExit("archived release import lock is unsafe")
    if stat.S_IMODE(info.st_mode) == 0o644:
        os.chmod(child, 0o600, follow_symlinks=False)
        descriptor = os.open(child, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    counters.append(int(match.group(1)))
counters.sort()
if counters != list(range(1, len(counters) + 1)) or len(counters) >= 9999:
    raise SystemExit("release import lock archive counters are invalid")
destination = archive_dir / f"ref-{len(counters) + 1:04d}.bin"
os.replace(source, destination)
fsync_dir(ref_parent)
fsync_dir(archive_dir)
os.chmod(destination, 0o600, follow_symlinks=False)
descriptor = os.open(destination, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
fsync_dir(archive_dir)
PY
}

install_release_bundle() {
  local expected_node_id="$1"
  local incoming_dir="$2"
  local target_sha="$3"
  local artifact_id="$4"
  local artifact_api_sha="$5"
  local manifest_sha="$6"
  local run_id="$7"
  local run_attempt="$8"
  local control_sha="$9"
  local source_sha="${10}"
  local target_tree_sha="${11}"
  local confirmation="${12}"
  local expected_confirmation helper_root summary canonical_dir receipt
  local runtime_cluster imported_ref source_bundle control_root control_helper
  local actual_summary canonical_summary
  case "$expected_node_id" in
    node01 | node02) ;;
    *) die "release bundle installer node identity is invalid" ;;
  esac
  validate_sha "$target_sha"
  [[ "$artifact_id" =~ ^[1-9][0-9]*$ ]] || die "release artifact ID is invalid"
  validate_digest "$artifact_api_sha"
  validate_digest "$manifest_sha"
  validate_digest "$control_sha"
  validate_digest "$source_sha"
  validate_sha "$target_tree_sha"
  [[ "$run_id" =~ ^[1-9][0-9]*$ ]] || die "release Quality Gates run ID is invalid"
  [[ "$run_attempt" =~ ^[1-9][0-9]*$ ]] || die "release Quality Gates attempt is invalid"
  expected_confirmation="$(release_bundle_install_confirmation \
    "$target_sha" "$artifact_id" "$artifact_api_sha" "$manifest_sha" \
    "$run_id" "$run_attempt" "$control_sha" "$source_sha" "$target_tree_sha")"
  test "$confirmation" = "$expected_confirmation" || \
    die "exact release bundle installation confirmation is missing"
  case "$incoming_dir" in
    "$RELEASE_INCOMING_PREFIX"????????) ;;
    *) die "release import directory is outside the exact volatile namespace" ;;
  esac
  test -d "$incoming_dir" && test ! -L "$incoming_dir" || \
    die "release import directory is missing or unsafe"
  test "$(stat -c '%F:%u:%g:%a' "$incoming_dir")" = "directory:0:0:700" || \
    die "release import directory security is invalid"
  test "$(realpath -e "$incoming_dir")" = "$incoming_dir" || \
    die "release import directory path is aliased"
  local expected_files=(
    release-manifest.json wheelhouse.tar dashboard-build.tar control-plane.tar
    source.bundle "$PYTHON_RUNTIME_ARTIFACT"
  )
  local path
  test "$(find "$incoming_dir" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)" = \
    "$(printf '%s\n' "${expected_files[@]}" | sort)" || \
    die "release import directory file set is not closed"
  for path in "${expected_files[@]}"; do
    path="$incoming_dir/$path"
    test -f "$path" && test ! -L "$path" || die "release import contains an unsafe file"
    test "$(stat -c '%F:%u:%g:%a:%h' "$path")" = "regular file:0:0:600:1" || \
      die "release import file security is invalid"
  done
  test "$(sha256sum "$incoming_dir/release-manifest.json" | awk '{print $1}')" = \
    "$manifest_sha" || die "release manifest differs from workflow authority"
  test "$(sha256sum "$incoming_dir/control-plane.tar" | awk '{print $1}')" = \
    "$control_sha" || die "release control plane differs from workflow authority"
  test "$(sha256sum "$incoming_dir/source.bundle" | awk '{print $1}')" = \
    "$source_sha" || die "release source bundle differs from workflow authority"

  require_root
  acquire_meta_live_lock
  runtime_cluster="$(assert_python_runtime_contract "$expected_node_id")"
  validate_digest "$runtime_cluster"
  test "$(configured_node_id)" = "$expected_node_id" || \
    die "canonical environment node identity differs from release installer authority"
  assert_no_other_meta_transaction

  helper_root="$(materialize_release_artifact_contract_from_control_plane \
    "$incoming_dir" "$control_sha")"
  summary="$(assert_release_bundle \
    "$target_sha" "$artifact_id" "$artifact_api_sha" "$manifest_sha" \
    "$run_id" "$run_attempt" "$incoming_dir" "$helper_root")"
  actual_summary="$(run_system_python_control -c \
    'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "$summary")"
  validate_digest "$actual_summary"

  control_root="$(mktemp -d -p /run linasbot-control-plane.XXXXXXXX)"
  test "$(stat -c '%u:%g:%a' "$control_root")" = "0:0:700" || \
    die "release control-plane verification root is unsafe"
  if ! run_system_python_control - \
      "$helper_root" "$incoming_dir/control-plane.tar" "$control_root" \
      "$control_sha" <<'PY'
import sys
from pathlib import Path

helper, archive, destination, expected_sha = sys.argv[1:]
sys.path.insert(0, helper)
from scripts.ha.release_artifact_contract import CONTROL_PLANE_MEMBERS, extract_archive

extract_archive(
    Path(archive),
    Path(destination),
    expected_sha,
    expected_paths=CONTROL_PLANE_MEMBERS,
)
PY
  then
    cleanup_release_artifact_contract "$helper_root" || true
    die "release control-plane extraction failed closed"
  fi
  control_helper="$control_root/$HELPER_REPO_PATH"
  test -f "$control_helper" && test ! -L "$control_helper" || \
    die "release control plane does not contain the deployment helper"
  test "$(sha256sum "$0" | awk '{print $1}')" = \
    "$(sha256sum "$control_helper" | awk '{print $1}')" || \
    die "running deployment helper is not the exact Quality Gates control-plane helper"

  ensure_meta_ha_state_root
  for path in \
    "$RELEASE_BUNDLE_ROOT" "$RELEASE_BUNDLE_RECEIPT_ROOT" "$RELEASE_IMPORT_INTENT_ROOT"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
      test -d "$path" && test ! -L "$path" || die "release authority root is unsafe"
      test "$(stat -c '%u:%g:%a' "$path")" = "0:0:700" || \
        die "release authority root security is invalid"
    else
      install -d -o root -g root -m 0700 "$path"
    fi
  done
  fsync_path_and_parents \
    "$RELEASE_BUNDLE_ROOT" "$RELEASE_BUNDLE_RECEIPT_ROOT" \
    "$RELEASE_IMPORT_INTENT_ROOT" "$META_HA_STATE_ROOT"

  source_bundle="$incoming_dir/source.bundle"
  local import_intent
  import_intent="$RELEASE_IMPORT_INTENT_ROOT/${artifact_id}-${artifact_api_sha}.intent"
  write_private_state "$import_intent" \
    "v1|$target_sha|$artifact_id|$artifact_api_sha|$manifest_sha|$source_sha|$target_tree_sha"
  recover_release_import_ref_lock "$target_sha" "$import_intent"
  test "$(git -C "$REPO_DIR" bundle list-heads "$source_bundle")" = "$target_sha HEAD" || \
    die "release source bundle does not advertise exactly the target HEAD"
  imported_ref="refs/linasbot-release-artifacts/$target_sha"
  if git -C "$REPO_DIR" show-ref --verify --quiet "$imported_ref"; then
    test "$(git -C "$REPO_DIR" rev-parse "$imported_ref^{commit}")" = "$target_sha" || \
      die "existing release source authority points to a different commit"
  else
    git -C "$REPO_DIR" fetch --quiet --no-tags --no-write-fetch-head \
      "$source_bundle" "HEAD:$imported_ref"
  fi
  assert_path_absent "$REPO_DIR/.git/refs/linasbot-release-artifacts/${target_sha}.lock" \
    "release source import lock remains after fetch"
  test "$(git -C "$REPO_DIR" rev-parse "$target_sha^{commit}")" = "$target_sha" || \
    die "imported release commit identity is invalid"
  test "$(git -C "$REPO_DIR" rev-parse "$target_sha^{tree}")" = "$target_tree_sha" || \
    die "imported release tree differs from workflow authority"
  fsync_tree "$REPO_DIR/.git"

  fsync_path_and_parents \
    "$REPO_DIR/.git/refs/linasbot-release-artifacts" \
    "$REPO_DIR/.git/refs" "$REPO_DIR/.git"
  canonical_dir="$(release_bundle_path "$artifact_id" "$artifact_api_sha")"
  if [ -e "$canonical_dir" ] || [ -L "$canonical_dir" ]; then
    canonical_summary="$(assert_release_bundle \
      "$target_sha" "$artifact_id" "$artifact_api_sha" "$manifest_sha" \
      "$run_id" "$run_attempt")"
    test "$canonical_summary" = "$summary" || \
      die "existing protected release bundle differs from the exact import"
  else
    run_system_python_control - "$incoming_dir" "$canonical_dir" <<'PY'
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
temporary = Path(tempfile.mkdtemp(prefix=".release-bundle.", dir=destination.parent))
os.chmod(temporary, 0o700)
try:
    for entry in os.scandir(source):
        info = entry.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
            raise SystemExit("release import changed before protected copy")
        target = temporary / entry.name
        source_fd = os.open(entry.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        target_fd = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            opened = os.fstat(source_fd)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                info.st_dev,
                info.st_ino,
                info.st_size,
            ):
                raise SystemExit("release import changed while opening")
            while True:
                payload = os.read(source_fd, 1 << 20)
                if not payload:
                    break
                os.write(target_fd, payload)
            os.fchmod(target_fd, 0o600)
            os.fchown(target_fd, 0, 0)
            os.fsync(target_fd)
        finally:
            os.close(source_fd)
            os.close(target_fd)
    directory_fd = os.open(temporary, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    os.replace(temporary, destination)
    parent_fd = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
except Exception:
    shutil.rmtree(temporary, ignore_errors=True)
    raise
PY
    canonical_summary="$(assert_release_bundle \
      "$target_sha" "$artifact_id" "$artifact_api_sha" "$manifest_sha" \
      "$run_id" "$run_attempt")"
    test "$canonical_summary" = "$summary" || \
      die "protected release bundle readback differs from the exact import"
  fi

  receipt="$RELEASE_BUNDLE_RECEIPT_ROOT/${artifact_id}-${artifact_api_sha}.json"
  run_system_python_control - \
    "$receipt" "$expected_node_id" "$summary" "$actual_summary" \
    "$runtime_cluster" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
node_id, summary_raw, summary_sha, runtime_sha = sys.argv[2:]
summary = json.loads(summary_raw)
payload = {
    "schema": 1,
    "format": "linasbot-release-bundle-install-v1",
    "status": "installed",
    "node_id": node_id,
    "target_sha": summary["target_sha"],
    "artifact_id": summary["artifact_id"],
    "artifact_api_sha256": summary["artifact_api_sha256"],
    "manifest_sha256": summary["manifest_sha256"],
    "run_id": summary["run_id"],
    "run_attempt": summary["run_attempt"],
    "target_tree_sha": summary["source_bundle"]["target_tree_sha"],
    "bundle_summary_sha256": summary_sha,
    "python_runtime_cluster_sha256": runtime_sha,
}
encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
if path.exists() or path.is_symlink():
    if path.read_bytes() != encoded:
        raise SystemExit("existing release bundle receipt differs from the exact authority")
else:
    descriptor, temporary_raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_raw)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
PY
  test "$(stat -c '%F:%u:%g:%a:%h' "$receipt")" = "regular file:0:0:600:1" || \
    die "release bundle receipt security is invalid"

  run_system_python_control - "$control_root" "$helper_root" <<'PY'
import shutil
import stat
import sys
from pathlib import Path
for raw, prefix in zip(sys.argv[1:], ("linasbot-control-plane.", "linasbot-release-contract.")):
    path = Path(raw)
    info = path.lstat()
    if path.parent != Path("/run") or not path.name.startswith(prefix):
        raise SystemExit("release helper cleanup path is invalid")
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
        raise SystemExit("release helper cleanup root is unsafe")
    shutil.rmtree(path)
PY
  log "exact Quality Gates release bundle installed for $expected_node_id"
}

assert_fresh_lb_ready_attestation() {
  local source_sha="$1"
  local attestation_sha="$2"
  local ready_projection_sha="$3"
  local explicit_path="${4:-}"
  local path helper_root rc=0 cleanup_rc=0 observed_at
  validate_sha "$source_sha"
  validate_digest "$attestation_sha"
  validate_digest "$ready_projection_sha"
  test "$attestation_sha" != "$(printf '%064d' 0)" || \
    die "all-zero LB attestation digest is never authority"
  test "$ready_projection_sha" != "$(printf '%064d' 0)" || \
    die "all-zero LB projection digest is never authority"
  if [ -n "$explicit_path" ]; then
    path="$explicit_path"
    case "$path" in
      "$META_HA_STATE_ROOT"/.lb-ready-deploy-install.*) ;;
      *) die "temporary LB attestation path is outside the protected state root" ;;
    esac
  else
    path="${LB_ATTESTATION_PREFIX}${attestation_sha}.json"
  fi
  test -f "$path" && test ! -L "$path" || \
    die "fresh DigitalOcean LB attestation is missing from its canonical path"
  test "$(stat -c '%F:%u:%g:%a:%h' "$path")" = "regular file:0:0:600:1" || \
    die "DigitalOcean LB attestation security is invalid"
  test "$(realpath -e "$path")" = "$path" || \
    die "DigitalOcean LB attestation path is not canonical"
  test "$(sha256sum "$path" | awk '{print $1}')" = "$attestation_sha" || \
    die "DigitalOcean LB attestation artifact digest changed"
  helper_root="$(materialize_lb_manager "$source_sha")"
  if observed_at="$(
    run_system_python_control - \
      "$helper_root/scripts/ha/manage_do_lb_ready_healthcheck.py" "$path" \
      "$attestation_sha" "$ready_projection_sha" <<'PY'
import hashlib
import importlib.util
import json
import os
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

module_path, artifact_raw, artifact_sha, ready_sha = sys.argv[1:]
spec = importlib.util.spec_from_file_location("linas_lb_validator", module_path)
if spec is None or spec.loader is None:
    raise SystemExit("authorized LB validator could not be loaded")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
artifact = Path(artifact_raw)
before = artifact.lstat()
if (
    not stat.S_ISREG(before.st_mode)
    or stat.S_ISLNK(before.st_mode)
    or before.st_uid != 0
    or before.st_gid != 0
    or stat.S_IMODE(before.st_mode) != 0o600
    or before.st_nlink != 1
    or before.st_size > 131_072
):
    raise SystemExit("LB attestation is unsafe")
descriptor = os.open(artifact, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    opened = os.fstat(descriptor)
    if (before.st_dev, before.st_ino, before.st_size) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
    ):
        raise SystemExit("LB attestation changed while opening")
    raw = os.read(descriptor, 131_073)
    if len(raw) > 131_072 or os.read(descriptor, 1):
        raise SystemExit("LB attestation is oversized")
finally:
    os.close(descriptor)
if hashlib.sha256(raw).hexdigest() != artifact_sha:
    raise SystemExit("LB attestation digest changed")


def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


payload = json.loads(raw, object_pairs_hook=no_duplicates)
if raw != module._canonical(payload) + b"\n":
    raise SystemExit("LB attestation bytes are not canonical")
module._validate_attestation(payload, ready_sha)
projection = payload["ready_projection"]
if (
    not isinstance(projection, dict)
    or set(projection) != module.LB_READY_PROJECTION_KEYS
):
    raise SystemExit("LB attestation is not the exact reviewed full projection")
try:
    module.validate_ready_projection_values(projection)
except RuntimeError as exc:
    raise SystemExit("LB attestation routing identity differs from the reviewed contract") from exc
rules = projection.get("forwarding_rules")
if not isinstance(rules, list) or len(rules) != 2 or any(not isinstance(rule, dict) for rule in rules):
    raise SystemExit("LB attestation forwarding rules are invalid")
http_rules = [rule for rule in rules if rule.get("entry_protocol") == "http"]
https_rules = [rule for rule in rules if rule.get("entry_protocol") == "https"]
if http_rules != [{
    "entry_protocol": "http",
    "entry_port": 80,
    "target_protocol": "http",
    "target_port": 80,
}]:
    raise SystemExit("LB attestation HTTP forwarding rule changed")
if len(https_rules) != 1 or set(https_rules[0]) != {
    "entry_protocol", "entry_port", "target_protocol", "target_port", "certificate_id"
}:
    raise SystemExit("LB attestation HTTPS forwarding rule shape changed")
https_rule = https_rules[0]
if (
    https_rule.get("entry_port") != 443
    or https_rule.get("target_protocol") != "http"
    or https_rule.get("target_port") != 80
    or not isinstance(https_rule.get("certificate_id"), str)
    or not https_rule["certificate_id"]
):
    raise SystemExit("LB attestation HTTPS forwarding rule changed")
observed_at = payload.get("observed_at")
if not isinstance(observed_at, str) or module._UTC_RE.fullmatch(observed_at) is None:
    raise SystemExit("LB attestation observation time is invalid")
observed = datetime.fromisoformat(observed_at[:-1] + "+00:00")
now = datetime.now(UTC)
if observed > now + timedelta(seconds=30) or now - observed > timedelta(seconds=300):
    raise SystemExit("LB attestation is older than the five-minute mutation window")
print(observed_at)
PY
  )"; then
    rc=0
  else
    rc=$?
  fi
  cleanup_lb_manager "$helper_root" || cleanup_rc=$?
  test "$cleanup_rc" = 0 || die "LB validator cleanup failed closed"
  test "$rc" = 0 || die "fresh DigitalOcean LB attestation validation failed"
  printf '%s\n' "$observed_at"
}

lb_attestation_install_confirmation() {
  local operation="$1"
  local target_sha="$2"
  local attestation_sha="$3"
  local ready_projection_sha="$4"
  local journal_digest="$5"
  local value
  case "$operation" in
    deploy)
      test "$journal_digest" = none || die "new deploy LB install cannot name a recovery journal"
      value="INSTALL_DEPLOY_LB_${target_sha:0:16}_${attestation_sha:0:16}_${ready_projection_sha:0:16}"
      ;;
    recover | retry | commit)
      validate_digest "$journal_digest"
      value="INSTALL_${operation^^}_LB_${target_sha:0:16}_${journal_digest:0:16}_${attestation_sha:0:16}_${ready_projection_sha:0:16}"
      ;;
    *) die "LB attestation install operation is invalid" ;;
  esac
  printf '%s\n' "${value^^}"
}

assert_lb_attestation_install_collision_contract() {
  local operation="$1"
  local target_sha="$2"
  local journal_digest="$3"
  local -a journal=()
  local path
  ensure_meta_ha_state_root
  for path in \
    "$BOOTSTRAP_ACTIVE_FILE" "$BOOTSTRAP_COORDINATOR_FILE" \
    "$SYNC_JOURNAL_FILE" "$SYNC_ENV_BACKUP_FILE" \
    "$PYTHON_RUNTIME_PROVISION_ACTIVE_FILE" "$PYTHON_RUNTIME_PROVISION_COORDINATOR_FILE" \
    "$CONTROLLED_FAILOVER_ACTIVE_FILE" "$REGISTRY_NFS_RETIRE_ACTIVE_FILE" \
    "$META_HA_STATE_ROOT/rekey/runtime.guard"; do
    assert_path_absent "$path" "another Meta HA mutation blocks LB attestation installation: $path"
  done
  case "$operation" in
    deploy)
      assert_path_absent "$DEPLOY_ACTIVE_FILE" \
        "an interrupted deploy requires recovery-specific LB attestation authority"
      assert_path_absent "$DEPLOY_NODE_ACTIVE_FILE" \
        "per-node deployment recovery blocks a new deploy LB attestation"
      ;;
    recover | retry | commit)
      mapfile -t journal < <(read_deploy_journal "$journal_digest")
      test "${#journal[@]}" -eq 22 || die "deployment recovery journal is incomplete"
      test "${journal[1]}" = "$target_sha" || \
        die "LB attestation target differs from the interrupted deployment"
      if [ "$operation" = commit ]; then
        test "${journal[9]}" = "target-parity-awaiting-fresh-lb" || \
          die "commit LB attestation requires exact drained target parity"
        test "${journal[10]}" = rollback || \
          die "commit LB attestation cannot replace a durable commit decision"
        test "$ready_projection_sha" = "${journal[14]}" || \
          die "commit LB projection differs from the reviewed deploy projection"
        test "$attestation_sha" != "${journal[13]}" || \
          die "commit LB attestation must be a distinct fresh provider observation"
      fi
      ;;
    *) die "LB attestation install operation is invalid" ;;
  esac
}

install_lb_ready_attestation() {
  local expected_node_id="$1"
  local operation="$2"
  local target_sha="$3"
  local attestation_sha="$4"
  local ready_projection_sha="$5"
  local journal_digest="$6"
  local confirmation="$7"
  local owner_confirmation="$8"
  local expected_confirmation destination temporary observed_at runtime_cluster
  validate_sha "$target_sha"
  test "$expected_node_id" = node01 || test "$expected_node_id" = node02 || \
    die "LB attestation installer node identity is invalid"
  validate_digest "$attestation_sha"
  validate_digest "$ready_projection_sha"
  test "$attestation_sha" != "$(printf '%064d' 0)" || \
    die "all-zero LB attestation digest is never install authority"
  test "$ready_projection_sha" != "$(printf '%064d' 0)" || \
    die "all-zero LB projection digest is never install authority"
  expected_confirmation="$(lb_attestation_install_confirmation \
    "$operation" "$target_sha" "$attestation_sha" "$ready_projection_sha" "$journal_digest")"
  test "$confirmation" = "$expected_confirmation" || \
    die "exact digest-bound LB attestation installation confirmation is missing"
  test "$owner_confirmation" = "I_HOLD_EXCLUSIVE_DO_LB_OWNER_UNTIL_DEPLOY_COMPLETE" || \
    die "exclusive DigitalOcean LB owner confirmation is missing"
  require_root
  acquire_meta_live_lock
  runtime_cluster="$(assert_python_runtime_contract "$expected_node_id")"
  validate_digest "$runtime_cluster"
  test "$(configured_node_id)" = "$expected_node_id" || \
    die "canonical environment node identity differs from the LB installer authority"
  test "$(git -C "$REPO_DIR" hash-object "$0")" = \
    "$(git -C "$REPO_DIR" rev-parse "$target_sha:$HELPER_REPO_PATH")" || \
    die "LB attestation installer is not the exact authorized target helper"
  assert_lb_attestation_install_collision_contract "$operation" "$target_sha" "$journal_digest"

  temporary="$(mktemp -p "$META_HA_STATE_ROOT" .lb-ready-deploy-install.XXXXXXXX)"
  test -f "$temporary" && test ! -L "$temporary" || die "LB attestation temporary file is unsafe"
  test "$(stat -c '%F:%u:%g:%a:%h' "$temporary")" = "regular empty file:0:0:600:1" || \
    die "LB attestation temporary file security is invalid"
  if ! /usr/bin/dd iflag=fullblock bs=131073 count=1 status=none \
      of="$temporary" conv=notrunc,fsync oflag=nofollow; then
    unlink "$temporary"
    die "LB attestation input could not be captured"
  fi
  if [ ! -s "$temporary" ] || [ "$(stat -c '%s' "$temporary")" -gt 131072 ]; then
    unlink "$temporary"
    die "LB attestation input size is invalid"
  fi
  if ! observed_at="$(assert_fresh_lb_ready_attestation \
      "$target_sha" "$attestation_sha" "$ready_projection_sha" "$temporary")"; then
    unlink "$temporary"
    die "LB attestation input did not pass the exact target validator"
  fi
  destination="${LB_ATTESTATION_PREFIX}${attestation_sha}.json"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    if ! assert_fresh_lb_ready_attestation \
        "$target_sha" "$attestation_sha" "$ready_projection_sha" >/dev/null || \
       ! cmp -s "$temporary" "$destination"; then
      unlink "$temporary"
      die "canonical LB attestation destination contains different or unsafe bytes"
    fi
    unlink "$temporary"
  else
    mv -T -- "$temporary" "$destination"
    fsync_path_and_parents "$destination" "$META_HA_STATE_ROOT"
  fi
  test "$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$attestation_sha" "$ready_projection_sha")" = "$observed_at" || \
    die "installed LB attestation failed exact readback"
  printf 'LB_ATTESTATION_SHA256=%s\nLB_READY_PROJECTION_SHA256=%s\nLB_OBSERVED_AT=%s\n' \
    "$attestation_sha" "$ready_projection_sha" "$observed_at"
}

assert_lb_observation_strictly_newer() {
  local previous_observed_at="$1"
  local fresh_observed_at="$2"
  run_system_python_control - "$previous_observed_at" "$fresh_observed_at" <<'PY'
from datetime import datetime
import re
import sys

pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
values = sys.argv[1:]
if len(values) != 2 or any(pattern.fullmatch(value) is None for value in values):
    raise SystemExit("LB observation time is invalid")
previous, fresh = (
    datetime.fromisoformat(value[:-1] + "+00:00") for value in values
)
if fresh <= previous:
    raise SystemExit("commit LB observation is not strictly newer")
PY
}

run_cluster_env_helper() {
  local source_sha="$1"
  shift
  local helper_root rc=0 cleanup_rc=0
  helper_root="$(materialize_cluster_env_helper "$source_sha")"
  if /usr/bin/env -i \
    HOME=/nonexistent \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONNOUSERSITE=1 \
    "$SYSTEM_PYTHON" -B -I -S "$helper_root/$CLUSTER_ENV_HELPER_REPO_PATH" "$@"; then
    rc=0
  else
    rc=$?
  fi
  cleanup_cluster_env_helper "$helper_root" || cleanup_rc=$?
  test "$cleanup_rc" = "0" || die "cluster environment helper cleanup failed closed"
  return "$rc"
}

cluster_runtime_env_evidence() {
  local helper_source_sha="$1"
  local expected_release_sha="$2"
  local node_id="$3"
  local process_environ="${4:-}"
  local process_contract="${5:-canonical}"
  validate_sha "$helper_source_sha"
  validate_sha "$expected_release_sha"
  test "$node_id" = "node01" || test "$node_id" = "node02" || \
    die "cluster environment evidence node identity is invalid"
  if [ -n "$process_environ" ]; then
    [[ "$process_environ" =~ ^/proc/[1-9][0-9]*/environ$ ]] || \
      die "cluster environment process proof path is invalid"
    local -a process_args=(
      fingerprint
      --env-file "$REPO_DIR/.env"
      --node-id "$node_id"
      --expected-release-sha "$expected_release_sha"
      --process-environ "$process_environ"
    )
    if [ "$process_contract" = "transient" ]; then
      process_args+=(--transient-verifier)
    elif [ "$process_contract" != "canonical" ]; then
      die "cluster environment process contract is invalid"
    fi
    run_cluster_env_helper "$helper_source_sha" "${process_args[@]}"
  else
    run_cluster_env_helper "$helper_source_sha" fingerprint \
      --env-file "$REPO_DIR/.env" \
      --node-id "$node_id" \
      --expected-release-sha "$expected_release_sha"
  fi
}

compare_cluster_runtime_env_evidence() {
  local helper_source_sha="$1"
  local expected_release_sha="$2"
  local node01_evidence="$3"
  local node02_evidence="$4"
  local helper_root node01_path node02_path rc=0 cleanup_rc=0
  validate_sha "$helper_source_sha"
  validate_sha "$expected_release_sha"
  helper_root="$(materialize_cluster_env_helper "$helper_source_sha")"
  node01_path="$helper_root/node01.json"
  node02_path="$helper_root/node02.json"
  run_system_python_control - "$node01_path" "$node02_path" "$node01_evidence" "$node02_evidence" <<'PY'
import json
import os
import sys

for raw_path, raw_payload in ((sys.argv[1], sys.argv[3]), (sys.argv[2], sys.argv[4])):
    payload = json.loads(raw_payload)
    encoded = (json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n").encode()
    descriptor = os.open(
        raw_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
PY
  if /usr/bin/env -i \
    HOME=/nonexistent \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONNOUSERSITE=1 \
    "$SYSTEM_PYTHON" -B -I -S "$helper_root/$CLUSTER_ENV_HELPER_REPO_PATH" compare \
      --node01-evidence "$node01_path" \
      --node02-evidence "$node02_path" \
      --expected-release-sha "$expected_release_sha"; then
    rc=0
  else
    rc=$?
  fi
  unlink "$node01_path" "$node02_path" || cleanup_rc=$?
  cleanup_cluster_env_helper "$helper_root" || cleanup_rc=$?
  test "$cleanup_rc" = "0" || die "cluster environment comparison cleanup failed closed"
  return "$rc"
}

assert_cluster_runtime_env_parity() {
  local peer_host="$1"
  local expected_release_sha="$2"
  local helper_source_sha="$3"
  local local_evidence peer_evidence
  local_evidence="$(cluster_runtime_env_evidence \
    "$helper_source_sha" "$expected_release_sha" node01)"
  peer_evidence="$(remote_node "$peer_host" env-evidence \
    "$expected_release_sha" "$helper_source_sha" node02)"
  compare_cluster_runtime_env_evidence \
    "$helper_source_sha" "$expected_release_sha" "$local_evidence" "$peer_evidence" >/dev/null || \
    die "full cluster runtime environment differs between fixed HA nodes"
}

assert_git_repository_trust() {
  local config_names key unsafe_path
  for path in /opt "$REPO_DIR" "$REPO_DIR/.git"; do
    test -d "$path" && test ! -L "$path" || \
      die "canonical Git path component is missing or symlinked: $path"
    test "$(/usr/bin/realpath -e "$path")" = "$path" || \
      die "canonical Git path component is aliased: $path"
    test "$(/usr/bin/stat -c '%u:%g' "$path")" = "0:0" || \
      die "canonical Git path component is not root-owned: $path"
    case "$path" in
      /opt | "$REPO_DIR")
        test "$(/usr/bin/stat -c '%a' "$path")" = 755 || \
          die "canonical Git worktree path mode is not 0755: $path"
        ;;
      "$REPO_DIR/.git")
        test "$(/usr/bin/stat -c '%a' "$path")" = 700 || \
          die "canonical Git directory mode is not 0700"
        ;;
    esac
  done
  unsafe_path="$(
    /usr/bin/find "$REPO_DIR/.git" -xdev \
      \( -type l -o ! -user root -o ! -group root -o -perm /022 \
         -o \( ! -type f ! -type d \) \) -print -quit
  )"
  test -z "$unsafe_path" || die "Git control directory contains an unsafe object: $unsafe_path"
  for path in \
    "$REPO_DIR/.git/refs/replace" \
    "$REPO_DIR/.git/commondir" \
    "$REPO_DIR/.git/info/grafts" \
    "$REPO_DIR/.git/info/attributes" \
    "$REPO_DIR/.git/objects/info/alternates" \
    "$REPO_DIR/.git/objects/info/http-alternates"; do
    assert_path_absent "$path" "Git replacement or alternate-object authority is forbidden: $path"
  done
  if [ -f "$REPO_DIR/.git/packed-refs" ] && \
     /usr/bin/grep -Eq ' refs/replace/' "$REPO_DIR/.git/packed-refs"; then
    die "packed Git replacement refs are forbidden"
  fi
  test -f "$REPO_DIR/.git/config" && test ! -L "$REPO_DIR/.git/config" || \
    die "canonical local Git configuration is missing or unsafe"
  test "$(/usr/bin/stat -c '%u:%g:%a:%h' "$REPO_DIR/.git/config")" = "0:0:600:1" || \
    die "canonical local Git configuration security is invalid"
  config_names="$(
    /usr/bin/env -i \
      HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin \
      GIT_NO_REPLACE_OBJECTS=1 GIT_ATTR_NOSYSTEM=1 \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
      /usr/bin/git --no-replace-objects --git-dir="$REPO_DIR/.git" \
        config --local --no-includes --name-only --get-regexp '.*'
  )"
  while IFS= read -r key; do
    case "$key" in
      core.repositoryformatversion | core.filemode | core.bare | core.logallrefupdates | \
      remote.origin.url | remote.origin.fetch | branch.main.remote | branch.main.merge) ;;
      "") ;;
      *) die "local Git configuration contains an unauthorized key: $key" ;;
    esac
  done <<<"$config_names"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all core.repositoryformatversion)" = 0 || \
    die "Git repository format is not exact"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all core.filemode)" = true || \
    die "Git file-mode tracking is not enabled"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all core.bare)" = false || \
    die "canonical Git repository unexpectedly is bare"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all core.logallrefupdates)" = true || \
    die "Git reflog contract is not exact"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all remote.origin.url)" = \
    git@github.com:MahmoudAlZougbhi/linasbot-server.git || die "Git origin identity is not exact"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all remote.origin.fetch)" = \
    '+refs/heads/*:refs/remotes/origin/*' || die "Git origin fetch refspec is not exact"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all branch.main.remote)" = origin || \
    die "Git main branch remote is not exact"
  test "$(git -C "$REPO_DIR" config --local --no-includes --get-all branch.main.merge)" = refs/heads/main || \
    die "Git main branch merge ref is not exact"
  test "$(git -C "$REPO_DIR" symbolic-ref -q HEAD)" = refs/heads/main || \
    die "canonical worktree HEAD is not the protected main branch"
  test "$(git -C "$REPO_DIR" rev-parse --absolute-git-dir)" = "$REPO_DIR/.git" || \
    die "Git directory resolves outside the canonical repository"
  test "$(git -C "$REPO_DIR" rev-parse --path-format=absolute --git-common-dir)" = \
    "$REPO_DIR/.git" || die "Git common directory is not canonical"
  test "$(/usr/bin/realpath -m "$(git -C "$REPO_DIR" rev-parse --git-path info/attributes)")" = \
    "$REPO_DIR/.git/info/attributes" || \
    die "Git attribute authority resolves outside the canonical repository"
}

current_head() {
  git -C "$REPO_DIR" rev-parse HEAD
}

assert_canonical_repo() {
  local top_level
  test "$(realpath -e "$REPO_DIR")" = "$REPO_DIR" || die "canonical repository path is not exact"
  top_level="$(git -C "$REPO_DIR" rev-parse --show-toplevel)"
  test "$top_level" = "$REPO_DIR" || die "Git top-level is not the canonical root"
  test -f "$REPO_DIR/main.py" || die "canonical main.py is missing"
  test -f "$REPO_DIR/.env" || die "canonical production .env is missing"
  test -d "$REPO_DIR/venv" && test ! -L "$REPO_DIR/venv" || die "canonical venv directory is unsafe"
  test -d "$REPO_DIR/data" && test ! -L "$REPO_DIR/data" || die "canonical data directory is unsafe"
  test -d "$REPO_DIR/dashboard/build" && test ! -L "$REPO_DIR/dashboard/build" || \
    die "live dashboard build directory is unsafe"
  test -f "$REPO_DIR/dashboard/build/index.html" || die "live dashboard build is missing"
  test -f /etc/nginx/sites-available/linasaibot && \
    test ! -L /etc/nginx/sites-available/linasaibot || die "canonical nginx vhost is unsafe"
  test -f /etc/nginx/conf.d/linasbot-privacy-log.conf && \
    test ! -L /etc/nginx/conf.d/linasbot-privacy-log.conf || die "nginx privacy log config is unsafe"
  test -L /etc/nginx/sites-enabled/linasaibot || die "canonical nginx enabled-site link is missing"
  test "$(readlink -f /etc/nginx/sites-enabled/linasaibot)" = \
    /etc/nginx/sites-available/linasaibot || die "canonical nginx enabled-site target is wrong"
  test -f /etc/systemd/system/linasbot.service && \
    test ! -L /etc/systemd/system/linasbot.service || die "canonical API unit is unsafe"
  test -f /etc/systemd/system/linasbot-worker@.service && \
    test ! -L /etc/systemd/system/linasbot-worker@.service || die "canonical worker unit is unsafe"
  if [ -e "$REPO_DIR/linaslaserbot-2.7.22" ] || [ -L "$REPO_DIR/linaslaserbot-2.7.22" ]; then
    die "legacy nested runtime still exists"
  fi
  if systemctl is-active --quiet "$VERIFY_API_UNIT" || \
     [ "$(systemctl show "$VERIFY_API_UNIT" --property=LoadState --value 2>/dev/null || true)" != "not-found" ]; then
    die "stale transient HA verification API requires owner recovery"
  fi
}

configured_node_id() {
  run_system_python_control - "$REPO_DIR/.env" <<'PY'
import ast
import re
import sys

values: dict[str, str] = {}
for raw_line in open(sys.argv[1], encoding="utf-8", errors="strict"):
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    raw_key, separator, raw_value = raw_line.partition("=")
    key = raw_key.strip()
    if not separator or re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None or key in values:
        raise SystemExit("canonical environment is ambiguous")
    value_text = raw_value.strip()
    if value_text[:1] in {"'", '"'}:
        if len(value_text) < 2 or value_text[-1] != value_text[0]:
            raise SystemExit("canonical environment quoting is invalid")
        value = ast.literal_eval(value_text)
        if not isinstance(value, str):
            raise SystemExit("canonical environment value is invalid")
    else:
        value = value_text
    values[key] = value
node_id = values.get("META_DELETION_NODE_ID", "").strip()
if node_id not in {"node01", "node02"}:
    raise SystemExit("canonical environment has no fixed node identity")
print(node_id)
PY
}

assert_legacy_retirement_contract() {
  local expected_node_id="$1"
  local legacy_unit=/etc/systemd/system/linas_ai_bot.service
  if [ "$expected_node_id" = "node01" ]; then
    test -f "$legacy_unit" && test ! -L "$legacy_unit" || \
      die "node01 legacy unit is missing from its protected retired state"
    test "$(stat -c '%u:%g' "$legacy_unit")" = "0:0" || \
      die "node01 legacy unit ownership is unsafe"
    assert_secure_maintenance_marker "$LEGACY_RETIREMENT_MARKER"
    test -f "$LEGACY_RETIREMENT_GUARD" && test ! -L "$LEGACY_RETIREMENT_GUARD" || \
      die "node01 persistent legacy retirement guard is missing or unsafe"
    test "$(stat -c '%u:%g:%a' "$LEGACY_RETIREMENT_GUARD")" = "0:0:644" || \
      die "node01 legacy retirement guard ownership or mode is unsafe"
    cmp -s "$LEGACY_RETIREMENT_GUARD" <(printf '%s\n' \
      '[Unit]' \
      '# Exact persistent retirement guard for the legacy :8000 runtime.' \
      'ConditionPathExists=!/var/lib/linasbot/meta-ha/bootstrap.active' \
      'ConditionPathExists=!/var/lib/linasbot/meta-ha/legacy-linas-ai-bot-retired') || \
      die "node01 legacy retirement guard content changed"
    systemctl is-enabled --quiet linas_ai_bot.service && \
      die "legacy linas_ai_bot service is enabled despite retirement"
    systemctl cat linas_ai_bot.service | \
      grep -Fq '/var/lib/linasbot/meta-ha/legacy-linas-ai-bot-retired' || \
      die "systemd did not load the persistent legacy retirement condition"
    test "$(systemctl show linas_ai_bot.service --property=NeedDaemonReload --value)" = "no" || \
      die "systemd has not loaded the persistent legacy retirement guard"
  elif [ "$expected_node_id" = "node02" ]; then
    assert_path_absent "$legacy_unit" "node02 unexpectedly has a legacy linas_ai_bot unit"
    assert_path_absent "$LEGACY_RETIREMENT_MARKER" \
      "node02 unexpectedly has the node01-only legacy retirement marker"
    assert_path_absent "$LEGACY_RETIREMENT_GUARD" \
      "node02 unexpectedly has the node01-only legacy retirement guard"
  else
    die "legacy retirement check requires a fixed node identity"
  fi
}

assert_controlled_failover_static_guard_contract() {
  assert_path_absent "$CONTROLLED_FAILOVER_RUNTIME_GUARD_FILE" \
    "controlled failover runtime guard requires exact transaction recovery"
  run_system_python_control - \
    /etc/systemd/system/linasbot.service.d/92-meta-controlled-failover.conf \
    /etc/systemd/system/linasbot-worker@.service.d/92-meta-controlled-failover.conf <<'PY'
import os
import stat
import sys
from pathlib import Path

expected = (
    b"[Unit]\n"
    b"# Permanently installed controlled Meta failover reboot guard.\n"
    b"ConditionPathExists=!/var/lib/linasbot/meta-ha/controlled-failover.runtime.guard\n"
)
for raw_path in sys.argv[1:]:
    path = Path(raw_path)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o644
        or before.st_nlink != 1
    ):
        raise SystemExit("controlled failover static guard is unsafe")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("controlled failover static guard changed while opening")
        payload = os.read(fd, len(expected) + 1)
        if payload != expected or os.read(fd, 1):
            raise SystemExit("controlled failover static guard content changed")
    finally:
        os.close(fd)
PY
  run_system_python_control - \
    /etc/systemd/system/linasbot.service.d/95-linasbot-credential-rekey-guard.conf \
    /etc/systemd/system/linasbot-worker@.service.d/95-linasbot-credential-rekey-guard.conf <<'PY'
import os
import stat
import sys
from pathlib import Path

expected = (
    b"[Unit]\n"
    b"# Managed only by rekey_meta_whatsapp_credentials.py.\n"
    b"ConditionPathExists=!/var/lib/linasbot/meta-ha/rekey/runtime.guard\n"
)
for raw_path in sys.argv[1:]:
    path = Path(raw_path)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o644
        or before.st_nlink != 1
    ):
        raise SystemExit("credential rekey static guard is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("credential rekey static guard changed while opening")
        if os.read(descriptor, len(expected) + 1) != expected or os.read(descriptor, 1):
            raise SystemExit("credential rekey static guard content changed")
    finally:
        os.close(descriptor)
PY
  local unit
  for unit in linasbot.service \
    linasbot-worker@high_priority.service \
    linasbot-worker@interactive.service \
    linasbot-worker@background.service \
    linasbot-worker@expensive.service; do
    test "$(systemctl show "$unit" --property=NeedDaemonReload --value)" = "no" || \
      die "controlled failover static guard is not loaded: $unit"
  done
}

assert_no_shadow_runtime() {
  local expected_node_id="$1"
  local blocker=0
  assert_legacy_retirement_contract "$expected_node_id" || blocker=1
  if systemctl is-active --quiet linas_ai_bot.service || \
     systemctl is-enabled --quiet linas_ai_bot.service; then
    echo "[ha-deploy] legacy linas_ai_bot service is active or enabled" >&2
    blocker=1
  fi
  if ss -H -ltnp 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:8000([[:space:]]|$)'; then
    echo "[ha-deploy] legacy port 8000 listener is active" >&2
    blocker=1
  fi
  return "$blocker"
}

assert_unit_file_contract() {
  local unit="$1"
  local working_directory exec_start environment_files fragment user exec_start_pre
  local exec_start_post exec_condition dropins environment expected_exec
  working_directory="$(systemctl show "$unit" --property=WorkingDirectory --value)"
  exec_start="$(systemctl show "$unit" --property=ExecStart --value)"
  environment_files="$(systemctl show "$unit" --property=EnvironmentFiles --value)"
  fragment="$(systemctl show "$unit" --property=FragmentPath --value)"
  user="$(systemctl show "$unit" --property=User --value)"
  exec_start_pre="$(systemctl show "$unit" --property=ExecStartPre --value)"
  exec_start_post="$(systemctl show "$unit" --property=ExecStartPost --value)"
  exec_condition="$(systemctl show "$unit" --property=ExecCondition --value)"
  dropins="$(systemctl show "$unit" --property=DropInPaths --value)"
  environment="$(systemctl show "$unit" --property=Environment --value)"
  test "$working_directory" = "$REPO_DIR" || die "$unit has a noncanonical WorkingDirectory"
  test "$user" = root || die "$unit has a non-root service user"
  test -z "$exec_start_pre" && test -z "$exec_start_post" && test -z "$exec_condition" || \
    die "$unit has an unauthorized pre/post/condition executable"
  test "$environment_files" = "$REPO_DIR/.env (ignore_errors=yes)" || \
    die "$unit has a noncanonical or additional EnvironmentFile"
  case "$unit" in
    linasbot.service)
      test "$fragment" = /etc/systemd/system/linasbot.service || \
        die "canonical API fragment path changed"
      expected_exec="argv[]=$REPO_DIR/venv/bin/python main.py ;"
      ;;
    linasbot-worker@*.service)
      test "$fragment" = /etc/systemd/system/linasbot-worker@.service || \
        die "canonical worker fragment path changed"
      local queue="${unit#linasbot-worker@}"
      queue="${queue%.service}"
      [[ " ${WORKER_QUEUES[*]} " == *" $queue "* ]] || die "unknown canonical worker instance"
      expected_exec="argv[]=$REPO_DIR/venv/bin/python scripts/run_queue_worker.py --queue $queue ;"
      ;;
    "$VERIFY_API_UNIT")
      test "$fragment" = "/run/systemd/transient/$VERIFY_API_UNIT" || \
        die "transient verification fragment path changed"
      expected_exec="argv[]=$REPO_DIR/venv/bin/python -B -I $REPO_DIR/$RELEASE_VERIFY_REPO_PATH ;"
      ;;
    *)
      die "unit is outside the closed HA runtime contract: $unit"
      ;;
  esac
  [[ "$exec_start" == *"$expected_exec"* ]] || die "$unit has a noncanonical ExecStart"
  run_system_python_control - "$unit" "$dropins" "$environment" <<'PY'
import shlex
import sys

unit, raw_dropins, raw_environment = sys.argv[1:]
dropins = set(raw_dropins.split()) if raw_dropins else set()
if unit == "linasbot-ha-verify.service":
    if dropins:
        raise SystemExit("transient verification unit has unauthorized drop-ins")
    expected_environment = {
        "PYTHONUNBUFFERED=1",
        "PYTHONDONTWRITEBYTECODE=1",
        "LINAS_HA_VERIFY_ONLY=true",
        # The exact SHA value is validated against the process separately.
        next(
            (item for item in shlex.split(raw_environment) if item.startswith("LINAS_HA_VERIFY_RELEASE_SHA=")),
            "",
        ),
        "DISABLE_API_DOCS=1",
        "PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin",
    }
else:
    prefix = "/etc/systemd/system/linasbot.service.d" if unit == "linasbot.service" else (
        "/etc/systemd/system/linasbot-worker@.service.d"
    )
    required = {
        f"{prefix}/92-meta-controlled-failover.conf",
        f"{prefix}/95-linasbot-credential-rekey-guard.conf",
    }
    allowed = required | {f"{prefix}/90-meta-ha-maintenance.conf"}
    if not required.issubset(dropins) or not dropins.issubset(allowed):
        raise SystemExit("canonical unit has a missing or unauthorized drop-in")
    expected_environment = {
        "PYTHONUNBUFFERED=1",
        "PYTHONDONTWRITEBYTECODE=1",
        "PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin",
    }
    if unit.startswith("linasbot-worker@"):
        queue = unit.removeprefix("linasbot-worker@").removesuffix(".service")
        expected_environment.add(f"LINAS_WORKER_QUEUE={queue}")
environment = set(shlex.split(raw_environment))
if "" in expected_environment or environment != expected_environment:
    raise SystemExit("canonical unit has an unauthorized direct environment assignment")
PY
}

assert_unit_contract() {
  local unit="$1"
  local main_pid
  assert_unit_file_contract "$unit"
  systemctl is-active --quiet "$unit" || die "$unit is not active"
  main_pid="$(systemctl show "$unit" --property=MainPID --value)"
  [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || die "$unit has no live MainPID"
  test "$(readlink -f "/proc/$main_pid/cwd")" = "$REPO_DIR" || die "$unit live cwd is noncanonical"
  test "$(readlink -f "/proc/$main_pid/exe")" = "$(readlink -f "$REPO_DIR/venv/bin/python")" || \
    die "$unit live interpreter is noncanonical"
}

assert_exact_runtime_process_contract() {
  local expected_autostart="$1"
  test "$expected_autostart" = "enabled" || test "$expected_autostart" = "disabled" || \
    die "exact process proof requires an enabled/disabled autostart expectation"
  run_system_python_control - "$REPO_DIR" "$expected_autostart" "${WORKER_QUEUES[@]}" <<'PY'
import ast
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

repo = Path(sys.argv[1])
expected_autostart = sys.argv[2]
queues = tuple(sys.argv[3:])
if expected_autostart not in {"enabled", "disabled"} or queues != (
    "high_priority",
    "interactive",
    "background",
    "expensive",
):
    raise SystemExit("exact runtime process proof arguments are invalid")
env_file = repo / ".env"
values: dict[str, str] = {}
for raw_line in env_file.read_text(encoding="utf-8", errors="strict").splitlines():
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    raw_key, separator, raw_value = raw_line.partition("=")
    key = raw_key.strip()
    if not separator or re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None or key in values:
        raise SystemExit("canonical environment is ambiguous")
    value_text = raw_value.strip()
    if value_text[:1] in {"'", '"'}:
        if len(value_text) < 2 or value_text[-1] != value_text[0]:
            raise SystemExit("canonical environment quoting is invalid")
        value = ast.literal_eval(value_text)
        if not isinstance(value, str):
            raise SystemExit("canonical environment value is invalid")
    else:
        value = value_text
    values[key] = value
if not values:
    raise SystemExit("canonical environment is empty or ambiguous")
forbidden = {
    "BASHOPTS", "BASH_ENV", "CDPATH", "ENV", "GCONV_PATH", "GLOBIGNORE", "GLIBC_TUNABLES",
    "HOSTALIASES", "IFS", "JAVA_TOOL_OPTIONS", "LD_LIBRARY_PATH", "LD_PRELOAD", "LOCPATH",
    "MALLOC_TRACE", "NLSPATH", "NODE_OPTIONS", "NODE_PATH", "OPENSSL_CONF", "OPENSSL_MODULES", "PATH", "PERL5LIB",
    "PERL5OPT", "PROMPT_COMMAND", "PYTHONBREAKPOINT", "PYTHONHOME", "PYTHONINSPECT",
    "PYTHONPATH", "PYTHONPLATLIBDIR", "PYTHONPYCACHEPREFIX", "PYTHONSTARTUP", "PYTHONUSERBASE",
    "PYTHONWARNINGS", "RUBYLIB", "RUBYOPT",
    "SHELLOPTS", "SSLKEYLOGFILE", "TZDIR", "_JAVA_OPTIONS",
}
prefixes = ("BASH_FUNC_", "DYLD_", "GIT_CONFIG_", "LD_", "LINAS_DEPLOY_MUTATION_", "LINAS_PRODUCTION_MUTATION_")
if any(str(key) in forbidden or str(key).startswith(prefixes) for key in values):
    raise SystemExit("canonical runtime environment contains a forbidden code-loader control")
expected_environment = {str(key): str(value) for key, value in values.items()}
expected_environment.update(
    {
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": f"{repo}/venv/bin:/usr/local/bin:/usr/bin:/bin",
    }
)
allowed_os_systemd = {
    "HOME": "/root",
    "USER": "root",
    "LOGNAME": "root",
    "SHELL": "/bin/bash",
}


def truthy(name: str) -> bool:
    return str(expected_environment.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


redis_configured = bool(
    str(expected_environment.get("REDIS_URL") or expected_environment.get("LINAS_REDIS_URL") or "").strip()
)
durable = redis_configured and (truthy("LINAS_REQUIRE_REDIS") or truthy("LINAS_ENABLE_DURABLE_QUEUES"))
python = str(repo / "venv/bin/python")
specs: dict[str, tuple[list[str], str | None, bool]] = {
    "linasbot.service": ([python, "main.py"], None, True),
}
for queue in queues:
    specs[f"linasbot-worker@{queue}.service"] = (
        [python, "scripts/run_queue_worker.py", "--queue", queue],
        queue,
        durable,
    )


def run(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=10)
    if check and result.returncode:
        raise SystemExit("systemd exact runtime process proof failed")
    return result


for unit, (expected_argv, queue, should_run) in specs.items():
    active = run("systemctl", "is-active", unit, check=False).returncode == 0
    enabled = run("systemctl", "is-enabled", unit, check=False).returncode == 0
    expected_enabled = expected_autostart == "enabled" and should_run
    if active is not should_run or enabled is not expected_enabled:
        raise SystemExit("canonical runtime active/enabled contract mismatch")
    if not should_run:
        continue
    working_directory = run("systemctl", "show", unit, "--property=WorkingDirectory", "--value").stdout.strip()
    exec_start = run("systemctl", "show", unit, "--property=ExecStart", "--value").stdout.strip()
    environment_files = run(
        "systemctl", "show", unit, "--property=EnvironmentFiles", "--value"
    ).stdout.strip()
    need_reload = run("systemctl", "show", unit, "--property=NeedDaemonReload", "--value").stdout.strip()
    main_pid = run("systemctl", "show", unit, "--property=MainPID", "--value").stdout.strip()
    env_paths = re.findall(r"/[^ ;}()]+", environment_files)
    expected_argv_text = "argv[]=" + " ".join(expected_argv) + " ;"
    if (
        working_directory != str(repo)
        or env_paths != [str(env_file)]
        or expected_argv_text not in exec_start
        or need_reload != "no"
        or not main_pid.isdigit()
        or int(main_pid) <= 0
    ):
        raise SystemExit("canonical systemd unit definition is not exact")
    proc = Path("/proc") / main_pid
    live_argv = [
        item.decode("utf-8", errors="strict")
        for item in (proc / "cmdline").read_bytes().split(b"\0")
        if item
    ]
    if live_argv != expected_argv:
        raise SystemExit("canonical runtime argv or worker queue is not exact")
    if Path(os.path.realpath(proc / "cwd")) != repo:
        raise SystemExit("canonical runtime cwd is not exact")
    if Path(os.path.realpath(proc / "exe")) != Path(os.path.realpath(repo / "venv/bin/python")):
        raise SystemExit("canonical runtime interpreter is not exact")
    live_environment: dict[str, str] = {}
    for entry in (proc / "environ").read_bytes().split(b"\0"):
        if not entry:
            continue
        if b"=" not in entry:
            raise SystemExit("canonical runtime environment is malformed")
        key, value = entry.split(b"=", 1)
        decoded_key = key.decode("utf-8", "strict")
        if decoded_key in live_environment:
            raise SystemExit("canonical runtime environment contains a duplicate key")
        live_environment[decoded_key] = value.decode("utf-8", "strict")
    live_forbidden = forbidden - {"PATH"}
    if any(key in live_forbidden or key.startswith(prefixes) for key in live_environment):
        raise SystemExit("canonical runtime loaded a forbidden execution-control key")
    expected = dict(expected_environment)
    if queue is not None:
        expected["LINAS_WORKER_QUEUE"] = queue
    if any(live_environment.get(key) != value for key, value in expected.items()):
        raise SystemExit("canonical runtime loaded a stale environment")
    unexpected = set(live_environment) - set(expected)
    for key in unexpected:
        value = live_environment[key]
        if key in allowed_os_systemd and value == allowed_os_systemd[key]:
            continue
        if key == "INVOCATION_ID" and re.fullmatch(r"[0-9a-f]{32}", value):
            continue
        if key == "JOURNAL_STREAM" and re.fullmatch(r"[0-9]+:[0-9]+", value):
            continue
        if key in {"SYSTEMD_EXEC_PID", "WATCHDOG_PID", "WATCHDOG_USEC"} and re.fullmatch(
            r"[1-9][0-9]*", value
        ):
            continue
        if key == "MEMORY_PRESSURE_WATCH" and value.startswith("/sys/fs/cgroup/"):
            continue
        if key == "MEMORY_PRESSURE_WRITE" and re.fullmatch(r"[A-Za-z0-9+/=]+", value):
            continue
        if key == "NOTIFY_SOCKET" and value in {
            "/run/systemd/notify",
            "@/org/freedesktop/systemd1/notify",
        }:
            continue
        raise SystemExit("canonical runtime loaded an extra non-system configuration key")
    stable_pid = run("systemctl", "show", unit, "--property=MainPID", "--value").stdout.strip()
    if stable_pid != main_pid or run("systemctl", "is-active", unit, check=False).returncode:
        raise SystemExit("canonical runtime PID changed during exact verification")

if durable:
    with urllib.request.urlopen("http://127.0.0.1:8003/api/queue/ready", timeout=5) as response:
        payload = json.load(response)
    if response.status != 200 or payload != {
        "ok": True,
        "role": "queue_readiness",
        "backend": "redis",
        "production_ready": True,
        "redis_required": True,
        "redis_configured": True,
    }:
        raise SystemExit("durable queue readiness contract is invalid")
PY
}

assert_active_runtime_process_env_contract() {
  local helper_source_sha="$1"
  local expected_release_sha="$2"
  local node_id="$3"
  local unit main_pid
  validate_sha "$helper_source_sha"
  validate_sha "$expected_release_sha"
  test "$node_id" = "node01" || test "$node_id" = "node02" || \
    die "runtime process environment proof node identity is invalid"
  for unit in linasbot.service \
    linasbot-worker@high_priority.service \
    linasbot-worker@interactive.service \
    linasbot-worker@background.service \
    linasbot-worker@expensive.service; do
    if systemctl is-active --quiet "$unit"; then
      main_pid="$(systemctl show "$unit" --property=MainPID --value)"
      [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || \
        die "$unit has no live PID for the cluster environment proof"
      cluster_runtime_env_evidence \
        "$helper_source_sha" "$expected_release_sha" "$node_id" "/proc/$main_pid/environ" \
        >/dev/null
      test "$(systemctl show "$unit" --property=MainPID --value)" = "$main_pid" || \
        die "$unit PID changed during the cluster environment proof"
    fi
  done
}

assert_transient_api_process_env_contract() {
  local helper_source_sha="$1"
  local expected_release_sha="$2"
  local node_id="$3"
  local main_pid
  main_pid="$(systemctl show "$VERIFY_API_UNIT" --property=MainPID --value)"
  [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || \
    die "transient verification API has no live PID for the cluster environment proof"
  test "$(git -C "$REPO_DIR" hash-object "$REPO_DIR/$RELEASE_VERIFY_REPO_PATH")" = \
    "$(git -C "$REPO_DIR" rev-parse "$expected_release_sha:$RELEASE_VERIFY_REPO_PATH")" || \
    die "transient verification entrypoint differs from the authorized target blob"
  run_system_python_control - "$main_pid" "$REPO_DIR" "$expected_release_sha" \
    "$RELEASE_VERIFY_REPO_PATH" <<'PY'
import ast
import os
import re
import sys
from pathlib import Path

raw_pid, raw_repo, expected_sha, relative_entrypoint = sys.argv[1:]
repo = Path(raw_repo)
proc = Path("/proc") / raw_pid
expected_argv = [
    str(repo / "venv/bin/python"),
    "-B",
    "-I",
    str(repo / relative_entrypoint),
]
live_argv = [
    item.decode("utf-8", "strict")
    for item in (proc / "cmdline").read_bytes().split(b"\0")
    if item
]
if live_argv != expected_argv:
    raise SystemExit("transient verification API argv is not exact")
if Path(os.path.realpath(proc / "cwd")) != repo:
    raise SystemExit("transient verification API cwd is not exact")
if Path(os.path.realpath(proc / "exe")) != Path(os.path.realpath(repo / "venv/bin/python")):
    raise SystemExit("transient verification API interpreter is not exact")
environment: dict[str, str] = {}
for entry in (proc / "environ").read_bytes().split(b"\0"):
    if not entry:
        continue
    key, separator, value = entry.partition(b"=")
    if not separator:
        raise SystemExit("transient verification environment is malformed")
    decoded = key.decode("utf-8", "strict")
    if decoded in environment:
        raise SystemExit("transient verification environment has a duplicate key")
    environment[decoded] = value.decode("utf-8", "strict")
if environment.get("LINAS_HA_VERIFY_ONLY") != "true":
    raise SystemExit("transient verification-only authority is missing")
if environment.get("LINAS_HA_VERIFY_RELEASE_SHA") != expected_sha:
    raise SystemExit("transient verification release authority is wrong")
if environment.get("DISABLE_API_DOCS") != "1":
    raise SystemExit("transient verification route-surface authority is missing")
canonical: dict[str, str] = {}
for raw_line in (repo / ".env").read_text(encoding="utf-8", errors="strict").splitlines():
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    raw_key, separator, raw_value = raw_line.partition("=")
    key = raw_key.strip()
    if not separator or re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None or key in canonical:
        raise SystemExit("transient verification canonical environment is ambiguous")
    value_text = raw_value.strip()
    if value_text[:1] in {"'", '"'}:
        if len(value_text) < 2 or value_text[-1] != value_text[0]:
            raise SystemExit("transient verification canonical environment quoting is invalid")
        value = ast.literal_eval(value_text)
        if not isinstance(value, str):
            raise SystemExit("transient verification canonical environment value is invalid")
    else:
        value = value_text
    canonical[key] = value
if not canonical:
    raise SystemExit("transient verification canonical environment is ambiguous")
expected = dict(canonical)
expected.update(
    {
        "PYTHONUNBUFFERED": "1",
        "PATH": f"{repo}/venv/bin:/usr/local/bin:/usr/bin:/bin",
        "LINAS_HA_VERIFY_ONLY": "true",
        "LINAS_HA_VERIFY_RELEASE_SHA": expected_sha,
        "DISABLE_API_DOCS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
)
if any(environment.get(key) != value for key, value in expected.items()):
    raise SystemExit("transient verification loaded a stale canonical environment")
allowed_os_systemd = {
    "HOME": "/root",
    "USER": "root",
    "LOGNAME": "root",
    "SHELL": "/bin/bash",
}
unexpected = set(environment) - set(expected)
for key in unexpected:
    value = environment[key]
    if key in allowed_os_systemd and value == allowed_os_systemd[key]:
        continue
    if key == "INVOCATION_ID" and re.fullmatch(r"[0-9a-f]{32}", value):
        continue
    if key == "JOURNAL_STREAM" and re.fullmatch(r"[0-9]+:[0-9]+", value):
        continue
    if key in {"SYSTEMD_EXEC_PID", "WATCHDOG_PID", "WATCHDOG_USEC"} and re.fullmatch(
        r"[1-9][0-9]*", value
    ):
        continue
    if key == "MEMORY_PRESSURE_WATCH" and value.startswith("/sys/fs/cgroup/"):
        continue
    if key == "MEMORY_PRESSURE_WRITE" and re.fullmatch(r"[A-Za-z0-9+/=]+", value):
        continue
    if key == "NOTIFY_SOCKET" and value in {
        "/run/systemd/notify",
        "@/org/freedesktop/systemd1/notify",
    }:
        continue
    raise SystemExit("transient verification loaded an extra non-system configuration key")
PY
  cluster_runtime_env_evidence \
    "$helper_source_sha" "$expected_release_sha" "$node_id" "/proc/$main_pid/environ" transient \
    >/dev/null
  test "$(systemctl show "$VERIFY_API_UNIT" --property=MainPID --value)" = "$main_pid" || \
    die "transient verification API PID changed during the cluster environment proof"
}

run_target_alembic_migrate() {
  local target_sha="$1"
  validate_sha "$target_sha"
  test "$(git -C "$REPO_DIR" hash-object "$REPO_DIR/$RELEASE_ALEMBIC_MIGRATE_REPO_PATH")" = \
    "$(git -C "$REPO_DIR" rev-parse "$target_sha:$RELEASE_ALEMBIC_MIGRATE_REPO_PATH")" || \
    die "target alembic migrate helper differs from the authorized target blob"
  systemd-run \
    --unit=linasbot-ha-alembic-migrate.service \
    --collect \
    --wait \
    --service-type=oneshot \
    --property=User=root \
    --property=RuntimeMaxSec=120s \
    --property=TimeoutStartSec=120s \
    --property=TimeoutStopSec=5s \
    --property=KillMode=control-group \
    --property=SendSIGKILL=yes \
    --property="WorkingDirectory=$REPO_DIR" \
    --property="EnvironmentFile=-$REPO_DIR/.env" \
    --property=Environment=PYTHONUNBUFFERED=1 \
    --property=Environment=PYTHONDONTWRITEBYTECODE=1 \
    --property=Environment=LINAS_HA_VERIFY_ONLY=true \
    --property="Environment=LINAS_HA_VERIFY_RELEASE_SHA=$target_sha" \
    --property=Environment=DISABLE_API_DOCS=1 \
    --property="Environment=PATH=$REPO_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    "$REPO_DIR/venv/bin/python" -B -I "$REPO_DIR/$RELEASE_ALEMBIC_MIGRATE_REPO_PATH" || \
    die "target alembic migration failed before readiness"
}

run_target_readiness_probe() {
  local target_sha="$1"
  local load_state
  validate_sha "$target_sha"
  test "$(git -C "$REPO_DIR" hash-object "$REPO_DIR/$RELEASE_READINESS_REPO_PATH")" = \
    "$(git -C "$REPO_DIR" rev-parse "$target_sha:$RELEASE_READINESS_REPO_PATH")" || \
    die "target readiness helper differs from the authorized target blob"
  # A killed SSH/workflow cannot leave an unbounded dependency probe holding
  # the fixed unit name. Exact recovery first stops and collects any stale
  # verifier, then systemd enforces a hard runtime/stop bound on the new probe.
  systemctl stop "$VERIFY_READINESS_UNIT" 2>/dev/null || true
  systemctl reset-failed "$VERIFY_READINESS_UNIT" 2>/dev/null || true
  for _ in $(seq 1 15); do
    load_state="$(systemctl show "$VERIFY_READINESS_UNIT" --property=LoadState --value 2>/dev/null || true)"
    if [ -z "$load_state" ] || [ "$load_state" = "not-found" ]; then
      break
    fi
    sleep 1
  done
  test -z "$load_state" || test "$load_state" = "not-found" || \
    die "stale target readiness verifier could not be stopped and collected"
  systemd-run \
    --unit="$VERIFY_READINESS_UNIT" \
    --collect \
    --wait \
    --service-type=oneshot \
    --property=User=root \
    --property=RuntimeMaxSec=45s \
    --property=TimeoutStartSec=45s \
    --property=TimeoutStopSec=5s \
    --property=KillMode=control-group \
    --property=SendSIGKILL=yes \
    --property="WorkingDirectory=$REPO_DIR" \
    --property="EnvironmentFile=-$REPO_DIR/.env" \
    --property=Environment=PYTHONUNBUFFERED=1 \
    --property=Environment=PYTHONDONTWRITEBYTECODE=1 \
    --property=Environment=LINAS_HA_VERIFY_ONLY=true \
    --property="Environment=LINAS_HA_VERIFY_RELEASE_SHA=$target_sha" \
    --property=Environment=DISABLE_API_DOCS=1 \
    --property="Environment=PATH=$REPO_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    "$REPO_DIR/venv/bin/python" -B -I "$REPO_DIR/$RELEASE_READINESS_REPO_PATH" || \
    die "target full dependency readiness failed before commit"
}

assert_ready() {
  run_system_python_control - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=5) as response:
    payload = json.load(response)
if response.status != 200 or payload.get("ok") is not True:
    raise SystemExit("canonical /api/ready is not healthy")
PY
}

assert_lb_ready() {
  run_system_python_control - <<'PY'
import json
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1/api/ready",
    headers={"Host": "linasaibot.com", "X-Forwarded-Proto": "https"},
)
with urllib.request.urlopen(request, timeout=5) as response:
    payload = json.load(response)
if response.status != 200 or payload.get("ok") is not True:
    raise SystemExit("LB-facing /api/ready is not healthy")
PY
}

assert_health_while_drained() {
  run_system_python_control - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8003/api/health", timeout=5) as response:
    payload = json.load(response)
if response.status != 200 or payload.get("ok") is not True:
    raise SystemExit("canonical /api/health is not healthy")
PY
}

assert_direct_maintenance_readiness() {
  run_system_python_control - <<'PY'
import json
import urllib.error
import urllib.request

try:
    urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=5)
except urllib.error.HTTPError as exc:
    payload = json.load(exc)
    if exc.code == 503 and payload == {
        "ok": False,
        "role": "readiness",
        "checks": {"maintenance": {"ok": False}},
    }:
        raise SystemExit(0)
    raise SystemExit("direct LB readiness maintenance response is invalid") from exc
raise SystemExit("direct LB port 8003 still advertises readiness")
PY
}

assert_public_ready() {
  run_system_python_control - <<'PY'
import json
import urllib.request

request = urllib.request.Request(
    "https://linasaibot.com/api/ready",
    headers={"User-Agent": "linasbot-ha-deploy-readiness-proof/1"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    payload = json.load(response)
if response.status != 200 or payload.get("ok") is not True:
    raise SystemExit("public load-balancer readiness is not healthy")
PY
}

assert_maintenance_readiness() {
  # Must remain usable while the canonical venv is between old/new versions.
  run_system_python_control - <<'PY'
import json
import urllib.error
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1/api/ready",
    headers={"Host": "linasaibot.com", "X-Forwarded-Proto": "https"},
)
try:
    urllib.request.urlopen(request, timeout=5)
except urllib.error.HTTPError as exc:
    payload = json.load(exc)
    if exc.code == 503 and payload == {
        "ok": False,
        "role": "readiness",
        "checks": {"maintenance": {"ok": False}},
    }:
        raise SystemExit(0)
    raise SystemExit("maintenance readiness response is invalid") from exc
raise SystemExit("maintenance marker did not withdraw readiness")
PY
}

assert_target_object() {
  local target_sha="$1"
  local expected_helper_hash="$2"
  local actual_helper_hash
  git -C "$REPO_DIR" fetch --no-tags origin main
  git -C "$REPO_DIR" cat-file -e "${target_sha}^{commit}"
  git -C "$REPO_DIR" merge-base --is-ancestor "$target_sha" origin/main || \
    die "authorized target is not on fetched origin/main"
  git -C "$REPO_DIR" cat-file -e "$target_sha:main.py"
  git -C "$REPO_DIR" cat-file -e "$target_sha:deploy.sh"
  git -C "$REPO_DIR" cat-file -e "$target_sha:$HELPER_REPO_PATH"
  git -C "$REPO_DIR" cat-file -e "$target_sha:$CLUSTER_ENV_HELPER_REPO_PATH"
  git -C "$REPO_DIR" cat-file -e "$target_sha:$PRODUCTION_GUARD_REPO_PATH"
  git -C "$REPO_DIR" cat-file -e "$target_sha:$RELEASE_VERIFY_REPO_PATH"
  git -C "$REPO_DIR" cat-file -e "$target_sha:$RELEASE_READINESS_REPO_PATH"
  git -C "$REPO_DIR" cat-file -e "$target_sha:$RELEASE_ALEMBIC_MIGRATE_REPO_PATH"
  git -C "$REPO_DIR" cat-file -e "$target_sha:$REQUIREMENTS_LOCK_REPO_PATH"
  git -C "$REPO_DIR" cat-file -e "$target_sha:scripts/ha/verify_meta_release_ha.sh"
  git -C "$REPO_DIR" cat-file -e "$target_sha:scripts/prod_cm_preserve_durable_flags.sh"
  git -C "$REPO_DIR" cat-file -e "$target_sha:scripts/prod_upsert_model_routing_env.py"
  git -C "$REPO_DIR" cat-file -e "$target_sha:deploy/systemd/linasbot-worker@.service"
  git -C "$REPO_DIR" cat-file -e "$target_sha:deploy/nginx-linasaibot.conf"
  if git -C "$REPO_DIR" ls-tree -r --name-only "$target_sha" | \
    grep -Eq '(^|/)(__pycache__/|[^/]+[.](pyc|pyo)$)'; then
    die "authorized target contains forbidden Python bytecode artifacts"
  fi
  git -C "$REPO_DIR" grep -Fq "/var/lib/linasbot/meta-ha/maintenance" \
    "$target_sha" -- modules/dashboard_api_health.py || \
    die "authorized target is not aware of the persistent maintenance marker"
  if git -C "$REPO_DIR" cat-file -e "$target_sha:linaslaserbot-2.7.22" 2>/dev/null; then
    die "authorized target contains the legacy nested runtime"
  fi
  actual_helper_hash="$(git -C "$REPO_DIR" show "$target_sha:$HELPER_REPO_PATH" | sha256sum | awk '{print $1}')"
  test "$actual_helper_hash" = "$expected_helper_hash" || die "authorized helper blob hash mismatch"
}

check_canonical_env_security() {
  local env_path="$REPO_DIR/.env"
  if [ -L "$env_path" ] || [ ! -f "$env_path" ]; then
    echo "[ha-deploy] canonical .env must be a regular non-symlink file" >&2
    return 1
  fi
  if [ "$(stat -c '%u:%g:%a' "$env_path")" != "0:0:600" ]; then
    echo "[ha-deploy] canonical .env must be root:root mode 0600" >&2
    return 1
  fi
}

audit_untracked_runtime() {
  local archive_parent="$1"
  local phase="$2"
  local expected_sha="$3"
  local path audit_dir list_path archive_path manifest_path target_entry target_blob
  local blocker=0
  local -a candidates=()
  local -a pathspecs=(
    '*.py' '*.pyi' '*.pyc' '*.pyo' '*.so' '*.pth'
    '*.sh' '*.bash' '*.zsh'
    '*.yml' '*.yaml' '*.toml' '*.ini' '*.cfg' '*.conf' '*.service'
    '*.js' '*.mjs' '*.cjs' '*.ts' '*.tsx' '*.jsx'
    '*.html' '*.css' '*.scss' '*.sql' '*.go' '*.rs' '*.c' '*.h'
    ':(exclude)venv/**'
    ':(exclude).venv/**'
    ':(exclude)dashboard/node_modules/**'
    ':(exclude)dashboard/build/**'
    ':(exclude)**/node_modules/**'
  )
  local -A seen=()

  while IFS= read -r -d '' path; do
    if [ -z "${seen[$path]+set}" ]; then
      candidates+=("$path")
      seen["$path"]=1
    fi
  done < <(git -C "$REPO_DIR" ls-files --others --exclude-standard -z -- "${pathspecs[@]}")
  while IFS= read -r -d '' path; do
    if [ -z "${seen[$path]+set}" ]; then
      candidates+=("$path")
      seen["$path"]=1
    fi
  done < <(git -C "$REPO_DIR" ls-files --others --ignored --exclude-standard -z -- "${pathspecs[@]}")
  while IFS= read -r -d '' path; do
    case "$path" in
      venv/* | .venv/* | dashboard/node_modules/* | dashboard/build/* | */node_modules/*)
        continue
        ;;
    esac
    if [ -f "$REPO_DIR/$path" ] && [ -x "$REPO_DIR/$path" ] && [ -z "${seen[$path]+set}" ]; then
      candidates+=("$path")
      seen["$path"]=1
    fi
  done < <(git -C "$REPO_DIR" ls-files --others --exclude-standard -z)
  while IFS= read -r -d '' path; do
    case "$path" in
      venv/* | .venv/* | dashboard/node_modules/* | dashboard/build/* | */node_modules/*)
        continue
        ;;
    esac
    if [ -f "$REPO_DIR/$path" ] && [ -x "$REPO_DIR/$path" ] && [ -z "${seen[$path]+set}" ]; then
      candidates+=("$path")
      seen["$path"]=1
    fi
  done < <(git -C "$REPO_DIR" ls-files --others --ignored --exclude-standard -z)

  if [ "${#candidates[@]}" -eq 0 ]; then
    return 0
  fi
  test ! -L "$BACKUP_ROOT" || die "HA backup root must not be a symlink"
  mkdir -p "$BACKUP_ROOT"
  chmod 0700 "$BACKUP_ROOT"
  test "$(stat -c '%u:%g:%a' "$BACKUP_ROOT")" = "0:0:700" || \
    die "HA backup root ownership or mode is unsafe"
  test ! -L "$archive_parent" || die "runtime audit archive parent must not be a symlink"
  mkdir -p "$archive_parent"
  chmod 0700 "$archive_parent"
  test "$(stat -c '%u:%g:%a' "$archive_parent")" = "0:0:700" || \
    die "runtime audit archive parent ownership or mode is unsafe"
  audit_dir="$(mktemp -d "$archive_parent/untracked-${phase}-${expected_sha}.XXXXXXXX")"
  chmod 0700 "$audit_dir"
  list_path="$audit_dir/runtime-paths.list"
  archive_path="$audit_dir/runtime-files.tar"
  manifest_path="$audit_dir/manifest.txt"
  : >"$list_path"
  : >"$manifest_path"
  chmod 0600 "$list_path" "$manifest_path"
  for path in "${candidates[@]}"; do
    printf '%s\0' "$path" >>"$list_path"
    target_entry="$(git -C "$REPO_DIR" ls-tree "$expected_sha" -- "$path")"
    if [[ "$target_entry" =~ ^100(644|755)[[:space:]]blob[[:space:]]([0-9a-f]{40})$'\t' ]]; then
      target_blob="${BASH_REMATCH[2]}"
      git -C "$REPO_DIR" cat-file -e "${target_blob}^{blob}" || \
        die "authorized target blob is missing for an archived runtime path"
      printf 'target-owned\t%s\t%s\n' "$target_blob" "$(printf '%q' "$path")" >>"$manifest_path"
      printf '[ha-deploy] archived target-owned runtime path before exact blob replacement: %q\n' \
        "$path" >&2
    else
      printf 'owner-blocker\t-\t%s\n' "$(printf '%q' "$path")" >>"$manifest_path"
      printf '[ha-deploy] target-untracked runtime blocker: %q\n' "$path" >&2
      blocker=1
    fi
  done
  tar --null --verbatim-files-from --numeric-owner -C "$REPO_DIR" \
    -cpf "$archive_path" -T "$list_path"
  chmod 0600 "$archive_path"
  sha256sum "$archive_path" | awk '{print $1}' >"$archive_path.sha256"
  chmod 0600 "$archive_path.sha256"
  test "$(sha256sum "$archive_path" | awk '{print $1}')" = "$(<"$archive_path.sha256")" || \
    die "untracked runtime audit archive verification failed"
  printf '[ha-deploy] preserved untracked runtime candidates without deletion: %s\n' "$archive_path" >&2
  if [ "$blocker" = "1" ]; then
    printf '[ha-deploy] target-untracked runtime blockers require owner remediation\n' >&2
    return 1
  fi
  return 0
}

node_preflight() {
  local target_sha="$1"
  local expected_node_id="$2"
  local expected_helper_hash="$3"
  local expected_bootstrap_plan="${4:-}"
  local expected_lb_attestation_sha="${5:-}"
  local expected_lb_projection_sha="${6:-}"
  local head node drain peer queue python_runtime_cluster_sha baseline_artifacts
  local lb_observed_at
  local blocker=0
  python_runtime_cluster_sha="$(assert_python_runtime_contract "$expected_node_id")"
  assert_canonical_repo
  assert_no_other_meta_transaction
  if [ -n "$expected_bootstrap_plan" ]; then
    validate_digest "$expected_bootstrap_plan"
    read_bootstrap_commit_proof "$expected_node_id" "$expected_bootstrap_plan" \
      "$python_runtime_cluster_sha" >/dev/null
  fi
  head="$(current_head)"
  validate_sha "$head"
  assert_target_object "$target_sha" "$expected_helper_hash"
  lb_observed_at="$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$expected_lb_attestation_sha" "$expected_lb_projection_sha")"
  git -C "$REPO_DIR" diff --quiet "$head" -- || die "live tracked tree is dirty"
  git -C "$REPO_DIR" diff --cached --quiet "$head" -- || die "live index is dirty"
  audit_untracked_runtime "$BACKUP_ROOT/untracked-audit" "preflight-${expected_node_id}" "$target_sha" || \
    blocker=1
  assert_no_shadow_runtime "$expected_node_id" || blocker=1
  assert_controlled_failover_static_guard_contract || blocker=1
  check_canonical_env_security || blocker=1
  if [ "$blocker" != "0" ]; then
    die "node has preflight blockers; originals were not deleted"
  fi
  command -v curl >/dev/null || die "curl is not provisioned"
  command -v nginx >/dev/null || die "nginx is not provisioned"
  command -v systemd-run >/dev/null || die "systemd-run is not provisioned"
  # The serving baseline venv is immutable rollback evidence and may predate
  # the first portable-runtime cutover. All staging and every target venv use
  # the receipt-bound SYSTEM_PYTHON; target admission proves exact 3.13.15.
  test -x "$REPO_DIR/venv/bin/python" && test ! -L "$REPO_DIR/venv" || \
    die "live rollback venv executable is missing or unsafe"
  mapfile -t contract < <(read_ha_contract "$expected_node_id")
  node="${contract[0]:-}"
  drain="${contract[1]:-}"
  peer="${contract[2]:-}"
  test "$node" = "$expected_node_id" || die "node identity preflight failed"
  [[ "$drain" =~ ^[0-9]+$ ]] || die "drain preflight failed"
  assert_exact_runtime_process_contract enabled
  assert_active_runtime_process_env_contract "$target_sha" "$target_sha" "$expected_node_id"
  assert_unit_contract linasbot
  for queue in "${WORKER_QUEUES[@]}"; do
    if systemctl is-active --quiet "linasbot-worker@${queue}.service" || \
       systemctl is-enabled --quiet "linasbot-worker@${queue}.service"; then
      assert_unit_contract "linasbot-worker@${queue}.service"
    fi
  done
  systemctl is-active --quiet nginx || die "nginx is not active"
  nginx -t >/dev/null 2>&1 || die "nginx configuration is invalid"
  grep -q 'root /opt/linasbot/dashboard/build;' /etc/nginx/sites-available/linasbot || \
    die "nginx dashboard root is noncanonical"
  grep -q 'proxy_pass http://127.0.0.1:8003;' /etc/nginx/sites-available/linasbot || \
    die "nginx API upstream is noncanonical"
  if grep -qE 'linaslaserbot-2\.7\.22|127\.0\.0\.1:8000' /etc/nginx/sites-available/linasbot; then
    die "nginx still references a legacy runtime"
  fi
  assert_path_absent "$MAINTENANCE_FILE" \
    "pre-existing persistent maintenance marker requires owner investigation"
  assert_path_absent "$VOLATILE_MAINTENANCE_FILE" \
    "pre-existing volatile maintenance marker requires owner investigation"
  assert_path_absent /etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf \
    "pre-existing HA API boot guard requires owner recovery"
  assert_path_absent /etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf \
    "pre-existing HA worker boot guard requires owner recovery"
  assert_ready
  assert_lb_ready
  baseline_artifacts="$(live_baseline_artifact_evidence)"
  printf 'NODE_ID=%s\nPREVIOUS_SHA=%s\nDRAIN_SECONDS=%s\nCONFIGURED_PEER=%s\nBOOTSTRAP_PLAN_SHA=%s\nPYTHON_RUNTIME_CLUSTER_SHA=%s\nLB_ATTESTATION_OBSERVED_AT=%s\nBASELINE_ARTIFACT_EVIDENCE=%s\n' \
    "$node" "$head" "$drain" "$peer" "$expected_bootstrap_plan" \
    "$python_runtime_cluster_sha" "$lb_observed_at" "$baseline_artifacts"
}

capture_service_state() {
  local output="$1"
  local unit enabled active
  local -a records=()
  test ! -e "$output" && test ! -L "$output" || \
    die "service state destination already exists or is unsafe"
  for unit in linasbot.service \
    linasbot-worker@high_priority.service \
    linasbot-worker@interactive.service \
    linasbot-worker@background.service \
    linasbot-worker@expensive.service; do
    enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
    active="$(systemctl is-active "$unit" 2>/dev/null || true)"
    test "$enabled" = "enabled" || test "$enabled" = "disabled" || \
      die "service enablement state is outside the closed rollback schema: $unit"
    test "$active" = "active" || test "$active" = "inactive" || \
      die "service activity state is outside the closed rollback schema: $unit"
    records+=("$unit|$enabled|$active")
  done
  run_system_python_control - "$output" "${records[@]}" <<'PY'
import os
import stat
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
records = sys.argv[2:]
units = (
    "linasbot.service",
    "linasbot-worker@high_priority.service",
    "linasbot-worker@interactive.service",
    "linasbot-worker@background.service",
    "linasbot-worker@expensive.service",
)
if len(records) != len(units):
    raise SystemExit("service rollback inventory is incomplete")
for expected, record in zip(units, records, strict=True):
    fields = record.split("|")
    if (
        len(fields) != 3
        or fields[0] != expected
        or fields[1] not in {"enabled", "disabled"}
        or fields[2] not in {"active", "inactive"}
    ):
        raise SystemExit("service rollback inventory is outside its closed schema")
payload = ("\n".join(records) + "\n").encode("ascii")
parent = path.parent
parent_info = parent.lstat()
if (
    not stat.S_ISDIR(parent_info.st_mode)
    or stat.S_ISLNK(parent_info.st_mode)
    or parent_info.st_uid != 0
    or parent_info.st_gid != 0
    or stat.S_IMODE(parent_info.st_mode) != 0o700
):
    raise SystemExit("service rollback inventory parent is unsafe")
if path.exists() or path.is_symlink():
    raise SystemExit("service rollback inventory destination already exists")

# A SIGKILL before the atomic rename can leave only an owned temporary. Keep
# its bytes for audit, but never treat it as rollback authority.
prefix = f".{path.name}.capture."
archive_prefix = f"incomplete-service-state-{path.name}-"
existing_archives: dict[int, Path] = {}
for archive in sorted(parent.glob(archive_prefix + "*")):
    suffix = archive.name.removeprefix(archive_prefix)
    if not suffix.isdigit() or int(suffix) < 1 or str(int(suffix)) != suffix:
        raise SystemExit("incomplete service state archive name is invalid")
    info = archive.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise SystemExit("incomplete service state archive is unsafe")
    existing_archives[int(suffix)] = archive
if sorted(existing_archives) != list(range(1, len(existing_archives) + 1)):
    raise SystemExit("incomplete service state archive sequence is invalid")
next_index = len(existing_archives) + 1
for incomplete in sorted(parent.glob(prefix + "*")):
    info = incomplete.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise SystemExit("incomplete service state capture is unsafe")
    archive = parent / f"{archive_prefix}{next_index}"
    if archive.exists() or archive.is_symlink():
        raise SystemExit("incomplete service state archive destination exists")
    os.replace(incomplete, archive)
    next_index += 1

fd, temporary_name = tempfile.mkstemp(prefix=prefix, dir=parent)
temporary = Path(temporary_name)
try:
    os.fchmod(fd, 0o600)
    os.fchown(fd, 0, 0)
    os.write(fd, payload)
    os.fsync(fd)
    os.close(fd)
    fd = -1
    if path.exists() or path.is_symlink():
        raise SystemExit("service rollback inventory destination raced")
    os.replace(temporary, path)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    if fd >= 0:
        os.close(fd)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY
  validate_service_state_file "$output"
}

validate_service_state_file() {
  local path="$1"
  run_system_python_control - "$path" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
before = path.lstat()
if (
    not stat.S_ISREG(before.st_mode)
    or stat.S_ISLNK(before.st_mode)
    or before.st_uid != 0
    or before.st_gid != 0
    or stat.S_IMODE(before.st_mode) != 0o600
    or before.st_nlink != 1
    or before.st_size > 2048
):
    raise SystemExit("service rollback inventory is not a private regular file")
fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
try:
    opened = os.fstat(fd)
    if (before.st_dev, before.st_ino, before.st_size) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
    ):
        raise SystemExit("service rollback inventory changed while opening")
    raw = os.read(fd, 2049)
    if len(raw) > 2048 or os.read(fd, 1):
        raise SystemExit("service rollback inventory is oversized")
finally:
    os.close(fd)
try:
    records = raw.decode("ascii").splitlines()
except UnicodeDecodeError as exc:
    raise SystemExit("service rollback inventory is not ASCII") from exc
units = (
    "linasbot.service",
    "linasbot-worker@high_priority.service",
    "linasbot-worker@interactive.service",
    "linasbot-worker@background.service",
    "linasbot-worker@expensive.service",
)
if len(records) != len(units) or not raw.endswith(b"\n"):
    raise SystemExit("service rollback inventory is incomplete")
for expected, record in zip(units, records, strict=True):
    fields = record.split("|")
    if (
        len(fields) != 3
        or fields[0] != expected
        or fields[1] not in {"enabled", "disabled"}
        or fields[2] not in {"active", "inactive"}
    ):
        raise SystemExit("service rollback inventory has an invalid closed schema")
PY
}

assert_service_state_capture_is_pre_mutation() {
  local expected_sha node_id
  assert_path_absent "$DEPLOY_NODE_ACTIVE_FILE" \
    "cannot recapture service state after the per-node deploy boundary"
  assert_path_absent "$MAINTENANCE_FILE" \
    "cannot recapture service state after persistent maintenance"
  assert_path_absent "$VOLATILE_MAINTENANCE_FILE" \
    "cannot recapture service state after volatile maintenance"
  assert_path_absent /etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf \
    "cannot recapture service state after API guard publication"
  assert_path_absent /etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf \
    "cannot recapture service state after worker guard publication"
  expected_sha="$(current_head)"
  validate_sha "$expected_sha"
  node_id="$(configured_node_id)"
  assert_exact_runtime_process_contract enabled
  assert_active_runtime_process_env_contract "$expected_sha" "$expected_sha" "$node_id"
}

disable_runtime_autostart() {
  local queue
  local -a units=(linasbot.service)
  # Do not stop the healthy process yet; only make every reboot fail closed
  # before publishing marker-dependent drop-ins.
  for queue in "${WORKER_QUEUES[@]}"; do
    units+=("linasbot-worker@${queue}.service")
  done
  systemctl disable "${units[@]}"
  systemctl is-enabled --quiet linasbot.service && \
    die "canonical API remained enabled before maintenance guard publication"
  for queue in "${WORKER_QUEUES[@]}"; do
    systemctl is-enabled --quiet "linasbot-worker@${queue}.service" && \
      die "canonical worker remained enabled before maintenance guard publication: $queue"
  done
  fsync_systemd_enablement_state
}

fsync_systemd_enablement_state() {
  local -a paths=(/etc/systemd/system)
  local directory
  for directory in \
    /etc/systemd/system/multi-user.target.wants \
    /etc/systemd/system/default.target.wants; do
    if [ -e "$directory" ] || [ -L "$directory" ]; then
      test -d "$directory" && test ! -L "$directory" || \
        die "systemd enablement directory is unsafe: $directory"
      paths+=("$directory")
    fi
  done
  fsync_path_and_parents "${paths[@]}"
}

fsync_path_and_parents() {
  run_system_python_control - "$@" <<'PY'
import os
import stat
import sys
from pathlib import Path

directories: set[Path] = set()
for raw in sys.argv[1:]:
    path = Path(raw)
    info = path.lstat()
    if stat.S_ISREG(info.st_mode):
        if stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
            raise SystemExit("durability file is unsafe")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (info.st_dev, info.st_ino, info.st_size) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ):
                raise SystemExit("durability file changed while opening")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directories.add(path.parent)
    elif stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        directories.add(path)
        directories.add(path.parent)
    else:
        raise SystemExit("durability path has an unsupported type")
for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
PY
}

fsync_tree() {
  run_system_python_control - "$@" <<'PY'
import os
import stat
import sys
from pathlib import Path

for raw_root in sys.argv[1:]:
    root = Path(raw_root)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise SystemExit("durability tree root is unsafe")
    directories: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.append(current_path)
        dirnames.sort()
        filenames.sort()
        for name in filenames:
            path = current_path / name
            child = path.lstat()
            if stat.S_ISLNK(child.st_mode):
                continue
            if not stat.S_ISREG(child.st_mode) or child.st_nlink != 1:
                raise SystemExit("durability tree contains an unsupported object")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(descriptor)
                if (child.st_dev, child.st_ino, child.st_size) != (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                ):
                    raise SystemExit("durability tree file changed while opening")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    parent = os.open(root.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
PY
}

write_private_state() {
  local path="$1"
  local value="$2"
  run_system_python_control - "$path" "$value" <<'PY'
import os
import stat
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
payload = (sys.argv[2] + "\n").encode("ascii")
parent = path.parent
info = parent.lstat()
if (
    not stat.S_ISDIR(info.st_mode)
    or stat.S_ISLNK(info.st_mode)
    or info.st_uid != 0
    or info.st_gid != 0
    or stat.S_IMODE(info.st_mode) & 0o022
):
    raise SystemExit("private state parent is unsafe")
descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.state.", dir=parent)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    os.fchown(descriptor, 0, 0)
    os.write(descriptor, payload)
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1
    if path.exists() or path.is_symlink():
        current = path.lstat()
        if (
            not stat.S_ISREG(current.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or current.st_uid != 0
            or current.st_gid != 0
            or stat.S_IMODE(current.st_mode) != 0o600
            or current.st_nlink != 1
        ):
            raise SystemExit("existing private state is unsafe")
    os.replace(temporary, path)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY
}

copy_private_file_durable() {
  local source="$1"
  local destination="$2"
  run_system_python_control - "$source" "$destination" <<'PY'
import os
import stat
import sys
import tempfile
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
before = source.lstat()
if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
    raise SystemExit("private copy source is unsafe")
descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    opened = os.fstat(descriptor)
    if (before.st_dev, before.st_ino, before.st_size) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
    ):
        raise SystemExit("private copy source changed while opening")
    payload = b""
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        payload += chunk
        if len(payload) > 1_048_576:
            raise SystemExit("private copy source is oversized")
finally:
    os.close(descriptor)
parent = destination.parent
descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.copy.", dir=parent)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    os.fchown(descriptor, 0, 0)
    os.write(descriptor, payload)
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1
    os.replace(temporary, destination)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY
}

archive_path() {
  local archive="$1"
  shift
  tar --numeric-owner -C / -cpf "$archive" "$@"
  chmod 0600 "$archive"
  fsync_path_and_parents "$archive"
  write_private_state "$archive.sha256" "$(sha256sum "$archive" | awk '{print $1}')"
  verify_archive "$archive"
}

verify_archive() {
  local archive="$1"
  local expected actual
  test -f "$archive" && test ! -L "$archive" || die "rollback archive is missing or unsafe"
  test -f "$archive.sha256" && test ! -L "$archive.sha256" || \
    die "rollback archive checksum is missing or unsafe"
  test "$(stat -c '%u:%g:%a' "$archive")" = "0:0:600" || \
    die "rollback archive ownership or mode is unsafe"
  test "$(stat -c '%u:%g:%a' "$archive.sha256")" = "0:0:600" || \
    die "rollback archive checksum ownership or mode is unsafe"
  expected="$(<"$archive.sha256")"
  [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || die "rollback archive checksum is invalid"
  actual="$(sha256sum "$archive" | awk '{print $1}')"
  test "$actual" = "$expected" || die "rollback archive integrity check failed"
}

stage_manifest_tool() {
  local operation="$1"
  local tx_dir="$2"
  local target_sha="$3"
  local previous_sha="$4"
  local python_runtime_cluster_sha
  python_runtime_cluster_sha="$(assert_python_runtime_contract "$(configured_node_id)")"
  run_system_python_control - "$operation" "$tx_dir" "$target_sha" "$previous_sha" \
    "$python_runtime_cluster_sha" <<'PY'
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

operation, raw_tx_dir, target_sha, previous_sha, python_runtime_cluster_sha = sys.argv[1:]
if not __import__("re").fullmatch(r"[0-9a-f]{64}", python_runtime_cluster_sha):
    raise SystemExit("stage Python runtime cluster digest is invalid")
tx_dir = Path(raw_tx_dir)
manifest_path = tx_dir / "stage.complete"
critical = (
    "previous.sha",
    "target.sha",
    "root.env",
    "venv.tar",
    "venv.tar.sha256",
    "data-pre-drain.tar",
    "data-pre-drain.tar.sha256",
    "dashboard-build.tar",
    "dashboard-build.tar.sha256",
    "nginx.tar",
    "nginx.tar.sha256",
    "systemd.tar",
    "systemd.tar.sha256",
    "predrain-service-state",
    "baseline-artifacts.json",
    "release-bundle.json",
    "runtime-data.list",
    "runtime-data.tar",
    "runtime-data.tar.sha256",
    "deploy-version",
    "sibling-path",
)


def secure_file(path: Path) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
    ):
        raise SystemExit(f"stage authority file is unsafe: {path.name}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("stage authority file changed while opening")
        digest = hashlib.sha256()
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            digest.update(chunk)
            if len(payload) <= 65536:
                payload.extend(chunk)
        if operation == "publish":
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return digest.hexdigest().encode("ascii") + b"\0" + bytes(payload[:65537])


def secure_manifest(path: Path) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or before.st_size > (1 << 20)
    ):
        raise SystemExit("stage manifest is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("stage manifest changed while opening")
        raw = os.read(descriptor, (1 << 20) + 1)
        if len(raw) > (1 << 20) or os.read(descriptor, 1):
            raise SystemExit("stage manifest is oversized")
        return raw
    finally:
        os.close(descriptor)


def tree_digest(root: Path) -> str:
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise SystemExit("staged tree root is unsafe")
    digest = hashlib.sha256()
    directories: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.append(current_path)
        dirnames.sort()
        filenames.sort()
        for name in [*dirnames, *filenames]:
            path = current_path / name
            relative = path.relative_to(root).as_posix().encode("utf-8")
            info = path.lstat()
            digest.update(len(relative).to_bytes(4, "big") + relative)
            digest.update(stat.S_IMODE(info.st_mode).to_bytes(4, "big"))
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path).encode("utf-8")
                digest.update(b"L" + len(target).to_bytes(4, "big") + target)
            elif stat.S_ISDIR(info.st_mode):
                digest.update(b"D")
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    opened = os.fstat(descriptor)
                    if (info.st_dev, info.st_ino, info.st_size) != (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_size,
                    ):
                        raise SystemExit("staged file changed while opening")
                    file_digest = hashlib.sha256()
                    while True:
                        chunk = os.read(descriptor, 1 << 20)
                        if not chunk:
                            break
                        file_digest.update(chunk)
                    if operation == "publish":
                        os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                digest.update(b"F" + info.st_size.to_bytes(8, "big") + file_digest.digest())
            else:
                raise SystemExit("staged tree contains an unsupported or multiply-linked object")
    if operation == "publish":
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    return digest.hexdigest()


file_hashes: dict[str, str] = {}
payloads: dict[str, bytes] = {}
for relative in critical:
    encoded_digest, payload = secure_file(tx_dir / relative).split(b"\0", 1)
    file_hashes[relative] = encoded_digest.decode("ascii")
    payloads[relative] = payload
if payloads["target.sha"] != (target_sha + "\n").encode("ascii"):
    raise SystemExit("stage target SHA authority changed")
if payloads["previous.sha"] != (previous_sha + "\n").encode("ascii"):
    raise SystemExit("stage previous SHA authority changed")
for archive in ("venv.tar", "data-pre-drain.tar", "dashboard-build.tar", "nginx.tar", "systemd.tar", "runtime-data.tar"):
    if payloads[archive + ".sha256"] != (file_hashes[archive] + "\n").encode("ascii"):
        raise SystemExit("stage archive checksum authority changed")
baseline_artifacts = json.loads(payloads["baseline-artifacts.json"])
if (
    not isinstance(baseline_artifacts, dict)
    or set(baseline_artifacts) != {
        "schema", "artifact_record_count", "artifact_projection_sha256",
        "python_executable_sha256",
    }
    or baseline_artifacts.get("schema") != 1
    or not isinstance(baseline_artifacts.get("artifact_record_count"), int)
    or baseline_artifacts["artifact_record_count"] < 1
    or any(
        __import__("re").fullmatch(r"[0-9a-f]{64}", str(baseline_artifacts.get(key) or ""))
        is None
        for key in ("artifact_projection_sha256", "python_executable_sha256")
    )
):
    raise SystemExit("baseline artifact evidence is invalid")
release_bundle = json.loads(payloads["release-bundle.json"])
release_keys = {
    "schema", "artifact_id", "artifact_api_sha256", "manifest_sha256",
    "repository", "workflow_ref", "run_id", "run_attempt", "target_sha",
    "source_bundle", "source_locks", "toolchains", "payloads",
}
if (
    not isinstance(release_bundle, dict)
    or set(release_bundle) != release_keys
    or release_bundle.get("schema") != 1
    or release_bundle.get("target_sha") != target_sha
    or not isinstance(release_bundle.get("artifact_id"), int)
    or release_bundle["artifact_id"] < 1
    or not isinstance(release_bundle.get("run_id"), int)
    or release_bundle["run_id"] < 1
    or not isinstance(release_bundle.get("run_attempt"), int)
    or release_bundle["run_attempt"] < 1
    or any(
        __import__("re").fullmatch(r"[0-9a-f]{64}", str(release_bundle.get(key) or ""))
        is None
        for key in ("artifact_api_sha256", "manifest_sha256")
    )
):
    raise SystemExit("release bundle stage authority is invalid")
sibling_text = payloads["sibling-path"].decode("ascii", errors="strict")
if not sibling_text.endswith("\n"):
    raise SystemExit("stage sibling authority is malformed")
sibling = Path(sibling_text.rstrip("\n"))
expected_sibling = Path("/opt") / f".linasbot-ha-rollback-{tx_dir.name}"
if sibling != expected_sibling:
    raise SystemExit("stage sibling authority path changed")
sibling_info = sibling.lstat()
repo_info = Path("/opt/linasbot").lstat()
if (
    not stat.S_ISDIR(sibling_info.st_mode)
    or stat.S_ISLNK(sibling_info.st_mode)
    or sibling_info.st_uid != 0
    or sibling_info.st_gid != 0
    or stat.S_IMODE(sibling_info.st_mode) != 0o700
    or sibling_info.st_dev != repo_info.st_dev
):
    raise SystemExit("stage sibling rollback directory is unsafe")
entries = sorted(sibling.iterdir(), key=lambda item: item.name)
if operation not in {"verify-recovery", "evidence"} and entries:
    raise SystemExit("stage sibling rollback directory crossed activation early")
if operation in {"verify-recovery", "evidence"}:
    allowed = __import__("re").compile(
        r"(?:live-(?:venv|dashboard-build)|"
        r"failed-(?:venv|dashboard-build|data)-g[0-9]{4}|"
        r"partial-(?:venv|dashboard-build|data)-g[0-9]{4}-[1-9][0-9]*)"
    )
    for entry in entries:
        info = entry.lstat()
        if (
            not allowed.fullmatch(entry.name)
            or not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or info.st_dev != sibling_info.st_dev
        ):
            raise SystemExit("stage sibling rollback generation is unsafe")
trees = {
    "stage/repo": tree_digest(tx_dir / "stage/repo"),
    "stage/repo/dashboard/build": tree_digest(tx_dir / "stage/repo/dashboard/build"),
    "stage/wheels": tree_digest(tx_dir / "stage/wheels"),
    "stage/control-plane": tree_digest(tx_dir / "stage/control-plane"),
}
toolchain = {
    "qg_toolchains": release_bundle["toolchains"],
    "python_runtime_cluster_sha256": python_runtime_cluster_sha,
}
manifest = {
    "schema": 1,
    "target_sha": target_sha,
    "previous_sha": previous_sha,
    "files": file_hashes,
    "trees": trees,
    "toolchain": toolchain,
    "sibling": {"path": str(sibling), "device": sibling_info.st_dev},
}
encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
if operation in {"verify", "verify-recovery", "evidence"}:
    if secure_manifest(manifest_path) != encoded:
        raise SystemExit("stage manifest or staged authority changed")
    if operation == "evidence":
        print(json.dumps({
            "schema": 1,
            "target_sha": target_sha,
            "deploy_version": payloads["deploy-version"].decode("ascii").strip(),
            "wheelhouse_sha256": trees["stage/wheels"],
            "dashboard_build_sha256": trees["stage/repo/dashboard/build"],
            "control_plane_sha256": trees["stage/control-plane"],
            "baseline_artifacts": baseline_artifacts,
            "release_bundle": release_bundle,
            "toolchain": toolchain,
        }, sort_keys=True, separators=(",", ":")))
elif operation == "publish":
    if manifest_path.exists() or manifest_path.is_symlink():
        raise SystemExit("stage manifest already exists")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".stage.complete.", dir=tx_dir)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, manifest_path)
        for directory in (sibling, sibling.parent, tx_dir / "stage", tx_dir, tx_dir.parent):
            directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
else:
    raise SystemExit("unknown stage manifest operation")
PY
}

publish_stage_manifest() {
  stage_manifest_tool publish "$@"
  stage_manifest_tool verify "$@"
}

verify_stage_manifest() {
  stage_manifest_tool verify "$@"
}

verify_stage_manifest_recovery() {
  stage_manifest_tool verify-recovery "$@"
}

stage_artifact_evidence() {
  stage_manifest_tool evidence "$@"
}

assert_stage_artifact_parity() {
  local peer_host="$1"
  local tx_dir="$2"
  local target_sha="$3"
  local local_previous="$4"
  local peer_previous="$5"
  local local_evidence peer_evidence
  local_evidence="$(stage_artifact_evidence "$tx_dir" "$target_sha" "$local_previous")"
  peer_evidence="$(remote_node "$peer_host" stage-evidence \
    "$target_sha" "$peer_previous" "$tx_dir")"
  run_system_python_control - "$local_evidence" "$peer_evidence" \
    "$local_previous" "$peer_previous" <<'PY' || \
    die "target artifacts or steady rollback baseline artifacts differ between HA nodes"
import json
import sys

node01 = json.loads(sys.argv[1])
node02 = json.loads(sys.argv[2])
node01_previous, node02_previous = sys.argv[3:]
keys = {
    "schema", "target_sha", "deploy_version", "wheelhouse_sha256",
    "dashboard_build_sha256", "control_plane_sha256", "toolchain",
    "baseline_artifacts", "release_bundle",
}
if not isinstance(node01, dict) or not isinstance(node02, dict):
    raise SystemExit(1)
if set(node01) != keys or set(node02) != keys:
    raise SystemExit(1)
target_keys = keys - {"baseline_artifacts"}
if any(node01[key] != node02[key] for key in target_keys):
    raise SystemExit(1)
if node01_previous == node02_previous and node01["baseline_artifacts"] != node02["baseline_artifacts"]:
    raise SystemExit(1)
PY
}

activation_state_tool() {
  local operation="$1"
  local tx_dir="$2"
  local target_sha="$3"
  local previous_sha="$4"
  local phase="${5:-}"
  local generation="${6:-}"
  run_system_python_control - "$operation" "$tx_dir" "$target_sha" "$previous_sha" "$phase" "$generation" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

operation, raw_tx_dir, target_sha, previous_sha, requested_phase, raw_generation = sys.argv[1:]
tx_dir = Path(raw_tx_dir)
state_path = tx_dir / "activation.state"
manifest_path = tx_dir / "stage.complete"
activation_root = tx_dir / "activation"
history_root = activation_root / "history"
phases = (
    "quiesced",
    "venv-moved",
    "dashboard-moved",
    "target-reset-started",
    "target-installed",
    "activated",
    "rollback-started",
    "rollback-live-moved",
    "restored",
    "rolled-back",
)


def read_secure(path: Path, *, limit: int = 1 << 20) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or before.st_size > limit
    ):
        raise SystemExit("activation authority file is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("activation authority changed while opening")
        raw = os.read(descriptor, limit + 1)
        if len(raw) > limit or os.read(descriptor, 1):
            raise SystemExit("activation authority file is oversized")
        return raw
    finally:
        os.close(descriptor)


if operation in {"read", "read-generation"} and not (
    state_path.exists() or state_path.is_symlink()
):
    print("")
    raise SystemExit(0)

manifest_raw = read_secure(manifest_path)
manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()


def tree_digest(path: Path) -> str:
    root_info = path.lstat()
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or stat.S_ISLNK(root_info.st_mode)
        or root_info.st_uid != 0
        or root_info.st_gid != 0
    ):
        raise SystemExit("activation sibling artifact is unsafe")
    digest = hashlib.sha256()
    for current, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in [*dirnames, *filenames]:
            child = current_path / name
            relative = child.relative_to(path).as_posix().encode("utf-8")
            info = child.lstat()
            digest.update(len(relative).to_bytes(4, "big") + relative)
            digest.update(stat.S_IMODE(info.st_mode).to_bytes(4, "big"))
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(child).encode("utf-8")
                digest.update(b"L" + len(target).to_bytes(4, "big") + target)
            elif stat.S_ISDIR(info.st_mode):
                digest.update(b"D")
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                descriptor = os.open(child, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    opened = os.fstat(descriptor)
                    if (info.st_dev, info.st_ino, info.st_size) != (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_size,
                    ):
                        raise SystemExit("activation sibling artifact changed while opening")
                    file_digest = hashlib.sha256()
                    while True:
                        chunk = os.read(descriptor, 1 << 20)
                        if not chunk:
                            break
                        file_digest.update(chunk)
                finally:
                    os.close(descriptor)
                digest.update(b"F" + info.st_size.to_bytes(8, "big") + file_digest.digest())
            else:
                raise SystemExit("activation sibling artifact contains an unsafe object")
    return digest.hexdigest()


def sibling_artifacts() -> dict[str, str]:
    sibling = Path("/opt") / f".linasbot-ha-rollback-{tx_dir.name}"
    info = sibling.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise SystemExit("activation sibling directory is unsafe")
    allowed = re.compile(
        r"(?:live-(?:venv|dashboard-build)|"
        r"failed-(?:venv|dashboard-build|data)-g[0-9]{4}|"
        r"partial-(?:venv|dashboard-build|data)-g[0-9]{4}-[1-9][0-9]*)"
    )
    result: dict[str, str] = {}
    for child in sorted(sibling.iterdir(), key=lambda item: item.name):
        if not allowed.fullmatch(child.name):
            raise SystemExit("activation sibling directory has an unknown generation artifact")
        result[child.name] = tree_digest(child)
    return result


def generation_files(generation: int) -> tuple[dict[str, str], Path]:
    relative_root = Path("activation") / f"g{generation:04d}"
    generation_root = tx_dir / relative_root
    names = (
        "data-quiesced.tar",
        "data-quiesced.tar.sha256",
        "runtime-quiesced.list",
        "runtime-quiesced.tar",
        "runtime-quiesced.tar.sha256",
        "root-quiesced.env",
    )
    result: dict[str, str] = {}
    for name in names:
        relative = (relative_root / name).as_posix()
        path = tx_dir / relative
        if path.exists() or path.is_symlink():
            if name in {"data-quiesced.tar", "runtime-quiesced.tar"}:
                before = path.lstat()
                if (
                    not stat.S_ISREG(before.st_mode)
                    or stat.S_ISLNK(before.st_mode)
                    or before.st_uid != 0
                    or before.st_gid != 0
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_nlink != 1
                ):
                    raise SystemExit("generation archive authority is unsafe")
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    opened = os.fstat(descriptor)
                    if (before.st_dev, before.st_ino, before.st_size) != (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_size,
                    ):
                        raise SystemExit("generation archive changed while opening")
                    digest = hashlib.sha256()
                    consumed = 0
                    while True:
                        chunk = os.read(descriptor, 1 << 20)
                        if not chunk:
                            break
                        consumed += len(chunk)
                        digest.update(chunk)
                    if consumed != opened.st_size:
                        raise SystemExit("generation archive size changed while hashing")
                finally:
                    os.close(descriptor)
                after = path.lstat()
                if (after.st_dev, after.st_ino, after.st_size) != (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                ):
                    raise SystemExit("generation archive changed after hashing")
                result[relative] = digest.hexdigest()
            else:
                result[relative] = hashlib.sha256(read_secure(path)).hexdigest()
    expected = {(relative_root / name).as_posix() for name in names}
    if result and set(result) != expected:
        raise SystemExit("generation quiesced rollback authority is incomplete")
    if result:
        archive_relative = (relative_root / "data-quiesced.tar").as_posix()
        checksum_relative = (relative_root / "data-quiesced.tar.sha256").as_posix()
        checksum = read_secure(tx_dir / checksum_relative).decode("ascii").strip()
        if checksum != result[archive_relative]:
            raise SystemExit("generation quiesced data checksum changed")
        runtime_archive = (relative_root / "runtime-quiesced.tar").as_posix()
        runtime_checksum = (relative_root / "runtime-quiesced.tar.sha256").as_posix()
        checksum = read_secure(tx_dir / runtime_checksum).decode("ascii").strip()
        if checksum != result[runtime_archive]:
            raise SystemExit("generation quiesced runtime checksum changed")
    return result, generation_root


def read_state() -> dict[str, object] | None:
    if not (state_path.exists() or state_path.is_symlink()):
        return None
    try:
        payload = json.loads(read_secure(state_path))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit("activation state is invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {
            "schema", "target_sha", "previous_sha", "stage_manifest_sha256",
            "generation", "quiesced", "release_artifacts", "sibling_artifacts", "phase",
        }
        or payload.get("schema") != 2
        or payload.get("target_sha") != target_sha
        or payload.get("previous_sha") != previous_sha
        or payload.get("stage_manifest_sha256") != manifest_sha256
        or not isinstance(payload.get("generation"), int)
        or not 1 <= payload["generation"] <= 9999
        or not isinstance(payload.get("quiesced"), dict)
        or not isinstance(payload.get("release_artifacts"), dict)
        or not isinstance(payload.get("sibling_artifacts"), dict)
        or payload.get("phase") not in phases
    ):
        raise SystemExit("activation state is outside its closed transaction schema")
    expected_quiesced, _ = generation_files(int(payload["generation"]))
    if payload["quiesced"] != expected_quiesced:
        raise SystemExit("activation state quiesced authority changed")
    allowed_release = {
        f"activation/g{payload['generation']:04d}/target-nginx.conf",
        f"activation/g{payload['generation']:04d}/installed-distributions.json",
    }
    for relative, expected_digest in payload["release_artifacts"].items():
        if relative not in allowed_release:
            raise SystemExit("activation release artifact schema is invalid")
        if hashlib.sha256(read_secure(tx_dir / relative)).hexdigest() != expected_digest:
            raise SystemExit("activation release artifact changed")
    event = history_root / f"g{payload['generation']:04d}-{payload['phase']}.json"
    if read_secure(event) != (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"):
        raise SystemExit("activation history event differs from current authority")
    return payload


current = read_state()


def publish_state_pointer(encoded: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".activation.state.adopt.", dir=tx_dir)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, state_path)
        directory = os.open(tx_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def adopt_pending_history_event(current_payload: dict[str, object] | None) -> dict[str, object] | None:
    """Finish an event-fsync -> pointer-replace ACK/power-loss boundary."""
    if current_payload is None:
        generation = 1
        candidates = ("quiesced",)
    else:
        generation = int(current_payload["generation"])
        current_phase = str(current_payload["phase"])
        forward_next = {
            "quiesced": "venv-moved",
            "venv-moved": "dashboard-moved",
            "dashboard-moved": "target-reset-started",
            "target-reset-started": "target-installed",
            "target-installed": "activated",
        }
        rollback_next = {
            "rollback-started": "rollback-live-moved",
            "rollback-live-moved": "restored",
            "restored": "rolled-back",
        }
        if current_phase == "rolled-back":
            generation += 1
            candidates = ("quiesced",)
        elif current_phase in forward_next:
            candidates = (forward_next[current_phase], "rollback-started")
        elif current_phase in rollback_next:
            candidates = (rollback_next[current_phase],)
        else:
            candidates = ()
    present = [history_root / f"g{generation:04d}-{phase}.json" for phase in candidates]
    present = [path for path in present if path.exists() or path.is_symlink()]
    if not present:
        return current_payload
    if len(present) != 1:
        raise SystemExit("activation history has ambiguous pending transitions")
    event_path = present[0]
    raw = read_secure(event_path)
    try:
        pending = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit("pending activation history event is invalid") from exc
    expected_phase = event_path.stem.split("-", 1)[1]
    if (
        not isinstance(pending, dict)
        or set(pending) != {
            "schema", "target_sha", "previous_sha", "stage_manifest_sha256",
            "generation", "quiesced", "release_artifacts", "sibling_artifacts", "phase",
        }
        or pending.get("schema") != 2
        or pending.get("target_sha") != target_sha
        or pending.get("previous_sha") != previous_sha
        or pending.get("stage_manifest_sha256") != manifest_sha256
        or pending.get("generation") != generation
        or pending.get("phase") != expected_phase
        or pending.get("sibling_artifacts") != sibling_artifacts()
    ):
        raise SystemExit("pending activation history event does not match live durable artifacts")
    expected_quiesced, _ = generation_files(generation)
    if pending.get("quiesced") != expected_quiesced:
        raise SystemExit("pending activation history quiesced authority changed")
    allowed_release = {
        f"activation/g{generation:04d}/target-nginx.conf",
        f"activation/g{generation:04d}/installed-distributions.json",
    }
    release_artifacts = pending.get("release_artifacts")
    if not isinstance(release_artifacts, dict):
        raise SystemExit("pending activation release artifact authority is invalid")
    for relative, expected_digest in release_artifacts.items():
        if relative not in allowed_release:
            raise SystemExit("pending activation release artifact schema is invalid")
        if hashlib.sha256(read_secure(tx_dir / relative)).hexdigest() != expected_digest:
            raise SystemExit("pending activation release artifact changed")
    encoded = (json.dumps(pending, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if raw != encoded:
        raise SystemExit("pending activation history event is not canonical")
    publish_state_pointer(encoded)
    return pending


current = adopt_pending_history_event(current)
if operation == "read":
    print("" if current is None else current["phase"])
    raise SystemExit(0)
if operation == "read-generation":
    print("" if current is None else current["generation"])
    raise SystemExit(0)
if operation == "verify-sibling":
    if current is None or current.get("sibling_artifacts") != sibling_artifacts():
        raise SystemExit("activation sibling generations differ from durable authority")
    raise SystemExit(0)
if operation == "release-evidence":
    if current is None or current.get("phase") != "activated":
        raise SystemExit("release artifact evidence requires an activated generation")
    if current.get("sibling_artifacts") != sibling_artifacts():
        raise SystemExit("activated sibling authority changed")
    try:
        stage = json.loads(manifest_raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit("stage manifest is invalid") from exc
    dashboard = tree_digest(Path("/opt/linasbot/dashboard/build"))
    if dashboard != stage.get("trees", {}).get("stage/repo/dashboard/build"):
        raise SystemExit("installed dashboard differs from staged artifact")
    print(json.dumps({
        "schema": 1,
        "target_sha": target_sha,
        "dashboard_build_sha256": dashboard,
        "release_artifacts": {
            Path(relative).name: digest
            for relative, digest in sorted(current["release_artifacts"].items())
        },
        "toolchain": stage.get("toolchain"),
    }, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)
if operation != "write" or requested_phase not in phases:
    raise SystemExit("activation state operation is invalid")
try:
    requested_generation = int(raw_generation)
except ValueError as exc:
    raise SystemExit("activation generation is invalid") from exc
if not 1 <= requested_generation <= 9999:
    raise SystemExit("activation generation is invalid")
quiesced, generation_root = generation_files(requested_generation)
if not quiesced:
    raise SystemExit("activation state cannot publish without quiesced rollback authority")
current_phase = "" if current is None else str(current["phase"])
current_generation = 0 if current is None else int(current["generation"])
if current_phase == requested_phase and current_generation == requested_generation:
    print(requested_phase)
    raise SystemExit(0)
forward = phases[:6]
allowed = False
if not current_phase and requested_phase == "quiesced" and requested_generation == 1:
    allowed = True
elif (
    current_phase == "rolled-back"
    and requested_phase == "quiesced"
    and requested_generation == current_generation + 1
):
    allowed = True
elif current_generation == requested_generation and current_phase in forward and requested_phase in forward:
    allowed = forward.index(requested_phase) == forward.index(current_phase) + 1
elif current_generation == requested_generation and current_phase in forward and requested_phase == "rollback-started":
    allowed = True
elif current_generation == requested_generation and current_phase == "rollback-started" and requested_phase == "rollback-live-moved":
    allowed = True
elif current_generation == requested_generation and current_phase == "rollback-live-moved" and requested_phase == "restored":
    allowed = True
elif current_generation == requested_generation and current_phase == "restored" and requested_phase == "rolled-back":
    allowed = True
if not allowed:
    raise SystemExit("activation state transition is not monotonic")
payload = {
    "schema": 2,
    "target_sha": target_sha,
    "previous_sha": previous_sha,
    "stage_manifest_sha256": manifest_sha256,
    "generation": requested_generation,
    "quiesced": quiesced,
    "release_artifacts": {},
    "sibling_artifacts": sibling_artifacts(),
    "phase": requested_phase,
}
for artifact_name in ("target-nginx.conf", "installed-distributions.json"):
    relative = f"activation/g{requested_generation:04d}/{artifact_name}"
    path = tx_dir / relative
    if path.exists() or path.is_symlink():
        payload["release_artifacts"][relative] = hashlib.sha256(read_secure(path)).hexdigest()
encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
for directory in (activation_root, history_root):
    if directory.exists() or directory.is_symlink():
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise SystemExit("activation history directory is unsafe")
    else:
        os.mkdir(directory, 0o700)
        os.chown(directory, 0, 0)
        parent_fd = os.open(directory.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
event_path = history_root / f"g{requested_generation:04d}-{requested_phase}.json"
if event_path.exists() or event_path.is_symlink():
    if read_secure(event_path) != encoded:
        raise SystemExit("activation history event changed")
else:
    event_fd, event_temporary_name = tempfile.mkstemp(prefix=".activation-event.", dir=history_root)
    event_temporary = Path(event_temporary_name)
    try:
        os.fchmod(event_fd, 0o600)
        os.fchown(event_fd, 0, 0)
        os.write(event_fd, encoded)
        os.fsync(event_fd)
        os.close(event_fd)
        event_fd = -1
        os.replace(event_temporary, event_path)
        history_fd = os.open(history_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(history_fd)
        finally:
            os.close(history_fd)
    finally:
        if event_fd >= 0:
            os.close(event_fd)
        try:
            event_temporary.unlink()
        except FileNotFoundError:
            pass
descriptor, temporary_name = tempfile.mkstemp(prefix=".activation.state.", dir=tx_dir)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    os.fchown(descriptor, 0, 0)
    os.write(descriptor, encoded)
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1
    os.replace(temporary, state_path)
    directory = os.open(tx_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
print(requested_phase)
PY
}

write_activation_phase() {
  activation_state_tool write "$@" >/dev/null
  test "$(activation_state_tool read "${@:1:3}")" = "$4" || \
    die "activation phase durable readback failed"
}

read_activation_phase() {
  activation_state_tool read "$@"
}

read_activation_generation() {
  activation_state_tool read-generation "$@"
}

verify_activation_sibling_authority() {
  activation_state_tool verify-sibling "$@"
}

recover_transaction_git_locks() {
  local tx_dir="$1"
  local generation="$2"
  local context="$3"
  local symbolic_ref
  validate_tx_dir "$tx_dir"
  [[ "$generation" =~ ^[1-9][0-9]{0,3}$ ]] || die "Git recovery generation is invalid"
  case "$context" in
    target-reset | rollback-reset) ;;
    *) die "Git recovery context is invalid" ;;
  esac
  symbolic_ref="$(git -C "$REPO_DIR" symbolic-ref --quiet HEAD 2>/dev/null || true)"
  run_system_python_control - "$REPO_DIR" "$LOCK_FILE" "$tx_dir" "$generation" \
    "$context" "$symbolic_ref" 9 0 0 <<'PY'
import fcntl
import hashlib
import os
import re
import stat
import sys
from pathlib import Path

(
    repo_raw,
    live_lock_raw,
    tx_raw,
    generation_raw,
    context,
    symbolic_ref,
    lock_fd_raw,
    expected_uid_raw,
    expected_gid_raw,
) = sys.argv[1:]
repo = Path(repo_raw)
git_dir = repo / ".git"
live_lock = Path(live_lock_raw)
tx_path = Path(tx_raw)
try:
    generation = int(generation_raw)
    lock_fd = int(lock_fd_raw)
    expected_uid = int(expected_uid_raw)
    expected_gid = int(expected_gid_raw)
except ValueError as exc:
    raise SystemExit("Git recovery numeric authority is invalid") from exc
if os.geteuid() != expected_uid or os.getegid() != expected_gid:
    raise SystemExit("Git recovery process ownership differs from its fixed authority")
if not 1 <= generation <= 9999 or context not in {"target-reset", "rollback-reset"}:
    raise SystemExit("Git recovery context is invalid")
if not re.fullmatch(r"[0-9a-f]{40}-[0-9]{14}-[0-9]+", tx_path.name):
    raise SystemExit("Git recovery transaction identity is invalid")


def exact_directory(path: Path, *, owner_root: bool, mode: int | None = None) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise SystemExit(f"Git recovery directory is unsafe: {path}")
    if owner_root and (info.st_uid != expected_uid or info.st_gid != expected_gid):
        raise SystemExit(f"Git recovery directory ownership is unsafe: {path}")
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise SystemExit(f"Git recovery directory mode is unsafe: {path}")


exact_directory(repo, owner_root=False)
exact_directory(git_dir, owner_root=False)
if repo.resolve(strict=True) != repo or git_dir.resolve(strict=True) != git_dir:
    raise SystemExit("Git recovery repository path is not canonical")

lock_info = live_lock.lstat()
fd_info = os.fstat(lock_fd)
if (
    not stat.S_ISREG(lock_info.st_mode)
    or stat.S_ISLNK(lock_info.st_mode)
    or lock_info.st_uid != expected_uid
    or lock_info.st_gid != expected_gid
    or stat.S_IMODE(lock_info.st_mode) != 0o600
    or (lock_info.st_dev, lock_info.st_ino) != (fd_info.st_dev, fd_info.st_ino)
):
    raise SystemExit("Git recovery does not hold the canonical Meta HA lock")
try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError as exc:
    raise SystemExit("Git recovery does not hold the exclusive Meta HA lock") from exc

if symbolic_ref:
    if (
        not re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]*", symbolic_ref)
        or ".." in symbolic_ref
        or any(part in {"", ".", ".."} for part in Path(symbolic_ref).parts)
        or symbolic_ref.endswith(".lock")
    ):
        raise SystemExit("Git symbolic HEAD is outside the closed recovery schema")

allowed: dict[Path, str] = {
    git_dir / "index.lock": "index.bin",
    git_dir / "HEAD.lock": "HEAD.bin",
    git_dir / "ORIG_HEAD.lock": "ORIG_HEAD.bin",
    git_dir / "logs/HEAD.lock": "logs-HEAD.bin",
}
if symbolic_ref:
    allowed[git_dir / f"{symbolic_ref}.lock"] = "current-ref.bin"
    allowed[git_dir / "logs" / f"{symbolic_ref}.lock"] = "current-ref-log.bin"


def under_repo(path: Path) -> bool:
    try:
        path.relative_to(repo)
    except ValueError:
        return False
    return True


# The shell owns the global HA lock, but an interrupted child Git process can
# outlive its caller briefly. Never move a lock that a live repository Git
# mutator may still own.
proc_root = Path("/proc")
if proc_root.is_dir():
    for process in proc_root.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            executable = Path(os.readlink(process / "exe")).name
            cwd = Path(os.readlink(process / "cwd"))
            command = (process / "cmdline").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if (executable == "git" or executable.startswith("git-")) and under_repo(cwd):
            raise SystemExit("a Git mutator is still running in the canonical repository")
        if executable == "git" or executable.startswith("git-"):
            decoded = [item.decode("utf-8", "surrogateescape") for item in command if item]
            if any(item == str(repo) or item.startswith(f"{repo}/") for item in decoded):
                raise SystemExit("a Git mutator still references the canonical repository")
        try:
            descriptors = list((process / "fd").iterdir())
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            descriptors = []
        for descriptor in descriptors:
            try:
                target = Path(os.readlink(descriptor))
            except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                continue
            if target in allowed:
                raise SystemExit("a process still owns a transaction Git lock")

present_locks = set(git_dir.rglob("*.lock"))
unknown = sorted(path for path in present_locks if path not in allowed)
if unknown:
    raise SystemExit(f"unknown Git lock blocks exact recovery: {unknown[0]}")


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


archive_root = git_dir / "linasbot-ha-orphan-locks"
archive_tx = archive_root / tx_path.name
archive_dir = archive_tx / f"g{generation:04d}-{context}"
current_parent = git_dir
for directory in (archive_root, archive_tx, archive_dir):
    if directory.exists() or directory.is_symlink():
        exact_directory(directory, owner_root=True, mode=0o700)
    else:
        os.mkdir(directory, 0o700)
        os.chown(directory, expected_uid, expected_gid)
        fsync_directory(current_parent)
    current_parent = directory

allowed_archive_stems = {Path(name).stem for name in allowed.values()}
archive_counters: dict[str, list[int]] = {stem: [] for stem in allowed_archive_stems}
for child in archive_dir.iterdir():
    match = re.fullmatch(
        r"(index|HEAD|ORIG_HEAD|logs-HEAD|current-ref|current-ref-log)-([0-9]{4})[.]bin",
        child.name,
    )
    if match is None or match.group(1) not in allowed_archive_stems:
        raise SystemExit("Git lock archive contains an unknown object")
    info = child.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) not in {0o600, 0o644}
        or info.st_size > (64 << 20)
    ):
        raise SystemExit("archived transaction Git lock is unsafe")
    # A power cut may persist the atomic rename before the post-rename chmod.
    # The root-only 0700 archive contains the bytes; normalize and fsync that
    # exact regular file before counters or any new reset attempt are trusted.
    if stat.S_IMODE(info.st_mode) == 0o644:
        descriptor = os.open(child, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (
                (opened.st_dev, opened.st_ino, opened.st_size)
                != (info.st_dev, info.st_ino, info.st_size)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
            ):
                raise SystemExit("archived Git lock changed during normalization")
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        fsync_directory(archive_dir)
    archive_counters[match.group(1)].append(int(match.group(2)))

for stem, counters in archive_counters.items():
    counters.sort()
    if counters != list(range(1, len(counters) + 1)):
        raise SystemExit(f"Git lock archive counter sequence is invalid: {stem}")

for source, archive_name in allowed.items():
    stem = Path(archive_name).stem
    counters = archive_counters[stem]
    source_exists = source.exists() or source.is_symlink()
    if source_exists:
        counter = len(counters) + 1
        if counter > 9999:
            raise SystemExit("too many interrupted Git reset attempts")
        destination = archive_dir / f"{stem}-{counter:04d}.bin"
        if destination.exists() or destination.is_symlink():
            raise SystemExit("next Git lock archive destination is not empty")
        info = source.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) not in {0o600, 0o644}
            or info.st_size > (64 << 20)
        ):
            raise SystemExit("transaction Git lock is unsafe")
        if source.stat().st_dev != archive_dir.stat().st_dev:
            raise SystemExit("transaction Git lock archive would cross devices")
        os.replace(source, destination)
        descriptor = os.open(destination, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise SystemExit("archived Git lock changed while opening")
            os.fchmod(descriptor, 0o600)
            os.fchown(descriptor, expected_uid, expected_gid)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        fsync_directory(source.parent)
        fsync_directory(archive_dir)
        counters.append(counter)
    for counter in counters:
        destination = archive_dir / f"{stem}-{counter:04d}.bin"
        descriptor = os.open(destination, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            digest = hashlib.sha256()
            for chunk in iter(lambda: os.read(descriptor, 1 << 20), b""):
                digest.update(chunk)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

remaining = set(git_dir.rglob("*.lock"))
if remaining:
    raise SystemExit("transaction Git locks remain after archival")
fsync_directory(archive_dir)
fsync_directory(archive_tx)
fsync_directory(archive_root)
fsync_directory(git_dir)
PY
}

write_installed_distribution_manifest() {
  local destination="$1"
  local payload
  payload="$(PYTHONDONTWRITEBYTECODE=1 "$REPO_DIR/venv/bin/python" -B -I - <<'PY'
import hashlib
import importlib.metadata
import json
import os
import stat
import sys
from pathlib import Path

packages = sorted(
    ({"name": item.metadata["Name"].lower(), "version": item.version} for item in importlib.metadata.distributions()),
    key=lambda item: (item["name"], item["version"]),
)
venv = Path(sys.prefix)
if venv != Path("/opt/linasbot/venv"):
    raise SystemExit("installed distribution manifest ran outside the canonical venv")
digest = hashlib.sha256()
entry_count = 0
for current, dirnames, filenames in os.walk(venv, topdown=True, followlinks=False):
    current_path = Path(current)
    dirnames.sort()
    filenames.sort()
    for name in [*dirnames, *filenames]:
        path = current_path / name
        relative = path.relative_to(venv).as_posix()
        info = path.lstat()
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise SystemExit("canonical venv contains forbidden Python bytecode")
        record = {"path": relative, "mode": stat.S_IMODE(info.st_mode)}
        if stat.S_ISLNK(info.st_mode):
            record.update({"type": "symlink", "target": os.readlink(path)})
        elif stat.S_ISDIR(info.st_mode):
            record.update({"type": "directory"})
        elif stat.S_ISREG(info.st_mode):
            file_hash = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    file_hash.update(chunk)
            record.update({"type": "file", "size": info.st_size, "sha256": file_hash.hexdigest()})
        else:
            raise SystemExit("canonical venv contains an unsupported filesystem object")
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
        entry_count += 1
executable = Path(os.path.realpath(sys.executable))
executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
print(json.dumps({
    "schema": 2,
    "python_version": sys.version.split()[0],
    "python_cache_tag": sys.implementation.cache_tag,
    "python_executable_sha256": executable_hash,
    "packages": packages,
    "venv_entry_count": entry_count,
    "venv_tree_sha256": digest.hexdigest(),
}, sort_keys=True, separators=(",", ":")))
PY
)"
  write_private_state "$destination" "$payload"
}

verify_installed_distribution_manifest() {
  local path="$1"
  local actual expected
  test -f "$path" && test ! -L "$path" || die "installed distribution authority is missing"
  actual="$(<"$path")"
  expected="$(PYTHONDONTWRITEBYTECODE=1 "$REPO_DIR/venv/bin/python" -B -I - <<'PY'
import hashlib
import importlib.metadata
import json
import os
import stat
import sys
from pathlib import Path

packages = sorted(
    ({"name": item.metadata["Name"].lower(), "version": item.version} for item in importlib.metadata.distributions()),
    key=lambda item: (item["name"], item["version"]),
)
venv = Path(sys.prefix)
if venv != Path("/opt/linasbot/venv"):
    raise SystemExit("installed distribution verification ran outside the canonical venv")
digest = hashlib.sha256()
entry_count = 0
for current, dirnames, filenames in os.walk(venv, topdown=True, followlinks=False):
    current_path = Path(current)
    dirnames.sort()
    filenames.sort()
    for name in [*dirnames, *filenames]:
        path = current_path / name
        relative = path.relative_to(venv).as_posix()
        info = path.lstat()
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise SystemExit("canonical venv contains forbidden Python bytecode")
        record = {"path": relative, "mode": stat.S_IMODE(info.st_mode)}
        if stat.S_ISLNK(info.st_mode):
            record.update({"type": "symlink", "target": os.readlink(path)})
        elif stat.S_ISDIR(info.st_mode):
            record.update({"type": "directory"})
        elif stat.S_ISREG(info.st_mode):
            file_hash = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    file_hash.update(chunk)
            record.update({"type": "file", "size": info.st_size, "sha256": file_hash.hexdigest()})
        else:
            raise SystemExit("canonical venv contains an unsupported filesystem object")
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
        entry_count += 1
executable = Path(os.path.realpath(sys.executable))
executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
print(json.dumps({
    "schema": 2,
    "python_version": sys.version.split()[0],
    "python_cache_tag": sys.implementation.cache_tag,
    "python_executable_sha256": executable_hash,
    "packages": packages,
    "venv_entry_count": entry_count,
    "venv_tree_sha256": digest.hexdigest(),
}, sort_keys=True, separators=(",", ":")))
PY
)"
  test "$actual" = "$expected" || die "installed distributions differ from durable activation authority"
}

release_artifact_evidence() {
  local tx_dir="$1"
  local target_sha="$2"
  local previous_sha="$3"
  local generation distribution_manifest
  verify_stage_manifest_recovery "$tx_dir" "$target_sha" "$previous_sha"
  test "$(read_activation_phase "$tx_dir" "$target_sha" "$previous_sha")" = "activated" || \
    die "release artifact evidence requires an activated release"
  generation="$(read_activation_generation "$tx_dir" "$target_sha" "$previous_sha")"
  printf -v distribution_manifest '%s/activation/g%04d/installed-distributions.json' \
    "$tx_dir" "$generation"
  verify_installed_distribution_manifest "$distribution_manifest"
  assert_release_bound_nginx_while_drained "$tx_dir"
  activation_state_tool release-evidence "$tx_dir" "$target_sha" "$previous_sha"
}

assert_release_artifact_parity() {
  local peer_host="$1"
  local tx_dir="$2"
  local target_sha="$3"
  local local_previous="$4"
  local peer_previous="$5"
  local local_evidence peer_evidence
  local_evidence="$(release_artifact_evidence "$tx_dir" "$target_sha" "$local_previous")"
  peer_evidence="$(remote_node "$peer_host" release-evidence \
    "$target_sha" "$peer_previous" "$tx_dir")"
  # Local crash history may legitimately produce different generation numbers.
  # Evidence canonicalizes authenticated artifacts by semantic basename while
  # every executable/build/package hash must still match exactly.
  test "$local_evidence" = "$peer_evidence" || \
    die "installed packages, dashboard, nginx, or toolchain differs between HA nodes"
}

prepare_activation_generation() {
  local tx_dir="$1"
  local generation="$2"
  local activation_root="$tx_dir/activation"
  local generation_root
  [[ "$generation" =~ ^[1-9][0-9]{0,3}$ ]] || die "activation generation is invalid"
  printf -v generation_root '%s/g%04d' "$activation_root" "$generation"
  install -d -o root -g root -m 0700 "$activation_root" "$generation_root"
  test ! -L "$activation_root" && test ! -L "$generation_root" || \
    die "activation generation directory is unsafe"
  test "$(stat -c '%u:%g:%a' "$activation_root")" = "0:0:700" || \
    die "activation root ownership or mode is unsafe"
  test "$(stat -c '%u:%g:%a' "$generation_root")" = "0:0:700" || \
    die "activation generation ownership or mode is unsafe"
  fsync_path_and_parents "$generation_root" "$activation_root" "$tx_dir"
  printf '%s\n' "$generation_root"
}

expected_sibling_dir() {
  local tx_dir="$1"
  validate_tx_dir "$tx_dir"
  printf '/opt/.linasbot-ha-rollback-%s\n' "$(basename "$tx_dir")"
}

prepare_sibling_dir() {
  local tx_dir="$1"
  local sibling_dir
  sibling_dir="$(expected_sibling_dir "$tx_dir")"
  assert_path_absent "$sibling_dir" "atomic rollback sibling already exists or is unsafe"
  install -d -o root -g root -m 0700 "$sibling_dir"
  test ! -L "$sibling_dir" || die "atomic rollback sibling must not be a symlink"
  test "$(stat -c '%u:%g:%a' "$sibling_dir")" = "0:0:700" || \
    die "atomic rollback sibling ownership or mode is unsafe"
  test "$(stat -c '%d' "$REPO_DIR")" = "$(stat -c '%d' "$sibling_dir")" || \
    die "atomic rollback sibling is not on the /opt repository device"
  fsync_path_and_parents "$sibling_dir" /opt
  write_private_state "$tx_dir/sibling-path" "$sibling_dir"
}

sibling_dir_for_tx() {
  local tx_dir="$1"
  local expected actual
  expected="$(expected_sibling_dir "$tx_dir")"
  test -f "$tx_dir/sibling-path" || die "atomic rollback sibling record is missing"
  actual="$(<"$tx_dir/sibling-path")"
  test "$actual" = "$expected" || die "atomic rollback sibling record is invalid"
  test -d "$actual" && test ! -L "$actual" || die "atomic rollback sibling is invalid"
  test "$(stat -c '%u:%g:%a' "$actual")" = "0:0:700" || \
    die "atomic rollback sibling ownership or mode changed"
  test "$(stat -c '%d' "$REPO_DIR")" = "$(stat -c '%d' "$actual")" || \
    die "atomic rollback sibling device changed"
  printf '%s\n' "$actual"
}

atomic_sibling_move() {
  local source="$1"
  local destination="$2"
  local destination_parent
  destination_parent="$(dirname "$destination")"
  test -d "$source" && test ! -L "$source" || die "atomic move source is missing or unsafe: $source"
  test -d "$destination_parent" && test ! -L "$destination_parent" || \
    die "atomic move destination parent is unsafe: $destination_parent"
  assert_path_absent "$destination" "atomic move destination already exists or is unsafe: $destination"
  test "$(stat -c '%d' "$source")" = "$(stat -c '%d' "$destination_parent")" || \
    die "atomic move would cross filesystem devices"
  mv -T -- "$source" "$destination"
  # Rename durability requires both directory entries, even when they share a
  # filesystem.  Recovery only interprets source/destination combinations
  # after these barriers complete.
  fsync_path_and_parents "$(dirname "$source")" "$destination_parent"
}

live_baseline_artifact_evidence() {
  local tx_dir="${1:-}"
  local nginx_source=/etc/nginx/sites-available/linasaibot
  if [ -n "$tx_dir" ] && [ -f "$tx_dir/maintenance-nginx.conf" ] && \
     [ ! -L "$tx_dir/maintenance-nginx.conf" ]; then
    test "$(stat -c '%u:%g:%a' "$tx_dir/maintenance-nginx.conf")" = "0:0:600" || \
      die "baseline nginx rollback authority is unsafe"
    nginx_source="$tx_dir/maintenance-nginx.conf"
  fi
  run_system_python_control - \
    "$REPO_DIR/venv" "$REPO_DIR/dashboard/build" \
    "$nginx_source" \
    /etc/nginx/sites-enabled/linasaibot \
    /etc/nginx/conf.d/linasbot-privacy-log.conf \
    /etc/systemd/system/linasbot.service \
    /etc/systemd/system/linasbot-worker@.service \
    /etc/systemd/system/linasbot.service.d \
    /etc/systemd/system/linasbot-worker@.service.d <<'PY'
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

paths = [Path(value) for value in sys.argv[1:]]
digest = hashlib.sha256()
records = 0


def add_record(record: dict[str, object]) -> None:
    global records
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big") + encoded)
    records += 1


def visit(path: Path, label: str) -> None:
    info = path.lstat()
    record: dict[str, object] = {
        "path": label,
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
    }
    if label == "artifact-2":
        if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) not in {0o600, 0o644}:
            raise SystemExit("baseline nginx authority ownership or mode is unsafe")
        record.update({"mode": 0o644, "uid": 0, "gid": 0})
    if stat.S_ISLNK(info.st_mode):
        record.update({"type": "symlink", "target": os.readlink(path)})
        add_record(record)
        return
    if stat.S_ISDIR(info.st_mode):
        record["type"] = "directory"
        add_record(record)
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            if child.name == "90-meta-ha-maintenance.conf":
                continue
            visit(child, f"{label}/{child.name}")
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SystemExit("baseline artifact contains an unsupported filesystem object")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (info.st_dev, info.st_ino, info.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("baseline artifact changed while opening")
        file_digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            file_digest.update(chunk)
    finally:
        os.close(descriptor)
    record.update({"type": "file", "size": info.st_size, "sha256": file_digest.hexdigest()})
    add_record(record)


for index, path in enumerate(paths):
    if not path.exists() and not path.is_symlink():
        raise SystemExit(f"baseline artifact is missing: {path}")
    visit(path, f"artifact-{index}")

venv_python = paths[0] / "bin/python"
resolved_python = Path(os.path.realpath(venv_python))
python_info = resolved_python.lstat()
if not stat.S_ISREG(python_info.st_mode):
    raise SystemExit("baseline Python interpreter is unsafe")
python_digest = hashlib.sha256()
with resolved_python.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1 << 20), b""):
        python_digest.update(chunk)
print(json.dumps({
    "schema": 1,
    "artifact_record_count": records,
    "artifact_projection_sha256": digest.hexdigest(),
    "python_executable_sha256": python_digest.hexdigest(),
}, sort_keys=True, separators=(",", ":")))
PY
}

capture_baseline_artifact_evidence() {
  local destination="$1"
  local evidence
  evidence="$(live_baseline_artifact_evidence)"
  write_private_state "$destination" "$evidence"
}

assert_baseline_artifact_evidence_restored() {
  local tx_dir="$1"
  local expected actual
  test -f "$tx_dir/baseline-artifacts.json" && \
    test ! -L "$tx_dir/baseline-artifacts.json" || \
    die "baseline artifact rollback authority is missing"
  test "$(stat -c '%u:%g:%a' "$tx_dir/baseline-artifacts.json")" = "0:0:600" || \
    die "baseline artifact rollback authority is unsafe"
  expected="$(<"$tx_dir/baseline-artifacts.json")"
  actual="$(live_baseline_artifact_evidence "$tx_dir")"
  test "$actual" = "$expected" || \
    die "restored baseline venv, dashboard, nginx, or systemd artifacts differ"
}

backup_live_node() {
  local target_sha="$1"
  local previous_sha="$2"
  local tx_dir="$3"
  local artifact_id="$4"
  local artifact_api_sha="$5"
  local manifest_sha="$6"
  local run_id="$7"
  local run_attempt="$8"
  local runtime_list="$tx_dir/runtime-data.list"
  local sibling_dir bundle_dir release_summary helper_root deploy_version
  local -a release_fields
  [[ "$artifact_id" =~ ^[1-9][0-9]*$ ]] || die "release artifact ID is invalid"
  validate_digest "$artifact_api_sha"
  validate_digest "$manifest_sha"
  [[ "$run_id" =~ ^[1-9][0-9]*$ ]] || die "release Quality Gates run ID is invalid"
  [[ "$run_attempt" =~ ^[1-9][0-9]*$ ]] || die "release Quality Gates attempt is invalid"
  bundle_dir="$(release_bundle_path "$artifact_id" "$artifact_api_sha")"
  release_summary="$(assert_release_bundle \
    "$target_sha" "$artifact_id" "$artifact_api_sha" "$manifest_sha" \
    "$run_id" "$run_attempt")"
  test "$(current_head)" = "$previous_sha" || die "node changed after preflight"
  git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || die "live tracked tree changed after preflight"
  git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || die "live index changed after preflight"
  ensure_transaction_dir_durable "$tx_dir"
  if [ -e "$tx_dir" ] || [ -L "$tx_dir" ]; then
    test -d "$tx_dir" && test ! -L "$tx_dir" || die "transaction path is not a safe directory"
    find "$tx_dir" -mindepth 1 -maxdepth 1 \
      ! -name maintenance-nginx.conf \
      ! -name maintenance-nginx.candidate \
      ! -name maintenance-boot-guard.conf \
      ! -name predrain-service-state \
      ! -name drain-guard.complete \
      ! -name drain-runtime-stopped \
      ! -name sibling-path \
      ! -name 'incomplete-service-state-*' \
      ! -name 'incomplete-stage-*' \
      -print -quit | grep -q . && die "transaction directory already contains unexpected state"
  fi
  if [ -e "$tx_dir/predrain-service-state" ] || [ -L "$tx_dir/predrain-service-state" ]; then
    validate_service_state_file "$tx_dir/predrain-service-state"
  else
    # Read-only rollback inventory: local node01 may stage while it continues
    # serving the old release. Drain authority is published separately later.
    assert_service_state_capture_is_pre_mutation
    capture_service_state "$tx_dir/predrain-service-state"
  fi
  mkdir -p "$tx_dir/stage/repo"
  chmod 0700 "$tx_dir" "$tx_dir/stage" "$tx_dir/stage/repo"
  if [ -f "$tx_dir/sibling-path" ]; then
    sibling_dir="$(sibling_dir_for_tx "$tx_dir")"
    if find "$sibling_dir" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
      die "incomplete stage crossed the live activation boundary"
    fi
  else
    prepare_sibling_dir "$tx_dir"
  fi
  write_private_state "$tx_dir/previous.sha" "$previous_sha"
  write_private_state "$tx_dir/target.sha" "$target_sha"
  write_private_state "$tx_dir/release-bundle.json" "$release_summary"
  copy_private_file_durable "$REPO_DIR/.env" "$tx_dir/root.env"
  archive_path "$tx_dir/venv.tar" opt/linasbot/venv
  archive_path "$tx_dir/data-pre-drain.tar" opt/linasbot/data
  archive_path "$tx_dir/dashboard-build.tar" opt/linasbot/dashboard/build
  archive_path "$tx_dir/nginx.tar" \
    etc/nginx/sites-available/linasaibot \
    etc/nginx/sites-enabled/linasaibot \
    etc/nginx/conf.d/linasbot-privacy-log.conf
  archive_path "$tx_dir/systemd.tar" \
    etc/systemd/system/linasbot.service etc/systemd/system/linasbot-worker@.service
  validate_service_state_file "$tx_dir/predrain-service-state"
  capture_baseline_artifact_evidence "$tx_dir/baseline-artifacts.json"

  git -C "$REPO_DIR" ls-files --others --ignored --exclude-standard -z -- data >"$runtime_list"
  chmod 0600 "$runtime_list"
  tar --null --verbatim-files-from --numeric-owner -C "$REPO_DIR" \
    -cpf "$tx_dir/runtime-data.tar" -T "$runtime_list"
  chmod 0600 "$tx_dir/runtime-data.tar"
  fsync_path_and_parents "$runtime_list" "$tx_dir/runtime-data.tar"
  write_private_state "$tx_dir/runtime-data.tar.sha256" \
    "$(sha256sum "$tx_dir/runtime-data.tar" | awk '{print $1}')"
  verify_archive "$tx_dir/runtime-data.tar"

  git -C "$REPO_DIR" archive "$target_sha" | tar -xpf - -C "$tx_dir/stage/repo"
  test -f "$tx_dir/stage/repo/$REQUIREMENTS_LOCK_REPO_PATH" || \
    die "target fully hashed Python production lock is missing"
  test -f "$tx_dir/stage/repo/requirements-dev.lock" || \
    die "target fully hashed Python development lock is missing"
  test -f "$tx_dir/stage/repo/dashboard/package-lock.json" || \
    die "target dashboard package lock is missing"

  mapfile -t release_fields < <(run_system_python_control - "$release_summary" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
for key in (
    "requirements_lock_sha256",
    "requirements_dev_lock_sha256",
    "dashboard_package_lock_sha256",
):
    print(payload["source_locks"][key])
for key in ("wheelhouse", "dashboard", "control_plane"):
    print(payload["payloads"][key]["archive_sha256"])
    print(payload["payloads"][key]["tree_sha256"])
PY
  )
  test "${#release_fields[@]}" -eq 9 || die "release artifact summary is incomplete"
  test "$(sha256sum "$tx_dir/stage/repo/requirements.lock" | awk '{print $1}')" = \
    "${release_fields[0]}" || die "target production lock differs from Quality Gates"
  test "$(sha256sum "$tx_dir/stage/repo/requirements-dev.lock" | awk '{print $1}')" = \
    "${release_fields[1]}" || die "target development lock differs from Quality Gates"
  test "$(sha256sum "$tx_dir/stage/repo/dashboard/package-lock.json" | awk '{print $1}')" = \
    "${release_fields[2]}" || die "target dashboard lock differs from Quality Gates"

  helper_root="$(materialize_release_artifact_contract "$target_sha")"
  if ! run_system_python_control - \
      "$helper_root" "$bundle_dir" "$tx_dir/stage" \
      "${release_fields[3]}" "${release_fields[4]}" \
      "${release_fields[5]}" "${release_fields[6]}" \
      "${release_fields[7]}" "${release_fields[8]}" <<'PY'
import sys
from pathlib import Path

(
    helper,
    bundle_raw,
    stage_raw,
    wheels_archive,
    wheels_tree,
    dashboard_archive,
    dashboard_tree,
    control_archive,
    control_tree,
) = sys.argv[1:]
sys.path.insert(0, helper)
from scripts.ha.release_artifact_contract import CONTROL_PLANE_MEMBERS, extract_archive

bundle = Path(bundle_raw)
stage = Path(stage_raw)
extract_archive(bundle / "wheelhouse.tar", stage / "wheels", wheels_archive, wheels_tree)
extract_archive(
    bundle / "dashboard-build.tar",
    stage / "repo/dashboard/build",
    dashboard_archive,
    dashboard_tree,
)
extract_archive(
    bundle / "control-plane.tar",
    stage / "control-plane",
    control_archive,
    control_tree,
    expected_paths=CONTROL_PLANE_MEMBERS,
)
PY
  then
    cleanup_release_artifact_contract "$helper_root" || true
    die "exact Quality Gates release payload extraction failed"
  fi
  cleanup_release_artifact_contract "$helper_root"
  test -f "$tx_dir/stage/repo/dashboard/build/index.html" || \
    die "Quality Gates dashboard build is incomplete"
  run_system_python_control -m venv --without-pip \
    "$tx_dir/stage/verify-venv"
  run_portable_pip "$tx_dir/pip-state" \
    --python "$tx_dir/stage/verify-venv/bin/python" install \
    --no-index \
    --no-compile \
    --only-binary=:all: \
    --require-hashes \
    --find-links "$tx_dir/stage/wheels" \
    --requirement "$tx_dir/stage/repo/$REQUIREMENTS_LOCK_REPO_PATH"
  run_portable_pip "$tx_dir/pip-state" \
    --python "$tx_dir/stage/verify-venv/bin/python" check

  # Release identity is target-derived and was embedded by the exact QG build.
  deploy_version="$(git -C "$REPO_DIR" show -s --format=%ct "$target_sha")"
  [[ "$deploy_version" =~ ^[1-9][0-9]*$ ]] || die "target commit epoch is invalid"
  write_private_state "$tx_dir/deploy-version" "$deploy_version"
  publish_stage_manifest "$tx_dir" "$target_sha" "$previous_sha"
  log "node stage and recoverable backups complete"
}

normalize_prequiesced_activation_prefix() {
  local tx_dir="$1"
  local target_sha="$2"
  local previous_sha="$3"
  local activation_root="$tx_dir/activation"
  local archive counter=1
  test -z "$(read_activation_phase "$tx_dir" "$target_sha" "$previous_sha")" || \
    die "pre-quiesced normalization requires no durable activation pointer"
  # No live sibling move is authorized before quiesced publication. Requiring
  # the original empty-sibling stage proof distinguishes safe partial backup
  # bytes/history-event ACK loss from an unjournaled activation mutation.
  verify_stage_manifest "$tx_dir" "$target_sha" "$previous_sha"
  test "$(current_head)" = "$previous_sha" || \
    die "pre-quiesced activation prefix changed the live release"
  git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || \
    die "pre-quiesced activation prefix has tracked runtime changes"
  git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || \
    die "pre-quiesced activation prefix changed the live index"
  if [ -e "$activation_root" ] || [ -L "$activation_root" ]; then
    test -d "$activation_root" && test ! -L "$activation_root" || \
      die "partial pre-quiesced activation root is unsafe"
    test "$(stat -c '%u:%g:%a' "$activation_root")" = "0:0:700" || \
      die "partial pre-quiesced activation root ownership or mode is unsafe"
    while :; do
      printf -v archive '%s/incomplete-prequiesced-activation-%03d' "$tx_dir" "$counter"
      if [ ! -e "$archive" ] && [ ! -L "$archive" ]; then
        break
      fi
      counter=$((counter + 1))
      test "$counter" -le 999 || die "too many partial pre-quiesced activation archives"
    done
    atomic_sibling_move "$activation_root" "$archive"
    fsync_tree "$archive"
  fi
}

prepare_retry_stage() {
  local target_sha="$1"
  local previous_sha="$2"
  local tx_dir="$3"
  local artifact_id="$4"
  local artifact_api_sha="$5"
  local manifest_sha="$6"
  local run_id="$7"
  local run_attempt="$8"
  local archive entry name expected_release_summary
  validate_tx_dir "$tx_dir"
  expected_release_summary="$(assert_release_bundle \
    "$target_sha" "$artifact_id" "$artifact_api_sha" "$manifest_sha" \
    "$run_id" "$run_attempt")"
  if [ -e "$tx_dir/stage.complete" ] || [ -L "$tx_dir/stage.complete" ]; then
    verify_stage_manifest_recovery "$tx_dir" "$target_sha" "$previous_sha"
    test -f "$tx_dir/release-bundle.json" && test ! -L "$tx_dir/release-bundle.json" || \
      die "retry stage release bundle authority is missing"
    test "$(<"$tx_dir/release-bundle.json")" = "$expected_release_summary" || \
      die "retry stage release bundle differs from the durable transaction"
    case "$(read_activation_phase "$tx_dir" "$target_sha" "$previous_sha")" in
      rolled-back)
        verify_activation_sibling_authority "$tx_dir" "$target_sha" "$previous_sha"
        ;;
      "")
        normalize_prequiesced_activation_prefix "$tx_dir" "$target_sha" "$previous_sha"
        ;;
      *) die "retry stage requires a rolled-back or authenticated pre-quiesced generation" ;;
    esac
    return 0
  fi
  archive="$tx_dir/incomplete-stage-$(date -u +%Y%m%d%H%M%S)-$$"
  mkdir "$archive"
  chmod 0700 "$archive"
  while IFS= read -r -d '' entry; do
    name="$(basename "$entry")"
    case "$name" in
      maintenance-nginx.conf | maintenance-nginx.candidate | maintenance-boot-guard.conf | \
        predrain-service-state | drain-guard.complete | drain-runtime-stopped | sibling-path | \
        incomplete-service-state-* | incomplete-stage-*)
        continue
        ;;
    esac
    mv -T -- "$entry" "$archive/$name"
  done < <(find "$tx_dir" -mindepth 1 -maxdepth 1 -print0)
  printf 'preserved incomplete stage before exact retry\n' >"$archive/reason"
  chmod 0600 "$archive/reason"
  backup_live_node "$target_sha" "$previous_sha" "$tx_dir" \
    "$artifact_id" "$artifact_api_sha" "$manifest_sha" "$run_id" "$run_attempt"
}

stop_runtime() {
  local queue
  systemctl stop "$VERIFY_API_UNIT" 2>/dev/null || true
  for queue in "${WORKER_QUEUES[@]}"; do
    systemctl stop "linasbot-worker@${queue}.service" 2>/dev/null || true
  done
  systemctl stop linasbot.service
  for _ in $(seq 1 30); do
    if ! ss -H -ltnp 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:8003([[:space:]]|$)'; then
      systemctl is-active --quiet linasbot.service && die "canonical API remained active after stop"
      systemctl is-active --quiet "$VERIFY_API_UNIT" && die "verification API remained active after stop"
      for queue in "${WORKER_QUEUES[@]}"; do
        systemctl is-active --quiet "linasbot-worker@${queue}.service" && \
          die "queue worker remained active after stop: $queue"
      done
      return 0
    fi
    sleep 1
  done
  die "canonical API port 8003 did not quiesce"
}

stop_queue_workers() {
  local queue
  for queue in "${WORKER_QUEUES[@]}"; do
    systemctl stop "linasbot-worker@${queue}.service" 2>/dev/null || true
    systemctl is-active --quiet "linasbot-worker@${queue}.service" && \
      die "queue worker remained active during HA maintenance: $queue"
  done
}

write_boot_guard_candidate() {
  local path="$1"
  local payload
  payload=$'[Unit]\n# Exact HA transaction boot guard.  A reboot must not start a drained runtime.\nConditionPathExists=!/var/lib/linasbot/meta-ha/deploy-node.active\nConditionPathExists=!/var/lib/linasbot/meta-ha/maintenance'
  write_private_state "$path" "$payload"
}

publish_boot_guard_atomic() {
  local candidate="$1"
  local destination="$2"
  run_system_python_control - "$candidate" "$destination" <<'PY'
import os
import stat
import sys
import tempfile
from pathlib import Path

candidate = Path(sys.argv[1])
destination = Path(sys.argv[2])
candidate_info = candidate.lstat()
if (
    not stat.S_ISREG(candidate_info.st_mode)
    or stat.S_ISLNK(candidate_info.st_mode)
    or candidate_info.st_uid != 0
    or candidate_info.st_gid != 0
    or stat.S_IMODE(candidate_info.st_mode) != 0o600
    or candidate_info.st_nlink != 1
):
    raise SystemExit("maintenance boot guard candidate is unsafe")
candidate_fd = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    expected = b""
    while True:
        chunk = os.read(candidate_fd, 65536)
        if not chunk:
            break
        expected += chunk
finally:
    os.close(candidate_fd)
parent_info = destination.parent.lstat()
if (
    not stat.S_ISDIR(parent_info.st_mode)
    or stat.S_ISLNK(parent_info.st_mode)
    or parent_info.st_uid != 0
    or parent_info.st_gid != 0
    or stat.S_IMODE(parent_info.st_mode) != 0o755
):
    raise SystemExit("maintenance boot guard parent is unsafe")
if destination.exists() or destination.is_symlink():
    current_info = destination.lstat()
    if (
        not stat.S_ISREG(current_info.st_mode)
        or stat.S_ISLNK(current_info.st_mode)
        or current_info.st_uid != 0
        or current_info.st_gid != 0
        or stat.S_IMODE(current_info.st_mode) != 0o644
        or current_info.st_nlink != 1
    ):
        raise SystemExit("maintenance boot guard destination is unsafe")
    current_fd = os.open(destination, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        current = b""
        while True:
            chunk = os.read(current_fd, 65536)
            if not chunk:
                break
            current += chunk
    finally:
        os.close(current_fd)
    if current == expected:
        descriptor = os.open(destination, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        raise SystemExit(0)
    # Compatibility recovery for a power loss in the old non-atomic install:
    # only an exact proper prefix can be replaced. Unknown bytes fail closed.
    if not expected.startswith(current) or len(current) >= len(expected):
        raise SystemExit("unknown maintenance boot guard already exists")
descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o644)
    os.fchown(descriptor, 0, 0)
    view = memoryview(expected)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("maintenance boot guard atomic write made no progress")
        view = view[written:]
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1
    os.replace(temporary, destination)
    directory = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY
}

install_maintenance_boot_guard() {
  local tx_dir="$1"
  local candidate="$tx_dir/maintenance-boot-guard.conf"
  local unit_dir destination api_guard worker_guard
  api_guard=/etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf
  worker_guard=/etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf
  write_boot_guard_candidate "$candidate"
  for unit_dir in \
    /etc/systemd/system/linasbot.service.d \
    /etc/systemd/system/linasbot-worker@.service.d; do
    install -d -o root -g root -m 0755 "$unit_dir"
    destination="$unit_dir/90-meta-ha-maintenance.conf"
    publish_boot_guard_atomic "$candidate" "$destination"
  done
  fsync_path_and_parents \
    "$api_guard" \
    "$worker_guard" \
    /etc/systemd/system/linasbot.service.d \
    /etc/systemd/system/linasbot-worker@.service.d \
    /etc/systemd/system
  systemctl daemon-reload
  test "$(systemctl show -p NeedDaemonReload --value linasbot.service)" = "no" || \
    die "systemd has not durably loaded the API maintenance guard"
  test "$(systemctl show -p NeedDaemonReload --value linasbot-worker@.service)" = "no" || \
    die "systemd has not durably loaded the worker maintenance guard"
  systemctl cat linasbot.service | grep -Fq "$api_guard" || \
    die "systemd API maintenance guard readback failed"
  systemctl cat linasbot-worker@.service | grep -Fq "$worker_guard" || \
    die "systemd worker maintenance guard readback failed"
}

assert_maintenance_boot_guard_loaded() {
  maintenance_boot_guard_is_loaded "$1" || \
    die "maintenance boot guard is missing, changed, or not loaded"
}

maintenance_boot_guard_is_loaded() {
  local tx_dir="$1"
  local candidate="$tx_dir/maintenance-boot-guard.conf"
  local api_guard=/etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf
  local worker_guard=/etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf
  test -f "$candidate" && test ! -L "$candidate" || return 1
  for guard in "$api_guard" "$worker_guard"; do
    test -f "$guard" && test ! -L "$guard" || return 1
    test "$(stat -c '%u:%g:%a' "$guard")" = "0:0:644" || \
      return 1
    cmp -s "$candidate" "$guard" || return 1
  done
  test "$(systemctl show -p NeedDaemonReload --value linasbot.service)" = "no" || \
    return 1
  test "$(systemctl show -p NeedDaemonReload --value linasbot-worker@.service)" = "no" || \
    return 1
  systemctl cat linasbot.service | grep -Fq "$api_guard" || \
    return 1
  systemctl cat linasbot-worker@.service | grep -Fq "$worker_guard" || \
    return 1
}

maintenance_boot_guard_files_match() {
  local tx_dir="$1"
  local candidate="$tx_dir/maintenance-boot-guard.conf"
  local guard
  test -f "$candidate" && test ! -L "$candidate" || return 1
  test "$(stat -c '%u:%g:%a' "$candidate")" = "0:0:600" || return 1
  for guard in \
    /etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf \
    /etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf; do
    test -f "$guard" && test ! -L "$guard" || return 1
    test "$(stat -c '%u:%g:%a' "$guard")" = "0:0:644" || return 1
    cmp -s "$candidate" "$guard" || return 1
  done
}

remove_maintenance_boot_guard() {
  local tx_dir="$1"
  local candidate="$tx_dir/maintenance-boot-guard.conf"
  local destination
  test -f "$candidate" && test ! -L "$candidate" || die "maintenance boot guard proof is missing"
  for destination in \
    /etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf \
    /etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf; do
    if [ -e "$destination" ] || [ -L "$destination" ]; then
      test -f "$destination" && test ! -L "$destination" || \
        die "maintenance boot guard has an unsafe type"
      cmp -s "$candidate" "$destination" || die "maintenance boot guard changed unexpectedly"
      unlink "$destination"
    fi
  done
  fsync_path_and_parents \
    /etc/systemd/system/linasbot.service.d \
    /etc/systemd/system/linasbot-worker@.service.d \
    /etc/systemd/system
  systemctl daemon-reload
  test "$(systemctl show -p NeedDaemonReload --value linasbot.service)" = "no" || \
    die "systemd API guard removal was not loaded"
  test "$(systemctl show -p NeedDaemonReload --value linasbot-worker@.service)" = "no" || \
    die "systemd worker guard removal was not loaded"
}

assert_direct_port_unavailable() {
  ! systemctl is-active --quiet linasbot.service || die "drained legacy API is still active"
  ! systemctl is-active --quiet "$VERIFY_API_UNIT" || die "drained verification API is still active"
  if ss -H -ltnp 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:8003([[:space:]]|$)'; then
    die "drained legacy API still listens on direct LB port 8003"
  fi
}

install_systemd_units() {
  local tx_dir="$1"
  local control_root="$tx_dir/stage/control-plane"
  run_system_python_control - "$control_root" <<'PY'
import os
import stat
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
sources = {
    root / "deploy/systemd/linasbot.service": Path("/etc/systemd/system/linasbot.service"),
    root / "deploy/systemd/linasbot-worker@.service": Path(
        "/etc/systemd/system/linasbot-worker@.service"
    ),
}
for source, destination in sources.items():
    before = source.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) not in {0o644, 0o755}
        or before.st_nlink != 1
        or before.st_size > (1 << 20)
    ):
        raise SystemExit("staged canonical systemd template is unsafe")
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise SystemExit("staged canonical systemd template changed while opening")
        payload = os.read(descriptor, (1 << 20) + 1)
        if len(payload) != before.st_size or os.read(descriptor, 1):
            raise SystemExit("staged canonical systemd template changed while reading")
    finally:
        os.close(descriptor)
    if payload.count(b"__APP_DIR__") < 1:
        raise SystemExit("canonical systemd template lacks its exact app-root placeholder")
    payload = payload.replace(b"__APP_DIR__", b"/opt/linasbot")
    if b"__APP_DIR__" in payload:
        raise SystemExit("canonical systemd template placeholder was not resolved")
    parent = destination.parent
    descriptor, temporary_raw = tempfile.mkstemp(prefix=f".{destination.name}.", dir=parent)
    temporary = Path(temporary_raw)
    try:
        os.fchmod(descriptor, 0o644)
        os.fchown(descriptor, 0, 0)
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, destination)
        parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
PY
  fsync_path_and_parents \
    /etc/systemd/system/linasbot.service \
    /etc/systemd/system/linasbot-worker@.service \
    /etc/systemd/system
  systemctl daemon-reload
  test "$(systemctl show -p NeedDaemonReload --value linasbot.service)" = no || \
    die "canonical API unit was not durably loaded"
  test "$(systemctl show -p NeedDaemonReload --value linasbot-worker@.service)" = no || \
    die "canonical worker unit was not durably loaded"
}

install_nginx_config() {
  install -o root -g root -m 0644 \
    "$REPO_DIR/deploy/nginx-privacy-log.conf" \
    /etc/nginx/conf.d/linasbot-privacy-log.conf
  install -o root -g root -m 0644 \
    "$REPO_DIR/deploy/nginx-linasaibot.conf" \
    /etc/nginx/sites-available/linasaibot
  test -L /etc/nginx/sites-enabled/linasaibot
  test "$(readlink -f /etc/nginx/sites-enabled/linasaibot)" = \
    "$(readlink -f /etc/nginx/sites-available/linasaibot)"
  nginx -t
  systemctl reload nginx
}

durable_queues_enabled() {
  grep -Eq '^[[:space:]]*(REDIS_URL|LINAS_REDIS_URL)=' "$REPO_DIR/.env" \
    && grep -Eqi '^[[:space:]]*(LINAS_REQUIRE_REDIS|LINAS_ENABLE_DURABLE_QUEUES)=(1|true|yes|on)' \
      "$REPO_DIR/.env"
}

start_target_runtime() {
  local tx_dir="$1"
  local queue target_sha node_id
  target_sha="$(<"$tx_dir/target.sha")"
  validate_sha "$target_sha"
  node_id="$(configured_node_id)"
  assert_deploy_node_sentinel "$tx_dir"
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  assert_legacy_retirement_contract "$(configured_node_id)"
  # Keep the canonical API/workers blocked by the durable boot guard until
  # both-node target parity is proven.  A /run transient verification service
  # disappears on reboot and has no queue workers, so a crash cannot admit an
  # unverified release or resume background side effects.
  install_maintenance_boot_guard "$tx_dir"
  systemctl disable --now linasbot.service 2>/dev/null || true
  for queue in "${WORKER_QUEUES[@]}"; do
    systemctl disable --now "linasbot-worker@${queue}.service" 2>/dev/null || true
  done
  systemd-run \
    --unit="$VERIFY_API_UNIT" \
    --collect \
    --service-type=simple \
    --property=User=root \
    --property="WorkingDirectory=$REPO_DIR" \
    --property="EnvironmentFile=-$REPO_DIR/.env" \
    --property=Environment=PYTHONUNBUFFERED=1 \
    --property=Environment=PYTHONDONTWRITEBYTECODE=1 \
    --property=Environment=LINAS_HA_VERIFY_ONLY=true \
    --property="Environment=LINAS_HA_VERIFY_RELEASE_SHA=$target_sha" \
    --property=Environment=DISABLE_API_DOCS=1 \
    --property="Environment=PATH=$REPO_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    "$REPO_DIR/venv/bin/python" -B -I "$REPO_DIR/$RELEASE_VERIFY_REPO_PATH"
  for _ in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:8003/api/health 2>/dev/null | \
      grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
      break
    fi
    sleep 1
  done
  systemctl is-active --quiet "$VERIFY_API_UNIT" || die "transient target verification API failed to start"
  assert_unit_contract "$VERIFY_API_UNIT"
  assert_transient_api_process_env_contract "$target_sha" "$target_sha" "$node_id"
  assert_health_while_drained
  # A separate non-routable target process executes the real Redis/Firestore/
  # Meta/etc readiness evaluator. Public /api/ready remains marker-gated 503.
  run_target_alembic_migrate "$target_sha"
  run_target_readiness_probe "$target_sha"
  for queue in "${WORKER_QUEUES[@]}"; do
    ! systemctl is-active --quiet "linasbot-worker@${queue}.service" || \
      die "queue worker started before final admission: $queue"
  done
  install_maintenance_boot_guard "$tx_dir"
  assert_maintenance_readiness
}

activate_impl() {
  local target_sha="$1"
  local previous_sha="$2"
  local tx_dir="$3"
  local deploy_version sibling_dir existing_phase generation generation_root runtime_list
  test "$(current_head)" = "$previous_sha" || die "node changed after preflight"
  existing_phase="$(read_activation_phase "$tx_dir" "$target_sha" "$previous_sha")"
  if [ -z "$existing_phase" ]; then
    verify_stage_manifest "$tx_dir" "$target_sha" "$previous_sha"
    generation=1
  elif [ "$existing_phase" = "rolled-back" ]; then
    verify_stage_manifest_recovery "$tx_dir" "$target_sha" "$previous_sha"
    verify_activation_sibling_authority "$tx_dir" "$target_sha" "$previous_sha"
    generation=$(( $(read_activation_generation "$tx_dir" "$target_sha" "$previous_sha") + 1 ))
  else
    die "node activation already crossed a durable boundary; use exact recovery"
  fi
  test ! -L "$tx_dir/activation.state" || die "activation state is an unsafe symlink"
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  assert_secure_maintenance_marker "$VOLATILE_MAINTENANCE_FILE"
  node_assert_runtime_drained "$tx_dir"
  sibling_dir="$(sibling_dir_for_tx "$tx_dir")"
  generation_root="$(prepare_activation_generation "$tx_dir" "$generation")"
  runtime_list="$generation_root/runtime-quiesced.list"

  stop_runtime
  # Runtime writes are allowed while node01 stages.  Once all processes stop,
  # refuse any tracked/index mutation instead of silently discarding it, and
  # capture ignored runtime data from this exact quiesced point for forward
  # activation.  The full data archive remains the rollback authority.
  git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || \
    die "tracked runtime data changed after staging; preserving it fail-closed"
  git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || \
    die "live index changed after staging; preserving it fail-closed"
  archive_path "$generation_root/data-quiesced.tar" opt/linasbot/data
  copy_private_file_durable "$REPO_DIR/.env" "$generation_root/root-quiesced.env"
  git -C "$REPO_DIR" ls-files --others --ignored --exclude-standard -z -- data >"$runtime_list"
  chmod 0600 "$runtime_list"
  tar --null --verbatim-files-from --numeric-owner -C "$REPO_DIR" \
    -cpf "$generation_root/runtime-quiesced.tar" -T "$runtime_list"
  chmod 0600 "$generation_root/runtime-quiesced.tar"
  fsync_path_and_parents "$runtime_list" "$generation_root/runtime-quiesced.tar"
  write_private_state "$generation_root/runtime-quiesced.tar.sha256" \
    "$(sha256sum "$generation_root/runtime-quiesced.tar" | awk '{print $1}')"
  verify_archive "$generation_root/runtime-quiesced.tar"
  write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" quiesced "$generation"
  atomic_sibling_move "$REPO_DIR/venv" "$sibling_dir/live-venv"
  write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" venv-moved "$generation"
  atomic_sibling_move "$REPO_DIR/dashboard/build" "$sibling_dir/live-dashboard-build"
  write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" dashboard-moved "$generation"

  git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || \
    die "tracked runtime data changed immediately before target reset; preserving it fail-closed"
  git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || \
    die "live index changed immediately before target reset; preserving it fail-closed"
  # Publish reset authority before Git can touch HEAD, the index, or any
  # tracked worktree byte. Recovery may then deterministically restore the
  # exact baseline even if reset/restore is killed with HEAD still old and a
  # partially rewritten tree.
  write_activation_phase \
    "$tx_dir" "$target_sha" "$previous_sha" target-reset-started "$generation"
  recover_transaction_git_locks "$tx_dir" "$generation" target-reset
  git -C "$REPO_DIR" reset --hard "$target_sha"
  git -C "$REPO_DIR" diff --quiet "$target_sha" --
  git -C "$REPO_DIR" diff --cached --quiet "$target_sha" --
  verify_archive "$generation_root/runtime-quiesced.tar"
  tar --numeric-owner -C "$REPO_DIR" -xpf "$generation_root/runtime-quiesced.tar"
  # A formerly ignored runtime-data path may become tracked in the new release.
  # Exact release content always wins for tracked paths.
  git -C "$REPO_DIR" restore --source "$target_sha" --staged --worktree -- .
  run_system_python_control -m venv --without-pip "$REPO_DIR/venv"
  run_portable_pip "$generation_root/pip-state" \
    --python "$REPO_DIR/venv/bin/python" install \
    --no-index \
    --no-compile \
    --only-binary=:all: \
    --require-hashes \
    --find-links "$tx_dir/stage/wheels" \
    --requirement "$REPO_DIR/$REQUIREMENTS_LOCK_REPO_PATH"
  run_portable_pip "$generation_root/pip-state" \
    --python "$REPO_DIR/venv/bin/python" check
  write_installed_distribution_manifest "$generation_root/installed-distributions.json"
  cp -a "$tx_dir/stage/repo/dashboard/build" "$REPO_DIR/dashboard/build"
  deploy_version="$(<"$tx_dir/deploy-version")"
  write_private_state "$REPO_DIR/data/.deploy_version" "$deploy_version"

  # Environment changes are a separate two-node transaction. A release deploy
  # never derives node-local CM/model values or mutates canonical .env.
  cluster_runtime_env_evidence \
    "$target_sha" "$target_sha" "$(configured_node_id)" >/dev/null

  install_systemd_units "$tx_dir"
  install_nginx_config
  copy_private_file_durable \
    /etc/nginx/sites-available/linasaibot "$generation_root/target-nginx.conf"
  fsync_tree "$REPO_DIR" "$sibling_dir"
  fsync_path_and_parents \
    /etc/systemd/system/linasbot.service \
    /etc/systemd/system/linasbot-worker@.service \
    /etc/nginx/sites-available/linasaibot \
    /etc/nginx/conf.d/linasbot-privacy-log.conf
  write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" target-installed "$generation"
  audit_untracked_runtime "$tx_dir" "pre-target-start" "$target_sha" || \
    die "untracked runtime source appeared before target service start"
  start_target_runtime "$tx_dir"
  test "$(current_head)" = "$target_sha" || die "activated target SHA mismatch"
  git -C "$REPO_DIR" diff --quiet "$target_sha" -- || die "activated tracked tree is dirty"
  git -C "$REPO_DIR" diff --cached --quiet "$target_sha" -- || die "activated index is dirty"
  write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" activated "$generation"
}

start_saved_runtime_disabled() {
  local state_file="$1"
  local tx_dir="$2"
  local unit enabled active queue api_active="" expected_sha helper_source_sha node_id
  validate_tx_dir "$tx_dir"
  expected_sha="$(current_head)"
  helper_source_sha="$(target_sha_from_tx "$tx_dir")"
  validate_sha "$expected_sha"
  validate_sha "$helper_source_sha"
  node_id="$(configured_node_id)"
  validate_service_state_file "$state_file"
  disable_runtime_autostart
  while IFS='|' read -r unit enabled active; do
    if [ "$unit" = "linasbot.service" ]; then
      api_active="$active"
      break
    fi
  done <"$state_file"
  test "$api_active" = "active" || die "saved canonical API was not active before drain"
  systemctl start linasbot.service
  for _ in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:8003/api/health 2>/dev/null | \
      grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
      break
    fi
    sleep 1
  done
  assert_unit_contract linasbot
  assert_health_while_drained
  for queue in "${WORKER_QUEUES[@]}"; do
    unit="linasbot-worker@${queue}.service"
    active="$(awk -F'|' -v wanted="$unit" '$1 == wanted {print $3}' "$state_file")"
    test -n "$active" || die "saved worker service state is incomplete: $queue"
    if [ "$active" = "active" ]; then
      systemctl start "$unit"
      assert_unit_contract "$unit"
    else
      systemctl stop "$unit" 2>/dev/null || true
    fi
  done
  assert_exact_runtime_process_contract disabled
  assert_active_runtime_process_env_contract "$helper_source_sha" "$expected_sha" "$node_id"
  # Reinstall the sentinel-bound boot guard after controlled manual starts.
  # Active processes keep running, while every enablement-prefix crash reboots
  # with all canonical units blocked until the sentinel is cleared last.
  install_maintenance_boot_guard "$tx_dir"
}

restore_saved_autostart() {
  local state_file="$1"
  local tx_dir="$2"
  local unit enabled active expected_sha helper_source_sha node_id
  validate_tx_dir "$tx_dir"
  expected_sha="$(current_head)"
  helper_source_sha="$(target_sha_from_tx "$tx_dir")"
  validate_sha "$expected_sha"
  validate_sha "$helper_source_sha"
  node_id="$(configured_node_id)"
  validate_service_state_file "$state_file"
  # Persist every worker decision before the API enablement decision. A reboot
  # can therefore never expose a marker-unaware baseline API with only a
  # partially enabled worker set.
  while IFS='|' read -r unit enabled active; do
    [ "$unit" != "linasbot.service" ] || continue
    if [ "$enabled" = "enabled" ]; then
      systemctl enable "$unit"
    else
      systemctl disable "$unit" 2>/dev/null || true
    fi
  done <"$state_file"
  fsync_systemd_enablement_state
  enabled="$(awk -F'|' '$1 == "linasbot.service" {print $2}' "$state_file")"
  test -n "$enabled" || die "saved API enablement state is missing"
  if [ "$enabled" = "enabled" ]; then
    systemctl enable linasbot.service
  else
    systemctl disable linasbot.service 2>/dev/null || true
  fi
  fsync_systemd_enablement_state
  while IFS='|' read -r unit enabled active; do
    if [ "$enabled" = "enabled" ]; then
      systemctl is-enabled --quiet "$unit" || \
        die "restored service enablement readback failed: $unit"
    else
      ! systemctl is-enabled --quiet "$unit" || \
        die "restored disabled service unexpectedly became enabled: $unit"
    fi
  done <"$state_file"
  assert_exact_runtime_process_contract enabled
  assert_active_runtime_process_env_contract "$helper_source_sha" "$expected_sha" "$node_id"
}

move_live_to_failed_once() {
  local source="$1"
  local destination="$2"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    test -d "$destination" && test ! -L "$destination" || \
      die "failed-runtime preservation destination is unsafe"
    assert_path_absent "$source" \
      "rollback source and preserved failed destination both exist"
  elif [ -e "$source" ] || [ -L "$source" ]; then
    test -d "$source" && test ! -L "$source" || die "rollback live source is unsafe"
    atomic_sibling_move "$source" "$destination"
  fi
}

preserve_partial_restore() {
  local source="$1"
  local sibling_dir="$2"
  local label="$3"
  local generation="$4"
  local counter=1 destination generation_label
  printf -v generation_label 'g%04d' "$generation"
  if [ ! -e "$source" ] && [ ! -L "$source" ]; then
    return 0
  fi
  test -d "$source" && test ! -L "$source" || die "partial rollback restore is unsafe"
  while :; do
    destination="$sibling_dir/partial-${label}-${generation_label}-${counter}"
    if [ ! -e "$destination" ] && [ ! -L "$destination" ]; then
      break
    fi
    counter=$((counter + 1))
    test "$counter" -le 100 || die "too many partial rollback restore generations"
  done
  atomic_sibling_move "$source" "$destination"
}

rollback_impl() {
  local previous_sha="$1"
  local tx_dir="$2"
  local sibling_dir target_sha phase generation generation_root generation_label
  if [ ! -e "$tx_dir/stage.complete" ] && [ ! -L "$tx_dir/stage.complete" ]; then
    return 0
  fi
  target_sha="$(<"$tx_dir/target.sha")"
  validate_sha "$target_sha"
  verify_stage_manifest_recovery "$tx_dir" "$target_sha" "$previous_sha"
  sibling_dir="$(sibling_dir_for_tx "$tx_dir")"
  phase="$(read_activation_phase "$tx_dir" "$target_sha" "$previous_sha")"
  if [ -z "$phase" ]; then
    test "$(current_head)" = "$previous_sha" || \
      die "activation crossed the release boundary without durable quiesced authority"
    git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || \
      die "tracked runtime data changed before activation; preserving it fail-closed"
    git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || \
      die "live index changed before activation; preserving it fail-closed"
    assert_path_absent "$sibling_dir/live-venv" \
      "activation moved the live venv without durable quiesced authority"
    assert_path_absent "$sibling_dir/live-dashboard-build" \
      "activation moved the dashboard without durable quiesced authority"
    log "node did not cross the durable activation boundary; keeping baseline drained"
    audit_untracked_runtime "$tx_dir" "pre-rollback-start" "$previous_sha" || \
      die "untracked runtime source appeared before rollback service start"
    node_ensure_maintenance "$tx_dir"
    node_assert_runtime_drained "$tx_dir"
    return 0
  fi
  generation="$(read_activation_generation "$tx_dir" "$target_sha" "$previous_sha")"
  [[ "$generation" =~ ^[1-9][0-9]{0,3}$ ]] || die "rollback activation generation is invalid"
  printf -v generation_label 'g%04d' "$generation"
  generation_root="$tx_dir/activation/$generation_label"
  if [ "$phase" = "rolled-back" ]; then
    test "$(current_head)" = "$previous_sha" || die "rolled-back phase has the wrong release"
    test -x "$REPO_DIR/venv/bin/python" || die "rolled-back phase lost the baseline venv"
    test -f "$REPO_DIR/dashboard/build/index.html" || \
      die "rolled-back phase lost the baseline dashboard"
    git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || \
      die "rolled-back tracked tree changed"
    git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || \
      die "rolled-back index changed"
    assert_baseline_artifact_evidence_restored "$tx_dir"
    verify_activation_sibling_authority "$tx_dir" "$target_sha" "$previous_sha"
    node_ensure_maintenance "$tx_dir"
    node_assert_runtime_drained "$tx_dir"
    return 0
  fi
  test -f "$MAINTENANCE_FILE" || die "rollback requires fail-closed maintenance"
  stop_runtime
  case "$phase" in
    quiesced | venv-moved | dashboard-moved)
      if [ "$(current_head)" = "$previous_sha" ]; then
        git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || \
          die "tracked runtime data changed before reset; rollback remains fail-closed"
        git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || \
          die "live index changed before reset; rollback remains fail-closed"
      fi
      ;;
  esac
  case "$phase" in
    quiesced | venv-moved | dashboard-moved | target-reset-started | target-installed | activated)
      write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" rollback-started "$generation"
      phase=rollback-started
      ;;
    rollback-started | rollback-live-moved | restored) ;;
    *) die "rollback activation phase is invalid" ;;
  esac
  if [ "$phase" = "rollback-started" ]; then
    move_live_to_failed_once "$REPO_DIR/venv" "$sibling_dir/failed-venv-$generation_label"
    move_live_to_failed_once \
      "$REPO_DIR/dashboard/build" "$sibling_dir/failed-dashboard-build-$generation_label"
    move_live_to_failed_once "$REPO_DIR/data" "$sibling_dir/failed-data-$generation_label"
    write_activation_phase \
      "$tx_dir" "$target_sha" "$previous_sha" rollback-live-moved "$generation"
    phase=rollback-live-moved
  fi
  if [ "$phase" = "rollback-live-moved" ]; then
    # A power cut during extraction can leave only a partial destination. Keep
    # it for audit and replay restoration solely from immutable stage authority.
    preserve_partial_restore "$REPO_DIR/venv" "$sibling_dir" venv "$generation"
    preserve_partial_restore \
      "$REPO_DIR/dashboard/build" "$sibling_dir" dashboard-build "$generation"
    preserve_partial_restore "$REPO_DIR/data" "$sibling_dir" data "$generation"
    # A killed forward or rollback reset may leave only Git's closed set of
    # root-owned lockfiles. Preserve those bytes under .git, prove no Git
    # mutator remains, and replay the exact baseline reset under the HA lock.
    recover_transaction_git_locks "$tx_dir" "$generation" rollback-reset
    git -C "$REPO_DIR" reset --hard "$previous_sha"
    verify_archive "$generation_root/data-quiesced.tar"
    tar --numeric-owner -C / -xpf "$generation_root/data-quiesced.tar"
    copy_private_file_durable "$generation_root/root-quiesced.env" "$REPO_DIR/.env"
    if [ -d "$sibling_dir/live-venv" ]; then
      atomic_sibling_move "$sibling_dir/live-venv" "$REPO_DIR/venv"
    else
      log "atomic live venv backup missing; restoring verified mode-600 archive fallback"
      verify_archive "$tx_dir/venv.tar"
      tar --numeric-owner -C / -xpf "$tx_dir/venv.tar"
    fi
    if [ -d "$sibling_dir/live-dashboard-build" ]; then
      atomic_sibling_move "$sibling_dir/live-dashboard-build" "$REPO_DIR/dashboard/build"
    else
      log "atomic dashboard backup missing; restoring verified mode-600 archive fallback"
      verify_archive "$tx_dir/dashboard-build.tar"
      tar --numeric-owner -C / -xpf "$tx_dir/dashboard-build.tar"
    fi
    test -x "$REPO_DIR/venv/bin/python" || die "rollback venv recovery failed"
    test -f "$REPO_DIR/dashboard/build/index.html" || die "rollback dashboard recovery failed"
    verify_archive "$tx_dir/systemd.tar"
    verify_archive "$tx_dir/nginx.tar"
    tar --numeric-owner -C / -xpf "$tx_dir/systemd.tar"
    tar --numeric-owner -C / -xpf "$tx_dir/nginx.tar"
    # HEAD, index, tracked worktree, runtime data and rollback runtimes are one
    # durability boundary.  A restored/rolled-back phase is never published
    # while Git or any live tree can still reflect a pre-power-loss state.
    fsync_tree "$REPO_DIR"
    fsync_path_and_parents \
      "$REPO_DIR/.env" \
      /etc/systemd/system/linasbot.service \
      /etc/systemd/system/linasbot-worker@.service \
      /etc/nginx/sites-available/linasaibot \
      /etc/nginx/sites-enabled \
      /etc/nginx/conf.d/linasbot-privacy-log.conf
    systemctl daemon-reload
    nginx -t
    systemctl reload nginx
    test "$(current_head)" = "$previous_sha" || die "rollback SHA changed before durable restore"
    git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || \
      die "rollback tracked tree is dirty before durable restore"
    git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || \
      die "rollback index is dirty before durable restore"
    write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" restored "$generation"
    phase=restored
  fi
  # Re-establish persistent markers and a boot guard.  A marker-unaware
  # baseline remains stopped until both-node rollback parity is proved.
  node_ensure_maintenance "$tx_dir"
  audit_untracked_runtime "$tx_dir" "pre-rollback-start" "$previous_sha" || \
    die "untracked runtime source appeared before rollback service start"
  assert_direct_port_unavailable
  assert_maintenance_readiness
  test "$(current_head)" = "$previous_sha" || die "rollback SHA mismatch"
  git -C "$REPO_DIR" diff --quiet "$previous_sha" -- || die "rolled-back tracked tree is dirty"
  git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" -- || die "rolled-back index is dirty"
  assert_baseline_artifact_evidence_restored "$tx_dir"
  fsync_tree "$REPO_DIR"
  write_activation_phase "$tx_dir" "$target_sha" "$previous_sha" rolled-back "$generation"
}

node_activate() {
  local target_sha="$1"
  local previous_sha="$2"
  local tx_dir="$3"
  local rc
  set +e
  (set -euo pipefail; activate_impl "$target_sha" "$previous_sha" "$tx_dir")
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    log "activation failed; starting automatic node rollback"
    rollback_impl "$previous_sha" "$tx_dir" || \
      die "activation and automatic node rollback both failed; maintenance remains active"
    return "$rc"
  fi
}

nginx_base_authority_for_tx() {
  local tx_dir="$1"
  local baseline="$tx_dir/maintenance-nginx.conf"
  local target_sha previous_sha phase generation target_authority
  if [ -f "$tx_dir/activation.state" ] && [ ! -L "$tx_dir/activation.state" ] && \
     [ -f "$tx_dir/stage.complete" ] && [ ! -L "$tx_dir/stage.complete" ] && \
     [ -f "$tx_dir/target.sha" ] && [ ! -L "$tx_dir/target.sha" ] && \
     [ -f "$tx_dir/previous.sha" ] && [ ! -L "$tx_dir/previous.sha" ]; then
    target_sha="$(<"$tx_dir/target.sha")"
    previous_sha="$(<"$tx_dir/previous.sha")"
    validate_sha "$target_sha"
    validate_sha "$previous_sha"
    phase="$(read_activation_phase "$tx_dir" "$target_sha" "$previous_sha")"
    case "$phase" in
      target-installed | activated | rollback-started | rollback-live-moved)
        if [ "$(current_head)" = "$target_sha" ]; then
          generation="$(read_activation_generation "$tx_dir" "$target_sha" "$previous_sha")"
          printf -v target_authority '%s/activation/g%04d/target-nginx.conf' "$tx_dir" "$generation"
          test -f "$target_authority" && test ! -L "$target_authority" || \
            die "target nginx activation authority is missing or unsafe"
          test "$(stat -c '%u:%g:%a' "$target_authority")" = "0:0:600" || \
            die "target nginx activation authority ownership or mode is unsafe"
          printf '%s\n' "$target_authority"
          return 0
        fi
        ;;
    esac
  fi
  test -f "$baseline" && test ! -L "$baseline" || \
    die "baseline nginx maintenance authority is missing or unsafe"
  test "$(stat -c '%u:%g:%a' "$baseline")" = "0:0:600" || \
    die "baseline nginx authority ownership or mode is unsafe"
  printf '%s\n' "$baseline"
}

publish_nginx_config_atomic() {
  local source="$1"
  local destination=/etc/nginx/sites-available/linasbot
  run_system_python_control - "$source" "$destination" <<'PY'
import hashlib
import os
import stat
import sys
import tempfile
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
parent = destination.parent


def read_regular(path: Path, *, expected_modes: set[int]) -> tuple[bytes, os.stat_result]:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) not in expected_modes
        or before.st_size > (1 << 20)
    ):
        raise SystemExit("nginx configuration authority is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("nginx configuration authority changed while opening")
        payload = os.read(descriptor, (1 << 20) + 1)
        if len(payload) > (1 << 20) or os.read(descriptor, 1):
            raise SystemExit("nginx configuration authority is oversized")
        return payload, before
    finally:
        os.close(descriptor)


parent_info = parent.lstat()
if (
    not stat.S_ISDIR(parent_info.st_mode)
    or stat.S_ISLNK(parent_info.st_mode)
    or parent_info.st_uid != 0
    or parent_info.st_gid != 0
):
    raise SystemExit("nginx configuration directory is unsafe")
payload, source_info = read_regular(source, expected_modes={0o600, 0o644})
if destination.exists() or destination.is_symlink():
    read_regular(destination, expected_modes={0o644})

descriptor, temporary_name = tempfile.mkstemp(prefix=".linasbot-ha-nginx.", dir=parent)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o644)
    os.fchown(descriptor, 0, 0)
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise SystemExit("nginx configuration atomic write made no progress")
        view = view[written:]
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1
    os.replace(temporary, destination)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass

installed, _ = read_regular(destination, expected_modes={0o644})
if installed != payload or hashlib.sha256(installed).digest() != hashlib.sha256(payload).digest():
    raise SystemExit("nginx configuration atomic readback differs")
after = source.lstat()
if (after.st_dev, after.st_ino, after.st_size) != (
    source_info.st_dev,
    source_info.st_ino,
    source_info.st_size,
):
    raise SystemExit("nginx source authority changed during publication")
PY
}

install_nginx_maintenance_override() {
  local tx_dir="$1"
  local live_config=/etc/nginx/sites-available/linasaibot
  local backup="$tx_dir/maintenance-nginx.conf"
  local candidate="$tx_dir/maintenance-nginx.candidate"
  local base_authority
  if [ -L "$backup" ]; then
    die "maintenance nginx backup is an unsafe symlink"
  elif [ ! -e "$backup" ]; then
    copy_private_file_durable "$live_config" "$backup"
  fi
  base_authority="$(nginx_base_authority_for_tx "$tx_dir")"
  run_system_python_control - "$base_authority" "$candidate" <<'PY'
import os
import re
import sys
import tempfile
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8", errors="strict")
if "linasbot-ha-maintenance-override" in source:
    raise SystemExit("maintenance nginx override already exists")
block = """    # linasbot-ha-maintenance-override
    location = /api/ready {
        default_type application/json;
        add_header Cache-Control \"no-store\" always;
        return 503 '{\"ok\":false,\"role\":\"readiness\",\"checks\":{\"maintenance\":{\"ok\":false}}}';
    }

"""
candidate, count = re.subn(r"(?m)^(server\s*\{\s*\n)", r"\1" + block, source)
if count < 1:
    raise SystemExit("no nginx server block found for maintenance override")
destination = Path(sys.argv[2])
descriptor, temporary_name = tempfile.mkstemp(prefix=".maintenance-nginx.candidate.", dir=destination.parent)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    os.fchown(descriptor, 0, 0)
    os.write(descriptor, candidate.encode("utf-8"))
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1
    os.replace(temporary, destination)
    directory = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY
  if ! cmp -s "$candidate" "$live_config"; then
    # The old publisher could be killed after copying an exact prefix. Repair
    # only bytes that are a strict prefix of this transaction's authenticated
    # candidate; every other live divergence remains an owner blocker.
    if ! run_system_python_control - "$live_config" "$candidate" <<'PY'
import os
import stat
import sys
from pathlib import Path

live, candidate = map(Path, sys.argv[1:])


def read(path: Path, expected_modes: set[int]) -> bytes:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) not in expected_modes
        or info.st_size > (1 << 20)
    ):
        raise SystemExit(1)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        payload = os.read(descriptor, (1 << 20) + 1)
        if (
            (info.st_dev, info.st_ino, info.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
            or len(payload) > (1 << 20)
            or os.read(descriptor, 1)
        ):
            raise SystemExit(1)
        return payload
    finally:
        os.close(descriptor)


live_bytes = read(live, {0o644})
candidate_bytes = read(candidate, {0o600})
if not live_bytes or len(live_bytes) >= len(candidate_bytes) or not candidate_bytes.startswith(live_bytes):
    raise SystemExit(1)
PY
    then
      cmp -s "$base_authority" "$live_config" || \
        die "live nginx configuration differs from its release-bound authority"
    fi
    publish_nginx_config_atomic "$candidate"
  fi
  fsync_path_and_parents "$backup" "$candidate" "$live_config" \
    "$tx_dir" /etc/nginx/sites-available
  if ! nginx -t; then
    publish_nginx_config_atomic "$base_authority"
    nginx -t
    stop_runtime
    die "nginx maintenance override validation failed; API stopped fail-closed"
  fi
  systemctl reload nginx
}

restore_nginx_maintenance_override() {
  local tx_dir="$1"
  local live_config=/etc/nginx/sites-available/linasaibot
  local base_authority
  if grep -q "linasbot-ha-maintenance-override" "$live_config" 2>/dev/null; then
    base_authority="$(nginx_base_authority_for_tx "$tx_dir")"
    publish_nginx_config_atomic "$base_authority"
    nginx -t
    systemctl reload nginx
  fi
}

assert_release_bound_nginx() {
  local tx_dir="$1"
  local expected
  expected="$(nginx_base_authority_for_tx "$tx_dir")"
  cmp -s "$expected" /etc/nginx/sites-available/linasaibot || \
    die "installed nginx config differs from the activation-phase authority"
  nginx -t
}

assert_release_bound_nginx_while_drained() {
  local tx_dir="$1"
  local expected
  expected="$(nginx_base_authority_for_tx "$tx_dir")"
  run_system_python_control - "$expected" /etc/nginx/sites-available/linasaibot <<'PY'
import re
import sys
from pathlib import Path

base = Path(sys.argv[1]).read_text(encoding="utf-8", errors="strict")
live = Path(sys.argv[2]).read_text(encoding="utf-8", errors="strict")
block = """    # linasbot-ha-maintenance-override
    location = /api/ready {
        default_type application/json;
        add_header Cache-Control \"no-store\" always;
        return 503 '{\"ok\":false,\"role\":\"readiness\",\"checks\":{\"maintenance\":{\"ok\":false}}}';
    }

"""
override, count = re.subn(r"(?m)^(server\s*\{\s*\n)", r"\1" + block, base)
if count < 1 or live not in {base, override}:
    raise SystemExit("drained nginx config differs from release-bound base/override authority")
PY
  nginx -t
}

clear_maintenance_markers_durable() {
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  assert_secure_maintenance_marker "$VOLATILE_MAINTENANCE_FILE"
  unlink "$VOLATILE_MAINTENANCE_FILE"
  unlink "$MAINTENANCE_FILE"
  fsync_path_and_parents "$META_HA_STATE_ROOT" /run
  assert_path_absent "$MAINTENANCE_FILE" "persistent maintenance marker removal failed"
  assert_path_absent "$VOLATILE_MAINTENANCE_FILE" "volatile maintenance marker removal failed"
}

drain_guard_authority_tool() {
  local operation="$1"
  local tx_dir="$2"
  run_system_python_control - "$operation" "$tx_dir" "$MAINTENANCE_FILE" \
    "$VOLATILE_MAINTENANCE_FILE" "$DEPLOY_NODE_ACTIVE_FILE" <<'PY'
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

operation, raw_tx_dir, persistent_raw, volatile_raw, sentinel_raw = sys.argv[1:]
tx_dir = Path(raw_tx_dir)
receipt = tx_dir / "drain-guard.complete"
paths = {
    "predrain-service-state": (tx_dir / "predrain-service-state", 0o600),
    "maintenance-nginx.conf": (tx_dir / "maintenance-nginx.conf", 0o600),
    "maintenance-boot-guard.conf": (tx_dir / "maintenance-boot-guard.conf", 0o600),
    "persistent-maintenance": (Path(persistent_raw), 0o600),
    "volatile-maintenance": (Path(volatile_raw), 0o600),
    "deploy-node-active": (Path(sentinel_raw), 0o600),
    "api-boot-guard": (
        Path("/etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf"),
        0o644,
    ),
    "worker-boot-guard": (
        Path("/etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf"),
        0o644,
    ),
}


def secure_read(path: Path, mode: int, *, limit: int = 1 << 20) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_nlink != 1
        or before.st_size > limit
    ):
        raise SystemExit(f"drain guard authority is unsafe: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SystemExit("drain guard authority changed while opening")
        raw = os.read(descriptor, limit + 1)
        if len(raw) > limit or os.read(descriptor, 1):
            raise SystemExit("drain guard authority is oversized")
        if operation == "publish":
            os.fsync(descriptor)
        return raw
    finally:
        os.close(descriptor)


raw = {name: secure_read(path, mode) for name, (path, mode) in paths.items()}
if raw["deploy-node-active"] != (raw_tx_dir + "\n").encode("ascii"):
    raise SystemExit("drain guard sentinel belongs to another transaction")
if raw["api-boot-guard"] != raw["maintenance-boot-guard.conf"]:
    raise SystemExit("installed API guard differs from durable candidate")
if raw["worker-boot-guard"] != raw["maintenance-boot-guard.conf"]:
    raise SystemExit("installed worker guard differs from durable candidate")
payload = {
    "schema": 1,
    "tx_dir": raw_tx_dir,
    "files": {name: hashlib.sha256(value).hexdigest() for name, value in sorted(raw.items())},
}
encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
if operation == "verify":
    if secure_read(receipt, 0o600) != encoded:
        raise SystemExit("durable drain guard receipt changed")
elif operation == "publish":
    if receipt.exists() or receipt.is_symlink():
        if secure_read(receipt, 0o600) != encoded:
            raise SystemExit("existing drain guard receipt changed")
    else:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".drain-guard.complete.", dir=tx_dir)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            os.fchown(descriptor, 0, 0)
            os.write(descriptor, encoded)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, receipt)
            directory = os.open(tx_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
else:
    raise SystemExit("unknown drain guard authority operation")
PY
}

verify_runtime_autostart_disabled() {
  local queue
  ! systemctl is-enabled --quiet linasbot.service || \
    die "canonical API autostart is enabled while node is drained"
  for queue in "${WORKER_QUEUES[@]}"; do
    ! systemctl is-enabled --quiet "linasbot-worker@${queue}.service" || \
      die "canonical worker autostart is enabled while node is drained: $queue"
  done
}

publish_drain_guard_authority() {
  local tx_dir="$1"
  validate_service_state_file "$tx_dir/predrain-service-state"
  assert_deploy_node_sentinel "$tx_dir"
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  assert_secure_maintenance_marker "$VOLATILE_MAINTENANCE_FILE"
  verify_runtime_autostart_disabled
  install_maintenance_boot_guard "$tx_dir"
  fsync_systemd_enablement_state
  fsync_path_and_parents \
    "$tx_dir/predrain-service-state" \
    "$tx_dir/maintenance-nginx.conf" \
    "$tx_dir/maintenance-boot-guard.conf" \
    "$MAINTENANCE_FILE" "$META_HA_STATE_ROOT" \
    /etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf \
    /etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf \
    /etc/systemd/system/linasbot.service.d \
    /etc/systemd/system/linasbot-worker@.service.d \
    /etc/systemd/system
  drain_guard_authority_tool publish "$tx_dir"
  drain_guard_authority_tool verify "$tx_dir"
}

verify_drain_guard_authority() {
  local tx_dir="$1"
  validate_service_state_file "$tx_dir/predrain-service-state"
  assert_deploy_node_sentinel "$tx_dir"
  verify_runtime_autostart_disabled
  test "$(systemctl show -p NeedDaemonReload --value linasbot.service)" = "no" || \
    die "API guard requires a systemd reload"
  test "$(systemctl show -p NeedDaemonReload --value linasbot-worker@.service)" = "no" || \
    die "worker guard requires a systemd reload"
  drain_guard_authority_tool verify "$tx_dir"
}

node_mark_maintenance() {
  local tx_dir="$1"
  validate_tx_dir "$tx_dir"
  ensure_transaction_dir_durable "$tx_dir"
  assert_path_absent "$MAINTENANCE_FILE" "persistent maintenance marker already exists or is unsafe"
  assert_path_absent "$VOLATILE_MAINTENANCE_FILE" "volatile maintenance marker already exists or is unsafe"
  if [ -e "$tx_dir/predrain-service-state" ] || [ -L "$tx_dir/predrain-service-state" ]; then
    validate_service_state_file "$tx_dir/predrain-service-state"
    assert_service_state_capture_is_pre_mutation
  else
    assert_service_state_capture_is_pre_mutation
    capture_service_state "$tx_dir/predrain-service-state"
  fi
  validate_service_state_file "$tx_dir/predrain-service-state"
  # The exact inventory and transaction authority are durable before the first
  # enablement change. A crash during/after disable is therefore recoverable.
  install_maintenance_boot_guard "$tx_dir"
  assert_maintenance_boot_guard_loaded "$tx_dir"
  arm_deploy_node_sentinel "$tx_dir"
  disable_runtime_autostart
  arm_maintenance_markers
  stop_queue_workers
  # Port 80 is only a diagnostic fallback.  The owner-confirmed DO load
  # balancer probes the API directly on :8003.
  install_nginx_maintenance_override "$tx_dir"
  if ! assert_direct_maintenance_readiness; then
    log "current release is not marker-aware on direct LB port 8003; stopping API and workers"
    stop_runtime
    printf 'stopped\n' >"$tx_dir/drain-runtime-stopped"
    chmod 0600 "$tx_dir/drain-runtime-stopped"
  fi
  publish_drain_guard_authority "$tx_dir"
  node_assert_runtime_drained "$tx_dir"
  log "node is fail-closed on direct LB port 8003"
}

node_ensure_maintenance() {
  local tx_dir="$1"
  validate_tx_dir "$tx_dir"
  ensure_transaction_dir_durable "$tx_dir"
  if [ -e "$tx_dir/predrain-service-state" ] || [ -L "$tx_dir/predrain-service-state" ]; then
    validate_service_state_file "$tx_dir/predrain-service-state"
  else
    assert_service_state_capture_is_pre_mutation
    capture_service_state "$tx_dir/predrain-service-state"
  fi
  if [ -e "$DEPLOY_NODE_ACTIVE_FILE" ] || [ -L "$DEPLOY_NODE_ACTIVE_FILE" ]; then
    assert_deploy_node_sentinel "$tx_dir"
    # Admission removes the transaction guards only after durably disabling
    # every canonical unit.  A crash in either unlink/reinstall prefix leaves
    # the sentinel but may leave one or both guard files absent.  Repair is
    # authorized only after proving autostart is still completely disabled.
    if ! maintenance_boot_guard_is_loaded "$tx_dir"; then
      verify_runtime_autostart_disabled
      stop_runtime
      assert_direct_port_unavailable
      install_maintenance_boot_guard "$tx_dir"
    fi
    assert_maintenance_boot_guard_loaded "$tx_dir"
  else
    install_maintenance_boot_guard "$tx_dir"
    assert_maintenance_boot_guard_loaded "$tx_dir"
    arm_deploy_node_sentinel "$tx_dir"
  fi
  disable_runtime_autostart
  arm_maintenance_markers
  stop_queue_workers
  if systemctl is-active --quiet linasbot.service && ! assert_direct_maintenance_readiness; then
    # A marker-unaware old release can only be withdrawn from the actual DO
    # :8003 health target by closing that port.
    stop_runtime
    printf 'stopped\n' >"$tx_dir/drain-runtime-stopped"
    chmod 0600 "$tx_dir/drain-runtime-stopped"
  fi
  install_nginx_maintenance_override "$tx_dir"
  publish_drain_guard_authority "$tx_dir"
  node_assert_runtime_drained "$tx_dir"
}

node_assert_runtime_drained() {
  local tx_dir="$1"
  local queue
  validate_tx_dir "$tx_dir"
  verify_drain_guard_authority "$tx_dir"
  assert_deploy_node_sentinel "$tx_dir"
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  assert_secure_maintenance_marker "$VOLATILE_MAINTENANCE_FILE"
  assert_maintenance_readiness
  for queue in "${WORKER_QUEUES[@]}"; do
    ! systemctl is-active --quiet "linasbot-worker@${queue}.service" || \
      die "queue worker is active while node is drained: $queue"
  done
  if systemctl is-active --quiet linasbot.service && systemctl is-active --quiet "$VERIFY_API_UNIT"; then
    die "canonical and transient verification APIs are both active"
  elif systemctl is-active --quiet "$VERIFY_API_UNIT"; then
    assert_unit_contract "$VERIFY_API_UNIT"
    assert_health_while_drained
    assert_direct_maintenance_readiness
  elif systemctl is-active --quiet linasbot.service; then
    assert_unit_contract linasbot
    assert_health_while_drained
    assert_direct_maintenance_readiness
  else
    assert_direct_port_unavailable
  fi
}

start_admitted_target_runtime() {
  local tx_dir="$1"
  local queue target_sha node_id
  target_sha="$(<"$tx_dir/target.sha")"
  validate_sha "$target_sha"
  node_id="$(configured_node_id)"
  assert_deploy_node_sentinel "$tx_dir"
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  # The canonical units remain disabled while the guard is removed. A crash at
  # this boundary therefore cannot let systemd auto-start an unverified worker.
  systemctl disable linasbot.service 2>/dev/null || true
  for queue in "${WORKER_QUEUES[@]}"; do
    systemctl disable "linasbot-worker@${queue}.service" 2>/dev/null || true
  done
  # Recheck the exact installed unit contract immediately before any canonical
  # process starts.  The earlier activation audit cannot authorize a unit file
  # that changed while both nodes were waiting for parity/admission.
  assert_unit_file_contract linasbot
  for queue in "${WORKER_QUEUES[@]}"; do
    assert_unit_file_contract "linasbot-worker@${queue}.service"
  done
  systemctl start linasbot.service
  for _ in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:8003/api/health 2>/dev/null | \
      grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
      break
    fi
    sleep 1
  done
  systemctl is-active --quiet linasbot.service || die "canonical target API failed final start"
  assert_unit_contract linasbot
  assert_health_while_drained
  assert_direct_maintenance_readiness
  if durable_queues_enabled; then
    for queue in "${WORKER_QUEUES[@]}"; do
      systemctl start "linasbot-worker@${queue}.service"
      systemctl is-active --quiet "linasbot-worker@${queue}.service" || \
        die "target worker failed final start: $queue"
      assert_unit_contract "linasbot-worker@${queue}.service"
    done
    curl -fsS http://127.0.0.1:8003/api/queue/ready | \
      grep -q '"ok"[[:space:]]*:[[:space:]]*true' || die "target queue readiness failed"
  else
    for queue in "${WORKER_QUEUES[@]}"; do
      systemctl disable --now "linasbot-worker@${queue}.service" 2>/dev/null || true
    done
  fi
  assert_direct_maintenance_readiness
  assert_legacy_retirement_contract "$(configured_node_id)"
  assert_exact_runtime_process_contract disabled
  assert_active_runtime_process_env_contract "$target_sha" "$target_sha" "$node_id"
  install_maintenance_boot_guard "$tx_dir"
}

enable_admitted_target_autostart() {
  local tx_dir="$1"
  local queue target_sha node_id
  validate_tx_dir "$tx_dir"
  target_sha="$(<"$tx_dir/target.sha")"
  validate_sha "$target_sha"
  node_id="$(configured_node_id)"
  # Workers are enabled and durably read back before the API is enabled last.
  # Until the final API barrier, a reboot cannot expose a partially enabled
  # canonical runtime to the direct load-balancer port.
  if durable_queues_enabled; then
    for queue in "${WORKER_QUEUES[@]}"; do
      systemctl is-active --quiet "linasbot-worker@${queue}.service" || \
        die "target worker stopped before autostart enable: $queue"
      assert_unit_contract "linasbot-worker@${queue}.service"
      systemctl enable "linasbot-worker@${queue}.service"
      systemctl is-enabled --quiet "linasbot-worker@${queue}.service" || \
        die "target worker autostart enable failed: $queue"
    done
  else
    for queue in "${WORKER_QUEUES[@]}"; do
      systemctl disable --now "linasbot-worker@${queue}.service" 2>/dev/null || true
      ! systemctl is-enabled --quiet "linasbot-worker@${queue}.service" || \
        die "disabled durable worker unexpectedly remained enabled: $queue"
    done
  fi
  fsync_systemd_enablement_state
  if durable_queues_enabled; then
    for queue in "${WORKER_QUEUES[@]}"; do
      systemctl is-enabled --quiet "linasbot-worker@${queue}.service" || \
        die "target worker enablement readback failed after durability barrier: $queue"
    done
  fi
  systemctl enable linasbot.service
  fsync_systemd_enablement_state
  systemctl is-enabled --quiet linasbot.service || die "target API enablement readback failed"
  assert_exact_runtime_process_contract enabled
  assert_active_runtime_process_env_contract "$target_sha" "$target_sha" "$node_id"
}

node_clear_maintenance() {
  local tx_dir="$1"
  local admission_sha activation_state="" rollback_state_file="" target_sha previous_sha
  validate_tx_dir "$tx_dir"
  assert_deploy_node_sentinel "$tx_dir"
  assert_secure_maintenance_marker "$MAINTENANCE_FILE"
  assert_secure_maintenance_marker "$VOLATILE_MAINTENANCE_FILE"
  admission_sha="$(current_head)"
  validate_sha "$admission_sha"
  target_sha="$(target_sha_from_tx "$tx_dir")"
  if [ -f "$tx_dir/previous.sha" ] && [ ! -L "$tx_dir/previous.sha" ]; then
    previous_sha="$(<"$tx_dir/previous.sha")"
  else
    previous_sha="$admission_sha"
  fi
  validate_sha "$target_sha"
  validate_sha "$previous_sha"
  audit_untracked_runtime "$tx_dir" "pre-admission" "$admission_sha" || \
    die "untracked runtime source appeared before LB admission"
  assert_legacy_retirement_contract "$(configured_node_id)"
  activation_state="$(read_activation_phase "$tx_dir" "$target_sha" "$previous_sha")"
  if [ "$activation_state" = "activated" ]; then
    test "$admission_sha" = "$target_sha" || die "target admission SHA differs from activation authority"
    # Target parity was proven with both nodes drained. Switch from the
    # reboot-volatile verification unit to canonical units while the durable
    # marker still returns direct :8003 readiness 503; workers start only here.
    stop_runtime
    assert_direct_port_unavailable
    disable_runtime_autostart
    remove_maintenance_boot_guard "$tx_dir"
    start_admitted_target_runtime "$tx_dir"
    restore_nginx_maintenance_override "$tx_dir"
    assert_release_bound_nginx "$tx_dir"
    enable_admitted_target_autostart "$tx_dir"
    write_pre_admission_proof "$tx_dir" "$admission_sha"
    clear_maintenance_markers_durable
  else
    test -z "$activation_state" || test "$activation_state" = "rolled-back" || \
      die "rollback admission requires a durable rolled-back activation phase"
    test "$admission_sha" = "$previous_sha" || \
      die "rollback admission SHA differs from baseline authority"
    # A marker-unaware exact rollback baseline must remain stopped until the
    # marker and guard are cleared after equal-baseline rollback parity.
    stop_runtime
    validate_service_state_file "$tx_dir/predrain-service-state"
    rollback_state_file="$tx_dir/predrain-service-state"
    disable_runtime_autostart
    remove_maintenance_boot_guard "$tx_dir"
    # Start the exact saved active state while every unit remains disabled.
    # The marker-unaware baseline may answer ready here, but orchestrators call
    # this phase only after equal rollback parity has already been proved.
    start_saved_runtime_disabled "$rollback_state_file" "$tx_dir"
    restore_saved_autostart "$rollback_state_file" "$tx_dir"
    write_pre_admission_proof "$tx_dir" "$admission_sha"
    clear_maintenance_markers_durable
    restore_nginx_maintenance_override "$tx_dir"
    assert_release_bound_nginx "$tx_dir"
  fi
  for _ in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:8003/api/ready 2>/dev/null | \
      grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
      assert_ready
      assert_legacy_retirement_contract "$(configured_node_id)"
      write_admission_proof "$tx_dir" "$admission_sha"
      # The transaction sentinel is the last per-node fail-closed artifact to
      # leave.  Exact readiness and a durable admission proof already exist.
      clear_deploy_node_sentinel "$tx_dir"
      # With the sentinel absent, the guard conditions permit the complete,
      # durably enabled runtime on reboot. Remove the transaction drop-ins only
      # after that safe boundary and prove the final serving contract again.
      remove_maintenance_boot_guard "$tx_dir"
      node_assert_serving_contract "$admission_sha"
      log "node admitted by /api/ready"
      return 0
    fi
    sleep 1
  done
  die "node did not become ready after maintenance clear"
}

node_assert_release_drained() {
  local expected_sha="$1"
  local tx_dir="$2"
  validate_tx_dir "$tx_dir"
  test "$(current_head)" = "$expected_sha" || die "drained node release mismatch"
  git -C "$REPO_DIR" diff --quiet "$expected_sha" -- || \
    die "drained node tracked worktree changed after activation proof"
  git -C "$REPO_DIR" diff --cached --quiet "$expected_sha" -- || \
    die "drained node index changed after activation proof"
  audit_untracked_runtime "$tx_dir" "precommit-drained" "$expected_sha" || \
    die "drained node gained an untracked executable/importable runtime"
  assert_legacy_retirement_contract "$(configured_node_id)"
  node_assert_runtime_drained "$tx_dir"
}

node_assert_serving_contract() {
  local expected_sha="$1"
  assert_path_absent "$MAINTENANCE_FILE" "ready node still has persistent maintenance marker"
  assert_path_absent "$VOLATILE_MAINTENANCE_FILE" "ready node still has volatile maintenance marker"
  assert_path_absent /etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf \
    "ready node still has an API boot guard"
  assert_path_absent /etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf \
    "ready node still has a worker boot guard"
  test "$(current_head)" = "$expected_sha" || die "ready node release mismatch"
  git -C "$REPO_DIR" diff --quiet "$expected_sha" -- || die "ready node tracked worktree is dirty"
  git -C "$REPO_DIR" diff --cached --quiet "$expected_sha" -- || die "ready node index is dirty"
  assert_legacy_retirement_contract "$(configured_node_id)"
  assert_controlled_failover_static_guard_contract
  assert_unit_contract linasbot
  assert_exact_runtime_process_contract enabled
  assert_ready
}

node_assert_release_ready() {
  local expected_sha="$1"
  assert_path_absent "$DEPLOY_NODE_ACTIVE_FILE" \
    "ready node still has a per-node deployment sentinel"
  node_assert_serving_contract "$expected_sha"
}

node_assert_exact_head() {
  local expected_sha="$1"
  local tx_dir="$2"
  validate_tx_dir "$tx_dir"
  test "$(current_head)" = "$expected_sha" || die "recovery node release mismatch"
  git -C "$REPO_DIR" diff --quiet "$expected_sha" -- || die "recovery tracked tree is dirty"
  git -C "$REPO_DIR" diff --cached --quiet "$expected_sha" -- || die "recovery index is dirty"
  audit_untracked_runtime "$tx_dir" "recovery-boundary" "$expected_sha" || \
    die "untracked runtime source blocks recovery"
  assert_legacy_retirement_contract "$(configured_node_id)"
}

node_recover_admit() {
  local expected_sha="$1"
  local tx_dir="$2"
  local helper_source_sha node_id
  helper_source_sha="$(target_sha_from_tx "$tx_dir")"
  validate_sha "$helper_source_sha"
  node_id="$(configured_node_id)"
  node_assert_exact_head "$expected_sha" "$tx_dir"
  if (node_assert_serving_contract "$expected_sha") >/dev/null 2>&1 && \
     admission_proof_is_exact "$tx_dir" "$expected_sha"; then
    assert_active_runtime_process_env_contract "$helper_source_sha" "$expected_sha" "$node_id"
    if [ -e "$DEPLOY_NODE_ACTIVE_FILE" ] || [ -L "$DEPLOY_NODE_ACTIVE_FILE" ]; then
      assert_deploy_node_sentinel "$tx_dir"
      clear_deploy_node_sentinel "$tx_dir"
    fi
    node_assert_release_ready "$expected_sha"
    log "recovery admission already completed for $expected_sha"
    return 0
  fi
  node_ensure_maintenance "$tx_dir"
  node_assert_release_drained "$expected_sha" "$tx_dir"
  node_clear_maintenance "$tx_dir"
  node_assert_release_ready "$expected_sha"
}

node_recover_rollback() {
  local previous_sha="$1"
  local tx_dir="$2"
  if (node_assert_release_ready "$previous_sha") >/dev/null 2>&1; then
    log "recovery rollback and admission already completed for $previous_sha"
    return 0
  fi
  node_ensure_maintenance "$tx_dir"
  rollback_impl "$previous_sha" "$tx_dir"
  node_assert_release_drained "$previous_sha" "$tx_dir"
}

node_dispatch() {
  local phase="${1:-}"
  local runtime_expected_node=""
  shift || true
  require_root
  if [ "$phase" = "preflight" ]; then
    runtime_expected_node="${2:-}"
  elif [ "$phase" = "runtime-contract" ]; then
    runtime_expected_node="${1:-}"
  fi
  acquire_meta_live_lock
  if [ "$phase" = "runtime-contract" ]; then
    assert_python_runtime_contract "$runtime_expected_node"
    return 0
  fi
  assert_python_runtime_contract "$runtime_expected_node" >/dev/null
  case "$phase" in
    preflight)
      validate_sha "${1:-}"
      node_preflight "$1" "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}"
      ;;
    lb-attestation)
      validate_sha "${1:-}"
      assert_fresh_lb_ready_attestation "$1" "${2:-}" "${3:-}"
      ;;
    release-bundle)
      validate_sha "${1:-}"
      assert_release_bundle "$1" "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}"
      ;;
    env-evidence)
      validate_sha "${1:-}"
      validate_sha "${2:-}"
      cluster_runtime_env_evidence "$2" "$1" "${3:-}"
      ;;
    stage)
      validate_sha "${1:-}"
      validate_sha "${2:-}"
      validate_tx_dir "${3:-}"
      backup_live_node "$1" "$2" "$3" "${4:-}" "${5:-}" "${6:-}" "${7:-}" "${8:-}"
      ;;
    retry-stage)
      validate_sha "${1:-}"
      validate_sha "${2:-}"
      validate_tx_dir "${3:-}"
      prepare_retry_stage "$1" "$2" "$3" "${4:-}" "${5:-}" "${6:-}" "${7:-}" "${8:-}"
      ;;
    stage-evidence)
      validate_sha "${1:-}"
      validate_sha "${2:-}"
      validate_tx_dir "${3:-}"
      stage_artifact_evidence "$3" "$1" "$2"
      ;;
    release-evidence)
      validate_sha "${1:-}"
      validate_sha "${2:-}"
      validate_tx_dir "${3:-}"
      release_artifact_evidence "$3" "$1" "$2"
      ;;
    mark-maintenance)
      validate_tx_dir "${1:-}"
      node_mark_maintenance "$1"
      ;;
    ensure-maintenance)
      validate_tx_dir "${1:-}"
      node_ensure_maintenance "$1"
      ;;
    clear-maintenance)
      validate_tx_dir "${1:-}"
      node_clear_maintenance "$1"
      ;;
    activate)
      validate_sha "${1:-}"
      validate_sha "${2:-}"
      validate_tx_dir "${3:-}"
      node_activate "$1" "$2" "$3"
      ;;
    rollback)
      validate_sha "${1:-}"
      validate_tx_dir "${2:-}"
      rollback_impl "$1" "$2"
      ;;
    assert-drained)
      validate_sha "${1:-}"
      validate_tx_dir "${2:-}"
      node_assert_release_drained "$1" "$2"
      ;;
    assert-ready)
      validate_sha "${1:-}"
      node_assert_release_ready "$1"
      ;;
    assert-head)
      validate_sha "${1:-}"
      validate_tx_dir "${2:-}"
      node_assert_exact_head "$1" "$2"
      ;;
    recover-admit)
      validate_sha "${1:-}"
      validate_tx_dir "${2:-}"
      node_recover_admit "$1" "$2"
      ;;
    recover-rollback)
      validate_sha "${1:-}"
      validate_tx_dir "${2:-}"
      node_recover_rollback "$1" "$2"
      ;;
    *)
      die "unknown node phase: $phase"
      ;;
  esac
}

reject_self_peer() {
  local peer_host="$1"
  local peer_addresses local_addresses
  peer_addresses="$(getent ahostsv4 "$peer_host" | awk '{print $1}' | sort -u)"
  local_addresses="$({ hostname -I 2>/dev/null || true; ip -o -4 addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1; } | \
    tr ' ' '\n' | sed '/^$/d' | sort -u)"
  test -n "$peer_addresses" || die "HA peer does not resolve"
  if grep -Fxf <(printf '%s\n' "$peer_addresses") \
    <(printf '%s\n' "$local_addresses") >/dev/null; then
    die "HA peer resolves to this node"
  fi
}

remote_node() {
  local peer_host="$1"
  shift
  ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
    /usr/bin/env -i HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    /bin/bash --noprofile --norc -s -- node \
    "$INTERNAL_NODE_DISPATCH_CONFIRM" "$@" <"$0"
}

prepare_remote_exact_helper() {
  local peer_host="$1"
  local helper_hash remote_root remote_helper
  helper_hash="$(sha256sum "$0" | awk '{print $1}')"
  validate_digest "$helper_hash"
  remote_root="$(ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
    /usr/bin/mktemp -d -p /run linasbot-release-helper.XXXXXXXX)"
  case "$remote_root" in
    /run/linasbot-release-helper.????????) ;;
    *) die "remote exact-helper root is outside its volatile namespace" ;;
  esac
  remote_helper="$remote_root/deploy_meta_release_ha.sh"
  /usr/bin/scp -q "${SSH_OPTIONS[@]}" -- "$0" "root@${peer_host}:$remote_helper"
  ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
    /usr/bin/env -i HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    /bin/bash --noprofile --norc -c \
    'set -euo pipefail
     helper="$1"
     expected="$2"
     chmod 0700 "$helper"
     test -f "$helper" && test ! -L "$helper"
     test "$(stat -c "%F:%u:%g:%a:%h" "$helper")" = "regular file:0:0:700:1"
     test "$(sha256sum "$helper" | awk "{print \\$1}")" = "$expected"
     sync -d "$helper"
     sync -f "$(dirname "$helper")"' \
    bash "$remote_helper" "$helper_hash"
  printf '%s\n' "$remote_root"
}

cleanup_remote_exact_helper() {
  local peer_host="$1"
  local remote_root="$2"
  case "$remote_root" in
    /run/linasbot-release-helper.????????) ;;
    *) die "remote exact-helper cleanup root is invalid" ;;
  esac
  ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
    /usr/bin/env -i HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    /bin/bash --noprofile --norc -c \
    'set -euo pipefail
     root="$1"
     case "$root" in /run/linasbot-release-helper.????????) ;; *) exit 1 ;; esac
     unlink "$root/deploy_meta_release_ha.sh"
     rmdir "$root"' bash "$remote_root"
}

install_release_bundle_cluster() {
  local incoming_dir="$1"
  local target_sha="$2"
  local artifact_id="$3"
  local artifact_api_sha="$4"
  local manifest_sha="$5"
  local run_id="$6"
  local run_attempt="$7"
  local control_sha="$8"
  local source_sha="$9"
  local target_tree_sha="${10}"
  local confirmation="${11}"
  local peer_host="$DEFAULT_PEER_HOST"
  local remote_helper_root="" remote_helper remote_incoming=""
  local path cleanup_rc=0 rc=0
  local expected_files=(
    release-manifest.json wheelhouse.tar dashboard-build.tar control-plane.tar
    source.bundle "$PYTHON_RUNTIME_ARTIFACT"
  )
  require_root
  validate_sha "$target_sha"
  case "$incoming_dir" in
    "$RELEASE_INCOMING_PREFIX"????????) ;;
    *) die "cluster release import directory is outside its exact namespace" ;;
  esac
  remote_helper_root="$(prepare_remote_exact_helper "$peer_host")"
  remote_helper="$remote_helper_root/deploy_meta_release_ha.sh"
  remote_incoming="$(ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
    /usr/bin/mktemp -d -p /run linasbot-release-import.XXXXXXXX)"
  case "$remote_incoming" in
    "$RELEASE_INCOMING_PREFIX"????????) ;;
    *) die "remote release import directory is outside its exact namespace" ;;
  esac
  for path in "${expected_files[@]}"; do
    /usr/bin/scp -q -p "${SSH_OPTIONS[@]}" -- \
      "$incoming_dir/$path" "root@${peer_host}:$remote_incoming/$path"
  done
  set +e
  ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
    /usr/bin/env -i HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    /bin/bash --noprofile --norc "$remote_helper" install-release-bundle \
    "$INTERNAL_NODE_DISPATCH_CONFIRM" node02 "$remote_incoming" "$target_sha" \
    "$artifact_id" "$artifact_api_sha" \
    "$manifest_sha" "$run_id" "$run_attempt" "$control_sha" "$source_sha" \
    "$target_tree_sha" "$confirmation"
  rc=$?
  set -e
  if [ "$rc" = 0 ]; then
    install_release_bundle node01 "$incoming_dir" "$target_sha" "$artifact_id" \
      "$artifact_api_sha" "$manifest_sha" "$run_id" "$run_attempt" \
      "$control_sha" "$source_sha" "$target_tree_sha" "$confirmation" || rc=$?
  fi
  if [ -n "$remote_incoming" ]; then
    ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
      /usr/bin/env -i HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      PATH=/usr/sbin:/usr/bin:/sbin:/bin \
      /bin/bash --noprofile --norc -c \
      'set -euo pipefail
       root="$1"
       shift
       case "$root" in /run/linasbot-release-import.????????) ;; *) exit 1 ;; esac
       for name in "$@"; do unlink "$root/$name"; done
       rmdir "$root"' bash "$remote_incoming" "${expected_files[@]}" || cleanup_rc=$?
  fi
  if [ -n "$remote_helper_root" ]; then
    cleanup_remote_exact_helper "$peer_host" "$remote_helper_root" || cleanup_rc=$?
  fi
  test "$cleanup_rc" = 0 || die "remote release import cleanup failed closed"
  test "$rc" = 0 || die "both-node release bundle installation failed"
  log "exact Quality Gates release bundle installed on node02 then node01"
}

install_lb_ready_attestation_cluster() {
  local attestation_path="$1"
  local operation="$2"
  local target_sha="$3"
  local attestation_sha="$4"
  local ready_projection_sha="$5"
  local journal_digest="$6"
  local confirmation="$7"
  local owner_confirmation="$8"
  local peer_host="$DEFAULT_PEER_HOST"
  local remote_helper_root remote_helper rc=0 cleanup_rc=0
  require_root
  case "$attestation_path" in
    /run/linasbot-lb-upload.????????) ;;
    *) die "cluster LB upload path is outside its exact volatile namespace" ;;
  esac
  test -f "$attestation_path" && test ! -L "$attestation_path" || \
    die "cluster LB upload is missing or unsafe"
  test "$(stat -c '%F:%u:%g:%a:%h' "$attestation_path")" = \
    "regular file:0:0:600:1" || die "cluster LB upload security is invalid"
  test "$(sha256sum "$attestation_path" | awk '{print $1}')" = "$attestation_sha" || \
    die "cluster LB upload differs from workflow authority"
  remote_helper_root="$(prepare_remote_exact_helper "$peer_host")"
  remote_helper="$remote_helper_root/deploy_meta_release_ha.sh"
  set +e
  ssh "${SSH_OPTIONS[@]}" "root@${peer_host}" \
    /usr/bin/env -i HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    /bin/bash --noprofile --norc "$remote_helper" install-lb-attestation \
    "$INTERNAL_NODE_DISPATCH_CONFIRM" node02 "$operation" "$target_sha" \
    "$attestation_sha" "$ready_projection_sha" "$journal_digest" "$confirmation" \
    "$owner_confirmation" <"$attestation_path"
  rc=$?
  set -e
  if [ "$rc" = 0 ]; then
    install_lb_ready_attestation node01 "$operation" "$target_sha" \
      "$attestation_sha" "$ready_projection_sha" "$journal_digest" \
      "$confirmation" "$owner_confirmation" <"$attestation_path" || rc=$?
  fi
  cleanup_remote_exact_helper "$peer_host" "$remote_helper_root" || cleanup_rc=$?
  test "$cleanup_rc" = 0 || die "remote LB installer cleanup failed closed"
  test "$rc" = 0 || die "both-node LB attestation installation failed"
  log "exact fresh LB attestation installed on node02 then node01"
}

extract_contract_value() {
  local name="$1"
  awk -F= -v name="$name" '$1 == name {print substr($0, length(name) + 2)}'
}

read_deploy_journal() {
  local expected_digest="$1"
  validate_digest "$expected_digest"
  test "$(deploy_journal_digest)" = "$expected_digest" || \
    die "deployment recovery journal digest differs from the owner-confirmed snapshot"
  run_system_python_control - "$DEPLOY_ACTIVE_FILE" <<'PY'
import json
import os
import re
import stat
import sys

path = sys.argv[1]
before = os.lstat(path)
if (
    not stat.S_ISREG(before.st_mode)
    or stat.S_ISLNK(before.st_mode)
    or before.st_uid != 0
    or before.st_gid != 0
    or stat.S_IMODE(before.st_mode) != 0o600
):
    raise SystemExit("deployment journal is unsafe")
fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    opened = os.fstat(fd)
    if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
        raise SystemExit("deployment journal changed while opened")
    payload = json.loads(os.read(fd, 65536))
finally:
    os.close(fd)
keys = {
    "schema", "tx_id", "target_sha", "node01_previous_sha", "node02_previous_sha",
    "peer_host", "tx_dir", "deploy_mode", "bootstrap_plan_sha256", "drain_seconds",
    "phase", "decision", "helper_sha256", "python_runtime_cluster_sha256",
    "lb_attestation_sha256", "lb_ready_projection_sha256", "lb_observed_at",
    "release_artifact_id", "release_artifact_api_sha256",
    "release_manifest_sha256", "release_run_id", "release_run_attempt",
    "release_target_tree_sha",
}
if set(payload) != keys or payload.get("schema") != 1:
    raise SystemExit("deployment journal schema is invalid")
if not re.fullmatch(r"[0-9a-f]{32}", str(payload.get("tx_id") or "")):
    raise SystemExit("deployment journal transaction ID is invalid")
for key in ("target_sha", "node01_previous_sha", "node02_previous_sha"):
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload.get(key) or "")):
        raise SystemExit("deployment journal SHA is invalid")
if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("helper_sha256") or "")):
    raise SystemExit("deployment journal helper digest is invalid")
if not re.fullmatch(
    r"[0-9a-f]{64}", str(payload.get("python_runtime_cluster_sha256") or "")
):
    raise SystemExit("deployment journal Python runtime cluster digest is invalid")
for key in ("lb_attestation_sha256", "lb_ready_projection_sha256"):
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(payload.get(key) or ""))
        or payload[key] == "0" * 64
    ):
        raise SystemExit("deployment journal LB attestation digest is invalid")
if not re.fullmatch(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z",
    str(payload.get("lb_observed_at") or ""),
):
    raise SystemExit("deployment journal LB observation time is invalid")
if (
    type(payload.get("release_artifact_id")) is not int
    or payload["release_artifact_id"] < 1
    or type(payload.get("release_run_id")) is not int
    or payload["release_run_id"] < 1
    or type(payload.get("release_run_attempt")) is not int
    or payload["release_run_attempt"] < 1
):
    raise SystemExit("deployment journal release artifact numeric identity is invalid")
for key in ("release_artifact_api_sha256", "release_manifest_sha256"):
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(payload.get(key) or ""))
        or payload[key] == "0" * 64
    ):
        raise SystemExit("deployment journal release artifact digest is invalid")
if not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("release_target_tree_sha") or "")):
    raise SystemExit("deployment journal release target tree is invalid")
if payload.get("peer_host") != "10.106.0.4" or payload.get("decision") not in {"rollback", "commit"}:
    raise SystemExit("deployment journal topology or decision is invalid")
if not re.fullmatch(
    rf"/var/backups/linasbot-ha/{payload['target_sha']}-[0-9]{{14}}-[0-9]+",
    str(payload.get("tx_dir") or ""),
):
    raise SystemExit("deployment journal transaction path is invalid")
if payload.get("deploy_mode") not in {"steady-confirmed", "reconcile"}:
    raise SystemExit("deployment journal mode is invalid")
bootstrap = str(payload.get("bootstrap_plan_sha256") or "")
if not re.fullmatch(r"[0-9a-f]{64}", bootstrap):
    raise SystemExit("deployment bootstrap digest is required")
if payload["deploy_mode"] == "steady-confirmed":
    if payload["node01_previous_sha"] != payload["node02_previous_sha"]:
        raise SystemExit("steady deployment journal contract is invalid")
elif payload["node01_previous_sha"] == payload["node02_previous_sha"]:
    raise SystemExit("reconciliation deployment journal contract is invalid")
if not isinstance(payload.get("drain_seconds"), int) or not 30 <= payload["drain_seconds"] <= 300:
    raise SystemExit("deployment journal drain interval is invalid")
if not re.fullmatch(r"[a-z0-9-]{3,64}", str(payload.get("phase") or "")):
    raise SystemExit("deployment journal phase is invalid")
for key in (
    "tx_id", "target_sha", "node01_previous_sha", "node02_previous_sha", "peer_host",
    "tx_dir", "deploy_mode", "bootstrap_plan_sha256", "drain_seconds", "phase",
    "decision", "helper_sha256", "python_runtime_cluster_sha256",
    "lb_attestation_sha256", "lb_ready_projection_sha256", "lb_observed_at",
    "release_artifact_id", "release_artifact_api_sha256",
    "release_manifest_sha256", "release_run_id", "release_run_attempt",
    "release_target_tree_sha",
):
    print(payload[key])
PY
}

recover_deployment() {
  local target_sha="$1"
  local expected_local_previous="$2"
  local expected_peer_previous="$3"
  local expected_journal_digest="$4"
  local recovery_confirmation="$5"
  local fresh_lb_attestation_sha="$6"
  local fresh_lb_projection_sha="$7"
  local lb_owner_confirmation="$8"
  local journal helper_hash expected_confirmation current_digest
  local tx_id journal_target previous_sha peer_previous_sha peer_host tx_dir deploy_mode
  local bootstrap_plan drain_seconds phase decision journal_helper journal_runtime_cluster
  local release_artifact_id release_artifact_api_sha release_manifest_sha
  local release_run_id release_run_attempt release_target_tree_sha
  local local_runtime_cluster peer_runtime_cluster transaction_succeeded=0
  local lb_observed_at peer_lb_observed_at
  validate_sha "$target_sha"
  validate_sha "$expected_local_previous"
  validate_sha "$expected_peer_previous"
  validate_digest "$expected_journal_digest"
  validate_digest "$fresh_lb_attestation_sha"
  validate_digest "$fresh_lb_projection_sha"
  test "$lb_owner_confirmation" = "I_HOLD_EXCLUSIVE_DO_LB_OWNER_UNTIL_DEPLOY_COMPLETE" || \
    die "exclusive DigitalOcean LB owner confirmation is missing"
  require_root
  acquire_meta_live_lock
  local_runtime_cluster="$(assert_python_runtime_contract node01)"
  mapfile -t journal < <(read_deploy_journal "$expected_journal_digest")
  test "${#journal[@]}" -eq 22 || die "deployment recovery journal output is incomplete"
  tx_id="${journal[0]}"
  journal_target="${journal[1]}"
  previous_sha="${journal[2]}"
  peer_previous_sha="${journal[3]}"
  peer_host="${journal[4]}"
  tx_dir="${journal[5]}"
  deploy_mode="${journal[6]}"
  bootstrap_plan="${journal[7]}"
  drain_seconds="${journal[8]}"
  phase="${journal[9]}"
  decision="${journal[10]}"
  journal_helper="${journal[11]}"
  journal_runtime_cluster="${journal[12]}"
  release_artifact_id="${journal[16]}"
  release_artifact_api_sha="${journal[17]}"
  release_manifest_sha="${journal[18]}"
  release_run_id="${journal[19]}"
  release_run_attempt="${journal[20]}"
  release_target_tree_sha="${journal[21]}"
  test "$journal_target" = "$target_sha" || die "recovery target differs from durable decision"
  test "$previous_sha" = "$expected_local_previous" || die "recovery node01 baseline differs"
  test "$peer_previous_sha" = "$expected_peer_previous" || die "recovery node02 baseline differs"
  test "$peer_host" = "$DEFAULT_PEER_HOST" || die "recovery peer is not fixed node02"
  validate_digest "$journal_runtime_cluster"
  test "$local_runtime_cluster" = "$journal_runtime_cluster" || \
    die "node01 Python runtime cluster certificate differs from the durable deployment"
  peer_runtime_cluster="$(remote_node "$peer_host" runtime-contract node02)"
  test "$peer_runtime_cluster" = "$journal_runtime_cluster" || \
    die "node02 Python runtime cluster certificate differs from the durable deployment"
  test "$(assert_release_bundle \
    "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
    "$release_manifest_sha" "$release_run_id" "$release_run_attempt")" = \
    "$(remote_node "$peer_host" release-bundle \
      "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
      "$release_manifest_sha" "$release_run_id" "$release_run_attempt")" || \
    die "recovery nodes do not share the durable Quality Gates release bundle"
  validate_tx_dir "$tx_dir"
  helper_hash="$(git -C "$REPO_DIR" show "$target_sha:$HELPER_REPO_PATH" | sha256sum | awk '{print $1}')"
  test "$helper_hash" = "$journal_helper" || die "recovery helper differs from durable transaction"
  test "$(sha256sum "$0" | awk '{print $1}')" = "$helper_hash" || \
    die "running recovery helper is not the exact authorized target blob"
  lb_observed_at="$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  peer_lb_observed_at="$(remote_node "$peer_host" lb-attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  test "$lb_observed_at" = "$peer_lb_observed_at" || \
    die "fixed HA nodes do not share the exact fresh LB attestation bytes"
  expected_confirmation="RECOVER_DEPLOY_${target_sha:0:16}_${expected_journal_digest:0:16}_LB_${fresh_lb_attestation_sha:0:16}_TO_${decision}"
  expected_confirmation="${expected_confirmation^^}"
  test "$recovery_confirmation" = "$expected_confirmation" || \
    die "exact digest-bound deployment recovery confirmation is missing"
  reject_self_peer "$peer_host"

  update_recovery_journal() {
    write_deploy_journal "$tx_id" "$target_sha" "$previous_sha" "$peer_previous_sha" \
      "$peer_host" "$tx_dir" "$deploy_mode" "$bootstrap_plan" "$drain_seconds" "$1" "$decision" \
      "$helper_hash" "$journal_runtime_cluster" "$fresh_lb_attestation_sha" \
      "$fresh_lb_projection_sha" "$lb_observed_at" \
      "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
      "$release_run_id" "$release_run_attempt" "$release_target_tree_sha"
  }
  fail_close_recovery() {
    local rc=$?
    trap - EXIT INT TERM
    if [ "$transaction_succeeded" != "1" ]; then
      set +e
      node_ensure_maintenance "$tx_dir" >/dev/null 2>&1
      remote_node "$peer_host" ensure-maintenance "$tx_dir" >/dev/null 2>&1
      log "recovery interrupted at durable decision=$decision; both nodes were forced fail-closed"
    fi
    exit "$rc"
  }
  trap fail_close_recovery EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  update_recovery_journal "recovery-lb-attested"
  update_recovery_journal "recovery-started"
  node_ensure_maintenance "$tx_dir"
  remote_node "$peer_host" ensure-maintenance "$tx_dir"
  sleep "$drain_seconds"
  if [ "$decision" = "commit" ]; then
    update_recovery_journal "commit-recovery-parity"
    node_assert_exact_head "$target_sha" "$tx_dir"
    remote_node "$peer_host" assert-head "$target_sha" "$tx_dir"
    node_assert_release_drained "$target_sha" "$tx_dir"
    remote_node "$peer_host" assert-drained "$target_sha" "$tx_dir"
    assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"
    assert_release_artifact_parity \
      "$peer_host" "$tx_dir" "$target_sha" "$previous_sha" "$peer_previous_sha"
    test "$(assert_fresh_lb_ready_attestation \
      "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")" = \
      "$lb_observed_at" || die "recovery LB attestation expired before commit admission"
    update_recovery_journal "commit-peer-admit"
    remote_node "$peer_host" recover-admit "$target_sha" "$tx_dir"
    assert_public_ready
    update_recovery_journal "commit-node01-admit"
    node_recover_admit "$target_sha" "$tx_dir"
    remote_node "$peer_host" assert-ready "$target_sha"
    node_assert_release_ready "$target_sha"
    /bin/bash --noprofile --norc \
      "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" "$target_sha" cluster
  else
    update_recovery_journal "rollback-restoring"
    node_recover_rollback "$previous_sha" "$tx_dir"
    remote_node "$peer_host" recover-rollback "$peer_previous_sha" "$tx_dir"
    node_assert_release_drained "$previous_sha" "$tx_dir"
    remote_node "$peer_host" assert-drained "$peer_previous_sha" "$tx_dir"
    if [ "$previous_sha" != "$peer_previous_sha" ]; then
      update_recovery_journal "distinct-rollback-drained"
      die "distinct exact baselines restored; both remain drained pending a newly confirmed reconciliation"
    fi
    assert_cluster_runtime_env_parity "$peer_host" "$previous_sha" "$target_sha"
    test "$(assert_fresh_lb_ready_attestation \
      "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")" = \
      "$lb_observed_at" || die "recovery LB attestation expired before rollback admission"
    update_recovery_journal "rollback-peer-admit"
    remote_node "$peer_host" recover-admit "$peer_previous_sha" "$tx_dir"
    assert_public_ready
    update_recovery_journal "rollback-node01-admit"
    node_recover_admit "$previous_sha" "$tx_dir"
    remote_node "$peer_host" assert-ready "$peer_previous_sha"
    node_assert_release_ready "$previous_sha"
  fi
  if [ "$decision" = "commit" ]; then
    assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"
  else
    assert_cluster_runtime_env_parity "$peer_host" "$previous_sha" "$target_sha"
  fi
  # Final serving proofs are terminal. Disarm fail-close before publishing the
  # terminal phase or deleting its journal; any later persistence/cleanup error
  # leaves an admitted cluster plus a replayable durable commit/rollback record.
  transaction_succeeded=1
  trap - EXIT INT TERM
  update_recovery_journal "complete"
  current_digest="$(deploy_journal_digest)"
  clear_deploy_journal "$current_digest"
  log "durable deployment decision=$decision recovered and verified on both nodes"
}

retry_distinct_reconciliation() {
  local target_sha="$1"
  local expected_local_previous="$2"
  local expected_peer_previous="$3"
  local expected_journal_digest="$4"
  local retry_confirmation="$5"
  local fresh_lb_attestation_sha="$6"
  local fresh_lb_projection_sha="$7"
  local lb_owner_confirmation="$8"
  local journal helper_hash expected_confirmation current_digest
  local tx_id journal_target previous_sha peer_previous_sha peer_host tx_dir deploy_mode
  local bootstrap_plan drain_seconds phase decision journal_helper journal_runtime_cluster
  local release_artifact_id release_artifact_api_sha release_manifest_sha
  local release_run_id release_run_attempt release_target_tree_sha
  local local_runtime_cluster peer_runtime_cluster transaction_succeeded=0
  local lb_observed_at peer_lb_observed_at
  validate_sha "$target_sha"
  validate_sha "$expected_local_previous"
  validate_sha "$expected_peer_previous"
  validate_digest "$expected_journal_digest"
  validate_digest "$fresh_lb_attestation_sha"
  validate_digest "$fresh_lb_projection_sha"
  test "$lb_owner_confirmation" = "I_HOLD_EXCLUSIVE_DO_LB_OWNER_UNTIL_DEPLOY_COMPLETE" || \
    die "exclusive DigitalOcean LB owner confirmation is missing"
  require_root
  acquire_meta_live_lock
  local_runtime_cluster="$(assert_python_runtime_contract node01)"
  mapfile -t journal < <(read_deploy_journal "$expected_journal_digest")
  test "${#journal[@]}" -eq 22 || die "deployment retry journal output is incomplete"
  tx_id="${journal[0]}"
  journal_target="${journal[1]}"
  previous_sha="${journal[2]}"
  peer_previous_sha="${journal[3]}"
  peer_host="${journal[4]}"
  tx_dir="${journal[5]}"
  deploy_mode="${journal[6]}"
  bootstrap_plan="${journal[7]}"
  drain_seconds="${journal[8]}"
  phase="${journal[9]}"
  decision="${journal[10]}"
  journal_helper="${journal[11]}"
  journal_runtime_cluster="${journal[12]}"
  release_artifact_id="${journal[16]}"
  release_artifact_api_sha="${journal[17]}"
  release_manifest_sha="${journal[18]}"
  release_run_id="${journal[19]}"
  release_run_attempt="${journal[20]}"
  release_target_tree_sha="${journal[21]}"
  test "$journal_target" = "$target_sha" || die "retry target differs from durable transaction"
  test "$previous_sha" = "$expected_local_previous" || die "retry node01 baseline differs"
  test "$peer_previous_sha" = "$expected_peer_previous" || die "retry node02 baseline differs"
  test "$previous_sha" != "$peer_previous_sha" || die "retry reconciliation requires distinct baselines"
  test "$peer_host" = "$DEFAULT_PEER_HOST" || die "retry peer is not fixed node02"
  validate_digest "$journal_runtime_cluster"
  test "$local_runtime_cluster" = "$journal_runtime_cluster" || \
    die "node01 Python runtime cluster certificate differs from the durable retry"
  peer_runtime_cluster="$(remote_node "$peer_host" runtime-contract node02)"
  test "$peer_runtime_cluster" = "$journal_runtime_cluster" || \
    die "node02 Python runtime cluster certificate differs from the durable retry"
  test "$(assert_release_bundle \
    "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
    "$release_manifest_sha" "$release_run_id" "$release_run_attempt")" = \
    "$(remote_node "$peer_host" release-bundle \
      "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
      "$release_manifest_sha" "$release_run_id" "$release_run_attempt")" || \
    die "retry nodes do not share the durable Quality Gates release bundle"
  test "$decision" = "rollback" || die "retry cannot override a durable commit decision"
  test "$phase" = "distinct-rollback-drained" || \
    die "retry is authorized only after exact distinct rollback parity is drained"
  validate_tx_dir "$tx_dir"
  helper_hash="$(git -C "$REPO_DIR" show "$target_sha:$HELPER_REPO_PATH" | sha256sum | awk '{print $1}')"
  test "$helper_hash" = "$journal_helper" || die "retry helper differs from durable transaction"
  test "$(sha256sum "$0" | awk '{print $1}')" = "$helper_hash" || \
    die "running retry helper is not the exact authorized target blob"
  lb_observed_at="$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  peer_lb_observed_at="$(remote_node "$peer_host" lb-attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  test "$lb_observed_at" = "$peer_lb_observed_at" || \
    die "fixed HA nodes do not share the exact fresh LB attestation bytes"
  expected_confirmation="RETRY_DEPLOY_${target_sha:0:16}_${expected_journal_digest:0:16}_LB_${fresh_lb_attestation_sha:0:16}_FROM_DISTINCT_DRAINED"
  test "$retry_confirmation" = "${expected_confirmation^^}" || \
    die "exact digest-bound distinct reconciliation retry confirmation is missing"
  reject_self_peer "$peer_host"

  update_retry_journal() {
    write_deploy_journal "$tx_id" "$target_sha" "$previous_sha" "$peer_previous_sha" \
      "$peer_host" "$tx_dir" "$deploy_mode" "$bootstrap_plan" "$drain_seconds" "$1" "$decision" \
      "$helper_hash" "$journal_runtime_cluster" "$fresh_lb_attestation_sha" \
      "$fresh_lb_projection_sha" "$lb_observed_at" \
      "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
      "$release_run_id" "$release_run_attempt" "$release_target_tree_sha"
  }
  refresh_retry_decision() {
    local digest
    local -a persisted=()
    digest="$(deploy_journal_digest)" || return 1
    mapfile -t persisted < <(read_deploy_journal "$digest")
    test "${#persisted[@]}" -eq 22 || return 1
    test "${persisted[0]}" = "$tx_id" || return 1
    test "${persisted[1]}" = "$target_sha" || return 1
    test "${persisted[2]}" = "$previous_sha" || return 1
    test "${persisted[3]}" = "$peer_previous_sha" || return 1
    test "${persisted[5]}" = "$tx_dir" || return 1
    test "${persisted[11]}" = "$helper_hash" || return 1
    test "${persisted[12]}" = "$journal_runtime_cluster" || return 1
    test "${persisted[13]}" = "$fresh_lb_attestation_sha" || return 1
    test "${persisted[14]}" = "$fresh_lb_projection_sha" || return 1
    test "${persisted[15]}" = "$lb_observed_at" || return 1
    test "${persisted[16]}" = "$release_artifact_id" || return 1
    test "${persisted[17]}" = "$release_artifact_api_sha" || return 1
    test "${persisted[18]}" = "$release_manifest_sha" || return 1
    test "${persisted[19]}" = "$release_run_id" || return 1
    test "${persisted[20]}" = "$release_run_attempt" || return 1
    test "${persisted[21]}" = "$release_target_tree_sha" || return 1
    decision="${persisted[10]}"
  }
  fail_close_retry() {
    local rc=$?
    local recovery_ok=1
    trap - EXIT INT TERM
    if [ "$transaction_succeeded" != "1" ]; then
      set +e
      node_ensure_maintenance "$tx_dir" >/dev/null 2>&1
      remote_node "$peer_host" ensure-maintenance "$tx_dir" >/dev/null 2>&1
      if ! refresh_retry_decision; then
        log "retry durable decision is unreadable; no rollback or admission is authorized"
        exit "$rc"
      fi
      if [ "$decision" = "rollback" ]; then
        sleep "$drain_seconds"
        node_recover_rollback "$previous_sha" "$tx_dir" >/dev/null 2>&1 || recovery_ok=0
        remote_node "$peer_host" recover-rollback \
          "$peer_previous_sha" "$tx_dir" >/dev/null 2>&1 || recovery_ok=0
        if [ "$recovery_ok" = "1" ]; then
          node_assert_exact_head "$previous_sha" "$tx_dir" >/dev/null 2>&1 || recovery_ok=0
          remote_node "$peer_host" assert-head \
            "$peer_previous_sha" "$tx_dir" >/dev/null 2>&1 || recovery_ok=0
          node_assert_release_drained "$previous_sha" "$tx_dir" >/dev/null 2>&1 || recovery_ok=0
          remote_node "$peer_host" assert-drained \
            "$peer_previous_sha" "$tx_dir" >/dev/null 2>&1 || recovery_ok=0
        fi
        if [ "$recovery_ok" = "1" ]; then
          update_retry_journal "distinct-rollback-drained" >/dev/null 2>&1 || recovery_ok=0
        fi
        if [ "$recovery_ok" != "1" ]; then
          update_retry_journal "rollback-uncertain" >/dev/null 2>&1 || true
        fi
      fi
      log "retry interrupted; durable decision=$decision and fail-closed recovery state were retained"
    fi
    exit "$rc"
  }
  trap fail_close_retry EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  update_retry_journal "retry-lb-attested"
  update_retry_journal "retry-preflight"
  node_ensure_maintenance "$tx_dir"
  remote_node "$peer_host" ensure-maintenance "$tx_dir"
  sleep "$drain_seconds"
  node_assert_exact_head "$previous_sha" "$tx_dir"
  remote_node "$peer_host" assert-head "$peer_previous_sha" "$tx_dir"
  node_assert_release_drained "$previous_sha" "$tx_dir"
  remote_node "$peer_host" assert-drained "$peer_previous_sha" "$tx_dir"
  update_retry_journal "retry-peer-stage"
  remote_node "$peer_host" retry-stage "$target_sha" "$peer_previous_sha" "$tx_dir" \
    "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
    "$release_run_id" "$release_run_attempt"
  update_retry_journal "retry-node01-stage"
  prepare_retry_stage "$target_sha" "$previous_sha" "$tx_dir" \
    "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
    "$release_run_id" "$release_run_attempt"
  assert_stage_artifact_parity \
    "$peer_host" "$tx_dir" "$target_sha" "$previous_sha" "$peer_previous_sha"
  update_retry_journal "retry-peer-activate"
  remote_node "$peer_host" activate "$target_sha" "$peer_previous_sha" "$tx_dir"
  remote_node "$peer_host" assert-drained "$target_sha" "$tx_dir"
  update_retry_journal "retry-node01-activate"
  node_activate "$target_sha" "$previous_sha" "$tx_dir"
  node_assert_release_drained "$target_sha" "$tx_dir"
  remote_node "$peer_host" assert-drained "$target_sha" "$tx_dir"
  assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"
  assert_release_artifact_parity \
    "$peer_host" "$tx_dir" "$target_sha" "$previous_sha" "$peer_previous_sha"

  update_retry_journal "target-parity-awaiting-fresh-lb"
  transaction_succeeded=1
  trap - EXIT INT TERM
  current_digest="$(deploy_journal_digest)"
  printf 'TARGET_PARITY_JOURNAL_SHA256=%s\n' "$current_digest"
  log "distinct baselines reached exact drained target parity; a new provider observation is required before commit"
}

deployment_recovery_status() {
  local target_sha="$1"
  local fresh_lb_attestation_sha="$2"
  local fresh_lb_projection_sha="$3"
  local lb_owner_confirmation="$4"
  local digest journal decision expected helper_hash local_runtime_cluster peer_runtime_cluster
  local lb_observed_at peer_lb_observed_at
  validate_sha "$target_sha"
  validate_digest "$fresh_lb_attestation_sha"
  validate_digest "$fresh_lb_projection_sha"
  test "$lb_owner_confirmation" = "I_HOLD_EXCLUSIVE_DO_LB_OWNER_UNTIL_DEPLOY_COMPLETE" || \
    die "exclusive DigitalOcean LB owner confirmation is missing"
  require_root
  acquire_meta_live_lock
  local_runtime_cluster="$(assert_python_runtime_contract node01)"
  digest="$(deploy_journal_digest)"
  mapfile -t journal < <(read_deploy_journal "$digest")
  test "${#journal[@]}" -eq 22 || die "deployment recovery journal output is incomplete"
  test "${journal[1]}" = "$target_sha" || die "recovery status target differs from durable transaction"
  decision="${journal[10]}"
  helper_hash="$(git -C "$REPO_DIR" show "$target_sha:$HELPER_REPO_PATH" | sha256sum | awk '{print $1}')"
  test "$helper_hash" = "${journal[11]}" || die "recovery status helper digest differs"
  test "$local_runtime_cluster" = "${journal[12]}" || \
    die "node01 Python runtime cluster certificate differs from the durable deployment"
  peer_runtime_cluster="$(remote_node "${journal[4]}" runtime-contract node02)"
  test "$peer_runtime_cluster" = "${journal[12]}" || \
    die "node02 Python runtime cluster certificate differs from the durable deployment"
  test "$(assert_release_bundle \
    "$target_sha" "${journal[16]}" "${journal[17]}" "${journal[18]}" \
    "${journal[19]}" "${journal[20]}")" = \
    "$(remote_node "${journal[4]}" release-bundle \
      "$target_sha" "${journal[16]}" "${journal[17]}" "${journal[18]}" \
      "${journal[19]}" "${journal[20]}")" || \
    die "recovery status nodes do not share the durable Quality Gates release bundle"
  lb_observed_at="$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  peer_lb_observed_at="$(remote_node "${journal[4]}" lb-attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  test "$lb_observed_at" = "$peer_lb_observed_at" || \
    die "fixed HA nodes do not share the exact fresh LB attestation bytes"
  test "$(sha256sum "$0" | awk '{print $1}')" = "$helper_hash" || \
    die "running recovery-status helper is not the exact authorized target blob"
  expected="RECOVER_DEPLOY_${target_sha:0:16}_${digest:0:16}_LB_${fresh_lb_attestation_sha:0:16}_TO_${decision}"
  printf 'TARGET_SHA=%s\nNODE01_PREVIOUS_SHA=%s\nNODE02_PREVIOUS_SHA=%s\n' \
    "$target_sha" "${journal[2]}" "${journal[3]}"
  printf 'JOURNAL_SHA256=%s\nDECISION=%s\nPHASE=%s\nCONFIRMATION=%s\n' \
    "$digest" "$decision" "${journal[9]}" "${expected^^}"
  if [ "$decision" = "rollback" ] && [ "${journal[2]}" != "${journal[3]}" ] && \
     [ "${journal[9]}" = "distinct-rollback-drained" ]; then
    expected="RETRY_DEPLOY_${target_sha:0:16}_${digest:0:16}_LB_${fresh_lb_attestation_sha:0:16}_FROM_DISTINCT_DRAINED"
    printf 'RETRY_CONFIRMATION=%s\n' "${expected^^}"
  fi
  if [ "$decision" = rollback ] && \
     [ "${journal[9]}" = "target-parity-awaiting-fresh-lb" ]; then
    expected="COMMIT_DEPLOY_${target_sha:0:16}_${digest:0:16}_LB_${fresh_lb_attestation_sha:0:16}_FROM_TARGET_PARITY"
    printf 'COMMIT_CONFIRMATION=%s\n' "${expected^^}"
  fi
}

commit_target_deployment() {
  local target_sha="$1"
  local expected_journal_digest="$2"
  local commit_confirmation="$3"
  local fresh_lb_attestation_sha="$4"
  local fresh_lb_projection_sha="$5"
  local lb_owner_confirmation="$6"
  local -a journal=()
  local tx_id previous_sha peer_previous_sha peer_host tx_dir deploy_mode bootstrap_plan
  local drain_seconds phase decision helper_hash journal_runtime_cluster
  local previous_lb_attestation_sha previous_lb_projection_sha previous_lb_observed_at
  local release_artifact_id release_artifact_api_sha release_manifest_sha
  local release_run_id release_run_attempt release_target_tree_sha
  local local_runtime_cluster peer_runtime_cluster release_summary peer_release_summary
  local lb_observed_at peer_lb_observed_at expected_confirmation current_digest
  local transaction_succeeded=0
  validate_sha "$target_sha"
  validate_digest "$expected_journal_digest"
  validate_digest "$fresh_lb_attestation_sha"
  validate_digest "$fresh_lb_projection_sha"
  test "$lb_owner_confirmation" = "I_HOLD_EXCLUSIVE_DO_LB_OWNER_UNTIL_DEPLOY_COMPLETE" || \
    die "exclusive DigitalOcean LB owner confirmation is missing"
  require_root
  acquire_meta_live_lock
  local_runtime_cluster="$(assert_python_runtime_contract node01)"
  mapfile -t journal < <(read_deploy_journal "$expected_journal_digest")
  test "${#journal[@]}" -eq 22 || die "deployment commit journal output is incomplete"
  tx_id="${journal[0]}"
  test "${journal[1]}" = "$target_sha" || die "commit target differs from durable transaction"
  previous_sha="${journal[2]}"
  peer_previous_sha="${journal[3]}"
  peer_host="${journal[4]}"
  tx_dir="${journal[5]}"
  deploy_mode="${journal[6]}"
  bootstrap_plan="${journal[7]}"
  drain_seconds="${journal[8]}"
  phase="${journal[9]}"
  decision="${journal[10]}"
  helper_hash="${journal[11]}"
  journal_runtime_cluster="${journal[12]}"
  previous_lb_attestation_sha="${journal[13]}"
  previous_lb_projection_sha="${journal[14]}"
  previous_lb_observed_at="${journal[15]}"
  release_artifact_id="${journal[16]}"
  release_artifact_api_sha="${journal[17]}"
  release_manifest_sha="${journal[18]}"
  release_run_id="${journal[19]}"
  release_run_attempt="${journal[20]}"
  release_target_tree_sha="${journal[21]}"
  test "$phase" = "target-parity-awaiting-fresh-lb" || \
    die "commit is authorized only from durable drained target parity"
  test "$decision" = rollback || die "commit cannot replace a durable deployment decision"
  test "$peer_host" = "$DEFAULT_PEER_HOST" || die "commit peer is not fixed node02"
  validate_tx_dir "$tx_dir"
  test "$fresh_lb_projection_sha" = "$previous_lb_projection_sha" || \
    die "commit LB projection differs from the reviewed deploy projection"
  test "$fresh_lb_attestation_sha" != "$previous_lb_attestation_sha" || \
    die "commit requires a distinct provider observation"
  test "$local_runtime_cluster" = "$journal_runtime_cluster" || \
    die "node01 Python runtime cluster certificate differs from the durable deployment"
  peer_runtime_cluster="$(remote_node "$peer_host" runtime-contract node02)"
  test "$peer_runtime_cluster" = "$journal_runtime_cluster" || \
    die "node02 Python runtime cluster certificate differs from the durable deployment"
  test "$(sha256sum "$0" | awk '{print $1}')" = "$helper_hash" || \
    die "running commit helper differs from the durable transaction"
  test "$(git -C "$REPO_DIR" show "$target_sha:$HELPER_REPO_PATH" | sha256sum | awk '{print $1}')" = \
    "$helper_hash" || die "canonical target helper differs from the durable transaction"
  release_summary="$(assert_release_bundle \
    "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
    "$release_manifest_sha" "$release_run_id" "$release_run_attempt")"
  peer_release_summary="$(remote_node "$peer_host" release-bundle \
    "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
    "$release_manifest_sha" "$release_run_id" "$release_run_attempt")"
  test "$release_summary" = "$peer_release_summary" || \
    die "commit nodes do not share the durable Quality Gates release bundle"
  test "$(run_system_python_control -c \
    'import json,sys; print(json.loads(sys.argv[1])["source_bundle"]["target_tree_sha"])' \
    "$release_summary")" = "$release_target_tree_sha" || \
    die "commit release tree differs from the durable workflow authority"
  lb_observed_at="$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  peer_lb_observed_at="$(remote_node "$peer_host" lb-attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")"
  test "$lb_observed_at" = "$peer_lb_observed_at" || \
    die "fixed HA nodes do not share the exact fresh commit LB attestation"
  assert_lb_observation_strictly_newer "$previous_lb_observed_at" "$lb_observed_at"
  expected_confirmation="COMMIT_DEPLOY_${target_sha:0:16}_${expected_journal_digest:0:16}_LB_${fresh_lb_attestation_sha:0:16}_FROM_TARGET_PARITY"
  test "$commit_confirmation" = "${expected_confirmation^^}" || \
    die "exact journal- and provider-bound deployment commit confirmation is missing"

  update_commit_journal() {
    local next_phase="$1"
    local next_decision="$2"
    write_deploy_journal "$tx_id" "$target_sha" "$previous_sha" "$peer_previous_sha" \
      "$peer_host" "$tx_dir" "$deploy_mode" "$bootstrap_plan" "$drain_seconds" \
      "$next_phase" "$next_decision" "$helper_hash" "$journal_runtime_cluster" \
      "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha" "$lb_observed_at" \
      "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
      "$release_run_id" "$release_run_attempt" "$release_target_tree_sha"
  }
  assert_commit_journal() {
    local expected_phase="$1"
    local expected_decision="$2"
    local -a persisted=()
    current_digest="$(deploy_journal_digest)"
    mapfile -t persisted < <(read_deploy_journal "$current_digest")
    test "${#persisted[@]}" -eq 22 || return 1
    test "${persisted[0]}" = "$tx_id" || return 1
    test "${persisted[1]}" = "$target_sha" || return 1
    test "${persisted[5]}" = "$tx_dir" || return 1
    test "${persisted[9]}" = "$expected_phase" || return 1
    test "${persisted[10]}" = "$expected_decision" || return 1
    test "${persisted[11]}" = "$helper_hash" || return 1
    test "${persisted[12]}" = "$journal_runtime_cluster" || return 1
    test "${persisted[13]}" = "$fresh_lb_attestation_sha" || return 1
    test "${persisted[14]}" = "$fresh_lb_projection_sha" || return 1
    test "${persisted[15]}" = "$lb_observed_at" || return 1
    test "${persisted[16]}" = "$release_artifact_id" || return 1
    test "${persisted[17]}" = "$release_artifact_api_sha" || return 1
    test "${persisted[18]}" = "$release_manifest_sha" || return 1
    test "${persisted[19]}" = "$release_run_id" || return 1
    test "${persisted[20]}" = "$release_run_attempt" || return 1
    test "${persisted[21]}" = "$release_target_tree_sha" || return 1
  }
  fail_close_commit() {
    local rc=$?
    trap - EXIT INT TERM
    if [ "$transaction_succeeded" != 1 ]; then
      set +e
      node_ensure_maintenance "$tx_dir" >/dev/null 2>&1
      remote_node "$peer_host" ensure-maintenance "$tx_dir" >/dev/null 2>&1
      log "commit interrupted; durable journal was retained and both nodes remain fail-closed"
    fi
    exit "$rc"
  }
  trap fail_close_commit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  update_commit_journal "commit-lb-attested" rollback
  assert_commit_journal "commit-lb-attested" rollback || \
    die "fresh commit LB authority was not durably read back"
  node_ensure_maintenance "$tx_dir"
  remote_node "$peer_host" ensure-maintenance "$tx_dir"
  node_assert_exact_head "$target_sha" "$tx_dir"
  remote_node "$peer_host" assert-head "$target_sha" "$tx_dir"
  node_assert_release_drained "$target_sha" "$tx_dir"
  remote_node "$peer_host" assert-drained "$target_sha" "$tx_dir"
  assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"
  assert_release_artifact_parity \
    "$peer_host" "$tx_dir" "$target_sha" "$previous_sha" "$peer_previous_sha"
  test "$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")" = \
    "$lb_observed_at" || die "commit LB attestation expired before durable decision"

  update_commit_journal "target-parity-proven" commit
  assert_commit_journal "target-parity-proven" commit || \
    die "durable deployment commit was not read back"
  test "$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")" = \
    "$lb_observed_at" || die "commit LB attestation expired before peer admission"
  update_commit_journal "peer-admit-started" commit
  remote_node "$peer_host" recover-admit "$target_sha" "$tx_dir"
  assert_public_ready
  test "$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$fresh_lb_attestation_sha" "$fresh_lb_projection_sha")" = \
    "$lb_observed_at" || die "commit LB attestation expired before node01 admission"
  update_commit_journal "node01-admit-started" commit
  node_recover_admit "$target_sha" "$tx_dir"
  remote_node "$peer_host" assert-ready "$target_sha"
  node_assert_release_ready "$target_sha"
  assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"
  /bin/bash --noprofile --norc \
    "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" "$target_sha" cluster
  write_private_state "$tx_dir/transaction.state" succeeded
  transaction_succeeded=1
  trap - EXIT INT TERM
  update_commit_journal complete commit
  assert_commit_journal complete commit || die "terminal deployment proof was not durable"
  clear_deploy_journal "$current_digest"
  log "exact authorized release committed and verified on both nodes; backups retained at $tx_dir"
}

orchestrate() {
  local target_sha="$1"
  local deploy_mode="${2:-steady-confirmed}"
  local expected_local_previous="${3:-}"
  local expected_peer_previous="${4:-}"
  local expected_bootstrap_plan="${5:-}"
  local reconcile_confirmation="${6:-}"
  local deploy_confirmation="${7:-}"
  local lb_attestation_sha="${8:-}"
  local lb_ready_projection_sha="${9:-}"
  local lb_owner_confirmation="${10:-}"
  local release_artifact_id="${11:-}"
  local release_artifact_api_sha="${12:-}"
  local release_manifest_sha="${13:-}"
  local release_run_id="${14:-}"
  local release_run_attempt="${15:-}"
  local release_target_tree_sha="${16:-}"
  local helper_hash local_preflight peer_preflight
  local local_baseline_artifacts peer_baseline_artifacts
  local previous_sha peer_previous_sha drain_seconds peer_drain_seconds
  local python_runtime_cluster_sha local_preflight_runtime_cluster_sha
  local peer_python_runtime_cluster_sha
  local lb_observed_at peer_lb_observed_at
  local release_summary peer_release_summary
  local configured_peer peer_host tx_stamp tx_dir
  local local_preflight_rc peer_preflight_rc
  local tx_id current_journal_digest durable_decision=rollback
  local transaction_started=0 transaction_succeeded=0 rollback_ok=1 commit_decided=0
  validate_sha "$target_sha"
  validate_digest "$lb_attestation_sha"
  validate_digest "$lb_ready_projection_sha"
  [[ "$release_artifact_id" =~ ^[1-9][0-9]*$ ]] || die "release artifact ID is invalid"
  validate_digest "$release_artifact_api_sha"
  validate_digest "$release_manifest_sha"
  [[ "$release_run_id" =~ ^[1-9][0-9]*$ ]] || die "release Quality Gates run ID is invalid"
  [[ "$release_run_attempt" =~ ^[1-9][0-9]*$ ]] || \
    die "release Quality Gates attempt is invalid"
  validate_sha "$release_target_tree_sha"
  test "$lb_owner_confirmation" = "I_HOLD_EXCLUSIVE_DO_LB_OWNER_UNTIL_DEPLOY_COMPLETE" || \
    die "exclusive DigitalOcean LB owner confirmation is missing"
  test "$deploy_confirmation" = \
    "DEPLOY_${target_sha}_LB_${lb_attestation_sha:0:16}_WITH_HA_PREFLIGHT_BACKUPS_AND_ROLLBACK" || \
    die "exact-SHA preflight/backup/drain/rollback confirmation is required"
  case "$deploy_mode" in
    steady-confirmed)
      validate_sha "$expected_local_previous"
      validate_sha "$expected_peer_previous"
      validate_digest "$expected_bootstrap_plan"
      test "$expected_local_previous" = "$expected_peer_previous" || \
        die "steady deployment requires one explicitly confirmed equal baseline"
      test -z "$reconcile_confirmation" || \
        die "steady deployment does not accept a reconciliation confirmation"
      ;;
    reconcile)
      validate_sha "$expected_local_previous"
      validate_sha "$expected_peer_previous"
      validate_digest "$expected_bootstrap_plan"
      test "$expected_local_previous" != "$expected_peer_previous" || \
        die "reconciliation mode is only for explicitly distinct node baselines"
      test "$reconcile_confirmation" = "I_UNDERSTAND_RECONCILING_DISTINCT_HA_BASELINES" || \
        die "explicit distinct-baseline reconciliation confirmation is required"
      ;;
    *)
      die "deployment mode is invalid"
      ;;
  esac
  require_root
  acquire_meta_live_lock
  python_runtime_cluster_sha="$(assert_python_runtime_contract node01)"
  release_summary="$(assert_release_bundle \
    "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
    "$release_manifest_sha" "$release_run_id" "$release_run_attempt")"
  peer_release_summary="$(remote_node "$DEFAULT_PEER_HOST" release-bundle \
    "$target_sha" "$release_artifact_id" "$release_artifact_api_sha" \
    "$release_manifest_sha" "$release_run_id" "$release_run_attempt")"
  test "$release_summary" = "$peer_release_summary" || \
    die "fixed HA nodes do not share the exact protected Quality Gates release bundle"
  test "$(run_system_python_control -c \
    'import json,sys; print(json.loads(sys.argv[1])["source_bundle"]["target_tree_sha"])' \
    "$release_summary")" = "$release_target_tree_sha" || \
    die "release target tree differs from workflow authority"
  helper_hash="$(git -C "$REPO_DIR" show "$target_sha:$HELPER_REPO_PATH" | sha256sum | awk '{print $1}')"
  if [ -f "$0" ]; then
    test "$(sha256sum "$0" | awk '{print $1}')" = "$helper_hash" || \
      die "running helper is not the exact authorized target blob"
  fi

  # Never trust a canonical .env that has not passed the root:root 0600 audit
  # to select a root SSH destination. The root operator may override this process
  # environment; otherwise the fixed private node02 address is used.
  peer_host="${LINAS_HA_PEER_HOST:-$DEFAULT_PEER_HOST}"
  test -n "$peer_host" || die "HA peer host is not configured"
  reject_self_peer "$peer_host"

  # Run both read-only node audits even when the first node has blockers. This
  # produces one complete owner remediation set without crossing the mutation boundary.
  set +e
  local_preflight="$(node_preflight "$target_sha" node01 "$helper_hash" \
    "$expected_bootstrap_plan" "$lb_attestation_sha" "$lb_ready_projection_sha")"
  local_preflight_rc=$?
  peer_preflight="$(
    remote_node "$peer_host" preflight "$target_sha" node02 "$helper_hash" \
      "$expected_bootstrap_plan" "$lb_attestation_sha" "$lb_ready_projection_sha"
  )"
  peer_preflight_rc=$?
  set -e
  if [ "$local_preflight_rc" -ne 0 ] || [ "$peer_preflight_rc" -ne 0 ]; then
    die "both-node preflight failed; no release, service, or admission mutation was attempted"
  fi
  previous_sha="$(printf '%s\n' "$local_preflight" | extract_contract_value PREVIOUS_SHA)"
  drain_seconds="$(printf '%s\n' "$local_preflight" | extract_contract_value DRAIN_SECONDS)"
  configured_peer="$(printf '%s\n' "$local_preflight" | extract_contract_value CONFIGURED_PEER)"
  if [ -n "$configured_peer" ] && [ "$configured_peer" != "$peer_host" ]; then
    die "secure canonical peer configuration differs from the selected root SSH peer"
  fi
  peer_previous_sha="$(printf '%s\n' "$peer_preflight" | extract_contract_value PREVIOUS_SHA)"
  peer_drain_seconds="$(printf '%s\n' "$peer_preflight" | extract_contract_value DRAIN_SECONDS)"
  local_preflight_runtime_cluster_sha="$(
    printf '%s\n' "$local_preflight" | extract_contract_value PYTHON_RUNTIME_CLUSTER_SHA
  )"
  peer_python_runtime_cluster_sha="$(
    printf '%s\n' "$peer_preflight" | extract_contract_value PYTHON_RUNTIME_CLUSTER_SHA
  )"
  validate_digest "$local_preflight_runtime_cluster_sha"
  validate_digest "$peer_python_runtime_cluster_sha"
  test "$python_runtime_cluster_sha" = "$local_preflight_runtime_cluster_sha" || \
    die "node01 Python runtime receipt changed inside the locked preflight"
  test "$python_runtime_cluster_sha" = "$peer_python_runtime_cluster_sha" || \
    die "nodes do not share one committed Python runtime cluster certificate"
  test "$(printf '%s\n' "$local_preflight" | extract_contract_value BOOTSTRAP_PLAN_SHA)" = \
    "$expected_bootstrap_plan" || die "node01 bootstrap commit proof is missing"
  test "$(printf '%s\n' "$peer_preflight" | extract_contract_value BOOTSTRAP_PLAN_SHA)" = \
    "$expected_bootstrap_plan" || die "node02 bootstrap commit proof is missing"
  lb_observed_at="$(
    printf '%s\n' "$local_preflight" | extract_contract_value LB_ATTESTATION_OBSERVED_AT
  )"
  peer_lb_observed_at="$(
    printf '%s\n' "$peer_preflight" | extract_contract_value LB_ATTESTATION_OBSERVED_AT
  )"
  test -n "$lb_observed_at" && test "$lb_observed_at" = "$peer_lb_observed_at" || \
    die "fixed HA nodes do not share one exact fresh DigitalOcean LB attestation"
  local_baseline_artifacts="$(
    printf '%s\n' "$local_preflight" | extract_contract_value BASELINE_ARTIFACT_EVIDENCE
  )"
  peer_baseline_artifacts="$(
    printf '%s\n' "$peer_preflight" | extract_contract_value BASELINE_ARTIFACT_EVIDENCE
  )"
  test -n "$local_baseline_artifacts" && test -n "$peer_baseline_artifacts" || \
    die "both-node baseline artifact preflight evidence is missing"
  assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"
  if [ "$deploy_mode" = "steady-confirmed" ]; then
    test "$previous_sha" = "$peer_previous_sha" || die "nodes do not share one previous SHA"
    test "$previous_sha" = "$expected_local_previous" || \
      die "node01 baseline differs from the explicitly confirmed steady SHA"
    test "$peer_previous_sha" = "$expected_peer_previous" || \
      die "node02 baseline differs from the explicitly confirmed steady SHA"
    test "$local_baseline_artifacts" = "$peer_baseline_artifacts" || \
      die "steady HA baselines have divergent venv, dashboard, nginx, or systemd bytes"
  else
    test "$previous_sha" = "$expected_local_previous" || \
      die "node01 baseline differs from the explicitly authorized reconciliation SHA"
    test "$peer_previous_sha" = "$expected_peer_previous" || \
      die "node02 baseline differs from the explicitly authorized reconciliation SHA"
  fi
  test "$drain_seconds" = "$peer_drain_seconds" || die "nodes do not share one approved drain interval"
  validate_sha "$previous_sha"
  validate_sha "$peer_previous_sha"
  if [ "$target_sha" = "$previous_sha" ] && [ "$target_sha" = "$peer_previous_sha" ]; then
    log "authorized target already runs on both nodes; no deployment needed"
    return 0
  fi

  tx_stamp="$(date -u +%Y%m%d%H%M%S)"
  tx_dir="$BACKUP_ROOT/${target_sha}-${tx_stamp}-$$"
  validate_tx_dir "$tx_dir"
  tx_id="$(run_system_python_control -c 'import secrets; print(secrets.token_hex(16))')"
  update_deploy_journal() {
    write_deploy_journal "$tx_id" "$target_sha" "$previous_sha" "$peer_previous_sha" \
      "$peer_host" "$tx_dir" "$deploy_mode" "$expected_bootstrap_plan" "$drain_seconds" "$1" \
      "$durable_decision" "$helper_hash" "$python_runtime_cluster_sha" \
      "$lb_attestation_sha" "$lb_ready_projection_sha" "$lb_observed_at" \
      "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
      "$release_run_id" "$release_run_attempt" "$release_target_tree_sha"
  }
  refresh_durable_decision() {
    local digest
    local -a persisted=()
    digest="$(deploy_journal_digest)" || return 1
    mapfile -t persisted < <(read_deploy_journal "$digest")
    test "${#persisted[@]}" -eq 22 || return 1
    test "${persisted[0]}" = "$tx_id" || return 1
    test "${persisted[1]}" = "$target_sha" || return 1
    test "${persisted[2]}" = "$previous_sha" || return 1
    test "${persisted[3]}" = "$peer_previous_sha" || return 1
    test "${persisted[4]}" = "$peer_host" || return 1
    test "${persisted[5]}" = "$tx_dir" || return 1
    test "${persisted[11]}" = "$helper_hash" || return 1
    test "${persisted[12]}" = "$python_runtime_cluster_sha" || return 1
    test "${persisted[13]}" = "$lb_attestation_sha" || return 1
    test "${persisted[14]}" = "$lb_ready_projection_sha" || return 1
    test "${persisted[15]}" = "$lb_observed_at" || return 1
    test "${persisted[16]}" = "$release_artifact_id" || return 1
    test "${persisted[17]}" = "$release_artifact_api_sha" || return 1
    test "${persisted[18]}" = "$release_manifest_sha" || return 1
    test "${persisted[19]}" = "$release_run_id" || return 1
    test "${persisted[20]}" = "$release_run_attempt" || return 1
    test "${persisted[21]}" = "$release_target_tree_sha" || return 1
    durable_decision="${persisted[10]}"
    if [ "$durable_decision" = "commit" ]; then
      commit_decided=1
    else
      commit_decided=0
    fi
  }
  update_deploy_journal "preflight-proven"
  rollback_transaction() {
    local reason_rc="$1"
    set +e
    if ! refresh_durable_decision; then
      node_ensure_maintenance "$tx_dir" >/dev/null 2>&1 || true
      remote_node "$peer_host" ensure-maintenance "$tx_dir" >/dev/null 2>&1 || true
      log "DURABLE DEPLOYMENT DECISION IS UNREADABLE; no rollback or admission is authorized"
      return 1
    fi
    if [ "$commit_decided" = "1" ]; then
      update_deploy_journal "commit-interrupted" || true
      node_ensure_maintenance "$tx_dir" >/dev/null 2>&1 || true
      remote_node "$peer_host" ensure-maintenance "$tx_dir" >/dev/null 2>&1 || true
      log "durable commit decision was already recorded; recovery must finish forward, never roll back"
      return 1
    fi
    update_deploy_journal "automatic-rollback" || rollback_ok=0
    log "deployment failed (rc=$reason_rc); enforcing fail-closed rollback"
    node_ensure_maintenance "$tx_dir" || rollback_ok=0
    remote_node "$peer_host" ensure-maintenance "$tx_dir" || rollback_ok=0
    if [ "$rollback_ok" = "1" ]; then
      sleep "$drain_seconds"
      rollback_impl "$previous_sha" "$tx_dir" || rollback_ok=0
      remote_node "$peer_host" rollback "$peer_previous_sha" "$tx_dir" || rollback_ok=0
    fi
    if [ "$rollback_ok" = "1" ]; then
      node_assert_release_drained "$previous_sha" "$tx_dir" || rollback_ok=0
      remote_node "$peer_host" assert-drained "$peer_previous_sha" "$tx_dir" || rollback_ok=0
    fi
    if [ "$rollback_ok" = "1" ] && [ "$previous_sha" != "$peer_previous_sha" ]; then
      update_deploy_journal "distinct-rollback-drained" || true
      log "distinct per-node baselines were restored exactly; both remain drained to prevent mixed-SHA serving"
      return 1
    fi
    if [ "$rollback_ok" = "1" ]; then
      assert_cluster_runtime_env_parity "$peer_host" "$previous_sha" "$target_sha" || rollback_ok=0
    fi
    if [ "$rollback_ok" = "1" ]; then
      remote_node "$peer_host" clear-maintenance "$tx_dir" || rollback_ok=0
      node_clear_maintenance "$tx_dir" || rollback_ok=0
    fi
    if [ "$rollback_ok" = "1" ]; then
      node_assert_release_ready "$previous_sha" || rollback_ok=0
      remote_node "$peer_host" assert-ready "$peer_previous_sha" || rollback_ok=0
      assert_cluster_runtime_env_parity "$peer_host" "$previous_sha" "$target_sha" || rollback_ok=0
    fi
    if [ "$rollback_ok" != "1" ]; then
      update_deploy_journal "rollback-uncertain" || true
      log "ROLLBACK PARITY IS UNCERTAIN; maintenance remains fail-closed for owner recovery"
      node_ensure_maintenance "$tx_dir" >/dev/null 2>&1 || true
      remote_node "$peer_host" ensure-maintenance "$tx_dir" >/dev/null 2>&1 || true
      return 1
    fi
    update_deploy_journal "rollback-complete" || return 1
    current_journal_digest="$(deploy_journal_digest)" || return 1
    clear_deploy_journal "$current_journal_digest" || return 1
    log "automatic rollback restored both nodes to their exact authorized baseline"
    return 0
  }

  on_exit() {
    local rc=$?
    trap - EXIT INT TERM
    if [ "$transaction_started" = "1" ] && [ "$transaction_succeeded" != "1" ]; then
      rollback_transaction "$rc" || exit 1
    fi
    exit "$rc"
  }
  trap on_exit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  transaction_started=1
  log "both-node preflight passed at node01=$previous_sha node02=$peer_previous_sha"
  test "$(assert_fresh_lb_ready_attestation \
    "$target_sha" "$lb_attestation_sha" "$lb_ready_projection_sha")" = "$lb_observed_at" || \
    die "node01 LB attestation changed at the first mutation boundary"
  test "$(remote_node "$peer_host" lb-attestation \
    "$target_sha" "$lb_attestation_sha" "$lb_ready_projection_sha")" = "$lb_observed_at" || \
    die "node02 LB attestation changed at the first mutation boundary"
  log "withdrawing peer before peer-first staging"
  update_deploy_journal "peer-mark-started"
  remote_node "$peer_host" mark-maintenance "$tx_dir"
  update_deploy_journal "peer-marked"
  node_assert_release_ready "$previous_sha"
  assert_public_ready
  sleep "$drain_seconds"
  remote_node "$peer_host" assert-drained "$peer_previous_sha" "$tx_dir"
  node_assert_release_ready "$previous_sha"
  assert_public_ready
  log "staging peer first with recoverable mode-600 backup archives"
  update_deploy_journal "peer-stage-started"
  remote_node "$peer_host" stage "$target_sha" "$peer_previous_sha" "$tx_dir" \
    "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
    "$release_run_id" "$release_run_attempt"
  update_deploy_journal "peer-staged"
  log "staging node01 without mutating its live runtime"
  update_deploy_journal "node01-stage-started"
  backup_live_node "$target_sha" "$previous_sha" "$tx_dir" \
    "$release_artifact_id" "$release_artifact_api_sha" "$release_manifest_sha" \
    "$release_run_id" "$release_run_attempt"
  update_deploy_journal "node01-staged"
  assert_stage_artifact_parity \
    "$peer_host" "$tx_dir" "$target_sha" "$previous_sha" "$peer_previous_sha"
  log "activating exact target on drained peer"
  update_deploy_journal "peer-activate-started"
  remote_node "$peer_host" activate "$target_sha" "$peer_previous_sha" "$tx_dir"
  update_deploy_journal "peer-activated"
  remote_node "$peer_host" assert-drained "$target_sha" "$tx_dir"
  node_assert_release_ready "$previous_sha"
  assert_public_ready

  log "withdrawing node01; owner-approved brief all-node maintenance begins"
  update_deploy_journal "node01-mark-started"
  node_mark_maintenance "$tx_dir"
  update_deploy_journal "node01-marked"
  sleep "$drain_seconds"
  log "activating exact target on drained node01"
  update_deploy_journal "node01-activate-started"
  node_activate "$target_sha" "$previous_sha" "$tx_dir"
  update_deploy_journal "node01-activated"
  remote_node "$peer_host" assert-drained "$target_sha" "$tx_dir"
  node_assert_release_drained "$target_sha" "$tx_dir"
  assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"
  assert_release_artifact_parity \
    "$peer_host" "$tx_dir" "$target_sha" "$previous_sha" "$peer_previous_sha"

  update_deploy_journal "target-parity-awaiting-fresh-lb"
  transaction_succeeded=1
  trap - EXIT INT TERM
  current_journal_digest="$(deploy_journal_digest)"
  printf 'TARGET_PARITY_JOURNAL_SHA256=%s\n' "$current_journal_digest"
  log "exact target parity is durable and both nodes remain drained pending a new provider observation"
}

case "${1:-}" in
  install-release-bundle)
    require_internal_node_dispatch "${2:-}"
    install_release_bundle \
      "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}" "${8:-}" \
      "${9:-}" "${10:-}" "${11:-}" "${12:-}" "${13:-}" "${14:-}"
    ;;
  install-release-bundle-cluster)
    install_release_bundle_cluster \
      "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}" \
      "${8:-}" "${9:-}" "${10:-}" "${11:-}" "${12:-}"
    ;;
  install-lb-attestation)
    require_internal_node_dispatch "${2:-}"
    install_lb_ready_attestation \
      "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}" "${8:-}" "${9:-}" "${10:-}"
    ;;
  install-lb-attestation-cluster)
    install_lb_ready_attestation_cluster \
      "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}" "${8:-}" "${9:-}"
    ;;
  orchestrate-confirmed)
    orchestrate "${2:-}" steady-confirmed "${3:-}" "${4:-}" "${5:-}" "" "${6:-}" \
      "${7:-}" "${8:-}" "${9:-}" "${10:-}" "${11:-}" "${12:-}" \
      "${13:-}" "${14:-}" "${15:-}"
    ;;
  orchestrate-reconcile)
    orchestrate "${2:-}" reconcile "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}" \
      "${8:-}" "${9:-}" "${10:-}" "${11:-}" "${12:-}" "${13:-}" \
      "${14:-}" "${15:-}" "${16:-}"
    ;;
  recover-confirmed)
    recover_deployment "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}" \
      "${7:-}" "${8:-}" "${9:-}"
    ;;
  retry-reconcile-confirmed)
    retry_distinct_reconciliation "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}" \
      "${7:-}" "${8:-}" "${9:-}"
    ;;
  commit-target-confirmed)
    commit_target_deployment "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}"
    ;;
  recovery-status)
    deployment_recovery_status "${2:-}" "${3:-}" "${4:-}" "${5:-}"
    ;;
  node)
    shift
    require_internal_node_dispatch "${1:-}"
    shift
    node_dispatch "$@"
    ;;
  *)
    die "usage: every deploy/recover/retry/status operation requires exact fresh LB attestation SHA, ready projection SHA, and I_HOLD_EXCLUSIVE_DO_LB_OWNER_UNTIL_DEPLOY_COMPLETE; see OWNER_RELEASE_EXECUTION_RUNBOOK.md"
    ;;
esac
