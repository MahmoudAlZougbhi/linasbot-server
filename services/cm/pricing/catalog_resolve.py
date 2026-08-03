"""Map customer wording/aliases to tenant-owned catalog item IDs (deterministic)."""

from __future__ import annotations

from dataclasses import dataclass

from services.cm.pricing.schemas import CatalogItem


@dataclass(frozen=True)
class CatalogMatch:
    catalog_item_id: str
    score: int
    matched_alias: str


def resolve_catalog_item_ids(
    message: str,
    catalog: list[CatalogItem],
    *,
    active_only: bool = True,
) -> list[CatalogMatch]:
    """Return ranked matches. Empty list => unknown; multiple high scores => ambiguous."""
    text = (message or "").strip().lower()
    if not text:
        return []
    matches: list[CatalogMatch] = []
    for item in catalog:
        if active_only and not item.active:
            continue
        candidates = [
            item.id,
            item.labels.en,
            item.labels.ar,
            item.labels.fr,
            item.labels.franco,
            *item.aliases,
        ]
        best_alias = ""
        best_score = 0
        for raw in candidates:
            alias = (raw or "").strip().lower()
            if not alias:
                continue
            if alias == text:
                score = 100
            elif alias in text or text in alias:
                score = 70 + min(len(alias), 20)
            else:
                continue
            if score > best_score:
                best_score = score
                best_alias = alias
        if best_score:
            matches.append(CatalogMatch(catalog_item_id=item.id, score=best_score, matched_alias=best_alias))
    matches.sort(key=lambda m: (-m.score, m.catalog_item_id))
    # Dedupe by item id keeping best
    seen: set[str] = set()
    unique: list[CatalogMatch] = []
    for match in matches:
        if match.catalog_item_id in seen:
            continue
        seen.add(match.catalog_item_id)
        unique.append(match)
    return unique


def disambiguate_matches(matches: list[CatalogMatch], *, min_score: int = 70) -> tuple[str | None, list[str]]:
    """Return (single_id|None, ambiguous_ids)."""
    strong = [m for m in matches if m.score >= min_score]
    if not strong:
        return None, []
    top = strong[0].score
    tied = [m for m in strong if m.score == top]
    if len(tied) == 1:
        return tied[0].catalog_item_id, []
    return None, [m.catalog_item_id for m in tied]
