"""FAQ question ANN: cosine ≥ 0.90 → published answer verbatim, zero generation.

Score is cosine similarity in [0, 1]. Postgres stores ``1 - (embedding <=> query)``
(pgvector cosine distance). The in-memory store uses the same cosine formula.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from services.ai_setup.constants import FAQ_EXACT_THRESHOLD
from services.brain.contracts.reply import FinalReplyEnvelope, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.faq_exact import faq_fast_path_safe, published_faq_entry
from services.brain.faq_freshness import faq_static_allowed
from services.brain.providers.spaces import ENTITY_DOCUMENT, ENTITY_QUERY
from services.brain.search.store import StoreHit, query_similar

FAQ_COSINE_MIN = float(FAQ_EXACT_THRESHOLD)
FAQ_TOP_K = 8
FAQ_EMBED_PATH = "faq_embed_90"


def _collapse_by_source(hits: list[StoreHit]) -> list[StoreHit]:
    best: dict[str, StoreHit] = {}
    for hit in hits:
        sid = (hit.source_id or "").strip()
        if not sid or hit.source_family != "faq":
            continue
        prior = best.get(sid)
        if prior is None or hit.score > prior.score:
            best[sid] = hit
    return sorted(best.values(), key=lambda row: (-row.score, row.source_id))


def pick_faq_embed_winner(hits: list[StoreHit]) -> tuple[str, StoreHit | None]:
    """Return (found|ambiguous|not_found, winner). Two FAQ ids ≥ 0.90 → ambiguous."""
    ranked = _collapse_by_source(hits)
    strong = [hit for hit in ranked if float(hit.score) >= FAQ_COSINE_MIN]
    if len(strong) >= 2:
        return "ambiguous", None
    if len(strong) == 1:
        return "found", strong[0]
    return "not_found", None


async def embed_faq_query(text: str) -> list[float] | None:
    from services.brain.flags import voyage_configured
    from services.brain.providers.voyage_client import embed_texts

    if not voyage_configured():
        return None
    try:
        out = await embed_texts(ENTITY_QUERY, [text])
    except Exception:
        return None
    if not out.vectors:
        return None
    return list(out.vectors[0])


def _hits_from_store(session: object | None, tenant_id: str, vector: list[float]) -> list[StoreHit]:
    result = query_similar(
        session,
        tenant_id=tenant_id,
        space_id=ENTITY_DOCUMENT.space_id,
        vector=vector,
        families={"faq"},
        limit=FAQ_TOP_K,
    )
    return list(result.items) if result.outcome == "found" else []


def query_faq_hits(tenant_id: str, vector: list[float]) -> list[StoreHit]:
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=True) as session:
            hits = _hits_from_store(session, tenant_id, vector)
            if hits:
                return hits
    except Exception:
        pass
    return _hits_from_store(None, tenant_id, vector)


async def faq_embed_result(
    turn: CustomerTurn,
    message: str,
    channel: str,
    *,
    apply_greeting: Callable[[CustomerTurn, str, str, FinalReplyEnvelope], FinalReplyEnvelope],
) -> TurnResult | None:
    if turn.invocation_kind == "followup" or not (message or "").strip():
        return None
    if not faq_fast_path_safe(message):
        return None
    vector = await embed_faq_query(message)
    if not vector:
        return None
    outcome, winner = pick_faq_embed_winner(query_faq_hits(turn.tenant_id, vector))
    if outcome != "found" or winner is None:
        return None
    entry = published_faq_entry(turn.tenant_id, winner.source_id)
    if not entry:
        return None
    answer = str(entry.get("answer") or "").strip()
    if not answer or not faq_static_allowed(answer, tenant_id=turn.tenant_id):
        return None
    from services.brain.faq_turn import faq_envelope

    extra: dict[str, Any] = {
        "path": FAQ_EMBED_PATH,
        "faq_id": winner.source_id,
        "response_class": "faq_only",
        "used_evidence_ids": [f"faq:{winner.source_id}"],
        "faq_cosine": round(float(winner.score), 4),
    }
    return faq_envelope(turn, message, channel, text=answer, extra=extra, apply_greeting=apply_greeting)
