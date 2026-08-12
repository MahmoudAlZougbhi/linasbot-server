#!/usr/bin/env bash
# Remove meta_registry NFS export/mount AFTER Postgres registry authority is verified.
# Keeps local copies on both nodes until soak (--apply only mutates NFS; local data retained).
# Default dry-run; pass --apply to unexport/unmount. Does NOT enable BOC or touch SportBook.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_managed_pg_common.sh"

usage() {
  cat <<EOF
usage: $0 node01|node02 [--apply] [--skip-registry-check]

Safely removes meta_registry NFS sharing once META_REGISTRY_BACKEND=postgres (or dual)
is live and registry Postgres authority is verified.

  node01  drop registry NFS export (keeps local ${DATA_ROOT:-/opt/linasbot_data}/meta_registry)
  node02  umount registry NFS + fstab cleanup (keeps local copy)

Default dry-run. --apply executes changes.
EOF
}

DATA_ROOT="${DATA_ROOT:-/opt/linasbot_data}"
REG_DIR="${DATA_ROOT}/meta_registry"
EXPORTS="/etc/exports"
NFS_MARKER="# linas-ha-share"
ROLE=""
APPLY=0
SKIP_CHECK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    node01|node02) ROLE="$1" ;;
    --apply) APPLY=1 ;;
    --skip-registry-check) SKIP_CHECK=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

[[ -n "$ROLE" ]] || { usage; exit 2; }

registry_postgres_ready() {
  python3 - <<'PY'
import json
import os
import urllib.request
from pathlib import Path

backend = (os.getenv("META_REGISTRY_BACKEND") or "").strip().lower()
env_path = Path("/opt/linasbot/.env")
if env_path.is_file():
    for line in env_path.read_text(errors="replace").splitlines():
        if line.startswith("META_REGISTRY_BACKEND="):
            backend = line.split("=", 1)[1].strip().strip("'\"").lower()
            break

if backend not in {"postgres", "dual"}:
    raise SystemExit(f"registry backend not postgres-ready: {backend!r}")

try:
    ready = json.load(urllib.request.urlopen("http://127.0.0.1:8003/api/ready", timeout=10))
except Exception as exc:
    raise SystemExit(f"/api/ready unreachable: {exc}") from exc

checks = ready.get("checks") if isinstance(ready.get("checks"), dict) else {}
meta = checks.get("meta_app_registry") or checks.get("meta_registry") or {}
if isinstance(meta, dict):
  ok = meta.get("ok")
  backend_live = str(meta.get("backend") or meta.get("storage") or "").lower()
  if ok is True and ("postgres" in backend_live or backend in {"postgres", "dual"}):
      print("registry_postgres_ok", backend_live or backend)
      raise SystemExit(0)
print("registry_check", json.dumps(meta)[:300])
raise SystemExit("registry postgres authority not verified on /api/ready")
PY
}

echo "[ha-registry-nfs] role=$ROLE hostname=$(hostname) apply=${APPLY}"

if [[ "$SKIP_CHECK" -ne 1 ]]; then
  if registry_postgres_ready; then
    echo "[ha-registry-nfs] registry postgres authority check PASS"
  else
    echo "[ha-registry-nfs] BLOCKED: registry not on postgres authority (use --skip-registry-check to override)" >&2
    exit 1
  fi
else
  echo "[ha-registry-nfs] WARN: skipping registry postgres authority check"
fi

if [[ "$ROLE" == "node02" ]]; then
  if mountpoint -q "${REG_DIR}" 2>/dev/null; then
    echo "[ha-registry-nfs] registry is NFS-mounted at ${REG_DIR}"
    if [[ "$APPLY" -eq 1 ]]; then
      umount "${REG_DIR}" || umount -l "${REG_DIR}"
      echo "[ha-registry-nfs] umounted ${REG_DIR}"
    else
      echo "[ha-registry-nfs] DRY-RUN: would umount ${REG_DIR}"
    fi
  else
    echo "[ha-registry-nfs] registry not mounted (already local)"
  fi

  if grep -qF "${NODE01_PRIV}:${REG_DIR}" /etc/fstab 2>/dev/null; then
    if [[ "$APPLY" -eq 1 ]]; then
      cp -a /etc/fstab "/etc/fstab.bak.registry-remove.$(date +%s)"
      grep -vF "${NODE01_PRIV}:${REG_DIR}" /etc/fstab > /tmp/fstab.registry-remove
      mv /tmp/fstab.registry-remove /etc/fstab
      echo "[ha-registry-nfs] fstab registry line removed"
    else
      echo "[ha-registry-nfs] DRY-RUN: would remove fstab line for ${NODE01_PRIV}:${REG_DIR}"
    fi
  fi

  mkdir -p "${REG_DIR}"
  if [[ ! -f "${REG_DIR}/registry.json" ]]; then
    echo "[ha-registry-nfs] WARN: local ${REG_DIR}/registry.json missing — keeping dir for soak"
  else
    echo "[ha-registry-nfs] local registry.json retained ($(stat -c%s "${REG_DIR}/registry.json" 2>/dev/null || stat -f%z "${REG_DIR}/registry.json") bytes)"
  fi
  echo "[ha-registry-nfs] DONE node02"
  exit 0
fi

# node01: remove registry export; keep local directory
if [[ -f "${REG_DIR}/registry.json" ]]; then
  echo "[ha-registry-nfs] local registry.json present (kept for soak)"
else
  echo "[ha-registry-nfs] WARN: ${REG_DIR}/registry.json missing on node01"
fi

if [[ "$APPLY" -ne 1 ]]; then
  echo "[ha-registry-nfs] DRY-RUN: would remove registry lines from ${EXPORTS} and exportfs -ra"
  echo "[ha-registry-nfs] DONE node01 (dry-run)"
  exit 0
fi

TMP_EXP="$(mktemp)"
if [[ -f "${EXPORTS}" ]]; then
  awk -v reg="${REG_DIR}" '
    $0 ~ reg {next}
    {print}
  ' "${EXPORTS}" > "${TMP_EXP}" || cp "${EXPORTS}" "${TMP_EXP}"
  # Also strip linas-ha-share marker block if registry-only
  awk -v m="${NFS_MARKER}" '
    $0 ~ m {skip=1; next}
    skip && /^[^#]/ && NF {skip=0}
    skip && /^$/ {next}
    skip {next}
    {print}
  ' "${TMP_EXP}" > "${TMP_EXP}.2" && mv "${TMP_EXP}.2" "${TMP_EXP}"
else
  : > "${TMP_EXP}"
fi
cp -a "${EXPORTS}" "${EXPORTS}.bak.registry-remove.$(date +%s)" 2>/dev/null || true
mv "${TMP_EXP}" "${EXPORTS}"
exportfs -ra
exportfs -v 2>/dev/null | sed 's/^/[ha-registry-nfs] export /' || true
echo "[ha-registry-nfs] DONE node01 (local registry kept; NFS export removed)"
