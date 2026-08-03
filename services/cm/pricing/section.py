"""Normalize PricesSection payloads and bridge legacy PriceRecord rows."""

from __future__ import annotations

from typing import Any

from services.cm.pricing.schemas import CatalogCategory, CatalogItem, DiscountRule, PriceEntry
from services.cm.schemas import LocalizedLabels, PricesSection


def _labels(**kwargs: str) -> LocalizedLabels:
    return LocalizedLabels(**kwargs)


def normalize_prices_section(payload: dict[str, Any] | PricesSection) -> PricesSection:
    section = payload if isinstance(payload, PricesSection) else PricesSection.model_validate(payload)
    catalog = [item if isinstance(item, CatalogItem) else CatalogItem.model_validate(item) for item in section.catalog]
    categories = [
        c if isinstance(c, CatalogCategory) else CatalogCategory.model_validate(c) for c in section.categories
    ]
    entries = [e if isinstance(e, PriceEntry) else PriceEntry.model_validate(e) for e in section.price_entries]
    rules = [r if isinstance(r, DiscountRule) else DiscountRule.model_validate(r) for r in section.discount_rules]

    # Bridge legacy items → catalog + price_entries when new fields empty.
    if section.items and not catalog and not entries:
        for legacy in section.items:
            catalog.append(
                CatalogItem(
                    id=legacy.service_id,
                    item_type="service",
                    labels=_labels(en=legacy.service_id),
                    base_price=float(legacy.amount),
                    currency=legacy.currency,
                    unit=legacy.unit,
                    branch_ids=[legacy.branch_id] if legacy.branch_id else [],
                    provenance="legacy_price_record",
                    notes=legacy.notes,
                )
            )
            entries.append(
                PriceEntry(
                    id=legacy.id,
                    catalog_item_id=legacy.service_id,
                    amount=float(legacy.amount),
                    currency=legacy.currency,
                    branch_id=legacy.branch_id,
                    unit=legacy.unit,
                    provenance="legacy_price_record",
                    notes=legacy.notes,
                )
            )

    return PricesSection(
        categories=[c.model_dump(mode="json") for c in categories],
        catalog=[c.model_dump(mode="json") for c in catalog],
        price_entries=[e.model_dump(mode="json") for e in entries],
        discount_rules=[r.model_dump(mode="json") for r in rules],
        items=section.items,
        notes=section.notes,
    )


def section_catalog_items(section: PricesSection) -> list[CatalogItem]:
    return [CatalogItem.model_validate(i) for i in section.catalog]


def section_price_entries(section: PricesSection) -> list[PriceEntry]:
    return [PriceEntry.model_validate(e) for e in section.price_entries]


def section_discount_rules(section: PricesSection) -> list[DiscountRule]:
    return [DiscountRule.model_validate(r) for r in section.discount_rules]


def section_categories(section: PricesSection) -> list[CatalogCategory]:
    return [CatalogCategory.model_validate(c) for c in section.categories]
