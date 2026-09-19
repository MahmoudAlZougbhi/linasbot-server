"""Thin Owner Copilot adapter over the canonical message ledger.

No private Copilot balance. Billing owns bands, reservations, and settlement.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from services.billing import credit_ai_gate as credit_ai_gate
from services.billing.membership.economy_policy import copilot_requires_confirm, copilot_units_for_cost
from services.billing.membership.message_ledger import InsufficientMessages, reserve, settle


@dataclass
class OwnerTurnHold:
    tenant_id: str
    reservation_id: str | None = None
    operation_id: str = ""
    units: int = 1
    blocked: bool = False
    confirm_required: bool = False
    _finalized: bool = field(default=False, repr=False)


def estimate_copilot_cost_usd(
    *,
    user_text: str = "",
    history_tokens: int = 0,
    attachment_count: int = 0,
) -> float:
    from services.brain.model_pricing import compute_cost_from_usage
    from services.owner_copilot.flags import owner_model_name

    prompt = max(1, (len(user_text or "") // 4) + max(0, int(history_tokens)))
    prompt += max(0, int(attachment_count)) * 1200
    completion_guess = min(1800, max(200, prompt // 2))
    priced = compute_cost_from_usage(owner_model_name(), prompt, completion_guess)
    return float(priced["cost_usd"])


def estimate_copilot_units(estimated_usd: float | None = None) -> int:
    return copilot_units_for_cost(estimated_usd)


def copilot_operation_id(
    *,
    tenant_id: str,
    conversation_id: str,
    user_text: str,
    confirm_tool: str | None = None,
    choice_id: str | None = None,
    attachment_ids: list[str] | None = None,
) -> str:
    payload = {
        "t": (tenant_id or "").strip().lower(),
        "c": (conversation_id or "").strip(),
        "u": (user_text or "").strip(),
        "tool": confirm_tool or "",
        "choice": choice_id or "",
        "att": list(attachment_ids or []),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:32]
    return f"owner:{digest}"


def confirm_copy(*, units: int, language: str = "en") -> str:
    lang = (language or "en").strip().lower()[:2]
    n = max(1, int(units))
    if lang == "ar":
        return f"هالإجراء رح يستخدم {n} رسائل."
    if lang == "fr":
        return f"Cette action utilisera {n} messages."
    return f"This action will use {n} messages."


def owner_turn_hold_begin(
    tenant_id: str,
    *,
    conversation_id: str = "",
    user_text: str = "",
    confirm_tool: str | None = None,
    choice_id: str | None = None,
    attachment_ids: list[str] | None = None,
    estimated_usd: float | None = None,
    confirm_billing: bool = False,
) -> OwnerTurnHold:
    tid = (tenant_id or "").strip().lower()
    units = estimate_copilot_units(estimated_usd)
    if not tid or credit_ai_gate.ai_generation_blocked(tid, need=units):
        return OwnerTurnHold(tenant_id=tid, blocked=True, units=units)
    if copilot_requires_confirm(units) and not confirm_billing:
        return OwnerTurnHold(tenant_id=tid, confirm_required=True, units=units)
    op = copilot_operation_id(
        tenant_id=tid,
        conversation_id=conversation_id,
        user_text=user_text,
        confirm_tool=confirm_tool,
        choice_id=choice_id,
        attachment_ids=attachment_ids,
    )
    try:
        reservation = None
        for attempt in range(8):
            key = op if attempt == 0 else f"{op}:{attempt}"
            reservation = reserve(
                tenant_id=tid,
                operation_id=key,
                response_class="generated_ai",
                units=units,
            )
            if reservation.status == "settled":
                return OwnerTurnHold(
                    tenant_id=tid,
                    reservation_id=reservation.reservation_id,
                    operation_id=key,
                    units=units,
                    _finalized=True,
                )
            if reservation.status in {"reserved", "not_required"}:
                op = key
                break
        else:
            return OwnerTurnHold(tenant_id=tid, blocked=True, units=units)
        return OwnerTurnHold(
            tenant_id=tid,
            reservation_id=reservation.reservation_id,
            operation_id=op,
            units=units,
        )
    except (InsufficientMessages, PermissionError, ValueError):
        return OwnerTurnHold(tenant_id=tid, blocked=True, units=units)


def owner_turn_hold_finalize(hold: OwnerTurnHold) -> None:
    if hold._finalized or not hold.operation_id:
        return
    try:
        settle(tenant_id=hold.tenant_id, operation_id=hold.operation_id, accepted=True)
        hold._finalized = True
    except Exception:
        owner_turn_hold_abort(hold)
        raise
    finally:
        hold.reservation_id = None


def owner_turn_hold_abort(hold: OwnerTurnHold) -> None:
    if hold._finalized or not hold.operation_id:
        return
    try:
        settle(tenant_id=hold.tenant_id, operation_id=hold.operation_id, accepted=False)
    except Exception:
        pass
    finally:
        hold.reservation_id = None
        hold.operation_id = ""


def owner_turn_hold_on_event(hold: OwnerTurnHold, event_type: str) -> None:
    if event_type == "done":
        owner_turn_hold_finalize(hold)
    elif event_type in {"cancelled", "error"}:
        owner_turn_hold_abort(hold)
