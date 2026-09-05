"""If Luna returns no business files, attach published knowledge/services for DMs."""

from __future__ import annotations

from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_reply_v2.models import EvidenceRecord, RetrievalResult
from services.customer_reply_v2.retrieval_item_index import raw_rows_for_section, record_content

_DM_CHANNELS = frozenset({"instagram_dm", "facebook_dm", "instagram", "facebook"})
_BUSINESS_SECTIONS = frozenset(
    {
        "knowledge",
        "services",
        "prices",
        "branches",
        "products",
        "opening_hours",
        "care",
        "faq",
    }
)
_FALLBACK_SECTIONS: tuple[tuple[str, int], ...] = (("knowledge", 8), ("services", 6), ("care", 4))
_MAX_ITEM_CHARS = 1800


def _is_dm_channel(channel: str) -> bool:
    return str(channel or "").strip().lower() in _DM_CHANNELS


def _has_business_evidence(retrieval: RetrievalResult) -> bool:
    return any(str(item.section_id or "") in _BUSINESS_SECTIONS for item in retrieval.evidence)


def ensure_dm_business_evidence(
    retrieval: RetrievalResult,
    *,
    tenant_id: str,
    channel: str,
) -> RetrievalResult:
    """Keep Luna's picks. Only fill empty DMs so Tera is not greeting-only."""

    if not tenant_id or not _is_dm_channel(channel):
        return retrieval
    if retrieval.error and str(retrieval.error).startswith("retrieval_model_blocker:"):
        return retrieval
    if _has_business_evidence(retrieval):
        return retrieval
    try:
        pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return retrieval

    revision = str(pointer.content_version_id or "")
    existing = {item.source_id for item in retrieval.evidence}
    added: list[EvidenceRecord] = []
    for section_id, limit in _FALLBACK_SECTIONS:
        payload = sections.get(section_id)
        if not isinstance(payload, dict):
            continue
        count = 0
        for raw in raw_rows_for_section(payload):
            if count >= limit:
                break
            item_id = str(raw.get("id") or "").strip()
            if not item_id:
                continue
            source_id = f"{section_id}:{item_id}"
            if source_id in existing:
                continue
            content = record_content(section_id, raw)[:_MAX_ITEM_CHARS].strip()
            if not content:
                continue
            title = str(raw.get("title") or item_id)
            added.append(
                EvidenceRecord(
                    source_id=source_id,
                    section_id=section_id,
                    title=title,
                    content=content,
                    published_revision=revision,
                )
            )
            existing.add(source_id)
            count += 1

    if not added:
        return retrieval

    retrieval.evidence = list(retrieval.evidence) + added
    retrieval.selected_source_ids = [*retrieval.selected_source_ids, *[item.source_id for item in added]]
    extra_sections = [item.section_id for item in added if item.section_id not in retrieval.selected_section_ids]
    retrieval.selected_section_ids = [*retrieval.selected_section_ids, *extra_sections]
    if retrieval.evidence_status in {"insufficient_final", "insufficient_can_retry"}:
        retrieval.evidence_status = "sufficient"
    retrieval.tool_trace = [
        *list(retrieval.tool_trace or []),
        {
            "tool": "ensure_dm_business_evidence",
            "ok": True,
            "added": len(added),
            "sections": extra_sections,
        },
    ]
    return retrieval
