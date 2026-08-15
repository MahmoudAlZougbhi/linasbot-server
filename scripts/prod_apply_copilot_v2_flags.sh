#!/usr/bin/env bash
# Upsert Owner Copilot V2 + Customer Reply AI V2 production flags and restart.
# Never prints secret values.
# Usage: prod_apply_copilot_v2_flags.sh
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_apply_copilot_v2_flags.sh"

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
from pathlib import Path

from scripts.ha.production_env_cas import atomic_update_canonical_env

updates = {
    # Owner V2 brain (also code-default true)
    "OWNER_COPILOT_V2": "true",
    # Required for CM Approve / propose→approve write path in production
    "OWNER_COPILOT_WRITES": "true",
    # Customer Reply V2 is unconditional in code; keep semantic retrieval + media on
    "CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED": "true",
    "CUSTOMER_MEDIA_CONTEXT_ENABLED": "true",
    "LINAS_CUSTOMER_RETRIEVAL_MODEL": "gpt-5.6-luna",
    "LINAS_CUSTOMER_ANSWER_MODEL": "gpt-5.6-terra",
    "LINAS_CUSTOMER_MODEL": "gpt-5.6-terra",
    # Preserve required production constraints
    "CM_DISABLE_LINAS_LEGACY_BRIDGE": "true",
}
path = Path("/opt/linasbot/.env")
for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
    if line.startswith("LINAS_REQUIRE_REDIS="):
        value = line.split("=", 1)[1].strip().strip('"').strip("'").lower()
        if value in {"1", "true", "yes", "on"}:
            updates["LINAS_REQUIRE_REDIS"] = "false"
        break
atomic_update_canonical_env(updates)
print(f"[copilot-v2-flags] canonical_env_updated=true keys={sorted(updates)}")
PY

systemctl restart linasbot
sleep 3
systemctl is-active linasbot

# Redacted verification (no secrets)
"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

def read_flag(paths, key, default=""):
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default

paths = [Path("/opt/linasbot/.env")]
keys = [
    "OWNER_COPILOT_V2",
    "OWNER_COPILOT_WRITES",
    "CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED",
    "CUSTOMER_MEDIA_CONTEXT_ENABLED",
    "LINAS_CUSTOMER_RETRIEVAL_MODEL",
    "LINAS_CUSTOMER_ANSWER_MODEL",
    "CM_DISABLE_LINAS_LEGACY_BRIDGE",
    "LINAS_REQUIRE_REDIS",
]
print("[copilot-v2-flags] effective:")
for k in keys:
    print(f"  {k}={read_flag(paths, k, '<unset>')}")
PY

echo "[copilot-v2-flags] COMPLETE_OK"
