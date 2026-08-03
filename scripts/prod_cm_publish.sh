#!/usr/bin/env bash
# Publish immutable CM version + OpenAI semantic index while customer traffic stays on legacy.
# Requires CM_PUBLISH_ENABLED=true and CM_RUNTIME_MODE=legacy (or published after cutover).
set -euo pipefail

APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export CM_EMBEDDING_PROVIDER="${CM_EMBEDDING_PROVIDER:-openai}"
export CM_EMBEDDING_MODEL="${CM_EMBEDDING_MODEL:-text-embedding-3-small}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"
REPORT_DIR="${LINASBOT_DATA_ROOT}/tenants/${TENANT_ID}/cm/reports"
mkdir -p "$REPORT_DIR"

echo "[cm-publish] deployed_sha=$(git rev-parse HEAD)"
echo "[cm-publish] embedding_provider=$CM_EMBEDDING_PROVIDER model=$CM_EMBEDDING_MODEL"

/opt/linasbot/venv/bin/python - <<PY
import asyncio
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
os.environ.setdefault("CM_EMBEDDING_PROVIDER", "${CM_EMBEDDING_PROVIDER}")
os.environ.setdefault("CM_EMBEDDING_MODEL", "${CM_EMBEDDING_MODEL}")
if not (os.environ.get("OPENAI_API_KEY") or "").strip():
    raise SystemExit("[cm-publish] OPENAI_API_KEY missing after .env load")
print("[cm-publish] env_loaded=true")

from services.cm.constants import cm_publish_enabled, cm_runtime_mode
from services.cm.embeddings import embedding_pin
from services.cm.publish import publish_draft
from services.cm.publish_gate import ensure_publish_enabled
from services.cm.validation import validate_cm

if not cm_publish_enabled():
    raise SystemExit("[cm-publish] CM_PUBLISH_ENABLED is false; aborting")
if cm_runtime_mode() == "published":
    print("[cm-publish] warning=runtime already published; publish still allowed")

pin = embedding_pin()
if pin.provider != "openai":
    raise SystemExit(f"[cm-publish] refusing non-openai provider={pin.provider}")

ensure_publish_enabled()
validation = validate_cm(tenant_id="${TENANT_ID}")
if not validation.get("ok"):
    print(json.dumps({"validation_error_count": validation.get("error_count")}, ensure_ascii=False))
    raise SystemExit("[cm-publish] validation blocked publish")

async def _run():
    return await publish_draft(tenant_id="${TENANT_ID}", published_by="prod_cm_publish")

result = asyncio.run(_run())
out = {
    "tenant_id": result.tenant_id,
    "content_version_id": result.content_version_id,
    "index_version_id": result.index_version_id,
    "embedding": {
        "provider": pin.provider,
        "model": pin.model,
        "version": pin.version,
        "dimensions": pin.dimensions,
    },
    "pointer": result.pointer,
    "previous_pointer": result.previous_pointer,
    "runtime_mode": cm_runtime_mode(),
    "publish_enabled": cm_publish_enabled(),
}
path = Path("${REPORT_DIR}") / "publish_report.json"
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
print(f"[cm-publish] report={path}")
print(f"[cm-publish] content_version_id={result.content_version_id}")
print(f"[cm-publish] index_version_id={result.index_version_id}")
print(f"[cm-publish] embedding_provider={pin.provider} model={pin.model} dims={pin.dimensions}")
print("[cm-publish] COMPLETE_OK")
PY
