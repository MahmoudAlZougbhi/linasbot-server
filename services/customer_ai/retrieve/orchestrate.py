"""Bounded retrieve: lexical + Voyage hybrid on published cards, then expand winners."""

from __future__ import annotations

from dataclasses import dataclass

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.voyage_client import VoyageContractError, VoyageNotConfiguredError
from services.customer_ai.retrieve.cards import TitleCard, load_published_cards
from services.customer_ai.retrieve.expand import expand_ranked
from services.customer_ai.retrieve.hybrid import HybridHit, search_hybrid
from services.customer_ai.retrieve.lexical import search_cards
from services.customer_ai.retrieve.rerank import rerank_hits
from services.customer_ai.retrieve.products import cards_from_products, load_product_cards
from services.customer_ai.retrieve.validate import validate_evidence
from services.cm.version_store import PublishedVersionError, load_published_content


@dataclass(frozen=True)
class RetrieveContext:
    tenant_id: str
    query: str
    families: set[SourceFamily] | None = None
    cards: list[TitleCard] | None = None
    sections: dict | None = None
    revision: str = ""
    store: str = "published_snapshot"


def _cap() -> int:
    return DEFAULT_BUDGETS.evidence_chunks_before_expand


async def retrieve_cards(
    cards: list[TitleCard],
    query: str,
    *,
    families: set[SourceFamily] | None = None,
    sections: dict | None = None,
    revision: str = "",
    tenant_id: str = "",
) -> EvidenceBundle:
    scoped = [c for c in cards if families is None or c.source_family in families]
    if not scoped:
        return EvidenceBundle(outcome="not_found")
    if not voyage_configured():
        return EvidenceBundle(outcome="provider_not_configured")
    try:
        hits: list[HybridHit] = await search_hybrid(
            scoped, query, families=families, limit=_cap(), tenant_id=tenant_id
        )
        hits = await rerank_hits(query, hits, tenant_id=tenant_id)
    except VoyageNotConfiguredError:
        return EvidenceBundle(outcome="provider_not_configured")
    except VoyageContractError:
        return EvidenceBundle(outcome="provider_error")
    bundle = expand_ranked(hits, sections or {}, revision=revision, tenant_id=tenant_id)
    if not bundle.items:
        lexical = search_cards(scoped, query, families=families, limit=_cap())
        if lexical:
            bundle = expand_ranked(lexical, sections or {}, revision=revision, tenant_id=tenant_id)
            if bundle.items:
                return validate_evidence(bundle.model_copy(update={"outcome": "found"}), sections=sections or {})
        return EvidenceBundle(outcome="not_found")
    return validate_evidence(bundle, sections=sections or {})


async def retrieve_published(ctx: RetrieveContext) -> EvidenceBundle:
    if ctx.tenant_id:
        from services.customer_ai.search.product_freshness import product_questions_blocked

        fams = set(ctx.families) if ctx.families is not None else None
        blocked = product_questions_blocked(ctx.tenant_id, fams)
        if blocked:
            return EvidenceBundle(outcome="product_index_stale")
        from services.customer_ai.search.readiness import resolve_search_readiness

        status = resolve_search_readiness(ctx.tenant_id)
        if not status.ready:
            reason = (
                status.reason
                if status.reason in {"provider_not_configured", "index_not_ready"}
                else "index_not_ready"
            )
            return EvidenceBundle(outcome=reason)  # type: ignore[arg-type]
    sections = ctx.sections
    revision = ctx.revision
    cards = list(ctx.cards or [])
    if sections is None and ctx.tenant_id:
        try:
            pointer, loaded = load_published_content(ctx.tenant_id)
        except PublishedVersionError:
            return EvidenceBundle(outcome="source_unpublished")
        sections = loaded
        revision = revision or str(getattr(pointer, "revision", "") or "")
        cards.extend(load_published_cards(ctx.tenant_id))
        cards.extend(load_product_cards(ctx.tenant_id))
    elif not cards:
        cards.extend(load_published_cards(ctx.tenant_id) if ctx.tenant_id else [])
    return await retrieve_cards(
        cards,
        ctx.query,
        families=ctx.families,
        sections=sections or {},
        revision=revision,
        tenant_id=ctx.tenant_id,
    )


def attach_product_cards(cards: list[TitleCard], product_rows: list[object]) -> list[TitleCard]:
    return [*cards, *cards_from_products(product_rows)]
