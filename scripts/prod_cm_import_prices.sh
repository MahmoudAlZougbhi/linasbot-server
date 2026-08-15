#!/usr/bin/env bash
# Import proven numeric Linas prices from production price_files into CM draft prices.
# Never invents amounts. Archives ambiguous lines for Mahmoud review. Does not publish.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard \
  "scripts/prod_cm_import_prices.sh" \
  "scripts/prod_cm_repair_linas_prices_publish.sh"

APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"
STAGING="${LINASBOT_DATA_ROOT}/tenants/${TENANT_ID}/cm/staging/price_import"
REPORT_DIR="${LINASBOT_DATA_ROOT}/tenants/${TENANT_ID}/cm/reports"
mkdir -p "$REPORT_DIR" "$STAGING"

echo "[cm-price-import] deployed_sha=$(git rev-parse HEAD)"
echo "[cm-price-import] tenant=$TENANT_ID staging=$STAGING"

/opt/linasbot/venv/bin/python - <<PY
from __future__ import annotations

import json
import os
from pathlib import Path

def load_env() -> None:
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

load_env()
os.environ.setdefault("LINASBOT_DATA_ROOT", "/opt/linasbot_data")
os.environ.setdefault("ENVIRONMENT", "production")

from services.cm.pricing.migration import migrate_staged_price_files_to_catalog
from services.cm.prod_migration import stage_live_data_for_migration
from services.cm.storage import get_draft
from services.cm.validation import validate_cm

tenant_id = "${TENANT_ID}"
data_root = Path(os.environ["LINASBOT_DATA_ROOT"])
staging = Path("${STAGING}")
report_dir = Path("${REPORT_DIR}")

stage = stage_live_data_for_migration(
    data_root=data_root,
    staging_root=staging,
    app_data_root=Path("/opt/linasbot/data"),
)
pricing = migrate_staged_price_files_to_catalog(
    staging_root=staging,
    tenant_id=tenant_id,
    updated_by="prod_cm_import_prices",
    category_id="body_area",
    category_label="Body areas",
    item_type="body_area",
)
draft = get_draft("prices", tenant_id=tenant_id, create_default=True)
payload = draft.payload if hasattr(draft, "payload") else {}
validation = validate_cm(tenant_id=tenant_id)
ambiguous_path = staging / "legacy" / "price_archive" / "ambiguous_lines.json"
ambiguous_count = 0
if ambiguous_path.is_file():
    try:
        ambiguous_count = int((json.loads(ambiguous_path.read_text(encoding="utf-8")) or {}).get("count") or 0)
    except Exception:
        ambiguous_count = 0

out = {
    "tenant_id": tenant_id,
    "stage_copied_count": len(stage.get("copied") or []),
    "stage_missing": stage.get("missing"),
    "pricing_import": pricing,
    "draft_catalog_count": len(payload.get("catalog") or []),
    "draft_price_entry_count": len(payload.get("price_entries") or []),
    "draft_legacy_items_count": len(payload.get("items") or []),
    "ambiguous_archived": ambiguous_count,
    "validation": {
        "ok": validation.get("ok"),
        "error_count": validation.get("error_count"),
        "warning_count": validation.get("warning_count"),
    },
    "needs_mahmoud_input": [],
}
if ambiguous_count:
    out["needs_mahmoud_input"].append(
        f"{ambiguous_count} ambiguous price lines archived at staging/legacy/price_archive/ambiguous_lines.json"
    )
if int(pricing.get("rows_imported") or 0) == 0 and int(out["draft_price_entry_count"]) == 0:
    out["needs_mahmoud_input"].append("no_proven_numeric_price_rows_imported")

path = report_dir / "price_import_report.json"
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
print(json.dumps(out, indent=2, ensure_ascii=False))
print(f"[cm-price-import] report={path}")
if not validation.get("ok"):
    print("[cm-price-import] COMPLETE_FAIL_VALIDATION")
    raise SystemExit(2)
if int(out["draft_price_entry_count"]) <= 0 and int(pricing.get("price_entry_count") or 0) <= 0:
    print("[cm-price-import] COMPLETE_FAIL_EMPTY")
    raise SystemExit(2)
print("[cm-price-import] COMPLETE_OK")
PY
