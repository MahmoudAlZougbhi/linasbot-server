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

_AMOUNT_KEYS = (
    "amount",
    "price",
    "unit_price",
    "base_price",
    "cost",
    "final_price",
    "discounted_price",
    "value",
)
_NAME_KEYS = (
    "name",
    "title",
    "label",
    "body_part",
    "service",
    "item",
    "area",
    "body_area",
    "part",
    "machine",
)

# Lines that look like session/schedule guidance, not sellable unit prices.
_SKIP_LINE_RE = re.compile(
    r"(?i)\b("
    r"session|sessions|interval|minimum sessions|"
    r"every\s+\d+|days?\s+apart|do not|selector|pricing rules|"
    r"use prices only|additional relevant context"
    r")\b"
)

# Name + separator + optional currency + amount (optional trailing notes after / or ().
_PRICED_LINE_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z\u0600-\u06FF][^:=\-|\$€£]{0,80}?)\s*"
    r"(?::|=|-|–|—|\.{2,}|\|)\s*"
    r"(?P<cur>\$|€|£|USD|EUR|LL|L\.?L\.?)?\s*"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)\s*"
    r"(?P<cur2>\$|€|£|USD|EUR|LL|L\.?L\.?)?\b",
    re.IGNORECASE,
)

_PRICE_TAG_HINTS = ("price", "pricing", "prices", "أسعار", "سعر", "tarif", "tarifs")
_PHONE_LIKE_RE = re.compile(r"^\+?\d{8,15}$")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    match = re.fullmatch(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:USD|EUR|LL|LBP)?", text, flags=re.IGNORECASE)
    if not match:
        # Allow plain "35" / "35.5" / "35 USD" already covered; also "USD 35"
        match = re.fullmatch(r"(?:USD|EUR|\$|€)?\s*(\d+(?:\.\d+)?)\s*(?:USD|EUR|\$|€)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def _labels_from_name(name: str) -> LocalizedLabels:
    return LocalizedLabels(en=name, ar=name, fr=name)


def _item_id_from_name(name: str, *, fallback_prefix: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or f"{fallback_prefix}_{abs(hash(name)) % 10_000}"


def _currency_from_tokens(*tokens: str | None, default: str = "USD") -> str:
    for tok in tokens:
        if not tok:
            continue
        upper = tok.strip().upper().replace(".", "")
        if upper in {"$", "USD"}:
            return "USD"
        if upper in {"€", "EUR"}:
            return "EUR"
        if upper in {"£", "GBP"}:
            return "GBP"
        if upper in {"LL", "LBP"}:
            return "LBP"
    return default


def extract_price_rows_from_text(text: str, *, source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract proven name+amount rows from free text. Ambiguous lines returned separately (no invent)."""
    rows: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    if not text or not str(text).strip():
        return rows, ambiguous

    for line_no, raw_line in enumerate(str(text).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or set(line) <= {"-", "=", "_", "*"}:
            continue
        if _SKIP_LINE_RE.search(line):
            continue
        match = _PRICED_LINE_RE.match(line)
        if not match:
            # Digit present but no clear name+amount structure → archive for review.
            if re.search(r"\d", line) and re.search(r"[A-Za-z\u0600-\u06FF]", line):
                ambiguous.append(
                    {
                        "source": source,
                        "line_no": line_no,
                        "reason": "no_clear_name_amount_separator",
                        "line_len": len(line),
                    }
                )
            continue
        name = (match.group("name") or "").strip()
        name = name.strip(".-–—|:")
        name = name.strip()
        amount = _as_float(match.group("amount"))
        if not name or amount is None:
            ambiguous.append(
                {
                    "source": source,
                    "line_no": line_no,
                    "reason": "missing_name_or_amount",
                    "line_len": len(line),
                }
            )
            continue
        if _PHONE_LIKE_RE.match(str(match.group("amount") or "")):
            ambiguous.append(
                {
                    "source": source,
                    "line_no": line_no,
                    "reason": "phone_like_amount",
                    "line_len": len(line),
                }
            )
            continue
        # Reject absurdly large bare integers that look like IDs (e.g. 10+ digits).
        amount_raw = str(match.group("amount") or "")
        if "." not in amount_raw and "," not in amount_raw and len(amount_raw) >= 7:
            ambiguous.append(
                {
                    "source": source,
                    "line_no": line_no,
                    "reason": "id_like_amount",
                    "line_len": len(line),
                }
            )
            continue
        currency = _currency_from_tokens(match.group("cur"), match.group("cur2"))
        rows.append(
            {
                "id": _item_id_from_name(name),
                "name": name,
                "amount": amount,
                "currency": currency,
                "provenance": f"{source}:L{line_no}",
            }
        )
    return rows, ambiguous


def extract_price_rows_from_json_obj(obj: Any, *, source: str) -> list[dict[str, Any]]:
    """Best-effort extract of {id,name,amount,currency} from heterogeneous tenant JSON.

    Supports:
    - objects with name+amount keys (nested walk)
    - flat string→number maps
    - content-file shape ``{title, content}`` where ``content`` has priced lines
    Never invents amounts.
    """
    rows: list[dict[str, Any]] = []
    ambiguous_bucket: list[dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            # Content-file selector shape used by Content Managers price section.
            content = node.get("content")
            if isinstance(content, str) and content.strip():
                text_rows, ambiguous = extract_price_rows_from_text(content, source=f"{source}{path}/content")
                rows.extend(text_rows)
                ambiguous_bucket.extend(ambiguous)

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
                item_id = str(node.get("id") or node.get("sku") or _item_id_from_name(name)).strip("_")
                rows.append(
                    {
                        "id": item_id or f"item_{len(rows)}",
                        "name": name,
                        "amount": amount,
                        "currency": str(node.get("currency") or "USD"),
                        "provenance": source if not path else f"{source}:{path}",
                    }
                )

            # Flat map: {"Arms": 35, "Legs": 50} — only when ALL values are numeric-ish and keys are names.
            if node and all(isinstance(k, str) for k in node.keys()):
                values = list(node.values())
                if (
                    values
                    and all(_as_float(v) is not None for v in values)
                    and all(
                        k.lower()
                        not in _AMOUNT_KEYS + _NAME_KEYS + ("id", "sku", "currency", "content", "tags", "language")
                        for k in node.keys()
                    )
                ):
                    # Avoid treating content-file metadata as a price map.
                    meta_keys = {"title", "audience", "priority", "created_at", "updated_at", "tags", "language"}
                    if not (meta_keys & {k.lower() for k in node.keys()}):
                        for key, value in node.items():
                            amount_v = _as_float(value)
                            if amount_v is None:
                                continue
                            rows.append(
                                {
                                    "id": _item_id_from_name(key),
                                    "name": key.strip(),
                                    "amount": amount_v,
                                    "currency": "USD",
                                    "provenance": f"{source}:map{path}",
                                }
                            )

            for key, value in node.items():
                if key == "content" and isinstance(value, str):
                    continue
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, f"{path}[{idx}]")

    walk(obj, "")
    # Attach ambiguous count on a side channel via provenance notes is not needed here;
    # callers that want archival use extract_with_ambiguous.
    _ = ambiguous_bucket

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        unique.append(row)
    return unique


def extract_price_rows_from_json_obj_with_ambiguous(
    obj: Any, *, source: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Like extract_price_rows_from_json_obj but also returns ambiguous text-line ledger entries."""
    rows = extract_price_rows_from_json_obj(obj, source=source)
    ambiguous: list[dict[str, Any]] = []
    if isinstance(obj, dict) and isinstance(obj.get("content"), str):
        _, ambiguous = extract_price_rows_from_text(obj["content"], source=f"{source}/content")
    return rows, ambiguous


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

    def _consume_json(path: Path, *, source: str) -> None:
        nonlocal scanned
        scanned += 1
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        extracted, ambiguous = extract_price_rows_from_json_obj_with_ambiguous(obj, source=source)
        rows.extend(extracted)
        ambiguous_all.extend(ambiguous)
        sources[source] = sources.get(source, 0) + len(extracted)

    def _consume_text(path: Path, *, source: str) -> None:
        nonlocal scanned
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        extracted, ambiguous = extract_price_rows_from_text(text, source=source)
        rows.extend(extracted)
        ambiguous_all.extend(ambiguous)
        sources[source] = sources.get(source, 0) + len(extracted)

    if legacy_prices.is_dir():
        for path in sorted(legacy_prices.glob("*.json")):
            _consume_json(path, source=f"price_files/{path.name}")
        for path in sorted(legacy_prices.glob("*.txt")):
            _consume_text(path, source=f"price_files/{path.name}")

    # price_list.txt is usually rules-only; still scan — rules lines are skipped, priced lines imported.
    price_list = legacy / "price_list.txt"
    if price_list.is_file():
        _consume_text(price_list, source="price_list.txt")

    knowledge_dir = legacy / "knowledge_files"
    if knowledge_dir.is_dir():
        for path in sorted(knowledge_dir.glob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(obj, dict) or not _looks_like_price_knowledge_file(obj):
                continue
            _consume_json(path, source=f"knowledge_files/{path.name}")

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
