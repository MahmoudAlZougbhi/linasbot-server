"""Merge service-shaped rows into CM prices.catalog (WAVE E single SoT)."""

from __future__ import annotations

from typing import Any

from services.ai_setup.pricing.schemas import CatalogItem
from services.ai_setup.schemas import PricesSection, ServiceRecord


def merge_service_records_into_prices(
    prices: PricesSection,
    services_by_id: dict[str, ServiceRecord],
) -> PricesSection:
    """Upsert service records into ``prices.catalog``. Does not write CM services."""
    if not services_by_id:
        return prices
    catalog: list[Any] = list(prices.catalog or [])
    index: dict[str, int] = {}
    for i, row in enumerate(catalog):
        rid = ""
        if isinstance(row, dict):
            rid = str(row.get("id") or "").strip()
        elif hasattr(row, "id"):
            rid = str(row.id or "").strip()
        if rid:
            index[rid] = i
    for sid, svc in services_by_id.items():
        dumped = CatalogItem(
            id=sid,
            item_type="service",
            labels=svc.labels,
            aliases=list(svc.aliases),
            active=bool(svc.available),
            audience=_audience(svc.audience),
            notes=svc.notes,
            provenance="knowledge_redistribution",
        ).model_dump(mode="json")
        if sid in index:
            catalog[index[sid]] = dumped
        else:
            index[sid] = len(catalog)
            catalog.append(dumped)
    return PricesSection(
        categories=prices.categories,
        catalog=catalog,
        price_entries=prices.price_entries,
        discount_rules=prices.discount_rules,
        dimension_definitions=prices.dimension_definitions,
        resources=prices.resources,
        price_books=prices.price_books,
        rule_sets=prices.rule_sets,
        package_rules=prices.package_rules,
        items=prices.items,
        policy_text=prices.policy_text,
        notes=prices.notes,
    )


def _audience(value: str | None) -> str:
    raw = (value or "any").strip().lower()
    if raw in {"men", "women", "general", "any"}:
        return raw
    return "any"
