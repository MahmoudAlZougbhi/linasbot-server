"""
Distributed idempotency for AI reply turns: one GPT/outbound pipeline per inbound batch.

Uses Firestore create-if-absent (same pattern as webhook_inbound_processed) so duplicate
workers or double webhook delivery does not run two full AI turns for the same inbound IDs.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import List, Optional

from google.cloud import firestore

from utils.phone_utils import phone_match_key
from utils.utils import get_canonical_user_id_and_phone, get_firestore_db


def stable_ai_claim_identity(user_id: str, phone_number: Optional[str] = None) -> str:
    """
    Stable key for ai_turn_claims: digits-only for phone users (same person regardless of +961 vs 961
    or room→phone resolution timing), else stripped room / raw id.
    """
    canonical, normalized = get_canonical_user_id_and_phone(user_id, phone_number)
    pk = phone_match_key(normalized or canonical or user_id)
    if pk:
        return pk
    return (canonical or user_id or "").strip()


def record_inbound_mid_for_ai_turn(user_data: dict, source_message_id: Optional[str]) -> None:
    """Append WhatsApp inbound message id(s) for this user turn (text combine, voice, image)."""
    mid = (source_message_id or "").strip()
    if not mid:
        return
    user_data.setdefault("_batch_inbound_mids", []).append(mid)


def _is_already_exists(exc: BaseException) -> bool:
    if type(exc).__name__ in ("AlreadyExists", "Conflict"):
        return True
    code = getattr(exc, "code", None)
    if code in (409, "ALREADY_EXISTS"):
        return True
    s = str(exc).lower()
    return "already exists" in s or "already_exists" in s


async def try_claim_ai_turn(stable_identity: str, inbound_mids: List[str]) -> bool:
    """
    Return True if this process should run the AI turn (claim created).
    Return False if another worker already claimed the same inbound id batch (skip GPT).
    Empty mids or no DB: return True (fail-open).

    Pass stable_identity from stable_ai_claim_identity(user_id, phone) so workers agree on the key.
    """
    mids = sorted({str(m).strip() for m in (inbound_mids or []) if m and str(m).strip()})
    if not mids:
        return True
    db = get_firestore_db()
    if not db:
        return True
    sid = (stable_identity or "").strip()
    key_basis = f"{sid}\0" + "|".join(mids)
    doc_id = hashlib.sha256(key_basis.encode("utf-8")).hexdigest()
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("ai_turn_claims")
        .document(doc_id)
    )

    def _create():
        ref.create(
            {
                "created_at": firestore.SERVER_TIMESTAMP,
                "stable_identity": (sid or "")[:256],
                "inbound_ids_preview": "|".join(mids)[:500],
            }
        )

    try:
        await asyncio.to_thread(_create)
        return True
    except Exception as e:
        if _is_already_exists(e):
            print(
                f"⚠️ ai_turn_claims duplicate — skipping duplicate AI turn "
                f"(doc={doc_id[:16]}… mids={len(mids)})"
            )
            return False
        print(f"⚠️ ai_turn_claims create failed (fail-open, running AI): {e}")
        return True
