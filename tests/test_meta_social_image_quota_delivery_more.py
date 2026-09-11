"""Meta social image quota consume, greeting, and fence tests."""

from __future__ import annotations

from typing import Any

import pytest

from services import social_messaging_processor as processor
from tests.meta_compliance_helpers import _FakeFirestore
from tests.meta_social_image_quota_delivery_support import (
    _accepted,
    _Adapter,
    _event,
    _install_adapter,
    _install_handler,
    _send_primary,
    _settings,
    _text_event,
    processor_meta_document,
)

pytest_plugins = ("tests.meta_social_image_quota_delivery_support",)


@pytest.mark.asyncio
async def test_crash_after_consumed_marker_retries_notice_without_reconsume(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _Adapter([_accepted("notice-after-crash"), _accepted("primary-after-crash")])
    _install_adapter(monkeypatch, adapter)
    _install_handler(monkeypatch, _send_primary)
    real_deliver = processor._deliver_image_quota_notice
    calls = 0

    async def crash_once(**kwargs: Any) -> dict[str, Any] | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("crash after durable consumed marker")
        return await real_deliver(**kwargs)

    monkeypatch.setattr(processor, "_deliver_image_quota_notice", crash_once)
    event_id = "ibe_" + "f" * 40
    with pytest.raises(RuntimeError, match="durable consumed marker"):
        await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    document = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert document["status"] == "sending"
    assert document["image_quota_phase"] == "consumed"

    result = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    assert result["ok"] is True
    assert runtime.quota_calls == [False, True]  # type: ignore[attr-defined]
    assert adapter.messages == ["quota notice", "primary reply"]
    assert processor_meta_document(runtime, event_id, "primary_reply")["status"] == "accepted"


@pytest.mark.asyncio
async def test_fully_allowed_quota_consumed_and_terminal_replays_never_reconsume(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import meta_outbound_attempts as attempts

    runtime.quota_mode = "allowed"  # type: ignore[attr-defined]
    adapter = _Adapter([_accepted("primary-after-allowed-replays")])
    _install_adapter(monkeypatch, adapter)
    real_finalize = attempts.finalize_allowed_image_quota
    finalize_calls = 0

    async def crash_before_first_finalize(**kwargs: Any) -> bool:
        nonlocal finalize_calls
        finalize_calls += 1
        if finalize_calls == 1:
            raise RuntimeError("crash after allowed quota consumed")
        return await real_finalize(**kwargs)

    monkeypatch.setattr(attempts, "finalize_allowed_image_quota", crash_before_first_finalize)
    handler_calls = 0

    async def crash_after_terminal_then_send(kwargs: dict[str, Any]) -> None:
        nonlocal handler_calls
        handler_calls += 1
        if handler_calls == 1:
            raise RuntimeError("crash after allowed quota terminal")
        await _send_primary(kwargs)

    _install_handler(monkeypatch, crash_after_terminal_then_send)
    event_id = "ibe_" + "0" * 40
    with pytest.raises(RuntimeError, match="allowed quota consumed"):
        await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    quota_document = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert quota_document["status"] == "sending"
    assert quota_document["image_quota_disposition"] == "allowed"
    assert quota_document["image_quota_allowed_amount"] == 3
    assert quota_document["image_quota_phase"] == "consumed"

    with pytest.raises(RuntimeError, match="allowed quota terminal"):
        await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    quota_document = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert quota_document["status"] == "accepted"
    assert quota_document["image_quota_phase"] == "consumed"
    assert quota_document["provider_message_id_sha256"] == ""

    result = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    assert result["ok"] is True
    assert runtime.quota_calls == [False, True]  # type: ignore[attr-defined]
    assert adapter.messages == ["primary reply"]
    assert processor_meta_document(runtime, event_id, "primary_reply")["status"] == "accepted"


@pytest.mark.asyncio
async def test_greeting_gender_ack_and_primary_use_independent_durable_purposes(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.meta_outbound_attempts import meta_outbound_send_purpose

    adapter = _Adapter(
        [
            _accepted("greeting-id"),
            _accepted("gender-id"),
            _accepted("primary-id"),
        ]
    )
    _install_adapter(monkeypatch, adapter)
    handler_calls = 0

    async def send_semantic_turn(kwargs: dict[str, Any]) -> None:
        nonlocal handler_calls
        handler_calls += 1
        if handler_calls == 1:
            with meta_outbound_send_purpose("session_greeting"):
                await kwargs["send_message_func"](kwargs["user_id"], "session greeting")
            with meta_outbound_send_purpose("gender_ack"):
                await kwargs["send_message_func"](kwargs["user_id"], "gender ack")
        await kwargs["send_message_func"](kwargs["user_id"], "primary reply")

    _install_handler(monkeypatch, send_semantic_turn)
    event_id = "ibe_" + "1" * 40

    first = await processor.process_meta_social_event(
        _text_event(),
        _settings(),
        inbound_event_id=event_id,
    )
    retry = await processor.process_meta_social_event(
        _text_event(),
        _settings(),
        inbound_event_id=event_id,
    )

    assert first["ok"] is retry["ok"] is True
    assert adapter.messages == ["session greeting", "gender ack", "primary reply"]
    for purpose in ("session_greeting", "gender_ack", "primary_reply"):
        document = processor_meta_document(runtime, event_id, purpose)
        assert document["purpose"] == purpose
        assert document["status"] == "accepted"
        assert document["image_quota_disposition"] == ""
        assert document["image_quota_allowed_amount"] == 0
        assert document["image_quota_phase"] == ""


@pytest.mark.asyncio
async def test_ambiguous_greeting_latches_primary_even_when_retry_skips_greeting(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.meta_outbound_attempts import meta_outbound_send_purpose

    adapter = _Adapter([{"success": True, "provider": "meta"}])
    _install_adapter(monkeypatch, adapter)
    handler_calls = 0

    async def greeting_then_primary(kwargs: dict[str, Any]) -> None:
        nonlocal handler_calls
        handler_calls += 1
        if handler_calls == 1:
            with meta_outbound_send_purpose("session_greeting"):
                await kwargs["send_message_func"](kwargs["user_id"], "session greeting")
        await kwargs["send_message_func"](kwargs["user_id"], "primary reply")

    _install_handler(monkeypatch, greeting_then_primary)
    event_id = "ibe_" + "2" * 40

    first = await processor.process_meta_social_event(
        _text_event(),
        _settings(),
        inbound_event_id=event_id,
    )
    retry = await processor.process_meta_social_event(
        _text_event(),
        _settings(),
        inbound_event_id=event_id,
    )

    assert first["ok"] is retry["ok"] is True
    assert adapter.messages == ["session greeting"]
    assert processor_meta_document(runtime, event_id, "session_greeting")["status"] == "needs_owner_action"
    assert processor_meta_document(runtime, event_id, "primary_reply") == {}


@pytest.mark.asyncio
async def test_quota_mismatch_reservation_is_reconciled_after_deletion_fence(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.ai_limits_enforcement as limits
    from services import meta_outbound_attempts as attempts
    from services.ai_usage_limits import QuotaDecision
    from services.meta_claim_data_deletion import build_shared_meta_claim_deletion_plan
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    calls: list[bool] = []

    def mismatch(**kwargs: Any) -> QuotaDecision:
        consume = bool(kwargs["consume"])
        calls.append(consume)
        return QuotaDecision(
            allowed=True,
            allowed_amount=1 if consume else 2,
            reason="image_truncated",
        )

    monkeypatch.setattr(limits, "enforce_image_analysis_quota", mismatch)
    adapter = _Adapter([])
    _install_adapter(monkeypatch, adapter)
    handler_calls = 0

    async def forbidden(_kwargs: dict[str, Any]) -> None:
        nonlocal handler_calls
        handler_calls += 1

    _install_handler(monkeypatch, forbidden)
    event_id = "ibe_" + "3" * 40
    binding_id = _settings().binding_id

    first = await processor.process_meta_social_event(
        _event(),
        _settings(),
        inbound_event_id=event_id,
    )
    assert first["delivery"] == "needs_owner_action"
    quota_document = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert quota_document["status"] == "sending"
    assert quota_document["image_quota_phase"] == "reserved"

    firestore_binding_deletion_fence_ref(runtime, binding_id).set({"status": "fenced"})
    retry = await processor.process_meta_social_event(
        _event(),
        _settings(),
        inbound_event_id=event_id,
    )

    assert retry["delivery"] == "needs_owner_action"
    assert calls == [False, True]
    assert adapter.messages == []
    assert handler_calls == 0
    quota_document = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert quota_document["status"] == "needs_owner_action"
    assert quota_document["image_quota_phase"] == "reserved"
    assert quota_document["safe_reason"] == "authorization_deletion_fenced"
    plan = build_shared_meta_claim_deletion_plan(runtime, {binding_id})
    assert (
        "meta_outbound_attempts",
        attempts._attempt_document_id(event_id, "image_quota_notice"),
    ) in plan.shared_documents
