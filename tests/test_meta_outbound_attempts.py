"""Meta outbound attempt fence, acceptance, and purpose tests."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import pytest

import services.meta_outbound_attempts as attempts
from tests.meta_compliance_helpers import (
    _FakeFirestore,
    _GoogleLikeFirestore,
    _install_google_transactional_fake,
)
from tests.meta_outbound_attempts_support import (
    _document,
    _prepare_notice,
)

pytest_plugins = ('tests.meta_outbound_attempts_support',)

@pytest.mark.asyncio
async def test_production_send_requires_binding_for_deletion_fence(
    outbound_store: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(attempts.MetaOutboundAttemptStoreError, match="binding identity"):
        await attempts.execute_guarded_meta_send(
            event_id="ibe_" + "8" * 40,
            surface="facebook_dm",
            send=lambda: pytest.fail("provider must not be called"),
        )


@pytest.mark.asyncio
async def test_provider_acceptance_is_shared_and_second_node_never_resends(
    outbound_store: _FakeFirestore,
) -> None:
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": True, "provider": "meta", "message_id": "provider-private-id"}

    event_id = "ibe_" + "a" * 40
    first = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        send=send,
    )
    second = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        send=send,
    )

    assert first["success"] is True
    assert second["duplicate_suppressed"] is True
    assert calls == 1
    stored = _document(outbound_store, event_id)
    assert stored["status"] == "accepted"
    assert len(stored["provider_message_id_sha256"]) == 64
    assert "provider-private-id" not in repr(stored)


@pytest.mark.asyncio
async def test_google_transactional_primary_send_is_accepted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.utils

    db = _GoogleLikeFirestore()
    _install_google_transactional_fake(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": True, "provider": "meta", "message_id": "google-transaction-provider-id"}

    event_id = "ibe_" + "9" * 40
    first = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        send=send,
    )
    second = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        send=send,
    )

    assert first["success"] is True
    assert second["duplicate_suppressed"] is True
    assert calls == 1
    assert _document(db, event_id)["status"] == "accepted"


@pytest.mark.parametrize("purpose", ("primary_reply", "image_quota_notice"))
@pytest.mark.asyncio
async def test_binding_deletion_fence_prevents_provider_call(
    outbound_store: _FakeFirestore,
    purpose: attempts.MetaOutboundPurpose,
) -> None:
    binding_id = "binding-being-deleted"
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    fence_ref = firestore_binding_deletion_fence_ref(outbound_store, binding_id)
    fence_ref.set({"status": "fenced"})
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": True, "provider": "meta", "message_id": "must-not-send"}

    result = await attempts.execute_guarded_meta_send(
        event_id="ibe_" + "0" * 40,
        surface="facebook_dm",
        binding_id=binding_id,
        purpose=purpose,
        image_quota_disposition="blocked" if purpose == "image_quota_notice" else "",
        image_quota_allowed_amount=0,
        image_quota_notice_text="quota notice" if purpose == "image_quota_notice" else "",
        send=send,
    )

    assert result["needs_owner_action"] is True
    assert calls == 0
    assert fence_ref.get().exists is True


@pytest.mark.asyncio
async def test_fence_installed_after_reservation_still_prevents_provider_call(
    outbound_store: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding_id = "binding-fenced-after-reservation"
    real_begin = attempts.begin_meta_outbound_attempt
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    async def begin_then_fence(**kwargs: Any) -> attempts.MetaOutboundAttemptDecision:
        decision = await real_begin(**kwargs)
        firestore_binding_deletion_fence_ref(outbound_store, binding_id).set({"status": "fenced"})
        return decision

    monkeypatch.setattr(attempts, "begin_meta_outbound_attempt", begin_then_fence)
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": True, "provider": "meta", "message_id": "must-not-send"}

    event_id = "ibe_" + "7" * 40
    result = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_comment",
        binding_id=binding_id,
        send=send,
    )

    assert result["needs_owner_action"] is True
    assert calls == 0
    assert _document(outbound_store, event_id)["status"] == "needs_owner_action"


@pytest.mark.asyncio
async def test_ambiguous_provider_exception_blocks_every_automatic_retry(
    outbound_store: _FakeFirestore,
) -> None:
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise TimeoutError("provider may have accepted")

    event_id = "ibe_" + "b" * 40
    with pytest.raises(TimeoutError):
        await attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="facebook_dm",
            send=send,
        )
    retry = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        send=send,
    )
    assert retry["needs_owner_action"] is True
    assert calls == 1
    assert _document(outbound_store, event_id)["status"] == "needs_owner_action"


@pytest.mark.asyncio
async def test_lost_post_provider_record_is_ambiguous_and_not_resent(
    outbound_store: _FakeFirestore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    real_finish = attempts.finish_meta_outbound_attempt

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": True, "provider": "meta", "message_id": "accepted-before-crash"}

    async def lose_acceptance(*args: Any, **kwargs: Any) -> None:
        if kwargs.get("status") == "accepted":
            raise RuntimeError("simulated crash before shared acknowledgement")
        await real_finish(*args, **kwargs)

    event_id = "ibe_" + "c" * 40
    monkeypatch.setattr(attempts, "finish_meta_outbound_attempt", lose_acceptance)
    result = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        send=send,
    )
    assert result["needs_owner_action"] is True
    monkeypatch.setattr(attempts, "finish_meta_outbound_attempt", real_finish)

    retry = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        send=send,
    )
    assert retry["needs_owner_action"] is True
    assert calls == 1


@pytest.mark.asyncio
async def test_definitive_provider_rejection_is_the_only_automatic_retry_path(
    outbound_store: _FakeFirestore,
) -> None:
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"success": False, "error": "http_400_invalid_recipient"}
        return {"success": True, "provider": "meta", "message_id": "retry-accepted"}

    event_id = "ibe_" + "d" * 40
    first = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_comment",
        send=send,
    )
    assert first["success"] is False
    assert _document(outbound_store, event_id)["status"] == "definitive_failure"

    second = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_comment",
        send=send,
    )
    assert second["success"] is True
    assert calls == 2
    assert _document(outbound_store, event_id)["status"] == "accepted"


@pytest.mark.asyncio
async def test_returned_provider_5xx_is_ambiguous_and_never_resent(
    outbound_store: _FakeFirestore,
) -> None:
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": False, "provider": "meta", "error": "http_503"}

    event_id = "ibe_" + "9" * 40
    first = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        send=send,
    )
    second = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        send=send,
    )

    assert first["needs_owner_action"] is True
    assert second["needs_owner_action"] is True
    assert calls == 1
    assert _document(outbound_store, event_id)["status"] == "needs_owner_action"


@pytest.mark.asyncio
async def test_primary_and_notice_have_stable_independent_exactly_once_documents(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "1" * 40
    binding_id = "binding-purpose-contract"
    calls: list[str] = []

    async def send(purpose: str) -> dict[str, Any]:
        calls.append(purpose)
        return {
            "success": True,
            "provider": "meta",
            "message_id": f"provider-{purpose}",
        }

    await _prepare_notice(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
    )
    notice = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        purpose="image_quota_notice",
        image_quota_disposition="truncated",
        image_quota_allowed_amount=2,
        image_quota_notice_text="quota notice",
        send=lambda: send("notice"),
    )
    primary = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        purpose="primary_reply",
        send=lambda: send("primary"),
    )
    notice_retry = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        purpose="image_quota_notice",
        image_quota_disposition="truncated",
        image_quota_allowed_amount=2,
        image_quota_notice_text="quota notice",
        send=lambda: send("notice-retry"),
    )
    primary_retry = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        purpose="primary_reply",
        send=lambda: send("primary-retry"),
    )

    assert notice["success"] is True
    assert primary["success"] is True
    assert notice_retry["duplicate_suppressed"] is True
    assert primary_retry["duplicate_suppressed"] is True
    assert calls == ["notice", "primary"]
    expected_notice_id = (
        "moa_" + hashlib.sha256(f"meta-outbound-purpose-v1\0{event_id}\0image_quota_notice".encode()).hexdigest()
    )
    assert attempts._attempt_document_id(event_id, "primary_reply") == event_id
    assert attempts._attempt_document_id(event_id, "image_quota_notice") == expected_notice_id
    primary_doc = _document(outbound_store, event_id)
    notice_doc = _document(outbound_store, event_id, "image_quota_notice")
    for document, purpose in (
        (primary_doc, "primary_reply"),
        (notice_doc, "image_quota_notice"),
    ):
        assert document["schema_version"] == 2
        assert document["event_id"] == event_id
        assert document["purpose"] == purpose
        assert document["status"] == "accepted"
        assert len(document["binding_id_sha256"]) == 64
    assert primary_doc["binding_id_sha256"] == notice_doc["binding_id_sha256"]
    assert primary_doc["image_quota_phase"] == ""
    assert notice_doc["image_quota_disposition"] == "truncated"
    assert notice_doc["image_quota_allowed_amount"] == 2
    assert notice_doc["image_quota_phase"] == "provider"


@pytest.mark.parametrize(
    "purpose",
    ("session_greeting", "gender_ack", "image_quota_notice"),
)
def test_non_primary_purpose_document_ids_are_domain_separated_and_stable(
    purpose: attempts.MetaOutboundPurpose,
) -> None:
    event_id = "ibe_" + "2" * 40
    expected = hashlib.sha256(f"meta-outbound-purpose-v1\0{event_id}\0{purpose}".encode()).hexdigest()

    assert attempts._attempt_document_id(event_id, "primary_reply") == event_id
    assert attempts._attempt_document_id(event_id, purpose) == f"moa_{expected}"


@pytest.mark.asyncio
async def test_send_purpose_context_is_task_local_and_always_resets() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    observed: list[tuple[str, str]] = []

    async def observe(purpose: attempts.MetaOutboundPurpose) -> None:
        with attempts.meta_outbound_send_purpose(purpose):
            observed.append((purpose, attempts.current_meta_outbound_send_purpose()))
            entered.set()
            await release.wait()
            observed.append((purpose, attempts.current_meta_outbound_send_purpose()))

    task = asyncio.create_task(observe("session_greeting"))
    await entered.wait()
    assert attempts.current_meta_outbound_send_purpose() == "primary_reply"
    with attempts.meta_outbound_send_purpose("gender_ack"):
        assert attempts.current_meta_outbound_send_purpose() == "gender_ack"
    release.set()
    await task

    assert observed == [
        ("session_greeting", "session_greeting"),
        ("session_greeting", "session_greeting"),
    ]
    assert attempts.current_meta_outbound_send_purpose() == "primary_reply"
