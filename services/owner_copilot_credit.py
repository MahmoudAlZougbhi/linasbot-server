"""Reserve / capture / release Owner Copilot turns on the credit ledger."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from services.credit_ai_gate import ai_generation_blocked


@dataclass
class OwnerTurnCredit:
    tenant_id: str
    reservation_id: str | None = None
    blocked: bool = False
    _finalized: bool = field(default=False, repr=False)


def owner_turn_credit_begin(tenant_id: str, *, conversation_id: str = "") -> OwnerTurnCredit:
    """Reserve one ledger credit before Owner Copilot generation. Fail closed at 0 remaining."""
    tid = (tenant_id or "").strip().lower()
    if not tid or ai_generation_blocked(tid):
        return OwnerTurnCredit(tenant_id=tid, blocked=True)
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.ensure_period_grant(tid)
        rid = credit_ledger_service.reserve(
            tenant_id=tid,
            user_id=None,
            credits=1,
            operation_type="owner_copilot",
            request_id=f"owner:{(conversation_id or 'turn').strip()[:48]}:{uuid.uuid4().hex[:12]}",
        )
        return OwnerTurnCredit(tenant_id=tid, reservation_id=rid)
    except PermissionError:
        return OwnerTurnCredit(tenant_id=tid, blocked=True)


def owner_turn_credit_finalize(credit: OwnerTurnCredit) -> None:
    if credit._finalized or not credit.reservation_id:
        return
    rid = credit.reservation_id
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.capture(
            tenant_id=credit.tenant_id,
            reservation_id=rid,
            provider_cost_usd=None,
            model_provider="owner_copilot",
        )
        credit._finalized = True
    except Exception:
        owner_turn_credit_abort(credit)
        raise
    finally:
        credit.reservation_id = None


def owner_turn_credit_abort(credit: OwnerTurnCredit) -> None:
    if credit._finalized or not credit.reservation_id:
        return
    rid = credit.reservation_id
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.release(tenant_id=credit.tenant_id, reservation_id=rid)
    except Exception:
        pass
    finally:
        credit.reservation_id = None


def owner_turn_credit_on_event(credit: OwnerTurnCredit, event_type: str) -> None:
    """Capture on terminal success; release on cancel/error before capture."""
    if event_type == "done":
        owner_turn_credit_finalize(credit)
    elif event_type in {"cancelled", "error"}:
        owner_turn_credit_abort(credit)
