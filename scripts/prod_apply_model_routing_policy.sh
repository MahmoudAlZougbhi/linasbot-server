#!/usr/bin/env bash
# Upsert Sol/Terra model-routing policy env keys and restart.
# Never prints secret values.
# Usage: prod_apply_model_routing_policy.sh
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_apply_model_routing_policy.sh"

REPO_ROOT="/opt/linasbot"
APP_DIR="$REPO_ROOT"

export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
export CM_PRESERVE_APP_DIR="$APP_DIR"

PYTHON_BIN="/opt/linasbot/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - <<'PY'
from scripts.ha.production_env_cas import atomic_update_canonical_env
from scripts.prod_upsert_model_routing_env import UPDATES

atomic_update_canonical_env(UPDATES)
print(f"[model-routing] canonical_env_updated=true keys={sorted(UPDATES)}")
PY

systemctl restart linasbot
sleep 3
systemctl is-active linasbot

"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from services.model_policy import (
    MODEL_CUSTOMER_TERRA,
    MODEL_OWNER_SOL,
    validate_model_policy_config,
)

for path in (Path("/opt/linasbot/.env"),):
    if not path.is_file():
        continue
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key.startswith("LINAS_") and "MODEL" in key:
            os.environ[key] = val

snap = validate_model_policy_config()
print(
    "[model-routing] verify ok "
    f"owner={snap['owner_model']} customer={snap['customer_model']} "
    f"mode={snap['reasoning_mode']}"
)
assert snap["owner_model"] == MODEL_OWNER_SOL
assert snap["customer_model"] == MODEL_CUSTOMER_TERRA
print("[model-routing] POLICY_LIVE")
PY
