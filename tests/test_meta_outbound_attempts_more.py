"""Meta outbound greeting, legacy, and identity tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import services.meta_outbound_attempts as attempts
from tests.meta_compliance_helpers import (
    _FakeFirestore,
)
from tests.meta_outbound_attempts_support import (
    _accepted,
    _document,
    _prepare_notice,
)

pytest_plugins = ("tests.meta_outbound_attempts_support",)


@pytest.mark.asyncio
async def test_ambiguous_greeting_durably_latches_gender_and_primary_retries(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "a" * 40
    binding_id = "binding-ambiguous-greeting"
    provider_calls: list[str] = []

    async def ambiguous_greeting() -> dict[str, Any]:
        provider_calls.append("session_greeting")
        return {"success": True, "provider": "meta"}

    greeting = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        purpose="session_greeting",
        send=ambiguous_greeting,
    )
    assert greeting["needs_owner_action"] is True

    for purpose in ("gender_ack", "primary_reply", "primary_reply"):
        blocked = await attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="facebook_dm",
            binding_id=binding_id,
            purpose=purpose,
            send=lambda: pytest.fail("a later semantic send must remain latched"),
        )
        assert blocked["needs_owner_action"] is True

    assert provider_calls == ["session_greeting"]
    assert _document(outbound_store, event_id, "session_greeting")["status"] == "needs_owner_action"
    assert _document(outbound_store, event_id, "gender_ack") == {}
    assert _document(outbound_store, event_id, "primary_reply") == {}


@pytest.mark.parametrize("purpose", ("session_greeting", "gender_ack"))
@pytest.mark.parametrize("legacy_status", ("accepted", "ambiguous"))
@pytest.mark.asyncio
async def test_legacy_primary_rollout_barrier_never_resends_auxiliary_role(
    outbound_store: _FakeFirestore,
    purpose: attempts.MetaOutboundPurpose,
    legacy_status: str,
) -> None:
    event_digit = "d" if purpose == "session_greeting" else "e"
    event_id = "ibe_" + event_digit * 40
    binding_id = f"binding-rollout-{purpose}-{legacy_status}"
    calls: list[str] = []

    async def legacy_send() -> dict[str, Any]:
        calls.append("legacy-primary")
        if legacy_status == "accepted":
            return {"success": True, "provider": "meta", "message_id": "legacy-provider-id"}
        return {"success": True, "provider": "meta"}

    await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        purpose="primary_reply",
        send=legacy_send,
    )
    blocked = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        purpose=purpose,
        send=lambda: pytest.fail("rollout must not duplicate an unknowable legacy send"),
    )

    assert blocked["needs_owner_action"] is True
    assert calls == ["legacy-primary"]
    assert _document(outbound_store, event_id, purpose) == {}


@pytest.mark.asyncio
async def test_terminal_predecessors_allow_distinct_later_semantic_sends(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "b" * 40
    binding_id = "binding-terminal-predecessors"
    calls: list[str] = []

    async def rejected() -> dict[str, Any]:
        calls.append("session_greeting")
        return {"success": False, "error": "http_400_invalid_recipient"}

    greeting = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        purpose="session_greeting",
        send=rejected,
    )
    assert greeting["success"] is False

    for purpose in ("gender_ack", "primary_reply"):
        result = await attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="instagram_dm",
            binding_id=binding_id,
            purpose=purpose,
            send=lambda purpose=purpose: _accepted(purpose),
        )
        assert result["success"] is True
        calls.append(purpose)

    assert calls == ["session_greeting", "gender_ack", "primary_reply"]
    assert _document(outbound_store, event_id, "session_greeting")["status"] == "definitive_failure"
    assert _document(outbound_store, event_id, "gender_ack")["status"] == "accepted"
    assert _document(outbound_store, event_id, "primary_reply")["status"] == "accepted"


@pytest.mark.asyncio
async def test_auxiliary_purpose_cannot_carry_image_quota_context(
    outbound_store: _FakeFirestore,
) -> None:
    with pytest.raises(ValueError, match="Non-quota"):
        await attempts.begin_meta_outbound_attempt(
            event_id="ibe_" + "c" * 40,
            surface="facebook_dm",
            purpose="session_greeting",
            image_quota_disposition="truncated",
            image_quota_allowed_amount=1,
        )


@pytest.mark.asyncio
async def test_legacy_primary_document_remains_suppressed_at_original_id(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "2" * 40
    legacy = _document(outbound_store, event_id)
    legacy.update(
        {
            "schema_version": 1,
            "event_id": event_id,
            "surface": "facebook_dm",
            "status": "accepted",
            "attempt_sequence": 1,
        }
    )
    reference = (
        outbound_store.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(event_id)
    )
    reference.set(legacy)

    result = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        send=lambda: pytest.fail("legacy accepted primary must not resend"),
    )

    assert result["duplicate_suppressed"] is True
    assert reference.data["schema_version"] == 1
    assert "purpose" not in reference.data


@pytest.mark.asyncio
async def test_legacy_definitive_failure_retries_in_place_and_upgrades_to_v2(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "3" * 40
    reference = (
        outbound_store.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(event_id)
    )
    reference.set(
        {
            "schema_version": 1,
            "event_id": event_id,
            "surface": "instagram_dm",
            "status": "definitive_failure",
            "attempt_sequence": 4,
            "created_at": 10.0,
            "binding_id_sha256": "",
        }
    )

    result = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        send=lambda: _accepted("legacy-retry"),
    )

    assert result["success"] is True
    assert reference.data["schema_version"] == 2
    assert reference.data["purpose"] == "primary_reply"
    assert reference.data["attempt_sequence"] == 5
    assert reference.data["created_at"] == 10.0


@pytest.mark.parametrize(
    ("field", "mutated"),
    (
        ("event_id", "ibe_" + "5" * 40),
        ("purpose", "primary_reply"),
    ),
)
@pytest.mark.asyncio
async def test_mutated_v2_notice_identity_fails_closed(
    outbound_store: _FakeFirestore,
    field: str,
    mutated: str,
) -> None:
    event_id = "ibe_" + "4" * 40
    await _prepare_notice(event_id=event_id, surface="facebook_dm")
    await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        purpose="image_quota_notice",
        image_quota_disposition="truncated",
        image_quota_allowed_amount=2,
        image_quota_notice_text="quota notice",
        send=lambda: _accepted("notice-before-mutation"),
    )
    document_id = attempts._attempt_document_id(event_id, "image_quota_notice")
    reference = (
        outbound_store.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(document_id)
    )
    reference.update({field: mutated})

    with pytest.raises(attempts.MetaOutboundAttemptStoreError, match="identity|purpose"):
        await attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="facebook_dm",
            purpose="image_quota_notice",
            image_quota_disposition="truncated",
            image_quota_allowed_amount=2,
            image_quota_notice_text="quota notice",
            send=lambda: pytest.fail("mutated authority must not send"),
        )


@pytest.mark.asyncio
async def test_unknown_purpose_is_rejected_before_provider_or_store(
    outbound_store: _FakeFirestore,
) -> None:
    with pytest.raises(ValueError, match="purpose"):
        await attempts.execute_guarded_meta_send(
            event_id="ibe_" + "6" * 40,
            surface="facebook_dm",
            purpose="marketing_notice",
            send=lambda: pytest.fail("unknown purpose must not send"),
        )


@pytest.mark.asyncio
async def test_real_meta_two_x_missing_id_shape_is_ambiguous_and_never_resent(
    outbound_store: _FakeFirestore,
) -> None:
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "success": False,
            "provider": "meta",
            "error": "meta_send_missing_message_id",
        }

    event_id = "ibe_" + "f" * 40
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

    assert first["needs_owner_action"] is True
    assert second["needs_owner_action"] is True
    assert calls == 1
    assert _document(outbound_store, event_id)["status"] == "needs_owner_action"


@pytest.mark.asyncio
async def test_concurrent_nodes_observe_one_shared_sending_intent(
    outbound_store: _FakeFirestore,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return {"success": True, "provider": "meta", "message_id": "one-only"}

    event_id = "ibe_" + "e" * 40
    first_task = asyncio.create_task(
        attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="instagram_dm",
            send=send,
        )
    )
    await entered.wait()
    second = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        send=send,
    )
    release.set()
    first = await first_task

    assert first["success"] is True
    assert second["needs_owner_action"] is True
    assert calls == 1
