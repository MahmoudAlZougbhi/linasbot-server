"""Unit tests: webhook dedupe keys and in-process memory claim (no server required)."""

import asyncio
import time


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

    assert _webhook_text_body_fingerprint({"type": "image", "content": {"image_id": "x"}, "phone_number": "+1"}) == ""


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


def test_outbound_duplicate_suppressed_after_successful_send():
    import asyncio

    from services.whatsapp_adapters import outbound_text_dedupe as od

    async def _run():
        od._cache.clear()
        od._inflight.clear()
        assert await od.should_skip_outbound_text("+96171110001", "نفس النص") is False
        await od.finish_outbound_text_attempt("+96171110001", "نفس النص", True)
        assert await od.should_skip_outbound_text("+96171110001", "نفس النص") is True

    asyncio.run(_run())


def test_outbound_same_user_different_phone_formats_share_dedupe():
    import asyncio

    from services.whatsapp_adapters import outbound_text_dedupe as od

    async def _run():
        od._cache.clear()
        od._inflight.clear()
        assert await od.should_skip_outbound_text("+96171110001", "hi") is False
        await od.finish_outbound_text_attempt("96171110001", "hi", True)
        assert await od.should_skip_outbound_text("+96171110001", "hi") is True

    asyncio.run(_run())
