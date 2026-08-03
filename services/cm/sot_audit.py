"""Read-only Source-of-Truth (SoT) audit (plan §14 / Phase 8 cutover prep).

Lists legacy, hardcoded Linas business-fact sources that remain on disk/in code, and reports
whether response-generation code paths still consult them outside the
``CM_RUNTIME_MODE == "published"`` gate. This is a REPORT ONLY tool — it never deletes, edits,
or disables anything; a human decides what to retire once CM becomes the sole source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from storage.persistent_storage import (
    KNOWLEDGE_BASE_FILE,
    PRICE_LIST_FILE,
    QA_PAIRS_FILE,
    STYLE_GUIDE_FILE,
    SYSTEM_PROMPT_TEMPLATE_FILE,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_PUBLISHED_MODE_GATE_MARKERS: tuple[str, ...] = (
    "CM AI CONTROL PLANE",
    'cm_runtime_mode() == "published"',
)


@dataclass(frozen=True)
class SotSource:
    id: str
    description: str
    kind: str  # "content_file" | "code_default"
    path: Path | None = None
    module: str | None = None
    attribute: str | None = None


#: Hand-maintained registry of known hardcoded/legacy Linas business-fact sources. Extending
#: this list is the normal way to widen audit coverage; the audit never discovers sources by
#: itself (no full-repo crawl / no guessing).
LEGACY_BUSINESS_FACT_SOURCES: tuple[SotSource, ...] = (
    SotSource(
        id="price_list_file",
        description="Legacy price list text file (loaded into config.PRICE_LIST)",
        kind="content_file",
        path=PRICE_LIST_FILE,
    ),
    SotSource(
        id="style_guide_file",
        description="Legacy bot style guide text file (loaded into config.BOT_STYLE_GUIDE)",
        kind="content_file",
        path=STYLE_GUIDE_FILE,
    ),
    SotSource(
        id="knowledge_base_file",
        description="Legacy core knowledge base text file (loaded into config.CORE_KNOWLEDGE_BASE)",
        kind="content_file",
        path=KNOWLEDGE_BASE_FILE,
    ),
    SotSource(
        id="system_prompt_template_file",
        description="Legacy system prompt template file (loaded into config.SYSTEM_PROMPT_TEMPLATE)",
        kind="content_file",
        path=SYSTEM_PROMPT_TEMPLATE_FILE,
    ),
    SotSource(
        id="qa_pairs_jsonl",
        description="Legacy Local Q&A store used by LocalQAService for exact/direct FAQ matching",
        kind="content_file",
        path=QA_PAIRS_FILE,
    ),
    SotSource(
        id="default_whatsapp_contacts",
        description="Hardcoded default WhatsApp handoff numbers",
        kind="code_default",
        module="services.social_contact_routing",
        attribute="DEFAULT_SOCIAL_WHATSAPP_CONTACTS",
    ),
    SotSource(
        id="default_dynamic_messages",
        description="Hardcoded default dynamic bot messages (dynamic_messages_service defaults)",
        kind="code_default",
        module="services.dynamic_messages_service",
        attribute="DEFAULT_DYNAMIC_MESSAGES",
    ),
)

#: Response-generation entry points in scope for this audit. Fixed, hand-maintained scope —
#: NOT a full-repo crawl — so results are predictable and reviewable.
SCAN_TARGET_FILES: tuple[str, ...] = (
    "handlers/text_handlers_respond.py",
    "services/chat_response_service.py",
    "services/local_qa_service.py",
    "services/social_contact_routing.py",
    "config.py",
    "utils/utils.py",
)


def _file_status(path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {"exists": exists, "size_bytes": path.stat().st_size if exists else 0}


def _read_scanned_file(rel_path: str) -> str | None:
    full = _PROJECT_ROOT / rel_path
    try:
        return full.read_text(encoding="utf-8")
    except OSError:
        return None


def _references_in_scanned_files(needle: str) -> list[str]:
    hits: list[str] = []
    for rel in SCAN_TARGET_FILES:
        text = _read_scanned_file(rel)
        if text and needle in text:
            hits.append(rel)
    return hits


def _reference_is_gated(rel_path: str) -> bool:
    """Heuristic-only: True if this file's legacy code appears reachable ONLY when
    ``CM_RUNTIME_MODE`` is NOT "published" (i.e. the file also contains the published-mode
    early-return gate). Purely informational — never used to change runtime behavior.
    """
    text = _read_scanned_file(rel_path)
    if not text:
        return False
    return all(marker in text for marker in _PUBLISHED_MODE_GATE_MARKERS)


def audit_sot_sources() -> dict[str, Any]:
    """Build the read-only SoT audit report. Never mutates any file."""
    findings: list[dict[str, Any]] = []
    for source in LEGACY_BUSINESS_FACT_SOURCES:
        entry: dict[str, Any] = {"id": source.id, "description": source.description, "kind": source.kind}
        if source.path is not None:
            entry["path"] = str(source.path)
            entry.update(_file_status(source.path))
            needle = source.path.name
        else:
            entry["module"] = source.module
            entry["attribute"] = source.attribute
            needle = str(source.attribute)

        referenced_in = _references_in_scanned_files(needle)
        entry["referenced_in"] = referenced_in
        entry["fully_gated_by_cm_runtime_mode"] = bool(referenced_in) and all(
            _reference_is_gated(rel) for rel in referenced_in
        )
        findings.append(entry)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scanned_files": list(SCAN_TARGET_FILES),
        "sources": findings,
        "note": (
            "Report only — no files were modified or deleted. A source with exists=True and "
            "referenced_in=[] is orphaned legacy data, safe to review for manual archival. A "
            "source referenced outside a CM_RUNTIME_MODE=published gate remains an active "
            "fallback risk that must be reviewed before Phase 8 cutover."
        ),
    }
