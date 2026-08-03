"""Migrate tenant pricing into generic catalog/price_entries/discount_rules (no invented amounts)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.cm.pricing.schemas import (
    CatalogCategory,
    CatalogItem,
    CatalogItemType,
    DiscountRule,
    EffectiveWindow,
    PriceEntry,
    RuleAction,
    RuleCondition,
    RuleConditionGroup,
)
from services.cm.schemas import LocalizedLabels, PricesSection
from services.cm.storage import get_draft, put_draft

_AMOUNT_KEYS = ("amount", "price", "unit_price", "base_price", "cost")
_NAME_KEYS = ("name", "title", "label", "body_part", "service", "item")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    return float(match.group(1))


def _labels_from_name(name: str) -> LocalizedLabels:
    return LocalizedLabels(en=name, ar=name, fr=name)


def extract_price_rows_from_json_obj(obj: Any, *, source: str) -> list[dict[str, Any]]:
    """Best-effort extract of {id,name,amount,currency} from heterogeneous tenant JSON."""
    rows: list[dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            amount = None
            for key in _AMOUNT_KEYS:
                if key in node:
                    amount = _as_float(node.get(key))
                    if amount is not None:
                        break
            name = None
            for key in _NAME_KEYS:
                if key in node and str(node.get(key) or "").strip():
                    name = str(node.get(key)).strip()
                    break
            if amount is not None and name:
                item_id = str(node.get("id") or node.get("sku") or re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")
                rows.append(
                    {
                        "id": item_id or f"item_{len(rows)}",
                        "name": name,
                        "amount": amount,
                        "currency": str(node.get("currency") or "USD"),
                        "provenance": source,
                    }
                )
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, f"{path}[{idx}]")

    walk(obj, "")
    # Dedupe by id keeping first
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        unique.append(row)
    return unique


def build_prices_section_from_rows(
    rows: list[dict[str, Any]],
    *,
    category_id: str = "sellable_items",
    category_label: str = "Sellable items",
    item_type: CatalogItemType = "custom",
    discount_rules: list[DiscountRule] | None = None,
) -> PricesSection:
    categories = [
        CatalogCategory(
            id=category_id,
            labels=_labels_from_name(category_label),
            active=True,
            notes="Tenant-defined category (not a platform default).",
        )
    ]
    catalog: list[CatalogItem] = []
    entries: list[PriceEntry] = []
    for row in rows:
        item_id = str(row["id"])
        catalog.append(
            CatalogItem(
                id=item_id,
                item_type=item_type,
                category_ids=[category_id],
                labels=_labels_from_name(str(row["name"])),
                aliases=[str(row["name"])],
                base_price=float(row["amount"]),
                currency=str(row.get("currency") or "USD"),
                active=True,
                provenance=str(row.get("provenance") or "import"),
            )
        )
        entries.append(
            PriceEntry(
                id=f"pe_{item_id}",
                catalog_item_id=item_id,
                amount=float(row["amount"]),
                currency=str(row.get("currency") or "USD"),
                active=True,
                provenance=str(row.get("provenance") or "import"),
            )
        )
    return PricesSection(
        categories=[c.model_dump(mode="json") for c in categories],
        catalog=[c.model_dump(mode="json") for c in catalog],
        price_entries=[e.model_dump(mode="json") for e in entries],
        discount_rules=[r.model_dump(mode="json") for r in (discount_rules or [])],
        items=[],
        notes="Imported into generic pricing catalog. Notes never override structured amounts.",
    )


def migrate_staged_price_files_to_catalog(
    *,
    staging_root: Path,
    tenant_id: str,
    updated_by: str = "pricing_migration",
    category_id: str = "sellable_items",
    category_label: str = "Sellable items",
    item_type: CatalogItemType = "custom",
) -> dict[str, Any]:
    """Scan staged legacy/price_files/*.json and import proven numeric rows only."""
    legacy_prices = staging_root / "legacy" / "price_files"
    rows: list[dict[str, Any]] = []
    scanned = 0
    if legacy_prices.is_dir():
        for path in sorted(legacy_prices.glob("*.json")):
            scanned += 1
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            rows.extend(extract_price_rows_from_json_obj(obj, source=f"price_files/{path.name}"))

    section = build_prices_section_from_rows(
        rows,
        category_id=category_id,
        category_label=category_label,
        item_type=item_type,
    )
    env = get_draft("prices", tenant_id=tenant_id, create_default=True)
    put_draft(
        "prices",
        payload=section.model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    return {
        "tenant_id": tenant_id,
        "files_scanned": scanned,
        "rows_imported": len(rows),
        "catalog_count": len(section.catalog),
        "price_entry_count": len(section.price_entries),
        "invented_amounts": 0,
    }


def seed_example_discount_rule_subtotal(
    *,
    rule_id: str,
    threshold: float,
    percent: float,
    currency: str = "USD",
) -> DiscountRule:
    """Declarative example builder for tests/fixtures — not Lina-specific."""
    return DiscountRule(
        id=rule_id,
        labels=LocalizedLabels(en=f"{percent}% off at {threshold}+"),
        priority=10,
        exclusive=True,
        stacking="exclusive",
        when=RuleConditionGroup(
            op="and",
            conditions=[RuleCondition(kind="subtotal_at_least", amount=threshold)],
        ),
        then=RuleAction(kind="percent_off", percent=percent),
        currency=currency,
        active=True,
        effective=EffectiveWindow(),
        provenance="fixture",
    )
