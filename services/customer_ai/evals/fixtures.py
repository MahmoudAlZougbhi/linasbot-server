"""Cross-business fixtures. Not special runtime branches."""

from __future__ import annotations

from typing import Any


def service_appointment_corpus() -> dict[str, Any]:
    return {
        "prices": {
            "catalog": [
                {
                    "id": "laser",
                    "labels": {"en": "Laser hair removal", "ar": "إزالة الشعر"},
                    "aliases": ["lazer"],
                    "active": True,
                }
            ],
            "price_entries": [
                {"id": "e1", "catalog_item_id": "laser", "amount": 80, "currency": "USD", "unit": "session", "active": True}
            ],
        },
        "opening_hours": {"items": [{"id": "main", "title": "Clinic hours", "monday": {"open": "10:00", "close": "20:00"}}]},
        "faq": {"items": []},
    }


def product_retailer_corpus() -> dict[str, Any]:
    return {
        "knowledge": {"items": [{"id": "ship", "title": "Shipping", "body": "Orders ship in two days.", "ai_search_description": "shipping"}]},
        "prices": {"catalog": []},
    }


def hospitality_corpus() -> dict[str, Any]:
    return {
        "opening_hours": {
            "items": [{"id": "kitchen", "title": "Kitchen hours", "friday": {"open": "12:00", "close": "23:00"}, "sunday": {"closed": True}}]
        },
        "knowledge": {"items": [{"id": "menu", "title": "Menu notes", "body": "No peanuts in the kitchen.", "ai_search_description": "allergy"}]},
    }


def knowledge_heavy_corpus() -> dict[str, Any]:
    return {
        "knowledge": {
            "items": [
                {
                    "id": "policy",
                    "title": "Refund booklet",
                    "body": "Refunds are allowed within seven days. After seven days refunds are not allowed.",
                    "ai_search_description": "refund policy deadline",
                }
            ]
        }
    }
