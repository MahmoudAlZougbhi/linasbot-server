"""Shared fixtures and helpers for Meta outbound attempt tests."""

from __future__ import annotations

from typing import Any

import pytest

import services.meta_outbound_attempts as attempts
from tests.meta_compliance_helpers import (
    _FakeFirestore,
)


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


async def _accepted(message_id: str) -> dict[str, Any]:
    return {"success": True, "provider": "meta", "message_id": message_id}
