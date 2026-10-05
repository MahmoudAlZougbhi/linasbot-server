"""Cursor page of dashboard accounts, ordered by document id.

The owner screen asks for the next page instead of stopping after 200 rows.
"""

from __future__ import annotations

from typing import Any

from services.scale.firestore_usage import record_usage


def list_user_directory_page(
    service: Any,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    cap = max(1, min(100, int(limit)))
    query = service.collection.order_by("__name__").limit(cap + 1)
    marker = (cursor or "").strip()
    if marker:
        query = query.start_after([marker])
    try:
        docs = list(query.stream(timeout=service.AUTH_QUERY_TIMEOUT_SECONDS, retry=None))
    except Exception as exc:
        print(f"[auth:user_directory] failed type={type(exc).__name__}", flush=True)
        return {"users": [], "next_cursor": None, "has_more": False}
    has_more = len(docs) > cap
    page = docs[:cap]
    users: list[dict[str, Any]] = []
    for doc in page:
        try:
            sanitized = service._sanitize_user(doc.to_dict() or {}, doc_id=doc.id)
        except Exception:
            continue
        if sanitized is not None:
            users.append(sanitized)
    next_cursor = str(page[-1].id) if has_more and page else None
    record_usage("owner_user_page", reads=max(1, len(page)))
    return {"users": users, "next_cursor": next_cursor, "has_more": next_cursor is not None}
