"""Lightweight typed business relationships from published CM (not Neo4j GraphRAG)."""

from __future__ import annotations

from typing import Any

from services.cm.version_store import PublishedVersionError, load_published_content


def _items(sections: dict[str, Any], key: str) -> list[dict[str, Any]]:
    payload = sections.get(key)
    if not isinstance(payload, dict):
        return []
    rows = payload.get("items") or payload.get("catalog") or []
    return [row for row in rows if isinstance(row, dict)]


def _label(row: dict[str, Any]) -> str:
    labels = row.get("labels")
    if isinstance(labels, dict):
        for lang in ("en", "ar", "fr", "franco"):
            value = str(labels.get(lang) or "").strip()
            if value:
                return value
    return str(row.get("title") or row.get("name") or row.get("id") or "").strip()


def load_relations(tenant_id: str) -> dict[str, Any]:
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return {"ok": False, "relations": {}}
    sections = sections if isinstance(sections, dict) else {}
    services = _items(sections, "prices") or _items(sections, "services")
    products = _items(sections, "products")
    branches = _items(sections, "branches")
    faqs = _items(sections, "faq")
    knowledge = _items(sections, "knowledge") + _items(sections, "care")

    relations: dict[str, list[dict[str, str]]] = {
        "service_prices": [],
        "service_branches": [],
        "product_prices": [],
        "branch_hours": [],
        "branch_contacts": [],
        "faq_entities": [],
        "resource_links": [],
    }
    for row in services:
        sid = str(row.get("id") or "")
        relations["service_prices"].append(
            {"service_id": sid, "price": str(row.get("base_price") or row.get("price") or ""), "currency": str(row.get("currency") or "USD")}
        )
        for bid in row.get("branch_ids") or row.get("branches") or []:
            relations["service_branches"].append({"service_id": sid, "branch_id": str(bid)})
    for row in products:
        pid = str(row.get("id") or "")
        relations["product_prices"].append(
            {"product_id": pid, "price": str(row.get("base_price") or row.get("price") or ""), "currency": str(row.get("currency") or "USD")}
        )
    for row in branches:
        bid = str(row.get("id") or "")
        relations["branch_hours"].append({"branch_id": bid, "hours": str(row.get("hours") or row.get("opening_hours") or "")})
        phone = str(row.get("phone") or row.get("whatsapp") or "")
        if phone:
            relations["branch_contacts"].append({"branch_id": bid, "phone": phone})
    for row in faqs:
        relations["faq_entities"].append({"faq_id": str(row.get("id") or row.get("qa_group_id") or ""), "title": _label(row)})
    for row in knowledge:
        for att in row.get("attachments") or []:
            if isinstance(att, dict):
                relations["resource_links"].append(
                    {"knowledge_id": str(row.get("id") or ""), "resource_id": str(att.get("id") or ""), "title": _label(row)}
                )
    return {"ok": True, "relations": relations}


def traverse(
    tenant_id: str,
    *,
    service_id: str = "",
    branch_id: str = "",
    product_id: str = "",
) -> dict[str, Any]:
    graph = load_relations(tenant_id)
    if not graph.get("ok"):
        return {"ok": False, "hits": []}
    rel = graph["relations"]
    hits: list[dict[str, str]] = []
    if service_id:
        hits.extend([row for row in rel["service_prices"] if row.get("service_id") == service_id])
        hits.extend([row for row in rel["service_branches"] if row.get("service_id") == service_id])
        if branch_id:
            hits.extend(
                [
                    row
                    for row in rel["service_branches"]
                    if row.get("service_id") == service_id and row.get("branch_id") == branch_id
                ]
            )
    if branch_id:
        hits.extend([row for row in rel["branch_hours"] if row.get("branch_id") == branch_id])
        hits.extend([row for row in rel["branch_contacts"] if row.get("branch_id") == branch_id])
    if product_id:
        hits.extend([row for row in rel["product_prices"] if row.get("product_id") == product_id])
    return {"ok": True, "hits": hits}
