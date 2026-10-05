"""Keep a conversation document at a recent tail and archive the older messages.

New saves still return immediately. When the stored array is over the tail,
a background pass copies a batch into thread_messages and then shortens the
parent. Older messages stay readable from that subcollection.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

TAIL_LIMIT = 40
_BATCH = 80


def message_document_id(message: dict[str, Any]) -> str:
    raw = str(message.get("message_id") or "").strip()
    if not raw:
        stamp = str(message.get("timestamp") or "")
        raw = hashlib.sha256(f"{stamp}:{message.get('role')}:{message.get('text')}".encode()).hexdigest()[:32]
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in raw)
    return cleaned[:180] or "message"


def schedule_thread_trim(doc_ref: Any) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(asyncio.to_thread(_trim_batches, doc_ref))


def _trim_batches(doc_ref: Any) -> None:
    for _ in range(8):
        if not _trim_one_batch(doc_ref):
            return


def _trim_one_batch(doc_ref: Any) -> bool:
    snapshot = doc_ref.get(timeout=8, retry=None)
    if getattr(snapshot, "exists", False) is not True:
        return False
    data = snapshot.to_dict() or {}
    messages = [item for item in list(data.get("messages") or []) if isinstance(item, dict)]
    if len(messages) <= TAIL_LIMIT:
        if data.get("thread_trim_pending"):
            doc_ref.update({"thread_trim_pending": False})
        return False
    overflow = messages[:-TAIL_LIMIT]
    tail = messages[-TAIL_LIMIT:]
    chunk = overflow[:_BATCH]
    rest = overflow[_BATCH:]
    collection = doc_ref.collection("thread_messages")
    for message in chunk:
        collection.document(message_document_id(message)).set(message, merge=True)
    doc_ref.update(
        {
            "messages": rest + tail,
            "thread_trim_pending": len(rest) > 0,
        }
    )
    return len(rest) > 0


def load_messages_before(doc_ref: Any, before: Any, limit: int) -> list[dict[str, Any]]:
    """Older archived messages strictly before a timestamp."""
    from services.persistence import query_api as firestore

    from services.live_chat.contracts import parse_timestamp_utc

    moment = parse_timestamp_utc(before)
    cap = max(1, min(100, int(limit)))
    query = doc_ref.collection("thread_messages").order_by("timestamp", direction=firestore.Query.DESCENDING)
    if moment is not None:
        query = query.where("timestamp", "<", moment)
    query = query.limit(cap)
    try:
        docs = list(query.stream(timeout=8, retry=None))
    except Exception:
        return []
    rows = []
    for doc in docs:
        payload = doc.to_dict() or {}
        if isinstance(payload, dict):
            rows.append(payload)
    rows.sort(key=lambda item: str(item.get("timestamp") or ""))
    return rows[-cap:]
