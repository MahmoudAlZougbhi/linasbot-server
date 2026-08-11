"""CM article/FAQ upsert proposal builders and tools (LOC split from owner_ai_tools_cm_content)."""

from __future__ import annotations

import uuid
from typing import Any

from services.owner_ai_tools_base import ToolResult
from services.owner_ai_tools_cm_content import (
    ARTICLE_SECTIONS,
    _article_meta,
    _faq_meta,
    _load_section_items,
    _normalize_section,
    _require,
)

def _build_article_upsert(
    *,
    tenant_id: str,
    section: str,
    article: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (patch, focused_preview) for a single article upsert."""
    from services.cm.schemas import ArticleRecord

    name = _normalize_section(section)
    if name not in ARTICLE_SECTIONS:
        raise ValueError(f"section must be one of {sorted(ARTICLE_SECTIONS)}")
    if not isinstance(article, dict):
        raise ValueError("article must be an object")

    items, payload, env = _load_section_items(tenant_id, name)
    del payload
    aid = str(article.get("id") or "").strip()
    existing_idx = next((i for i, row in enumerate(items) if str(row.get("id") or "") == aid), None) if aid else None
    action = "update" if existing_idx is not None else "create"

    if action == "create":
        if not aid:
            aid = f"art_{uuid.uuid4().hex[:12]}"
        base: dict[str, Any] = {
            "id": aid,
            "title": "",
            "body": "",
            "tags": [],
            "language": "",
            "audience": "general",
            "category": "",
            "status": "active",
            "source_filename": None,
            "source_checksum": None,
            "linked_service_ids": [],
            "linked_branch_ids": [],
            "notes": None,
            "attachments": [],
        }
        before: dict[str, Any] | None = None
    else:
        assert existing_idx is not None
        base = dict(items[existing_idx])
        before = _article_meta(base, section=name)
        before["body_preview"] = str(base.get("body") or "")[:240]

    allowed = (
        "title",
        "body",
        "tags",
        "language",
        "audience",
        "category",
        "status",
        "source_filename",
        "notes",
        "linked_service_ids",
        "linked_branch_ids",
        "attachments",
    )
    for key in allowed:
        if key in article:
            base[key] = article[key]
    base["id"] = aid
    validated = ArticleRecord.model_validate(base).model_dump(mode="json")

    if action == "create":
        items.append(validated)
    else:
        assert existing_idx is not None
        items[existing_idx] = validated

    patch = {"items": items}
    after = _article_meta(validated, section=name)
    body_text = str(validated.get("body") or "")
    after["body_preview"] = body_text[:240]
    title = str(validated.get("title") or aid)
    before_body = ""
    if isinstance(before, dict):
        before_body = str(before.get("body_preview") or "")
    preview = {
        "section": name,
        "kind": "article_upsert",
        "action": action,
        "article_id": aid,
        "field": title,
        "changed_keys": ["items"],
        "before": before,
        "after": after,
        # Focused item for Review-in-CM local overlay (not the full items list).
        "proposed_item": validated,
        "current_value": before_body,
        "proposed_value": f"{title}\n\n{body_text}".strip()[:4000],
        "revision": getattr(env, "revision", None),
        "item_count_after": len(items),
    }
    return patch, preview


def _build_faq_upsert(
    *,
    tenant_id: str,
    faq: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from services.cm.schemas import FaqRecord

    if not isinstance(faq, dict):
        raise ValueError("faq must be an object")
    items, _payload, env = _load_section_items(tenant_id, "faq")
    gid = str(faq.get("qa_group_id") or "").strip()
    existing_idx = (
        next((i for i, row in enumerate(items) if str(row.get("qa_group_id") or "") == gid), None) if gid else None
    )
    action = "update" if existing_idx is not None else "create"

    if action == "create":
        if not gid:
            gid = f"qa_{uuid.uuid4().hex[:10]}"
        base: dict[str, Any] = {
            "qa_group_id": gid,
            "variants": [],
            "tags": [],
            "notes": None,
            "status": "draft",
            "source_language": None,
            "reviewed": False,
            "provenance": "owner_copilot",
            "revision": 1,
        }
        before = None
    else:
        assert existing_idx is not None
        base = dict(items[existing_idx])
        before = _faq_meta(base)

    for key in ("variants", "tags", "notes", "status", "source_language", "reviewed", "provenance", "revision"):
        if key in faq:
            base[key] = faq[key]
    base["qa_group_id"] = gid
    validated = FaqRecord.model_validate(base).model_dump(mode="json")

    if action == "create":
        items.append(validated)
    else:
        assert existing_idx is not None
        items[existing_idx] = validated

    after_meta = _faq_meta(validated)
    raw_variants = validated.get("variants")
    variants: list[Any] = list(raw_variants) if isinstance(raw_variants, list) else []
    variant_bits: list[str] = []
    for row in variants:
        if not isinstance(row, dict):
            continue
        lang = str(row.get("language") or "")
        q = str(row.get("question") or "").strip()
        a = str(row.get("answer") or "").strip()
        if q or a:
            variant_bits.append(f"[{lang}] Q: {q}\nA: {a}".strip())
    proposed_text = "\n\n".join(variant_bits).strip() or f"FAQ {gid}"
    preview = {
        "section": "faq",
        "kind": "faq_upsert",
        "action": action,
        "qa_group_id": gid,
        "field": gid,
        "changed_keys": ["items"],
        "before": before,
        "after": after_meta,
        "proposed_item": validated,
        "current_value": "",
        "proposed_value": proposed_text[:4000],
        "revision": getattr(env, "revision", None),
        "item_count_after": len(items),
    }
    return {"items": items}, preview


async def tool_propose_cm_article_upsert(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    section: str,
    article: dict[str, Any],
    replace_proposal_id: str | None = None,
) -> ToolResult:
    _require(role, "contentManagers")
    from services.owner_ai_cm_approval import cm_patch_proposal_store, reject_cm_patch

    try:
        patch, preview = _build_article_upsert(tenant_id=tenant_id, section=section, article=article)
    except Exception as exc:
        return ToolResult(
            ok=False,
            name="propose_cm_article_upsert",
            data={},
            error=f"{type(exc).__name__}: {exc}",
        )

    if replace_proposal_id:
        try:
            reject_cm_patch(tenant_id=tenant_id, user_id=user_id, proposal_id=str(replace_proposal_id))
        except Exception:
            pass

    prop = cm_patch_proposal_store.create(
        tenant_id=tenant_id,
        user_id=user_id,
        section=preview["section"],
        patch=patch,
        preview=preview,
    )
    data = {
        "proposal_id": prop.id,
        "confirmation_token": f"approve_cm_patch:{prop.id}",
        "preview": preview,
        "status": prop.status,
        "requires_confirmation": True,
        "section": preview["section"],
        "article_id": preview.get("article_id"),
        "action": preview.get("action"),
    }
    return ToolResult(
        ok=True,
        name="propose_cm_article_upsert",
        data=data,
        requires_confirmation=True,
        confirmation_token=str(data["confirmation_token"]),
        error="Confirmation required before CM draft is saved",
    )


async def tool_propose_cm_faq_upsert(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    faq: dict[str, Any],
    replace_proposal_id: str | None = None,
) -> ToolResult:
    _require(role, "contentManagers")
    from services.owner_ai_cm_approval import cm_patch_proposal_store, reject_cm_patch

    try:
        patch, preview = _build_faq_upsert(tenant_id=tenant_id, faq=faq)
    except Exception as exc:
        return ToolResult(
            ok=False,
            name="propose_cm_faq_upsert",
            data={},
            error=f"{type(exc).__name__}: {exc}",
        )

    if replace_proposal_id:
        try:
            reject_cm_patch(tenant_id=tenant_id, user_id=user_id, proposal_id=str(replace_proposal_id))
        except Exception:
            pass

    prop = cm_patch_proposal_store.create(
        tenant_id=tenant_id,
        user_id=user_id,
        section="faq",
        patch=patch,
        preview=preview,
    )
    data = {
        "proposal_id": prop.id,
        "confirmation_token": f"approve_cm_patch:{prop.id}",
        "preview": preview,
        "status": prop.status,
        "requires_confirmation": True,
        "section": "faq",
        "qa_group_id": preview.get("qa_group_id"),
        "action": preview.get("action"),
    }
    return ToolResult(
        ok=True,
        name="propose_cm_faq_upsert",
        data=data,
        requires_confirmation=True,
        confirmation_token=str(data["confirmation_token"]),
        error="Confirmation required before CM draft is saved",
    )
