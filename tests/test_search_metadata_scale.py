"""Incremental save and search scale simulations (no production backfill)."""

from __future__ import annotations

import time
from types import SimpleNamespace

from services.products.search_scoring import rank_products
from services.search_metadata.cm_apply import enrich_section_payload, last_cm_apply_stats
from services.search_metadata.generate import SearchMetadata, reset_metadata_generator, set_metadata_generator
from services.search_metadata.product_apply import enrich_product_row, last_product_apply_stats


def setup_function() -> None:
    reset_metadata_generator()


def teardown_function() -> None:
    reset_metadata_generator()


def test_save_one_knowledge_among_5000() -> None:
    calls: list[str] = []
    set_metadata_generator(
        lambda req: (
            calls.append(str(req.get("item_id")))
            or SearchMetadata(title="Updated File", description="Changed item only.")
        )
    )
    previous = {
        "items": [
            {
                "id": f"k{i}",
                "title": f"File {i}",
                "body": f"Body {i}",
                "status": "active",
                "ai_search_title": "Old",
                "ai_search_description": "Old desc",
            }
            for i in range(5000)
        ]
    }
    current = {"items": [dict(row) for row in previous["items"]]}
    current["items"][422]["body"] = "Session prices and shaving instructions."
    started = time.perf_counter()
    out = enrich_section_payload("knowledge", current, previous)
    elapsed = time.perf_counter() - started
    stats = last_cm_apply_stats()
    assert stats["generated_ids"] == ["k422"]
    assert calls == ["k422"]
    assert out["items"][1]["ai_search_title"] == "Old"
    assert elapsed < 8.0


def test_save_one_product_among_20000() -> None:
    calls: list[str] = []
    set_metadata_generator(
        lambda req: (
            calls.append(str(req.get("item_id")))
            or SearchMetadata(title="One Product", description="Changed product only.", keywords=["one"])
        )
    )
    row = SimpleNamespace(
        id="p19999",
        name="Nivea Soft",
        description="Face moisturizing cream",
        price="",
        sizes=[],
        colors=[],
        note="",
        availability="in_stock",
        ai_search_title=None,
        ai_search_description=None,
        ai_search_keywords=None,
        ai_search_title_normalized=None,
    )
    enrich_product_row(row, previous=None)
    assert last_product_apply_stats()["product_id"] == "p19999"
    assert calls == ["p19999"]


def test_rank_20000_products_original_query() -> None:
    rows = [
        SimpleNamespace(
            id=f"p{i}",
            name=f"Catalog {i:05d}",
            name_normalized=f"catalog {i:05d}",
            description="generic item",
            description_normalized="generic item",
            ai_search_title=f"Catalog Item {i:05d}",
            ai_search_description="generic catalog row",
            ai_search_keywords=["catalog"],
            note="",
        )
        for i in range(20000)
    ]
    rows[12345].name = "Nivea Face Cream"
    rows[12345].name_normalized = "nivea face cream"
    rows[12345].description = "Moisturizing cream for the face."
    rows[12345].description_normalized = "moisturizing cream for the face"
    rows[12345].ai_search_title = "Nivea Face Moisturizing Cream"
    started = time.perf_counter()
    scored = rank_products("nevia creem", rows, limit=5)
    elapsed = time.perf_counter() - started
    assert scored
    assert scored[0][1].id == "p12345"
    assert elapsed < 12.0


def test_save_one_comment_rule_among_300() -> None:
    calls: list[str] = []
    set_metadata_generator(
        lambda req: (
            calls.append(str(req.get("item_id")))
            or SearchMetadata(title="Comment AI Rule", description="One comment rule.")
        )
    )
    previous = {
        "rules": [
            {
                "id": f"c{i}",
                "name": f"Rule {i}",
                "rule_mode": "ai_guidance",
                "ai_instructions": "x",
                "enabled": True,
                "ai_search_title": "Old",
                "ai_search_description": "Old",
            }
            for i in range(300)
        ]
    }
    current = {"rules": [dict(row) for row in previous["rules"]]}
    current["rules"][77]["ai_instructions"] = "أجب عن التعليق باختصار"
    enrich_section_payload("comments", current, previous)
    assert last_cm_apply_stats()["generated_ids"] == ["c77"]
    assert calls == ["c77"]


def test_request_and_comment_counts_do_not_expand_save() -> None:
    calls: list[str] = []
    set_metadata_generator(
        lambda req: calls.append(str(req.get("item_id"))) or SearchMetadata(title="Rule", description="One rule.")
    )
    previous = {
        "rules": [
            {
                "id": f"r{i}",
                "name": f"Rule {i}",
                "notes": "x",
                "enabled": True,
                "ai_search_title": "Old",
                "ai_search_description": "Old",
            }
            for i in range(600)
        ]
    }
    current = {"rules": [dict(row) for row in previous["rules"]]}
    current["rules"][10]["notes"] = "Updated appointment capture note"
    enrich_section_payload("requests_appointments", current, previous)
    assert last_cm_apply_stats()["generated_ids"] == ["r10"]
    assert calls == ["r10"]
