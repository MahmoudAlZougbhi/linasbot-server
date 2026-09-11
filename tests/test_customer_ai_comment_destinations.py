"""Brain comment destinations must not post a private DM as a public reply."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.customer_ai.comments.destinations import (
    CommentDestinations,
    coerce_comment_destinations,
    destinations_from_outcome,
    public_text_for_channel,
)
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.runtime import _outcome


def test_mixed_outcome_keeps_public_and_private_separate() -> None:
    result = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[
                OutboundMessage(destination="dm", text="Private price 99"),
                OutboundMessage(
                    destination="comment",
                    text="Sent you a DM.",
                    depends_on=["private"],
                ),
            ],
        ),
    )
    outcome = _outcome(result, comment_surface=True)
    assert outcome.reply == "Sent you a DM."
    plan = destinations_from_outcome(outcome)
    assert plan.public_text == "Sent you a DM."
    assert plan.private_text == "Private price 99"
    assert plan.public_depends_on_private is True
    assert public_text_for_channel(plan, private_send_possible=False) == ""


def test_string_generate_result_stays_public_only() -> None:
    plan = coerce_comment_destinations("Thanks for your question.")
    assert plan is not None
    assert plan.public_text == "Thanks for your question."
    assert plan.private_text == ""
    assert plan.has_any is True


@pytest.mark.asyncio
async def test_simulated_send_posts_private_before_public_claim() -> None:
    from services.meta_comment_brain_send import send_comment_destinations

    binding = SimpleNamespace(
        tenant_id="t1",
        channel="facebook",
        binding_id="bind-1",
        asset_id="page-1",
        app_key="A",
    )
    captured: list[dict] = []
    result = await send_comment_destinations(
        plan=CommentDestinations(
            public_text="Sent you a DM.",
            private_text="Private details",
            comment_mode="ai_both",
            public_depends_on_private=True,
        ),
        binding=binding,
        comment_id="c1",
        simulation=True,
        capture_send=captured,
        inbound_event_id=None,
        token="tok",
        graph_api_version="v24.0",
        client=None,
    )
    assert result.status == "simulated_both"
    assert [item["delivery"] for item in captured] == ["private_reply", "public_reply"]
    assert captured[0]["message"] == "Private details"
    assert captured[1]["message"] == "Sent you a DM."


@pytest.mark.asyncio
async def test_ai_both_skips_public_when_already_replied() -> None:
    from services.meta_comment_brain_send import send_comment_destinations

    binding = SimpleNamespace(
        tenant_id="t1",
        channel="facebook",
        binding_id="bind-1",
        asset_id="page-1",
        app_key="A",
    )
    captured: list[dict] = []
    result = await send_comment_destinations(
        plan=CommentDestinations(
            public_text="Sent you a DM.",
            private_text="Private details",
            comment_mode="ai_both",
            public_depends_on_private=True,
        ),
        binding=binding,
        comment_id="c1",
        simulation=True,
        capture_send=captured,
        inbound_event_id=None,
        token="tok",
        graph_api_version="v24.0",
        client=None,
        skip_public=True,
    )
    assert result.status == "simulated"
    assert [item["delivery"] for item in captured] == ["private_reply"]


@pytest.mark.asyncio
async def test_public_claim_skipped_when_private_send_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.meta_comment_brain_send import send_comment_destinations

    async def fail_dm(**_k):
        return {"ok": False, "hard_fail": True, "status": "failed", "reason": "private_reply:denied"}

    async def public_send(**_k):
        raise AssertionError("public claim must not send after private failure")

    monkeypatch.setattr("services.meta_comment_brain_send._guarded_private_dm", fail_dm)
    monkeypatch.setattr("services.meta_comment_brain_send._guarded_public_reply", public_send)
    binding = SimpleNamespace(
        tenant_id="t1",
        channel="facebook",
        binding_id="bind-1",
        asset_id="page-1",
        app_key="A",
    )
    result = await send_comment_destinations(
        plan=CommentDestinations(
            public_text="Sent you a DM.",
            private_text="Private details",
            comment_mode="ai_both",
            public_depends_on_private=True,
        ),
        binding=binding,
        comment_id="c1",
        simulation=False,
        capture_send=None,
        inbound_event_id=None,
        token="tok",
        graph_api_version="v24.0",
        client=object(),
    )
    assert result.status == "failed"
    assert "private_reply" in result.reason


@pytest.mark.asyncio
async def test_empty_destinations_release_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.meta_comment_brain_send import send_comment_destinations

    settled: list[dict] = []
    monkeypatch.setattr(
        "services.meta_comment_brain_send._settle_comment_send",
        lambda **k: settled.append(k),
    )
    binding = SimpleNamespace(tenant_id="t1", channel="facebook", binding_id="b", asset_id="p", app_key="A")
    result = await send_comment_destinations(
        plan=CommentDestinations(),
        binding=binding,
        comment_id="c-empty",
        simulation=False,
        capture_send=None,
        inbound_event_id="evt-1",
        token="tok",
        graph_api_version="v24.0",
        client=object(),
    )
    assert result.status == "skipped"
    assert settled == [
        {
            "binding": binding,
            "comment_id": "c-empty",
            "inbound_event_id": "evt-1",
            "reply_id": "",
            "accepted": False,
        }
    ]
