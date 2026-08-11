#!/usr/bin/env bash
# Upsert Owner Copilot V2 + Customer Reply AI V2 production flags and restart.
# Never prints secret values.
# Usage: prod_apply_copilot_v2_flags.sh
set -euo pipefail

REPO_ROOT="/opt/linasbot"
CANONICAL_SUBDIR="$REPO_ROOT/linaslaserbot-2.7.22"
APP_DIR="$REPO_ROOT"
if [ -f "$CANONICAL_SUBDIR/main.py" ]; then
  APP_DIR="$CANONICAL_SUBDIR"
fi

export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
export CM_PRESERVE_APP_DIR="$APP_DIR"

PYTHON_BIN="/opt/linasbot/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from services.cm.durable_flags import default_production_env_paths, upsert_env_file

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
# Explicitly do NOT set LINAS_REQUIRE_REDIS=true
app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
for path in default_production_env_paths(app_dir=app_dir):
    if not path.parent.exists():
        continue
    upsert_env_file(path, updates)
    print(f"[copilot-v2-flags] upserted path={path} keys={sorted(updates)}")

# Ensure Redis requirement stays off if present
for path in default_production_env_paths(app_dir=app_dir):
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    lines = []
    changed = False
    for line in text.splitlines():
        if line.startswith("LINAS_REQUIRE_REDIS="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'").lower()
            if val in {"1", "true", "yes", "on"}:
                lines.append("LINAS_REQUIRE_REDIS=false")
                changed = True
                continue
        lines.append(line)
    if changed:
        path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
        print(f"[copilot-v2-flags] forced LINAS_REQUIRE_REDIS=false path={path}")
PY

# Keep durable bridge flag synced
if [ -x /opt/linasbot/scripts/prod_cm_preserve_durable_flags.sh ] || [ -f /opt/linasbot/scripts/prod_cm_preserve_durable_flags.sh ]; then
  bash /opt/linasbot/scripts/prod_cm_preserve_durable_flags.sh "$APP_DIR" || true
fi

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

app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
from services.cm.durable_flags import default_production_env_paths
paths = default_production_env_paths(app_dir=app_dir)
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
