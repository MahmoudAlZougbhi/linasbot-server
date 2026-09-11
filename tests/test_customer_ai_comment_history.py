"""Comment history-50 and catalog comment gates. Activation flags stay off."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.customer_ai.contracts.turn import HistorySnapshot, VisibleMessage
from services.customer_reply_v2.models import ENGINE_REMOVED


@pytest.mark.asyncio
async def test_comment_ai_loads_history_and_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: dict[str, str] = {}

    async def fake_history(**kwargs):
        loaded.update({key: str(kwargs.get(key) or "") for key in ("user_id", "conversation_id")})
        return HistorySnapshot(
            messages=[
                VisibleMessage(id="old", role="user", text="earlier comment"),
            ]
        )

    monkeypatch.setattr("services.customer_ai.runtime.load_history_snapshot", fake_history)
    monkeypatch.setattr("services.customer_ai.runtime.winning_comment_mode", lambda **_k: (None, None))
    monkeypatch.setattr("services.customer_ai.runtime.evaluate_gates", lambda *_a, **_k: type("G", (), {"allow": True, "reason": "", "detail": {}})())
    monkeypatch.setattr("services.customer_ai.runtime.apply_live_control", lambda turn: turn)

    captured = {}

    async def fake_run(turn, *, message, channel):
        captured["history"] = [item.text for item in turn.history.messages]
        captured["caption"] = turn.extra.get("post_caption")
        from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult

        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="ok")],
            ),
        )

    monkeypatch.setattr("services.customer_ai.runtime.run_dm_after_gates", fake_run)
    monkeypatch.setattr(
        "services.customer_ai.comments.pipeline.apply_ai_comment_destinations",
        lambda result, _mode: result,
    )
    monkeypatch.setattr("services.customer_ai.runtime.apply_message_billing", lambda _turn, result: result)

    from services.customer_ai.runtime import run_customer_ai_comment
    from services.entitlements_service import entitlements_store

    entitlements_store.set_plan(tenant_id="c-shop", plan_id="starter", status="active", source="admin")
    outcome = await run_customer_ai_comment(
        tenant_id="c-shop",
        comment_text="price?",
        comment_id="c9",
        post_id="p1",
        conversation_id="thread-1",
        provider_sender_id="ig:user",
        parent_comment="how much",
        caption="Spring facial",
    )
    assert outcome.stop is False
    assert loaded["user_id"] == "ig:user"
    assert loaded["conversation_id"] == "thread-1"
    assert "how much" in captured["history"]
    assert captured["caption"] == "Spring facial"


@pytest.mark.asyncio
async def test_comment_gate_blocks_lite_like_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    monkeypatch.delenv("FREE_PLAN_ENFORCEMENT_ENABLED", raising=False)
    from services.entitlements_service import entitlements_store

    entitlements_store.set_plan(tenant_id="lite-c", plan_id="lite", status="active", source="admin")
    monkeypatch.setattr("services.customer_ai.runtime.winning_comment_mode", lambda **_k: (None, None))
    monkeypatch.setattr(
        "services.customer_ai.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": False, "reason": "unpublished", "detail": {}})(),
    )
    monkeypatch.setattr("services.customer_ai.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr(
        "services.customer_ai.runtime.load_history_snapshot",
        AsyncMock(return_value=HistorySnapshot()),
    )
    from services.customer_ai.runtime import run_customer_ai_comment

    blocked = await run_customer_ai_comment(tenant_id="lite-c", comment_text="hi", comments_enabled=True)
    assert blocked.reason == "COMMENT_AUTOMATION_DENIED"

    entitlements_store.set_plan(tenant_id="lite-c", plan_id="starter", status="active", source="admin")
    tiktok = await run_customer_ai_comment(
        tenant_id="lite-c",
        comment_text="hi",
        comments_enabled=True,
        channel="tiktok_comment",
    )
    assert tiktok.reason == "TIKTOK_PLAN_DENIED"
    outcome = await run_customer_ai_comment(tenant_id="lite-c", comment_text="hi", comments_enabled=True)
    assert outcome.reason == "unpublished"


@pytest.mark.asyncio
async def test_whatsapp_brain_blocks_lite(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.runtime import run_customer_ai_dm
    from services.entitlements_service import entitlements_store

    entitlements_store.set_plan(tenant_id="lite-wa", plan_id="lite", status="active", source="admin")
    blocked = await run_customer_ai_dm(tenant_id="lite-wa", message="hi", channel="whatsapp")
    assert blocked.reason == "WHATSAPP_PLAN_DENIED"

    monkeypatch.setattr(
        "services.customer_ai.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": False, "reason": "unpublished", "detail": {}})(),
    )
    monkeypatch.setattr("services.customer_ai.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr(
        "services.customer_ai.runtime.load_history_snapshot",
        AsyncMock(return_value=HistorySnapshot()),
    )
    allowed = await run_customer_ai_dm(tenant_id="lite-wa", message="hi", channel="instagram_dm")
    assert allowed.reason == "unpublished"


@pytest.mark.asyncio
async def test_followup_gate_waits_for_enforcement_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    monkeypatch.delenv("FREE_PLAN_ENFORCEMENT_ENABLED", raising=False)
    from services.customer_ai.runtime import run_customer_ai_dm
    from services.entitlements_service import entitlements_store

    entitlements_store.set_plan(tenant_id="free-fu", plan_id="free", status="active", source="admin")
    monkeypatch.setattr(
        "services.customer_ai.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": False, "reason": "unpublished", "detail": {}})(),
    )
    monkeypatch.setattr("services.customer_ai.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr(
        "services.customer_ai.runtime.load_history_snapshot",
        AsyncMock(return_value=HistorySnapshot()),
    )
    allowed = await run_customer_ai_dm(
        tenant_id="free-fu",
        message="",
        channel="instagram_dm",
        followup_goal="ask_if_still_needed",
    )
    assert allowed.reason == "unpublished"
    monkeypatch.setenv("FREE_PLAN_ENFORCEMENT_ENABLED", "true")
    blocked = await run_customer_ai_dm(
        tenant_id="free-fu",
        message="",
        channel="instagram_dm",
        followup_goal="ask_if_still_needed",
    )
    assert blocked.reason == "FOLLOWUP_DISABLED"


@pytest.mark.asyncio
async def test_omni_comment_passes_thread_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_reply_v2.models import CustomerReplyOutcome
    from services.omnichannel.generate import _generate_canonical

    captured: dict = {}

    async def fake_comment(**kwargs):
        captured.update(kwargs)
        return CustomerReplyOutcome(stop=False, reply="ok", reason="")

    monkeypatch.setattr("services.customer_reply_v2.comment_runtime.run_customer_reply_v2_comment", fake_comment)
    text, _res, err = await _generate_canonical(
        channel="instagram",
        surface="comment",
        tenant_id="t1",
        payload={
            "text": "price?",
            "comment_id": "c9",
            "post_id": "p1",
            "caption": "Spring facial",
            "parent_comment": "how much",
            "author_id": "ig:user",
        },
        conversation_key="t1:instagram:comment:c9",
    )
    assert err is None
    assert text == "ok"
    assert captured["comment_id"] == "c9"
    assert captured["post_id"] == "p1"
    assert captured["caption"] == "Spring facial"
    assert captured["parent_comment"] == "how much"
    assert captured["comment_context"]["conversation_id"]


@pytest.mark.asyncio
async def test_meta_generate_passes_comment_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_reply_v2.models import CustomerReplyOutcome
    from services.meta_comment_reply_generate import generate_comment_reply_text

    captured: dict = {}

    async def fake_comment(**kwargs):
        captured.update(kwargs)
        return CustomerReplyOutcome(
            stop=False,
            reply="ok",
            reason="",
            metadata={"outbound_messages": [{"destination": "comment", "text": "ok"}]},
        )

    monkeypatch.setattr("services.cm.constants.tenant_uses_cm_runtime", lambda _tid: True)
    monkeypatch.setattr("services.customer_reply_v2.comment_runtime.run_customer_reply_v2_comment", fake_comment)
    monkeypatch.setattr(
        "services.customer_ai.comments.destinations.destinations_from_outcome",
        lambda _out: type("P", (), {"has_any": True})(),
    )
    await generate_comment_reply_text(
        tenant_id="t1",
        comment_text="price?",
        instructions="",
        channel="instagram",
        comment_context={"comment_id": "c9", "post_id": "p1", "caption": "Spring facial", "parent_comment": "how much"},
        provider_sender_id="ig:user",
    )
    assert captured["comment_id"] == "c9"
    assert captured["post_id"] == "p1"
    assert captured["caption"] == "Spring facial"
    assert captured["parent_comment"] == "how much"
    assert captured["comment_context"]["conversation_id"].startswith("comment:t1:instagram:")


def test_comment_path_is_permanent_brain(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from services.customer_ai.runtime import run_customer_ai_comment

    outcome = asyncio.run(run_customer_ai_comment(tenant_id="x", comment_text="hi", comment_id="m1"))
    assert outcome.reason != ENGINE_REMOVED


def test_manual_comment_mode_is_zero_units() -> None:
    from services.customer_ai.billing import classify_result
    from services.customer_ai.comment_normalize import normalize_comment_mode
    from services.customer_ai.comments.pipeline import deterministic_comment_result
    from services.customer_ai.contracts.turn import CustomerTurn
    from services.membership.message_policy import message_units_for

    assert normalize_comment_mode(action="manual") == "manual"
    result = deterministic_comment_result("manual", type("D", (), {"reply_text": "", "dm_text": "", "rule_id": "r1"})())
    assert result is not None
    assert result.envelope.decision == "no_reply"
    billed = classify_result(CustomerTurn(tenant_id="shop", invocation_kind="comment"), result)
    assert billed == "no_reply"
    assert message_units_for("no_reply") == 0


def test_static_and_ai_comments_share_fallback_thread() -> None:
    from inspect import getsource

    from services.customer_ai.history_ids import comment_conversation_id
    from services.customer_ai.runtime import run_customer_ai_comment

    fallback = comment_conversation_id(
        tenant_id="shop",
        conversation_id="",
        channel="instagram_comment",
        post_id="p1",
    )
    assert fallback == "comment:shop:instagram_comment:p1"
    assert comment_conversation_id(tenant_id="shop", conversation_id="thread-1", post_id="p1") == "thread-1"
    src = getsource(run_customer_ai_comment)
    assert src.count("comment_conversation_id") >= 2


def test_comment_runtime_binds_existing_comment_or_post_id() -> None:
    from inspect import getsource

    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    src = getsource(run_customer_reply_v2_comment)
    assert "conversation_id_for_brain" in src
    assert "comment_id or post_id" in src
