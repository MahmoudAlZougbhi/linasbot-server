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

from utils.utils import get_firestore_db


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


async def try_claim_ai_turn(canonical_user_id: str, inbound_mids: List[str]) -> bool:
    """
    Return True if this process should run the AI turn (claim created).
    Return False if another worker already claimed the same inbound id batch (skip GPT).
    Empty mids or no DB: return True (fail-open).
    """
    mids = sorted({str(m).strip() for m in (inbound_mids or []) if m and str(m).strip()})
    if not mids:
        return True
    db = get_firestore_db()
    if not db:
        return True
    key_basis = f"{canonical_user_id}\0" + "|".join(mids)
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
                "canonical_user_id": (canonical_user_id or "")[:256],
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
