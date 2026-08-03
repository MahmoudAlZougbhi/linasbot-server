#!/usr/bin/env bash
# Atomic CM runtime cutover: require published pointer with openai embeddings, then set
# CM_RUNTIME_MODE=published and restart. Explicit rollback script exists separately.
set -euo pipefail

APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"
REPORT_DIR="${LINASBOT_DATA_ROOT}/tenants/${TENANT_ID}/cm/reports"
mkdir -p "$REPORT_DIR"

echo "[cm-cutover] verifying published pointer before flipping runtime"

/opt/linasbot/venv/bin/python - <<PY
import json
from pathlib import Path
from services.cm.embeddings import assert_published_embedding_pin
from services.cm.version_store import load_published_content

pointer, sections = load_published_content("${TENANT_ID}")
assert_published_embedding_pin(pointer.embedding_provider, context="cutover_pointer")
if not pointer.index_version_id:
    raise SystemExit("published pointer missing index_version_id")
if not sections:
    raise SystemExit("published content empty")
out = {
    "content_version_id": pointer.content_version_id,
    "index_version_id": pointer.index_version_id,
    "embedding_provider": pointer.embedding_provider,
    "embedding_model": pointer.embedding_model,
    "embedding_dimensions": pointer.embedding_dimensions,
    "section_count": len(sections),
}
Path("${REPORT_DIR}/cutover_precheck.json").write_text(json.dumps(out, indent=2) + "\\n", encoding="utf-8")
print(f"[cm-cutover] precheck_ok content={pointer.content_version_id} index={pointer.index_version_id}")
PY

export CM_RUNTIME_MODE_VALUE=published
export CM_PUBLISH_ENABLED_VALUE=true
export CM_EMBEDDING_PROVIDER_VALUE=openai
export CM_EMBEDDING_MODEL_VALUE=text-embedding-3-small
sudo -E bash /opt/linasbot/scripts/prod_cm_apply_flags.sh

# Post-cutover readiness probe (local)
sleep 3
curl -fsS http://127.0.0.1:8003/api/ready >/tmp/cm_cutover_ready.json || curl -fsS http://127.0.0.1:8000/api/ready >/tmp/cm_cutover_ready.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/cm_cutover_ready.json").read_text())
assert data.get("ok") is True
print("[cm-cutover] ready_ok=true")
PY

echo "[cm-cutover] COMPLETE_OK"
