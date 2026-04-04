"""
Cross-replica outbound text dedupe: in-memory outbound_text_dedupe only works inside one process.

Duplicate WhatsApp deliveries often come from two Cloud Run (etc.) instances each completing
the same AI turn. Firestore create-if-absent on a time-bucketed key lets only one instance
perform the HTTP send for identical body + recipient within a short window.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Optional

from google.cloud import firestore

from utils.utils import get_firestore_db

# Align bucket with outbound window so duplicate replicas hit the same document id.
_BUCKET_SEC = max(
    15,
    int(float(os.getenv("OUTBOUND_TEXT_DEDUPE_WINDOW_SEC", "90"))),
)


def _is_already_exists(exc: BaseException) -> bool:
    if type(exc).__name__ in ("AlreadyExists", "Conflict"):
        return True
    code = getattr(exc, "code", None)
    if code in (409, "ALREADY_EXISTS"):
        return True
    s = str(exc).lower()
    return "already exists" in s or "already_exists" in s


def _doc_id(recipient_pk: str, body_norm: str) -> str:
    slot = int(time.time() // _BUCKET_SEC)
    b = (body_norm or "")[:12000]
    basis = f"{recipient_pk}\0{b}\0slot{slot}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()


def firestore_outbound_dedupe_enabled() -> bool:
    return os.getenv("OUTBOUND_TEXT_FIRESTORE_DEDUPE", "true").lower() in (
        "1",
        "true",
        "yes",
    )


async def try_acquire_outbound_send_firestore(recipient_pk: str, body_norm: str) -> Optional[str]:
    """
    Try to claim the right to send this exact text to this recipient in the current time bucket.

    Returns:
      None — another instance already claimed (skip send).
      "" — Firestore disabled/unavailable/empty key; no claim to release.
      str — document id; caller must call release_outbound_send_firestore after HTTP completes.
    """
    if not firestore_outbound_dedupe_enabled():
        return ""
    r = (recipient_pk or "").strip()
    b = (body_norm or "").strip()
    if not r or not b:
        return ""
    db = get_firestore_db()
    if not db:
        return ""
    doc_id = _doc_id(r, b)
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("outbound_text_dedupe")
        .document(doc_id)
    )

    def _create():
        ref.create(
            {
                "created_at": firestore.SERVER_TIMESTAMP,
                "recipient_prefix": r[:32],
                "bucket_sec": _BUCKET_SEC,
            }
        )

    try:
        await asyncio.to_thread(_create)
        return doc_id
    except Exception as e:
        if _is_already_exists(e):
            return None
        print(f"⚠️ outbound_text_dedupe Firestore create failed (fail-open send): {e}")
        return ""


async def release_outbound_send_firestore(doc_id: str, send_success: bool) -> None:
    """After HTTP: keep doc on success (blocks duplicate replicas); delete on failure so retries can claim."""
    if not doc_id or not firestore_outbound_dedupe_enabled():
        return
    db = get_firestore_db()
    if not db:
        return
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("outbound_text_dedupe")
        .document(doc_id)
    )

    def _delete():
        try:
            ref.delete()
        except Exception as ex:
            print(f"⚠️ outbound_text_dedupe delete failed: {ex}")

    if send_success:
        return
    await asyncio.to_thread(_delete)
