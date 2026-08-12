"""Migrate tenant pricing into generic catalog/price_entries/discount_rules (no invented amounts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.cm.pricing.migration_extract import (
    _labels_from_name,
    extract_price_rows_from_json_obj,
    extract_price_rows_from_json_obj_with_ambiguous,
    extract_price_rows_from_text,
)
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

_PRICE_TAG_HINTS = ("price", "pricing", "prices", "أسعار", "سعر", "tarif", "tarifs")

__all__ = [
    "build_prices_section_from_rows",
    "extract_price_rows_from_json_obj",
    "extract_price_rows_from_json_obj_with_ambiguous",
    "extract_price_rows_from_text",
    "migrate_staged_price_files_to_catalog",
    "seed_example_discount_rule_subtotal",
]


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


def _looks_like_price_knowledge_file(obj: dict[str, Any]) -> bool:
    title = str(obj.get("title") or "").lower()
    tags = [str(t).lower() for t in (obj.get("tags") or [])]
    if any(hint in title for hint in _PRICE_TAG_HINTS):
        return True
    if any(any(hint in tag for hint in _PRICE_TAG_HINTS) for tag in tags):
        return True
    return False


def migrate_staged_price_files_to_catalog(
    *,
    staging_root: Path,
    tenant_id: str,
    updated_by: str = "pricing_migration",
    category_id: str = "sellable_items",
    category_label: str = "Sellable items",
    item_type: CatalogItemType = "custom",
) -> dict[str, Any]:
    """Scan staged price JSON/TXT (+ price-tagged knowledge files) and import proven numeric rows only.

    Never invent amounts. Never wipe an existing non-empty prices draft with an empty import.
    Ambiguous lines are archived under ``legacy/price_archive/`` for human review (excluded from publish).
    """
    legacy = staging_root / "legacy"
    legacy_prices = legacy / "price_files"
    rows: list[dict[str, Any]] = []
    ambiguous_all: list[dict[str, Any]] = []
    scanned = 0
    sources: dict[str, int] = {}

    def _consume_json(path: Path, *, source: str, allow_space_amounts: bool) -> None:
        nonlocal scanned
        scanned += 1
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        extracted, ambiguous = extract_price_rows_from_json_obj_with_ambiguous(
            obj,
            source=source,
            allow_space_amounts=allow_space_amounts,
        )
        rows.extend(extracted)
        ambiguous_all.extend(ambiguous)
        sources[source] = sources.get(source, 0) + len(extracted)

    def _consume_text(path: Path, *, source: str, allow_space_amounts: bool) -> None:
        nonlocal scanned
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        extracted, ambiguous = extract_price_rows_from_text(
            text,
            source=source,
            allow_space_amounts=allow_space_amounts,
        )
        rows.extend(extracted)
        ambiguous_all.extend(ambiguous)
        sources[source] = sources.get(source, 0) + len(extracted)

    if legacy_prices.is_dir():
        for path in sorted(legacy_prices.glob("*.json")):
            _consume_json(path, source=f"price_files/{path.name}", allow_space_amounts=True)
        for path in sorted(legacy_prices.glob("*.txt")):
            _consume_text(path, source=f"price_files/{path.name}", allow_space_amounts=True)

    # price_list.txt is usually rules-only; still scan — rules lines are skipped, priced lines imported.
    price_list = legacy / "price_list.txt"
    if price_list.is_file():
        _consume_text(price_list, source="price_list.txt", allow_space_amounts=False)

    knowledge_dir = legacy / "knowledge_files"
    if knowledge_dir.is_dir():
        for path in sorted(knowledge_dir.glob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(obj, dict) or not _looks_like_price_knowledge_file(obj):
                continue
            _consume_json(path, source=f"knowledge_files/{path.name}", allow_space_amounts=True)

    if ambiguous_all:
        archive_dir = legacy / "price_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "ambiguous_lines.json").write_text(
            json.dumps(
                {
                    "schema": "cm_price_ambiguous_v1",
                    "count": len(ambiguous_all),
                    "entries": ambiguous_all,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    env = get_draft("prices", tenant_id=tenant_id, create_default=True)
    existing = PricesSection.model_validate(env.payload)
    existing_catalog_count = len(existing.catalog) + len(existing.price_entries) + len(existing.items)

    # Dedupe rows by id keeping first proven amount.
    seen: set[str] = set()
    unique_rows: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        unique_rows.append(row)

    if not unique_rows:
        return {
            "tenant_id": tenant_id,
            "files_scanned": scanned,
            "rows_imported": 0,
            "catalog_count": len(existing.catalog),
            "price_entry_count": len(existing.price_entries),
            "invented_amounts": 0,
            "ambiguous_archived": len(ambiguous_all),
            "rows_by_source": sources,
            "skipped_empty_overwrite": existing_catalog_count > 0,
            "preserved_existing": True,
        }

    section = build_prices_section_from_rows(
        unique_rows,
        category_id=category_id,
        category_label=category_label,
        item_type=item_type,
    )
    if existing.discount_rules and not section.discount_rules:
        section.discount_rules = list(existing.discount_rules)
    if existing.resources and not section.resources:
        section.resources = list(existing.resources)
    if existing.dimension_definitions and not section.dimension_definitions:
        section.dimension_definitions = list(existing.dimension_definitions)
    if existing.package_rules and not section.package_rules:
        section.package_rules = list(existing.package_rules)

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
        "rows_imported": len(unique_rows),
        "catalog_count": len(section.catalog),
        "price_entry_count": len(section.price_entries),
        "invented_amounts": 0,
        "ambiguous_archived": len(ambiguous_all),
        "rows_by_source": sources,
        "skipped_empty_overwrite": False,
        "preserved_existing": False,
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
