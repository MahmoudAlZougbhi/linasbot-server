"""Meta outbound quota reservation and deletion-fence tests."""

from __future__ import annotations

import asyncio

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

pytest_plugins = ('tests.meta_outbound_attempts_support',)

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
