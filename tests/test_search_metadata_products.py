"""Product description, English search metadata, query preservation, no invented facts."""

from __future__ import annotations

from types import SimpleNamespace

from services.ai_setup.search_metadata.generate import (
    SearchMetadata,
    is_weak_owner_description,
    reset_metadata_generator,
    set_metadata_generator,
)
from services.ai_setup.search_metadata.product_apply import (
    enrich_product_row,
    last_product_apply_stats,
    product_content_payload,
)


def setup_function() -> None:
    reset_metadata_generator()


def teardown_function() -> None:
    reset_metadata_generator()


def _row(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": "p1",
        "name": "Nivea",
        "description": "",
        "price": "10",
        "sizes": [],
        "colors": [],
        "note": "",
        "availability": "in_stock",
        "ai_search_title": None,
        "ai_search_description": None,
        "ai_search_keywords": None,
        "ai_search_title_normalized": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_weak_description_detection() -> None:
    assert is_weak_owner_description("aaa") is True
    assert is_weak_owner_description("good product") is True
    assert is_weak_owner_description("123") is True
    assert is_weak_owner_description("Face moisturizing cream") is False


def test_nivea_soft_uses_owner_description_fact() -> None:
    calls: list[dict] = []

    def gen(req: dict) -> SearchMetadata:
        calls.append(req)
        return SearchMetadata(
            title="Nivea Face Moisturizing Cream",
            description="Face moisturizing cream from the owner description.",
            keywords=["nivea", "face", "cream"],
        )

    set_metadata_generator(gen)
    row = _row(name="Nivea Soft", description="Face moisturizing cream")
    assert enrich_product_row(row) is True
    assert row.name == "Nivea Soft"
    assert "Face" in row.ai_search_title
    assert "cream" in " ".join(row.ai_search_keywords).lower()
    assert "Face moisturizing cream" in calls[0]["content"]


def test_weak_description_does_not_invent_face_cream() -> None:
    set_metadata_generator(
        lambda req: SearchMetadata(
            title="Nivea Face Cream",
            description="Face cream for dry skin after laser.",
            keywords=["face", "laser"],
        )
    )
    row = _row(name="Nivea", description="aaa")
    enrich_product_row(row)
    blob = f"{row.ai_search_title} {row.ai_search_description} {row.ai_search_keywords}".lower()
    assert "face cream" not in blob
    assert "laser" not in blob
    assert row.name == "Nivea"


def test_good_product_does_not_invent_category() -> None:
    set_metadata_generator(
        lambda req: SearchMetadata(
            title="ABC Wireless Headset",
            description="Noise cancelling headset for calls.",
            keywords=["headset", "audio"],
        )
    )
    row = _row(name="ABC", description="good product")
    enrich_product_row(row)
    blob = f"{row.ai_search_title} {row.ai_search_description}".lower()
    assert "headset" not in blob
    assert row.name == "ABC"


def test_arabic_weak_description_does_not_keep_invented_title() -> None:
    set_metadata_generator(
        lambda req: SearchMetadata(
            title="Nivea Face Cream",
            description="Face cream for dry skin.",
            keywords=["face", "laser"],
        )
    )
    row = _row(name="نيفيا", description="aaa")
    enrich_product_row(row)
    assert row.name == "نيفيا"
    blob = f"{row.ai_search_title} {row.ai_search_description} {row.ai_search_keywords}".lower()
    assert "face cream" not in blob
    assert "laser" not in blob
    assert row.ai_search_title == "Catalog product"


def test_arabic_product_keeps_user_data_english_metadata() -> None:
    set_metadata_generator(
        lambda req: SearchMetadata(title="Nivea Soft Cream", description="Named catalog product.", keywords=["nivea"])
    )
    row = _row(name="نيفيا", description="كريم للوجه")
    enrich_product_row(row)
    assert row.name == "نيفيا"
    assert row.description == "كريم للوجه"
    assert row.ai_search_title == "Nivea Soft Cream"


def test_chinese_product_keeps_user_data() -> None:
    set_metadata_generator(
        lambda req: SearchMetadata(title="Moisturizing Cream", description="Owner-described cream.", keywords=["cream"])
    )
    row = _row(name="妮维雅", description="面霜")
    enrich_product_row(row)
    assert row.name == "妮维雅"
    assert row.description == "面霜"


def test_one_product_save_does_not_touch_others() -> None:
    calls: list[dict] = []
    set_metadata_generator(
        lambda req: calls.append(req) or SearchMetadata(title="One", description="One item.", keywords=["one"])
    )
    previous = product_content_payload(_row(id="unchanged", name="Keep", description="same"))
    row = _row(id="p422", name="Changed", description="Face moisturizing cream")
    enrich_product_row(row, previous=None)
    assert last_product_apply_stats()["product_id"] == "p422"
    assert last_product_apply_stats()["generated"] is True
    unchanged = _row(id="unchanged", name="Keep", description="same")
    assert enrich_product_row(unchanged, previous=previous) is False
    assert [c["item_id"] for c in calls] == ["p422"]
