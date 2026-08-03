"""Validate pricing section integrity and deterministic rule conflicts."""

from __future__ import annotations

from typing import Any

from services.cm.conflict_validation import ValidationFailure
from services.cm.pricing.schemas import CatalogItem, DiscountRule, PriceEntry


def validate_pricing_section(
    *,
    categories: list[dict[str, Any]] | list[Any],
    catalog: list[dict[str, Any]] | list[Any],
    price_entries: list[dict[str, Any]] | list[Any],
    discount_rules: list[dict[str, Any]] | list[Any],
) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    cat_ids = {str(c.get("id") if isinstance(c, dict) else c.id) for c in categories}
    items: list[CatalogItem] = [c if isinstance(c, CatalogItem) else CatalogItem.model_validate(c) for c in catalog]
    item_ids = {i.id for i in items}
    entries: list[PriceEntry] = [
        e if isinstance(e, PriceEntry) else PriceEntry.model_validate(e) for e in price_entries
    ]
    rules: list[DiscountRule] = [
        r if isinstance(r, DiscountRule) else DiscountRule.model_validate(r) for r in discount_rules
    ]

    for item in items:
        for cid in item.category_ids:
            if cid not in cat_ids:
                failures.append(
                    ValidationFailure(
                        code="PRICING_UNKNOWN_CATEGORY",
                        message=f"Catalog item '{item.id}' references unknown category '{cid}'.",
                        path=f"prices.catalog[{item.id}].category_ids",
                        details={"catalog_item_id": item.id, "category_id": cid},
                    )
                )
        variant_ids = {v.id for v in item.variants}
        if len(variant_ids) != len(item.variants):
            failures.append(
                ValidationFailure(
                    code="PRICING_DUPLICATE_VARIANT",
                    message=f"Catalog item '{item.id}' has duplicate variant ids.",
                    path=f"prices.catalog[{item.id}].variants",
                    details={"catalog_item_id": item.id},
                )
            )

    if len(item_ids) != len(items):
        failures.append(
            ValidationFailure(
                code="PRICING_DUPLICATE_CATALOG_ID",
                message="Duplicate catalog item ids are not allowed.",
                path="prices.catalog",
            )
        )

    entry_ids: set[str] = set()
    for entry in entries:
        if entry.id in entry_ids:
            failures.append(
                ValidationFailure(
                    code="PRICING_DUPLICATE_PRICE_ENTRY",
                    message=f"Duplicate price entry id '{entry.id}'.",
                    path=f"prices.price_entries[{entry.id}]",
                )
            )
        entry_ids.add(entry.id)
        if entry.catalog_item_id not in item_ids:
            failures.append(
                ValidationFailure(
                    code="PRICING_PRICE_UNKNOWN_ITEM",
                    message=f"Price entry '{entry.id}' references unknown catalog item '{entry.catalog_item_id}'.",
                    path=f"prices.price_entries[{entry.id}]",
                    details={"price_entry_id": entry.id},
                )
            )
            continue
        item = next(i for i in items if i.id == entry.catalog_item_id)
        if entry.variant_id and entry.variant_id not in {v.id for v in item.variants}:
            failures.append(
                ValidationFailure(
                    code="PRICING_PRICE_UNKNOWN_VARIANT",
                    message=f"Price entry '{entry.id}' references unknown variant '{entry.variant_id}'.",
                    path=f"prices.price_entries[{entry.id}]",
                )
            )

    # Ambiguous overlapping exclusive rules with identical priority + same condition fingerprint
    by_priority: dict[int, list[DiscountRule]] = {}
    for rule in rules:
        if not rule.active:
            continue
        by_priority.setdefault(rule.priority, []).append(rule)
    for priority, group in by_priority.items():
        exclusive = [r for r in group if r.exclusive or r.stacking == "exclusive"]
        if len(exclusive) > 1:
            # Same priority exclusive rules are ambiguous unless WHEN differs materially.
            fingerprints = [
                (
                    r.when.model_dump(mode="json"),
                    tuple(sorted(r.eligible_item_ids)),
                    tuple(sorted(r.eligible_category_ids)),
                )
                for r in exclusive
            ]
            if len(fingerprints) != len({str(f) for f in fingerprints}):
                failures.append(
                    ValidationFailure(
                        code="PRICING_AMBIGUOUS_EXCLUSIVE_RULES",
                        message=(
                            f"Multiple exclusive discount rules share priority {priority} "
                            "with identical WHEN/eligibility — resolve priority or conditions."
                        ),
                        path="prices.discount_rules",
                        details={
                            "priority": str(priority),
                            "rule_ids": ",".join(r.id for r in exclusive),
                        },
                    )
                )

    rule_ids: set[str] = set()
    for rule in rules:
        if rule.id in rule_ids:
            failures.append(
                ValidationFailure(
                    code="PRICING_DUPLICATE_RULE_ID",
                    message=f"Duplicate discount rule id '{rule.id}'.",
                    path=f"prices.discount_rules[{rule.id}]",
                )
            )
        rule_ids.add(rule.id)
        for iid in [*rule.eligible_item_ids, *rule.excluded_item_ids]:
            if iid not in item_ids:
                failures.append(
                    ValidationFailure(
                        code="PRICING_RULE_UNKNOWN_ITEM",
                        message=f"Discount rule '{rule.id}' references unknown catalog item '{iid}'.",
                        path=f"prices.discount_rules[{rule.id}]",
                    )
                )
        for cid in [*rule.eligible_category_ids, *rule.excluded_category_ids]:
            if cid not in cat_ids:
                failures.append(
                    ValidationFailure(
                        code="PRICING_RULE_UNKNOWN_CATEGORY",
                        message=f"Discount rule '{rule.id}' references unknown category '{cid}'.",
                        path=f"prices.discount_rules[{rule.id}]",
                    )
                )
    return failures
