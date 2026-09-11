#!/usr/bin/env bash
# Upsert Customer Brain production support flags (Brain is permanent — no enable flag).
set -euo pipefail
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_apply_customer_brain_flags.sh"
PYTHON_BIN="/opt/linasbot/venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" - <<'PY'
from scripts.ha.production_env_cas import atomic_update_canonical_env
updates = {
    "LINAS_CUSTOMER_AI_LAB": "true",
    "EMERGENCY_LEGACY_REPLY_ENABLED": "false",
    "MESSAGE_BILLING_CUTOVER": "false",
    "MESSAGE_BILLING_ENABLED": "false",
}
atomic_update_canonical_env(updates)
print(f"[customer-brain-flags] canonical_env_updated=true keys={sorted(updates)}")
PY
systemctl restart linasbot
sleep 3
systemctl is-active linasbot
echo "[customer-brain-flags] COMPLETE_OK"
