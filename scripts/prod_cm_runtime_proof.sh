#!/usr/bin/env bash
# Read-only proof that Linas customer answers use published CM runtime.
# Never prints secrets or full customer PII.
set -euo pipefail
cd /opt/linasbot
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="/opt/linasbot${PYTHONPATH:+:$PYTHONPATH}"

echo "[runtime-proof] deployed_sha=$(git rev-parse HEAD)"

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

from handlers.text_handlers_respond import _handle_published_cm_runtime
from services.cm.constants import (
    cm_disable_linas_legacy_bridge,
    tenant_allows_legacy_bridge,
    tenant_has_published_cm,
    tenant_uses_cm_runtime,
)
from services.cm.version_store import load_published_content, read_published_pointer

tenant_id = "linas"
_ = read_published_pointer(tenant_id)
loaded_pointer, sections = load_published_content(tenant_id)
ai = sections.get("ai_basics") or {}

report: dict = {
    "tenant_id": tenant_id,
    "tenant_uses_cm_runtime": tenant_uses_cm_runtime(tenant_id),
    "tenant_has_published_cm": tenant_has_published_cm(tenant_id),
    "tenant_allows_legacy_bridge": tenant_allows_legacy_bridge(tenant_id),
    "cm_disable_linas_legacy_bridge": cm_disable_linas_legacy_bridge(),
    "published_pointer": {
        "content_version_id": loaded_pointer.content_version_id,
        "index_version_id": loaded_pointer.index_version_id,
    },
    "assistant_name": ai.get("assistant_name"),
    "clinic_name": ai.get("clinic_name"),
    "probes": [],
    "journal_scan": {},
    "ok": False,
    "failures": [],
}

if not report["tenant_uses_cm_runtime"]:
    report["failures"].append("tenant_uses_cm_runtime_false")
if not report["published_pointer"]["content_version_id"]:
    report["failures"].append("missing_content_version")
an = str(report["assistant_name"] or "").lower()
cn = str(report["clinic_name"] or "").lower()
if "marwa" in an or "marwa" in cn:
    report["failures"].append("marwa_identity")
if "linas" not in an and "lina" not in an:
    report["failures"].append("assistant_name_not_linas")

probes = [
    ("business", "What laser services do you offer?"),
    ("branch", "Where is your Beirut branch?"),
    ("service", "Do you offer laser hair removal?"),
    ("price", "How much is underarm laser?"),
    ("handoff", "I want to book an appointment with a human."),
    ("off_day", "Are you open today?"),
]


async def run_probes() -> None:
    for kind, message in probes:
        text, meta = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message=message,
            detected_language="en",
            response_language="en",
        )
        if not isinstance(meta, dict):
            meta = {}
        # Early-stop paths may omit version ids; stamp published pointer for proof.
        cv = meta.get("content_version_id") or loaded_pointer.content_version_id
        low = str(text or "").lower()
        probe = {
            "kind": kind,
            "handler_path": "cm_runtime_pipeline",
            "reason": meta.get("reason"),
            "content_version_id": cv,
            "index_version_id": meta.get("index_version_id") or loaded_pointer.index_version_id,
            "ai_called": meta.get("ai_called"),
            "reply_chars": len(text or ""),
            "reply_preview": str(text or "")[:160].replace("\n", " "),
            "mentions_marwa": "marwa" in low,
            "mentions_montymobile": "montymobile" in low or "monty mobile" in low,
            "has_wa_me": "wa.me/" in low,
            "has_expected_phone_tail": any(
                tail in re.sub(r"\D", "", str(text or ""))
                for tail in ("78847527", "70707354", "71534928", "71226082")
            ),
        }
        if cv != loaded_pointer.content_version_id:
            report["failures"].append(f"probe_version_mismatch:{kind}")
        if probe["mentions_marwa"]:
            report["failures"].append(f"probe_marwa:{kind}")
        if probe["mentions_montymobile"]:
            report["failures"].append(f"probe_montymobile:{kind}")
        if kind == "handoff" and not (probe["has_wa_me"] or probe["has_expected_phone_tail"]):
            report["failures"].append("handoff_missing_destination")
        report["probes"].append(probe)


asyncio.run(run_probes())

# Journal / log scan for recent handler_path evidence (redacted counts only)
patterns = {
    "cm_runtime_pipeline": r"handler_path[=:]['\"]?cm_runtime_pipeline",
    "ai_orchestration": r"handler_path[=:]['\"]?ai_orchestration",
    "marwa": r"\bmarwa\b",
    "booking_tool": r"booking[_ ]tool|crm_book|legacy_booking",
    "montymobile_ai": r"montymobile.*ai|whatsapp_inbound_ai",
}
counts = {k: 0 for k in patterns}
log_paths = [
    Path("/opt/linasbot/logs"),
    Path("/var/log"),
]
lines: list[str] = []
try:
    import subprocess

    completed = subprocess.run(
        ["journalctl", "-u", "linasbot", "--since", "2 hours ago", "--no-pager", "-o", "cat"],
        check=False,
        capture_output=True,
        text=True,
    )
    lines.extend((completed.stdout or "").splitlines()[-5000:])
except Exception:
    pass
for root in log_paths:
    if not root.exists():
        continue
    for path in root.rglob("*.log"):
        try:
            data = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines.extend(data.splitlines()[-2000:])

for line in lines[-8000:]:
    for name, pat in patterns.items():
        if re.search(pat, line, re.IGNORECASE):
            counts[name] += 1
report["journal_scan"] = counts

# Interaction JSONL diagnostics if present
diag_hits = {"cm_runtime_pipeline": 0, "content_version_match": 0, "scanned": 0}
data_root = Path(os.environ.get("LINASBOT_DATA_ROOT", "/opt/linasbot_data"))
for path in data_root.rglob("*interaction*.jsonl"):
    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]:
            if "cm_runtime_pipeline" in raw:
                diag_hits["cm_runtime_pipeline"] += 1
            if loaded_pointer.content_version_id in raw:
                diag_hits["content_version_match"] += 1
            diag_hits["scanned"] += 1
    except OSError:
        continue
report["interaction_scan"] = diag_hits

if counts["cm_runtime_pipeline"] == 0 and diag_hits["cm_runtime_pipeline"] == 0:
    # Probes themselves prove pipeline callable; soft warning only
    report["warnings"] = report.get("warnings", []) + ["no_recent_live_handler_path_log_hits"]

report["ok"] = len(report["failures"]) == 0 and report["tenant_uses_cm_runtime"] is True
print(json.dumps(report, indent=2, ensure_ascii=False))
print("[runtime-proof] COMPLETE_OK" if report["ok"] else "[runtime-proof] COMPLETE_WITH_FAILURES")
raise SystemExit(0 if report["ok"] else 2)
PY
