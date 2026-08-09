#!/usr/bin/env bash
# Read-only Linas legacy-bridge readiness check.
set -euo pipefail
cd /opt/linasbot
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"

echo "[bridge-readiness] deployed_sha=$(git rev-parse HEAD)"
/opt/linasbot/venv/bin/python scripts/cm_prepare_remove_linas_bridge.py --tenant linas
