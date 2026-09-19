"""Incremental Voyage upsert/delete for one product. Customer turns never call this."""

from __future__ import annotations

import logging
from typing import Any

from services.brain.flags import voyage_configured
from services.brain.providers.spaces import ENTITY_DOCUMENT
from services.brain.retrieve.products import cards_from_products
from services.brain.search.index_job import document_rows, embed_document_rows_incremental
from services.brain.search.store import activate_pointer, get_source_pointer_ready, write_documents
from services.products.availability import is_customer_searchable

log = logging.getLogger("customer_ai.product_reindex")


def schedule_product_reindex(
    tenant_id: str,
    product_id: str,
    *,
    deleted: bool = False,
    session: Any | None = None,
) -> None:
    tid = (tenant_id or "").strip()
    pid = (product_id or "").strip()
    if not tid or not pid:
        return
    if deleted:
        delete_product_vectors(session, tid, pid)
        return
    if not voyage_configured():
        return
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        loop.create_task(upsert_product_vectors(tid, pid))
    except RuntimeError:
        _enqueue(tid, pid)


def _enqueue(tenant_id: str, product_id: str) -> None:
    try:
        from services.brain.search.index_schedule import published_revision
        from services.queues.job_queue import job_queue

        job_queue.enqueue(
            queue="expensive",
            job_type="customer_ai_index",
            tenant_id=tenant_id,
            payload={
                "revision": published_revision(tenant_id),
                "reason": "product_upsert",
                "product_id": product_id,
            },
            idempotency_key=f"cai-product:{tenant_id}:{product_id}",
        )
    except Exception:
        log.info("product reindex enqueue skipped tenant=%s", tenant_id)


def delete_product_vectors(session: Any | None, tenant_id: str, product_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    pid = (product_id or "").strip()
    if not tid or not pid:
        return {"ok": False, "reason": "missing_ids"}
    _delete_memory(tid, pid)
    if session is None:
        return {"ok": True, "backend": "memory"}
    try:
        from sqlalchemy import text

        session.execute(
            text(
                """
                DELETE FROM customer_ai_search_documents
                WHERE tenant_id = :tenant_id
                  AND source_family = 'products'
                  AND source_id = :source_id
                """
            ),
            {"tenant_id": tid, "source_id": pid},
        )
        return {"ok": True, "backend": "pgvector"}
    except Exception:
        return {"ok": True, "backend": "best_effort"}


async def upsert_product_vectors(tenant_id: str, product_id: str, session: Any | None = None) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    pid = (product_id or "").strip()
    if not tid or not pid:
        return {"ok": False, "reason": "missing_ids"}
    if session is not None:
        return await _upsert_with(session, tid, pid)
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

        with whatsapp_session(require=True) as db:
            return await _upsert_with(db, tid, pid)
    except WhatsAppDatabaseUnavailable:
        return await _upsert_with(None, tid, pid)
    except Exception as exc:
        log.warning("product upsert failed tenant=%s err=%s", tid, type(exc).__name__)
        return {"ok": False, "reason": "provider_error"}


async def run_product_reindex_job(tenant_id: str, product_id: str, *, deleted: bool = False) -> dict[str, Any]:
    if deleted:
        return delete_product_vectors(None, tenant_id, product_id)
    return await upsert_product_vectors(tenant_id, product_id)


def _delete_memory(tenant_id: str, product_id: str) -> None:
    from services.brain.search.store import _MEMORY

    bucket = _MEMORY.get(tenant_id)
    if not bucket:
        return
    bucket[:] = [
        item
        for item in bucket
        if not (str(item.get("source_family") or "") == "products" and str(item.get("source_id") or "") == product_id)
    ]


def _load_row(session: Any | None, tenant_id: str, product_id: str) -> Any | None:
    from services.products.repository import ProductsRepository

    if session is not None:
        return ProductsRepository(session).get_product(tenant_id=tenant_id, product_id=product_id)
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=True) as db:
            return ProductsRepository(db).get_product(tenant_id=tenant_id, product_id=product_id)
    except Exception:
        return None


async def _upsert_with(session: Any | None, tenant_id: str, product_id: str) -> dict[str, Any]:
    row = _load_row(session, tenant_id, product_id)
    if row is None or not is_customer_searchable(str(getattr(row, "availability", "") or "")):
        return delete_product_vectors(session, tenant_id, product_id)
    pointer = get_source_pointer_ready(tenant_id, "entities") or {}
    version = str(pointer.get("active_version") or "")
    if not version:
        return {"ok": False, "reason": "no_active_index"}
    if not voyage_configured():
        return {"ok": False, "reason": "provider_not_configured"}
    cards = cards_from_products([row])
    if not cards:
        return delete_product_vectors(session, tenant_id, product_id)
    rows = document_rows(cards, tenant_id=tenant_id, version=version)
    try:
        vectors, _embedded = await embed_document_rows_incremental(rows, session=session)
    except Exception as exc:
        log.warning("product embed failed tenant=%s err=%s", tenant_id, type(exc).__name__)
        return {"ok": False, "reason": "provider_error"}
    written = write_documents(session, rows, vectors)
    if not written.get("ok"):
        return {"ok": False, "reason": str(written.get("reason") or "index_not_ready")}
    activate_pointer(
        session,
        tenant_id=tenant_id,
        space_id=ENTITY_DOCUMENT.space_id,
        source_family="products",
        version=version,
        count=int(pointer.get("record_count") or len(rows)),
        source_revision=version,
    )
    return {"ok": True, "reason": "ok", "count": len(rows), "version": version}
