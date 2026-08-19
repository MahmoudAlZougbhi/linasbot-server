"""Live Luna+Terra multi-intent path. Skips when no real OpenAI key is present."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _live_cert.bootstrap import load_openai_key, looks_real_openai_key
from tests.cm_test_helpers import publish_pointer_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


@pytest.mark.asyncio
async def test_scripted_multi_intent_selects_beirut_hours_product_and_one_rule(
    v2_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import create_engine, event

    from db.models import Base
    from db.session import reset_engine_for_tests, whatsapp_session
    from services.cm.request_rules import format_request_rules_for_ai
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna
    from services.products.schemas import ProductWriteBody
    from services.products.service import ProductsService

    url = f"sqlite:///{Path(str(v2_env)) / 'scripted_multi.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    sections = _rich_sections()
    sections["opening_hours"] = {
        "items": [
            {
                "id": "oh_beirut",
                "title": "ساعات بيروت",
                "monday": {"closed": False, "open": "10:00", "close": "18:00"},
                "sunday": {"closed": True, "open": "", "close": ""},
            }
        ]
    }
    sections["off_days"] = {
        "timezone": "Asia/Beirut",
        "rules": [{"id": "sun", "kind": "weekly", "weekday": 6, "reason": "Sunday closed"}],
    }
    sections["requests_appointments"] = {
        "module_enabled": True,
        "enabled_types": ["APPOINTMENT", "ORDER"],
        "rules": [
            {
                "id": "appt1",
                "type": "APPOINTMENT",
                "name": "حجز موعد",
                "notes": "يجمع التاريخ",
                "enabled": True,
            },
            {
                "id": "order1",
                "type": "ORDER",
                "name": "طلب شراء",
                "notes": "طلب منتجات",
                "enabled": True,
            },
        ],
    }
    publish_pointer_content("t_scripted_multi", sections)
    with whatsapp_session(require=True) as session:
        ProductsService(session).create_product(
            tenant_id="t_scripted_multi",
            body=ProductWriteBody(
                name="Nivea Face Cream",
                description="Face moisturizing cream.",
                price="12 USD",
                sizes=[],
                colors=[],
                links=[],
            ),
        )

    retrieval = await run_retrieval_luna(
        tenant_id="t_scripted_multi",
        message="أي ساعة فاتحين بفرع بيروت؟ وعندكم نيفيا فيس كريم؟ وبدي احجز موعد.",
        customer_profile={},
        scripted_tool_calls=[
            [
                {
                    "name": "read_published_cm_items",
                    "arguments": {"item_ids": ["branches:br_beirut", "opening_hours:oh_beirut"]},
                },
                {
                    "name": "search_product_by_title",
                    "arguments": {
                        "title": "نيفيا فيس كريم",
                        "original_query": "نيفيا فيس كريم",
                        "alternate_queries": ["Nivea Face Cream"],
                    },
                },
            ],
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": [
                        "branches:br_beirut",
                        "opening_hours:oh_beirut",
                        "requests_appointments:appt1",
                    ],
                    "recommended_tera_effort": "medium",
                }
            },
        ],
    )
    ids = {e.source_id for e in retrieval.evidence}
    assert "branches:br_beirut" in ids
    assert "opening_hours:oh_beirut" in ids
    assert "br_other" not in str(ids)
    blob = " ".join(e.content for e in retrieval.evidence)
    assert "Sunday closed" in blob or "weekly_off_days" in blob
    assert "12 USD" in blob or retrieval.product_match_found is True
    guidance = format_request_rules_for_ai(
        sections["requests_appointments"],
        selected_ids=["requests_appointments:appt1"],
    )
    assert "حجز موعد" in guidance
    assert "طلب شراء" not in guidance


@pytest.mark.asyncio
async def test_live_multi_intent_beirut_hours_product_appointment(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    key = load_openai_key()
    if not looks_real_openai_key(key):
        pytest.skip("no real OPENAI_API_KEY for live Luna/Terra")

    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("LINAS_SEARCH_METADATA_LLM", "0")
    monkeypatch.setenv("CUSTOMER_AI_V10_RUNTIME", "true")

    from openai import AsyncOpenAI

    import config
    from services import llm_core_service

    config.OPENAI_API_KEY = key
    llm_core_service.client = AsyncOpenAI(api_key=key)

    from sqlalchemy import create_engine, event

    from db.models import Base
    from db.session import reset_engine_for_tests, whatsapp_session
    from services.products.schemas import ProductWriteBody
    from services.products.service import ProductsService
    from tests.cm_test_helpers import publish_test_content
    from tests.customer_reply_ai_v2_helpers import _rich_sections

    url = f"sqlite:///{Path(str(v2_env)) / 'live_multi.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    sections = _rich_sections()
    sections["branches"]["items"][0]["weekly_schedule"] = {
        "monday": {"enabled": True, "open": "10:00", "close": "18:00", "off_day": False},
        "sunday": {"enabled": True, "open": "", "close": "", "off_day": True},
    }
    sections["opening_hours"] = {
        "items": [
            {
                "id": "oh_beirut",
                "title": "ساعات بيروت",
                "monday": {"closed": False, "open": "10:00", "close": "18:00"},
                "sunday": {"closed": True, "open": "", "close": ""},
                "ai_search_title": "Beirut Weekly Opening Hours",
                "ai_search_description": "Open and close times for Beirut.",
            }
        ]
    }
    sections["off_days"] = {
        "timezone": "Asia/Beirut",
        "rules": [{"id": "sun", "kind": "weekly", "weekday": 6, "reason": "Sunday closed"}],
    }
    sections["requests_appointments"] = {
        "module_enabled": True,
        "enabled_types": ["APPOINTMENT"],
        "rules": [
            {
                "id": "appt1",
                "type": "APPOINTMENT",
                "name": "حجز موعد",
                "notes": "يجمع التاريخ والهاتف",
                "enabled": True,
                "ai_search_title": "Appointment Booking",
                "ai_search_description": "Captures appointment date and phone.",
            },
            {
                "id": "other",
                "type": "ORDER",
                "name": "طلب شراء",
                "notes": "طلب منتجات",
                "enabled": True,
                "ai_search_title": "Product Order",
                "ai_search_description": "Captures product order fields.",
            },
        ],
    }
    await publish_test_content("t_live_multi", sections)

    with whatsapp_session(require=True) as session:
        ProductsService(session).create_product(
            tenant_id="t_live_multi",
            body=ProductWriteBody(
                name="Nivea Face Cream",
                description="Face moisturizing cream.",
                price="12 USD",
                sizes=[],
                colors=[],
                links=[],
            ),
        )

    from services.customer_reply_v2.answer_luna import run_answer_luna
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    message = "مرحبا، أي ساعة فاتحين بفرع بيروت؟ وعندكم نيفيا فيس كريم؟ وإذا موجود قدي سعره؟ وبدي احجز موعد بكرا."
    try:
        retrieval = await run_retrieval_luna(
            tenant_id="t_live_multi",
            message=message,
            customer_profile={},
            channel="instagram_dm",
        )
        answer = await run_answer_luna(
            tenant_id="t_live_multi",
            message=message,
            retrieval=retrieval,
            customer_profile={},
            channel="instagram_dm",
            response_language="ar",
            history_messages=[],
        )
    except Exception as exc:
        name = type(exc).__name__
        text = str(exc)
        if "401" in text or "Incorrect API key" in text or "Authentication" in name:
            pytest.skip(f"live OpenAI key rejected ({name})")
        if "429" in text or "RateLimit" in name:
            pytest.skip(f"live OpenAI rate limited ({name})")
        raise
    trace = {
        "message": message,
        "selected_source_ids": retrieval.selected_source_ids,
        "evidence_ids": [e.source_id for e in retrieval.evidence],
        "product_match_found": retrieval.product_match_found,
        "reply_preview": (answer.reply_text or "")[:500],
        "error": retrieval.error,
    }
    out = Path(str(v2_env)) / "live_multi_intent_trace.json"
    out.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    durable = Path("/tmp/linasbot_live_multi_intent_trace.json")
    durable.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    assert retrieval.error is None, trace
    blob = " ".join(e.content for e in retrieval.evidence) + " " + " ".join(retrieval.selected_source_ids)
    assert "br_beirut" in blob or "Beirut" in blob or "بيروت" in blob, trace
    assert "other" not in str(retrieval.selected_source_ids) or "appt1" in str(retrieval.selected_source_ids), trace
    assert answer.reply_text, trace
    assert "Nivea Body" not in (answer.reply_text or "")
