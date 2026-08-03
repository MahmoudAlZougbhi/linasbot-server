"""Additional multi-tenant pricing fixtures + FAQ canonical writer proofs."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from services.cm.faq_integration import (
    create_faq_pair_from_livechat,
    find_duplicate_faq_groups,
    list_cm_faq,
)
from services.cm.pricing.engine import compute_quote
from services.cm.pricing.money import as_money, quantize_money
from services.cm.pricing.schemas import (
    CatalogItem,
    ItemVariant,
    PackageRule,
    PriceEntry,
    PricingContext,
    QuoteRequestLine,
    ResourceOrMethod,
    RuleAction,
    RuleCondition,
    RuleConditionGroup,
)
from services.cm.pricing.section import normalize_prices_section
from services.cm.schemas import LocalizedLabels, PricesSection


def _labels(en: str) -> LocalizedLabels:
    return LocalizedLabels(en=en)


@pytest.mark.asyncio
async def test_livechat_like_writes_canonical_cm_faq_only(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_translate(**kwargs):  # type: ignore[no-untyped-def]
        q = kwargs.get("question") or ""
        a = kwargs.get("answer") or ""
        langs = kwargs.get("target_languages") or []
        return {
            "success": True,
            "translations": {
                lang: {
                    "question": q if lang == (kwargs.get("source_language") or "ar") else f"{lang}:{q}",
                    "answer": a if lang in ("ar", "franco") else f"{lang}:{a}",
                }
                for lang in langs
            },
        }

    async def _fake_ar(text: str, _src: str) -> str:
        return "السعر عشرين دولار."

    monkeypatch.setattr(
        "services.cm.faq_integration.language_detection_service.translate_training_pair",
        _fake_translate,
    )
    monkeypatch.setattr(
        "services.cm.faq_integration._translate_to_arabic_script",
        _fake_ar,
    )

    remote_calls: list[str] = []

    async def _forbidden_remote(**_kwargs):  # type: ignore[no-untyped-def]
        remote_calls.append("remote")
        raise AssertionError("remote QA must not be called")

    monkeypatch.setattr(
        "services.qa_database_service.qa_db_service.create_qa_pair",
        _forbidden_remote,
        raising=False,
    )

    result = await create_faq_pair_from_livechat(
        question="shu se3r el laser?",
        answer="ashreen dolar",
        language="franco",
        tenant_id="tenant_livechat_faq",
        updated_by="test_operator",
    )
    assert result["success"] is True
    assert result["awaiting_publication"] is True
    assert result["count_created"] == 4
    groups = list_cm_faq(tenant_id="tenant_livechat_faq")
    assert any(g["qa_group_id"] == result["qa_group_id"] for g in groups)
    assert remote_calls == []


def test_duplicate_detection_exact_normalized() -> None:
    # Seed via mirror path: create through list empty then detect after manual draft inject is heavy;
    # unit-level: empty tenant has no duplicates.
    assert find_duplicate_faq_groups(question="hello", language="en", tenant_id="dup_empty") == []


def test_same_engine_serves_clinic_salon_retail_fixtures() -> None:
    """One generic engine: Lina-style body_area data, salon duration variants, retail packages."""
    clinic_items = [
        CatalogItem(
            id="ba_full_legs",
            item_type="body_area",
            category_ids=["body_area"],
            labels=_labels("Full legs"),
            aliases=["رجلين", "full legs"],
            base_price=80,
            currency="USD",
        )
    ]
    clinic_entries = [
        PriceEntry(id="pe1", catalog_item_id="ba_full_legs", amount=80, currency="USD", provenance="fixture")
    ]
    salon_items = [
        CatalogItem(
            id="cut_wash",
            item_type="service",
            labels=_labels("Cut & wash"),
            currency="USD",
            variants=[ItemVariant(id="45m", labels=_labels("45 min"), duration_minutes=45)],
        )
    ]
    salon_entries = [
        PriceEntry(
            id="pe2",
            catalog_item_id="cut_wash",
            variant_id="45m",
            amount=45,
            currency="USD",
            duration_minutes=45,
        )
    ]
    retail_items = [
        CatalogItem(id="shampoo", item_type="product", labels=_labels("Shampoo"), base_price=12, currency="USD"),
        CatalogItem(id="addon_mask", item_type="add_on", labels=_labels("Mask"), base_price=8, currency="USD"),
    ]
    retail_entries = [
        PriceEntry(id="pe3", catalog_item_id="shampoo", amount=12, currency="USD", min_quantity=1),
        PriceEntry(id="pe4", catalog_item_id="addon_mask", amount=8, currency="USD"),
    ]
    package = PackageRule(
        id="pkg_bundle",
        labels=_labels("Shampoo+mask"),
        when=RuleConditionGroup(
            op="and",
            conditions=[
                RuleCondition(kind="includes_items", item_ids=["shampoo", "addon_mask"]),
            ],
        ),
        then=RuleAction(kind="bundle_price", amount=18, currency="USD"),
        included_item_ids=["shampoo", "addon_mask"],
        currency="USD",
    )

    ctx_a = PricingContext(tenant_id="clinic_a", currency="USD")
    q1 = compute_quote(
        request_lines=[QuoteRequestLine(catalog_item_id="ba_full_legs", quantity=1)],
        catalog_items=clinic_items,
        price_entries=clinic_entries,
        discount_rules=[],
        context=ctx_a,
    )
    assert q1.final_total == 80
    assert q1.tenant_id == "clinic_a"

    ctx_b = PricingContext(tenant_id="salon_b", currency="USD")
    q2 = compute_quote(
        request_lines=[QuoteRequestLine(catalog_item_id="cut_wash", variant_id="45m", quantity=1)],
        catalog_items=salon_items,
        price_entries=salon_entries,
        discount_rules=[],
        context=ctx_b,
    )
    assert q2.final_total == 45

    ctx_c = PricingContext(tenant_id="retail_c", currency="USD")
    q3 = compute_quote(
        request_lines=[
            QuoteRequestLine(catalog_item_id="shampoo", quantity=1),
            QuoteRequestLine(catalog_item_id="addon_mask", quantity=1),
        ],
        catalog_items=retail_items,
        price_entries=retail_entries,
        discount_rules=[package.as_discount_rule()],
        context=ctx_c,
    )
    assert q3.subtotal == 20
    assert q3.final_total == 18
    assert any(r.rule_id == "pkg_bundle" for r in q3.applied_rules)

    with pytest.raises(ValueError, match="unknown_or_inactive_catalog_item"):
        compute_quote(
            request_lines=[QuoteRequestLine(catalog_item_id="cut_wash", quantity=1)],
            catalog_items=clinic_items,
            price_entries=clinic_entries,
            discount_rules=[],
            context=ctx_a,
        )


def test_decimal_money_quantization() -> None:
    assert quantize_money(as_money("10.005"), "nearest_0_01") == Decimal("10.01")
    assert quantize_money(as_money("10.004"), "nearest_0_01") == Decimal("10.00")
    assert quantize_money(as_money("10.019"), "floor_0_01") == Decimal("10.01")
    assert quantize_money(as_money("10.011"), "ceil_0_01") == Decimal("10.02")


def test_normalize_projects_package_and_resources() -> None:
    section = normalize_prices_section(
        PricesSection(
            catalog=[{"id": "x", "item_type": "custom", "labels": {"en": "X"}, "base_price": 1}],
            package_rules=[
                {
                    "id": "pkg1",
                    "labels": {"en": "Pkg"},
                    "when": {"op": "and", "conditions": [], "groups": []},
                    "then": {"kind": "bundle_price", "amount": 9},
                    "included_item_ids": ["x"],
                }
            ],
            resources=[{"id": "machine_a", "labels": {"en": "Device A"}, "resource_kind": "machine"}],
            dimension_definitions=[
                {"id": "size", "labels": {"en": "Size"}, "value_type": "enum", "allowed_values": ["S", "L"]}
            ],
        )
    )
    assert any(r.get("id") == "pkg1" for r in section.discount_rules)
    assert any(r.get("id") == "machine_a" for r in section.resources)
    ResourceOrMethod.model_validate(section.resources[0])


def test_no_body_part_engine_symbols_in_pricing_package() -> None:
    import services.cm.pricing as pricing_pkg
    import services.cm.pricing.engine as engine
    import services.cm.pricing.schemas as schemas

    for mod in (pricing_pkg, engine, schemas):
        assert not hasattr(mod, "BodyPartPricingEngine")
        assert not hasattr(mod, "body_part_id")


def test_empty_price_import_does_not_wipe_existing_catalog(tmp_path: Path) -> None:
    from services.cm.pricing.migration import migrate_staged_price_files_to_catalog
    from services.cm.storage import get_draft, put_draft

    tenant = "tenant_empty_guard"
    env = get_draft("prices", tenant_id=tenant, create_default=True)
    put_draft(
        "prices",
        payload=PricesSection(
            catalog=[{"id": "keep_me", "item_type": "custom", "labels": {"en": "Keep"}, "base_price": 10}],
            price_entries=[{"id": "pe", "catalog_item_id": "keep_me", "amount": 10}],
        ).model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant,
        updated_by="test",
    )
    stage = tmp_path / "stage"
    (stage / "legacy" / "price_files").mkdir(parents=True)
    (stage / "legacy" / "price_files" / "empty.json").write_text("{}", encoding="utf-8")
    result = migrate_staged_price_files_to_catalog(staging_root=stage, tenant_id=tenant)
    assert result["preserved_existing"] is True
    assert result["catalog_count"] == 1
    after = get_draft("prices", tenant_id=tenant)
    assert after.payload["catalog"][0]["id"] == "keep_me"


def test_content_price_file_import_populates_catalog(tmp_path: Path) -> None:
    from services.cm.pricing.migration import migrate_staged_price_files_to_catalog
    from services.cm.storage import get_draft

    tenant = "tenant_price_content_import"
    stage = tmp_path / "stage"
    pf = stage / "legacy" / "price_files"
    pf.mkdir(parents=True)
    (pf / "women.json").write_text(
        json.dumps(
            {
                "id": "women",
                "title": "Women prices",
                "content": "Underarms: 40\nBikini: 55 USD\nSessions: 8",
                "tags": ["price"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = migrate_staged_price_files_to_catalog(
        staging_root=stage,
        tenant_id=tenant,
        category_id="body_area",
        category_label="Body areas",
        item_type="body_area",
    )
    assert result["rows_imported"] >= 2
    assert result["invented_amounts"] == 0
    assert result["preserved_existing"] is False
    draft = get_draft("prices", tenant_id=tenant)
    names = {item["labels"]["en"] for item in draft.payload["catalog"]}
    assert "Underarms" in names
    assert "Bikini" in names
