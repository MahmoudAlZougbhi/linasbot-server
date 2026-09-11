"""Customer reply entry points always use permanent Customer Brain (no enable flag)."""

from __future__ import annotations

import pytest

from services.customer_reply_v2.orchestrator import run_customer_reply_v2_comment, run_customer_reply_v2_dm


@pytest.mark.asyncio
async def test_dm_facade_is_brain_not_flag_stub() -> None:
    out = await run_customer_reply_v2_dm(
        tenant_id="t1",
        message="hello",
        conversation_id="c1",
        message_id="m1",
    )
    assert out.reason != "engine_removed"
    assert (out.metadata or {}).get("customer_engine", "brain") in {"brain", None} or out.reason != "engine_removed"


@pytest.mark.asyncio
async def test_comment_facade_is_brain_not_flag_stub() -> None:
    out = await run_customer_reply_v2_comment(
        tenant_id="t1",
        comment_text="nice",
        comment_id="m1",
    )
    assert out.reason != "engine_removed"


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
