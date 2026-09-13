"""Isolated QA corpora. Not production Linas Laser business data."""

from __future__ import annotations

from typing import Any


def _week(open_t: str, close_t: str, *, sunday_off: bool = False) -> dict[str, Any]:
    day = {"enabled": True, "open": open_t, "close": close_t, "off_day": False}
    off = {"enabled": True, "open": "", "close": "", "off_day": True}
    week = {name: dict(day) for name in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")}
    week["sunday"] = dict(off) if sunday_off else dict(day)
    return week


def linas_like_qa_sections() -> dict[str, Any]:
    """Two-branch clinic shaped like Linas Laser, with distinct clocks and a QA product."""
    return {
        "ai_basics": {
            "assistant_name": "Lina QA",
            "clinic_name": "Linas Laser QA",
            "identity_summary": "QA clone. Never invent hours or prices.",
        },
        "style": {"tone": "friendly", "style_body": "Short replies. Quote published clocks exactly."},
        "knowledge": {
            "items": [
                {
                    "id": "greet_policy",
                    "title": "Greeting policy",
                    "body": "Use this rule only if the user message is only a casual greeting.",
                    "status": "active",
                }
            ]
        },
        "branches": {
            "items": [
                {
                    "id": "beirut",
                    "labels": {"en": "Beirut", "ar": "بيروت"},
                    "aliases": ["beirut", "بيروت"],
                    "phone": "+9611111111",
                    "weekly_schedule": _week("10:00", "20:00"),
                    "status": "active",
                },
                {
                    "id": "antelias",
                    "labels": {"en": "Antelias", "ar": "أنطلياس"},
                    "aliases": ["antelias", "أنطلياس", "antalyas"],
                    "phone": "+9611222222",
                    "weekly_schedule": _week("11:00", "19:00"),
                    "status": "active",
                },
            ]
        },
        "opening_hours": {
            "items": [
                {
                    "id": "oh_beirut",
                    "title": "Beirut Opening Hours",
                    "aliases": ["beirut hours"],
                    "monday": {"open": "10:00", "close": "20:00"},
                    "sunday": {"open": "10:00", "close": "20:00"},
                    "status": "active",
                },
                {
                    "id": "oh_antelias",
                    "title": "Antelias Opening Hours",
                    "aliases": ["antelias hours", "أنطلياس"],
                    "monday": {"open": "11:00", "close": "19:00"},
                    "sunday": {"open": "11:00", "close": "19:00"},
                    "status": "active",
                },
            ]
        },
        "prices": {
            "catalog": [
                {
                    "id": "laser",
                    "labels": {"en": "Laser hair removal", "ar": "ليزر"},
                    "aliases": ["laser", "ليزر"],
                    "active": True,
                    "attachments": [
                        {
                            "id": "att_laser_women",
                            "kind": "image",
                            "title": "Laser women photo",
                            "caption": "Send this photo when the customer asks for laser pictures.",
                            "url": "https://qa.linas.example/laser-women.png",
                            "status": "active",
                        },
                        {
                            "id": "att_laser_video",
                            "kind": "video",
                            "title": "Laser session video",
                            "caption": "Send this video when the customer asks how a laser session looks.",
                            "url": "https://qa.linas.example/videos/laser-session.mp4",
                            "status": "active",
                        },
                        {
                            "id": "att_laser_booking_link",
                            "kind": "link",
                            "title": "Laser booking link",
                            "caption": "Send this link when the customer asks for the booking page.",
                            "url": "https://qa.linas.example/book/laser",
                            "status": "active",
                        },
                    ],
                },
                {
                    "id": "face_laser",
                    "labels": {"en": "Face laser", "ar": "ليزر الوجه"},
                    "aliases": ["face laser", "ليزر الوجه"],
                    "active": True,
                    "attachments": [
                        {
                            "id": "att_face_photo",
                            "kind": "image",
                            "title": "Face laser photo",
                            "caption": "Send this photo for face laser examples.",
                            "url": "https://qa.linas.example/face-laser.png",
                            "status": "active",
                        }
                    ],
                },
            ],
            "price_entries": [
                {
                    "id": "laser_beirut",
                    "catalog_item_id": "laser",
                    "branch_id": "beirut",
                    "amount": 80,
                    "currency": "USD",
                    "active": True,
                },
                {
                    "id": "laser_antelias",
                    "catalog_item_id": "laser",
                    "branch_id": "antelias",
                    "amount": 70,
                    "currency": "USD",
                    "active": True,
                },
                {
                    "id": "face_beirut",
                    "catalog_item_id": "face_laser",
                    "branch_id": "beirut",
                    "amount": 50,
                    "currency": "USD",
                    "active": True,
                },
                {
                    "id": "face_antelias",
                    "catalog_item_id": "face_laser",
                    "branch_id": "antelias",
                    "amount": 45,
                    "currency": "USD",
                    "active": True,
                },
            ],
        },
        "faq": {
            "items": [
                {
                    "id": "faq_parking",
                    "title": "Parking",
                    "variants": [{"question": "Is parking available?", "answer": "Yes, street parking."}],
                    "status": "active",
                }
            ]
        },
        "requests_appointments": {
            "module_enabled": True,
            "enabled_types": ["APPOINTMENT", "ORDER", "HUMAN"],
            "rules": [
                {
                    "id": "req_appt",
                    "type": "APPOINTMENT",
                    "name": "موعد ليزر",
                    "notes": "Collect name, branch, preferred day. Confirm before submit.",
                    "enabled": True,
                },
                {
                    "id": "req_product",
                    "type": "ORDER",
                    "name": "طلب After Care",
                    "notes": "Collect product name and quantity. Confirm before submit.",
                    "enabled": True,
                },
                {
                    "id": "req_human",
                    "type": "HUMAN",
                    "name": "Human handoff",
                    "notes": "Escalate immediately. Do not keep answering.",
                    "enabled": True,
                    "scope": "handoff",
                },
            ],
        },
    }


def shop_b_qa_sections() -> dict[str, Any]:
    """Second tenant: same product name, different price, different hours and rules."""
    return {
        "ai_basics": {
            "assistant_name": "Nora QA",
            "clinic_name": "North Spa QA",
            "identity_summary": "QA tenant B. Never use Linas facts.",
        },
        "style": {"tone": "formal", "style_body": "Formal. Quote this tenant only."},
        "branches": {
            "items": [
                {
                    "id": "hamra",
                    "labels": {"en": "Hamra", "ar": "حمرا"},
                    "aliases": ["hamra", "حمرا"],
                    "phone": "+9619999999",
                    "weekly_schedule": _week("09:00", "15:00", sunday_off=True),
                    "status": "active",
                }
            ]
        },
        "prices": {
            "catalog": [
                {
                    "id": "alpha",
                    "labels": {"en": "Product Alpha", "ar": "منتج ألفا"},
                    "aliases": ["alpha", "product alpha"],
                    "active": True,
                }
            ],
            "price_entries": [
                {
                    "id": "alpha_hamra",
                    "catalog_item_id": "alpha",
                    "amount": 99,
                    "currency": "USD",
                    "active": True,
                }
            ],
        },
        "requests_appointments": {
            "module_enabled": True,
            "enabled_types": ["ORDER"],
            "rules": [
                {
                    "id": "req_b_order",
                    "type": "ORDER",
                    "name": "Shop B order",
                    "notes": "Ship to Hamra only. Never book appointments.",
                    "enabled": True,
                }
            ],
        },
    }


def linas_like_products() -> list[dict[str, Any]]:
    return [
        {
            "id": "alpha",
            "title": "Product Alpha",
            "description": "Linas QA Product Alpha. Price 10 USD.",
            "price": "10",
            "currency": "USD",
            "image_url": "https://qa.linas.example/alpha.png",
            "product_url": "https://qa.linas.example/products/alpha",
            "status": "active",
        },
        {
            "id": "aftercare_cream",
            "title": "After Care Cream",
            "description": "Post-laser cream. Price 25 USD.",
            "price": "25",
            "currency": "USD",
            "image_url": "https://qa.linas.example/aftercare.png",
            "product_url": "https://qa.linas.example/products/aftercare",
            "video_url": "https://qa.linas.example/videos/aftercare.mp4",
            "status": "active",
        },
    ]


def shop_b_products() -> list[dict[str, Any]]:
    return [
        {
            "id": "alpha",
            "title": "Product Alpha",
            "description": "Shop B Product Alpha. Price 99 USD.",
            "price": "99",
            "currency": "USD",
            "image_url": "https://qa.shopb.example/alpha.png",
            "product_url": "https://qa.shopb.example/products/alpha",
            "status": "active",
        }
    ]


def clinic_c_qa_sections() -> dict[str, Any]:
    """Third tenant: different city, off-day, HUMAN-only rules, unique knowledge."""
    return {
        "ai_basics": {
            "assistant_name": "Cora QA",
            "clinic_name": "Clinic C QA",
            "identity_summary": "QA tenant C. Never use Linas or Shop B facts.",
        },
        "style": {"tone": "direct", "style_body": "Direct. Quote this tenant only."},
        "knowledge": {
            "items": [
                {
                    "id": "c_policy",
                    "title": "Clinic C parking",
                    "body": "Clinic C has private garage parking in Jounieh only.",
                    "status": "active",
                }
            ]
        },
        "branches": {
            "items": [
                {
                    "id": "jounieh",
                    "labels": {"en": "Jounieh", "ar": "جونيه"},
                    "aliases": ["jounieh", "جونيه"],
                    "phone": "+9611333333",
                    "weekly_schedule": _week("08:00", "16:00", sunday_off=True),
                    "status": "active",
                }
            ]
        },
        "prices": {
            "catalog": [
                {
                    "id": "alpha",
                    "labels": {"en": "Product Alpha", "ar": "منتج ألفا"},
                    "aliases": ["alpha", "product alpha"],
                    "active": True,
                }
            ],
            "price_entries": [
                {
                    "id": "alpha_jounieh",
                    "catalog_item_id": "alpha",
                    "amount": 5,
                    "currency": "USD",
                    "active": True,
                }
            ],
        },
        "requests_appointments": {
            "module_enabled": True,
            "enabled_types": ["HUMAN"],
            "rules": [
                {
                    "id": "req_c_human",
                    "type": "HUMAN",
                    "name": "Clinic C human",
                    "notes": "Escalate only. Do not take orders or appointments.",
                    "enabled": True,
                    "scope": "handoff",
                }
            ],
        },
    }


def clinic_c_products() -> list[dict[str, Any]]:
    return [
        {
            "id": "alpha",
            "title": "Product Alpha",
            "description": "Clinic C Product Alpha. Price 5 USD.",
            "price": "5",
            "currency": "USD",
            "image_url": "https://qa.clinicc.example/alpha.png",
            "product_url": "https://qa.clinicc.example/products/alpha",
            "status": "active",
        }
    ]
