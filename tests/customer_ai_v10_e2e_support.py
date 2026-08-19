"""Shared fixtures and traces for Customer AI V10 E2E workflow tests.

Mode: INTEGRATION SIMULATION (real orchestrator, fixture LLM, mock Meta).
Not a live Meta account test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def v10_clinic_sections() -> dict[str, dict[str, Any]]:
    sections = _rich_sections()
    sections["services"]["items"].append(
        {
            "id": "svc_full_body",
            "labels": {"en": "Full Body", "ar": "فل بودي", "fr": "Full Body"},
            "available": True,
            "audience": "women",
            "aliases": ["full body", "فل بودي"],
            "notes": "Full Body laser session. Price 299 USD.",
        }
    )
    sections["branches"]["items"].append(
        {
            "id": "br_antelias",
            "labels": {"en": "Antelias", "ar": "أنطلياس", "fr": "Antelias"},
            "address": "Antelias main road",
            "hours": {"monday": "10-20", "thursday": "10-20", "saturday": "10-18"},
            "available": True,
            "notes": "Antelias branch closes 8pm weekdays.",
        }
    )
    sections["opening_hours"] = {
        "items": [
            {
                "id": "oh_antelias",
                "title": "Antelias Opening Hours",
                "monday": {"open": "10:00", "close": "20:00"},
                "thursday": {"open": "10:00", "close": "20:00"},
                "saturday": {"open": "10:00", "close": "18:00"},
                "sunday": {"closed": True},
                "notes": "فرع أنطلياس بيسكر الساعة ٨ مساءً أيام الأسبوع.",
            }
        ]
    }
    sections["prices"]["items"].append(
        {"id": "price_full_antelias", "service_id": "svc_full_body", "amount": 299.0, "currency": "USD"}
    )
    sections["knowledge"]["items"].append(
        {
            "id": "kn_full_body",
            "title": "Full Body notes",
            "body": "Full Body is a full-leg and body laser package at Glow Clinic.",
            "status": "active",
        }
    )
    sections["comments"] = {
        "default_action": "reply_comment",
        "policy_text": "Keep public replies short. Ask private booking details in DM.",
        "rules": [
            {
                "id": "rule_ai_public",
                "enabled": True,
                "name": "Public price guidance",
                "keywords": ["سعر", "قدي", "price"],
                "action": "reply_comment",
                "rule_mode": "ai_guidance",
                "ai_action_mode": "reply_comment",
                "ai_instructions": "Reply publicly, short. Do not collect name/age/phone. Invite DM for booking.",
                "priority": 5,
                "scope": "all_posts",
            },
            {
                "id": "rule_post_override",
                "enabled": True,
                "name": "Promo post tone",
                "keywords": ["سعر", "قدي"],
                "action": "reply_comment",
                "rule_mode": "ai_guidance",
                "ai_action_mode": "reply_comment",
                "ai_instructions": "This promo post: mention the Full Body promo tone, still use real price evidence.",
                "priority": 9,
                "scope": "specific_post",
                "post_id": "POST_PROMO",
            },
            {
                "id": "rule_static_dm",
                "enabled": True,
                "name": "Static DM",
                "keywords": ["عرض خاص"],
                "action": "reply_dm",
                "rule_mode": "deterministic",
                "reply_template": "أرسلنا التفاصيل بالخاص.",
                "priority": 20,
            },
            {
                "id": "rule_both",
                "enabled": True,
                "name": "Public plus DM",
                "keywords": ["كود الخصم"],
                "action": "reply_comment_and_dm",
                "rule_mode": "deterministic",
                "reply_template": "تم، شيكي الخاص.",
                "dm_template": "كود الخصم بالخاص: GLOW10",
                "priority": 20,
            },
        ],
    }
    sections["requests_appointments"] = {
        "module_enabled": True,
        "enabled_types": ["APPOINTMENT"],
        "rules": [
            {
                "id": "req_full_body",
                "type": "APPOINTMENT",
                "name": "موعد Full Body",
                "notes": "موعد Full Body. جيب الاسم والعمر والطول والوزن والمنطقة واليوم المطلوب. لا تجمع هالبيانات على تعليق عام.",
                "enabled": True,
            }
        ],
    }
    return sections


def scripted_read(item_ids: list[str], *, effort: str = "medium") -> list[Any]:
    return [
        [{"name": "read_published_cm_items", "arguments": {"item_ids": item_ids}}],
        {
            "final_plan": {
                "evidence_status": "sufficient",
                "selected_source_ids": list(item_ids),
                "selected_section_ids": sorted({iid.split(":", 1)[0] for iid in item_ids}),
                "recommended_tera_effort": effort,
            }
        },
    ]


def trace_from_outcome(*, message: str, channel: str, out: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = dict(out.metadata or {})
    metering = dict(meta.get("metering") or {})
    ops = [str(row.get("operation") or "") for row in metering.get("invocations") or []]
    channel_meta = dict(meta.get("channel_metadata") or {})
    return {
        "mode": "INTEGRATION_SIMULATION",
        "incoming_message": message,
        "channel": channel,
        "surface": channel_meta.get("surface"),
        "is_public": channel_meta.get("is_public"),
        "safety": meta.get("safety_result"),
        "reason": out.reason,
        "reply": out.reply,
        "faq_direct": meta.get("faq_direct_reply"),
        "comment_rule_mode": meta.get("comment_rule_mode"),
        "comment_rule_id": meta.get("comment_rule_id"),
        "luna_called": "luna_retrieval" in ops,
        "tera_called": any(op.startswith("tera_") for op in ops),
        "selected_source_ids": list(meta.get("selected_source_ids") or []),
        "selected_section_ids": list(meta.get("selected_section_ids") or []),
        "tool_trace": list(meta.get("tool_trace") or []),
        "media_actions": meta.get("media_actions") or [],
        "media_delivery": meta.get("media_delivery") or {},
        "draft_result": meta.get("draft_result") or {},
        "metering": metering,
        "ai_called": meta.get("ai_called"),
        "cost_status": meta.get("cost_status"),
        "luna_recommended_tera_effort": meta.get("luna_recommended_tera_effort"),
        "ai_guidance_comment_rules": meta.get("ai_guidance_comment_rules") or [],
        **(extra or {}),
    }


async def install_hours_faq(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_tier(message: str, _lang: str) -> dict[str, Any] | None:
        if "أوقات" in (message or "") or "دوام" in (message or ""):
            return {
                "tier": "exact",
                "match_score": 1.0,
                "matched_language": "ar",
                "qa_pair": {
                    "id": "faq_hours",
                    "qa_group_id": "faq_hours",
                    "revision": "7",
                    "question": "شو أوقات الدوام؟",
                    "answer": "من الاثنين للسبت من 10 إلى 8.",
                    "language": "ar",
                },
            }
        return None

    monkeypatch.setattr("services.local_qa_service.local_qa_service.find_match_with_tier", _fake_tier)


@pytest.fixture()
def products_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, v2_env: Path) -> Path:
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    url = f"sqlite:///{tmp_path / 'v10_e2e_products.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    from db.models import Base
    from db.session import reset_engine_for_tests

    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()


def create_product(tenant: str, **kwargs: Any) -> dict[str, Any]:
    from db.session import whatsapp_session
    from services.products.schemas import ProductWriteBody
    from services.products.service import ProductsService

    kwargs.setdefault("description", kwargs.get("name") or "test product")
    with whatsapp_session(require=True) as session:
        return ProductsService(session).create_product(tenant_id=tenant, body=ProductWriteBody(**kwargs))


async def publish_clinic(tenant_id: str) -> None:
    await publish_test_content(tenant_id, v10_clinic_sections())
