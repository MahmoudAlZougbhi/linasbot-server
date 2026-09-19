"""Price claims must match a resolved entity amount, not any number in the corpus."""

from __future__ import annotations

import re
from typing import Any

from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.plan import PlannerPlan
from services.brain.entity_identity import prefer_standalone, score_label
from services.brain.grounding import extract

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_BARE_AMOUNT = re.compile(r"(?<![\w:])(\d+(?:[.,]\d+)?)(?![\w:])")


def is_price_context(message: str, plan: PlannerPlan | None = None) -> bool:
    """Planner/evidence flags only — not a price-keyword intent regex."""
    _ = message
    if plan is None:
        return False
    families = {fam for task in plan.tasks for fam in (task.source_families or [])}
    return "prices" in families


def _latin_digits(text: str) -> str:
    return (text or "").translate(_ARABIC_DIGITS)


def reply_price_numbers(text: str, *, price_context: bool) -> set[str]:
    body = _latin_digits(text)
    tagged = {item.split("|", 1)[0] for item in extract.amounts(body)}
    if not price_context:
        return tagged
    clocks = extract.clock_surfaces(body)
    found = set(tagged)
    for match in _BARE_AMOUNT.finditer(body):
        raw = extract._number(match.group(1))  # noqa: SLF001
        if raw in clocks or any(raw in variant for variant in clocks):
            continue
        if len(raw) >= 4 and raw.isdigit():
            continue
        found.add(raw)
    return found


def _item_amounts(item: EvidenceItem) -> set[str]:
    body = _latin_digits(f"{item.title}\n{item.text}")
    tagged = extract.amounts(body)
    numbers = {item_amt.split("|", 1)[0] for item_amt in tagged}
    extra_amount = item.extra.get("amount") if isinstance(item.extra, dict) else None
    if extra_amount is not None:
        numbers.add(extract._number(str(extra_amount)))  # noqa: SLF001
    return numbers


def _item_row(item: EvidenceItem) -> dict[str, Any]:
    extra = item.extra if isinstance(item.extra, dict) else {}
    aliases = extra.get("aliases") or []
    if not isinstance(aliases, (list, tuple)):
        aliases = []
    return {
        "id": str(extra.get("entity_id") or item.source_id),
        "title": item.title,
        "name": item.title,
        "aliases": [str(alias) for alias in aliases],
    }


def resolved_price_item(message: str, bundle: EvidenceBundle) -> EvidenceItem | None:
    rows = [_item_row(item) for item in bundle.items]
    winner = prefer_standalone(message, rows)
    if winner is None:
        return None
    wanted = str(winner.get("id") or "")
    for item in bundle.items:
        extra = item.extra if isinstance(item.extra, dict) else {}
        if str(extra.get("entity_id") or item.source_id) == wanted:
            return item
        if score_label(message, item.title) >= 70 and item is not None:
            if str(item.source_id) == wanted:
                return item
    return next((item for item in bundle.items if str(item.source_id) == wanted), None)


def ungrounded_price_claims(
    reply_text: str,
    bundle: EvidenceBundle,
    *,
    message: str = "",
    plan: PlannerPlan | None = None,
    receipts: list[str] | None = None,
) -> list[str]:
    price_context = is_price_context(message, plan)
    claimed = reply_price_numbers(reply_text, price_context=price_context)
    if not claimed:
        return []
    allowed: set[str] = set()
    for item in bundle.items:
        allowed |= _item_amounts(item)
    for line in receipts or []:
        allowed |= {part.split("|", 1)[0] for part in extract.amounts(_latin_digits(line))}
        for match in _BARE_AMOUNT.finditer(_latin_digits(line)):
            if "fact:price:" in line or "price" in line.casefold() or "usd" in line.casefold():
                allowed.add(extract._number(match.group(1)))  # noqa: SLF001
    preferred = resolved_price_item(message, bundle) if price_context else None
    if preferred is not None:
        preferred_amounts = _item_amounts(preferred)
        reply_mentions_other = any(
            score_label(reply_text, item.title) >= 70 and item.source_id != preferred.source_id for item in bundle.items
        )
        if preferred_amounts and not reply_mentions_other:
            allowed = preferred_amounts
    tagged = extract.amounts(_latin_digits(reply_text))
    tagged_by_num = {item.split("|", 1)[0]: item for item in tagged}
    if not price_context:
        corpus = extract.amounts(_latin_digits("\n".join(item.text for item in bundle.items)))
        return [f"amount:{claim}" for claim in sorted(tagged - corpus)]
    return [f"amount:{tagged_by_num.get(claim, claim)}" for claim in sorted(claimed - allowed)]
