"""Deterministic read tools against published CM / cards / products."""

from __future__ import annotations

from typing import Any

from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.normalize import normalize_search_text
from services.customer_ai.retrieve.cards import TitleCard, load_published_cards
from services.customer_ai.retrieve.lexical import search_cards
from services.customer_ai.retrieve.products import load_product_cards


def _sections(tenant_id: str) -> dict[str, Any]:
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return {}
    return sections if isinstance(sections, dict) else {}


def _items(sections: dict[str, Any], key: str) -> list[dict[str, Any]]:
    payload = sections.get(key)
    if not isinstance(payload, dict):
        return []
    rows = payload.get("items") or payload.get("catalog") or []
    return [row for row in rows if isinstance(row, dict)]


def _label(row: dict[str, Any]) -> str:
    labels = row.get("labels")
    if isinstance(labels, dict):
        for key in ("en", "ar", "fr", "franco"):
            value = str(labels.get(key) or "").strip()
            if value:
                return value
    return str(row.get("title") or row.get("name") or row.get("id") or "").strip()


def _match_id(rows: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    needle = (item_id or "").strip()
    if not needle:
        return None
    for row in rows:
        rid = str(row.get("id") or row.get("qa_group_id") or "").strip()
        if rid == needle or rid.endswith(f":{needle}"):
            return row
    return None


def _search_rows(rows: list[dict[str, Any]], query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    needle = normalize_search_text(query)
    if not needle:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        blob = normalize_search_text(
            " ".join(
                [
                    _label(row),
                    str(row.get("description") or ""),
                    str(row.get("body") or ""),
                    " ".join(str(a) for a in (row.get("aliases") or [])),
                ]
            )
        )
        score = sum(1 for token in needle.split() if token and token in blob)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], _label(pair[1])))
    return [row for _score, row in scored[:limit]]


def _card_search(tenant_id: str, query: str, families: set[str] | None, *, limit: int = 5) -> list[dict[str, Any]]:
    cards: list[TitleCard] = load_published_cards(tenant_id) + load_product_cards(tenant_id)
    hits = search_cards(cards, query, families=families, limit=limit)  # type: ignore[arg-type]
    return [
        {
            "id": hit.card.item_id,
            "family": hit.card.source_family,
            "title": hit.card.title,
            "text": (hit.card.body or hit.card.search_text)[:500],
            "score": float(hit.score),
        }
        for hit in hits
    ]


def _hours_from_branch(row: dict[str, Any]) -> dict[str, Any]:
    hours = row.get("hours") or row.get("opening_hours") or row.get("schedule") or {}
    return {
        "id": str(row.get("id") or ""),
        "name": _label(row),
        "hours": hours if isinstance(hours, dict) else {"raw": hours},
        "phone": str(row.get("phone") or row.get("whatsapp") or ""),
        "address": str(row.get("address") or ""),
    }


