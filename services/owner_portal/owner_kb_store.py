"""Platform owner knowledge entries. Vectors live in the customer search index."""

from __future__ import annotations

import uuid
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import text

from services.brain.providers.spaces import ENTITY_DOCUMENT
from services.owner_portal.owner_embed import embed_one

OWNER_KB_TENANT = "linas-owner-copilot"
_FAMILY = "owner_kb"
_TOP_K = 5


def _session() -> AbstractContextManager[Any]:
    from db.session import whatsapp_session

    return whatsapp_session(require=False)


def list_entries() -> list[dict[str, str]]:
    try:
        with _session() as session:
            if session is None:
                return []
            rows = session.execute(
                text("SELECT id, title, body, updated_at FROM owner_copilot_kb_entries ORDER BY updated_at DESC")
            ).all()
    except Exception:
        return []
    return [
        {"id": str(row[0]), "title": str(row[1] or ""), "body": str(row[2] or ""), "updated_at": str(row[3] or "")}
        for row in rows
    ]


def save_entry(*, title: str, body: str, entry_id: str | None = None) -> dict[str, str]:
    from datetime import UTC, datetime

    item_id = (entry_id or "").strip() or uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    with _session() as session:
        if session is None:
            raise RuntimeError("database_unavailable")
        session.execute(
            text(
                """
                INSERT INTO owner_copilot_kb_entries (id, title, body, updated_at)
                VALUES (:id, :title, :body, :updated_at)
                ON CONFLICT (id) DO UPDATE
                SET title = excluded.title, body = excluded.body, updated_at = excluded.updated_at
                """
            ),
            {"id": item_id, "title": title.strip(), "body": body.strip(), "updated_at": now},
        )
        session.commit()
    _reindex(item_id, title.strip(), body.strip())
    return {"id": item_id, "title": title.strip(), "body": body.strip(), "updated_at": now}


def delete_entry(entry_id: str) -> None:
    with _session() as session:
        if session is None:
            return
        session.execute(text("DELETE FROM owner_copilot_kb_entries WHERE id = :id"), {"id": entry_id})
        session.commit()
    _reindex(entry_id, "", "")


def _reindex(entry_id: str, title: str, body: str) -> None:
    from services.brain.search.store import write_documents

    text_value = f"{title}\n{body}".strip()
    vector = embed_one(text_value, query=False) if text_value else None
    if not vector:
        return
    row = {
        "id": f"owner-kb-{entry_id}",
        "tenant_id": OWNER_KB_TENANT,
        "space_id": ENTITY_DOCUMENT.space_id,
        "source_family": _FAMILY,
        "source_id": entry_id,
        "chunk_id": "0",
        "parent_id": entry_id,
        "index_version": "",
        "source_revision": "1",
        "content_hash": entry_id,
        "title": title,
        "search_text": text_value,
        "visible": bool(text_value),
    }
    with _session() as session:
        write_documents(session, [row], [vector])
        if session is not None:
            session.commit()


def search_kb(query: str, *, limit: int = _TOP_K) -> list[dict[str, Any]]:
    from services.brain.search.store import query_similar

    vector = embed_one(query, query=True)
    if vector:
        with _session() as session:
            found = query_similar(
                session,
                tenant_id=OWNER_KB_TENANT,
                space_id=ENTITY_DOCUMENT.space_id,
                vector=vector,
                families={_FAMILY},
                limit=limit,
            )
        if found.items:
            return [
                {"id": hit.source_id, "title": hit.title, "body": hit.search_text, "score": hit.score}
                for hit in found.items
            ]
    return _overlap(query, limit)


def _overlap(query: str, limit: int) -> list[dict[str, Any]]:
    tokens = [part for part in (query or "").lower().split() if len(part) >= 3]
    ranked: list[tuple[int, dict[str, str]]] = []
    for item in list_entries():
        blob = f"{item['title']} {item['body']}".lower()
        score = sum(2 for token in tokens if token in blob)
        ranked.append((score, item))
    ranked.sort(key=lambda pair: -pair[0])
    return [{**item, "score": score} for score, item in ranked[:limit] if score > 0]
