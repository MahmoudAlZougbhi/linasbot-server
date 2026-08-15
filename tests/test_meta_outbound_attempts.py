from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import pytest

import services.meta_outbound_attempts as attempts
from tests.meta_compliance_helpers import _FakeFirestore


@pytest.fixture()
def outbound_store(monkeypatch: pytest.MonkeyPatch) -> _FakeFirestore:
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    return db


def _document(
    db: _FakeFirestore,
    event_id: str,
    purpose: attempts.MetaOutboundPurpose = "primary_reply",
) -> dict[str, Any]:
    return (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(attempts._attempt_document_id(event_id, purpose))
        .data
    )


async def _prepare_notice(
    *,
    event_id: str,
    surface: attempts.MetaEvidenceSurface | str,
    binding_id: str = "",
    disposition: attempts.ImageQuotaDisposition = "truncated",
    allowed_amount: int = 2,
    notice_text: str = "quota notice",
) -> attempts.MetaOutboundAttemptDecision:
    reservation = await attempts.reserve_image_quota_notice(
        event_id=event_id,
        surface=surface,
        binding_id=binding_id,
        disposition=disposition,
        allowed_amount=allowed_amount,
        notice_text=notice_text,
    )
    assert reservation.kind in {"quota_reserved", "nonproduction_bypass"}
    assert await attempts.confirm_image_quota_consumed(reservation) is True
    return reservation


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


@pytest.mark.parametrize("purpose", ("primary_reply", "image_quota_notice"))
@pytest.mark.asyncio
async def test_binding_deletion_fence_prevents_provider_call(
    outbound_store: _FakeFirestore,
    purpose: attempts.MetaOutboundPurpose,
) -> None:
    binding_id = "binding-being-deleted"
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    firestore_binding_deletion_fence_ref(outbound_store, binding_id).set({"status": "fenced"})
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


async def _accepted(message_id: str) -> dict[str, Any]:
    return {"success": True, "provider": "meta", "message_id": message_id}


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


@pytest.mark.asyncio
async def test_quota_phases_remain_deletion_active_until_provider_terminal(
    outbound_store: _FakeFirestore,
) -> None:
    from services.meta_claim_data_deletion import _claim_is_active

    event_id = "ibe_" + "1" * 40
    reservation = await attempts.reserve_image_quota_notice(
        event_id=event_id,
        surface="facebook_dm",
        binding_id="binding-quota-phases",
        disposition="truncated",
        allowed_amount=2,
        notice_text="quota notice",
    )
    reserved = _document(outbound_store, event_id, "image_quota_notice")
    assert reservation.kind == "quota_reserved"
    assert reserved["status"] == "sending"
    assert reserved["image_quota_phase"] == "reserved"
    assert reserved["image_quota_notice_text"] == "quota notice"
    assert len(reserved["image_quota_notice_sha256"]) == 64
    assert "quota notice" not in repr(reservation)
    assert _claim_is_active(reserved) is True

    assert await attempts.confirm_image_quota_consumed(reservation) is True
    consumed = _document(outbound_store, event_id, "image_quota_notice")
    assert consumed["status"] == "sending"
    assert consumed["image_quota_phase"] == "consumed"
    assert _claim_is_active(consumed) is True


@pytest.mark.parametrize(
    "notice_text",
    (
        "x" * 1_001,
        "unsafe\nnotice",
        "unsafe\u202enotice",
        "\ud800",
    ),
)
@pytest.mark.asyncio
async def test_quota_notice_snapshot_rejects_oversize_control_and_invalid_utf8(
    outbound_store: _FakeFirestore,
    notice_text: str,
) -> None:
    with pytest.raises(ValueError, match="notice text"):
        await attempts.reserve_image_quota_notice(
            event_id="ibe_" + "a" * 40,
            surface="facebook_dm",
            binding_id="binding-invalid-system-notice",
            disposition="truncated",
            allowed_amount=1,
            notice_text=notice_text,
        )


@pytest.mark.asyncio
async def test_quota_notice_snapshot_rejects_wrong_type_and_disposition_pair(
    outbound_store: _FakeFirestore,
) -> None:
    with pytest.raises(ValueError, match="notice authority"):
        await attempts.reserve_image_quota_notice(
            event_id="ibe_" + "b" * 40,
            surface="facebook_dm",
            binding_id="binding-invalid-system-notice-type",
            disposition="truncated",
            allowed_amount=1,
            notice_text=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="notice authority"):
        await attempts.reserve_image_quota_notice(
            event_id="ibe_" + "c" * 40,
            surface="facebook_dm",
            binding_id="binding-allowed-cannot-notice",
            disposition="allowed",
            allowed_amount=1,
            notice_text="must stay empty",
        )


