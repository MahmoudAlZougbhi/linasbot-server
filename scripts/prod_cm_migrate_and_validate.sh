#!/usr/bin/env bash
# Stage live content, migrate into CM drafts, seed owner-confirmed truth, validate.
# Keeps CM_RUNTIME_MODE=legacy. Does not publish. Never prints FAQ/content bodies.
set -euo pipefail

APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"
STAGING="${LINASBOT_DATA_ROOT}/tenants/${TENANT_ID}/cm/staging/prod_migration"
REPORT_DIR="${LINASBOT_DATA_ROOT}/tenants/${TENANT_ID}/cm/reports"
mkdir -p "$REPORT_DIR"

echo "[cm-migrate] deployed_sha=$(git rev-parse HEAD)"
echo "[cm-migrate] data_root=$LINASBOT_DATA_ROOT tenant=$TENANT_ID"

/opt/linasbot/venv/bin/python - <<PY
import json
from pathlib import Path
from services.cm.prod_migration import run_production_content_migration
from services.cm.validation import validate_cm
from services.cm.sot_audit import audit_sot_sources

report = run_production_content_migration(
    data_root=Path("${LINASBOT_DATA_ROOT}"),
    staging_root=Path("${STAGING}"),
    tenant_id="${TENANT_ID}",
    updated_by="prod_cm_migration",
)
validation = validate_cm(tenant_id="${TENANT_ID}")
sot = audit_sot_sources()
out = {
    "migration": {
        "tenant_id": report["tenant_id"],
        "conflict_count": report["conflict_count"],
        "publish_ready": report["publish_ready"],
        "faq_groups_imported": report["migrate"]["faq_groups_imported"],
        "knowledge_articles_imported": report["migrate"]["knowledge_articles_imported"],
        "care_articles_imported": report["migrate"]["care_articles_imported"],
        "handoff_contacts_imported": report["migrate"]["handoff_contacts_imported"],
        "seeded": report["seeded"],
        "scrub_faq_removed": len(report["scrub"]["faq_removed"]),
        "scrub_knowledge_archived": len(report["scrub"]["knowledge_archived_ids"]),
        "conflicts": report["conflicts"],
        "stage_missing": report["stage"]["missing"],
        "stage_copied_count": len(report["stage"]["copied"]),
    },
    "validation": {
        "ok": validation.get("ok"),
        "error_count": validation.get("error_count"),
        "warning_count": validation.get("warning_count"),
        "errors": validation.get("errors"),
    },
    "sot": {
        "source_count": len(sot.get("sources") or sot) if isinstance(sot, dict) else None,
        "raw_type": type(sot).__name__,
    },
}
# Normalize SoT summary without dumping file contents
if isinstance(sot, dict) and "sources" in sot:
    out["sot"]["ungated"] = [
        s.get("id") or s.get("path")
        for s in sot["sources"]
        if s.get("referenced_in") and not s.get("fully_gated_by_cm_runtime_mode")
    ]
elif isinstance(sot, list):
    out["sot"]["ungated"] = [
        s.get("id") or s.get("path")
        for s in sot
        if s.get("referenced_in") and not s.get("fully_gated_by_cm_runtime_mode")
    ]

path = Path("${REPORT_DIR}") / "migration_report.json"
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
print(f"[cm-migrate] report={path}")
print(f"[cm-migrate] conflict_count={out['migration']['conflict_count']}")
print(f"[cm-migrate] validation_ok={out['validation']['ok']} errors={out['validation']['error_count']}")
print(f"[cm-migrate] faq_groups={out['migration']['faq_groups_imported']}")
if out["migration"]["conflict_count"] or not out["validation"]["ok"]:
    print("[cm-migrate] BLOCKED_NOT_PUBLISH_READY")
    raise SystemExit(2)
print("[cm-migrate] COMPLETE_OK")
PY
