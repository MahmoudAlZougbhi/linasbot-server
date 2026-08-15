#!/usr/bin/env bash
# Preserve the durable CM ops flag in the canonical production EnvironmentFile.
# Never prints secret values. The common live/deploy guard must already be held.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_cm_preserve_durable_flags.sh"

APP_DIR="${1:-}"
if [ -z "$APP_DIR" ]; then
  REPO_ROOT="/opt/linasbot"
  CANONICAL_SUBDIR="$REPO_ROOT/linaslaserbot-2.7.22"
  APP_DIR="$REPO_ROOT"
  if [ -f "$CANONICAL_SUBDIR/main.py" ]; then
    APP_DIR="$CANONICAL_SUBDIR"
  fi
fi

export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
export CM_PRESERVE_APP_DIR="$APP_DIR"

echo "[cm-durable-flags] app_dir=$APP_DIR"
echo "[cm-durable-flags] data_root=$LINASBOT_DATA_ROOT"

PYTHON_BIN="/opt/linasbot/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("LINASBOT_DATA_ROOT", "/opt/linasbot_data")
os.environ.setdefault("ENVIRONMENT", "production")

from services.cm.durable_flags import (
    CM_DISABLE_LINAS_LEGACY_BRIDGE,
    default_production_env_paths,
    parse_env_bool,
    preserve_disable_linas_legacy_bridge,
    read_env_file_map,
    readiness_requires_disable_bridge,
)
from scripts.ha.production_env_cas import atomic_update_canonical_env
from services.cm.constants import tenant_has_published_cm

app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
paths = default_production_env_paths(app_dir=app_dir)
linas_published = tenant_has_published_cm("linas")
report = preserve_disable_linas_legacy_bridge(
    paths,
    linas_has_published_cm=linas_published,
    dry_run=True,
)
effective = report.get("effective")
if effective is not None:
    atomic_update_canonical_env(
        {CM_DISABLE_LINAS_LEGACY_BRIDGE: "true" if effective else "false"}
    )
    report["updated_paths"] = ["/opt/linasbot/.env"]
    report["dry_run"] = False
persisted = parse_env_bool(
    read_env_file_map(Path("/opt/linasbot/.env")).get(CM_DISABLE_LINAS_LEGACY_BRIDGE)
)
if effective is not None and persisted != effective:
    report["ok"] = False
    report["failures"].append("canonical_env_postcondition_failed")
gate = readiness_requires_disable_bridge(
    linas_has_published_cm=linas_published,
    effective_disable_bridge=persisted,
)
out = {"preserve": report, "readiness": gate}
print(json.dumps(out, indent=2, ensure_ascii=False))
if not report.get("ok") or not gate.get("ok"):
    print("[cm-durable-flags] COMPLETE_FAIL")
    raise SystemExit(2)
print("[cm-durable-flags] COMPLETE_OK")
PY
