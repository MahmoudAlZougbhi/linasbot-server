"""Fixture tenants for generic CM pricing engine tests."""

from __future__ import annotations

from services.cm.pricing.migration import seed_example_discount_rule_subtotal
from services.cm.pricing.schemas import (
    CatalogCategory,
    CatalogItem,
    DiscountRule,
    ItemVariant,
    PriceEntry,
    RuleAction,
    RuleCondition,
    RuleConditionGroup,
)
from services.cm.schemas import LocalizedLabels


def _labels(en: str, **extra: str) -> LocalizedLabels:
    return LocalizedLabels(en=en, **extra)


def _fixture_linas_style() -> tuple[list[CatalogItem], list[PriceEntry], list[DiscountRule], list[CatalogCategory]]:
    """Tenant data shaped like a laser clinic — still generic engine contracts."""
    categories = [CatalogCategory(id="body_area", labels=_labels("Body areas"))]
    catalog = [
        CatalogItem(
            id="full_legs",
            item_type="body_area",
            category_ids=["body_area"],
            labels=_labels("Full Legs", ar="رجلين كامل"),
            aliases=["legs", "full legs", "رجلين"],
            base_price=120.0,
            currency="USD",
        ),
        CatalogItem(
            id="underarms",
            item_type="body_area",
            category_ids=["body_area"],
            labels=_labels("Underarms"),
            aliases=["armpits", "underarms"],
            base_price=40.0,
            currency="USD",
        ),
        CatalogItem(
            id="bikini",
            item_type="body_area",
            category_ids=["body_area"],
            labels=_labels("Bikini"),
            aliases=["bikini"],
            base_price=50.0,
            currency="USD",
        ),
    ]
    entries = [
        PriceEntry(id="pe_full_legs", catalog_item_id="full_legs", amount=120.0, currency="USD"),
        PriceEntry(id="pe_underarms", catalog_item_id="underarms", amount=40.0, currency="USD"),
        PriceEntry(id="pe_bikini", catalog_item_id="bikini", amount=50.0, currency="USD"),
    ]
    rules = [
        seed_example_discount_rule_subtotal(rule_id="pkg_200", threshold=200.0, percent=10.0, currency="USD"),
    ]
    return catalog, entries, rules, categories


def _fixture_salon() -> tuple[list[CatalogItem], list[PriceEntry], list[DiscountRule], list[CatalogCategory]]:
    categories = [CatalogCategory(id="hair", labels=_labels("Hair services"))]
    catalog = [
        CatalogItem(
            id="cut",
            item_type="service",
            category_ids=["hair"],
            labels=_labels("Haircut"),
            aliases=["cut", "haircut"],
            currency="EUR",
            variants=[
                ItemVariant(id="30m", labels=_labels("30 min"), duration_minutes=30),
                ItemVariant(id="60m", labels=_labels("60 min"), duration_minutes=60),
            ],
        )
    ]
    entries = [
        PriceEntry(id="pe_cut_30", catalog_item_id="cut", variant_id="30m", amount=25.0, currency="EUR"),
        PriceEntry(id="pe_cut_60", catalog_item_id="cut", variant_id="60m", amount=45.0, currency="EUR"),
    ]
    rules = [
        DiscountRule(
            id="multi_cut",
            labels=_labels("2+ cuts 15% off"),
            priority=5,
            exclusive=True,
            stacking="exclusive",
            when=RuleConditionGroup(conditions=[RuleCondition(kind="eligible_quantity_at_least", count=2)]),
            then=RuleAction(kind="percent_off", percent=15),
            currency="EUR",
        )
    ]
    return catalog, entries, rules, categories


def _fixture_retail() -> tuple[list[CatalogItem], list[PriceEntry], list[DiscountRule], list[CatalogCategory]]:
    categories = [
        CatalogCategory(id="products", labels=_labels("Products")),
        CatalogCategory(id="addons", labels=_labels("Add-ons")),
    ]
    catalog = [
        CatalogItem(
            id="serum",
            item_type="product",
            category_ids=["products"],
            labels=_labels("Serum"),
            aliases=["serum"],
            currency="GBP",
            base_price=30.0,
        ),
        CatalogItem(
            id="mask",
            item_type="add_on",
            category_ids=["addons"],
            labels=_labels("Mask"),
            aliases=["mask", "face mask"],
            currency="GBP",
            base_price=12.0,
        ),
    ]
    entries = [
        PriceEntry(id="pe_serum", catalog_item_id="serum", amount=30.0, currency="GBP"),
        PriceEntry(id="pe_mask", catalog_item_id="mask", amount=12.0, currency="GBP"),
    ]
    rules = [
        DiscountRule(
            id="bundle_serum_mask",
            labels=_labels("Serum + mask package"),
            priority=1,
            exclusive=True,
            stacking="exclusive",
            when=RuleConditionGroup(
                conditions=[
                    RuleCondition(kind="includes_items", item_ids=["serum", "mask"]),
                ]
            ),
            then=RuleAction(kind="bundle_price", amount=35.0),
            currency="GBP",
        )
    ]
    return catalog, entries, rules, categories
