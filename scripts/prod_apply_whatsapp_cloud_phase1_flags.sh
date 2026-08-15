#!/usr/bin/env bash
# Apply Phase 1 WhatsApp Cloud operational flags on production.
# Keeps WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false (internal pilot only).
# Never prints secret values. Does not touch Meta Console / Redis-required.
#
# Usage: sudo bash scripts/prod_apply_whatsapp_cloud_phase1_flags.sh
set -euo pipefail

# This script is a child of the reviewed phase-1 entrypoint and shares its lock.
# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_whatsapp_cloud_phase1_ops.sh"

PYTHONPATH=/opt/linasbot /opt/linasbot/venv/bin/python - <<'PY'
from scripts.ha.production_env_cas import atomic_update_canonical_env

updates = {
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true",
    "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true",
    "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true",
    "WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true",
    "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false",
}
atomic_update_canonical_env(updates)
print(f"[wa-phase1] canonical_env_updated=true keys={sorted(updates)}")
PY

systemctl restart linasbot
sleep 3
systemctl is-active --quiet linasbot
echo "[wa-phase1] service_active=true"
echo "[wa-phase1] public_availability=false (Phase 1 internal pilot only)"
echo "[wa-phase1] COMPLETE_OK"
