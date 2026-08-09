#!/usr/bin/env bash
# Upsert Sol/Terra model-routing policy env keys and restart.
# Never prints secret values.
# Usage: prod_apply_model_routing_policy.sh
set -euo pipefail

REPO_ROOT="/opt/linasbot"
CANONICAL_SUBDIR="$REPO_ROOT/linaslaserbot-2.7.22"
APP_DIR="$REPO_ROOT"
if [ -f "$CANONICAL_SUBDIR/main.py" ]; then
  APP_DIR="$CANONICAL_SUBDIR"
fi

export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"
export CM_PRESERVE_APP_DIR="$APP_DIR"

PYTHON_BIN="/opt/linasbot/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${APP_DIR}/venv/bin/python"
fi
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

UPSERT="$REPO_ROOT/scripts/prod_upsert_model_routing_env.py"
if [ ! -f "$UPSERT" ]; then
  UPSERT="$APP_DIR/scripts/prod_upsert_model_routing_env.py"
fi
"$PYTHON_BIN" "$UPSERT"

systemctl restart linasbot
sleep 3
systemctl is-active linasbot

"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from services.cm.durable_flags import default_production_env_paths
from services.model_policy import (
    MODEL_CUSTOMER_TERRA,
    MODEL_OWNER_SOL,
    validate_model_policy_config,
)

app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
for path in default_production_env_paths(app_dir=app_dir):
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
