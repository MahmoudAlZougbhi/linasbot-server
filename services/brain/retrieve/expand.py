"""Hydrate canonical text for winning IDs only. No media bytes."""

from __future__ import annotations

from typing import Any

from services.ai_setup.version_store import PublishedVersionError, load_published_content
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.retrieve.lexical import LexicalHit


def _rows(sections: dict[str, Any], family: str) -> list[dict[str, Any]]:
    if family == "hours":
        payload = sections.get("opening_hours")
        opening = payload.get("items") if isinstance(payload, dict) else None
        hours = [row for row in opening or [] if isinstance(row, dict)]
        branches = sections.get("branches")
        branch_items = branches.get("items") if isinstance(branches, dict) else None
        branch_rows = [row for row in branch_items or [] if isinstance(row, dict)]
        off_payload = sections.get("off_days")
        off_rows: list[dict[str, Any]] = [{"id": "off_days", **off_payload}] if isinstance(off_payload, dict) else []
        # Branch weekly_schedule is the hours SoT. Opening-hours rows must not
        # hide branch ids like hours:antelias at hydrate time.
        return [*hours, *branch_rows, *off_rows]
    if family in {"prices", "services"}:
        payload = sections.get("prices")
        catalog = payload.get("catalog") if isinstance(payload, dict) else None
        if isinstance(catalog, list) and catalog:
            return [r for r in catalog if isinstance(r, dict)]
        return []
    payload = sections.get(family)
    rows = payload.get("items") if isinstance(payload, dict) else None
    return [r for r in rows or [] if isinstance(r, dict)]


def _row_id(raw: dict[str, Any]) -> str:
    return str(raw.get("id") or raw.get("qa_group_id") or "").strip()


def _hours_name_blob(raw: dict[str, Any]) -> str:
    labels = raw.get("labels")
    label_bits: list[str] = []
    if isinstance(labels, dict):
        label_bits.extend(str(value or "") for value in labels.values())
    aliases = raw.get("aliases")
    alias_bits = [str(item or "") for item in aliases] if isinstance(aliases, list) else []
    return " ".join(
        [
            _row_id(raw),
            str(raw.get("branch_id") or ""),
            str(raw.get("title") or raw.get("name") or ""),
            *label_bits,
            *alias_bits,
        ]
    ).casefold()


def _hours_row_matches(row: dict[str, Any], source_id: str) -> bool:
    sid = source_id.casefold()
    rid = _row_id(row).casefold()
    branch_id = str(row.get("branch_id") or "").strip().casefold()
    if rid == sid or branch_id == sid or rid.endswith(f":{sid}"):
        return True
    return sid in _hours_name_blob(row)


def _select_hours_row(sections: dict[str, Any], source_id: str) -> dict[str, Any] | None:
    """Prefer the published hours/branch row that actually contains clocks."""
    from services.brain.retrieve.schedule_text import schedule_lines

    sid = (source_id or "").strip()
    if not sid:
        return None
    candidates = [row for row in _rows(sections, "hours") if _hours_row_matches(row, sid)]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (
            len(schedule_lines(row)),
            int(_row_id(row).casefold() == sid.casefold()),
        ),
    )


def _label(labels: Any) -> str:
    if isinstance(labels, dict):
        for key in ("en", "ar", "fr", "franco"):
            value = str(labels.get(key) or "").strip()
            if value:
                return value
    return ""


def _price_lines(sections: dict[str, Any], catalog_item_id: str) -> list[str]:
    from services.brain.retrieve.price_text import price_evidence_lines

    return price_evidence_lines(sections, catalog_item_id)


def _schedule_lines(raw: dict[str, Any]) -> list[str]:
    from services.brain.retrieve.schedule_text import schedule_lines

    return schedule_lines(raw)


