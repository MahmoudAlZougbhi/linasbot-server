"""Frozen five-plan catalog (membership-v1) without Postgres spine."""

from __future__ import annotations

from services.membership.comment_gate import CommentAutomationDenied, assert_comment_automation_allowed
from services.membership.plan_catalog import (
    CATALOG_VERSION,
    PUBLIC_PLAN_IDS,
    plan_features,
    public_plan_matrix,
)
from services.plan_economics import PLAN_FEATURES, PLAN_PRICES_USD, recommend_allowance


def test_public_matrix_is_five_plans_lite_to_max() -> None:
    assert PUBLIC_PLAN_IDS == ("lite", "starter", "growth", "pro", "max")
    assert list(PLAN_PRICES_USD.keys()) == list(PUBLIC_PLAN_IDS)
    assert PLAN_PRICES_USD["lite"] == 9.99
    assert PLAN_PRICES_USD["starter"] == 25.0
    assert PLAN_PRICES_USD["max"] == 259.0
    rows = public_plan_matrix()
    assert len(rows) == 5
    assert rows[0]["plan_id"] == "lite"
    assert rows[0]["comment_automation"] is False
    assert rows[1]["comment_automation"] is True
    assert CATALOG_VERSION.startswith("membership-v1")


def test_catalog_features_gate_comments_and_creative() -> None:
    assert plan_features("lite")["comment_automation"] is False
    assert plan_features("starter")["comment_automation"] is True
    assert plan_features("lite")["whatsapp"] is False
    assert plan_features("starter")["whatsapp"] is True
    assert plan_features("growth")["tiktok"] is True
    assert plan_features("pro")["tiktok"] is True
    assert PLAN_FEATURES["pro"]["image_generation"] is True
    assert PLAN_FEATURES["growth"]["image_generation"] is False
    assert recommend_allowance("lite").included_credits == 7000
    assert recommend_allowance("starter").included_credits == 17500


def test_comment_gate_allows_exempt_blocks_lite(monkeypatch, tmp_path) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import comment_gate as cg

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(cg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")

    assert_comment_automation_allowed("linas")

    store.set_plan(tenant_id="biz", plan_id="lite", status="active", source="admin")
    try:
        assert_comment_automation_allowed("biz")
        raise AssertionError("lite must deny comments")
    except CommentAutomationDenied:
        pass

    store.set_plan(tenant_id="biz", plan_id="starter", status="active", source="admin")
    assert_comment_automation_allowed("biz")
