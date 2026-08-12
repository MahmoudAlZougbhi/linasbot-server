"""Shared live-chat helpers (idempotency, env, display name). Qiscus/WhatsApp adapters stay on the service mixins."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Any

from google.cloud import firestore

from services.meta_messaging import scrub_legacy_meta_channel_placeholder

# In-memory fallback when Firestore idempotency is unavailable (single-process only).
_operator_send_idempotency_keys: dict[str, float] = {}


def _live_chat_display_name(*candidates: Any, fallback: str = "Unknown Customer") -> str:
    """Pick the first non-empty label, scrubbing legacy Meta channel placeholders."""
    for candidate in candidates:
        cleaned = scrub_legacy_meta_channel_placeholder(candidate)
        if cleaned:
            return cleaned
    return fallback


def _operator_send_idempotency_memory_consume(fingerprint: str) -> bool:
    """Return False if this fingerprint was seen recently (skip duplicate send)."""
    if not fingerprint or not str(fingerprint).strip():
        return True
    k = str(fingerprint).strip()
    ttl = _env_float("OPERATOR_SEND_IDEMPOTENCY_TTL_SECONDS", 120.0)
    now = time.time()
    expired = [x for x, ts in _operator_send_idempotency_keys.items() if now - ts > ttl]
    for x in expired:
        _operator_send_idempotency_keys.pop(x, None)
    if k in _operator_send_idempotency_keys:
        print(f"⚠️ Duplicate operator send suppressed (memory idempotency, fp={k[:48]}...)")
        return False
    _operator_send_idempotency_keys[k] = now
    return True


def _build_operator_idempotency_fingerprint(
    idempotency_key: str | None,
    conversation_id: str,
    operator_id: str,
    message_type: str,
    message: str,
) -> str:
    """Stable string per logical send. Client UUID preferred; else hash+time bucket for double-submit without key."""
    if idempotency_key and str(idempotency_key).strip():
        return str(idempotency_key).strip()
    bucket_sec = max(1.0, _env_float("OPERATOR_SEND_ANON_BUCKET_SECONDS", 3.0))
    bucket = int(time.time() / bucket_sec)
    body_hash = hashlib.sha256(
        f"{conversation_id}\0{operator_id}\0{message_type}\0{message}".encode("utf-8", errors="replace")
    ).hexdigest()
    return f"anon:{body_hash}:{bucket}"


def _operator_idempotency_doc_id(fingerprint: str) -> str:
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


async def _try_acquire_operator_send_idempotency(db: Any, app_id: str, fingerprint: str) -> Any:
    """
    Returns (acquired: bool, lock_ref_or_none).
    lock_ref is a Firestore DocumentReference when acquired via Firestore; caller must delete on failure.
    """
    doc_id = _operator_idempotency_doc_id(fingerprint)
    if db is None:
        ok = _operator_send_idempotency_memory_consume(fingerprint)
        return ok, None

    ref = db.collection("artifacts").document(app_id).collection("operator_outbound_idempotency").document(doc_id)

    def _create_lock() -> None:
        # create() is atomic: second caller gets ALREADY_EXISTS — works across workers (unlike in-memory).
        ref.create(
            {
                "created_at": firestore.SERVER_TIMESTAMP,
                "fp_prefix": fingerprint[:200],
            }
        )

    def _is_already_exists(err: BaseException) -> bool:
        name = type(err).__name__
        if name in ("AlreadyExists", "Conflict", "Aborted"):
            return True
        code = getattr(err, "code", None)
        if code in (409, "ALREADY_EXISTS"):
            return True
        s = str(err).lower()
        return "already exists" in s or "already_exists" in s or "document already exists" in s or "409" in s

    try:
        await asyncio.to_thread(_create_lock)
        return True, ref
    except Exception as e:
        if _is_already_exists(e):
            print(f"⚠️ Duplicate operator send suppressed (Firestore idempotency doc={doc_id[:16]}...)")
            return False, None
        print(f"⚠️ Firestore idempotency create failed, falling back to memory: {e}")
        ok = _operator_send_idempotency_memory_consume(fingerprint)
        return ok, None


async def _release_operator_idempotency_lock(db: Any, lock_ref: Any) -> None:
    if db is None or lock_ref is None:
        return
    try:
        await asyncio.to_thread(lock_ref.delete)
    except Exception as e:
        print(f"⚠️ Could not release operator idempotency lock: {e}")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


