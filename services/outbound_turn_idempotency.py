"""
Distributed idempotency for AI reply turns: one GPT/outbound pipeline per inbound batch.

Uses Firestore create-if-absent (same pattern as webhook_inbound_processed) so duplicate
workers or double webhook delivery does not run two full AI turns for the same inbound IDs.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

from google.cloud import firestore

from utils.phone_utils import phone_match_key
from utils.utils import get_canonical_user_id_and_phone, get_firestore_db


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


def _is_already_exists(exc: BaseException) -> bool:
    if type(exc).__name__ in ("AlreadyExists", "Conflict"):
        return True
    code = getattr(exc, "code", None)
    if code in (409, "ALREADY_EXISTS"):
        return True
    s = str(exc).lower()
    return "already exists" in s or "already_exists" in s


async def try_claim_ai_turn(
    stable_identity: str,
    inbound_mids: list[str],
    inbound_body_fps: list[str] | None = None,
) -> bool:
    """
    Return True if this process should run the AI turn (claim created).
    Return False if another worker already claimed the same inbound id batch (skip GPT).
    Empty mids and no body fingerprints: return True (fail-open).

    When there is exactly one inbound message id but the provider also sent a stable
    _webhook_text_body_fingerprint, we key by (identity + body_fp + 15s time slot) so two
    parallel webhooks with *different* wamids for the same user text still share one claim.

    Multiple combined user messages (len(mids) > 1) still key only on sorted message ids.
    """
    mids = sorted({str(m).strip() for m in (inbound_mids or []) if m and str(m).strip()})
    bfps = sorted({str(b).strip() for b in (inbound_body_fps or []) if b and str(b).strip()})
    if not mids and not bfps:
        return True
    sid = (stable_identity or "").strip()

    if len(mids) > 1:
        key_basis = f"{sid}\0mids\0" + "|".join(mids)
        key_kind = "mids_multi"
    elif len(mids) == 1 and len(bfps) == 1:
        slot = int(time.time() // 15)
        key_basis = f"{sid}\0textbody\0{bfps[0]}\0slot{slot}"
        key_kind = "textbody_slot"
    elif mids:
        key_basis = f"{sid}\0mids\0" + "|".join(mids)
        key_kind = "mids"
    else:
        slot = int(time.time() // 15)
        key_basis = f"{sid}\0textbody\0" + "|".join(bfps) + f"\0slot{slot}"
        key_kind = "textbody_only_slot"

    doc_id = hashlib.sha256(key_basis.encode("utf-8")).hexdigest()
    db = get_firestore_db()
    if db:
        ref = db.collection("artifacts").document("linas-ai-bot-backend").collection("ai_turn_claims").document(doc_id)

        def _create() -> None:
            ref.create(
                {
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "stable_identity": (sid or "")[:256],
                    "inbound_ids_preview": "|".join(mids)[:500] if mids else "",
                    "key_kind": key_kind,
                    "body_fp_prefix": (bfps[0][:48] + "…") if bfps else "",
                }
            )

        try:
            await asyncio.to_thread(_create)
            return True
        except Exception as e:
            if _is_already_exists(e):
                print(
                    f"⚠️ ai_turn_claims duplicate — skipping duplicate AI turn "
                    f"(doc={doc_id[:16]}… kind={key_kind} mids={len(mids)} bfps={len(bfps)})"
                )
                return False
            print(f"⚠️ ai_turn_claims Firestore create failed; durable file fallback: {e}")

    # Fail-closed durable file claim when Firestore is unavailable or errored.
    from services.durable_event_claim import try_claim_event

    claimed = await try_claim_event(
        "ai_turn_claims",
        key_basis,
        ttl_seconds=120.0,
        firestore_collection="ai_turn_claims_file",
    )
    if not claimed:
        print(
            f"⚠️ ai_turn_claims file duplicate — skipping duplicate AI turn "
            f"(kind={key_kind} mids={len(mids)} bfps={len(bfps)})"
        )
    return claimed
