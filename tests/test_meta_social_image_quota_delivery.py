"""Meta social image quota notice and retry tests."""

from __future__ import annotations

from datetime import UTC, datetime
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
    processor_meta_document,
)

pytest_plugins = ("tests.meta_social_image_quota_delivery_support",)


@pytest.mark.asyncio
async def test_partial_images_keep_allowed_and_non_images_with_two_independent_sends(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _Adapter([_accepted("notice-id"), _accepted("primary-id")])
    _install_adapter(monkeypatch, adapter)
    _install_handler(monkeypatch, _send_primary)
    event = _event()
    event_id = "ibe_" + "a" * 40

    await processor.process_meta_social_event(
        _event(),
        _settings(),
        inbound_event_id=event_id,
    )
    await processor.process_meta_social_event(
        event,
        _settings(),
        inbound_event_id=event_id,
    )

    assert adapter.messages == ["quota notice", "primary reply"]
    assert runtime.quota_calls == [False, True]  # type: ignore[attr-defined]
    assert event["attachments"] == [
        {"type": "image", "id": "image-1"},
        {"type": "file", "id": "file-1"},
        {"type": "image", "id": "image-2"},
        {"type": "audio", "id": "audio-1"},
    ]
    primary = processor_meta_document(runtime, event_id, "primary_reply")
    notice = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert primary["status"] == notice["status"] == "accepted"
    assert primary["purpose"] == "primary_reply"
    assert notice["purpose"] == "image_quota_notice"
    assert notice["image_quota_notice_text"] == "quota notice"
    assert len(notice["image_quota_notice_sha256"]) == 64


@pytest.mark.asyncio
async def test_first_truncation_notice_preserves_exact_localized_planned_copy(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.ai_limits_enforcement as limits
    from services.ai_limits_messages import customer_photos_truncated_message
    from services.ai_usage_limits import QuotaDecision

    exact_notice = customer_photos_truncated_message(photo_limit=2, lang="ar")
    quota_calls: list[bool] = []

    def enforce(**kwargs: Any) -> QuotaDecision:
        quota_calls.append(bool(kwargs["consume"]))
        return QuotaDecision(
            allowed=True,
            allowed_amount=2,
            customer_message=exact_notice,
            reason="photos_per_message_truncated",
        )

    monkeypatch.setattr(limits, "enforce_image_analysis_quota", enforce)
    adapter = _Adapter([_accepted("localized-notice"), _accepted("localized-primary")])
    _install_adapter(monkeypatch, adapter)
    _install_handler(monkeypatch, _send_primary)
    event_id = "ibe_" + "1" * 40

    result = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)

    assert result["ok"] is True
    assert quota_calls == [False, True]
    assert adapter.messages == [exact_notice, "primary reply"]
    notice = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert notice["image_quota_notice_text"] == exact_notice


@pytest.mark.asyncio
async def test_period_reset_notice_replays_exact_snapshot_without_quota_recheck(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.ai_limits_enforcement as limits
    from services.ai_limits_messages import customer_window_limit_message
    from services.ai_usage_limits import QuotaDecision

    exact_notice = customer_window_limit_message(
        kind="image",
        period="week",
        lang="fr",
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )
    quota_calls: list[bool] = []

    def enforce(**kwargs: Any) -> QuotaDecision:
        quota_calls.append(bool(kwargs["consume"]))
        return QuotaDecision(
            allowed=False,
            allowed_amount=0,
            customer_message=exact_notice,
            reason="image_week_limit",
        )

    monkeypatch.setattr(limits, "enforce_image_analysis_quota", enforce)
    adapter = _Adapter([_accepted("period-notice-after-crash")])
    _install_adapter(monkeypatch, adapter)

    async def forbidden_handler(_kwargs: dict[str, Any]) -> None:
        pytest.fail("blocked quota must not run the primary handler")

    _install_handler(monkeypatch, forbidden_handler)
    real_deliver = processor._deliver_image_quota_notice

    async def crash_after_marker(**_kwargs: Any) -> dict[str, Any] | None:
        raise RuntimeError("crash after persisted period notice")

    monkeypatch.setattr(processor, "_deliver_image_quota_notice", crash_after_marker)
    event_id = "ibe_" + "2" * 40
    with pytest.raises(RuntimeError, match="persisted period notice"):
        await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    notice = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert notice["image_quota_phase"] == "consumed"
    assert notice["image_quota_notice_text"] == exact_notice

    def quota_must_not_be_rechecked(**_kwargs: Any) -> Any:
        pytest.fail("a consumed replay must not recheck or reconsume quota")

    monkeypatch.setattr(limits, "enforce_image_analysis_quota", quota_must_not_be_rechecked)
    monkeypatch.setattr(processor, "_deliver_image_quota_notice", real_deliver)
    result = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)

    assert result["delivery"] == "blocked_quota"
    assert quota_calls == [False, True]
    assert adapter.messages == [exact_notice]


@pytest.mark.asyncio
async def test_retry_after_notice_acceptance_sends_only_primary_reply(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _Adapter([_accepted("notice-before-crash"), _accepted("primary-after-retry")])
    _install_adapter(monkeypatch, adapter)
    calls = 0

    async def crash_then_send(kwargs: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("crash after durable notice")
        await _send_primary(kwargs)

    _install_handler(monkeypatch, crash_then_send)
    event = _event()
    event_id = "ibe_" + "b" * 40

    with pytest.raises(RuntimeError, match="durable notice"):
        await processor.process_meta_social_event(event, _settings(), inbound_event_id=event_id)
    await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)

    assert adapter.messages == ["quota notice", "primary reply"]
    assert runtime.quota_calls == [False, True]  # type: ignore[attr-defined]
    assert processor_meta_document(runtime, event_id, "image_quota_notice")["status"] == "accepted"
    assert processor_meta_document(runtime, event_id, "primary_reply")["status"] == "accepted"


@pytest.mark.asyncio
async def test_ambiguous_notice_blocks_primary_and_every_automatic_retry(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _Adapter([{"success": True, "provider": "meta"}])
    _install_adapter(monkeypatch, adapter)
    handler_calls = 0

    async def forbidden(_kwargs: dict[str, Any]) -> None:
        nonlocal handler_calls
        handler_calls += 1

    _install_handler(monkeypatch, forbidden)
    event_id = "ibe_" + "c" * 40

    first = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    retry = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)

    assert (
        first
        == retry
        == {
            "ok": False,
            "delivery": "needs_owner_action",
            "retryable": False,
            "terminal": True,
        }
    )
    assert adapter.messages == ["quota notice"]
    assert runtime.quota_calls == [False, True]  # type: ignore[attr-defined]
    assert handler_calls == 0
    assert processor_meta_document(runtime, event_id, "image_quota_notice")["status"] == "needs_owner_action"


@pytest.mark.asyncio
async def test_definitive_notice_failure_retries_before_primary_reply(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _Adapter(
        [
            {"success": False, "provider": "meta", "error": "http_400_invalid_recipient"},
            _accepted("notice-after-retry"),
            _accepted("primary-after-notice"),
        ]
    )
    _install_adapter(monkeypatch, adapter)
    handler_calls = 0

    async def send(kwargs: dict[str, Any]) -> None:
        nonlocal handler_calls
        handler_calls += 1
        await _send_primary(kwargs)

    _install_handler(monkeypatch, send)
    event_id = "ibe_" + "d" * 40

    first = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    assert first == {
        "ok": False,
        "delivery": "quota_notice_failed",
        "retryable": True,
        "terminal": False,
    }
    assert handler_calls == 0

    await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)

    assert adapter.messages == ["quota notice", "quota notice", "primary reply"]
    assert runtime.quota_calls == [False, True]  # type: ignore[attr-defined]
    assert handler_calls == 1
    assert processor_meta_document(runtime, event_id, "image_quota_notice")["attempt_sequence"] == 2
    assert processor_meta_document(runtime, event_id, "primary_reply")["status"] == "accepted"


@pytest.mark.asyncio
async def test_crash_after_quota_consume_before_marker_never_reconsumes_or_sends(
    runtime: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import meta_outbound_attempts as attempts

    adapter = _Adapter([])
    _install_adapter(monkeypatch, adapter)
    handler_calls = 0

    async def forbidden(_kwargs: dict[str, Any]) -> None:
        nonlocal handler_calls
        handler_calls += 1

    _install_handler(monkeypatch, forbidden)
    real_confirm = attempts.confirm_image_quota_consumed

    async def crash_after_consume(_decision: attempts.MetaOutboundAttemptDecision) -> bool:
        raise RuntimeError("crash after irreversible quota consume")

    monkeypatch.setattr(attempts, "confirm_image_quota_consumed", crash_after_consume)
    event_id = "ibe_" + "e" * 40
    with pytest.raises(RuntimeError, match="irreversible quota consume"):
        await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    document = processor_meta_document(runtime, event_id, "image_quota_notice")
    assert document["status"] == "sending"
    assert document["image_quota_phase"] == "reserved"

    monkeypatch.setattr(attempts, "confirm_image_quota_consumed", real_confirm)
    retry = await processor.process_meta_social_event(_event(), _settings(), inbound_event_id=event_id)
    assert retry == {
        "ok": False,
        "delivery": "needs_owner_action",
        "retryable": False,
        "terminal": True,
    }
    assert runtime.quota_calls == [False, True]  # type: ignore[attr-defined]
    assert adapter.messages == []
    assert handler_calls == 0