@pytest.mark.asyncio
async def test_reserved_quota_retry_requires_owner_and_never_calls_provider(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "2" * 40
    await attempts.reserve_image_quota_notice(
        event_id=event_id,
        surface="instagram_dm",
        binding_id="binding-reserved-crash",
        disposition="truncated",
        allowed_amount=1,
        notice_text="quota notice",
    )

    result = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        binding_id="binding-reserved-crash",
        purpose="image_quota_notice",
        image_quota_disposition="truncated",
        image_quota_allowed_amount=1,
        image_quota_notice_text="quota notice",
        send=lambda: pytest.fail("reserved quota must not reach provider"),
    )

    assert result["needs_owner_action"] is True
    document = _document(outbound_store, event_id, "image_quota_notice")
    assert document["status"] == "sending"
    assert document["image_quota_phase"] == "reserved"


@pytest.mark.asyncio
async def test_provider_phase_crash_blocks_every_automatic_notice_retry(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "7" * 40
    binding_id = "binding-provider-phase-crash"
    await _prepare_notice(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        disposition="truncated",
        allowed_amount=1,
    )
    decision = await attempts.begin_meta_outbound_attempt(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        purpose="image_quota_notice",
        image_quota_disposition="truncated",
        image_quota_allowed_amount=1,
        image_quota_notice_text="quota notice",
    )
    assert decision.kind == "send"
    document = _document(outbound_store, event_id, "image_quota_notice")
    assert document["status"] == "sending"
    assert document["image_quota_phase"] == "provider"
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    firestore_binding_deletion_fence_ref(outbound_store, binding_id).set({"status": "fenced"})

    retry = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="instagram_dm",
        binding_id=binding_id,
        purpose="image_quota_notice",
        image_quota_disposition="truncated",
        image_quota_allowed_amount=1,
        image_quota_notice_text="quota notice",
        send=lambda: pytest.fail("ambiguous provider phase must not resend"),
    )
    assert retry["needs_owner_action"] is True
    assert document["status"] == "sending"
    assert document["image_quota_phase"] == "provider"


@pytest.mark.asyncio
async def test_fence_after_consumed_marker_settles_attempt_for_real_deletion_plan(
    outbound_store: _FakeFirestore,
) -> None:
    from services.meta_claim_data_deletion import build_shared_meta_claim_deletion_plan
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    event_id = "ibe_" + "8" * 40
    binding_id = "binding-consumed-before-fence"
    await _prepare_notice(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        disposition="truncated",
        allowed_amount=2,
    )
    document = _document(outbound_store, event_id, "image_quota_notice")
    assert document["status"] == "sending"
    assert document["image_quota_phase"] == "consumed"
    firestore_binding_deletion_fence_ref(outbound_store, binding_id).set({"status": "fenced"})
    plan = build_shared_meta_claim_deletion_plan(outbound_store, {binding_id})
    document = _document(outbound_store, event_id, "image_quota_notice")
    assert document["status"] == "needs_owner_action"
    assert document["image_quota_phase"] == "consumed"
    assert document["safe_reason"] == "authorization_deletion_fenced"
    document_id = attempts._attempt_document_id(event_id, "image_quota_notice")
    assert ("meta_outbound_attempts", document_id) in plan.shared_documents


@pytest.mark.asyncio
async def test_fence_reconciles_reserved_quota_for_real_deletion_plan(
    outbound_store: _FakeFirestore,
) -> None:
    from services.meta_claim_data_deletion import build_shared_meta_claim_deletion_plan
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    event_id = "ibe_" + "9" * 40
    binding_id = "binding-reserved-before-fence"
    reservation = await attempts.reserve_image_quota_notice(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        disposition="truncated",
        allowed_amount=1,
        notice_text="quota notice",
    )
    assert reservation.kind == "quota_reserved"
    firestore_binding_deletion_fence_ref(outbound_store, binding_id).set({"status": "fenced"})

    plan = build_shared_meta_claim_deletion_plan(outbound_store, {binding_id})
    receipt = await attempts.read_meta_outbound_attempt_receipt(
        event_id=event_id, surface="facebook_dm", binding_id=binding_id, purpose="image_quota_notice"
    )
    assert receipt is not None
    assert receipt.status == "needs_owner_action"
    assert receipt.image_quota_phase == "reserved"
    document = _document(outbound_store, event_id, "image_quota_notice")
    assert document["status"] == "needs_owner_action"
    assert document["safe_reason"] == "authorization_deletion_fenced"
    assert (
        "meta_outbound_attempts",
        attempts._attempt_document_id(event_id, "image_quota_notice"),
    ) in plan.shared_documents


