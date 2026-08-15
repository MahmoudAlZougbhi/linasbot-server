#!/usr/bin/env bash
# Repair Linas draft identity from published SoT, keep/import proven prices, probe catalog match, publish.
# Never invents amounts or assistant names. Does not enable Meta comments.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_cm_repair_linas_prices_publish.sh"

APP_DIR="/opt/linasbot"
cd "$APP_DIR"
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"
export CM_EMBEDDING_PROVIDER="${CM_EMBEDDING_PROVIDER:-openai}"
export CM_EMBEDDING_MODEL="${CM_EMBEDDING_MODEL:-text-embedding-3-small}"
TENANT_ID="${LINASBOT_TENANT_ID:-linas}"
REPORT_DIR="${LINASBOT_DATA_ROOT}/tenants/${TENANT_ID}/cm/reports"
mkdir -p "$REPORT_DIR"

echo "[cm-price-repair] deployed_sha=$(git rev-parse HEAD)"
echo "[cm-price-repair] tenant=$TENANT_ID"

# Re-run proven price import first (idempotent overwrite of structured catalog).
bash /opt/linasbot/scripts/prod_cm_import_prices.sh

/opt/linasbot/venv/bin/python - <<'PY'
from __future__ import annotations

import asyncio
import json
import os
import re
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

from services.cm.constants import cm_publish_enabled
from services.cm.pricing.catalog_resolve import disambiguate_matches, resolve_catalog_item_ids
from services.cm.pricing.section import normalize_prices_section, section_catalog_items, section_price_entries
from services.cm.publish import publish_draft
from services.cm.publish_gate import ensure_publish_enabled
from services.cm.storage import get_draft, put_draft
from services.cm.validation import validate_cm
from services.cm.version_store import load_published_content, read_published_pointer

tenant_id = "linas"
report_dir = Path(os.environ["LINASBOT_DATA_ROOT"]) / "tenants" / tenant_id / "cm" / "reports"
staging = Path(os.environ["LINASBOT_DATA_ROOT"]) / "tenants" / tenant_id / "cm" / "staging" / "price_import"
ambiguous_path = staging / "legacy" / "price_archive" / "ambiguous_lines.json"

pointer, published_sections = load_published_content(tenant_id)
pub_ai = dict(published_sections.get("ai_basics") or {})
draft_ai_env = get_draft("ai_basics", tenant_id=tenant_id, create_default=True)
draft_ai = dict(draft_ai_env.payload or {})

def _looks_like_linas(name: object) -> bool:
    text = str(name or "").strip().lower()
    return "lina" in text or "linas" in text

identity_actions: list[str] = []
draft_name = draft_ai.get("assistant_name")
pub_name = pub_ai.get("assistant_name")
if not _looks_like_linas(draft_name) and _looks_like_linas(pub_name):
    # Restore polluted draft identity from currently published (authoritative) SoT only.
    for key in (
        "assistant_name",
        "clinic_name",
        "business_type",
        "system_prompt",
        "prompt",
        "persona",
        "grounding_facts",
    ):
        if key in pub_ai:
            draft_ai[key] = pub_ai[key]
    put_draft(
        "ai_basics",
        payload=draft_ai,
        if_match=draft_ai_env.etag,
        tenant_id=tenant_id,
        updated_by="prod_cm_repair_linas_prices_publish",
    )
    identity_actions.append("restored_ai_basics_from_published")
elif not _looks_like_linas(draft_name) and not _looks_like_linas(pub_name):
    identity_actions.append("BLOCKED_no_authoritative_linas_assistant_name")
else:
    identity_actions.append("draft_identity_ok")

prices_env = get_draft("prices", tenant_id=tenant_id, create_default=True)
prices_section = normalize_prices_section(prices_env.payload or {})
catalog = section_catalog_items(prices_section)
entries = section_price_entries(prices_section)

catalog_rows = []
for item in catalog[:80]:
    entry = next((e for e in entries if e.catalog_item_id == item.id), None)
    catalog_rows.append(
        {
            "id": item.id,
            "label_en": item.labels.en,
            "label_ar": item.labels.ar,
            "aliases": list(item.aliases)[:6],
            "currency": item.currency,
            "amount": entry.amount if entry is not None else item.base_price,
            "active": item.active,
        }
    )

probe_messages = [
    "How much is underarm laser?",
    "كم سعر الإبط؟",
    "سعر تحت الإبط",
]
if catalog_rows:
    first_label = catalog_rows[0].get("label_en") or catalog_rows[0].get("label_ar") or catalog_rows[0]["id"]
    probe_messages.append(f"How much is {first_label}?")

