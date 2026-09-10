"""Stub contract: customer reply entry points do not generate until the new engine lands."""

from __future__ import annotations

import pytest

from services.customer_reply_v2.models import ENGINE_REMOVED
from services.customer_reply_v2.orchestrator import run_customer_reply_v2_comment, run_customer_reply_v2_dm


@pytest.mark.asyncio
async def test_dm_stub_returns_engine_removed() -> None:
    out = await run_customer_reply_v2_dm(tenant_id="t1", message="hello")
    assert out.stop is True
    assert out.reply is None
    assert out.reason == ENGINE_REMOVED
    assert out.metadata.get("ai_called") is False


@pytest.mark.asyncio
async def test_comment_stub_returns_engine_removed() -> None:
    out = await run_customer_reply_v2_comment(tenant_id="t1", comment_text="nice")
    assert out.stop is True
    assert out.reply is None
    assert out.reason == ENGINE_REMOVED
    assert out.metadata.get("ai_called") is False


@pytest.mark.asyncio
async def test_comment_toggle_off_still_wins() -> None:
    out = await run_customer_reply_v2_comment(
        tenant_id="t1",
        comment_text="nice",
        comments_enabled=False,
    )
    assert out.stop is True
    assert out.reply is None
    assert out.reason == "comments_toggle_off"
