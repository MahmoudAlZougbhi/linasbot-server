"""Publish-time Voyage index. Never rebuild the corpus on a customer turn."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.spaces import ENTITY_DOCUMENT, ENTITY_MODEL, KNOWLEDGE_MODEL
from services.customer_ai.providers.voyage_client import VoyageContractError, embed_texts
from services.customer_ai.retrieve.cards import TitleCard, load_published_cards
from services.customer_ai.retrieve.products import load_product_cards
from services.customer_ai.search.store import activate_pointer, write_documents

log = logging.getLogger("customer_ai.index")
COMPILER_VERSION = "customer_ai.compiler.v1"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row(*, tenant_id: str, card: TitleCard, version: str, chunk_id: str, text: str) -> dict[str, Any]:
    return {
        "id": f"{tenant_id}:{chunk_id or card.item_id}:{version}",
        "tenant_id": tenant_id,
        "space_id": ENTITY_DOCUMENT.space_id,
        "source_family": card.source_family,
        "source_id": card.item_id.split(":", 1)[-1],
        "chunk_id": chunk_id,
        "index_version": version,
        "source_revision": card.revision,
        "content_hash": _hash(text),
        "title": card.title,
        "search_text": text,
        "visible": True,
        "payload": {
            "embedding_model": ENTITY_MODEL,
            "compiler_version": COMPILER_VERSION,
            "index_role": "candidate",
        },
    }


def document_rows(cards: list[TitleCard], *, tenant_id: str, version: str) -> list[dict[str, Any]]:
    from services.customer_ai.compiler.chunks import chunk_document

    rows: list[dict[str, Any]] = []
    for card in cards:
        if card.source_family == "knowledge":
            chunks = chunk_document(document_id=card.item_id, body=card.body or card.search_text)
            if chunks:
                for chunk in chunks:
                    rows.append(
                        _row(tenant_id=tenant_id, card=card, version=version, chunk_id=chunk.chunk_id, text=chunk.text)
                    )
                continue
        rows.append(_row(tenant_id=tenant_id, card=card, version=version, chunk_id="", text=card.search_text))
    return rows


async def embed_card_batch(cards: list[TitleCard]) -> list[list[float]]:
    rows = document_rows(cards, tenant_id="embed", version="batch")
    return await embed_document_rows(rows)


async def embed_document_rows(rows: list[dict[str, Any]]) -> list[list[float]]:
    if not rows:
        return []
    if not voyage_configured():
        raise VoyageContractError("provider_not_configured")
    vectors = await embed_texts(ENTITY_DOCUMENT, [str(row.get("search_text") or "") for row in rows])
    return vectors.vectors


def write_entity_candidate(
    session: Any | None, rows: list[dict[str, Any]], vectors: list[list[float]], *, tenant_id: str, revision: str
) -> dict[str, Any]:
    if not rows:
        return {
            "written": True,
            "ready": False,
            "reason": "empty_entity",
            "count": 0,
            "version": revision,
            "role": "candidate",
            "store": "memory" if session is None else "pgvector",
            "model": ENTITY_MODEL,
        }
    written = write_documents(session, rows, vectors)
    if not written.get("ok"):
        return {
            "written": False,
            "ready": False,
            "reason": written.get("reason") or "index_not_ready",
            "count": len(rows),
            "version": revision,
            "role": "candidate",
        }
    return {
        "written": True,
        "ready": False,
        "reason": "candidate_built",
        "count": len(rows),
        "version": revision,
        "role": "candidate",
        "store": written.get("backend"),
        "model": ENTITY_MODEL,
        "compiler_version": COMPILER_VERSION,
    }


def activate_entity_index(
    session: Any | None, *, tenant_id: str, revision: str, count: int
) -> dict[str, Any]:
    pointer = activate_pointer(
        session,
        tenant_id=tenant_id,
        space_id=ENTITY_DOCUMENT.space_id,
        source_family="entities",
        version=revision or "unpublished",
        count=count,
        source_revision=revision,
    )
    if not pointer.get("ok") and session is not None:
        return {"ok": False, "reason": pointer.get("reason") or "index_not_ready"}
    return {"ok": True, "pointer": pointer.get("pointer"), "store": pointer.get("backend")}


def _serving_ready(session: Any | None, store: str) -> bool:
    return store == "pgvector" or session is None


async def index_published_tenant(
    tenant_id: str,
    *,
    revision: str,
    session: Any | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"ready": False, "reason": "unpublished", "count": 0, "health": "NO_INDEX"}
    from services.membership.processing_budgets import ProcessingBudgetError, begin_job, consume_attempt, end_job

    try:
        begin_job(tid)
        consume_attempt(tid)
    except ProcessingBudgetError as exc:
        return {"ready": False, "reason": exc.code, "count": 0, "health": "FAILED"}
    try:
        return await _index_published_body(tid, revision=revision, session=session, activate=activate)
    finally:
        end_job(tid)


async def _index_published_body(
    tid: str, *, revision: str, session: Any | None, activate: bool
) -> dict[str, Any]:
    cards = [*load_published_cards(tid), *load_product_cards(tid)]
    rows = document_rows(cards, tenant_id=tid, version=revision or "unpublished")
    if not voyage_configured():
        log.info("customer_ai index skipped: voyage_not_configured tenant=%s", tid)
        from services.customer_ai.search.index_lifecycle import mark_failed

        mark_failed(tid, revision=revision, reason="provider_not_configured")
        return {"ready": False, "reason": "provider_not_configured", "count": len(rows), "health": "FAILED"}
    try:
        vectors = await embed_document_rows(rows)
        from services.membership.provider_expense import record_pending_provider

        record_pending_provider(
            event_id=f"embed:{tid}:{revision}",
            tenant_id=tid,
            category="embedding",
            feature="knowledge",
            provider="voyage",
            model=ENTITY_MODEL,
            quantity=len(rows),
            operation_id=revision,
        )
    except Exception as exc:
        log.warning("customer_ai index embed failed tenant=%s err=%s", tid, type(exc).__name__)
        from services.customer_ai.search.index_lifecycle import mark_failed

        mark_failed(tid, revision=revision, reason="provider_error")
        return {"ready": False, "reason": "provider_error", "count": len(rows), "health": "FAILED"}
    if len(vectors) != len(rows):
        from services.customer_ai.search.index_lifecycle import mark_failed

        mark_failed(tid, revision=revision, reason="provider_error")
        return {"ready": False, "reason": "provider_error", "count": len(rows), "health": "FAILED"}

    if session is not None:
        return await _persist_candidate_and_maybe_activate(
            session, tid=tid, revision=revision, rows=rows, vectors=vectors, cards=cards, activate=activate
        )
    return await _index_with_resolved_session(tid, revision=revision, rows=rows, vectors=vectors, cards=cards, activate=activate)


async def _index_with_resolved_session(
    tid: str,
    *,
    revision: str,
    rows: list[dict[str, Any]],
    vectors: list[list[float]],
    cards: list[TitleCard],
    activate: bool,
) -> dict[str, Any]:
    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    from services.queues.config import is_production_env

    try:
        with whatsapp_session(require=True) as db:
            return await _persist_candidate_and_maybe_activate(
                db, tid=tid, revision=revision, rows=rows, vectors=vectors, cards=cards, activate=activate
            )
    except WhatsAppDatabaseUnavailable:
        if is_production_env():
            from services.customer_ai.search.index_lifecycle import mark_failed

            mark_failed(tid, revision=revision, reason="index_not_ready")
            return {"ready": False, "reason": "index_not_ready", "count": len(rows), "store": "unavailable", "health": "FAILED"}
        return await _persist_candidate_and_maybe_activate(
            None, tid=tid, revision=revision, rows=rows, vectors=vectors, cards=cards, activate=activate
        )
    except Exception:
        from services.customer_ai.search.index_lifecycle import mark_failed

        mark_failed(tid, revision=revision, reason="index_not_ready")
        return {"ready": False, "reason": "index_not_ready", "count": len(rows), "store": "unavailable", "health": "FAILED"}


async def _persist_candidate_and_maybe_activate(
    session: Any | None,
    *,
    tid: str,
    revision: str,
    rows: list[dict[str, Any]],
    vectors: list[list[float]],
    cards: list[TitleCard],
    activate: bool,
) -> dict[str, Any]:
    from services.customer_ai.compiler.chunks import CONTEXTUALIZATION_VERSION
    from services.customer_ai.search.contextual_index import CHUNKER_VERSION, build_and_activate_contextual_index
    from services.customer_ai.search.index_lifecycle import mark_active, mark_candidate_ready, mark_failed
    from services.customer_ai.search.index_validate import candidate_is_activatable

    entity = write_entity_candidate(session, rows, vectors, tenant_id=tid, revision=revision)
    contextual = await build_and_activate_contextual_index(
        cards, tenant_id=tid, revision=revision, session=session, activate=False
    )
    gate = candidate_is_activatable(entity=entity, contextual=contextual)
    meta = {
        "entity": entity,
        "contextual": contextual,
        "version": revision,
        "count": entity.get("count") or len(rows),
        "embedding_model": ENTITY_MODEL,
        "contextual_model": KNOWLEDGE_MODEL,
        "compiler_version": COMPILER_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "contextualization_version": CONTEXTUALIZATION_VERSION,
        "manual_index_required": False,
    }
    if not gate.get("ok"):
        mark_failed(tid, revision=revision, reason=str(gate.get("reason") or "candidate_failed"))
        return {**meta, "ready": False, "reason": gate.get("reason"), "health": "FAILED"}
    mark_candidate_ready(
        tid,
        content_revision=revision,
        candidate_version=str(contextual.get("version") or revision),
        embedding_model=ENTITY_MODEL,
        contextual_model=KNOWLEDGE_MODEL,
        contextualization_version=CONTEXTUALIZATION_VERSION,
        chunker_version=CHUNKER_VERSION,
        compiler_version=COMPILER_VERSION,
    )
    if not activate:
        return {**meta, "ready": True, "reason": "candidate_ready", "health": "READY", "role": "candidate"}
    previous = ""
    try:
        from services.customer_ai.search.store import get_source_pointer_ready

        prev = get_source_pointer_ready(tid, "entities") or {}
        previous = str(prev.get("active_version") or "")
    except Exception:
        previous = ""
    entity_act = activate_entity_index(session, tenant_id=tid, revision=revision, count=int(entity.get("count") or 0))
    from services.customer_ai.providers.spaces import KNOWLEDGE_DOCUMENT
    from services.customer_ai.search.contextual_index import CONTEXT_FAMILY

    ctx_pointer = activate_pointer(
        session,
        tenant_id=tid,
        space_id=KNOWLEDGE_DOCUMENT.space_id,
        source_family=CONTEXT_FAMILY,
        version=str(contextual.get("version") or f"ctx:{revision}"),
        count=int(contextual.get("count") or 0),
        source_revision=revision,
    )
    ctx_act = {**contextual, "role": "active", "pointer": ctx_pointer.get("pointer"), "ready": True}
    if not ctx_pointer.get("ok") and session is not None:
        ctx_act = {**contextual, "ready": False, "reason": ctx_pointer.get("reason") or "pointer_activate_failed"}
    store = str(entity.get("store") or contextual.get("store") or "")
    ready = bool(entity_act.get("ok")) and bool(ctx_act.get("ready"))
    if not _serving_ready(session, store) and session is not None:
        ready = False
    if session is None:
        ready = bool(entity_act.get("ok"))
    if not ready:
        mark_failed(tid, revision=revision, reason=str(ctx_act.get("reason") or entity_act.get("reason") or "activate_failed"))
        return {**meta, "ready": False, "reason": "activate_failed", "health": "FAILED", "contextual": ctx_act}
    mark_active(
        tid,
        content_revision=revision,
        active_version=revision,
        candidate_version=str(contextual.get("version") or revision),
        rollback_version=previous,
        embedding_model=ENTITY_MODEL,
        contextual_model=KNOWLEDGE_MODEL,
        contextualization_version=CONTEXTUALIZATION_VERSION,
        chunker_version=CHUNKER_VERSION,
        compiler_version=COMPILER_VERSION,
    )
    return {
        **meta,
        "entity": {**entity, "ready": True, "role": "active"},
        "contextual": ctx_act,
        "ready": True,
        "reason": "ok",
        "health": "ACTIVE",
        "role": "active",
        "store": store or ("memory" if session is None else "pgvector"),
        "rollback_version": previous,
    }
