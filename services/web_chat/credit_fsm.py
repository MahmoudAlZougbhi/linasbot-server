"""Crash-recoverable credit reserve / capture / release for Website Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from services.web_chat.operation_fsm import OperationState, is_visible_state, may_release_credit


class CreditFsmState(StrEnum):
    IDLE = "idle"
    RESERVED = "reserved"
    CAPTURED = "captured"
    RELEASED = "released"
    RELEASE_PENDING = "release_pending"
    BILLING_PENDING = "billing_pending"


@dataclass
class WebChatCreditHandle:
    tenant_id: str
    reservation_id: str | None
    request_id: str
    state: CreditFsmState = CreditFsmState.IDLE
    operation_state: OperationState | None = None
    _released_once: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self.hydrate_from_operation_context()

    def hydrate_from_operation_context(self) -> None:
        """Reconstruct in-memory credit state from durable operation + reservation ids."""
        if self.state != CreditFsmState.IDLE:
            return
        if self.operation_state is None:
            return
        op = OperationState(str(self.operation_state))
        if op == OperationState.RELEASED:
            self.state = CreditFsmState.RELEASED
            return
        if op == OperationState.RELEASE_PENDING:
            self.state = CreditFsmState.RELEASE_PENDING
            return
        if op in {OperationState.CAPTURED, OperationState.COMPLETE} and not self.reservation_id:
            self.state = CreditFsmState.CAPTURED
            return
        if not self.reservation_id:
            return
        if op == OperationState.BILLING_PENDING or (
            op in {OperationState.DURABLE_VISIBLE, OperationState.CAPTURED} and self._reservation_is_open()
        ):
            self.state = CreditFsmState.BILLING_PENDING
            return
        if op in {
            OperationState.RESERVED,
            OperationState.REPLY_READY,
            OperationState.CLAIMED,
        }:
            self.state = CreditFsmState.RESERVED

    def _reservation_is_open(self) -> bool:
        if not self.reservation_id:
            return False
        from services.credit_ledger_service import credit_ledger_service

        return credit_ledger_service.reservation_terminal(self.tenant_id, self.reservation_id) is None

    def reconcile_existing_reservation(self) -> str | None:
        from services.credit_ledger_service import credit_ledger_service

        return credit_ledger_service.find_open_reservation_by_request(self.tenant_id, self.request_id)

    def reserve(self) -> None:
        if self.state == CreditFsmState.RELEASE_PENDING:
            if not self.reconcile_release():
                return
        if self.state == CreditFsmState.RESERVED and self.reservation_id:
            return
        if self.state == CreditFsmState.CAPTURED:
            return
        if self.state not in {CreditFsmState.IDLE, CreditFsmState.BILLING_PENDING}:
            return
        existing = self.reconcile_existing_reservation()
        if existing:
            self.reservation_id = existing
            self.state = CreditFsmState.RESERVED
            return
        from services.credit_ledger_service import credit_ledger_service

        self.reservation_id = credit_ledger_service.reserve(
            tenant_id=self.tenant_id,
            user_id=None,
            credits=1,
            operation_type="web_customer_reply",
            request_id=self.request_id,
        )
        self.state = CreditFsmState.RESERVED

    def capture(self, *, model_provider: str = "web_chat") -> None:
        if self.state == CreditFsmState.CAPTURED:
            return
        if self.state not in {CreditFsmState.RESERVED, CreditFsmState.BILLING_PENDING} or not self.reservation_id:
            return
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.capture(
            tenant_id=self.tenant_id,
            reservation_id=self.reservation_id,
            provider_cost_usd=None,
            model_provider=model_provider,
        )
        self.state = CreditFsmState.CAPTURED
        self.reservation_id = None

    def release(self) -> bool:
        if self._released_once and self.state == CreditFsmState.RELEASED:
            return True
        if self.operation_state is not None and not may_release_credit(self.operation_state):
            return False
        if (
            self.state
            not in {
                CreditFsmState.RESERVED,
                CreditFsmState.BILLING_PENDING,
                CreditFsmState.RELEASE_PENDING,
            }
            or not self.reservation_id
        ):
            return False
        return self.reconcile_release()

    def reconcile_release(self) -> bool:
        if self.state == CreditFsmState.RELEASED:
            return True
        if not self.reservation_id:
            return False
        from services.credit_ledger_service import credit_ledger_service

        terminal = credit_ledger_service.reservation_terminal(self.tenant_id, self.reservation_id)
        if terminal == "release":
            self.state = CreditFsmState.RELEASED
            self.reservation_id = None
            self._released_once = True
            return True
        if terminal == "capture":
            self.state = CreditFsmState.CAPTURED
            self.reservation_id = None
            return False
        try:
            credit_ledger_service.release(tenant_id=self.tenant_id, reservation_id=self.reservation_id)
        except Exception:
            self.state = CreditFsmState.RELEASE_PENDING
            return False
        terminal = credit_ledger_service.reservation_terminal(self.tenant_id, self.reservation_id)
        if terminal != "release":
            self.state = CreditFsmState.RELEASE_PENDING
            return False
        self.state = CreditFsmState.RELEASED
        self.reservation_id = None
        self._released_once = True
        return True

    def mark_billing_pending(self) -> None:
        if self.operation_state is not None and is_visible_state(self.operation_state):
            self.state = CreditFsmState.BILLING_PENDING

    def on_failure(self) -> None:
        if self.operation_state is not None and is_visible_state(self.operation_state):
            self.mark_billing_pending()
            return
        if self.state in {CreditFsmState.RESERVED, CreditFsmState.BILLING_PENDING, CreditFsmState.RELEASE_PENDING}:
            self.reconcile_release()

    def reconcile_capture(self, *, model_provider: str = "web_chat") -> bool:
        """Retry capture for billing_pending without a second reserve."""
        self.hydrate_from_operation_context()
        if self.state == CreditFsmState.CAPTURED:
            return True
        if not self.reservation_id:
            existing = self.reconcile_existing_reservation()
            if existing:
                self.reservation_id = existing
                self.state = CreditFsmState.RESERVED
        if self.state not in {CreditFsmState.RESERVED, CreditFsmState.BILLING_PENDING}:
            return False
        if not self.reservation_id:
            return False
        from services.credit_ledger_service import credit_ledger_service

        terminal = credit_ledger_service.reservation_terminal(self.tenant_id, self.reservation_id)
        if terminal == "capture":
            self.state = CreditFsmState.CAPTURED
            self.reservation_id = None
            return True
        if terminal == "release":
            self.state = CreditFsmState.RELEASED
            self.reservation_id = None
            return False
        try:
            self.capture(model_provider=model_provider)
            return self.state == CreditFsmState.CAPTURED
        except Exception:
            return False


def tenant_scoped_user_data(*, tenant_id: str, user_id: str, visitor_id: str) -> dict[str, Any]:
    """Immutable tenant identity snapshot for logs/transcripts (no shared mutable races)."""
    return {
        "tenant_id": str(tenant_id or "").strip().lower(),
        "channel": "web",
        "social_sender_id": str(visitor_id or "").strip(),
        "phone_number": f"room:{user_id}",
        "user_preferred_lang": "",
    }
