"""Activation readiness never enables flags or invents commercial values."""

from __future__ import annotations

from services.membership.activation_readiness import activation_readiness
from services.membership.message_catalog import UNCONFIGURED_FREE_FIELDS


def test_readiness_stays_blocked_and_does_not_enable() -> None:
    report = activation_readiness()
    assert report["ready_to_enable"] is False
    assert report["daily_edit_default"] == 30
    assert report["conversion"]["blocked"] is True
    assert report["conversion"]["assumed_rate"] is None
    assert report["lab_isolated"] is True
    for field in UNCONFIGURED_FREE_FIELDS:
        assert field in report["catalog_unconfigured"]
        assert field in report["blockers"]
    assert all(report["imports"].values())
    assert report["imports"]["followup_billing"] is True
    assert report["imports"]["omni_hold"] is True
    assert report["imports"]["evals"] is True
    assert report["imports"]["social_turn_outcome"] is True
    assert report["imports"]["social_customer_name"] is True
    assert report["imports"]["hold_policy"] is True
    assert report["imports"]["outbox_pg"] is True
    assert report["imports"]["conversation_store_pg"] is True
    assert report["imports"]["catalog_admin_pg"] is True
    assert report["imports"]["credit_reservation_index_pg"] is True
    assert report["imports"]["processing_budgets_pg"] is True
    assert report["imports"]["durable_tables"] is True
    assert report["catalog"]["published"] is False
    assert report["catalog"]["checkout_ready"] is False
    assert report["store"] != "postgres"
    assert "message_store_not_postgres" in report["blockers"]
    assert "message_catalog_unpublished" in report["blockers"]
    assert "message_checkout_not_ready" in report["blockers"]
    assert "message_topup_not_sale_ready" in report["blockers"]
    assert "message_billing_cutover_off" in report["blockers"]
    assert "live_message_skus_not_sale_ready" in report["blockers"]
    assert "eval_suite_below_800" in report["blockers"]
    assert "live_channel_proof_missing" in report["blockers"]
    assert "live_voyage_pgvector_unverified" in report["blockers"]
    assert report["verification"]["eval_suite_complete"] is False
    assert report["verification"]["live_channel_proof"] is False
    assert report["verification"]["live_voyage_pgvector"] is False
    assert "leftover_credit_holds" in report
    assert report["leftover_credit_holds"]["open"] >= 0
    assert "durable_tables_incomplete" in report["blockers"]
    assert report["durable_tables"]["ready"] is False
    assert "customer_ai_outbox" in report["durable_tables"]["tables"]
    assert "never enables" in report["note"]


def test_platform_readiness_route_is_owner_only() -> None:
    from inspect import getsource

    from modules import platform_message_api

    src = getsource(platform_message_api.platform_activation_readiness)
    assert "require_platform_owner" in src
    assert "activation_readiness()" in src
