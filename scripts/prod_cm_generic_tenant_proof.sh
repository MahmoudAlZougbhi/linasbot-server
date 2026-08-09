#!/usr/bin/env bash
# Production-safe generic tenant CM runtime proof (isolated tenant id; no Meta assets).
# Creates/publishes/deletes only under tenants/<proof_tenant>/cm. Never touches linas.
set -euo pipefail
cd /opt/linasbot
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"

echo "[generic-proof] deployed_sha=$(git rev-parse HEAD)"

/opt/linasbot/venv/bin/python - <<'PY'
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
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

from services.cm.constants import tenant_uses_cm_runtime
from services.cm.publish import publish_draft
from services.cm.schemas import AiBasics, BranchesSection, BranchRecord, HandoffContact, HandoffMatrixRow, HandoffPolicy, LocalizedLabels, ServicesSection, ServiceRecord
from services.cm.storage import ensure_defaults, get_draft, put_draft
from services.cm.version_store import load_published_content
from handlers.text_handlers_respond import _handle_published_cm_runtime

PROOF_TENANT = "cutover_proof_saas"
LEAK_TERMS = [
    "marwa",
    "linas laser",
    "laser hair",
    "tattoo",
    "beirut",
    "antelias",
    "khaled",
    "78847527",
    "70707354",
    "71534928",
    "71226082",
]

data_root = Path(os.environ["LINASBOT_DATA_ROOT"])
tenant_root = data_root / "tenants" / PROOF_TENANT
report: dict = {
    "tenant_id": PROOF_TENANT,
    "steps": [],
    "leaks": [],
    "ok": False,
    "meta_asset_e2e": "pending_no_safe_test_asset",
}

# Clean any prior proof tenant
if tenant_root.exists():
    shutil.rmtree(tenant_root)
    report["steps"].append("removed_prior_proof_tenant")

ensure_defaults(tenant_id=PROOF_TENANT, updated_by="cutover_proof")


def _overwrite(section: str, payload: dict) -> None:
    env = get_draft(section, tenant_id=PROOF_TENANT, create_default=True)
    put_draft(
        section,
        payload=payload,
        if_match=env.etag,
        tenant_id=PROOF_TENANT,
        updated_by="cutover_proof",
    )


_overwrite(
    "ai_basics",
    AiBasics(
        assistant_name="Nova Concierge",
        clinic_name="Green Field Cafe",
        ai_role="cafe concierge",
        business_purpose="Help customers of Green Field Cafe with menu and location questions.",
        short_introduction="Hi, I'm Nova Concierge for Green Field Cafe.",
        advanced_instructions="Never invent other brands. Never mention Linas, Marwa, laser, tattoo, Beirut, or Antelias.",
    ).model_dump(mode="json"),
)
_overwrite(
    "services",
    ServicesSection(
        items=[
            ServiceRecord(
                id="espresso",
                labels=LocalizedLabels(en="Espresso", ar="إسبريسو", fr="Espresso"),
                available=True,
            )
        ]
    ).model_dump(mode="json"),
)
_overwrite(
    "branches",
    BranchesSection(
        items=[
            BranchRecord(
                id="downtown",
                labels=LocalizedLabels(en="Downtown", ar="داون تاون", fr="Centre-ville"),
                available=True,
            )
        ]
    ).model_dump(mode="json"),
)
contact = HandoffContact(
    id="cafe_whatsapp",
    phone_e164="+96171111111",
    label="Cafe WhatsApp",
    gender="any",
    branch_id="downtown",
)
_overwrite(
    "handoff",
    HandoffPolicy(
        contacts=[contact],
        matrix=[HandoffMatrixRow(id="row_cafe", contact_id=contact.id, enabled=True, branch_id="downtown")],
    ).model_dump(mode="json"),
)
report["steps"].append("configured_cm_drafts")

async def _publish_and_probe() -> None:
    result = await publish_draft(tenant_id=PROOF_TENANT, published_by="cutover_proof")
    report["published"] = {
        "content_version_id": result.content_version_id,
        "index_version_id": result.index_version_id,
    }
    report["steps"].append("published")
    assert tenant_uses_cm_runtime(PROOF_TENANT) is True
    report["tenant_uses_cm_runtime"] = True
    pointer, sections = load_published_content(PROOF_TENANT)
    report["loaded_identity"] = {
        "assistant_name": (sections.get("ai_basics") or {}).get("assistant_name"),
        "clinic_name": (sections.get("ai_basics") or {}).get("clinic_name"),
        "content_version_id": pointer.content_version_id,
    }
    probes = [
        "What do you sell?",
        "Where are you located?",
        "I want to talk to a human",
    ]
    outs = []
    for msg in probes:
        text, meta = await _handle_published_cm_runtime(
            tenant_id=PROOF_TENANT,
            message=msg,
            detected_language="en",
            response_language="en",
        )
        blob = f"{text}\n{json.dumps(meta, ensure_ascii=False)}"
        low = blob.lower()
        found = [t for t in LEAK_TERMS if t in low]
        outs.append(
            {
                "message": msg,
                "reason": meta.get("reason"),
                "content_version_id": meta.get("content_version_id") or pointer.content_version_id,
                "reply_preview": str(text or "")[:140].replace("\n", " "),
                "leaks": found,
            }
        )
        report["leaks"].extend(found)
    report["probes"] = outs

asyncio.run(_publish_and_probe())

# Cleanup proof tenant data so production stays clean
if tenant_root.exists():
    shutil.rmtree(tenant_root)
    report["steps"].append("cleaned_proof_tenant")

report["ok"] = (
    report.get("tenant_uses_cm_runtime") is True
    and not report["leaks"]
    and str((report.get("loaded_identity") or {}).get("assistant_name") or "").lower() == "nova concierge"
)
print(json.dumps(report, indent=2, ensure_ascii=False))
print("[generic-proof] COMPLETE_OK" if report["ok"] else "[generic-proof] COMPLETE_WITH_FAILURES")
raise SystemExit(0 if report["ok"] else 2)
PY
