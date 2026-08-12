"""Fail-closed Redis claim behavior for HA correctness-critical paths."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest


def test_redis_claims_fail_closed_explicit_env(monkeypatch):
    monkeypatch.delenv("LINAS_REQUIRE_REDIS", raising=False)
    monkeypatch.setenv("LINAS_FAIL_CLOSED_REDIS_CLAIMS", "true")

    from services.scale.redis_claims import redis_claims_fail_closed

    assert redis_claims_fail_closed() is True


def test_redis_claims_fail_closed_via_require_redis(monkeypatch):
    monkeypatch.delenv("LINAS_FAIL_CLOSED_REDIS_CLAIMS", raising=False)
    monkeypatch.setenv("LINAS_REQUIRE_REDIS", "true")

    from services.scale.redis_claims import redis_claims_fail_closed

    assert redis_claims_fail_closed() is True


@pytest.mark.asyncio
async def test_webhook_mid_fail_closed_rejects_when_redis_unavailable(monkeypatch):
    monkeypatch.setenv("LINAS_FAIL_CLOSED_REDIS_CLAIMS", "true")
    from modules.webhook_handlers_dedupe import _webhook_memory_try_claim

    with patch("services.scale.redis_claims.redis_try_claim", return_value=None):
        assert await _webhook_memory_try_claim("fc-mid-1", time.time()) is False


@pytest.mark.asyncio
async def test_webhook_bodyfp_fail_closed_rejects_when_redis_unavailable(monkeypatch):
    monkeypatch.setenv("LINAS_FAIL_CLOSED_REDIS_CLAIMS", "true")
    from modules.webhook_handlers_dedupe import _webhook_bodyfp_try_claim

    with patch("services.scale.redis_claims.redis_try_claim", return_value=None):
        assert await _webhook_bodyfp_try_claim("bodyfp_fc_test", time.time()) is False


@pytest.mark.asyncio
async def test_outbound_fail_closed_skips_when_redis_unavailable(monkeypatch):
    monkeypatch.setenv("LINAS_FAIL_CLOSED_REDIS_CLAIMS", "true")
    from services.whatsapp_adapters import outbound_text_dedupe as od

    od._cache.clear()
    od._inflight.clear()
    with patch("services.whatsapp_adapters.outbound_text_dedupe._redis_claim_outbound", return_value=None):
        assert await od.should_skip_outbound_text("+96171110099", "fail-closed text") is True


def test_job_lock_fail_closed_denies_when_redis_unavailable(monkeypatch):
    monkeypatch.setenv("LINAS_FAIL_CLOSED_REDIS_CLAIMS", "true")
    from services.durable_event_claim import try_acquire_job_lock

    with patch("services.scale.redis_claims.redis_try_claim", return_value=None):
        assert try_acquire_job_lock("job-fc-1", ttl_seconds=30) is False
