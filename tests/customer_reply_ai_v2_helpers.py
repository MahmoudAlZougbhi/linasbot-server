"""Published-content sections for Customer Reply AI V2 tests."""

from __future__ import annotations

from typing import Any


def _rich_sections() -> dict[str, dict[str, Any]]:
    return {
        "ai_basics": {
            "assistant_name": "Lina",
            "clinic_name": "Glow Clinic",
            "identity_summary": "Friendly clinic assistant for Glow Clinic.",
            "advanced_instructions": "Always be accurate. Never invent prices.",
        },
        "style": {
            "tone": "warm",
            "formality": "casual",
            "style_body": "Short replies. Use the customer name sparingly.",
            "do_list": ["Be clear"],
            "dont_list": ["Invent prices"],
        },
        "services": {
            "items": [
                {
                    "id": "svc_full",
                    "labels": {"en": "Full body laser", "ar": "ليزر كامل", "fr": "Laser complet"},
                    "available": True,
                    "audience": "women",
                    "aliases": ["full", "full body"],
                },
                {
                    "id": "svc_face",
                    "labels": {"en": "Face laser", "ar": "ليزر وجه", "fr": "Laser visage"},
                    "available": True,
                    "audience": "general",
                },
            ]
        },
        "branches": {
            "items": [
                {
                    "id": "br_beirut",
                    "labels": {"en": "Beirut", "ar": "بيروت", "fr": "Beyrouth"},
                    "address": "Hamra St",
                    "hours": {"monday": "10-18", "tuesday": "10-18"},
                    "available": True,
                },
                {
                    "id": "br_other",
                    "labels": {"en": "Other Branch", "ar": "فرع آخر", "fr": "Autre branche"},
                    "address": "Jounieh",
                    "available": True,
                },
            ]
        },
        "prices": {
            "items": [
                {"id": "price_full_w", "service_id": "svc_full", "amount": 299.0, "currency": "USD"},
                {"id": "price_face", "service_id": "svc_face", "amount": 99.0, "currency": "USD"},
            ]
        },
        "care": {
            "items": [
                {
                    "id": "care_pre",
                    "title": "Before session",
                    "body": "Avoid sun 48h before. شو لازم أعمل قبل الجلسة: لا تتعرض للشمس.",
                    "status": "active",
                    "language": "ar",
                },
                {
                    "id": "care_post",
                    "title": "After session",
                    "body": "Moisturize after. وبعدها رطب البشرة.",
                    "status": "active",
                    "language": "ar",
                },
            ]
        },
        "knowledge": {
            "items": [
                {
                    "id": "kn_hours",
                    "title": "Opening hours note",
                    "body": "We are open tomorrow except public holidays.",
                    "status": "active",
                }
            ]
        },
        "faq": {
            "items": [
                {
                    "qa_group_id": "faq_hours",
                    "status": "active",
                    "variants": [
                        {"language": "en", "question": "What are your hours?", "answer": "We open 10am to 6pm."},
                        {"language": "ar", "question": "شو أوقاتكم؟", "answer": "منفتح من ١٠ ل ٦."},
                        {"language": "fr", "question": "Quels sont vos horaires ?", "answer": "Ouvert de 10h à 18h."},
                        {"language": "franco", "question": "shu aw2atkon?", "answer": "منفتح من ١٠ ل ٦."},
                    ],
                }
            ]
        },
        "off_days": {"days": [], "specific_days": []},
        "handoff": {
            "contacts": [
                {"id": "c1", "label": "WA", "destination_type": "whatsapp", "destination_value": "+96170000000"}
            ],
            "matrix": [{"id": "m1", "enabled": True, "contact_id": "c1"}],
        },
        "restricted": {
            "topics": [
                {
                    "id": "tattoo_removal",
                    "active": True,
                    "labels": {"en": "Tattoo removal", "ar": "إزالة الوشم"},
                    "keywords": ["tattoo removal", "إزالة الوشم"],
                    "refuse_template": "We do not offer tattoo removal.",
                }
            ]
        },
        "actions": {
            "items": [
                {"id": "human_handoff", "enabled": True},
            ]
        },
    }
