"""Message-economy live meter: policy, grants, conversion block."""

from __future__ import annotations

from services.billing.membership.catalog_admin import reset_catalog_admin_for_tests, update_draft
from services.billing.membership.conversion_dry_run import apply_credit_conversion
from services.billing.membership.economy_policy import (
    action_units,
    copilot_requires_confirm,
    copilot_units_for_cost,
    validate_economy,
)
from services.billing.membership.message_flags import message_billing_enabled
from services.billing.membership.message_ledger import grant_lot, remaining_messages, reset_ledger_for_tests
from services.billing.membership.period_grants import ensure_included_grant


def setup_function() -> None:
    reset_ledger_for_tests()
    reset_catalog_admin_for_tests()


def test_message_billing_is_the_live_meter() -> None:
    assert message_billing_enabled() is True


def test_conversion_stays_blocked_without_rate() -> None:
    result = apply_credit_conversion(dry_run=False)
    assert result["blocked"] is True
    assert result["applied"] is False
    assert result["assumed_rate"] is None


def test_both_mode_each_sums_comment_and_dm() -> None:
    update_draft(
        actor="test",
        changes={
            "economy": validate_economy(
                {
                    "action_costs": {
                        "ai_public_comment": 2,
                        "ai_comment_dm": 3,
                        "ai_both_mode": "each",
                    }
                }
            )
        },
        reason="test",
    )
    assert action_units(response_class="generated_ai", invocation_kind="comment", comment_mode="ai_both") == 5


def test_both_mode_once_charges_max() -> None:
    update_draft(
        actor="test",
        changes={
            "economy": validate_economy(
                {
                    "action_costs": {
                        "ai_public_comment": 2,
                        "ai_comment_dm": 3,
                        "ai_both_mode": "once",
                    }
                }
            )
        },
        reason="test",
    )
    assert action_units(response_class="generated_ai", invocation_kind="comment", comment_mode="ai_both") == 3


def test_copilot_empty_bands_are_one_message_and_no_confirm() -> None:
    assert copilot_units_for_cost(None) == 1
    assert copilot_requires_confirm(1) is False
    assert copilot_requires_confirm(2) is True


def test_copilot_bands_convert_cost_to_units() -> None:
    update_draft(
        actor="test",
        changes={
            "economy": validate_economy(
                {
                    "copilot": {
                        "confirm_threshold_messages": 4,
                        "bands": [
                            {"min_usd": 0, "max_usd": 0.1, "message_units": 1},
                            {"min_usd": 0.1, "max_usd": 0.5, "message_units": 5},
                        ],
                    }
                }
            )
        },
        reason="test",
    )
    assert copilot_units_for_cost(0.05) == 1
    assert copilot_units_for_cost(0.2) == 5
    assert copilot_requires_confirm(5) is True


def test_copilot_begin_confirms_then_reserves() -> None:
    from services.owner_copilot.message_billing import owner_turn_hold_begin

    grant_lot(
        tenant_id="econ-copilot",
        lot_id="econ-copilot:seed",
        kind="purchased",
        period_id="seed",
        amount=20,
        expires=False,
    )
    update_draft(
        actor="test",
        changes={
            "economy": validate_economy(
                {
                    "copilot": {
                        "confirm_threshold_messages": 2,
                        "bands": [{"min_usd": 0, "max_usd": 1, "message_units": 5}],
                    }
                }
            )
        },
        reason="test",
    )
    pending = owner_turn_hold_begin("econ-copilot", estimated_usd=0.2)
    assert pending.confirm_required is True
    assert pending.reservation_id is None
    held = owner_turn_hold_begin("econ-copilot", estimated_usd=0.2, confirm_billing=True)
    assert held.confirm_required is False
    assert held.reservation_id
    assert remaining_messages("econ-copilot") == 15


def test_period_grant_uses_message_catalog_included() -> None:
    from services.billing.entitlements_service import entitlements_store

    entitlements_store.set_plan(tenant_id="econ-lite", plan_id="lite", status="active", source="test")
    ensure_included_grant("econ-lite")
    assert remaining_messages("econ-lite") == 550


def test_purchased_lot_does_not_expire() -> None:
    grant_lot(
        tenant_id="econ-pack",
        lot_id="econ-pack:purchased:txn-1",
        kind="purchased",
        period_id="txn-1",
        amount=100,
        expires=False,
    )
    assert remaining_messages("econ-pack") == 100
