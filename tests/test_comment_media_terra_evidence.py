"""AI comment modes attach post image/video evidence Terra already reads."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.brain.contracts.reply import FinalReplyEnvelope, TurnResult
from services.brain.gates import GateDecision
from services.brain.runtime import run_customer_ai_comment


@pytest.mark.asyncio
async def test_ai_comment_image_post_puts_visual_in_turn_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_analyze(**kwargs: object) -> dict[str, object]:
        captured["analyze"] = dict(kwargs)
        return {
            "post_transcript": "",
            "post_visual_description": "white cream jar on a marble table",
            "post_media_duration_s": 0.0,
            "post_media_truncated": False,
            "post_media_analysis_status": "ok",
            "post_media_cache_hit": False,
            "post_media_frame_count": 0,
        }

    async def fake_dm(turn, *, message: str, channel: str):
        captured["extra"] = dict(turn.extra or {})
        captured["message"] = message
        captured["channel"] = channel
        return TurnResult(stop_reason="ok", envelope=FinalReplyEnvelope(decision="no_reply"), extra=dict(turn.extra))

    monkeypatch.setattr("services.brain.tenant_gate.evaluate_brain_tenant_gate", lambda _t: {"allow": True})
    monkeypatch.setattr("services.brain.runtime.assert_channel_plan_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.billing.membership.comment_gate.assert_comment_automation_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates", lambda *_a, **_k: GateDecision(allow=True, reason="ok")
    )
    monkeypatch.setattr(
        "services.brain.runtime.winning_comment_mode",
        lambda **_k: ("ai_comment", SimpleNamespace(rule_id="r1", policy_text="")),
    )
    monkeypatch.setattr(
        "services.billing.membership.generative_gate.generative_block_reason",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr("services.brain.media.comment_attach.analysis_fields_for_comment", fake_analyze)
    monkeypatch.setattr("services.brain.runtime.run_dm_after_gates", fake_dm)
    monkeypatch.setattr("services.brain.runtime.record_turn_history", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr("services.brain.runtime.remember_turn", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.runtime.apply_message_billing", lambda _turn, result: result)
    monkeypatch.setattr("services.brain.runtime.load_history_snapshot", _empty_history)

    outcome = await run_customer_ai_comment(
        tenant_id="shop",
        comment_text="what is this?",
        comments_enabled=True,
        comment_id="c-img",
        post_id="p-img",
        channel="instagram_comment",
        caption="New cream",
        media_type="IMAGE",
        image_urls=["https://cdn.example/cream.jpg"],
        provider_sender_id="ig:alice",
    )
    extra = captured["extra"]
    assert extra.get("post_visual_description") == "white cream jar on a marble table"
    assert extra.get("post_media_analysis_status") == "ok"
    assert captured["analyze"].get("post_id") == "p-img"
    assert outcome.metadata.get("post_visual_description") == "white cream jar on a marble table"


@pytest.mark.asyncio
async def test_ai_comment_video_post_puts_frames_in_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_analyze(**kwargs: object) -> dict[str, object]:
        captured["analyze"] = dict(kwargs)
        return {
            "post_transcript": "welcome to the clinic",
            "post_visual_description": "laser machine on screen",
            "post_media_duration_s": 12.0,
            "post_media_truncated": False,
            "post_media_analysis_status": "ok",
            "post_media_cache_hit": False,
            "post_media_frame_count": 6,
        }

    async def fake_dm(turn, *, message: str, channel: str):
        captured["extra"] = dict(turn.extra or {})
        return TurnResult(stop_reason="ok", envelope=FinalReplyEnvelope(decision="no_reply"), extra=dict(turn.extra))

    monkeypatch.setattr("services.brain.tenant_gate.evaluate_brain_tenant_gate", lambda _t: {"allow": True})
    monkeypatch.setattr("services.brain.runtime.assert_channel_plan_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.billing.membership.comment_gate.assert_comment_automation_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates", lambda *_a, **_k: GateDecision(allow=True, reason="ok")
    )
    monkeypatch.setattr(
        "services.brain.runtime.winning_comment_mode",
        lambda **_k: ("ai_both", SimpleNamespace(rule_id="r2", policy_text="")),
    )
    monkeypatch.setattr(
        "services.billing.membership.generative_gate.generative_block_reason",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr("services.brain.media.comment_attach.analysis_fields_for_comment", fake_analyze)
    monkeypatch.setattr("services.brain.runtime.run_dm_after_gates", fake_dm)
    monkeypatch.setattr("services.brain.runtime.record_turn_history", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr("services.brain.runtime.remember_turn", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.runtime.apply_message_billing", lambda _turn, result: result)
    monkeypatch.setattr("services.brain.runtime.load_history_snapshot", _empty_history)

    await run_customer_ai_comment(
        tenant_id="shop",
        comment_text="what treatment is this?",
        comments_enabled=True,
        comment_id="c-vid",
        post_id="p-vid",
        channel="tiktok_comment",
        caption="laser reel",
        media_type="video",
        comment_context={
            "video_url": "https://cdn.example/reel.mp4",
            "video_transcript": "welcome to the clinic",
            "visual_description": "laser machine on screen",
            "frame_count": 6,
        },
        provider_sender_id="tt:bob",
    )
    extra = captured["extra"]
    assert extra.get("post_transcript") == "welcome to the clinic"
    assert extra.get("post_visual_description") == "laser machine on screen"
    assert extra.get("post_media_frame_count") == 6
    assert captured["analyze"].get("video_url") == "https://cdn.example/reel.mp4"


@pytest.mark.asyncio
async def test_static_comment_skips_heavy_media_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"analyze": 0}

    async def fake_analyze(**_k: object) -> dict[str, object]:
        called["analyze"] += 1
        return {}

    monkeypatch.setattr("services.brain.tenant_gate.evaluate_brain_tenant_gate", lambda _t: {"allow": True})
    monkeypatch.setattr("services.brain.runtime.assert_channel_plan_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.billing.membership.comment_gate.assert_comment_automation_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates", lambda *_a, **_k: GateDecision(allow=True, reason="ok")
    )
    monkeypatch.setattr(
        "services.brain.runtime.winning_comment_mode",
        lambda **_k: (
            "static_comment",
            SimpleNamespace(reply_text="Thanks!", dm_text="", rule_id="static-1", policy_text=""),
        ),
    )
    monkeypatch.setattr("services.brain.media.comment_attach.analysis_fields_for_comment", fake_analyze)
    monkeypatch.setattr("services.brain.runtime.record_turn_history", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr("services.brain.runtime.apply_message_billing", lambda _turn, result: result)

    outcome = await run_customer_ai_comment(
        tenant_id="shop",
        comment_text="nice",
        comments_enabled=True,
        comment_id="c-static",
        post_id="p-static",
        channel="instagram_comment",
        media_type="IMAGE",
        image_urls=["https://cdn.example/post.jpg"],
    )
    assert called["analyze"] == 0
    assert outcome.reply == "Thanks!"


async def _empty_history(**_k):
    from services.brain.contracts.turn import HistorySnapshot

    return HistorySnapshot()
