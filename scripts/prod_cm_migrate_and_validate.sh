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
if not (os.environ.get("OPENAI_API_KEY") or "").strip():
    raise SystemExit("[cm-migrate] OPENAI_API_KEY missing after .env load")
print("[cm-migrate] env_loaded=true")

from services.cm.prod_migration import run_production_content_migration
from services.cm.sot_audit import audit_sot_sources
from services.cm.validation import validate_cm

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
        "stage_copied_names": sorted({Path(c["dest"]).name for c in report["stage"]["copied"]}),
        "qa_stats": report.get("qa_stats"),
        "redistribution": {
            "mapped": (report.get("redistribution") or {}).get("mapped"),
            "active_knowledge": (report.get("redistribution") or {}).get("active_knowledge"),
            "archived_knowledge": (report.get("redistribution") or {}).get("archived_knowledge"),
            "services_count": (report.get("redistribution") or {}).get("services_count"),
            "availability_conflicts": (report.get("redistribution") or {}).get("availability_conflicts"),
            "ledger_path": (report.get("redistribution") or {}).get("ledger_path"),
            "ledger": (report.get("redistribution") or {}).get("ledger"),
        },
        "section_counts_before": report.get("section_counts_before"),
        "section_counts_after": report.get("section_counts_after"),
    },
    "validation": {
        "ok": validation.get("ok"),
        "error_count": validation.get("error_count"),
        "warning_count": validation.get("warning_count"),
        "errors": validation.get("errors"),
    },
    "sot": {
        "source_count": len(sot.get("sources") or []) if isinstance(sot, dict) else None,
    },
}
if isinstance(sot, dict) and "sources" in sot:
    out["sot"]["ungated"] = [
        s.get("id") or s.get("path")
        for s in sot["sources"]
        if s.get("referenced_in") and not s.get("fully_gated_by_cm_runtime_mode")
    ]

path = Path("${REPORT_DIR}") / "migration_report.json"
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
print(f"[cm-migrate] report={path}")
print(f"[cm-migrate] conflict_count={out['migration']['conflict_count']}")
print(f"[cm-migrate] validation_ok={out['validation']['ok']} errors={out['validation']['error_count']}")
print(f"[cm-migrate] faq_groups={out['migration']['faq_groups_imported']}")
print(f"[cm-migrate] knowledge_articles={out['migration']['knowledge_articles_imported']}")
print(f"[cm-migrate] stage_copied={out['migration']['stage_copied_names']}")
print(f"[cm-migrate] stage_missing={out['migration']['stage_missing']}")
print(f"[cm-migrate] qa_stats={out['migration'].get('qa_stats')}")
print(f"[cm-migrate] scrub_faq_removed={out['migration']['scrub_faq_removed']}")
print(f"[cm-migrate] pricing_import={out['migration']['seeded'].get('pricing_import')}")
print(f"[cm-migrate] prices_structured={out['migration']['seeded'].get('prices_structured')}")
print(f"[cm-migrate] conflict_codes={[c.get('code') for c in out['migration']['conflicts']]}")
print(
    f"[cm-migrate] validation_codes={[e.get('code') or e.get('rule') or e.get('message') for e in (out['validation'].get('errors') or [])]}"
)
print(f"[cm-migrate] sot_ungated={out['sot'].get('ungated')}")
if "qa_pairs.jsonl" in out["migration"]["stage_missing"]:
    print("[cm-migrate] BLOCKED_MISSING_QA_SOURCE")
    raise SystemExit(3)
if out["migration"]["faq_groups_imported"] < 1 and "qa_pairs.jsonl" in out["migration"]["stage_copied_names"]:
    print("[cm-migrate] BLOCKED_EMPTY_QA_IMPORT")
    raise SystemExit(3)
if out["migration"]["conflict_count"] or not out["validation"]["ok"]:
    print("[cm-migrate] BLOCKED_NOT_PUBLISH_READY")
    raise SystemExit(2)
print("[cm-migrate] COMPLETE_OK")
PY
