"""WhatsApp plan gate — Lite excluded; Starter+ included; exempt tenants allowed."""

from __future__ import annotations

import pytest

from services.membership.plan_catalog import PLAN_CATALOG, plan_features
from services.membership.whatsapp_gate import WhatsAppPlanDenied, assert_whatsapp_plan_allowed
from services.plan_economics import PLAN_FEATURES


def test_whatsapp_tiktok_matrix_matches_product() -> None:
    assert PLAN_CATALOG["lite"].whatsapp is False
    assert PLAN_CATALOG["lite"].tiktok is False
    assert PLAN_CATALOG["starter"].whatsapp is True
    assert PLAN_CATALOG["starter"].tiktok is False
    assert PLAN_CATALOG["growth"].whatsapp is True
    assert PLAN_CATALOG["growth"].tiktok is False
    assert PLAN_CATALOG["pro"].whatsapp is True
    assert PLAN_CATALOG["pro"].tiktok is True
    assert PLAN_CATALOG["max"].whatsapp is True
    assert PLAN_CATALOG["max"].tiktok is True
    for pid in ("lite", "starter", "growth", "pro", "max"):
        assert plan_features(pid)["whatsapp"] is PLAN_CATALOG[pid].whatsapp
        assert plan_features(pid)["tiktok"] is PLAN_CATALOG[pid].tiktok
        assert PLAN_FEATURES[pid]["whatsapp"] is PLAN_CATALOG[pid].whatsapp
        assert PLAN_FEATURES[pid]["tiktok"] is PLAN_CATALOG[pid].tiktok


def test_whatsapp_gate_blocks_lite_allows_starter(monkeypatch, tmp_path) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import whatsapp_gate as wg

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(wg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")

    assert_whatsapp_plan_allowed("linas")

    store.set_plan(tenant_id="biz", plan_id="lite", status="active", source="admin")
    with pytest.raises(WhatsAppPlanDenied) as exc:
        assert_whatsapp_plan_allowed("biz")
    assert exc.value.code == "WHATSAPP_PLAN_DENIED"

    store.set_plan(tenant_id="biz", plan_id="starter", status="active", source="admin")
    assert_whatsapp_plan_allowed("biz")
