"""Website Chat leftover holds write through the credit reservation index."""

from __future__ import annotations

from services.billing.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests
from services.billing.membership.message_ledger import grant_lot, reset_ledger_for_tests
from services.billing.membership.pending_settlement import reset_pending_settlements_for_tests
from services.brain.leftover_reserve import leftover_policy_for, reset_leftover_pins_for_tests
from services.integrations.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle


def _prep(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_ledger_for_tests()
    reset_credit_reservation_index_for_tests()
    reset_leftover_pins_for_tests()
    reset_pending_settlements_for_tests()
    grant_lot(
        tenant_id="shop",
        lot_id="shop:seed",
        kind="purchased",
        period_id="seed",
        amount=5,
        expires=False,
    )


def test_web_chat_reserve_capture_indexes_leftover(monkeypatch) -> None:
    _prep(monkeypatch)
    handle = WebChatCreditHandle(
        tenant_id="shop",
        reservation_id=None,
        request_id="web:idx:1",
        conversation_id="web:shop:visitor-1",
    )
    handle.reserve()
    assert handle.state == CreditFsmState.RESERVED
    assert open_counts(tenant_id="shop")["open"] == 1
    assert leftover_policy_for("shop", "web:idx:1") == "message_units"
    assert leftover_policy_for("shop", "web:shop:visitor-1") == "message_units"
    handle.capture()
    assert handle.state == CreditFsmState.CAPTURED
    assert open_counts(tenant_id="shop")["open"] == 0
    assert leftover_policy_for("shop", "web:idx:1") is None
    assert leftover_policy_for("shop", "web:shop:visitor-1") is None


def test_web_chat_release_closes_index(monkeypatch) -> None:
    _prep(monkeypatch)
    handle = WebChatCreditHandle(tenant_id="shop", reservation_id=None, request_id="web:idx:2")
    handle.reserve()
    assert leftover_policy_for("shop", "web:idx:2") == "message_units"
    assert handle.release() is True
    assert handle.state == CreditFsmState.RELEASED
    assert open_counts(tenant_id="shop")["open"] == 0
    assert leftover_policy_for("shop", "web:idx:2") is None
