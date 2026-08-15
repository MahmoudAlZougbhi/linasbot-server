#!/usr/bin/env bash
# Retire only the Meta registry NFS mount/export after exact Postgres HA proof.
# Dry-run by default. Local encrypted-at-rest credential files are retained in a
# root-only backup for soak/rollback. This script never imports NFS into Postgres.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_managed_pg_common.sh"

usage() {
  cat <<EOF
usage: $0 node01|node02 --expected-release-sha SHA --expected-pg-sha256 SHA [options]

Options:
  --apply                 internal: perform one coordinator-locked phase
  --rollback              internal: restore this node's exact config backup
  --confirm TOKEN         required with --apply; exact token REMOVE_META_REGISTRY_NFS

Preconditions on BOTH nodes:
  * exact same verified release and live /api/ready
  * canonical META_REGISTRY_BACKEND=postgres (explicit; dual/default is rejected)
  * identical expected deep Postgres registry digest and valid invariants
  * node identity, peer identity, legacy :8000 rejection, and LB /api/ready owner gate

There is deliberately no skip/bypass option and no lazy-unmount fallback.
EOF
}

ROLE=""
APPLY=0
CONFIRM=""
EXPECTED_RELEASE_SHA=""
EXPECTED_PG_SHA256=""
EXPECTED_CONFIG_SHA256=""
EXPECTED_RUNTIME_SHA256=""
EXPECTED_POST_CONFIG_SHA256=""
ROLLBACK=0
TRANSACTION_STAMP=""
COORDINATOR_TX_ID=""
DATA_ROOT="/opt/linasbot_data"
REG_DIR="${DATA_ROOT}/meta_registry"
BACKUP_DIR="/opt/linasbot_backups/meta-registry-nfs"
ENV_FILE="${DEFAULT_ENV_FILE:-/opt/linasbot/.env}"
EXPORTS="/etc/exports"
CONFIRMATION_TOKEN="REMOVE_META_REGISTRY_NFS"
REPO_DIR="/opt/linasbot"
NFS_CONFIG_HELPER="${REPO_DIR}/scripts/ha/registry_nfs_config.py"

while [[ $# -gt 0 ]]; do
  case "$1" in
    node01|node02) ROLE="$1" ;;
    --apply) APPLY=1 ;;
    --rollback) ROLLBACK=1 ;;
    --confirm) CONFIRM="${2:?missing confirmation token}"; shift ;;
    --expected-release-sha) EXPECTED_RELEASE_SHA="${2:?missing release SHA}"; shift ;;
    --expected-pg-sha256) EXPECTED_PG_SHA256="${2:?missing PG digest}"; shift ;;
    --expected-config-sha256) EXPECTED_CONFIG_SHA256="${2:?missing config digest}"; shift ;;
    --expected-runtime-sha256) EXPECTED_RUNTIME_SHA256="${2:?missing runtime digest}"; shift ;;
    --expected-post-config-sha256) EXPECTED_POST_CONFIG_SHA256="${2:?missing postimage digest}"; shift ;;
    --transaction-stamp) TRANSACTION_STAMP="${2:?missing transaction stamp}"; shift ;;
    --coordinator-tx-id) COORDINATOR_TX_ID="${2:?missing coordinator transaction id}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument" >&2; usage; exit 2 ;;
  esac
  shift
done

