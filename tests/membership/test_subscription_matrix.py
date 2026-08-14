"""Frozen five-plan catalog + seats + comment enable gate."""

from __future__ import annotations

import pytest

from services.membership.comment_gate import CommentAutomationDenied, assert_comment_automation_allowed
from services.membership.plan_catalog import (
    CATALOG_VERSION,
    PLAN_CATALOG,
    PUBLIC_PLAN_IDS,
    public_plan_matrix,
)
from services.membership.seats import SeatLimitExceeded, assert_can_add_seat, seat_usage
from services.plan_economics import PLAN_FAQ_MAX_ENTRIES, PLAN_FEATURES, PLAN_PRICES_USD


def test_frozen_matrix_exact_values() -> None:
    assert PUBLIC_PLAN_IDS == ("lite", "starter", "growth", "pro", "max")
    expected = {
        "lite": (9.99, 7000, 50, 0, False),
        "starter": (25.0, 17500, 110, 2, True),
        "growth": (59.0, 41300, 250, 5, True),
        "pro": (109.0, 76300, 600, None, True),
        "max": (259.0, 181300, 1500, None, True),
    }
    for pid, (price, credits, faq, seats, comments) in expected.items():
        plan = PLAN_CATALOG[pid]
        assert PLAN_PRICES_USD[pid] == price
        assert plan.included_credits == credits
        assert plan.faq_capacity == faq
        assert PLAN_FAQ_MAX_ENTRIES[pid] == faq
        assert plan.additional_seats is seats
        assert plan.additional_seats is None or isinstance(plan.additional_seats, int)
        assert plan.comment_automation is comments
        assert PLAN_FEATURES[pid]["comment_automation"] is comments
        assert plan.whatsapp is (pid != "lite")
        assert plan.tiktok is (pid in {"pro", "max"})
    assert CATALOG_VERSION.startswith("membership-v1")
    assert len(public_plan_matrix()) == 5


def test_unlimited_seats_are_none_not_magic() -> None:
    assert PLAN_CATALOG["pro"].additional_seats is None
    assert PLAN_CATALOG["max"].additional_seats is None
    assert 999_999 not in {PLAN_CATALOG[p].additional_seats for p in PUBLIC_PLAN_IDS}


def test_seat_owner_excluded_and_pending_count() -> None:
    assert seat_usage(active_non_owner_members=0, pending_invitations=0) == 0
    assert seat_usage(active_non_owner_members=2, pending_invitations=1) == 3
    # Lite allows 0 additional seats — cannot add even when currently unused.
    with pytest.raises(SeatLimitExceeded):
        assert_can_add_seat("lite", active_non_owner_members=0, pending_invitations=0)
    assert_can_add_seat("starter", active_non_owner_members=1, pending_invitations=0)
    with pytest.raises(SeatLimitExceeded):
        assert_can_add_seat("starter", active_non_owner_members=2, pending_invitations=0)
    with pytest.raises(SeatLimitExceeded):
        assert_can_add_seat("growth", active_non_owner_members=4, pending_invitations=1)
    # Unlimited
    assert_can_add_seat("pro", active_non_owner_members=10_000, pending_invitations=50)
    assert_can_add_seat("max", active_non_owner_members=10_000, pending_invitations=50)


def test_comment_gate_blocks_lite_allows_starter(monkeypatch, tmp_path) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import comment_gate as cg

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(cg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")

    store.set_plan(tenant_id="biz", plan_id="lite", status="active", source="admin")
    with pytest.raises(CommentAutomationDenied):
        assert_comment_automation_allowed("biz")

    store.set_plan(tenant_id="biz", plan_id="starter", status="active", source="admin")
    assert_comment_automation_allowed("biz")


@pytest.mark.asyncio
async def test_set_channel_toggle_comments_denied_on_lite(monkeypatch, tmp_path) -> None:
    from services import entitlements_service as es
    from services.channel_capability_toggles import ChannelToggleError, set_channel_toggle
    from services.entitlements_service import EntitlementsStore
    from services.membership import comment_gate as cg

    store = EntitlementsStore(root=tmp_path / "ent2")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(cg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")
    store.set_plan(tenant_id="biz2", plan_id="lite", status="active", source="admin")
    # CONNECT_REQUIRED runs before plan gate — stub a connected channel.
    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [{"asset_id": "ig-connected"}],
    )

    with pytest.raises(ChannelToggleError) as exc:
        await set_channel_toggle(
            tenant_id="biz2",
            platform="instagram",
            toggle="comments",
            enabled=True,
            actor="test",
        )
    assert exc.value.code == "COMMENT_AUTOMATION_DENIED"


def test_public_plans_omit_provider_cost() -> None:
    import asyncio

    from modules.plans_api import public_plans

    body = asyncio.run(public_plans())
    assert body["billing_period"] == "monthly"
    assert "credit_unit" not in body
    blob = str(body).lower()
    assert "openai" not in blob
    assert "provider cost" not in blob
    assert "margin" not in blob
    assert len(body["plans"]) == 5
    for plan in body["plans"]:
        assert "creative_studio" not in plan["features"]
        assert "video_generation" not in plan["features"]


def test_iap_product_map_covers_five_monthly() -> None:
    from services.store_iap_service import _product_map, map_product_to_plan

    mapping = _product_map()
    for pid in PUBLIC_PLAN_IDS:
        assert pid in mapping.values()
    assert map_product_to_plan("com.linasai.app.lite.monthly") == "lite"
    assert map_product_to_plan("linas_ai_max_monthly") == "max"


def test_duplicate_iap_notification(monkeypatch, tmp_path) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore, apply_store_notification

    root = tmp_path / "data"
    store = EntitlementsStore(root=root / "entitlements")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(es, "_DATA_ROOT", root)

    first = apply_store_notification(
        tenant_id="t1",
        plan_id="growth",
        status="active",
        source="apple",
        original_transaction_id="tx-1",
        idempotency_key="apple:evt-1",
    )
    second = apply_store_notification(
        tenant_id="t1",
        plan_id="growth",
        status="active",
        source="apple",
        original_transaction_id="tx-1",
        idempotency_key="apple:evt-1",
    )
    assert first["duplicate"] is False
    assert second["duplicate"] is True
