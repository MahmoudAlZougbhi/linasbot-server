"""Generic CM Pricing Engine tests — one engine, multiple fixture tenants (no Lina code paths)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ai_setup.paths import indexes_dir, tenant_cm_root
from services.ai_setup.pricing.engine import compute_quote
from services.ai_setup.pricing.schemas import (
    CatalogCategory,
    CatalogItem,
    DiscountRule,
    PriceEntry,
    PricingContext,
    QuoteRequestLine,
    RuleAction,
    RuleCondition,
    RuleConditionGroup,
)
from services.ai_setup.pricing.validation import validate_pricing_section
from services.ai_setup.schemas import PricesSection
from services.ai_setup.storage import get_draft, put_draft
from services.ai_setup.version_store import version_dir
from tests.cm_pricing_engine_helpers import (
    _fixture_linas_style,
    _fixture_retail,
    _fixture_salon,
    _labels,
    seed_example_discount_rule_subtotal,
)


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
        assert quote.provenance["engine"] == "services.ai_setup.pricing.engine.compute_quote"


def test_tenant_isolation_storage_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))

    a = get_draft("prices", tenant_id="tenant_a", create_default=True)
    put_draft(
        "prices",
        payload=PricesSection(
            catalog=[
                {
                    "id": "a_only",
                    "item_type": "product",
                    "category_ids": ["cat_a"],
                    "labels": {"en": "A Item"},
                    "base_price": 11,
                    "currency": "USD",
                }
            ],
            price_entries=[{"id": "pe_a_only", "catalog_item_id": "a_only", "amount": 11, "currency": "USD"}],
        ).model_dump(mode="json"),
        if_match=a.etag,
        tenant_id="tenant_a",
        updated_by="test",
    )
    b = get_draft("prices", tenant_id="tenant_b", create_default=True)
    put_draft(
        "prices",
        payload=PricesSection(
            catalog=[
                {
                    "id": "b_only",
                    "item_type": "service",
                    "category_ids": ["cat_b"],
                    "labels": {"en": "B Item"},
                    "base_price": 22,
                    "currency": "EUR",
                }
            ],
            price_entries=[{"id": "pe_b_only", "catalog_item_id": "b_only", "amount": 22, "currency": "EUR"}],
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


def test_audit_no_linas_pricing_engine_in_code() -> None:
    forbidden = (
        "BodyPartPricingEngine",
        "body_part_pricing",
        "LinasPricingEngine",
        "linas_discount_threshold",
        "LINAS_PRICE_",
        "class BodyPartPrice",
    )
    scanned = 0
    findings = []
    root = Path(__file__).resolve().parents[1]
    for folder in (root / "services" / "ai_setup",):
        for path in folder.rglob("*.py"):
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for symbol in forbidden:
                if symbol in text:
                    findings.append(f"{path}:{symbol}")
    assert scanned > 0
    assert not findings, findings


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


def test_validate_pricing_section_invalid_discount_is_failure_not_exception() -> None:
    failures = validate_pricing_section(
        categories=[],
        catalog=[],
        price_entries=[],
        discount_rules=[
            {
                "id": "bad_rule",
                "then": {"kind": "percent_off", "percent": 150},
                "when": {"op": "and", "conditions": [], "groups": []},
            }
        ],
    )
    assert any(f.code == "PRICING_INVALID_DISCOUNT_RULE" for f in failures)