[[ "$(id -u)" -eq 0 ]] || { echo "[registry-nfs] root privileges required" >&2; exit 1; }
[[ -n "$ROLE" ]] || { usage; exit 2; }
[[ "$EXPECTED_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "[registry-nfs] invalid release SHA" >&2; exit 2; }
[[ "$EXPECTED_PG_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "[registry-nfs] invalid registry digest" >&2; exit 2; }
if [[ "$APPLY" -eq 1 && "$CONFIRM" != "$CONFIRMATION_TOKEN" ]]; then
  echo "[registry-nfs] --apply requires --confirm ${CONFIRMATION_TOKEN}" >&2
  exit 2
fi
if [[ "$APPLY" -eq 1 && "$ROLLBACK" -eq 1 ]]; then
  echo "[registry-nfs] apply and rollback are mutually exclusive" >&2
  exit 2
fi
if [[ "$APPLY" -eq 1 || "$ROLLBACK" -eq 1 ]]; then
  [[ "$COORDINATOR_TX_ID" =~ ^mnr_[0-9a-f]{64}$ ]] || {
    echo "[registry-nfs] coordinated mutation requires an exact transaction id" >&2
    exit 2
  }
  [[ "$TRANSACTION_STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || {
    echo "[registry-nfs] coordinated mutation requires an exact UTC transaction stamp" >&2
    exit 2
  }
  [[ "$EXPECTED_CONFIG_SHA256" =~ ^[0-9a-f]{64}$ && \
     "$EXPECTED_RUNTIME_SHA256" =~ ^[0-9a-f]{64}$ && \
     "$EXPECTED_POST_CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "[registry-nfs] coordinated mutation requires exact preimage digests" >&2
    exit 2
  }
  [[ "${META_NFS_COORDINATOR_TX_ID:-}" == "$COORDINATOR_TX_ID" ]] || {
    echo "[registry-nfs] direct mutation is refused; use the HA coordinator" >&2
    exit 2
  }
  [[ "${META_NFS_LOCK_FD:-}" =~ ^[0-9]+$ && -e "/proc/self/fd/${META_NFS_LOCK_FD}" ]] || {
    echo "[registry-nfs] coordinator application lock is not inherited" >&2
    exit 2
  }
elif [[ "${META_NFS_COORDINATOR_TX_ID:-}" =~ ^mnr_[0-9a-f]{64}$ && \
        "${META_NFS_LOCK_FD:-}" =~ ^[0-9]+$ && -e "/proc/self/fd/${META_NFS_LOCK_FD}" ]]; then
  : # The HA coordinator owns the inherited application-lock descriptor.
else
  exec 9>/run/lock/linasbot-meta-live.lock
  flock -x 9
fi

if [[ "$ROLE" == "node01" ]]; then
  LOCAL_PRIV="$NODE01_PRIV"
  PEER_PRIV="$NODE02_PRIV"
  PEER_ROLE="node02"
else
  LOCAL_PRIV="$NODE02_PRIV"
  PEER_PRIV="$NODE01_PRIV"
  PEER_ROLE="node01"
fi

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes)

assert_local_identity() {
  if ! ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$LOCAL_PRIV"; then
    echo "[registry-nfs] local private address does not match requested role" >&2
    return 1
  fi
}

assert_exact_registry_path() {
  [[ "$DATA_ROOT" == "/opt/linasbot_data" && "$REG_DIR" == "/opt/linasbot_data/meta_registry" ]] || {
    echo "[registry-nfs] registry path is not the fixed production target" >&2
    return 1
  }
  [[ -d "$DATA_ROOT" && ! -L "$DATA_ROOT" && "$(realpath -e "$DATA_ROOT")" == "$DATA_ROOT" ]] || {
    echo "[registry-nfs] production data root is absent or resolves through a symlink" >&2
    return 1
  }
  [[ -d "$REG_DIR" && ! -L "$REG_DIR" && "$(realpath -e "$REG_DIR")" == "$REG_DIR" ]] || {
    echo "[registry-nfs] registry directory is absent or resolves through a symlink" >&2
    return 1
  }
  [[ -f "$NFS_CONFIG_HELPER" && ! -L "$NFS_CONFIG_HELPER" ]] || {
    echo "[registry-nfs] exact config parser is unavailable" >&2
    return 1
  }
}

fstab_exact_count() {
  "$REPO_DIR/venv/bin/python" "$NFS_CONFIG_HELPER" fstab-count /etc/fstab \
    --source "$NODE01_PRIV:$REG_DIR" --target "$REG_DIR"
}

exports_file_exact_count() {
  "$REPO_DIR/venv/bin/python" "$NFS_CONFIG_HELPER" exports-count "$EXPORTS" --target "$REG_DIR"
}

active_export_exact_count() {
  local temporary count status
  temporary="$(mktemp /tmp/meta-registry-exportfs.XXXXXX)"
  exportfs -v >"$temporary" || {
    status=$?
    rm -f -- "$temporary"
    return "$status"
  }
  count="$("$REPO_DIR/venv/bin/python" "$NFS_CONFIG_HELPER" exports-count "$temporary" --target "$REG_DIR")" || {
    status=$?
    rm -f -- "$temporary"
    return "$status"
  }
  rm -f "$temporary"
  printf '%s\n' "$count"
}

active_export_exact_snapshot() {
  local destination="$1" temporary status
  temporary="$(mktemp /tmp/meta-registry-exportfs.XXXXXX)"
  exportfs -v >"$temporary" || {
    status=$?
    rm -f -- "$temporary"
    return "$status"
  }
  "$REPO_DIR/venv/bin/python" "$NFS_CONFIG_HELPER" exports-select "$temporary" \
    --target "$REG_DIR" >"$destination" || {
    status=$?
    rm -f -- "$temporary" "$destination"
    return "$status"
  }
  rm -f -- "$temporary"
}

active_mount_exact_snapshot() {
  findmnt -rn -o SOURCE,TARGET,FSTYPE --target "$REG_DIR"
}

sha256_file_value() {
  sha256sum "$1" | awk '{print $1}'
}

assert_current_preimage() {
  local runtime_temp config_sha runtime_sha
  if [[ "$ROLE" == "node02" ]]; then
    config_sha="$(sha256_file_value /etc/fstab)"
    runtime_temp="$(mktemp /tmp/meta-registry-mount-preimage.XXXXXX)"
    active_mount_exact_snapshot >"$runtime_temp"
  else
    config_sha="$(sha256_file_value "$EXPORTS")"
    runtime_temp="$(mktemp /tmp/meta-registry-export-preimage.XXXXXX)"
    active_export_exact_snapshot "$runtime_temp"
  fi
  runtime_sha="$(sha256_file_value "$runtime_temp")"
  rm -f -- "$runtime_temp"
  [[ "$config_sha" == "$EXPECTED_CONFIG_SHA256" && \
     "$runtime_sha" == "$EXPECTED_RUNTIME_SHA256" ]] || {
    echo "[registry-nfs] NFS preimage changed after coordinator snapshot" >&2
    return 1
  }
}

assert_exact_active_mount() {
  local matches
  matches="$(findmnt -rn -o SOURCE,TARGET,FSTYPE --target "$REG_DIR" | \
    awk -v source="$NODE01_PRIV:$REG_DIR" -v target="$REG_DIR" \
      '$1 == source && $2 == target && ($3 == "nfs" || $3 == "nfs4") {count++} END {print count + 0}')"
  [[ "$matches" == "1" ]] || {
    echo "[registry-nfs] active registry mount source/target/type is not exact" >&2
    return 1
  }
}

verify_local_node() {
  LINAS_HA_PEER_HOST="$PEER_PRIV" \
    bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
      "$EXPECTED_RELEASE_SHA" local-only "" "$ROLE"
  "$REPO_DIR/venv/bin/python" "$REPO_DIR/scripts/ha/verify_meta_registry_postgres.py" \
    --env-file "$ENV_FILE" --store "$REG_DIR/registry.json" \
    --expected-pg-sha256 "$EXPECTED_PG_SHA256"
}

verify_peer_node() {
  "${SSH[@]}" "root@${PEER_PRIV}" \
    env LINAS_HA_PEER_HOST="$LOCAL_PRIV" \
    bash "$REPO_DIR/scripts/ha/verify_meta_release_ha.sh" \
      "$EXPECTED_RELEASE_SHA" local-only "" "$PEER_ROLE"
  "${SSH[@]}" "root@${PEER_PRIV}" \
    "$REPO_DIR/venv/bin/python" "$REPO_DIR/scripts/ha/verify_meta_registry_postgres.py" \
      --env-file "$ENV_FILE" --store "$REG_DIR/registry.json" \
      --expected-pg-sha256 "$EXPECTED_PG_SHA256"
}

verify_ready_exact() {
  "$REPO_DIR/venv/bin/python" - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=8) as response:
    payload = json.load(response)
if response.status != 200 or payload.get("ok") is not True:
    raise SystemExit("local readiness is not exact 200/ok=true")
PY
  "${SSH[@]}" "root@${PEER_PRIV}" "$REPO_DIR/venv/bin/python" - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=8) as response:
    payload = json.load(response)
if response.status != 200 or payload.get("ok") is not True:
    raise SystemExit("peer readiness is not exact 200/ok=true")
PY
}

backup_registry_dir() {
  local stamp="$1"
  local temporary final checksum
  [[ ! -L /opt/linasbot_backups && ! -L "$BACKUP_DIR" ]] || {
    echo "[registry-nfs] backup path must not contain a symlink" >&2
    return 1
  }
  install -d -o root -g root -m 0700 "$BACKUP_DIR"
  [[ "$(stat -c '%u:%g:%a' "$BACKUP_DIR")" == "0:0:700" ]] || {
    echo "[registry-nfs] backup directory security contract failed" >&2
    return 1
  }
  temporary="$(mktemp "$BACKUP_DIR/.registry-${ROLE}-${stamp}.XXXXXX")"
  final="$BACKUP_DIR/registry-${ROLE}-${stamp}.tar"
  checksum="${final}.sha256"
  if [[ -e "$final" || -L "$final" || -e "$checksum" || -L "$checksum" ]]; then
    [[ -f "$final" && ! -L "$final" && -f "$checksum" && ! -L "$checksum" ]] || {
      echo "[registry-nfs] partial protected registry backup blocks recovery" >&2
      return 1
    }
    [[ "$(stat -c '%u:%g:%a' "$final")" == "0:0:600" && \
       "$(stat -c '%u:%g:%a' "$checksum")" == "0:0:600" ]] || return 1
    sha256sum -c "$checksum" >/dev/null
    echo "[registry-nfs] existing protected registry backup re-authenticated: $final"
    return 0
  fi
  chmod 0600 "$temporary"
  tar --one-file-system -C "$(dirname "$REG_DIR")" -cpf "$temporary" "$(basename "$REG_DIR")"
  sync -f "$temporary"
  ln "$temporary" "$final"
  rm -f "$temporary"
  chmod 0600 "$final"
  sha256sum "$final" > "${checksum}.tmp"
  chmod 0600 "${checksum}.tmp"
  ln "${checksum}.tmp" "$checksum"
  rm -f "${checksum}.tmp"
  sync -f "$BACKUP_DIR"
  sha256sum -c "$checksum" >/dev/null
  echo "[registry-nfs] protected registry backup verified: $final"
}

atomic_restore_file() {
  local backup="$1" destination="$2" temporary
  temporary="$(mktemp "$(dirname "$destination")/.meta-registry-rollback.XXXXXX")"
  cp -a "$backup" "$temporary"
  sync -f "$temporary"
  mv "$temporary" "$destination"
  sync -f "$(dirname "$destination")"
}

atomic_backup_file() {
  local source="$1" destination="$2" temporary
  if [[ -e "$destination" || -L "$destination" ]]; then
    [[ -f "$destination" && ! -L "$destination" ]] || return 1
    cmp -s -- "$source" "$destination" || {
      echo "[registry-nfs] existing config backup differs from current rollback preimage" >&2
      return 1
    }
    return 0
  fi
  temporary="$(mktemp "$(dirname "$destination")/.meta-registry-backup.XXXXXX")"
  cp --preserve=all "$source" "$temporary"
  sync -f "$temporary"
  ln "$temporary" "$destination"
  rm -f "$temporary"
  sync -f "$(dirname "$destination")"
}

preflight() {
  echo "[registry-nfs] preflight role=$ROLE apply=$APPLY"
  assert_local_identity
  assert_exact_registry_path
  verify_local_node
  verify_peer_node
  verify_ready_exact
  if [[ "$ROLE" == "node02" ]]; then
    [[ -f /etc/fstab && ! -L /etc/fstab ]] || {
      echo "[registry-nfs] fstab is unsafe/absent" >&2
      return 1
    }
    mountpoint -q "$REG_DIR" || { echo "[registry-nfs] expected NFS mount is absent" >&2; return 1; }
    assert_exact_active_mount
    [[ "$(fstab_exact_count)" == "1" ]] || {
      echo "[registry-nfs] expected exactly one parsed registry fstab entry" >&2
      return 1
    }
  else
    [[ -f "$EXPORTS" && ! -L "$EXPORTS" ]] || { echo "[registry-nfs] exports file is unsafe/absent" >&2; return 1; }
    [[ "$(exports_file_exact_count)" -ge 1 && "$(active_export_exact_count)" -ge 1 ]] || {
      echo "[registry-nfs] exact registry export is absent" >&2
      return 1
    }
    if [[ "$APPLY" -eq 1 ]]; then
      "${SSH[@]}" "root@${PEER_PRIV}" bash -s -- "$REG_DIR" "$NODE01_PRIV" <<'SH'
set -euo pipefail
reg_dir="$1"
node01_priv="$2"
if mountpoint -q "$reg_dir"; then
  echo "peer node02 registry NFS mount must be retired first" >&2
  exit 1
fi
count="$(/opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/registry_nfs_config.py \
  fstab-count /etc/fstab --source "$node01_priv:$reg_dir" --target "$reg_dir")"
if [ "$count" != "0" ]; then
  echo "peer node02 registry fstab entry must be retired first" >&2
  exit 1
fi
SH
    fi
  fi
  echo "[registry-nfs] preflight PASS on both nodes"
}

retire_node02_mount() {
  local stamp="$1" fstab_backup fstab_temp changed=0 originally_mounted=1
  fstab_backup="/etc/fstab.meta-registry-backup-${stamp}"
  fstab_temp="$(mktemp /etc/.fstab.meta-registry.XXXXXX)"
  atomic_backup_file /etc/fstab "$fstab_backup"
  [[ "$(sha256_file_value "$fstab_backup")" == "$EXPECTED_CONFIG_SHA256" ]] || {
    echo "[registry-nfs] node02 config backup differs from the journaled preimage" >&2
    return 1
  }
  "$REPO_DIR/venv/bin/python" "$NFS_CONFIG_HELPER" fstab-filter /etc/fstab \
    --source "$NODE01_PRIV:$REG_DIR" --target "$REG_DIR" >"$fstab_temp"
  [[ "$(sha256_file_value "$fstab_temp")" == "$EXPECTED_POST_CONFIG_SHA256" ]] || {
    echo "[registry-nfs] node02 filtered postimage differs from the journal" >&2
    return 1
  }
  chown root:root "$fstab_temp"
  chmod --reference=/etc/fstab "$fstab_temp"
  sync -f "$fstab_temp"

  rollback_node02() {
    local status=$?
    trap - ERR
    if [[ "$changed" -eq 1 ]]; then
      atomic_restore_file "$fstab_backup" /etc/fstab || true
    else
      rm -f "$fstab_temp"
    fi
    if [[ "$originally_mounted" -eq 1 ]] && ! mountpoint -q "$REG_DIR"; then
      mount "$REG_DIR" || true
    fi
    echo "[registry-nfs] node02 operation failed; fstab/mount rollback attempted" >&2
    exit "$status"
  }
  trap rollback_node02 ERR

  mv "$fstab_temp" /etc/fstab
  changed=1
  sync -f /etc
  umount "$REG_DIR"
  if mountpoint -q "$REG_DIR" || findmnt -n --target "$REG_DIR" >/dev/null 2>&1; then
    return 1
  fi
  mkdir -p "$REG_DIR"
  chmod 0700 "$REG_DIR"
  trap - ERR
  echo "[registry-nfs] node02 NFS mount retired; backup and hidden local directory retained for soak"
}

retire_node01_export() {
  local stamp="$1" exports_backup active_backup exports_temp active_temp changed=0
  exports_backup="/etc/exports.meta-registry-backup-${stamp}"
  active_backup="/etc/exports.meta-registry-active-backup-${stamp}"
  exports_temp="$(mktemp /etc/.exports.meta-registry.XXXXXX)"
  active_temp="$(mktemp /etc/.exports.meta-registry-active.XXXXXX)"
  atomic_backup_file "$EXPORTS" "$exports_backup"
  active_export_exact_snapshot "$active_temp"
  [[ -s "$active_temp" ]] || {
    echo "[registry-nfs] exact active export preimage is empty" >&2
    return 1
  }
  atomic_backup_file "$active_temp" "$active_backup"
  rm -f -- "$active_temp"
  [[ "$(sha256_file_value "$exports_backup")" == "$EXPECTED_CONFIG_SHA256" && \
     "$(sha256_file_value "$active_backup")" == "$EXPECTED_RUNTIME_SHA256" ]] || {
    echo "[registry-nfs] node01 backup differs from the journaled preimage" >&2
    return 1
  }
  "$REPO_DIR/venv/bin/python" "$NFS_CONFIG_HELPER" exports-filter "$EXPORTS" \
    --target "$REG_DIR" >"$exports_temp"
  [[ "$(sha256_file_value "$exports_temp")" == "$EXPECTED_POST_CONFIG_SHA256" ]] || {
    echo "[registry-nfs] node01 filtered postimage differs from the journal" >&2
    return 1
  }
  chown root:root "$exports_temp"
  chmod --reference="$EXPORTS" "$exports_temp"
  sync -f "$exports_temp"

  rollback_node01() {
    local status=$?
    trap - ERR
    if [[ "$changed" -eq 1 ]]; then
      atomic_restore_file "$exports_backup" "$EXPORTS" || true
      exportfs -ra || true
    else
      rm -f "$exports_temp"
    fi
    echo "[registry-nfs] node01 operation failed; exports rollback attempted" >&2
    exit "$status"
  }
  trap rollback_node01 ERR

  mv "$exports_temp" "$EXPORTS"
  changed=1
  sync -f /etc
  exportfs -ra
  if [[ "$(exports_file_exact_count)" != "0" || "$(active_export_exact_count)" != "0" ]]; then
    return 1
  fi
  trap - ERR
  echo "[registry-nfs] node01 registry export retired; local directory retained for soak"
}

rollback_node02_mount() {
  local stamp="$1" fstab_backup current_sha
  fstab_backup="/etc/fstab.meta-registry-backup-${stamp}"
  [[ -f "$fstab_backup" && ! -L "$fstab_backup" ]] || {
    echo "[registry-nfs] exact node02 fstab rollback backup is absent" >&2
    return 1
  }
  [[ "$(sha256_file_value "$fstab_backup")" == "$EXPECTED_CONFIG_SHA256" ]] || {
    echo "[registry-nfs] node02 rollback backup does not match the journal" >&2
    return 1
  }
  [[ "$(fstab_exact_count)" == "0" || "$(fstab_exact_count)" == "1" ]] || {
    echo "[registry-nfs] node02 fstab is not an exact retired state" >&2
    return 1
  }
  current_sha="$(sha256_file_value /etc/fstab)"
  [[ "$current_sha" == "$EXPECTED_POST_CONFIG_SHA256" || \
     "$current_sha" == "$EXPECTED_CONFIG_SHA256" ]] || {
    echo "[registry-nfs] node02 config changed outside the retirement transaction" >&2
    return 1
  }
  if ! cmp -s -- "$fstab_backup" /etc/fstab; then
    atomic_restore_file "$fstab_backup" /etc/fstab
  fi
  if mountpoint -q "$REG_DIR"; then
    if ! assert_exact_active_mount; then
      umount "$REG_DIR"
      mount "$REG_DIR"
    fi
  else
    mount "$REG_DIR"
  fi
  cmp -s -- "$fstab_backup" /etc/fstab
  [[ "$(sha256_file_value /etc/fstab)" == "$EXPECTED_CONFIG_SHA256" ]]
  [[ "$(fstab_exact_count)" == "1" ]]
  assert_exact_active_mount
  local mount_current
  mount_current="$(mktemp /tmp/meta-registry-mount-current.XXXXXX)"
  active_mount_exact_snapshot >"$mount_current"
  [[ "$(sha256_file_value "$mount_current")" == "$EXPECTED_RUNTIME_SHA256" ]]
  rm -f -- "$mount_current"
  echo "[registry-nfs] node02 fstab/mount rollback verified"
}

rollback_node01_export() {
  local stamp="$1" exports_backup active_backup active_current current_sha
  exports_backup="/etc/exports.meta-registry-backup-${stamp}"
  active_backup="/etc/exports.meta-registry-active-backup-${stamp}"
  [[ -f "$exports_backup" && ! -L "$exports_backup" ]] || {
    echo "[registry-nfs] exact node01 exports rollback backup is absent" >&2
    return 1
  }
  [[ -f "$active_backup" && ! -L "$active_backup" ]] || {
    echo "[registry-nfs] exact node01 active-export rollback preimage is absent" >&2
    return 1
  }
  [[ "$(sha256_file_value "$exports_backup")" == "$EXPECTED_CONFIG_SHA256" && \
     "$(sha256_file_value "$active_backup")" == "$EXPECTED_RUNTIME_SHA256" ]] || {
    echo "[registry-nfs] node01 rollback backups do not match the journal" >&2
    return 1
  }
  [[ "$(exports_file_exact_count)" == "0" || "$(exports_file_exact_count)" -ge 1 ]] || {
    echo "[registry-nfs] node01 exports are not an exact retired state" >&2
    return 1
  }
  current_sha="$(sha256_file_value "$EXPORTS")"
  [[ "$current_sha" == "$EXPECTED_POST_CONFIG_SHA256" || \
     "$current_sha" == "$EXPECTED_CONFIG_SHA256" ]] || {
    echo "[registry-nfs] node01 config changed outside the retirement transaction" >&2
    return 1
  }
  if ! cmp -s -- "$exports_backup" "$EXPORTS"; then
    atomic_restore_file "$exports_backup" "$EXPORTS"
  fi
  exportfs -ra
  cmp -s -- "$exports_backup" "$EXPORTS"
  [[ "$(sha256_file_value "$EXPORTS")" == "$EXPECTED_CONFIG_SHA256" ]]
  [[ "$(exports_file_exact_count)" -ge 1 && "$(active_export_exact_count)" -ge 1 ]]
  active_current="$(mktemp /etc/.exports.meta-registry-active-current.XXXXXX)"
  active_export_exact_snapshot "$active_current"
  cmp -s -- "$active_backup" "$active_current"
  [[ "$(sha256_file_value "$active_current")" == "$EXPECTED_RUNTIME_SHA256" ]]
  rm -f -- "$active_current"
  echo "[registry-nfs] node01 exports rollback verified"
}

if [[ "$ROLLBACK" -eq 1 ]]; then
  if [[ "$ROLE" == "node02" ]]; then
    rollback_node02_mount "$TRANSACTION_STAMP"
  else
    rollback_node01_export "$TRANSACTION_STAMP"
  fi
  echo "[registry-nfs] ROLLBACK_DONE role=$ROLE tx=$COORDINATOR_TX_ID"
  exit 0
fi

preflight
if [[ "$APPLY" -ne 1 ]]; then
  echo "[registry-nfs] DRY-RUN: would make a protected registry backup, atomically back up config,"
  if [[ "$ROLE" == "node02" ]]; then
    echo "[registry-nfs] DRY-RUN: then remove exact fstab entry and perform a normal (never lazy) unmount"
  else
    echo "[registry-nfs] DRY-RUN: then remove exact exports entry and verify exportfs convergence"
  fi
  exit 0
fi

STAMP="$TRANSACTION_STAMP"
assert_current_preimage
backup_registry_dir "$STAMP"
if [[ "$ROLE" == "node02" ]]; then
  retire_node02_mount "$STAMP"
else
  retire_node01_export "$STAMP"
fi

echo "[registry-nfs] DONE role=$ROLE; rollback config and protected registry backup retained"
