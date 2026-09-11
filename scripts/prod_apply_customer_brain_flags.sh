#!/usr/bin/env bash
# Upsert Customer Brain production flags into canonical .env and restart.
# Never prints secret values. Does NOT restore Luna/Terra.
# Usage: prod_apply_customer_brain_flags.sh
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_apply_customer_brain_flags.sh"

PYTHON_BIN="/opt/linasbot/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" - <<'PY'
from pathlib import Path

from scripts.ha.production_env_cas import atomic_update_canonical_env

updates = {
    # Customer Brain is the only customer reply engine on this branch.
    "CUSTOMER_BRAIN_ENABLED": "true",
    "LINAS_CUSTOMER_AI_LAB": "true",
    "CUSTOMER_BRAIN_TENANT_ALLOWLIST": "linas",
    "EMERGENCY_LEGACY_REPLY_ENABLED": "false",
    # Keep message commerce cutover off until priced/sale-ready.
    "MESSAGE_BILLING_CUTOVER": "false",
    "MESSAGE_BILLING_ENABLED": "false",
}
atomic_update_canonical_env(updates)
print(f"[customer-brain-flags] canonical_env_updated=true keys={sorted(updates)}")
PY

systemctl restart linasbot
sleep 3
systemctl is-active linasbot

"$PYTHON_BIN" - <<'PY'
from pathlib import Path

def read_flag(key: str, default: str = "<unset>") -> str:
    path = Path("/opt/linasbot/.env")
    if not path.exists():
        return default
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default

keys = [
    "CUSTOMER_BRAIN_ENABLED",
    "LINAS_CUSTOMER_AI_LAB",
    "CUSTOMER_BRAIN_TENANT_ALLOWLIST",
    "EMERGENCY_LEGACY_REPLY_ENABLED",
    "MESSAGE_BILLING_CUTOVER",
    "MESSAGE_BILLING_ENABLED",
    "OPENAI_API_KEY",
    "VOYAGE_API_KEY",
]
print("[customer-brain-flags] effective:")
for key in keys:
    value = read_flag(key)
    if key.endswith("_API_KEY"):
        print(f"  {key}={'SET' if value not in {'', '<unset>'} else 'MISSING'}")
    else:
        print(f"  {key}={value}")
PY

echo "[customer-brain-flags] COMPLETE_OK"