async def run_read(name: str, args: dict[str, Any], turn: CustomerTurn) -> dict[str, Any]:
    tenant_id = turn.tenant_id
    sections = _sections(tenant_id)
    query = str(args.get("query") or args.get("q") or args.get("text") or "").strip()
    item_id = str(
        args.get("id") or args.get("service_id") or args.get("product_id") or args.get("branch_id") or ""
    ).strip()

    if name == "get_service":
        prices = _items(sections, "prices") or _items(sections, "services")
        row = _match_id(prices, item_id) or (_search_rows(prices, query, limit=1)[:1] or [None])[0]
        if not row:
            hits = _card_search(tenant_id, item_id or query, {"services", "prices"}, limit=1)
            return {"ok": bool(hits), "data": hits[0] if hits else None, "error": None if hits else "not_found"}
        return {
            "ok": True,
            "data": {
                "id": row.get("id"),
                "title": _label(row),
                "price": row.get("base_price") or row.get("price"),
                "currency": row.get("currency"),
                "description": row.get("description") or row.get("body") or "",
            },
        }

    if name == "search_services":
        return {"ok": True, "data": _card_search(tenant_id, query, {"services", "prices"})}

    if name == "get_product":
        products = _items(sections, "products")
        row = _match_id(products, item_id) or (_search_rows(products, query, limit=1)[:1] or [None])[0]
        if not row:
            hits = _card_search(tenant_id, item_id or query, {"products"}, limit=1)
            return {"ok": bool(hits), "data": hits[0] if hits else None, "error": None if hits else "not_found"}
        return {"ok": True, "data": {"id": row.get("id"), "title": _label(row), "text": row.get("description") or ""}}

    if name == "search_products":
        return {"ok": True, "data": _card_search(tenant_id, query, {"products"})}

    if name == "get_price":
        prices = _items(sections, "prices") or _items(sections, "services")
        rows = [_match_id(prices, item_id)] if item_id else _search_rows(prices, query, limit=5)
        rows = [row for row in rows if row]
        if not rows:
            hits = _card_search(tenant_id, query or item_id, {"services", "prices"})
            return {"ok": bool(hits), "data": hits if hits else None, "error": None if hits else "not_found"}
        data = [
            {
                "id": row.get("id"),
                "title": _label(row),
                "price": row.get("base_price") or row.get("price"),
                "currency": row.get("currency") or "USD",
            }
            for row in rows
        ]
        return {"ok": True, "data": data[0] if item_id else data}

    if name == "get_branch":
        branches = _items(sections, "branches")
        row = _match_id(branches, item_id) or (_search_rows(branches, query, limit=1)[:1] or [None])[0]
        if not row:
            return {"ok": False, "error": "not_found", "data": None}
        return {"ok": True, "data": _hours_from_branch(row)}

    if name == "get_branch_hours":
        branches = _items(sections, "branches") or _items(sections, "opening_hours")
        if item_id or query:
            row = _match_id(branches, item_id) or (_search_rows(branches, query or item_id, limit=1)[:1] or [None])[0]
            if not row:
                hits = _card_search(tenant_id, query or item_id, {"hours", "branches"})
                return {"ok": bool(hits), "data": hits, "error": None if hits else "not_found"}
            return {"ok": True, "data": _hours_from_branch(row)}
        return {"ok": True, "data": [_hours_from_branch(row) for row in branches[:10]]}

    if name == "get_faq":
        faqs = _items(sections, "faq")
        rows = [_match_id(faqs, item_id)] if item_id else _search_rows(faqs, query, limit=5)
        rows = [row for row in rows if row]
        if not rows:
            hits = _card_search(tenant_id, query or item_id, {"faq"})
            return {"ok": bool(hits), "data": hits, "error": None if hits else "not_found"}
        data = [
            {
                "id": row.get("id") or row.get("qa_group_id"),
                "title": _label(row),
                "answer": row.get("answer") or row.get("body") or row.get("content") or "",
            }
            for row in rows
        ]
        return {"ok": True, "data": data[0] if item_id else data}

    if name == "get_published_knowledge":
        return {"ok": True, "data": _card_search(tenant_id, query, {"knowledge", "care", "faq"})}

    if name == "resolve_resource":
        needle = normalize_search_text(item_id or query or str(args.get("resource_id") or ""))
        if not needle:
            return {"ok": False, "error": "missing_resource_id", "data": None}
        knowledge = _items(sections, "knowledge") + _items(sections, "care")
        for row in knowledge:
            rid = str(row.get("id") or "")
            attachments = row.get("attachments") or []
            if needle in normalize_search_text(rid) or needle in normalize_search_text(_label(row)):
                return {"ok": True, "data": {"id": rid, "title": _label(row), "attachments": attachments}}
            for att in attachments if isinstance(attachments, list) else []:
                if isinstance(att, dict) and needle in normalize_search_text(str(att.get("id") or "")):
                    return {"ok": True, "data": {"id": rid, "attachment": att, "title": _label(row)}}
        return {"ok": False, "error": "not_found", "data": None}

    return {"ok": False, "error": "unknown_tool", "data": None}


# Alias for older drafts.
run_read_tool = run_read
