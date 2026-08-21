"""Google-SDK-like Firestore regressions for Meta outbound quota helpers."""

from __future__ import annotations

import pytest

import services.meta_outbound_attempts as attempts
from tests.meta_compliance_helpers import (
    _GoogleLikeFirestore,
    _install_google_transactional_fake,
)


@pytest.mark.asyncio
async def test_google_transactional_quota_reserve_and_fence_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.utils
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    db = _GoogleLikeFirestore()
    _install_google_transactional_fake(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)

    raw = db.transaction()
    event_id = "ibe_" + "7" * 40
    binding_id = "binding-google-quota"
    with pytest.raises(ValueError, match="Transaction not in progress"):
        db.collection("artifacts").document("linas-ai-bot-backend").collection("meta_outbound_attempts").document(
            attempts._attempt_document_id(event_id, "image_quota_notice")
        ).get(transaction=raw)

    reservation = await attempts.reserve_image_quota_notice(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        disposition="truncated",
        allowed_amount=1,
        notice_text="quota notice",
    )
    assert reservation.kind == "quota_reserved"
    receipt = await attempts.read_meta_outbound_attempt_receipt(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
        purpose="image_quota_notice",
    )
    assert receipt is not None
    assert receipt.status == "sending"
    assert receipt.image_quota_phase == "reserved"

    firestore_binding_deletion_fence_ref(db, binding_id).set({"status": "fenced"})
    reconciled = await attempts.reconcile_image_quota_receipt(
        event_id=event_id,
        surface="facebook_dm",
        binding_id=binding_id,
    )
    assert reconciled is not None
    assert reconciled.status == "needs_owner_action"
    assert reconciled.image_quota_phase == "reserved"
    stored = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(attempts._attempt_document_id(event_id, "image_quota_notice"))
        .data
    )
    assert stored["status"] == "needs_owner_action"
    assert stored["safe_reason"] == "authorization_deletion_fenced"
