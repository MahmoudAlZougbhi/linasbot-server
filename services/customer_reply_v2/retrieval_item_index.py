"""Item index helpers for Retrieval Luna (no AI Basics/Style bodies)."""

from __future__ import annotations

import json
from typing import Any

from services.customer_reply_v2.models import ItemIndexEntry

MAX_ITEMS_PER_SECTION = 80
MAX_ITEMS_PER_READ = 20
MAX_EVIDENCE_CHARS = 12000


def label_of(labels: Any) -> str:
    if isinstance(labels, dict):
        return str(labels.get("en") or labels.get("ar") or labels.get("fr") or "").strip()
    return str(getattr(labels, "en", "") or getattr(labels, "ar", "") or "").strip()


def iter_section_items(section_id: str, payload: dict[str, Any]) -> list[ItemIndexEntry]:
    entries: list[ItemIndexEntry] = []
    items = payload.get("items")
    if isinstance(items, list):
        for raw in items[:MAX_ITEMS_PER_SECTION]:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or raw.get("qa_group_id") or "").strip()
            if not item_id:
                continue
            title = str(raw.get("title") or label_of(raw.get("labels")) or item_id)
            desc = str(raw.get("notes") or raw.get("body") or raw.get("short_introduction") or "")[:240]
            status = str(raw.get("status") or ("active" if raw.get("available", True) else "inactive"))
            if status == "draft":
                continue
            entries.append(
                ItemIndexEntry(
                    item_id=f"{section_id}:{item_id}",
                    section_id=section_id,
                    title=title,
                    short_description=desc,
                    language=str(raw.get("language") or ""),
                    status=status,
                    relations={
                        "service_id": raw.get("service_id"),
                        "linked_service_ids": raw.get("linked_service_ids") or [],
                        "linked_branch_ids": raw.get("linked_branch_ids") or [],
                        "category": raw.get("category"),
                    },
                )
            )
        return entries
    topics = payload.get("topics")
    if isinstance(topics, list):
        for raw in topics[:MAX_ITEMS_PER_SECTION]:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or "").strip()
            if not item_id:
                continue
            entries.append(
                ItemIndexEntry(
                    item_id=f"{section_id}:{item_id}",
                    section_id=section_id,
                    title=label_of(raw.get("labels")) or item_id,
                    short_description="restricted topic" if section_id == "restricted" else "",
                    status="active" if raw.get("active", True) else "inactive",
                )
            )
        return entries
    rules = payload.get("rules")
    if isinstance(rules, list):
        for raw in rules[:MAX_ITEMS_PER_SECTION]:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or "").strip()
            if not item_id:
                continue
            title = str(raw.get("name") or raw.get("title") or item_id)
            status = "active" if raw.get("enabled", True) else "inactive"
            entries.append(
                ItemIndexEntry(
                    item_id=f"{section_id}:{item_id}",
                    section_id=section_id,
                    title=title,
                    short_description=str(raw.get("notes") or raw.get("action") or "")[:240],
                    status=status,
                    relations={"post_id": raw.get("post_id"), "action": raw.get("action")},
                )
            )
    return entries


def record_content(section_id: str, raw: dict[str, Any]) -> str:
    if section_id == "faq":
        variants = raw.get("variants") or []
        bits = []
        for v in variants:
            if isinstance(v, dict):
                bits.append(f"Q({v.get('language')}): {v.get('question')} | A: {v.get('answer')}")
        return "\n".join(bits)
    if section_id == "prices":
        return json.dumps(
            {
                "id": raw.get("id"),
                "service_id": raw.get("service_id"),
                "amount": raw.get("amount"),
                "currency": raw.get("currency"),
                "catalog_item_id": raw.get("catalog_item_id"),
            },
            ensure_ascii=False,
        )
    if section_id == "branches":
        return json.dumps(
            {
                "id": raw.get("id"),
                "labels": raw.get("labels"),
                "address": raw.get("address"),
                "hours": raw.get("hours"),
            },
            ensure_ascii=False,
        )
    if section_id == "comments":
        return json.dumps(
            {
                "id": raw.get("id"),
                "name": raw.get("name"),
                "action": raw.get("action"),
                "match_mode": raw.get("match_mode"),
                "keywords": raw.get("keywords") or [],
                "post_id": raw.get("post_id"),
                "notes": raw.get("notes") or "",
                "ai_instructions": raw.get("ai_instructions") or "",
                "ai_action_mode": raw.get("ai_action_mode") or raw.get("action"),
                "scope": raw.get("scope") or ("specific_post" if raw.get("post_id") else "all_posts"),
                "priority": raw.get("priority") or 0,
                "revision": raw.get("revision") or 1,
            },
            ensure_ascii=False,
        )
    body = raw.get("body") or raw.get("notes") or ""
    title = raw.get("title") or label_of(raw.get("labels"))
    text = f"{title}\n{body}".strip()
    if section_id in {"knowledge", "care"}:
        from services.cm.article_media import format_attachments_block

        att_block = format_attachments_block(list(raw.get("attachments") or []))
        if att_block:
            text = f"{text}\n\n{att_block}".strip() if text else att_block
    return text


def raw_rows_for_section(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "topics", "rules"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []
