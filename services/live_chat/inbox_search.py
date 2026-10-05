"""Search the tenant inbox by paging the recency index.

One request scans at most 160 index documents. The returned cursor is the last
document examined, so the next request continues and can reach every row.
"""

from __future__ import annotations

from typing import Any

_PAGE = 40
_MAX_DOCS = 160


class SearchPage:
    def __init__(self, docs: list[Any], *, has_more: bool, next_cursor: str | None) -> None:
        self.docs = docs
        self.has_more = has_more
        self.next_cursor = next_cursor


def _cursor_of(service: Any, doc: Any) -> str:
    data = doc.to_dict() or {}
    last_at = data.get("last_message_at") or ""
    if hasattr(last_at, "isoformat"):
        last_at = last_at.isoformat()
    return f"{last_at}|{getattr(doc, 'id', '')}"


def _matches(doc: Any, needle: str) -> bool:
    data = doc.to_dict() or {}
    customer = data.get("customer_info") or {}
    fields = (
        data.get("user_name"),
        customer.get("name"),
        data.get("user_phone"),
        data.get("phone_clean"),
        customer.get("phone_full"),
        customer.get("phone_clean"),
    )
    return any(needle in str(field or "").lower() for field in fields)


def search_index_page(
    service: Any,
    index_coll: Any,
    tenant_id: str,
    *,
    search: str,
    cursor: str | None,
    page_size: int,
) -> SearchPage:
    needle = (search or "").strip().lower()
    want = max(1, int(page_size))
    matched: list[Any] = []
    current = (cursor or "").strip() or None
    scanned = 0
    has_more = False
    next_cursor: str | None = None
    while scanned < _MAX_DOCS and len(matched) < want:
        docs = service._stream_tenant_index_docs(
            index_coll,
            tenant_id,
            limit=_PAGE,
            cursor=current,
        )
        if not docs:
            has_more = False
            break
        for doc in docs:
            scanned += 1
            current = _cursor_of(service, doc)
            next_cursor = current
            if needle and _matches(doc, needle):
                matched.append(doc)
                if len(matched) >= want:
                    has_more = True
                    break
        else:
            has_more = len(docs) >= _PAGE
            if not has_more:
                next_cursor = None
            continue
        break
    if not has_more:
        next_cursor = None
    return SearchPage(matched, has_more=has_more, next_cursor=next_cursor)
