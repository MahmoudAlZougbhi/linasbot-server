"""Pending downgrade scheduling at period end."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.apple_iap_effects import apply_subscription_effect
from services.entitlements_service import EntitlementsStore, apply_store_notification
from services.subscription_downgrade import (
    is_downgrade,
    schedule_pending_downgrade,
    should_schedule_instead_of_apply,
)


@pytest.fixture()
def ent_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EntitlementsStore:
    store = EntitlementsStore(root=tmp_path / "entitlements")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.apple_iap_effects.entitlements_store", store)
    monkeypatch.setattr("services.subscription_downgrade.entitlements_store", store)
    return store


def test_is_downgrade_ranking() -> None:
    assert is_downgrade("max", "lite") is True
    assert is_downgrade("pro", "growth") is True
    assert is_downgrade("growth", "pro") is False
    assert is_downgrade("lite", "starter") is False


def test_should_schedule_on_client_verify_not_on_renewal() -> None:
    assert should_schedule_instead_of_apply(
        current_plan_id="pro",
        target_plan_id="starter",
        status="active",
        notification_type=None,
    )
    assert not should_schedule_instead_of_apply(
        current_plan_id="pro",
        target_plan_id="starter",
        status="active",
        notification_type="DID_RENEW",
    )


def test_apply_subscription_effect_schedules_downgrade_without_plan_swap(ent_store: EntitlementsStore) -> None:
    ent_store.set_plan(
        tenant_id="t1",
        plan_id="pro",
        status="active",
        source="apple",
        store_original_transaction_id="orig_1",
        period_days=30,
    )
    ent = ent_store.get("t1")
    ent.current_period_end = time.time() + 15 * 86400
    ent_store.save(ent)

    effect = apply_subscription_effect(
        tenant_id="t1",
        product_id="com.linasai.subscription.plus.monthly",
        original_transaction_id="orig_1",
        status="active",
        idempotency_key="test:downgrade:1",
    )

    assert effect.get("scheduled_downgrade") is True
    after = ent_store.get("t1")
    assert after.plan_id == "pro"
    assert after.pending_plan_id == "starter"
    assert after.pending_plan_effective_at is not None


def test_apply_subscription_effect_upgrade_clears_pending(ent_store: EntitlementsStore) -> None:
    ent_store.set_plan(
        tenant_id="t2",
        plan_id="starter",
        status="active",
        source="apple",
        store_original_transaction_id="orig_2",
    )
    schedule_pending_downgrade(
        tenant_id="t2",
        pending_plan_id="lite",
        effective_at=time.time() + 86400,
    )

    apply_subscription_effect(
        tenant_id="t2",
        product_id="com.linasai.subscription.pro.monthly",
        original_transaction_id="orig_2",
        status="active",
        idempotency_key="test:upgrade:1",
    )

    after = ent_store.get("t2")
    assert after.plan_id == "pro"
    assert after.pending_plan_id is None


def test_schedule_downgrade_keeps_current_plan(ent_store: EntitlementsStore) -> None:
    ent_store.set_plan(
        tenant_id="t4",
        plan_id="growth",
        status="active",
        source="apple",
        store_original_transaction_id="orig_4",
    )
    ent = ent_store.get("t4")
    ent.current_period_end = time.time() + 20 * 86400
    ent_store.save(ent)

    pending = schedule_pending_downgrade(
        tenant_id="t4",
        pending_plan_id="starter",
        effective_at=ent.current_period_end,
    )
    assert pending is not None
    assert pending["plan_id"] == "starter"
    after = ent_store.get("t4")
    assert after.plan_id == "growth"
    assert after.pending_plan_id == "starter"


def test_renewal_applies_downgraded_plan(ent_store: EntitlementsStore) -> None:
    ent_store.set_plan(
        tenant_id="t3",
        plan_id="max",
        status="active",
        source="apple",
        store_original_transaction_id="orig_3",
    )
    schedule_pending_downgrade(
        tenant_id="t3",
        pending_plan_id="growth",
        effective_at=time.time() + 86400,
    )

    apply_subscription_effect(
        tenant_id="t3",
        product_id="com.linasai.subscription.growth.monthly",
        original_transaction_id="orig_3",
        status="active",
        idempotency_key="test:renew:1",
        notification_type="DID_RENEW",
    )

    after = ent_store.get("t3")
    assert after.plan_id == "growth"
    assert after.pending_plan_id is None


def test_apply_store_notification_schedules_downgrade(ent_store: EntitlementsStore) -> None:
    ent_store.set_plan(
        tenant_id="biz",
        plan_id="growth",
        status="active",
        source="apple",
        store_original_transaction_id="orig_5",
    )
    ent = ent_store.get("biz")
    ent.current_period_end = 1_800_000_000.0
    ent_store.save(ent)

    result = apply_store_notification(
        tenant_id="biz",
        plan_id="starter",
        status="active",
        source="apple",
        original_transaction_id="orig_5",
        idempotency_key="test-downgrade-key-001",
    )
    saved = ent_store.get("biz")
    assert result.get("scheduled_downgrade") is True
    assert saved.plan_id == "growth"
    assert saved.pending_plan_id == "starter"
