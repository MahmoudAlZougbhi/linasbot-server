#!/usr/bin/env bash
# Upsert CM_DISABLE_LINAS_LEGACY_BRIDGE into durable EnvironmentFile .env paths and restart.
# Never prints secret values. Usage: prod_cm_set_linas_bridge_flag.sh true|false
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_cm_set_linas_bridge_flag.sh"

VALUE="${1:-}"
if [ "$VALUE" != "true" ] && [ "$VALUE" != "false" ]; then
  echo "[cm-bridge-flag] usage: $0 true|false" >&2
  exit 1
fi

REPO_ROOT="/opt/linasbot"
APP_DIR="$REPO_ROOT"

export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
export CM_DISABLE_LINAS_LEGACY_BRIDGE_VALUE="$VALUE"
export CM_PRESERVE_APP_DIR="$APP_DIR"

PYTHON_BIN="/opt/linasbot/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from services.cm.durable_flags import CM_DISABLE_LINAS_LEGACY_BRIDGE
from scripts.ha.production_env_cas import atomic_update_canonical_env

desired = os.environ["CM_DISABLE_LINAS_LEGACY_BRIDGE_VALUE"]
atomic_update_canonical_env({CM_DISABLE_LINAS_LEGACY_BRIDGE: desired})
print(f"[cm-bridge-flag] canonical_env_updated=true key={CM_DISABLE_LINAS_LEGACY_BRIDGE}")
PY

systemctl restart linasbot
sleep 2
systemctl is-active linasbot
echo "[cm-bridge-flag] CM_DISABLE_LINAS_LEGACY_BRIDGE=$VALUE"
echo "[cm-bridge-flag] COMPLETE_OK"
