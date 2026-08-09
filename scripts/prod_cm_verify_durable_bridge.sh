#!/usr/bin/env bash
# Non-destructive verification that durable bridge-disable remains true after
# rendering the same EnvironmentFile paths deploy uses (no service restart required
# when VERIFY_RELOAD=0; optional safe restart when VERIFY_RELOAD=1).
set -euo pipefail

VERIFY_RELOAD="${VERIFY_RELOAD:-0}"
REPO_ROOT="/opt/linasbot"
CANONICAL_SUBDIR="$REPO_ROOT/linaslaserbot-2.7.22"
APP_DIR="$REPO_ROOT"
if [ -f "$CANONICAL_SUBDIR/main.py" ]; then
  APP_DIR="$CANONICAL_SUBDIR"
fi

export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
export CM_PRESERVE_APP_DIR="$APP_DIR"

echo "[cm-durable-verify] app_dir=$APP_DIR deployed_sha=$(git -C /opt/linasbot rev-parse HEAD)"

# Re-run preserve (idempotent) then readiness gate.
sudo bash /opt/linasbot/scripts/prod_cm_preserve_durable_flags.sh "$APP_DIR"

if [ "$VERIFY_RELOAD" = "1" ]; then
  systemctl daemon-reload
  systemctl restart linasbot
  sleep 2
  systemctl is-active linasbot
fi

/opt/linasbot/venv/bin/python - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("LINASBOT_DATA_ROOT", "/opt/linasbot_data")
os.environ.setdefault("ENVIRONMENT", "production")

from services.cm.constants import cm_disable_linas_legacy_bridge, tenant_has_published_cm, tenant_uses_cm_runtime
from services.cm.durable_flags import (
    CM_DISABLE_LINAS_LEGACY_BRIDGE,
    default_production_env_paths,
    parse_env_bool,
    read_env_file_map,
    readiness_requires_disable_bridge,
)

app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
paths = default_production_env_paths(app_dir=app_dir)
env_file = Path(app_dir) / ".env"
file_val = parse_env_bool(read_env_file_map(env_file).get(CM_DISABLE_LINAS_LEGACY_BRIDGE))
# Load EnvironmentFile values into process for effective check (no secrets printed).
for path in paths:
    mapping = read_env_file_map(path)
    for key, value in mapping.items():
        if key.startswith("CM_"):
            os.environ[key] = value

effective = cm_disable_linas_legacy_bridge()
linas_published = tenant_has_published_cm("linas")
gate = readiness_requires_disable_bridge(
    linas_has_published_cm=linas_published,
    effective_disable_bridge=effective,
)
report = {
    "app_dir": app_dir,
    "environment_file": str(env_file),
    "file_parsed_disable_bridge": file_val,
    "effective_cm_disable_linas_legacy_bridge": effective,
    "tenant_has_published_cm": linas_published,
    "tenant_uses_cm_runtime": tenant_uses_cm_runtime("linas"),
    "readiness": gate,
}
print(json.dumps(report, indent=2, ensure_ascii=False))
if not gate.get("ok") or effective is not True:
    print("[cm-durable-verify] COMPLETE_FAIL")
    raise SystemExit(2)
print("[cm-durable-verify] COMPLETE_OK")
PY
