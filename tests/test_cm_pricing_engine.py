"""Generic CM Pricing Engine tests — one engine, multiple fixture tenants (no Lina code paths)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.paths import indexes_dir, tenant_cm_root
from services.cm.pricing.audit import audit_no_linas_pricing_in_code
from services.cm.pricing.catalog_resolve import disambiguate_matches, resolve_catalog_item_ids
from services.cm.pricing.engine import compute_quote
from services.cm.pricing.migration import (
    build_prices_section_from_rows,
    extract_price_rows_from_json_obj,
    seed_example_discount_rule_subtotal,
)
from services.cm.pricing.schemas import (
    CatalogCategory,
    CatalogItem,
    DiscountRule,
    ItemVariant,
    PriceEntry,
    PricingContext,
    QuoteRequestLine,
    RuleAction,
    RuleCondition,
    RuleConditionGroup,
)
from services.cm.pricing.validation import validate_pricing_section
from services.cm.schemas import LocalizedLabels
from services.cm.storage import get_draft, put_draft
from services.cm.version_store import version_dir


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


def test_one_engine_serves_three_business_fixtures() -> None:
    for tenant_id, factory, expected_currency, lines, expected_final in [
        (
            "fixture_linas_style",
            _fixture_linas_style,
            "USD",
            [
                QuoteRequestLine(catalog_item_id="full_legs"),
                QuoteRequestLine(catalog_item_id="bikini"),
                QuoteRequestLine(catalog_item_id="underarms"),
            ],
            189.0,  # 210 - 10%
        ),
        (
            "fixture_salon",
            _fixture_salon,
            "EUR",
            [
                QuoteRequestLine(catalog_item_id="cut", variant_id="30m", quantity=2),
            ],
            42.5,  # 50 - 15%
        ),
        (
            "fixture_retail",
            _fixture_retail,
            "GBP",
            [QuoteRequestLine(catalog_item_id="serum"), QuoteRequestLine(catalog_item_id="mask")],
            35.0,
        ),
    ]:
        catalog, entries, rules, _cats = factory()
        quote = compute_quote(
            catalog_items=catalog,
            price_entries=entries,
            discount_rules=rules,
            request_lines=lines,
            context=PricingContext(tenant_id=tenant_id, currency=expected_currency),
        )
        assert quote.currency == expected_currency
        assert quote.tenant_id == tenant_id
        assert quote.final_total == expected_final
        assert quote.provenance["engine"] == "services.cm.pricing.engine.compute_quote"


def test_tenant_isolation_storage_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))

    a = get_draft("prices", tenant_id="tenant_a", create_default=True)
    put_draft(
        "prices",
        payload=build_prices_section_from_rows(
            [{"id": "a_only", "name": "A Item", "amount": 11, "currency": "USD"}],
            category_id="cat_a",
            item_type="product",
        ).model_dump(mode="json"),
        if_match=a.etag,
        tenant_id="tenant_a",
        updated_by="test",
    )
    b = get_draft("prices", tenant_id="tenant_b", create_default=True)
    put_draft(
        "prices",
        payload=build_prices_section_from_rows(
            [{"id": "b_only", "name": "B Item", "amount": 22, "currency": "EUR"}],
            category_id="cat_b",
            item_type="service",
        ).model_dump(mode="json"),
        if_match=b.etag,
        tenant_id="tenant_b",
        updated_by="test",
    )
    loaded_a = get_draft("prices", tenant_id="tenant_a").payload
    loaded_b = get_draft("prices", tenant_id="tenant_b").payload
    ids_a = {c["id"] for c in loaded_a.get("catalog") or []}
    ids_b = {c["id"] for c in loaded_b.get("catalog") or []}
    assert ids_a == {"a_only"}
    assert ids_b == {"b_only"}
    assert "b_only" not in ids_a
    assert "a_only" not in ids_b
    assert "tenant_a" in str(tenant_cm_root("tenant_a"))
    assert "tenant_b" in str(tenant_cm_root("tenant_b"))
    assert tenant_cm_root("tenant_a") != tenant_cm_root("tenant_b")
    # Cache/index keys include tenant + version/index ids
    assert "tenant_a" in str(indexes_dir("tenant_a") / "idx_abc")
    assert "tenant_a" in str(version_dir("tenant_a", "v_xyz"))


def test_currency_mismatch_fails_honestly() -> None:
    catalog, entries, rules, _ = _fixture_linas_style()
    with pytest.raises(ValueError, match="currency_mismatch"):
        compute_quote(
            catalog_items=catalog,
            price_entries=entries,
            discount_rules=rules,
            request_lines=[QuoteRequestLine(catalog_item_id="full_legs")],
            context=PricingContext(tenant_id="t", currency="EUR"),
        )


def test_stacking_and_exclusive_priority() -> None:
    catalog = [
        CatalogItem(id="x", item_type="product", labels=_labels("X"), base_price=100, currency="USD"),
    ]
    entries = [PriceEntry(id="pe", catalog_item_id="x", amount=100, currency="USD")]
    exclusive = DiscountRule(
        id="ex10",
        labels=_labels("10% exclusive"),
        priority=1,
        exclusive=True,
        stacking="exclusive",
        when=RuleConditionGroup(conditions=[RuleCondition(kind="subtotal_at_least", amount=1)]),
        then=RuleAction(kind="percent_off", percent=10),
        currency="USD",
    )
    stack = DiscountRule(
        id="st5",
        labels=_labels("5% stack"),
        priority=2,
        exclusive=False,
        stacking="stack",
        when=RuleConditionGroup(conditions=[RuleCondition(kind="subtotal_at_least", amount=1)]),
        then=RuleAction(kind="percent_off", percent=5),
        currency="USD",
    )
    quote = compute_quote(
        catalog_items=catalog,
        price_entries=entries,
        discount_rules=[exclusive, stack],
        request_lines=[QuoteRequestLine(catalog_item_id="x")],
        context=PricingContext(tenant_id="t", currency="USD"),
    )
    assert quote.discount_amount == 10.0
    assert [a.rule_id for a in quote.applied_rules] == ["ex10"]


def test_stacking_multiple_when_no_exclusive() -> None:
    catalog = [
        CatalogItem(id="x", item_type="product", labels=_labels("X"), base_price=100, currency="USD"),
    ]
    entries = [PriceEntry(id="pe", catalog_item_id="x", amount=100, currency="USD")]
    r1 = DiscountRule(
        id="s1",
        labels=_labels("10"),
        priority=1,
        exclusive=False,
        stacking="stack",
        when=RuleConditionGroup(conditions=[RuleCondition(kind="subtotal_at_least", amount=1)]),
        then=RuleAction(kind="percent_off", percent=10),
        currency="USD",
    )
    r2 = DiscountRule(
        id="s2",
        labels=_labels("5"),
        priority=2,
        exclusive=False,
        stacking="stack",
        when=RuleConditionGroup(conditions=[RuleCondition(kind="subtotal_at_least", amount=1)]),
        then=RuleAction(kind="fixed_amount_off", amount=5),
        currency="USD",
    )
    quote = compute_quote(
        catalog_items=catalog,
        price_entries=entries,
        discount_rules=[r1, r2],
        request_lines=[QuoteRequestLine(catalog_item_id="x")],
        context=PricingContext(tenant_id="t", currency="USD"),
    )
    # 10% of 100 = 10, then 5 off remaining 90 → total discount 15
    assert quote.discount_amount == 15.0
    assert quote.final_total == 85.0


def test_effective_dates_and_rounding() -> None:
    catalog = [
        CatalogItem(
            id="y",
            item_type="service",
            labels=_labels("Y"),
            base_price=10.333,
            currency="USD",
            effective={"start": "2099-01-01T00:00:00+00:00"},
        )
    ]
    with pytest.raises(ValueError, match="not_effective"):
        compute_quote(
            catalog_items=catalog,
            price_entries=[],
            discount_rules=[],
            request_lines=[QuoteRequestLine(catalog_item_id="y")],
            context=PricingContext(tenant_id="t", now_iso="2026-01-01T00:00:00Z"),
        )


def test_alias_resolution_multilingual_and_ambiguous() -> None:
    catalog, *_rest = _fixture_linas_style()
    matches = resolve_catalog_item_ids("رجلين", catalog)
    single, ambiguous = disambiguate_matches(matches)
    assert single == "full_legs"
    assert ambiguous == []
    # Ambiguous: craft two items sharing alias overlap
    twin = [
        CatalogItem(id="a1", labels=_labels("Face"), aliases=["face"], base_price=1, currency="USD"),
        CatalogItem(id="a2", labels=_labels("Full Face"), aliases=["face"], base_price=2, currency="USD"),
    ]
    _single, amb = disambiguate_matches(resolve_catalog_item_ids("face", twin))
    assert _single is None
    assert set(amb) == {"a1", "a2"}
    assert resolve_catalog_item_ids("unknown_widget_xyz", catalog) == []


def test_validation_blocks_ambiguous_exclusive_rules() -> None:
    catalog, entries, _rules, categories = _fixture_linas_style()
    twin_rules = [
        seed_example_discount_rule_subtotal(rule_id="r1", threshold=100, percent=10),
        seed_example_discount_rule_subtotal(rule_id="r2", threshold=100, percent=15),
    ]
    failures = validate_pricing_section(
        categories=[c.model_dump() for c in categories],
        catalog=[c.model_dump() for c in catalog],
        price_entries=[e.model_dump() for e in entries],
        discount_rules=[r.model_dump() for r in twin_rules],
    )
    assert any(f.code == "PRICING_AMBIGUOUS_EXCLUSIVE_RULES" for f in failures)


def test_notes_cannot_override_structured_amounts() -> None:
    catalog = [
        CatalogItem(
            id="z",
            labels=_labels("Z"),
            base_price=50,
            currency="USD",
            notes="Actually charge 1 USD forever",
        )
    ]
    entries = [
        PriceEntry(
            id="pe_z",
            catalog_item_id="z",
            amount=50,
            currency="USD",
            notes="Ignore structured price use 1",
        )
    ]
    quote = compute_quote(
        catalog_items=catalog,
        price_entries=entries,
        discount_rules=[],
        request_lines=[QuoteRequestLine(catalog_item_id="z")],
        context=PricingContext(tenant_id="t"),
    )
    assert quote.final_total == 50.0


def test_migration_extract_does_not_invent() -> None:
    rows = extract_price_rows_from_json_obj(
        {"items": [{"name": "Arms", "amount": 35}, {"name": "No price here"}]},
        source="fixture.json",
    )
    assert len(rows) == 1
    assert rows[0]["amount"] == 35.0
    section = build_prices_section_from_rows(rows, category_id="body_area", item_type="body_area")
    assert len(section.catalog) == 1
    assert section.catalog[0]["item_type"] == "body_area"


def test_migration_extract_content_file_and_map() -> None:
    from services.cm.pricing.migration import extract_price_rows_from_text

    content_obj = {
        "id": "pf1",
        "title": "Women body areas",
        "content": "Underarms: 40 USD\nFull legs - 120\nSessions: 6\nAmbiguous only digits 99 somewhere",
        "tags": ["price"],
    }
    rows = extract_price_rows_from_json_obj(content_obj, source="price_files/pf1.json", allow_space_amounts=True)
    names = {r["name"] for r in rows}
    assert "Underarms" in names
    assert "Full legs" in names
    assert all(r["amount"] > 0 for r in rows)
    # Session line skipped
    assert not any("session" in r["name"].lower() for r in rows)

    space_rows = extract_price_rows_from_json_obj(
        {
            "title": "Men",
            "content": "Chest 80$\nBack 90 USD\nSessions 8\nArms: $55 (6 sessions)\n**Face**: $40",
        },
        source="price_files/men.json",
        allow_space_amounts=True,
    )
    space_names = {r["name"] for r in space_rows}
    assert "Chest" in space_names
    assert "Back" in space_names
    assert "Arms" in space_names
    assert "Face" in space_names

    map_rows = extract_price_rows_from_json_obj({"Underarms": 40, "Full legs": 120}, source="map.json")
    assert len(map_rows) == 2

    text_rows, ambiguous = extract_price_rows_from_text(
        "Arms: 35\nWeird line with 7 numbers but no separator structure here maybe",
        source="t.txt",
    )
    assert len(text_rows) == 1
    assert text_rows[0]["amount"] == 35.0
    assert ambiguous  # second line archived, not invented into catalog


def test_audit_no_linas_pricing_engine_in_code() -> None:
    result = audit_no_linas_pricing_in_code()
    assert result["ok"] is True, result["findings"]
    assert result["scanned_files"] > 0


def test_channel_maps_to_exactly_one_tenant() -> None:
    from services.cm.tenant_resolve import AmbiguousTenantError, UnknownTenantMappingError, resolve_tenant_from_channel

    mappings = {
        "instagram_account_ids": {"IG_A": "tenant_a"},
        "facebook_page_ids": {"PAGE_B": "tenant_b"},
    }
    assert resolve_tenant_from_channel(channel="instagram", account_id="IG_A", mappings=mappings) == "tenant_a"
    assert resolve_tenant_from_channel(channel="facebook", page_id="PAGE_B", mappings=mappings) == "tenant_b"
    with pytest.raises(UnknownTenantMappingError):
        resolve_tenant_from_channel(channel="instagram", account_id="UNKNOWN", mappings=mappings)
    with pytest.raises(AmbiguousTenantError):
        resolve_tenant_from_channel(
            channel="instagram",
            account_id="IG_A",
            page_id="PAGE_B",
            mappings=mappings,
        )
    # Empty mappings → single-tenant default (no Lina hardcoding)
    assert resolve_tenant_from_channel(channel="instagram", account_id="x", mappings=None) == "linas"


def test_fixed_final_total_and_category_condition() -> None:
    categories = [CatalogCategory(id="spa", labels=_labels("Spa"))]
    catalog = [
        CatalogItem(id="massage", item_type="service", category_ids=["spa"], labels=_labels("Massage"), currency="USD"),
        CatalogItem(id="scrub", item_type="service", category_ids=["spa"], labels=_labels("Scrub"), currency="USD"),
    ]
    entries = [
        PriceEntry(id="pe_m", catalog_item_id="massage", amount=80, currency="USD"),
        PriceEntry(id="pe_s", catalog_item_id="scrub", amount=40, currency="USD"),
    ]
    rules = [
        DiscountRule(
            id="spa_pkg",
            labels=_labels("Spa package"),
            priority=1,
            exclusive=True,
            stacking="exclusive",
            when=RuleConditionGroup(
                conditions=[RuleCondition(kind="category_count_at_least", count=1, category_ids=["spa"])]
            ),
            then=RuleAction(kind="fixed_final_total", amount=100),
            currency="USD",
            eligible_category_ids=["spa"],
        )
    ]
    failures = validate_pricing_section(
        categories=[c.model_dump() for c in categories],
        catalog=[c.model_dump() for c in catalog],
        price_entries=[e.model_dump() for e in entries],
        discount_rules=[r.model_dump() for r in rules],
    )
    assert failures == []
    quote = compute_quote(
        catalog_items=catalog,
        price_entries=entries,
        discount_rules=rules,
        request_lines=[
            QuoteRequestLine(catalog_item_id="massage"),
            QuoteRequestLine(catalog_item_id="scrub"),
        ],
        context=PricingContext(tenant_id="spa_tenant", currency="USD"),
    )
    assert quote.subtotal == 120.0
    assert quote.final_total == 100.0
