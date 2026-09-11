"""Purchased-lot refunds, Stripe/Google honesty, activation-flag report."""

from __future__ import annotations

import pytest

from services.membership.iap_message_grant import (
    apply_verified_stripe_message_checkout,
    grant_from_mapped_pack,
    maybe_revoke_purchased_from_verified_txn,
    stripe_checkout_kind,
)
from services.membership.message_flags import activation_flags_report
from services.membership.message_ledger import remaining_messages, reserve, reset_ledger_for_tests


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    monkeypatch.delenv("MESSAGE_BILLING_CUTOVER", raising=False)
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    reset_ledger_for_tests()


def _grant(tenant_id: str = "pack-shop", txn: str = "txn-pack-1") -> None:
    result = grant_from_mapped_pack(
        tenant_id=tenant_id,
        transaction_id=txn,
        pack={"pack_id": "messages_100", "quantity": 100, "price_usd": 4, "sale_ready": True},
    )
    assert result["granted"] is True


def test_revoke_purchased_zeros_unused_and_is_idempotent() -> None:
    _grant()
    reserve(tenant_id="pack-shop", operation_id="hold-1", response_class="generated_ai")
    first = maybe_revoke_purchased_from_verified_txn(tenant_id="pack-shop", transaction_id="txn-pack-1")
    assert first["revoked"] is True
    assert first["remaining_cleared"] == 100
    assert first["reservations_released"] == 1
    assert remaining_messages("pack-shop") == 0
    again = maybe_revoke_purchased_from_verified_txn(tenant_id="pack-shop", transaction_id="txn-pack-1")
    assert again["revoked"] is True
    assert again["remaining_cleared"] == 0


def test_revoke_missing_lot_is_honest() -> None:
    result = maybe_revoke_purchased_from_verified_txn(tenant_id="none-shop", transaction_id="missing")
    assert result == {"revoked": False, "reason": "no_purchased_lot"}


def test_apple_refund_revokes_message_lot_without_subscription() -> None:
    from services.apple_assn_handlers import handle_refund_or_revoke

    _grant()
    out = handle_refund_or_revoke(
        payload={"productId": "com.linasai.messages.100", "transactionId": "txn-pack-1"},
        tenant_id="pack-shop",
        notification_type="REFUND",
    )
    assert out["message_revoke"]["revoked"] is True
    assert "subscription" not in out
    assert remaining_messages("pack-shop") == 0


def test_google_revoked_state_revokes_instead_of_granting(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.store_iap_api import apply_google_notification_effect

    _grant(tenant_id="g-pack", txn="txn-g-pack")
    monkeypatch.setattr(
        "modules.store_iap_api.apply_normalized_notification",
        lambda **_k: (_ for _ in ()).throw(ValueError("Unmapped store product")),
    )
    result = apply_google_notification_effect(
        {
            "tenant_id": "g-pack",
            "product_id": "com.linasai.messages.100",
            "subscription_state": "REVOKED",
            "original_transaction_id": "txn-g-pack",
            "event_id": "evt-rev",
        }
    )
    assert result["message_revoke"]["revoked"] is True
    assert remaining_messages("g-pack") == 0


def test_stripe_token_pack_never_grants_messages() -> None:
    assert stripe_checkout_kind({"product": "linas_token_pack"}) == "token_pack"
    grant = apply_verified_stripe_message_checkout(
        tenant_id="stripe-shop",
        product_id="linas_token_pack",
        transaction_id="cs_token",
    )
    assert grant == {"granted": False, "reason": "cutover_off"}
    assert remaining_messages("stripe-shop") == 0


def test_stripe_message_pack_stays_blocked_without_sale_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    assert stripe_checkout_kind({"product": "linas_message_pack"}) == "message_pack"
    monkeypatch.setenv("MESSAGE_BILLING_CUTOVER", "true")
    grant = apply_verified_stripe_message_checkout(
        tenant_id="stripe-msg",
        product_id="com.linasai.messages.100",
        transaction_id="cs_msg",
    )
    assert grant == {"granted": False, "reason": "unmapped_or_unpriced_pack"}
    assert remaining_messages("stripe-msg") == 0


def test_refunded_plan_expires_included_lot(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.entitlements_service import entitlements_store

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    entitlements_store.set_plan(tenant_id="refund-grant", plan_id="lite", status="active", source="admin")
    assert remaining_messages("refund-grant") == 550
    entitlements_store.set_plan(tenant_id="refund-grant", plan_id="lite", status="refunded", source="apple")
    assert remaining_messages("refund-grant") == 0


def test_preflight_script_fails_closed_on_activation_flags() -> None:
    from pathlib import Path

    source = Path("scripts/prod_preflight_readonly.sh").read_text(encoding="utf-8")
    assert "ACTIVATION_FLAGS_MUST_STAY_OFF" in source
    assert "activation_flags_report" in source
    assert "message_billing_tables_ready" in source
    assert "message_durable_tables_ready" in source
    assert "durable_table_report" in source


def test_activation_flags_report_requires_all_off() -> None:
    ok = activation_flags_report(
        {
                        "MESSAGE_BILLING_ENABLED": "",
            "MESSAGE_BILLING_CUTOVER": "0",
            "FREE_PLAN_ENFORCEMENT_ENABLED": "false",
            "LINAS_CUSTOMER_AI_LAB": "false",
        }
    )
    assert ok["ok"] is True
    assert ok["enabled"] == []
    blocked = activation_flags_report({"MESSAGE_BILLING_ENABLED": "true"})
    assert blocked["ok"] is False
    assert "MESSAGE_BILLING_ENABLED" in blocked["enabled"]


def test_stale_reservation_gc_marks_unresolved_without_refund() -> None:
    from datetime import datetime, timedelta, timezone

    from services.membership.message_ledger import (
        grant_lot,
        list_reservations,
        remaining_messages,
        reserve,
        reset_ledger_for_tests,
    )
    from services.membership.pending_settlement import list_pending, reset_pending_settlements_for_tests
    from services.membership.reservation_gc import release_stale_reservations, run_reservation_gc

    reset_ledger_for_tests()
    reset_pending_settlements_for_tests()
    from services.membership.lot_window import current_period_id

    grant_lot(tenant_id="gc-shop", lot_id="inc", kind="included", period_id=current_period_id(), amount=5)
    reserve(tenant_id="gc-shop", operation_id="stuck", response_class="generated_ai")
    held = next(item for item in list_reservations("gc-shop") if item.operation_id == "stuck")
    held.created_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert remaining_messages("gc-shop") == 4
    assert release_stale_reservations(max_age_seconds=3600) == 1
    assert remaining_messages("gc-shop") == 4
    assert any(item.state == "unresolved" and item.operation_id == "stuck" for item in list_pending())
    result = run_reservation_gc()
    assert result["ran"] is True
    assert remaining_messages("gc-shop") == 4
