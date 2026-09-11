"""Website Chat leftover holds write through the credit reservation index."""

from __future__ import annotations

from services.customer_ai.leftover_reserve import leftover_policy_for, reset_leftover_pins_for_tests
from services.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests
from services.membership.pending_settlement import reset_pending_settlements_for_tests
from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle


class _Ledger:
    def __init__(self) -> None:
        self.reserved: dict[str, str] = {}

    def reserve(self, **kwargs):
        rid = f"cr_{kwargs['request_id']}"
        self.reserved[rid] = "open"
        return rid

    def capture(self, **kwargs):
        self.reserved[kwargs["reservation_id"]] = "capture"

    def release(self, **kwargs):
        self.reserved[kwargs["reservation_id"]] = "release"

    def reservation_terminal(self, tenant_id, reservation_id):
        state = self.reserved.get(reservation_id)
        return None if state == "open" else state

    def find_open_reservation_by_request(self, tenant_id, request_id):
        rid = f"cr_{request_id}"
        return rid if self.reserved.get(rid) == "open" else None


def test_web_chat_reserve_capture_indexes_leftover(monkeypatch) -> None:
    reset_credit_reservation_index_for_tests()
    reset_leftover_pins_for_tests()
    reset_pending_settlements_for_tests()
    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    monkeypatch.setattr("services.web_chat.credit_fsm.followup_uses_message_ledger", lambda: False)
    handle = WebChatCreditHandle(
        tenant_id="shop",
        reservation_id=None,
        request_id="web:idx:1",
        conversation_id="web:shop:visitor-1",
    )
    handle.reserve()
    assert handle.state == CreditFsmState.RESERVED
    assert open_counts(tenant_id="shop")["open"] == 1
    assert leftover_policy_for("shop", "web:idx:1") == "legacy_credits"
    assert leftover_policy_for("shop", "web:shop:visitor-1") == "legacy_credits"
    handle.capture()
    assert handle.state == CreditFsmState.CAPTURED
    assert open_counts(tenant_id="shop")["open"] == 0
    assert leftover_policy_for("shop", "web:idx:1") is None
    assert leftover_policy_for("shop", "web:shop:visitor-1") is None


def test_web_chat_release_closes_index(monkeypatch) -> None:
    reset_credit_reservation_index_for_tests()
    reset_leftover_pins_for_tests()
    reset_pending_settlements_for_tests()
    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    monkeypatch.setattr("services.web_chat.credit_fsm.followup_uses_message_ledger", lambda: False)
    handle = WebChatCreditHandle(tenant_id="shop", reservation_id=None, request_id="web:idx:2")
    handle.reserve()
    assert leftover_policy_for("shop", "web:idx:2") == "legacy_credits"
    assert handle.release() is True
    assert handle.state == CreditFsmState.RELEASED
    assert open_counts(tenant_id="shop")["open"] == 0
    assert leftover_policy_for("shop", "web:idx:2") is None
