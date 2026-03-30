"""Unit tests: webhook dedupe keys and in-process memory claim (no server required)."""
import asyncio
import time

from services.whatsapp_adapters.montymobile_adapter import (
    MontyMobileAdapter,
    _stable_id_when_provider_omits_message_id,
)


def test_stable_generic_payload_same_id_twice():
    payload = {
        "from": {"phone": "+96171111111", "name": "T"},
        "message": {"type": "text", "text": "hello dedupe"},
    }
    a = _stable_id_when_provider_omits_message_id(payload)
    b = _stable_id_when_provider_omits_message_id(payload)
    assert a == b
    assert a.startswith("synth_")


def test_stable_generic_payload_timestamp_field_dropped():
    p1 = {"from": {"phone": "+1"}, "message": {"type": "text", "text": "x"}, "timestamp": 111}
    p2 = {"from": {"phone": "+1"}, "message": {"type": "text", "text": "x"}, "timestamp": 999}
    assert _stable_id_when_provider_omits_message_id(p1) == _stable_id_when_provider_omits_message_id(p2)


def test_stable_id_differs_when_body_differs():
    a = _stable_id_when_provider_omits_message_id(
        {"from": {"phone": "+1"}, "message": {"type": "text", "text": "a"}}
    )
    b = _stable_id_when_provider_omits_message_id(
        {"from": {"phone": "+1"}, "message": {"type": "text", "text": "b"}}
    )
    assert a != b


def test_parse_montymobile_generic_uses_stable_id_when_no_message_id():
    adapter = MontyMobileAdapter(
        api_token="t", tenant_id="tenant", api_id="aid", source_number="9611"
    )
    body = {
        "from": {"phone": "+96179999999", "name": "U"},
        "message": {"type": "text", "text": "same"},
    }
    p1 = adapter._parse_montymobile_format(body)
    p2 = adapter._parse_montymobile_format(body)
    assert p1 and p2
    assert p1["message_id"] == p2["message_id"]


def test_webhook_memory_try_claim_first_wins():
    from modules import webhook_handlers as wh

    async def _run():
        wh._webhook_dedup_cache.clear()
        wh._webhook_memory_dedup_locks.clear()
        t = time.time()
        assert await wh._webhook_memory_try_claim("unit-test-mid-1", t) is True
        assert await wh._webhook_memory_try_claim("unit-test-mid-1", t + 0.01) is False

    asyncio.run(_run())


def test_text_body_fingerprint_same_for_duplicate_payload_shape():
    from modules.webhook_handlers import _webhook_text_body_fingerprint

    p = {
        "type": "text",
        "content": {"text": "  hello  "},
        "phone_number": "+96171112222",
        "user_id": "+96171112222",
        "message_id": "a",
    }
    q = {**p, "message_id": "b"}
    assert _webhook_text_body_fingerprint(p) == _webhook_text_body_fingerprint(q)
    assert _webhook_text_body_fingerprint(p).startswith("bodyfp_")


def test_text_body_fingerprint_empty_for_non_text():
    from modules.webhook_handlers import _webhook_text_body_fingerprint

    assert (
        _webhook_text_body_fingerprint(
            {"type": "image", "content": {"image_id": "x"}, "phone_number": "+1"}
        )
        == ""
    )


def test_webhook_bodyfp_try_claim_serializes():
    from modules import webhook_handlers as wh

    async def _run():
        wh._webhook_bodyfp_cache.clear()
        wh._webhook_bodyfp_locks.clear()
        t = time.time()
        fp = "bodyfp_test123"
        assert await wh._webhook_bodyfp_try_claim(fp, t) is True
        assert await wh._webhook_bodyfp_try_claim(fp, t + 0.01) is False

    asyncio.run(_run())


def test_webhook_memory_concurrent_only_one_claim():
    from modules import webhook_handlers as wh

    async def run():
        wh._webhook_dedup_cache.clear()
        wh._webhook_memory_dedup_locks.clear()
        t = time.time()
        results = await asyncio.gather(
            wh._webhook_memory_try_claim("concurrent-mid", t),
            wh._webhook_memory_try_claim("concurrent-mid", t),
            wh._webhook_memory_try_claim("concurrent-mid", t),
        )
        assert results.count(True) == 1
        assert results.count(False) == 2

    asyncio.run(run())
