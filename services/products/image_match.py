"""Match an inbound image to catalog product ids via the save-time fingerprint index.

Phase 1: pHash / sha256 / histogram (image_index). Voyage multimodal is flag-off.
"""

from __future__ import annotations

from typing import Any

from services.brain.flags import env_flag
from services.products.image_index import SIMILARITY_THRESHOLD, TOP_K_DEFAULT, find_image_candidates


def voyage_multimodal_search_enabled() -> bool:
    """Phase 2 only. Default OFF — do not query Voyage image embeddings at runtime."""
    return env_flag("LINAS_PRODUCT_MULTIMODAL_SEARCH", default=False)


def match_product_image(
    tenant_id: str,
    query_bytes: bytes,
    *,
    top_k: int = TOP_K_DEFAULT,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """Return ranked product candidates. ``high_confidence`` follows the live threshold."""
    tid = (tenant_id or "").strip()
    if not tid or not query_bytes:
        return []
    threshold = float(min_score) if min_score is not None else SIMILARITY_THRESHOLD
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    except Exception:
        return []
    try:
        with whatsapp_session(require=True) as session:
            raw = find_image_candidates(
                session,
                tenant_id=tid,
                query_bytes=query_bytes,
                top_k=top_k,
                similarity_threshold=threshold,
            )
    except WhatsAppDatabaseUnavailable:
        return []
    except Exception:
        return []
    high_cut = SIMILARITY_THRESHOLD
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw:
        pid = str(row.get("product_id") or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        score = float(row.get("similarity") or 0.0)
        out.append(
            {
                "product_id": pid,
                "score": score,
                "high_confidence": score >= high_cut,
                "media_id": str(row.get("media_id") or ""),
            }
        )
    return out


def high_confidence_matches(
    tenant_id: str,
    query_bytes: bytes,
    *,
    top_k: int = TOP_K_DEFAULT,
) -> list[dict[str, Any]]:
    return [row for row in match_product_image(tenant_id, query_bytes, top_k=top_k) if row.get("high_confidence")]
