#!/usr/bin/env bash
# Upsert CM_DISABLE_LINAS_LEGACY_BRIDGE into durable EnvironmentFile .env paths and restart.
# Never prints secret values. Usage: prod_cm_set_linas_bridge_flag.sh true|false
set -euo pipefail

VALUE="${1:-}"
if [ "$VALUE" != "true" ] && [ "$VALUE" != "false" ]; then
  echo "[cm-bridge-flag] usage: $0 true|false" >&2
  exit 1
fi

REPO_ROOT="/opt/linasbot"
CANONICAL_SUBDIR="$REPO_ROOT/linaslaserbot-2.7.22"
APP_DIR="$REPO_ROOT"
if [ -f "$CANONICAL_SUBDIR/main.py" ]; then
  APP_DIR="$CANONICAL_SUBDIR"
fi

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

from services.cm.durable_flags import (
    CM_DISABLE_LINAS_LEGACY_BRIDGE,
    default_production_env_paths,
    upsert_env_file,
)

desired = os.environ["CM_DISABLE_LINAS_LEGACY_BRIDGE_VALUE"]
app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
for path in default_production_env_paths(app_dir=app_dir):
    if not path.parent.exists():
        continue
    upsert_env_file(path, {CM_DISABLE_LINAS_LEGACY_BRIDGE: desired})
    print(f"[cm-bridge-flag] upserted path={path} key={CM_DISABLE_LINAS_LEGACY_BRIDGE}")
PY

# Sync/verify durable readiness (idempotent).
bash /opt/linasbot/scripts/prod_cm_preserve_durable_flags.sh "$APP_DIR"

systemctl restart linasbot
sleep 2
systemctl is-active linasbot
echo "[cm-bridge-flag] CM_DISABLE_LINAS_LEGACY_BRIDGE=$VALUE"
echo "[cm-bridge-flag] COMPLETE_OK"
