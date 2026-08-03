#!/usr/bin/env bash
# Atomic CM content+index pointer rollback to an existing published version.
# Does not rebuild embeddings. Does not invent content. Requires CM_PUBLISH_ENABLED=true.
set -euo pipefail

APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"
TARGET="${CM_ROLLBACK_CONTENT_VERSION_ID:-}"

if [ -z "$TARGET" ]; then
  echo "[cm-rollback-version] missing CM_ROLLBACK_CONTENT_VERSION_ID" >&2
  exit 1
fi

echo "[cm-rollback-version] deployed_sha=$(git rev-parse HEAD)"
echo "[cm-rollback-version] target=${TARGET}"

/opt/linasbot/venv/bin/python - <<PY
import json
import os
from pathlib import Path

def _load_env() -> None:
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
                os.environ.setdefault(key, value.strip().strip("'").strip('"'))

_load_env()

from services.cm.constants import cm_publish_enabled
from services.cm.publish import RollbackTargetError, rollback_to_version
from services.cm.version_store import read_published_pointer

if not cm_publish_enabled():
    raise SystemExit("[cm-rollback-version] CM_PUBLISH_ENABLED is false; aborting")

before = read_published_pointer("${TENANT_ID}")
print("[cm-rollback-version] before=" + json.dumps({
    "content_version_id": getattr(before, "content_version_id", None) if before else None,
    "index_version_id": getattr(before, "index_version_id", None) if before else None,
}, ensure_ascii=False))

try:
    result = rollback_to_version(tenant_id="${TENANT_ID}", content_version_id="${TARGET}")
except RollbackTargetError as exc:
    raise SystemExit(f"[cm-rollback-version] {exc}") from exc

print("[cm-rollback-version] after=" + json.dumps({
    "content_version_id": result.content_version_id,
    "index_version_id": result.index_version_id,
}, ensure_ascii=False))
print("[cm-rollback-version] COMPLETE_OK")
PY
