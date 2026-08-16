"""Catalog item attachments persist on CM prices services."""

from __future__ import annotations

from services.cm.pricing.schemas import CatalogAttachment, CatalogItem
from services.cm.pricing.section import normalize_prices_section
from services.cm.schemas import LocalizedLabels


def test_catalog_item_keeps_image_video_link_attachments() -> None:
    item = CatalogItem(
        id="svc_laser",
        item_type="service",
        labels=LocalizedLabels(en="Laser hair removal"),
        description="Full treatment details and aftercare",
        attachments=[
            CatalogAttachment(
                id="cmed_img",
                kind="image",
                filename="aftercare.jpg",
                mime="image/jpeg",
                caption="Send after a session",
            ),
            CatalogAttachment(
                id="cmed_vid",
                kind="video",
                filename="clip.mp4",
                mime="video/mp4",
                duration_seconds=40,
            ),
            CatalogAttachment(
                id="link_1",
                kind="link",
                filename="example.com",
                url="https://example.com/prep",
            ),
        ],
    )
    dumped = item.model_dump(mode="json")
    assert dumped["attachments"][1]["kind"] == "video"
    roundtrip = CatalogItem.model_validate(dumped)
    assert roundtrip.attachments[2].kind == "link"
    assert roundtrip.attachments[2].url.startswith("https://")


def test_normalize_prices_section_preserves_catalog_attachments() -> None:
    section = normalize_prices_section(
        {
            "catalog": [
                {
                    "id": "svc_1",
                    "item_type": "service",
                    "labels": {"en": "Consultation", "ar": "", "fr": "", "franco": ""},
                    "attachments": [
                        {
                            "id": "cmed_a",
                            "kind": "file",
                            "filename": "prep.pdf",
                            "mime": "application/pdf",
                            "caption": "Prep sheet",
                        }
                    ],
                }
            ],
            "price_entries": [
                {
                    "id": "e1",
                    "catalog_item_id": "svc_1",
                    "amount": 0,
                    "currency": "USD",
                    "notes": "Consult",
                    "dimensions": {},
                }
            ],
        }
    )
    catalog = section.catalog
    assert isinstance(catalog, list)
    assert catalog[0]["attachments"][0]["filename"] == "prep.pdf"


def test_price_catalog_index_includes_note_and_media_caption() -> None:
    from services.cm.semantic_index import _price_catalog_entries

    rows = _price_catalog_entries(
        {
            "catalog": [
                {
                    "id": "svc_1",
                    "item_type": "service",
                    "labels": {"en": "Laser hair removal", "ar": "", "fr": "", "franco": ""},
                    "description": "Full treatment details and aftercare",
                    "attachments": [
                        {
                            "id": "cmed_a",
                            "kind": "image",
                            "filename": "after.jpg",
                            "caption": "Send after a session",
                        }
                    ],
                }
            ],
            "price_entries": [
                {
                    "id": "e1",
                    "catalog_item_id": "svc_1",
                    "amount": 100,
                    "currency": "USD",
                    "notes": "Standard session",
                    "duration_minutes": 60,
                    "dimensions": {},
                }
            ],
        }
    )
    assert len(rows) == 1
    text = rows[0][3]
    assert "Laser hair removal" in text
    assert "Full treatment details" in text
    assert "Standard session" in text
    assert "Send after a session" in text
