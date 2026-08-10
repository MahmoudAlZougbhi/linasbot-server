"""Welcome chips + subscription app_access for owner onboarding."""

from __future__ import annotations

from services.entitlements_service import EntitlementsStore, get_tenant_entitlement_public
from services.owner_ai_onboarding import welcome_chips


def test_welcome_chips_new_stage_includes_setup_paths() -> None:
    chips = welcome_chips(setup_stage="new", language="en")
    ids = {c["id"] for c in chips}
    assert "learn_app" in ids
    assert "setup_guided" in ids
    assert "setup_bulk" in ids
    guided = next(c for c in chips if c["id"] == "setup_guided")
    assert guided["mode"] == "work"
    assert "cm_fill_plan" in guided["prompt"]


def test_welcome_chips_fully_configured_hides_setup() -> None:
    chips = welcome_chips(setup_stage="fully_configured", language="en")
    ids = {c["id"] for c in chips}
    assert "setup_guided" not in ids
    assert "setup_bulk" not in ids
    assert "learn_app" in ids


def test_app_access_requires_active_plan(tmp_path, monkeypatch) -> None:
    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    pub = get_tenant_entitlement_public("t-none")
    assert pub["app_access"] is False
    store.set_plan(tenant_id="t1", plan_id="starter", status="active", source="admin")
    pub2 = get_tenant_entitlement_public("t1")
    assert pub2["app_access"] is True
    assert pub2["subscription_required"] is True
