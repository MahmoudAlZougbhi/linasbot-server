"""Web Chat plan gate and channel helpers."""

from __future__ import annotations

import pytest

from services.live_chat_channel import resolve_live_chat_channel
from services.membership.plan_catalog import PLAN_CATALOG, plan_features
from services.membership.web_gate import WebPlanDenied, assert_web_plan_allowed
from services.plan_economics import PLAN_FEATURES
from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT, SOURCE_CHANNELS
from services.smart_followup.channels import normalize_followup_channel
from services.web_chat.store import WebChatStore


def test_web_plan_matrix_matches_whatsapp_tier() -> None:
    assert PLAN_CATALOG["lite"].web is False
    assert PLAN_CATALOG["starter"].web is True
    assert PLAN_CATALOG["growth"].web is True
    for pid in ("lite", "starter", "growth", "pro", "max"):
        assert plan_features(pid)["web"] is PLAN_CATALOG[pid].web
        assert PLAN_FEATURES[pid]["web"] is PLAN_CATALOG[pid].web


def test_web_gate_blocks_lite_allows_starter(monkeypatch, tmp_path) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import web_gate as wg

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(wg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")

    assert_web_plan_allowed("linas")

    store.set_plan(tenant_id="biz", plan_id="lite", status="active", source="admin")
    with pytest.raises(WebPlanDenied):
        assert_web_plan_allowed("biz")

    store.set_plan(tenant_id="biz", plan_id="starter", status="active", source="admin")
    assert_web_plan_allowed("biz")


def test_web_gate_allows_max_plan(monkeypatch, tmp_path) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import web_gate as wg

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(wg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "")

    store.set_plan(tenant_id="clinic", plan_id="max", status="active", source="admin")
    assert_web_plan_allowed("clinic")


def test_entitlements_public_includes_web_for_max(tmp_path, monkeypatch) -> None:
    from services.entitlements_service import EntitlementsStore, get_tenant_entitlement_public

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "")

    store.set_plan(tenant_id="clinic", plan_id="max", status="active", source="admin")
    pub = get_tenant_entitlement_public("clinic")
    assert pub["plan_id"] == "max"
    assert pub["web"] is True
    assert pub["features"]["web"] is True


def test_entitlements_public_web_true_for_exempt_tenant(tmp_path, monkeypatch) -> None:
    from services.entitlements_service import get_tenant_entitlement_public

    monkeypatch.delenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", raising=False)
    pub = get_tenant_entitlement_public("linas")
    assert pub["subscription_exempt"] is True
    assert pub["web"] is True


def test_live_chat_resolves_web_channel() -> None:
    assert resolve_live_chat_channel("web:visitor123") == "web"
    assert resolve_live_chat_channel("visitor", {"customer_info": {"channel": "web_chat"}}) == "web"


def test_requests_include_web_chat_source() -> None:
    assert SOURCE_CHANNEL_WEB_CHAT in SOURCE_CHANNELS


def test_followup_normalizes_web_channel() -> None:
    assert normalize_followup_channel("web_chat") == SOURCE_CHANNEL_WEB_CHAT
    assert normalize_followup_channel("web") == SOURCE_CHANNEL_WEB_CHAT


def test_widget_store_roundtrip(tmp_path) -> None:
    store = WebChatStore(root=tmp_path / "web_chat")
    widget = store.get_or_create_widget("tenant-a")
    assert widget.widget_key
    updated = store.update_widget("tenant-a", site_url="https://shop.example.com", enabled=True)
    assert updated.site_url == "https://shop.example.com"
    assert updated.enabled is True
    assert updated.connected is True
    by_key = store.get_widget_by_key(updated.widget_key)
    assert by_key is not None
    assert by_key.tenant_id == "tenant-a"
