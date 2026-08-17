"""Invalidate / version-link FAQ Smart Answers when related CM content changes."""

from __future__ import annotations

import re
import time
from typing import Any

_SESSION_RANGE_RE = re.compile(
    r"\b(\d+)\s*(?:-|–|to|إلى|a)\s*(\d+)\s*(?:sessions?|جلسات|séances?)?\b",
    re.I,
)
_SESSION_SINGLE_RE = re.compile(r"\b(\d+)\s*(?:sessions?|جلسات|séances?)\b", re.I)


def _text_blob(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, dict):
        return " ".join(_text_blob(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_text_blob(v) for v in obj)
    return str(obj)


def extract_session_markers(text: str) -> set[str]:
    markers: set[str] = set()
    for a, b in _SESSION_RANGE_RE.findall(text or ""):
        markers.add(f"{a}-{b}")
    for n in _SESSION_SINGLE_RE.findall(text or ""):
        markers.add(n)
    return markers


def related_faq_group_ids(*, tenant_id: str, section: str, patch: dict[str, Any]) -> list[str]:
    """Find FAQ groups that likely depend on the patched CM section content."""
    from services.cm.faq_integration import list_cm_faq

    patch_blob = _text_blob(patch).lower()
    section_l = (section or "").strip().lower()
    session_markers = extract_session_markers(patch_blob)
    hits: list[str] = []
    for item in list_cm_faq(tenant_id=tenant_id, include_archived=False):
        gid = str(item.get("qa_group_id") or "")
        if not gid:
            continue
        variants = item.get("variants") or []
        blob = " ".join(
            f"{v.get('question', '')} {v.get('answer', '')}" for v in variants if isinstance(v, dict)
        ).lower()
        tags = " ".join(str(t) for t in (item.get("tags") or [])).lower()
        related = False
        if section_l in {"services", "basics", "locations", "prices", "hours", "style"}:
            if section_l in tags or section_l in blob:
                related = True
        if session_markers and extract_session_markers(blob) & session_markers:
            related = True
        # Location / service keyword overlap
        for key in ("location", "address", "service", "موقع", "خدمة"):
            if key in patch_blob and key in blob:
                related = True
        if related:
            hits.append(gid)
    return sorted(set(hits))


def mark_faq_groups_stale(
    *,
    tenant_id: str,
    qa_group_ids: list[str],
    reason: str,
    cm_section: str,
    cm_revision: Any = None,
) -> dict[str, Any]:
    """Mark FAQ groups + local QA rows stale and version-link to CM change."""
    from services.cm.faq_integration import get_cm_faq_group, list_cm_faq
    from services.cm.schemas import FaqSection
    from services.cm.storage import get_draft, put_draft
    from services.local_qa_service import local_qa_service

    if not qa_group_ids:
        return {"stale_groups": [], "stale_rows": 0, "reason": reason}

    env = get_draft("faq", tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    stale_set = set(qa_group_ids)
    updated_items = []
    marked: list[str] = []
    for item in section.items:
        if item.qa_group_id in stale_set and item.status not in {"archived", "restricted"}:
            notes = (item.notes or "") + f"\n[stale:{reason}]"
            updated_items.append(
                item.model_copy(
                    update={
                        "status": "needs_review",
                        "notes": notes.strip(),
                        "revision": item.revision + 1,
                        "reviewed": False,
                    }
                )
            )
            marked.append(item.qa_group_id)
        else:
            updated_items.append(item)

    if marked:
        from services.cm.faq_integration_helpers import faq_section_payload

        put_draft(
            "faq",
            payload=faq_section_payload(
                items=updated_items,
                notes=section.notes,
                smart_answer_languages=section.smart_answer_languages,
            ),
            if_match=env.etag,
            tenant_id=tenant_id,
            updated_by="faq_cm_invalidation",
        )

    stale_rows = 0
    for pair in local_qa_service.qa_pairs:
        if str(pair.get("tenant_id") or "").lower() != tenant_id.lower():
            continue
        if pair.get("qa_group_id") in stale_set:
            pair["cm_stale"] = True
            pair["stale"] = True
            pair["status"] = "needs_review"
            pair["stale_reason"] = reason
            pair["cm_section"] = cm_section
            pair["cm_revision"] = cm_revision
            pair["stale_at"] = time.time()
            stale_rows += 1
    if stale_rows:
        local_qa_service.save_to_jsonl()

    # Touch listed groups that may only exist in local qa
    for gid in qa_group_ids:
        if get_cm_faq_group(qa_group_id=gid, tenant_id=tenant_id) is None:
            continue

    return {
        "stale_groups": marked,
        "stale_rows": stale_rows,
        "reason": reason,
        "cm_section": cm_section,
        "known_groups": [i.get("qa_group_id") for i in list_cm_faq(tenant_id=tenant_id, include_archived=True)],
    }


def invalidate_faq_for_cm_patch(
    *,
    tenant_id: str,
    section: str,
    patch: dict[str, Any],
    cm_revision: Any = None,
) -> dict[str, Any]:
    gids = related_faq_group_ids(tenant_id=tenant_id, section=section, patch=patch)
    reason = f"cm_patch:{section}"
    # Special case: session count range changes (7 → 7-10)
    blob = _text_blob(patch)
    markers = extract_session_markers(blob)
    if markers:
        reason = f"session_markers_changed:{','.join(sorted(markers))}"
    return mark_faq_groups_stale(
        tenant_id=tenant_id,
        qa_group_ids=gids,
        reason=reason,
        cm_section=section,
        cm_revision=cm_revision,
    )
