"""Reserve / settle Owner Copilot turns on the message ledger."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from services.billing.credit_ai_gate import ai_generation_blocked
from services.billing.membership.economy_policy import copilot_requires_confirm, copilot_units_for_cost
from services.billing.membership.message_ledger import InsufficientMessages, reserve, settle


@dataclass
class OwnerTurnCredit:
    tenant_id: str
    reservation_id: str | None = None
    operation_id: str = ""
    units: int = 1
    blocked: bool = False
    confirm_required: bool = False
    _finalized: bool = field(default=False, repr=False)


def estimate_copilot_cost_usd(*, user_text: str = "", history_tokens: int = 0) -> float:
    from services.brain.model_pricing import compute_cost_from_usage
    from services.owner_copilot.flags import owner_model_name

    prompt = max(1, (len(user_text or "") // 4) + max(0, int(history_tokens)))
    completion_guess = min(1200, max(200, prompt // 2))
    priced = compute_cost_from_usage(owner_model_name(), prompt, completion_guess)
    return float(priced["cost_usd"])


def estimate_copilot_units(estimated_usd: float | None = None) -> int:
    return copilot_units_for_cost(estimated_usd)


def owner_turn_credit_begin(
    tenant_id: str,
    *,
    conversation_id: str = "",
    estimated_usd: float | None = None,
    confirm_billing: bool = False,
) -> OwnerTurnCredit:
    tid = (tenant_id or "").strip().lower()
    units = estimate_copilot_units(estimated_usd)
    if not tid or ai_generation_blocked(tid, need=units):
        return OwnerTurnCredit(tenant_id=tid, blocked=True, units=units)
    if copilot_requires_confirm(units) and not confirm_billing:
        return OwnerTurnCredit(tenant_id=tid, confirm_required=True, units=units)
    op = f"owner:{(conversation_id or 'turn').strip()[:48]}:{uuid.uuid4().hex[:12]}"
    try:
        reservation = reserve(
            tenant_id=tid,
            operation_id=op,
            response_class="generated_ai",
            units=units,
        )
        return OwnerTurnCredit(
            tenant_id=tid,
            reservation_id=reservation.reservation_id,
            operation_id=op,
            units=units,
        )
    except (InsufficientMessages, PermissionError, ValueError):
        return OwnerTurnCredit(tenant_id=tid, blocked=True, units=units)


def owner_turn_credit_finalize(credit: OwnerTurnCredit) -> None:
    if credit._finalized or not credit.operation_id:
        return
    try:
        settle(tenant_id=credit.tenant_id, operation_id=credit.operation_id, accepted=True)
        credit._finalized = True
    except Exception:
        owner_turn_credit_abort(credit)
        raise
    finally:
        credit.reservation_id = None


def owner_turn_credit_abort(credit: OwnerTurnCredit) -> None:
    if credit._finalized or not credit.operation_id:
        return
    try:
        settle(tenant_id=credit.tenant_id, operation_id=credit.operation_id, accepted=False)
    except Exception:
        pass
    finally:
        credit.reservation_id = None
        credit.operation_id = ""


def owner_turn_credit_on_event(credit: OwnerTurnCredit, event_type: str) -> None:
    if event_type == "done":
        owner_turn_credit_finalize(credit)
    elif event_type in {"cancelled", "error"}:
        owner_turn_credit_abort(credit)
