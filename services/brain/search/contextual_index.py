"""Build and activate voyage-context-4 candidate index for knowledge families."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from services.brain.compiler.chunks import CONTEXTUALIZATION_VERSION, chunks_from_texts, contextual_groups
from services.brain.flags import voyage_configured
from services.brain.providers.spaces import KNOWLEDGE_DOCUMENT, KNOWLEDGE_MODEL
from services.brain.providers.voyage_client import VoyageContractError, embed_contextual_groups
from services.brain.retrieve.cards import TitleCard
from services.brain.search.store import activate_pointer, write_documents

log = logging.getLogger("customer_ai.contextual_index")

CONTEXT_FAMILY = "knowledge_ctx"
CHUNKER_VERSION = "customer_ai.chunk.v2"
COMPILER_VERSION = "customer_ai.compiler.v1"
CONTEXT_GROUP_BATCH = 4


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def knowledge_cards(cards: list[TitleCard]) -> list[TitleCard]:
    return [card for card in cards if card.source_family in {"knowledge", "care", "faq"}]


def build_contextual_rows(
    cards: list[TitleCard],
    *,
    tenant_id: str,
    version: str,
) -> tuple[list[dict[str, Any]], list[list[str]], list[str]]:
    """Returns (rows aligned to flattened vectors later, groups for API, parent order)."""
    rows: list[dict[str, Any]] = []
    groups: list[list[str]] = []
    parents: list[str] = []
    for card in knowledge_cards(cards):
        texts = card.chunks
        if not texts:
            blob = (card.body or card.search_text or "").strip()
            if not blob:
                continue
            texts = (blob,)
        chunks = chunks_from_texts(
            document_id=card.item_id,
            texts=texts,
            document_title=card.title,
            entity=card.title,
            source_family=card.source_family,
            tenant_id=tenant_id,
            source_version=card.revision or version,
        )
        if not chunks:
            continue
        grouped = contextual_groups(chunks)
        for parent_id, group_texts in grouped.items():
            parents.append(parent_id)
            groups.append(group_texts)
            for chunk in chunks:
                if chunk.parent_id != parent_id:
                    continue
                rows.append(
                    {
                        "id": f"{tenant_id}:{chunk.chunk_id}:{version}:ctx",
                        "tenant_id": tenant_id,
                        "space_id": KNOWLEDGE_DOCUMENT.space_id,
                        "source_family": card.source_family,
                        "source_id": card.item_id.split(":", 1)[-1],
                        "chunk_id": chunk.chunk_id,
                        "parent_id": chunk.parent_id,
                        "index_version": version,
                        "source_revision": card.revision,
                        "content_hash": _hash(chunk.raw_text),
                        "title": card.title,
                        "search_text": chunk.raw_text,
                        "visible": True,
                        "payload": {
                            **dict(chunk.metadata),
                            "raw_text": chunk.raw_text,
                            "contextualized_text": chunk.contextualized_text,
                            "embedding_model": KNOWLEDGE_MODEL,
                            "chunker_version": CHUNKER_VERSION,
                            "compiler_version": COMPILER_VERSION,
                            "contextualization_version": CONTEXTUALIZATION_VERSION,
                            "index_role": "candidate",
                        },
                    }
                )
    return rows, groups, parents


async def embed_contextual_rows(
    rows: list[dict[str, Any]],
    groups: list[list[str]],
    *,
    session: Any | None = None,
) -> tuple[list[list[float]], int]:
    if not rows:
        return [], 0
    if not voyage_configured():
        raise VoyageContractError("provider_not_configured")
    if not groups:
        return [], 0
    from services.brain.search.reuse_vectors import group_row_slices, lookup_prior_vectors, merge_prior_and_fresh

    prior = lookup_prior_vectors(session, rows)
    slices = group_row_slices(groups)
    if slices and slices[-1][1] != len(rows):
        raise VoyageContractError(f"contextual_group_row_mismatch:{slices[-1][1]}!={len(rows)}")
    fresh_groups: list[list[str]] = []
    missing: list[int] = []
    for group, (start, end) in zip(groups, slices, strict=True):
        if any(prior[index] is None for index in range(start, end)):
            for index in range(start, end):
                prior[index] = None
            fresh_groups.append(group)
            missing.extend(range(start, end))
    if not missing:
        return [vector for vector in prior if vector is not None], 0
    fresh: list[list[float]] = []
    for start in range(0, len(fresh_groups), CONTEXT_GROUP_BATCH):
        batch = fresh_groups[start : start + CONTEXT_GROUP_BATCH]
        embedded = await embed_contextual_groups(KNOWLEDGE_DOCUMENT, batch)
        for group_vectors in embedded:
            fresh.extend(group_vectors.vectors)
    if len(fresh) != len(missing):
        raise VoyageContractError(f"contextual_row_mismatch:{len(fresh)}!={len(missing)}")
    return merge_prior_and_fresh(prior, fresh), len(missing)


async def build_and_activate_contextual_index(
    cards: list[TitleCard],
    *,
    tenant_id: str,
    revision: str,
    session: Any | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Build candidate contextual index; optionally atomic-activate pointer."""
    tid = (tenant_id or "").strip()
    version = f"ctx:{revision or 'unpublished'}"
    rows, groups, _parents = build_contextual_rows(cards, tenant_id=tid, version=version)
    if not rows:
        return {
            "ready": True,
            "reason": "no_knowledge_chunks",
            "count": 0,
            "space_id": KNOWLEDGE_DOCUMENT.space_id,
            "model": KNOWLEDGE_MODEL,
            "version": version,
            "role": "candidate",
        }
    try:
        vectors, _embedded = await embed_contextual_rows(rows, groups, session=session)
    except Exception as exc:
        log.warning("contextual embed failed tenant=%s err=%s detail=%s", tid, type(exc).__name__, str(exc)[:200])
        return {
            "ready": False,
            "reason": "provider_error",
            "error": f"{type(exc).__name__}:{str(exc)[:160]}",
            "count": len(rows),
            "space_id": KNOWLEDGE_DOCUMENT.space_id,
            "model": KNOWLEDGE_MODEL,
            "version": version,
            "role": "candidate",
        }
    written = write_documents(session, rows, vectors)
    if not written.get("ok"):
        return {
            "ready": False,
            "reason": written.get("reason") or "index_not_ready",
            "count": len(rows),
            "space_id": KNOWLEDGE_DOCUMENT.space_id,
            "version": version,
            "role": "candidate",
        }
    result: dict[str, Any] = {
        "ready": False,
        "reason": "candidate_built",
        "count": len(rows),
        "space_id": KNOWLEDGE_DOCUMENT.space_id,
        "model": KNOWLEDGE_MODEL,
        "version": version,
        "role": "candidate",
        "store": written.get("backend"),
        "dimensions": KNOWLEDGE_DOCUMENT.dimensions,
        "contextualization_version": CONTEXTUALIZATION_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "compiler_version": COMPILER_VERSION,
    }
    result["ready"] = True
    if not activate:
        return result
    pointer = activate_pointer(
        session,
        tenant_id=tid,
        space_id=KNOWLEDGE_DOCUMENT.space_id,
        source_family=CONTEXT_FAMILY,
        version=version,
        count=len(rows),
        source_revision=revision,
    )
    if not pointer.get("ok") and session is not None:
        result["reason"] = pointer.get("reason") or "pointer_activate_failed"
        return result
    result["ready"] = str(written.get("backend") or "") == "pgvector" or session is None
    result["reason"] = "ok" if result["ready"] else "index_not_ready"
    result["role"] = "active"
    result["pointer"] = pointer.get("pointer")
    return result
