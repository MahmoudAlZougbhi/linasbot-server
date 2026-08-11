#!/usr/bin/env bash
# SSH-safe single entry for WhatsApp Cloud production ops (drone-ssh script_stop).
# Installs sibling scripts from OPS_REF then dispatches MODE.
# Usage: sudo MODE=<mode> OPS_REF=origin/ops/whatsapp-postgres-provision bash scripts/prod_whatsapp_cloud_ssh_entry.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
MODE="${MODE:-}"
OPS_REF="${OPS_REF:-origin/ops/whatsapp-postgres-provision}"

echo "[wa-ssh] deployed_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "[wa-ssh] mode=${MODE} ops_ref=${OPS_REF}"

install_script() {
  local name="$1"
  git show "${OPS_REF}:scripts/${name}" > "/tmp/${name}"
  install -m 0755 "/tmp/${name}" "${APP_DIR}/scripts/${name}"
  echo "[wa-ssh] installed=${name}"
}

install_script prod_whatsapp_cloud_postgres_bootstrap.sh
install_script prod_provision_whatsapp_postgres.sh
install_script prod_whatsapp_pg_backup.sh
install_script prod_whatsapp_grant_pilot.sh
install_script prod_whatsapp_db_probe.sh
install_script prod_whatsapp_cloud_migrate.sh
install_script prod_apply_whatsapp_cloud_phase1_flags.sh
install_script prod_whatsapp_cloud_phase1_ops.sh

case "$MODE" in
  PROBE_WHATSAPP_DB)
    bash scripts/prod_whatsapp_db_probe.sh
    ;;
  PROVISION_WHATSAPP_POSTGRES_AND_PHASE1)
    MODE="$MODE" bash scripts/prod_whatsapp_cloud_postgres_bootstrap.sh
    ;;
  APPLY_WHATSAPP_CLOUD_PHASE1|APPLY_WHATSAPP_CLOUD_PHASE1_FLAGS_ONLY)
    MODE="$MODE" bash scripts/prod_whatsapp_cloud_phase1_ops.sh
    ;;
  *)
    echo "[wa-ssh] BLOCKED: unknown mode=${MODE}"
    exit 2
    ;;
esac

echo "[wa-ssh] COMPLETE_OK"
