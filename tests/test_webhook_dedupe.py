"""Webhook museum dedupe is gone. Live outbound text dedupe stays."""

from __future__ import annotations

import asyncio
from pathlib import Path


def test_legacy_webhook_dedupe_is_gone() -> None:
    assert not Path("modules/webhook_handlers_dedupe.py").exists()
    webhook = Path("modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert "_webhook_dedup_cache" not in webhook
    assert "_webhook_text_body_fingerprint" not in webhook
    assert "process_parsed_message" not in webhook


def test_outbound_duplicate_suppressed_after_successful_send():
    from services.integrations.whatsapp.adapters import outbound_text_dedupe as od

    async def _run():
        od._cache.clear()
        od._inflight.clear()
        assert await od.should_skip_outbound_text("+15555550101", "same text") is False
        await od.finish_outbound_text_attempt("+15555550101", "same text", True)
        assert await od.should_skip_outbound_text("+15555550101", "same text") is True

    asyncio.run(_run())


def test_outbound_same_user_different_phone_formats_share_dedupe():
    from services.integrations.whatsapp.adapters import outbound_text_dedupe as od

    async def _run():
        od._cache.clear()
        od._inflight.clear()
        assert await od.should_skip_outbound_text("+15555550101", "hi") is False
        await od.finish_outbound_text_attempt("15555550101", "hi", True)
        assert await od.should_skip_outbound_text("+15555550101", "hi") is True

    asyncio.run(_run())
