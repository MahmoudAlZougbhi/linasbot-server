"""Deterministic tenant-scoped pricing engine (no LLM, no eval, no business-specific branches)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.cm.pricing.schemas import (
    ActionKind,
    AppliedRule,
    AudienceScope,
    CatalogItem,
    DiscountRule,
    PriceEntry,
    PriceQuote,
    PricingContext,
    QuoteLine,
    QuoteRequestLine,
    RoundingPolicy,
    RuleCondition,
    RuleConditionGroup,
)


def _parse_now(now_iso: str | None) -> datetime:
    if not now_iso:
        return datetime.now(UTC)
    text = now_iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _in_effective(window_start: str | None, window_end: str | None, now: datetime) -> bool:
    if window_start:
        start = _parse_now(window_start)
        if now < start:
            return False
    if window_end:
        end = _parse_now(window_end)
        if now > end:
            return False
    return True


def _round_amount(value: float, policy: RoundingPolicy) -> float:
    from services.cm.pricing.money import as_money, money_to_float, quantize_money

    return money_to_float(quantize_money(as_money(value), policy))


def _audience_matches(scope: AudienceScope, context_audience: AudienceScope) -> bool:
    if scope in {"any", "general"}:
        return True
    if context_audience in {"any", "general"}:
        return True
    return scope == context_audience


def select_price_entry(
    *,
    entries: list[PriceEntry],
    item: CatalogItem,
    variant_id: str | None,
    quantity: float,
    context: PricingContext,
    now: datetime,
) -> PriceEntry | None:
    candidates: list[tuple[int, PriceEntry]] = []
    for entry in entries:
        if not entry.active or entry.catalog_item_id != item.id:
            continue
        if entry.variant_id and entry.variant_id != variant_id:
            continue
        if variant_id and entry.variant_id and entry.variant_id != variant_id:
            continue
        if entry.branch_id and context.branch_id and entry.branch_id != context.branch_id:
            continue
        if entry.branch_id and not context.branch_id:
            continue
        if not _audience_matches(entry.audience, context.audience):
            continue
        if entry.min_quantity is not None and quantity < entry.min_quantity:
            continue
        if entry.max_quantity is not None and quantity > entry.max_quantity:
            continue
        if not _in_effective(entry.effective.start, entry.effective.end, now):
            continue
        score = 0
        if entry.variant_id and entry.variant_id == variant_id:
            score += 4
        if entry.branch_id and entry.branch_id == context.branch_id:
            score += 2
        if entry.audience not in {"any", "general"}:
            score += 1
        candidates.append((score, entry))
    if candidates:
        candidates.sort(key=lambda pair: (-pair[0], pair[1].id))
        return candidates[0][1]
    if item.base_price is None:
        return None
    # Synthetic entry from catalog base_price (still structured, not invented by engine).
    return PriceEntry(
        id=f"base:{item.id}",
        catalog_item_id=item.id,
        variant_id=variant_id,
        amount=float(item.base_price),
        currency=item.currency,
        audience=item.audience if item.audience != "any" else "any",
        unit=item.unit,
        provenance=item.provenance,
    )


def _item_eligible_for_rule(item: CatalogItem, rule: DiscountRule) -> bool:
    if item.id in rule.excluded_item_ids:
        return False
    if any(cid in rule.excluded_category_ids for cid in item.category_ids):
        return False
    if rule.eligible_item_ids and item.id not in rule.eligible_item_ids:
        return False
    if rule.eligible_category_ids and not any(cid in rule.eligible_category_ids for cid in item.category_ids):
        return False
    return item.discount_eligible


def _eval_condition_for_rule(
    cond: RuleCondition,
    *,
    rule: DiscountRule,
    lines: list[QuoteLine],
    items_by_id: dict[str, CatalogItem],
    subtotal: float,
    context: PricingContext,
    now: datetime,
) -> bool:
    eligible = [ln for ln in lines if _item_eligible_for_rule(items_by_id[ln.catalog_item_id], rule)]
    kind = cond.kind
    if kind == "subtotal_at_least":
        return subtotal >= float(cond.amount or 0)
    if kind == "eligible_item_count_at_least":
        return len({ln.catalog_item_id for ln in eligible}) >= int(cond.count or 0)
    if kind == "eligible_quantity_at_least":
        return sum(ln.quantity for ln in eligible) >= float(cond.count or cond.amount or 0)
    if kind == "category_count_at_least":
        cats: set[str] = set()
        for ln in eligible:
            cats.update(items_by_id[ln.catalog_item_id].category_ids)
        if cond.category_ids:
            cats &= set(cond.category_ids)
        return len(cats) >= int(cond.count or 0)
    if kind == "includes_items":
        have = {ln.catalog_item_id for ln in lines}
        return all(i in have for i in cond.item_ids)
    if kind == "excludes_items":
        have = {ln.catalog_item_id for ln in lines}
        return all(i not in have for i in cond.item_ids)
    if kind == "includes_categories":
        have_cats: set[str] = set()
        for ln in lines:
            have_cats.update(items_by_id[ln.catalog_item_id].category_ids)
        return all(c in have_cats for c in cond.category_ids)
    if kind == "excludes_categories":
        have_cats = set()
        for ln in lines:
            have_cats.update(items_by_id[ln.catalog_item_id].category_ids)
        return all(c not in have_cats for c in cond.category_ids)
    if kind == "branch_in":
        if not context.branch_id:
            return False
        return context.branch_id in cond.branch_ids
    if kind == "audience_in":
        return context.audience in cond.audiences or "any" in cond.audiences
    if kind == "effective_now":
        return _in_effective(rule.effective.start, rule.effective.end, now)
    return False


def _eval_group(
    group: RuleConditionGroup,
    *,
    rule: DiscountRule,
    lines: list[QuoteLine],
    items_by_id: dict[str, CatalogItem],
    subtotal: float,
    context: PricingContext,
    now: datetime,
) -> bool:
    parts: list[bool] = [
        _eval_condition_for_rule(
            c,
            rule=rule,
            lines=lines,
            items_by_id=items_by_id,
            subtotal=subtotal,
            context=context,
            now=now,
        )
        for c in group.conditions
    ]
    parts.extend(
        _eval_group(
            g,
            rule=rule,
            lines=lines,
            items_by_id=items_by_id,
            subtotal=subtotal,
            context=context,
            now=now,
        )
        for g in group.groups
    )
    if not parts:
        return True
    if group.op == "or":
        return any(parts)
    return all(parts)


def _apply_action(
    action_kind: ActionKind,
    *,
    percent: float | None,
    amount: float | None,
    subtotal: float,
    rounding: RoundingPolicy,
    min_discount: float | None,
    max_discount: float | None,
) -> float:
    if action_kind == "percent_off":
        discount = subtotal * (float(percent or 0) / 100.0)
    elif action_kind == "fixed_amount_off":
        discount = float(amount or 0)
    elif action_kind in {"fixed_final_total", "bundle_price"}:
        target = float(amount or 0)
        discount = max(0.0, subtotal - target)
    else:
        discount = 0.0
    discount = min(discount, subtotal)
    if min_discount is not None:
        discount = max(discount, min_discount)
    if max_discount is not None:
        discount = min(discount, max_discount)
    return _round_amount(discount, rounding)


def compute_quote(
    *,
    catalog_items: list[CatalogItem],
    price_entries: list[PriceEntry],
    discount_rules: list[DiscountRule],
    request_lines: list[QuoteRequestLine],
    context: PricingContext,
) -> PriceQuote:
    """Pure deterministic quote. Raises ValueError on missing catalog/price (honest failure)."""
    now = _parse_now(context.now_iso)
    items_by_id = {item.id: item for item in catalog_items if item.active}
    lines: list[QuoteLine] = []
    currency = context.currency

    for req in request_lines:
        item = items_by_id.get(req.catalog_item_id)
        if item is None:
            raise ValueError(f"unknown_or_inactive_catalog_item:{req.catalog_item_id}")
        if item.branch_ids and context.branch_id and context.branch_id not in item.branch_ids:
            raise ValueError(f"catalog_item_not_available_at_branch:{item.id}")
        if not _in_effective(item.effective.start, item.effective.end, now):
            raise ValueError(f"catalog_item_not_effective:{item.id}")
        entry = select_price_entry(
            entries=price_entries,
            item=item,
            variant_id=req.variant_id,
            quantity=req.quantity,
            context=context,
            now=now,
        )
        if entry is None:
            raise ValueError(f"no_price_for_catalog_item:{item.id}")
        if currency is None:
            currency = entry.currency
        if entry.currency != currency:
            raise ValueError(f"currency_mismatch:{entry.currency}!={currency}")
        unit = float(entry.amount)
        line_subtotal = _round_amount(unit * float(req.quantity), "nearest_0_01")
        label = item.labels.en or item.labels.ar or item.id
        lines.append(
            QuoteLine(
                catalog_item_id=item.id,
                variant_id=req.variant_id,
                quantity=float(req.quantity),
                unit_amount=unit,
                line_subtotal=line_subtotal,
                currency=entry.currency,
                price_entry_id=entry.id,
                label=label,
            )
        )

    if not lines:
        raise ValueError("empty_quote")
    assert currency is not None
    subtotal = _round_amount(sum(ln.line_subtotal for ln in lines), "nearest_0_01")

    active_rules = [
        rule
        for rule in discount_rules
        if rule.active and rule.currency == currency and _in_effective(rule.effective.start, rule.effective.end, now)
    ]
    active_rules.sort(key=lambda r: (r.priority, r.id))

    matching: list[DiscountRule] = []
    for rule in active_rules:
        if _eval_group(
            rule.when,
            rule=rule,
            lines=lines,
            items_by_id=items_by_id,
            subtotal=subtotal,
            context=context,
            now=now,
        ):
            matching.append(rule)

    applied: list[AppliedRule] = []
    discount_total = 0.0
    if matching:
        exclusive = [r for r in matching if r.exclusive or r.stacking == "exclusive"]
        stackable = [r for r in matching if r.stacking == "stack" and not r.exclusive]
        best_of = [r for r in matching if r.stacking == "best_of"]

        chosen: list[DiscountRule] = []
        if exclusive:
            chosen.append(exclusive[0])
        elif best_of:
            # Evaluate each and keep max discount
            scored: list[tuple[float, DiscountRule]] = []
            for rule in best_of:
                d = _apply_action(
                    rule.then.kind,
                    percent=rule.then.percent,
                    amount=rule.then.amount,
                    subtotal=subtotal,
                    rounding=rule.rounding,
                    min_discount=rule.min_discount,
                    max_discount=rule.max_discount,
                )
                scored.append((d, rule))
            scored.sort(key=lambda p: (-p[0], p[1].priority, p[1].id))
            chosen.append(scored[0][1])
        else:
            chosen.extend(stackable or matching[:1])

        running_subtotal = subtotal
        for rule in chosen:
            d = _apply_action(
                rule.then.kind,
                percent=rule.then.percent,
                amount=rule.then.amount,
                subtotal=running_subtotal if rule.stacking == "stack" else subtotal,
                rounding=rule.rounding,
                min_discount=rule.min_discount,
                max_discount=rule.max_discount,
            )
            applied.append(
                AppliedRule(
                    rule_id=rule.id,
                    label=rule.labels.en or rule.labels.ar or rule.id,
                    action_kind=rule.then.kind,
                    discount_amount=d,
                )
            )
            discount_total += d
            if rule.stacking == "stack":
                running_subtotal = max(0.0, running_subtotal - d)

    discount_total = _round_amount(min(discount_total, subtotal), "nearest_0_01")
    final_total = _round_amount(subtotal - discount_total, "nearest_0_01")
    return PriceQuote(
        tenant_id=context.tenant_id,
        currency=currency,
        lines=lines,
        subtotal=subtotal,
        matching_rule_ids=[r.id for r in matching],
        applied_rules=applied,
        discount_amount=discount_total,
        final_total=final_total,
        content_version_id=context.content_version_id,
        provenance={
            "engine": "services.cm.pricing.engine.compute_quote",
            "catalog_item_count": len(items_by_id),
            "price_entry_count": len(price_entries),
            "rule_count": len(discount_rules),
        },
    )


def quote_to_answer_facts(quote: PriceQuote) -> list[dict[str, Any]]:
    """Serialize quote into AnswerFact-compatible dicts for the packet/validator."""
    facts: list[dict[str, Any]] = [
        {
            "kind": "price",
            "value": f"{quote.final_total} {quote.currency}",
            "source_id": f"quote:final:{quote.content_version_id or 'draft'}",
        },
        {
            "kind": "price",
            "value": f"{quote.subtotal} {quote.currency}",
            "source_id": f"quote:subtotal:{quote.content_version_id or 'draft'}",
        },
    ]
    for line in quote.lines:
        facts.append(
            {
                "kind": "price",
                "value": f"{line.line_subtotal} {line.currency}",
                "source_id": f"quote:line:{line.catalog_item_id}:{line.price_entry_id or 'base'}",
            }
        )
    if quote.discount_amount:
        facts.append(
            {
                "kind": "price",
                "value": f"{quote.discount_amount} {quote.currency}",
                "source_id": f"quote:discount:{','.join(a.rule_id for a in quote.applied_rules) or 'none'}",
            }
        )
    return facts
