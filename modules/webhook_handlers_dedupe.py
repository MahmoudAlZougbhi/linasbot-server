"""Webhook inbound dedupe, delayed-processing wait, and text fingerprint (LOC split)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from google.cloud import firestore

from services.whatsapp_adapters.outbound_text_dedupe import normalize_text_body_for_dedupe
from utils.phone_utils import phone_match_key
from utils.utils import get_firestore_db

# Webhook deduplication cache: {message_id: timestamp}
# Prevents processing the same webhook multiple times within a time window
_webhook_dedup_cache: dict[str, Any] = {}
# Per-message_id lock so check+record is atomic (avoids two concurrent requests both passing memory dedupe when Firestore is down / fail-open).
_webhook_memory_dedup_locks: dict[str, asyncio.Lock] = {}
WEBHOOK_DEDUP_WINDOW_SECONDS = (
    60  # Consider duplicate if received within 60 seconds (Qiscus can send duplicates up to 15+ seconds apart)
)

# Some providers deliver the same user text twice with different message ids; message_id dedupe misses that.
# MontyMobile / retries can arrive >5s apart — keep a generous window so we do not run GPT twice for one user tap.
WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS = 45.0
WEBHOOK_TEXT_BODYFP_MAX_CHARS = 4000
_webhook_bodyfp_cache: dict[str, float] = {}
_webhook_bodyfp_locks: dict[str, asyncio.Lock] = {}


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text", "") or "")
    return str(content or "")



def _webhook_text_body_fingerprint(parsed_message: dict[str, Any]) -> str:
    """
    Stable key for short-window text dedupe (same logical sender + same body).
    Aligns phone with phone_match_key (+961 vs 961, room→phone) and text with outbound NFKC/ZW normalization
    so parallel workers and duplicate provider deliveries collapse to one fingerprint.
    """
    if (parsed_message.get("type") or "") != "text":
        return ""
    text = _extract_text_from_content(parsed_message.get("content"))
    text = normalize_text_body_for_dedupe(text)
    if not text:
        return ""
    text = text[:WEBHOOK_TEXT_BODYFP_MAX_CHARS]
    raw_sender = (parsed_message.get("phone_number") or parsed_message.get("user_id") or "").strip()
    sender_key = phone_match_key(raw_sender)
    if not sender_key:
        # Room / non-E.164 ids: still dedupe duplicate webhooks for the same provider id
        sid = (parsed_message.get("user_id") or raw_sender or "").strip()
        if not sid:
            return ""
        sender_key = "id_" + hashlib.sha256(sid.encode("utf-8", errors="replace")).hexdigest()[:24]
    basis = f"{sender_key}|{text}"
    return "bodyfp_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]


async def _webhook_bodyfp_try_claim(fp: str, current_time: float) -> bool:
    if not fp:
        return True
    expired = [k for k, ts in _webhook_bodyfp_cache.items() if current_time - ts > WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS]
    for k in expired:
        _webhook_bodyfp_cache.pop(k, None)
        _webhook_bodyfp_locks.pop(k, None)

    lock = _webhook_bodyfp_locks.setdefault(fp, asyncio.Lock())
    async with lock:
        if fp in _webhook_bodyfp_cache:
            return False
        _webhook_bodyfp_cache[fp] = current_time
        return True


async def _webhook_memory_try_claim(message_id: str, current_time: float) -> bool:
    """
    Return True if this request should proceed, False if duplicate within WEBHOOK_DEDUP_WINDOW_SECONDS.
    Atomic per message_id for same-process concurrent webhooks.
    """
    mid = (message_id or "").strip()
    if not mid:
        return True

    expired_keys = [k for k, v in _webhook_dedup_cache.items() if current_time - v > WEBHOOK_DEDUP_WINDOW_SECONDS]
    for k in expired_keys:
        _webhook_dedup_cache.pop(k, None)
        _webhook_memory_dedup_locks.pop(k, None)

    lock = _webhook_memory_dedup_locks.setdefault(mid, asyncio.Lock())
    async with lock:
        if mid in _webhook_dedup_cache:
            return False
        _webhook_dedup_cache[mid] = current_time
        return True


def _synthetic_inbound_id_from_wa_message(msg: dict) -> str:
    """When WhatsApp message.id is missing, dedupe keys must not collapse to one value."""
    basis = json.dumps(msg, sort_keys=True, default=str)
    return "synth_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]


async def _webhook_firestore_try_acquire(message_id: str) -> bool:
    """
    Return True if we should process this inbound WhatsApp message_id.
    Return False if another worker (or earlier request) already registered it (duplicate webhook).
    """
    mid = (message_id or "").strip()
    if not mid:
        return True
    db = get_firestore_db()
    if not db:
        from services.durable_event_claim import try_claim_event

        return await try_claim_event(
            "webhook_inbound_processed",
            mid,
            ttl_seconds=300.0,
            firestore_collection="webhook_inbound_processed_file",
        )
    doc_id = hashlib.sha256(mid.encode("utf-8")).hexdigest()
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("webhook_inbound_processed")
        .document(doc_id)
    )

    def _create() -> None:
        ref.create(
            {
                "created_at": firestore.SERVER_TIMESTAMP,
                "message_id_prefix": mid[:200],
            }
        )

    def _is_dup(exc: BaseException) -> bool:
        if type(exc).__name__ in ("AlreadyExists", "Conflict"):
            return True
        code = getattr(exc, "code", None)
        if code in (409, "ALREADY_EXISTS"):
            return True
        s = str(exc).lower()
        return "already exists" in s or "already_exists" in s

    try:
        await asyncio.to_thread(_create)
        return True
    except Exception as e:
        if _is_dup(e):
            return False
        print(f"⚠️ Webhook Firestore dedupe create failed; durable file fallback: {e}")
        from services.durable_event_claim import try_claim_event

        return await try_claim_event(
            "webhook_inbound_processed",
            mid,
            ttl_seconds=300.0,
            firestore_collection="webhook_inbound_processed_file",
        )


async def _webhook_bodyfp_firestore_try_acquire(body_fp: str, current_time: float) -> bool:
    """
    Multi-worker: same inbound text + sender within WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS (bucketed)
    should only enqueue one process_parsed_message, even when the provider sends different message_ids.
    """
    fp = (body_fp or "").strip()
    if not fp:
        return True
    slot = int(current_time // WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS)
    basis = f"{fp}\0bodyfp_slot{slot}"
    db = get_firestore_db()
    if not db:
        from services.durable_event_claim import try_claim_event

        return await try_claim_event(
            "webhook_text_body_processed",
            basis,
            ttl_seconds=float(WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS) * 2,
            firestore_collection="webhook_text_body_processed_file",
        )
    doc_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("webhook_text_body_processed")
        .document(doc_id)
    )

    def _create() -> None:
        ref.create(
            {
                "created_at": firestore.SERVER_TIMESTAMP,
                "body_fingerprint_prefix": fp[:120],
                "time_slot": slot,
            }
        )

    def _is_dup(exc: BaseException) -> bool:
        if type(exc).__name__ in ("AlreadyExists", "Conflict"):
            return True
        code = getattr(exc, "code", None)
        if code in (409, "ALREADY_EXISTS"):
            return True
        s = str(exc).lower()
        return "already exists" in s or "already_exists" in s

    try:
        await asyncio.to_thread(_create)
        return True
    except Exception as e:
        if _is_dup(e):
            return False
        print(f"⚠️ Webhook body-fp Firestore dedupe create failed; durable file fallback: {e}")
        from services.durable_event_claim import try_claim_event

        return await try_claim_event(
            "webhook_text_body_processed",
            basis,
            ttl_seconds=float(WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS) * 2,
            firestore_collection="webhook_text_body_processed_file",
        )


# Second line of defense: same worker can queue two process_parsed_message tasks for the same message_id
# (e.g. webhook handler returns before Firestore create is visible). Serialize + skip duplicate in-process.
_process_parsed_mid_locks: dict[str, asyncio.Lock] = {}
_process_parsed_mid_claims: dict[str, float] = {}
_PROCESS_PARSED_MID_TTL_SECONDS = 120.0


async def _process_parsed_should_skip_duplicate(message_id: str) -> bool:
    """Return True if this message_id is already being or was recently processed (skip)."""
    mid = (message_id or "").strip()
    if not mid:
        return False
    now = time.time()
    expired = [k for k, ts in _process_parsed_mid_claims.items() if now - ts > _PROCESS_PARSED_MID_TTL_SECONDS]
    for k in expired:
        _process_parsed_mid_claims.pop(k, None)
        _process_parsed_mid_locks.pop(k, None)

    lock = _process_parsed_mid_locks.setdefault(mid, asyncio.Lock())
    async with lock:
        if mid in _process_parsed_mid_claims:
            print(f"⚠️ skip duplicate process_parsed_message (in-process): {mid[:56]}...")
            return True
        _process_parsed_mid_claims[mid] = now
    return False


def _process_parsed_release_claim_on_error(message_id: str) -> None:
    mid = (message_id or "").strip()
    if not mid:
        return
    _process_parsed_mid_claims.pop(mid, None)
    _process_parsed_mid_locks.pop(mid, None)


async def await_whatsapp_delayed_processing(user_id: str) -> None:
    """
    handle_message() schedules combine+GPT in a Task and returns immediately. process_parsed_message
    is also run via ensure_future after the webhook returns 200 — if we do not await this task here,
    the background chain can end before the reply is sent (users see no AI response on WhatsApp).
    """
    from handlers.text_handlers import _delayed_processing_tasks

    if user_id not in _delayed_processing_tasks:
        return
    task = _delayed_processing_tasks[user_id]
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        print(f"⚠️ [webhook] Delayed processing cancelled for user_id={user_id}")
    except Exception as e:
        print(f"❌ [webhook] Delayed processing failed for user_id={user_id}: {e}")
    finally:
        _delayed_processing_tasks.pop(user_id, None)


