"""Normalize PricesSection payloads and bridge legacy PriceRecord rows."""

from __future__ import annotations

from typing import Any, TypeVar

from services.cm.pricing.schemas import (
    CatalogCategory,
    CatalogItem,
    DiscountRule,
    DiscountRuleSet,
    PackageRule,
    PriceBook,
    PriceEntry,
    PricingDimensionDefinition,
    ResourceOrMethod,
)
from services.cm.schemas import CmBaseModel, LocalizedLabels, PricesSection

TModel = TypeVar("TModel", bound=CmBaseModel)


def _labels(**kwargs: str) -> LocalizedLabels:
    return LocalizedLabels(**kwargs)


def _validate_list(raw: list[Any], model_cls: type[TModel]) -> list[TModel]:
    return [item if isinstance(item, model_cls) else model_cls.model_validate(item) for item in raw]


def normalize_prices_section(payload: dict[str, Any] | PricesSection) -> PricesSection:
    section = payload if isinstance(payload, PricesSection) else PricesSection.model_validate(payload)
    catalog = _validate_list(section.catalog, CatalogItem)
    categories = _validate_list(section.categories, CatalogCategory)
    entries = _validate_list(section.price_entries, PriceEntry)
    rules = _validate_list(section.discount_rules, DiscountRule)
    dimensions = _validate_list(section.dimension_definitions, PricingDimensionDefinition)
    resources = _validate_list(section.resources, ResourceOrMethod)
    price_books = _validate_list(section.price_books, PriceBook)
    rule_sets = _validate_list(section.rule_sets, DiscountRuleSet)
    package_rules = _validate_list(section.package_rules, PackageRule)

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

    # Package rules participate in the same engine via DiscountRule projection.
    for package in package_rules:
        projected = package.as_discount_rule()
        if all(r.id != projected.id for r in rules):
            rules.append(projected)

    return PricesSection(
        categories=[c.model_dump(mode="json") for c in categories],
        catalog=[c.model_dump(mode="json") for c in catalog],
        price_entries=[e.model_dump(mode="json") for e in entries],
        discount_rules=[r.model_dump(mode="json") for r in rules],
        dimension_definitions=[d.model_dump(mode="json") for d in dimensions],
        resources=[r.model_dump(mode="json") for r in resources],
        price_books=[b.model_dump(mode="json") for b in price_books],
        rule_sets=[s.model_dump(mode="json") for s in rule_sets],
        package_rules=[p.model_dump(mode="json") for p in package_rules],
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


def section_resources(section: PricesSection) -> list[ResourceOrMethod]:
    return [ResourceOrMethod.model_validate(r) for r in section.resources]


def section_dimension_definitions(section: PricesSection) -> list[PricingDimensionDefinition]:
    return [PricingDimensionDefinition.model_validate(d) for d in section.dimension_definitions]