@pytest.mark.asyncio
async def test_fence_after_quota_consume_records_truth_and_blocks_provider(
    outbound_store: _FakeFirestore,
) -> None:
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    event_id = "ibe_" + "3" * 40
    binding_id = "binding-fenced-after-consume"
    reservation = await attempts.reserve_image_quota_notice(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        disposition="blocked",
        allowed_amount=0,
        notice_text="quota notice",
    )
    # The caller has performed the one external quota mutation at this point.
    firestore_binding_deletion_fence_ref(outbound_store, binding_id).set({"status": "fenced"})

    assert await attempts.confirm_image_quota_consumed(reservation) is False
    document = _document(outbound_store, event_id, "image_quota_notice")
    assert document["status"] == "needs_owner_action"
    assert document["image_quota_phase"] == "consumed"
    result = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        purpose="image_quota_notice",
        image_quota_disposition="blocked",
        image_quota_allowed_amount=0,
        image_quota_notice_text="quota notice",
        send=lambda: pytest.fail("fenced consumed quota must not reach provider"),
    )
    assert result["needs_owner_action"] is True


@pytest.mark.parametrize(
    ("field", "mutated", "match"),
    (
        ("image_quota_disposition", "blocked", "quota context"),
        ("image_quota_allowed_amount", 1, "quota context"),
        ("image_quota_phase", "reserved", "quota phase"),
        ("image_quota_phase", "unknown", "quota context"),
        ("image_quota_notice_text", "mutated system notice", "quota context"),
        ("image_quota_notice_sha256", "0" * 64, "quota context"),
        ("image_quota_notice_sha256", "", "quota notice"),
        ("image_quota_notice_sha256", None, "quota notice"),
        ("image_quota_notice_sha256", False, "quota notice"),
        ("image_quota_notice_sha256", 64, "quota notice"),
        ("image_quota_notice_sha256", "A" * 64, "quota notice"),
        ("missing:image_quota_notice_sha256", None, "quota notice"),
    ),
)
@pytest.mark.asyncio
async def test_mutated_v2_notice_quota_authority_fails_closed(
    outbound_store: _FakeFirestore,
    field: str,
    mutated: object,
    match: str,
) -> None:
    event_id = "ibe_" + "4" * 40
    binding_id = "binding-mutated-quota"
    await _prepare_notice(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
    )
    await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        purpose="image_quota_notice",
        image_quota_disposition="truncated",
        image_quota_allowed_amount=2,
        image_quota_notice_text="quota notice",
        send=lambda: _accepted("accepted-before-mutation"),
    )
    document_id = attempts._attempt_document_id(event_id, "image_quota_notice")
    reference = (
        outbound_store.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(document_id)
    )
    if field.startswith("missing:"):
        reference.data.pop(field.removeprefix("missing:"))
    else:
        reference.update({field: mutated})

    with pytest.raises(attempts.MetaOutboundAttemptStoreError, match=match):
        await attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="facebook_dm",
            binding_id=binding_id,
            purpose="image_quota_notice",
            image_quota_disposition="truncated",
            image_quota_allowed_amount=2,
            image_quota_notice_text="quota notice",
            send=lambda: pytest.fail("mutated quota authority must not send"),
        )


@pytest.mark.asyncio
async def test_legacy_binding_digest_cannot_be_erased_during_v2_upgrade(
    outbound_store: _FakeFirestore,
) -> None:
    from services.durable_event_claim import meta_claim_binding_digest

    event_id = "ibe_" + "5" * 40
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
            "surface": "facebook_dm",
            "status": "definitive_failure",
            "attempt_sequence": 1,
            "binding_id_sha256": meta_claim_binding_digest("bound-legacy"),
        }
    )

    with pytest.raises(attempts.MetaOutboundAttemptStoreError, match="binding"):
        await attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="facebook_dm",
            send=lambda: pytest.fail("binding downgrade must not send"),
        )
    assert reference.data["schema_version"] == 1


@pytest.mark.asyncio
async def test_concurrent_quota_reservation_has_one_consumption_authority(
    outbound_store: _FakeFirestore,
) -> None:
    event_id = "ibe_" + "6" * 40

    async def reserve() -> attempts.MetaOutboundAttemptDecision:
        return await attempts.reserve_image_quota_notice(
            event_id=event_id,
            surface="instagram_dm",
            binding_id="binding-concurrent-quota",
            disposition="truncated",
            allowed_amount=2,
            notice_text="quota notice",
        )

    decisions = await asyncio.gather(reserve(), reserve())
    assert sorted(item.kind for item in decisions) == ["needs_owner_action", "quota_reserved"]