def _text_card(family: str, raw: dict[str, Any], *, sections: dict[str, Any], tenant_id: str = "") -> str:
    parts = [
        str(raw.get("title") or raw.get("name") or _label(raw.get("labels")) or ""),
        str(raw.get("description") or raw.get("body") or raw.get("notes") or ""),
        str(raw.get("ai_search_description") or ""),
    ]
    if family in {"services", "prices"}:
        if raw.get("base_price") is not None:
            parts.append(f"{raw.get('base_price')} {raw.get('currency') or ''}".strip())
        parts.extend(_price_lines(sections, str(raw.get("id") or "")))
    if family == "faq":
        for variant in raw.get("variants") or []:
            if isinstance(variant, dict):
                parts.append(str(variant.get("answer") or ""))
    if family == "branches":
        parts.append(str(raw.get("address") or raw.get("maps_url") or ""))
    if family in {"branches", "hours"}:
        tz = str(raw.get("timezone") or raw.get("tz") or "").strip()
        if tz:
            parts.append(f"timezone {tz}")
        if family == "hours" and _row_id(raw) == "off_days":
            from services.brain.retrieve.schedule_text import off_days_search_blob

            parts.append(off_days_search_blob(raw))
        else:
            parts.extend(_schedule_lines(raw))
    if family in {"branches", "hours", "services"}:
        attachments = raw.get("attachments") or []
        if attachments:
            from services.ai_setup.article_media import format_attachments_block

            block = format_attachments_block(list(attachments), tenant_id=tenant_id)
            if block:
                parts.append(block)
    return "\n".join(p.strip() for p in parts if str(p).strip())


def expand_ranked(
    ranked: list[Any],
    sections: dict[str, Any],
    *,
    revision: str = "",
    tenant_id: str = "",
) -> EvidenceBundle:
    hits: list[LexicalHit] = []
    for item in ranked:
        card = getattr(item, "card", None)
        if card is None:
            continue
        score = float(getattr(item, "lexical_score", 0.0) or getattr(item, "score", 0.0) or 0.0)
        hits.append(LexicalHit(card=card, score=score))
    return expand_hits(hits, sections, revision=revision, tenant_id=tenant_id)


def expand_hits(
    hits: list[LexicalHit],
    sections: dict[str, Any],
    *,
    revision: str = "",
    tenant_id: str = "",
) -> EvidenceBundle:
    items: list[EvidenceItem] = []
    for hit in hits:
        card = hit.card
        _, _, source_id = card.item_id.partition(":")
        family = card.source_family
        if family == "products":
            from services.brain.retrieve.products import evidence_from_product, load_product_evidence

            match = next((row for row in _rows(sections, family) if _row_id(row) == source_id), None)
            if match is not None:
                product_item = evidence_from_product(match)
            else:
                product_item = load_product_evidence(tenant_id, source_id)
            if product_item is None:
                continue
            items.append(
                product_item.model_copy(
                    update={
                        "revision": revision or product_item.revision or card.revision,
                        "extra": {**(product_item.extra or {}), "lexical_score": hit.score},
                    }
                )
            )
            continue
        match = (
            _select_hours_row(sections, source_id)
            if family == "hours"
            else next((row for row in _rows(sections, family) if _row_id(row) == source_id), None)
        )
        if match is None:
            continue
        if family == "knowledge" and (card.body or "").strip():
            chunk = card.body.strip()
            full = _text_card(family, match, sections=sections, tenant_id=tenant_id)
            # Prefer indexed winning chunk when shorter than (or equal to) the full article.
            text = chunk if (not full or len(chunk) <= len(full)) else full
        else:
            text = _text_card(family, match, sections=sections, tenant_id=tenant_id)
        if family in {"hours", "branches"} and not _schedule_lines(match):
            sibling = _select_hours_row(sections, source_id)
            extra_clocks = _schedule_lines(sibling) if sibling is not None else []
            if extra_clocks:
                text = "\n".join(part for part in [text, *extra_clocks] if str(part).strip())
        if not text:
            continue
        extra = {
            "lexical_score": hit.score,
            "entity_id": source_id,
            "entity_type": family,
            "tenant_id": tenant_id,
            "bundle": "+" in card.title or " and " in card.title.casefold(),
            "aliases": list(card.aliases),
        }
        items.append(
            EvidenceItem(
                evidence_id=card.item_id,
                source_family=family,
                source_id=source_id,
                revision=revision or card.revision,
                title=card.title,
                text=text,
                extra=extra,
            )
        )
    outcome = "found" if items else "not_found"
    return EvidenceBundle(items=items, outcome=outcome)  # type: ignore[arg-type]


def expand_published(tenant_id: str, hits: list[LexicalHit]) -> EvidenceBundle:
    try:
        pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return EvidenceBundle(outcome="source_unpublished")
    revision = str(getattr(pointer, "revision", "") or "")
    return expand_hits(hits, sections, revision=revision, tenant_id=tenant_id)
