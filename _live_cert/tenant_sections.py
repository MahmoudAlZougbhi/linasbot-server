"""Published CM payload for the isolated V10 live-cert store."""

from __future__ import annotations

from typing import Any

from _live_cert.bootstrap import FAQ_AR_A, FAQ_AR_Q, FAQ_EN_A, FAQ_EN_Q
from tests.customer_reply_ai_v2_helpers import _rich_sections

APPT_SOURCE = "موعد Full Body\nجيب الاسم والعمر والطول والمنطقة واليوم المطلوب."
ORDER_SOURCE = "طلب After Care Cream\nجيب الاسم والكمية."


def _week_hours(open_t: str, close_t: str) -> dict[str, Any]:
    day = {"enabled": True, "open": open_t, "close": close_t, "off_day": False}
    off = {"enabled": False, "open": "", "close": "", "off_day": True}
    return {name: dict(day) for name in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")} | {
        "sunday": dict(off)
    }


def _oh_days(open_t: str, close_t: str) -> dict[str, Any]:
    day = {"closed": False, "open": open_t, "close": close_t}
    off = {"closed": True, "open": "", "close": ""}
    return {name: dict(day) for name in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")} | {
        "sunday": dict(off)
    }


def _att(**kwargs: Any) -> dict[str, Any]:
    row = {
        "status": "active",
        "sort_order": 0,
        "title": "",
        "description": "",
        "caption": "",
        "url": "",
        "mime": "",
        "filename": "",
        "size": 0,
    }
    row.update(kwargs)
    if not row.get("caption"):
        row["caption"] = str(row.get("description") or "")
    return row