match_probes = []
for msg in probe_messages:
    matches = resolve_catalog_item_ids(msg, catalog)
    single, ambiguous = disambiguate_matches(matches)
    match_probes.append(
        {
            "message": msg,
            "match_count": len(matches),
            "single_id": single,
            "ambiguous_ids": ambiguous,
            "top": [
                {"id": m.catalog_item_id, "score": m.score, "alias": m.matched_alias}
                for m in matches[:5]
            ],
        }
    )

ambiguous_count = 0
ambiguous_reasons: dict[str, int] = {}
if ambiguous_path.is_file():
    try:
        amb = json.loads(ambiguous_path.read_text(encoding="utf-8")) or {}
        ambiguous_count = int(amb.get("count") or 0)
        for entry in amb.get("entries") or []:
            if isinstance(entry, dict):
                reason = str(entry.get("reason") or "unknown")
                ambiguous_reasons[reason] = ambiguous_reasons.get(reason, 0) + 1
    except Exception:
        ambiguous_count = -1

needs_mahmoud: list[str] = []
if ambiguous_count > 0:
    needs_mahmoud.append(
        f"{ambiguous_count} ambiguous price lines archived (reasons={ambiguous_reasons}); "
        "Mahmoud must confirm service/branch/variant amounts before import."
    )
underarm_hit = any(
    p.get("single_id") and "underarm" in p.get("message", "").lower()
    for p in match_probes
) or any(
    p.get("single_id") and "إبط" in p.get("message", "")
    for p in match_probes
)
if not underarm_hit:
    needs_mahmoud.append(
        "underarm / إبط has no unambiguous catalog match among proven imported rows; "
        "confirm the authoritative label/amount for underarm laser (and branch/variant if any)."
    )

validation = validate_cm(tenant_id=tenant_id)
draft_ai_after = get_draft("ai_basics", tenant_id=tenant_id, create_default=False)
assistant_after = (draft_ai_after.payload or {}).get("assistant_name") if draft_ai_after else None

out = {
    "tenant_id": tenant_id,
    "published_before": {
        "content_version_id": pointer.content_version_id,
        "index_version_id": pointer.index_version_id,
        "assistant_name": pub_name,
    },
    "identity_actions": identity_actions,
    "draft_assistant_name_after": assistant_after,
    "catalog_count": len(catalog),
    "price_entry_count": len(entries),
    "catalog_sample": catalog_rows[:30],
    "match_probes": match_probes,
    "ambiguous_archived": ambiguous_count,
    "ambiguous_reasons": ambiguous_reasons,
    "needs_mahmoud_input": needs_mahmoud,
    "validation": {
        "ok": validation.get("ok"),
        "error_count": validation.get("error_count"),
        "warning_count": validation.get("warning_count"),
    },
    "publish": None,
}

if "BLOCKED_no_authoritative_linas_assistant_name" in identity_actions:
    out["ok"] = False
    path = report_dir / "price_repair_report.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[cm-price-repair] report={path}")
    print("[cm-price-repair] COMPLETE_FAIL_IDENTITY")
    raise SystemExit(2)

if not validation.get("ok"):
    out["ok"] = False
    path = report_dir / "price_repair_report.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[cm-price-repair] report={path}")
    print("[cm-price-repair] COMPLETE_FAIL_VALIDATION")
    raise SystemExit(2)

if len(catalog) <= 0 or len(entries) <= 0:
    out["ok"] = False
    path = report_dir / "price_repair_report.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[cm-price-repair] report={path}")
    print("[cm-price-repair] COMPLETE_FAIL_EMPTY_CATALOG")
    raise SystemExit(2)

if not cm_publish_enabled():
    raise SystemExit("[cm-price-repair] CM_PUBLISH_ENABLED is false; aborting")
ensure_publish_enabled()

async def _publish():
    return await publish_draft(tenant_id=tenant_id, published_by="prod_cm_repair_linas_prices_publish")

result = asyncio.run(_publish())
out["publish"] = {
    "content_version_id": result.content_version_id,
    "index_version_id": result.index_version_id,
    "previous_pointer": result.previous_pointer,
}
out["ok"] = True

# Prefer a probe message that actually resolves to a catalog item for runtime_proof guidance.
preferred_probe = next((p for p in match_probes if p.get("single_id")), None)
out["preferred_price_probe_message"] = preferred_probe["message"] if preferred_probe else None

path = report_dir / "price_repair_report.json"
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(out, indent=2, ensure_ascii=False))
print(f"[cm-price-repair] report={path}")
print(f"[cm-price-repair] content_version_id={result.content_version_id}")
print(f"[cm-price-repair] index_version_id={result.index_version_id}")
print("[cm-price-repair] COMPLETE_OK")
PY
