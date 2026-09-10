"""Publish-time Voyage index. Never rebuild the corpus on a customer turn."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.spaces import ENTITY_DOCUMENT
from services.customer_ai.providers.voyage_client import VoyageContractError, embed_texts
from services.customer_ai.retrieve.cards import TitleCard, load_published_cards
from services.customer_ai.retrieve.products import load_product_cards
from services.customer_ai.search.store import activate_pointer, write_documents

log = logging.getLogger("customer_ai.index")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def document_rows(cards: list[TitleCard], *, tenant_id: str, version: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        rows.append(
            {
                "id": f"{tenant_id}:{card.item_id}:{version}",
                "tenant_id": tenant_id,
                "space_id": ENTITY_DOCUMENT.space_id,
                "source_family": card.source_family,
                "source_id": card.item_id.split(":", 1)[-1],
                "chunk_id": "",
                "index_version": version,
                "source_revision": card.revision,
                "content_hash": _hash(card.search_text),
                "title": card.title,
                "search_text": card.search_text,
                "visible": True,
            }
        )
    return rows


async def embed_card_batch(cards: list[TitleCard]) -> list[list[float]]:
    if not cards:
        return []
    if not voyage_configured():
        raise VoyageContractError("provider_not_configured")
    vectors = await embed_texts(ENTITY_DOCUMENT, [card.search_text for card in cards])
    return vectors.vectors


def _persist_index(session: Any | None, rows: list[dict[str, Any]], vectors: list[list[float]], *, tenant_id: str, revision: str) -> dict[str, Any]:
    written = write_documents(session, rows, vectors)
    if not written.get("ok"):
        return {"ready": False, "reason": written.get("reason") or "index_not_ready", "count": len(rows)}
    pointer = activate_pointer(
        session,
        tenant_id=tenant_id,
        space_id=ENTITY_DOCUMENT.space_id,
        source_family="entities",
        version=revision or "unpublished",
        count=len(rows),
        source_revision=revision,
    )
    if not pointer.get("ok") and session is not None:
        return {"ready": False, "reason": pointer.get("reason") or "index_not_ready", "count": len(rows)}
    backend = str(written.get("backend") or "memory")
    ready = backend == "pgvector"
    return {
        "ready": ready,
        "reason": "ok" if ready else "index_not_ready",
        "count": len(rows),
        "store": backend,
    }


async def index_published_tenant(tenant_id: str, *, revision: str, session: Any | None = None) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"ready": False, "reason": "unpublished", "count": 0}
    cards = [*load_published_cards(tid), *load_product_cards(tid)]
    rows = document_rows(cards, tenant_id=tid, version=revision or "unpublished")
    if not voyage_configured():
        log.info("customer_ai index skipped: voyage_not_configured tenant=%s", tid)
        return {"ready": False, "reason": "provider_not_configured", "count": len(rows)}
    try:
        vectors = await embed_card_batch(cards)
    except Exception as exc:
        log.warning("customer_ai index embed failed tenant=%s err=%s", tid, type(exc).__name__)
        return {"ready": False, "reason": "provider_error", "count": len(rows)}
    if len(vectors) != len(rows):
        return {"ready": False, "reason": "provider_error", "count": len(rows)}
    if session is not None:
        return _persist_index(session, rows, vectors, tenant_id=tid, revision=revision)
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

        with whatsapp_session(require=True) as db:
            return _persist_index(db, rows, vectors, tenant_id=tid, revision=revision)
    except WhatsAppDatabaseUnavailable:
        return {"ready": False, "reason": "index_not_ready", "count": len(rows), "store": "unavailable"}
    except Exception:
        return {"ready": False, "reason": "index_not_ready", "count": len(rows), "store": "unavailable"}
