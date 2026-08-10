"""Welcome chips + subscription app_access for owner onboarding."""

from __future__ import annotations

from services.entitlements_service import (
    EntitlementsStore,
    get_tenant_entitlement_public,
    is_subscription_exempt_tenant,
    tenant_has_app_access,
)
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
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")
    pub = get_tenant_entitlement_public("t-none")
    assert pub["app_access"] is False
    assert pub["subscription_exempt"] is False
    assert pub["subscription_required"] is True
    store.set_plan(tenant_id="t1", plan_id="starter", status="active", source="admin")
    pub2 = get_tenant_entitlement_public("t1")
    assert pub2["app_access"] is True
    assert pub2["subscription_required"] is True
    assert pub2["subscription_exempt"] is False


def test_linas_laser_tenant_exempt_from_subscription_without_plan(tmp_path, monkeypatch) -> None:
    """Linas Laser (tenant_id=linas) gets app_access via explicit allowlist only."""
    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.delenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", raising=False)
    assert is_subscription_exempt_tenant("linas")
    assert tenant_has_app_access("linas") is True
    pub = get_tenant_entitlement_public("linas")
    assert pub["app_access"] is True
    assert pub["subscription_exempt"] is True
    assert pub["subscription_required"] is False
    assert pub["plan_id"] == "none"
    # Other tenants stay gated.
    assert is_subscription_exempt_tenant("acme-co") is False
    assert tenant_has_app_access("acme-co") is False


def test_subscription_exempt_allowlist_is_explicit(tmp_path, monkeypatch) -> None:
    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "clinic-x")
    assert is_subscription_exempt_tenant("clinic-x")
    assert tenant_has_app_access("clinic-x") is True
    assert is_subscription_exempt_tenant("linas") is False
    assert tenant_has_app_access("linas") is False
    pub = get_tenant_entitlement_public("clinic-x")
    assert pub["subscription_exempt"] is True
    assert pub["app_access"] is True


def test_entitlements_public_survives_faq_errors(tmp_path, monkeypatch) -> None:
    """FAQ enrichment failure must not 500 entitlements/me (mobile fail-closes)."""
    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.delenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", raising=False)

    def _boom(_tenant_id: str):
        raise RuntimeError("faq store unavailable")

    monkeypatch.setattr("services.faq_entitlements.get_faq_entitlement", _boom)
    pub = get_tenant_entitlement_public("linas")
    assert pub["app_access"] is True
    assert pub["subscription_exempt"] is True
    assert pub["faq_enabled"] is False
