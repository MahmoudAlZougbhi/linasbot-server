#!/usr/bin/env bash
# FAQ-only publish: draft FAQ over current published base + semantic index (no dirty non-FAQ drafts).
set -euo pipefail
APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"

echo "[cm-faq-publish] deployed_sha=$(git rev-parse HEAD)"

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
from services.cm.publish import publish_faq_only
from services.cm.publish_gate import ensure_publish_enabled
from services.cm.storage import get_draft
from services.cm.schemas import FaqSection

ensure_publish_enabled()
faq = FaqSection.model_validate(get_draft("faq", tenant_id="${TENANT_ID}", create_default=True).payload)
print(f"[cm-faq-publish] draft_faq_groups={len(faq.items)}")

result = asyncio.run(
    publish_faq_only(tenant_id="${TENANT_ID}", published_by="prod_cm_faq_only", notes="faq_only_publish")
)
print(f"[cm-faq-publish] content_version_id={result.content_version_id}")
print(f"[cm-faq-publish] index_version_id={result.index_version_id}")
print(json.dumps({"pointer": result.pointer, "previous": result.previous_pointer}, ensure_ascii=False))
print("[cm-faq-publish] COMPLETE_OK")
PY
