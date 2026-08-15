"""
Distributed idempotency for AI reply turns: one GPT/outbound pipeline per inbound batch.

Uses Firestore create-if-absent (same pattern as webhook_inbound_processed) so duplicate
workers or double webhook delivery does not run two full AI turns for the same inbound IDs.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

from utils.phone_utils import phone_match_key
from utils.utils import get_canonical_user_id_and_phone, get_firestore_db

_AI_TURN_CLAIM_NAMESPACE = "ai_turn_claims"
_AI_TURN_PRIMARY_COLLECTION = "ai_turn_claims"
_AI_TURN_LEGACY_COLLECTION = "ai_turn_claims_file"
_ACTIVE_AI_CLAIMS: dict[str, tuple[Any, asyncio.Task[None]]] = {}


def stable_ai_claim_identity(user_id: str, phone_number: str | None = None) -> str:
    """
    Stable key for ai_turn_claims: digits-only for phone users (same person regardless of +961 vs 961
    or room→phone resolution timing), else stripped room / raw id.
    """
    canonical, normalized = get_canonical_user_id_and_phone(user_id, phone_number)
    pk = phone_match_key(normalized or canonical or user_id)
    if pk:
        return pk
    return (canonical or user_id or "").strip()


def record_inbound_mid_for_ai_turn(user_data: dict, source_message_id: str | None) -> None:
    """Append WhatsApp inbound message id(s) for this user turn (text combine, voice, image)."""
    mid = (source_message_id or "").strip()
    if not mid:
        return
    user_data.setdefault("_batch_inbound_mids", []).append(mid)


async def try_claim_ai_turn(
    stable_identity: str,
    inbound_mids: list[str],
    inbound_body_fps: list[str] | None = None,
    *,
    binding_id: str = "",
    inbound_event_id: str = "",
) -> bool:
    """
    Return True if this process should run the AI turn (claim created).
    Return False if another worker already claimed the same inbound id batch (skip GPT).
    Empty mids and no body fingerprints: return True (fail-open).

    When a prior turn has a saved reply awaiting delivery, returns False so the caller
    can retry delivery without regenerating (see pending_delivery_for_claim).
    """
    mids = sorted({str(m).strip() for m in (inbound_mids or []) if m and str(m).strip()})
    bfps = sorted({str(b).strip() for b in (inbound_body_fps or []) if b and str(b).strip()})
    if not mids and not bfps:
        return True
    sid = (stable_identity or "").strip()
    key_basis = _claim_key_basis(sid, mids, bfps)
    key_kind = _claim_key_kind(mids, bfps)

    from services.ai_reply_turn_runtime import pending_delivery_for_claim

    if pending_delivery_for_claim(key_basis):
        print(
            f"⚠️ ai_turn_claims pending_delivery — skip regeneration (kind={key_kind} mids={len(mids)} bfps={len(bfps)})"
        )
        return False

    # Keep the historical sha256(key_basis) document id: already-deployed workers
    # create this exact document. The durable helper must use that same id for
    # create, complete, and release so a failed turn can be retried by a peer.
    doc_id = _ai_turn_claim_document_id(key_basis)
    if await _legacy_ai_turn_claim_exists(key_basis):
        print(
            f"⚠️ ai_turn_claims legacy duplicate — skipping duplicate AI turn "
            f"(doc={doc_id[:16]}… kind={key_kind} mids={len(mids)} bfps={len(bfps)})"
        )
        return False
    from services.durable_event_claim import meta_claim_binding_digest, renew_event_claim, try_claim_event_handle

    safe_event_id = str(inbound_event_id or "").strip().lower()
    if not (safe_event_id.startswith("ibe_") and len(safe_event_id) == 44):
        safe_event_id = ""

    claim_handle = await try_claim_event_handle(
        _AI_TURN_CLAIM_NAMESPACE,
        key_basis,
        ttl_seconds=120.0,
        firestore_collection=_AI_TURN_PRIMARY_COLLECTION,
        firestore_document_id=doc_id,
        firestore_claim_metadata={
            "stable_identity_sha256": hashlib.sha256(sid.encode()).hexdigest() if sid else "",
            "inbound_ids_sha256": hashlib.sha256("|".join(mids).encode()).hexdigest() if mids else "",
            "inbound_ids_count": len(mids),
            "key_kind": key_kind,
            "body_fingerprint_count": len(bfps),
            "binding_id_sha256": meta_claim_binding_digest(binding_id),
            "inbound_event_id": safe_event_id,
        },
        meta_binding_id=str(binding_id or "").strip(),
    )
    if claim_handle is None:
        print(
            f"⚠️ ai_turn_claims duplicate — skipping duplicate AI turn "
            f"(doc={doc_id[:16]}… kind={key_kind} mids={len(mids)} bfps={len(bfps)})"
        )
        return False

    owner_task = asyncio.current_task()

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(30.0)
            try:
                owned = await renew_event_claim(claim_handle, ttl_seconds=120.0)
            except BaseException:
                owned = False
            if not owned:
                if owner_task is not None and not owner_task.done():
                    owner_task.cancel()
                return

    previous = _ACTIVE_AI_CLAIMS.pop(key_basis, None)
    if previous is not None:
        previous[1].cancel()
    _ACTIVE_AI_CLAIMS[key_basis] = (claim_handle, asyncio.create_task(_heartbeat()))
    return True


def _claim_key_basis(sid: str, mids: list[str], bfps: list[str]) -> str:
    if len(mids) > 1:
        return f"{sid}\0mids\0" + "|".join(mids)
    if len(mids) == 1 and len(bfps) == 1:
        slot = int(time.time() // 15)
        return f"{sid}\0textbody\0{bfps[0]}\0slot{slot}"
    if mids:
        return f"{sid}\0mids\0" + "|".join(mids)
    slot = int(time.time() // 15)
    return f"{sid}\0textbody\0" + "|".join(bfps) + f"\0slot{slot}"


def _claim_key_kind(mids: list[str], bfps: list[str]) -> str:
    if len(mids) > 1:
        return "mids_multi"
    if len(mids) == 1 and len(bfps) == 1:
        return "textbody_slot"
    if mids:
        return "mids"
    return "textbody_only_slot"


def _ai_turn_claim_document_id(key_basis: str) -> str:
    return hashlib.sha256(key_basis.encode("utf-8")).hexdigest()


def _legacy_ai_turn_claim_document_id(key_basis: str) -> str:
    return hashlib.sha256(f"{_AI_TURN_CLAIM_NAMESPACE}\0{key_basis}".encode()).hexdigest()


async def _legacy_ai_turn_claim_exists(key_basis: str) -> bool:
    """Fail closed on an ownership marker written by the former fallback path."""

    import asyncio

    try:
        db = get_firestore_db()
    except Exception:
        db = None
    if not db:
        return False
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection(_AI_TURN_LEGACY_COLLECTION)
        .document(_legacy_ai_turn_claim_document_id(key_basis))
    )
    try:
        snapshot = await asyncio.to_thread(ref.get)
    except Exception as exc:
        print(f"⚠️ ai_turn_claims legacy marker check failed closed: {type(exc).__name__}")
        return True
    return bool(getattr(snapshot, "exists", False))


async def _sync_legacy_ai_turn_claim(key_basis: str, *, release: bool) -> None:
    """Best-effort cleanup for claims written by the former split collection path."""

    import asyncio

    try:
        db = get_firestore_db()
    except Exception:
        db = None
    if not db:
        return
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection(_AI_TURN_LEGACY_COLLECTION)
        .document(_legacy_ai_turn_claim_document_id(key_basis))
    )
    try:
        if release:
            await asyncio.to_thread(ref.delete)
            return
        snapshot = await asyncio.to_thread(ref.get)
        if getattr(snapshot, "exists", False):
            from google.cloud import firestore

            await asyncio.to_thread(
                ref.set,
                {"status": "completed", "completed_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
    except Exception as exc:
        # The primary lifecycle has already completed. A stale compatibility
        # marker is safe (it only blocks legacy workers), so do not undo success.
        print(f"⚠️ ai_turn_claims legacy marker sync failed: {type(exc).__name__}")


async def complete_ai_turn_claim(key_basis: str) -> None:
    """Mark AI turn claim completed after successful delivery."""
    from services.durable_event_claim import complete_event_claim

    active = _ACTIVE_AI_CLAIMS.pop(key_basis, None)
    if active is not None:
        claim_handle, heartbeat = active
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        await complete_event_claim(
            _AI_TURN_CLAIM_NAMESPACE,
            key_basis,
            firestore_collection=_AI_TURN_PRIMARY_COLLECTION,
            firestore_document_id=_ai_turn_claim_document_id(key_basis),
            claim_handle=claim_handle,
        )
    await _sync_legacy_ai_turn_claim(key_basis, release=False)


async def release_ai_turn_claim(key_basis: str) -> None:
    """Release claim on AI/delivery failure so reconcile can retry."""
    from services.durable_event_claim import release_event_claim

    active = _ACTIVE_AI_CLAIMS.pop(key_basis, None)
    if active is not None:
        claim_handle, heartbeat = active
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        await release_event_claim(
            _AI_TURN_CLAIM_NAMESPACE,
            key_basis,
            firestore_collection=_AI_TURN_PRIMARY_COLLECTION,
            firestore_document_id=_ai_turn_claim_document_id(key_basis),
            claim_handle=claim_handle,
        )
    await _sync_legacy_ai_turn_claim(key_basis, release=True)
