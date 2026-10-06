"""Cross-replica outbound text dedupe using a Redis TTL key.

Duplicate deliveries from two nodes hit the same key. The key is deleted when
the send fails so a retry can claim it. A successful send leaves the key until
the bucket window ends.
"""

from __future__ import annotations

import hashlib
import os
import time

from services.scale.redis_claims import RedisClaimStore

_BUCKET_SEC = max(
    15,
    int(float(os.getenv("OUTBOUND_TEXT_DEDUPE_WINDOW_SEC", "90"))),
)


def _enabled() -> bool:
    raw = os.getenv("OUTBOUND_TEXT_DEDUPE", os.getenv("OUTBOUND_TEXT_FIRESTORE_DEDUPE", "false"))
    return raw.strip().lower() in {"1", "true", "yes"}


def firestore_outbound_dedupe_enabled() -> bool:
    return _enabled()


def _doc_id(recipient_pk: str, body_norm: str) -> str:
    slot = int(time.time() // _BUCKET_SEC)
    basis = f"{recipient_pk}\0{(body_norm or '')[:12000]}\0slot{slot}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()


async def try_acquire_outbound_send_firestore(recipient_pk: str, body_norm: str) -> str | None:
    """Return a claim id, None when another node owns the send, or '' when dedupe is off."""
    if not _enabled():
        return ""
    recipient = (recipient_pk or "").strip()
    body = (body_norm or "").strip()
    if not recipient or not body:
        return ""
    doc_id = _doc_id(recipient, body)
    claimed = RedisClaimStore().try_claim("outbound_text", doc_id, ttl_seconds=_BUCKET_SEC)
    if claimed is True:
        return doc_id
    if claimed is False:
        return None
    return ""


async def release_outbound_send_firestore(doc_id: str, send_success: bool) -> None:
    """Keep the key after success. Delete it after a failed send so a retry can proceed."""
    if not doc_id or not _enabled() or send_success:
        return
    RedisClaimStore().release_claim("outbound_text", doc_id)
