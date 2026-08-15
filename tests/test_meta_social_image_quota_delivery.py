from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

import config
from services import social_messaging_processor as processor
from services.meta_messaging import MetaMessagingSettings
from tests.meta_compliance_helpers import _FakeFirestore


class _Adapter:
    def __init__(self, responses: list[dict[str, Any] | BaseException]) -> None:
        self.responses = responses
        self.messages: list[str] = []

    async def send_text_message(self, _sender_id: str, message: str) -> dict[str, Any]:
        self.messages.append(message)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def send_typing(self, _sender_id: str) -> dict[str, Any]:
        return {"success": True}

    async def fetch_participant_profile(self, _sender_id: str) -> dict[str, Any]:
        return {}

    async def close(self) -> None:
        return None


def _accepted(message_id: str) -> dict[str, Any]:
    return {"success": True, "provider": "meta", "message_id": message_id}


def _settings() -> MetaMessagingSettings:
    return MetaMessagingSettings(
        enabled=True,
        app_secret="unused",
        page_id="page-id",
        page_access_token="token",
        instagram_account_id="",
        verify_token="unused",
        graph_api_version="v24.0",
        app_id="app-id",
        app_key="app-key",
        tenant_id="tenant-a",
        binding_id="binding-a",
    )


def _event() -> dict[str, Any]:
    return {
        "channel": "facebook",
        "sender_id": "sender-a",
        "sender_name": "Customer",
        "recipient_id": "page-id",
        "account_id": "page-id",
        "message_id": "provider-inbound-a",
        "tenant_id": "tenant-a",
        "text": "Please inspect these",
        "attachments": [
            {"type": "image", "id": "image-1"},
            {"type": "file", "id": "file-1"},
            {"type": "image", "id": "image-2"},
            {"type": "audio", "id": "audio-1"},
            {"type": "image", "id": "image-3"},
        ],
    }


def _text_event() -> dict[str, Any]:
    event = _event()
    event["attachments"] = []
    return event


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeFirestore]:
    import services.ai_limits_enforcement as limits
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)

    async def restore(_user_id: str) -> dict[str, Any]:
        return {}

    async def persist_name(_user_id: str, _name: str) -> None:
        return None

    monkeypatch.setattr(processor, "get_user_state_from_firestore", restore)
    monkeypatch.setattr(processor, "save_user_name_to_firestore", persist_name)
    quota_calls: list[bool] = []

    def enforce(**kwargs: Any) -> Any:
        from services.ai_usage_limits import QuotaDecision

        quota_calls.append(bool(kwargs["consume"]))
        if getattr(db, "quota_mode", "truncated") == "allowed":
            return QuotaDecision(
                allowed=True,
                allowed_amount=int(kwargs["amount"]),
                reason="ok",
            )
        return QuotaDecision(
            allowed=True,
            allowed_amount=2,
            customer_message="quota notice",
            reason="image_truncated",
        )

    db.quota_calls = quota_calls  # type: ignore[attr-defined]
    db.quota_mode = "truncated"  # type: ignore[attr-defined]
    monkeypatch.setattr(
        limits,
        "enforce_image_analysis_quota",
        enforce,
    )
    snapshots = {
        "user_data_whatsapp": dict(config.user_data_whatsapp),
        "user_names": dict(config.user_names),
        "user_gender": dict(config.user_gender),
    }
    yield db
    for name, snapshot in snapshots.items():
        mapping = getattr(config, name)
        mapping.clear()
        mapping.update(snapshot)


def _install_adapter(monkeypatch: pytest.MonkeyPatch, adapter: _Adapter) -> None:
    monkeypatch.setattr(processor, "MetaMessagingAdapter", lambda **_kwargs: adapter)


def _install_handler(
    monkeypatch: pytest.MonkeyPatch,
    callback: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    async def handle(**kwargs: Any) -> None:
        await callback(kwargs)

    monkeypatch.setattr(processor, "handle_message", handle)


async def _send_primary(kwargs: dict[str, Any]) -> None:
    await kwargs["send_message_func"](kwargs["user_id"], "primary reply")


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


def processor_meta_document(
    db: _FakeFirestore,
    event_id: str,
    purpose: str,
) -> dict[str, Any]:
    from services.meta_outbound_attempts import _attempt_document_id

    return (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(_attempt_document_id(event_id, purpose))
        .data
    )


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
