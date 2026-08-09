"""Phase 2 core: mobile refresh, entitlements, credits, safety, owner tools."""

from __future__ import annotations

import pytest

from services.credit_ledger_service import CreditLedgerService
from services.entitlements_service import EntitlementsStore, apply_store_notification
from services.mobile_refresh_token_service import MobileRefreshTokenService
from services.owner_chat_store import OwnerChatStore
from services.platform_owner_service import PlatformOwnerService
from services.safety_gateway import SafetyGateway


def test_mobile_refresh_rotate(tmp_path) -> None:
    svc = MobileRefreshTokenService(store_dir=tmp_path / "refresh")
    raw = svc.issue(user_id="u1", email="a@b.com", tenant_id="t1", session_id="s1")
    rec = svc.consume(raw)
    assert rec is not None
    assert svc.consume(raw) is None


def test_entitlement_set_plan(tmp_path) -> None:
    store = EntitlementsStore(root=tmp_path / "ent")
    ent = store.set_plan(tenant_id="t1", plan_id="growth", status="active", source="admin")
    assert ent.plan_id == "growth"
    assert ent.features.get("comment_automation") is True
    assert ent.included_credits > 0


def test_entitlement_notification_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "services.entitlements_service._DATA_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        "services.entitlements_service.entitlements_store",
        EntitlementsStore(root=tmp_path / "entitlements"),
    )
    first = apply_store_notification(
        tenant_id="t1",
        plan_id="starter",
        status="active",
        source="apple",
        original_transaction_id="tx1",
        idempotency_key="evt-1",
    )
    second = apply_store_notification(
        tenant_id="t1",
        plan_id="starter",
        status="active",
        source="apple",
        original_transaction_id="tx1",
        idempotency_key="evt-1",
    )
    assert first["duplicate"] is False
    assert second["duplicate"] is True


def test_credit_reserve_release(tmp_path, monkeypatch) -> None:
    from services import entitlements_service as es

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    store.set_plan(tenant_id="t1", plan_id="pro", status="active", source="admin")
    monkeypatch.setattr(
        "services.credit_ledger_service.entitlements_store",
        store,
    )
    ledger = CreditLedgerService(root=tmp_path / "ledger")
    ledger.ensure_period_grant("t1")
    start = ledger.get_balance("t1")
    rid = ledger.reserve(
        tenant_id="t1",
        user_id="u1",
        credits=10,
        operation_type="creative_image",
        request_id="r1",
    )
    mid = ledger.get_balance("t1")
    assert mid == start - 10
    ledger.release(tenant_id="t1", reservation_id=rid)
    assert ledger.get_balance("t1") == start


@pytest.mark.asyncio
async def test_safety_blocks_explicit_policy() -> None:
    gw = SafetyGateway()
    decision = await gw.check_text(
        tenant_id="t1",
        user_id="u1",
        text="how to make a bomb for school",
        channel="creative",
    )
    assert decision.decision == "block"


def test_owner_chat_isolation(tmp_path) -> None:
    store = OwnerChatStore(root=tmp_path / "chat")
    a = store.create_conversation(tenant_id="t1", user_id="u1")
    b = store.create_conversation(tenant_id="t2", user_id="u1")
    assert store.get_conversation(tenant_id="t2", user_id="u1", conversation_id=a.id) is None
    assert store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=b.id) is None


def test_platform_owner_suspend_audit(tmp_path) -> None:
    svc = PlatformOwnerService(root=tmp_path / "owner")
    svc.suspend_tenant(actor_user_id="owner1", tenant_id="bad", reason="abuse")
    assert svc.is_suspended("bad")
    svc.reactivate_tenant(actor_user_id="owner1", tenant_id="bad")
    assert not svc.is_suspended("bad")


def test_platform_metrics_requires_platform_owner(monkeypatch) -> None:
    """Normal tenants must not reach global revenue/cost/queue admin surfaces."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    from modules.core import app

    client = TestClient(app)
    r = client.get("/api/platform/metrics")
    assert r.status_code == 401
