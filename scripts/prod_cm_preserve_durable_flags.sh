#!/usr/bin/env bash
# Preserve durable CM ops flags across dual .env paths used by production deploy.
# Never prints secret values. Safe to run on every deploy before service restart.
set -euo pipefail

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
    default_production_env_paths,
    preserve_disable_linas_legacy_bridge,
    readiness_requires_disable_bridge,
)
from services.cm.constants import tenant_has_published_cm

app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
paths = default_production_env_paths(app_dir=app_dir)
linas_published = tenant_has_published_cm("linas")
report = preserve_disable_linas_legacy_bridge(
    paths,
    linas_has_published_cm=linas_published,
    dry_run=False,
)
gate = readiness_requires_disable_bridge(
    linas_has_published_cm=linas_published,
    effective_disable_bridge=report.get("effective"),
)
out = {"preserve": report, "readiness": gate}
print(json.dumps(out, indent=2, ensure_ascii=False))
if not report.get("ok") or not gate.get("ok"):
    print("[cm-durable-flags] COMPLETE_FAIL")
    raise SystemExit(2)
print("[cm-durable-flags] COMPLETE_OK")
PY