def v10_store_sections(*, attachments: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, dict[str, Any]]:
    atts = attachments or {}
    women = list(atts.get("laser_women") or [])
    service_files = list(atts.get("laser_service") or [])
    cream_files = list(atts.get("cream_files") or [])
    comment_res = list(atts.get("comment_rule") or [])
    sections = _rich_sections()
    sections["ai_basics"] = {
        "assistant_name": "Lina",
        "clinic_name": "V10 Test Store",
        "ai_role": "customer assistant",
        "identity_summary": "Friendly assistant for V10 Test Store. Never invent price or availability.",
        "advanced_instructions": (
            "Be friendly. Never invent price or availability. Reply in the customer's language. "
            "Use only published prices, hours, and product facts."
        ),
        "greeting_behavior": "Greet warmly in the customer's language.",
    }
    sections["style"] = {
        "tone": "friendly",
        "formality": "casual",
        "style_body": "Short friendly replies. Never invent prices. Match the customer language.",
        "do_list": ["Be friendly", "Use published facts"],
        "dont_list": ["Invent price", "Invent availability"],
    }
    sections["services"] = {
        "items": [
            {
                "id": "svc_full_body",
                "labels": {"en": "Full Body", "ar": "فل بودي", "fr": "Full Body", "franco": ""},
                "available": True,
                "audience": "women",
                "aliases": ["full body", "فل بودي"],
                "notes": "Full Body laser session. Published price 299 USD.",
            },
            {
                "id": "svc_laser_women",
                "labels": {
                    "en": "Laser Hair Removal Women",
                    "ar": "ليزر شعر للنساء",
                    "fr": "Épilation laser femmes",
                    "franco": "",
                },
                "available": True,
                "audience": "women",
                "aliases": ["laser hair removal", "laser hair removal women", "ليزر شعر"],
                "notes": "Women laser hair removal. Send only the women photo resources on this service.",
                "attachments": women,
            },
            {
                "id": "svc_underarms",
                "labels": {"en": "Underarms", "ar": "تحت الإبط", "fr": "Aisselles", "franco": ""},
                "available": True,
                "audience": "women",
                "aliases": ["underarms", "underarm"],
                "notes": "Underarms laser session. Published price 49 USD.",
            },
        ]
    }
    sections["branches"] = {
        "items": [
            {
                "id": "br_beirut",
                "labels": {"en": "Beirut", "ar": "بيروت", "fr": "Beyrouth", "franco": ""},
                "address": "Beirut test street",
                "hours": {
                    "monday": "10:00-20:00",
                    "tuesday": "10:00-20:00",
                    "wednesday": "10:00-20:00",
                    "thursday": "10:00-20:00",
                    "friday": "10:00-20:00",
                    "saturday": "10:00-20:00",
                    "sunday": "",
                    "summary": "Beirut 10:00–20:00",
                },
                "weekly_schedule": _week_hours("10:00", "20:00"),
                "available": True,
                "notes": "Beirut closes 20:00.",
            },
            {
                "id": "br_antelias",
                "labels": {"en": "Antelias", "ar": "أنطلياس", "fr": "Antelias", "franco": ""},
                "address": "Antelias test road",
                "hours": {
                    "monday": "11:00-19:00",
                    "tuesday": "11:00-19:00",
                    "wednesday": "11:00-19:00",
                    "thursday": "11:00-19:00",
                    "friday": "11:00-19:00",
                    "saturday": "11:00-19:00",
                    "sunday": "",
                    "summary": "Antelias 11:00–19:00",
                },
                "weekly_schedule": _week_hours("11:00", "19:00"),
                "available": True,
                "notes": "Antelias closes 19:00.",
            },
        ],
        "timezone": "Asia/Beirut",
        "policy_text": "",
        "specific_off_rules": [],
    }
    sections["opening_hours"] = {
        "items": [
            {
                "id": "oh_beirut",
                "title": "Beirut Opening Hours",
                "notes": "Beirut 10:00–20:00",
                **_oh_days("10:00", "20:00"),
            },
            {
                "id": "oh_antelias",
                "title": "Antelias Opening Hours",
                "notes": "فرع أنطلياس بيسكر الساعة 19:00.",
                **_oh_days("11:00", "19:00"),
            },
        ]
    }
    sections["prices"] = {
        "items": [
            {"id": "price_full", "service_id": "svc_full_body", "amount": 299.0, "currency": "USD"},
            {"id": "price_underarms", "service_id": "svc_underarms", "amount": 49.0, "currency": "USD"},
        ]
    }
    sections["care"] = {
        "items": [
            {
                "id": "care_before",
                "title": "Before Session",
                "body": "Before Session: avoid sun 48 hours. شو لازم قبل الجلسة: لا تتعرض للشمس.",
                "status": "active",
                "language": "ar",
            },
            {
                "id": "care_after",
                "title": "After Care",
                "body": "After Care: moisturize. بعد الجلسة رطّب البشرة.",
                "status": "active",
                "language": "ar",
            },
        ]
    }
    sections["knowledge"] = {
        "items": [
            {
                "id": "kn_laser_service",
                "title": "Laser Hair Removal Service",
                "body": "Laser Hair Removal Service files for staff. Not the women photo set.",
                "status": "active",
                "attachments": service_files,
            },
            {
                "id": "kn_cancel",
                "title": "Cancellation Policy",
                "body": "Cancellation Policy: cancel at least 24 hours before. سياسة الإلغاء قبل 24 ساعة.",
                "status": "active",
                "attachments": cream_files,
            },
        ]
    }
    sections["faq"] = {
        "items": [
            {
                "qa_group_id": "faq_hours",
                "status": "active",
                "revision": 7,
                "variants": [
                    {"language": "ar", "question": FAQ_AR_Q, "answer": FAQ_AR_A},
                    {"language": "en", "question": FAQ_EN_Q, "answer": FAQ_EN_A},
                    {
                        "language": "fr",
                        "question": "Quels sont vos horaires ?",
                        "answer": "Beyrouth 10:00–20:00. Antelias 11:00–19:00.",
                    },
                    {"language": "franco", "question": "shu aw2at el dawam?", "answer": FAQ_AR_A},
                ],
            }
        ]
    }
    sections["comments"] = {
        "default_action": "reply_comment",
        "policy_text": "Keep public replies short and friendly.",
        "rules": [
            {
                "id": "rule_ai_global",
                "enabled": True,
                "name": "Global AI short friendly",
                "keywords": ["سعر", "قدي", "price", "hours", "دوام"],
                "action": "reply_comment",
                "rule_mode": "ai_guidance",
                "ai_action_mode": "reply_comment",
                "ai_instructions": "Reply publicly, short and friendly. Do not collect name/age/phone. Invite DM for booking. Do not replace published knowledge with this guidance.",
                "priority": 5,
                "scope": "all_posts",
                "trigger_type": "contains_any",
            },
            {
                "id": "rule_post_branch",
                "enabled": True,
                "name": "Post-specific ask branch",
                "keywords": ["سعر", "قدي", "أنطلياس", "انطلياس"],
                "action": "reply_comment",
                "rule_mode": "ai_guidance",
                "ai_action_mode": "reply_comment",
                "ai_instructions": "This promo post: mention Antelias branch hours from evidence. Still use real published price.",
                "priority": 9,
                "scope": "specific_post",
                "post_id": "POST_PROMO",
                "trigger_type": "contains_any",
            },
            {
                "id": "rule_livev10",
                "enabled": True,
                "name": "Deterministic LIVEV10TEST",
                "keywords": ["LIVEV10TEST", "TESTDM"],
                "action": "send_dm_static",
                "rule_mode": "deterministic",
                "reply_template": "V10 live cert static DM. No second copy.",
                "priority": 50,
                "scope": "all_posts",
                "trigger_type": "contains_any",
                "attachments": comment_res,
            },
            {
                "id": "rule_both",
                "enabled": True,
                "name": "Comment plus DM",
                "keywords": ["كود الخصم", "V10DUAL"],
                "action": "reply_comment_and_dm_static",
                "rule_mode": "deterministic",
                "reply_template": "تم، شيكي الخاص.",
                "dm_template": "كود الخصم بالخاص: V10TEST",
                "priority": 40,
                "scope": "all_posts",
                "trigger_type": "contains_any",
            },
        ],
    }
    sections["requests_appointments"] = {
        "module_enabled": True,
        "enabled_types": ["APPOINTMENT", "ORDER"],
        "rules": [
            {
                "id": "req_full_body",
                "type": "APPOINTMENT",
                "name": "موعد Full Body",
                "notes": APPT_SOURCE,
                "enabled": True,
            },
            {
                "id": "req_cream",
                "type": "ORDER",
                "name": "طلب After Care Cream",
                "notes": ORDER_SOURCE,
                "enabled": True,
            },
        ],
    }
    sections["ai_limits"] = {
        "unlimited": True,
        "voice_processing_enabled": True,
        "image_analysis_enabled": True,
        "text_words_per_message": 2000,
        "text_replies_per_day": 500,
        "text_replies_per_week": 2000,
        "text_replies_per_month": 8000,
        "photos_per_message": 8,
        "image_per_day": 50,
        "image_per_week": 200,
        "image_per_month": 800,
    }
    return sections
