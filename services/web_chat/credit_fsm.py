"""Crash-recoverable credit reserve / capture / release for Website Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from services.web_chat.followup_message_ledger import (
    followup_uses_message_ledger,
    is_message_reservation,
    message_reservation_id,
)
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
    conversation_id: str = ""
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
        if op in {OperationState.CAPTURED, OperationState.COMPLETE} and (
            not self.reservation_id or is_message_reservation(self.reservation_id)
        ):
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

    def _index_open(self) -> None:
        rid = str(self.reservation_id or "")
        if not rid or is_message_reservation(rid):
            return
        try:
            from services.customer_ai.leftover_reserve import remember_leftover_hold

            remember_leftover_hold(
                tenant_id=self.tenant_id,
                reservation_id=rid,
                request_id=self.request_id,
                operation_type="web_customer_reply",
                pin_ids=(self.conversation_id,) if self.conversation_id else (),
            )
        except Exception:
            from services.membership.credit_reservation_index import record_open

            record_open(
                tenant_id=self.tenant_id,
                reservation_id=rid,
                request_id=self.request_id,
                operation_type="web_customer_reply",
            )

    def _index_close(self, reservation_id: str | None, *, state: str) -> None:
        rid = str(reservation_id or "")
        if not rid or is_message_reservation(rid):
            return
        try:
            if state == "settled":
                from services.customer_ai.leftover_reserve import complete_leftover_capture

                complete_leftover_capture(
                    self.tenant_id,
                    rid,
                    operation_id=self.request_id,
                    extra_ids=(self.conversation_id,) if self.conversation_id else (),
                )
                return
            if state == "released":
                from services.customer_ai.leftover_reserve import complete_leftover_release

                complete_leftover_release(
                    self.tenant_id,
                    rid,
                    extra_ids=tuple(item for item in (self.request_id, self.conversation_id) if item),
                )
                return
        except Exception:
            pass
        from services.membership.credit_reservation_index import mark_closed

        mark_closed(rid, state=state)

    def _reservation_is_open(self) -> bool:
        if not self.reservation_id or is_message_reservation(self.reservation_id):
            return False
        from services.credit_ledger_service import credit_ledger_service

        return credit_ledger_service.reservation_terminal(self.tenant_id, self.reservation_id) is None

    def reconcile_existing_reservation(self) -> str | None:
        if followup_uses_message_ledger() or is_message_reservation(self.reservation_id):
            return None
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
        if followup_uses_message_ledger():
            self.reservation_id = message_reservation_id(self.request_id)
            self.state = CreditFsmState.RESERVED
            return
        existing = self.reconcile_existing_reservation()
        if existing:
            self.reservation_id = existing
            self.state = CreditFsmState.RESERVED
            self._index_open()
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
        self._index_open()

    def capture(self, *, model_provider: str = "web_chat") -> None:
        if self.state == CreditFsmState.CAPTURED:
            return
        if self.state not in {CreditFsmState.RESERVED, CreditFsmState.BILLING_PENDING} or not self.reservation_id:
            return
        if is_message_reservation(self.reservation_id):
            self.state = CreditFsmState.CAPTURED
            self.reservation_id = None
            return
        from services.credit_ledger_service import credit_ledger_service

        reserved = self.reservation_id
        credit_ledger_service.capture(
            tenant_id=self.tenant_id,
            reservation_id=self.reservation_id,
            provider_cost_usd=None,
            model_provider=model_provider,
        )
        self.state = CreditFsmState.CAPTURED
        self.reservation_id = None
        self._index_close(reserved, state="settled")

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
        if is_message_reservation(self.reservation_id):
            self.state = CreditFsmState.RELEASED
            self.reservation_id = None
            self._released_once = True
            return True
        from services.credit_ledger_service import credit_ledger_service

        reserved = self.reservation_id
        terminal = credit_ledger_service.reservation_terminal(self.tenant_id, self.reservation_id)
        if terminal == "release":
            self.state = CreditFsmState.RELEASED
            self.reservation_id = None
            self._released_once = True
            self._index_close(reserved, state="released")
            return True
        if terminal == "capture":
            self.state = CreditFsmState.CAPTURED
            self.reservation_id = None
            self._index_close(reserved, state="settled")
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
        self._index_close(reserved, state="released")
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
                self._index_open()
        if self.state not in {CreditFsmState.RESERVED, CreditFsmState.BILLING_PENDING}:
            return False
        if not self.reservation_id:
            return False
        if is_message_reservation(self.reservation_id):
            try:
                self.capture(model_provider=model_provider)
                return self.state == CreditFsmState.CAPTURED
            except Exception:
                return False
        from services.credit_ledger_service import credit_ledger_service

        terminal = credit_ledger_service.reservation_terminal(self.tenant_id, self.reservation_id)
        reserved = self.reservation_id
        if terminal == "capture":
            self.state = CreditFsmState.CAPTURED
            self.reservation_id = None
            self._index_close(reserved, state="settled")
            return True
        if terminal == "release":
            self.state = CreditFsmState.RELEASED
            self.reservation_id = None
            self._index_close(reserved, state="released")
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
