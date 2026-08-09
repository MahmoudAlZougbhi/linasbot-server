#!/usr/bin/env bash
# Read-only Linas legacy-bridge readiness check (loads EnvironmentFile .env values).
set -euo pipefail
cd /opt/linasbot
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"

echo "[bridge-readiness] deployed_sha=$(git rev-parse HEAD)"

# Load CM_* flags from durable EnvironmentFile paths into this process env.
set -a
# shellcheck disable=SC1091
if [ -f /opt/linasbot/.env ]; then
  # Prefer python loader below; keep shell env minimal.
  :
fi
set +a

/opt/linasbot/venv/bin/python - <<'PY'
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

def load_env() -> None:
    for env_path in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, value = s.split("=", 1)
            key = key.strip()
            if key:
                os.environ[key] = value.strip().strip("'").strip('"')

load_env()
os.environ.setdefault("LINASBOT_DATA_ROOT", "/opt/linasbot_data")
os.environ.setdefault("ENVIRONMENT", "production")
sys.argv = ["cm_prepare_remove_linas_bridge.py", "--tenant", "linas"]
try:
    runpy.run_path("/opt/linasbot/scripts/cm_prepare_remove_linas_bridge.py", run_name="__main__")
except SystemExit as exc:
    code = exc.code
    raise SystemExit(int(code) if isinstance(code, int) else (0 if code is None else 1))
PY
