#!/usr/bin/env bash
# Read-only published-mode SoT audit summary (no file bodies / secrets).
set -euo pipefail
cd /opt/linasbot
echo "[sot-audit] deployed_sha=$(git rev-parse HEAD)"
/opt/linasbot/venv/bin/python - <<'PY'
import json
from services.cm.sot_audit import audit_sot_sources

report = audit_sot_sources()
ungated = [
    {"id": s.get("id"), "referenced_in": s.get("referenced_in"), "exists": s.get("exists")}
    for s in report.get("sources", [])
    if s.get("referenced_in") and not s.get("fully_gated_by_cm_runtime_mode")
]
gated = [
    s.get("id")
    for s in report.get("sources", [])
    if s.get("referenced_in") and s.get("fully_gated_by_cm_runtime_mode")
]
print(
    json.dumps(
        {
            "ungated_count": len(ungated),
            "gated_ids": gated,
            "ungated": ungated,
            "scanned_files": report.get("scanned_files"),
        },
        indent=2,
        ensure_ascii=False,
    )
)
print("[sot-audit] COMPLETE_OK")
PY
