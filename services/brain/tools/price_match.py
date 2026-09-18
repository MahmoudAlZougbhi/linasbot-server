"""Ranked structured price lookup. A generic token is never sufficient evidence."""

from __future__ import annotations

from typing import Any

from services.brain.entity_identity import canonical_id, is_bundle_name, score_label
from services.brain.normalize import normalize_search_text

MIN_PRICE_SCORE = 36.0


def _aliases(row: dict[str, Any]) -> list[str]:
    raw = row.get("aliases") or []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _title(row: dict[str, Any]) -> str:
    labels = row.get("labels")
    if isinstance(labels, dict):
        for key in ("en", "ar", "fr", "franco"):
            value = str(labels.get(key) or "").strip()
            if value:
                return value
    return str(row.get("title") or row.get("name") or row.get("id") or "").strip()


def score_catalog_row(query: str, row: dict[str, Any]) -> float:
    title = _title(row)
    aliases = _aliases(row)
    category = str(row.get("category") or row.get("category_id") or "")
    score = score_label(query, title, aliases=aliases)
    if category:
        cat_score = score_label(query, category)
        if cat_score >= 70:
            score = max(score, min(58.0, cat_score - 20))
    return score


def rank_price_rows(
    query: str,
    rows: list[dict[str, Any]],
    *,
    service_id: str = "",
    limit: int = 5,
) -> list[tuple[float, dict[str, Any]]]:
    wanted = canonical_id(service_id)
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        rid = canonical_id(row.get("id"), row.get("catalog_item_id"), row.get("service_id"))
        if wanted and rid in {wanted, f"services:{wanted}"} or (wanted and rid.endswith(f":{wanted}")):
            scored.append((100.0, row))
            continue
        score = score_catalog_row(query, row)
        if score >= MIN_PRICE_SCORE:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], _title(item[1]), canonical_id(item[1].get("id"))))
    if not scored:
        return []
    best = scored[0][0]
    # Keep near-ties so Terra can clarify; drop weak extra rows.
    kept = [(score, row) for score, row in scored if score >= max(MIN_PRICE_SCORE, best - 18.0)]
    standalone_hits = [(score, row) for score, row in kept if not is_bundle_name(_title(row))]
    if standalone_hits and score_label(query, _title(standalone_hits[0][1])) >= MIN_PRICE_SCORE:
        best_stand = standalone_hits[0][0]
        if best_stand + 8.0 >= best:
            kept = [(score, row) for score, row in kept if not is_bundle_name(_title(row)) or score >= best_stand + 12]
    return kept[:limit]


def query_is_generic(query: str) -> bool:
    tokens = [tok for tok in normalize_search_text(query).split() if tok]
    distinctive = [tok for tok in tokens if tok not in {"price", "cost", "how", "much", "service", "laser", "hair"}]
    return len(distinctive) == 0
