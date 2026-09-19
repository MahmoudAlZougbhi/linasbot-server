"""WAVE 4/D: mobile Subscription billing SoT. Live meter is credits."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOBILE_BILLING = ROOT / "mobile/linas-ai/src/features/billing/useBillingData.ts"

# Keys useBillingData.ts reads from GET /api/entitlements/me (entitlement object).
ENTITLEMENT_KEYS = (
    "plan_id",
    "status",
    "current_period_end",
    "included_credits",
    "purchased_credits",
    "extra_credits",
    "pending_downgrade",
    "message_billing_active",
    "included_messages",
    "available_messages",
    "included_remaining",
    "purchased_messages",
)

# Message keys useBillingData.ts also reads from GET /api/mobile/usage.
USAGE_MESSAGE_KEYS = (
    "message_billing_active",
    "included_messages",
    "available_messages",
    "included_remaining",
    "purchased_messages",
)


def test_subscription_ui_reads_entitlements_and_usage() -> None:
    text = MOBILE_BILLING.read_text(encoding="utf-8")
    assert "/api/entitlements/me" in text
    assert "/api/mobile/usage" in text
    assert "/api/public/plans" in text
    for key in USAGE_MESSAGE_KEYS:
        assert key in text, key
    assert "messageBillingActive" in text
    assert "availableMessages" in text


def test_entitlements_and_usage_compose_overlay_message_fields() -> None:
    entitlements = (ROOT / "services/billing/entitlements_service.py").read_text(encoding="utf-8")
    usage_api = (ROOT / "modules/mobile_integrations_api.py").read_text(encoding="utf-8")
    assert "overlay_message_fields" in entitlements
    assert "overlay_message_fields" in usage_api
    assert "get_tenant_entitlement_public" in entitlements


def test_entitlements_public_exposes_subscription_keys(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.billing import entitlements_service as es
    from services.billing.entitlements_service import EntitlementsStore, get_tenant_entitlement_public

    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    store.set_plan(tenant_id="sot-lite", plan_id="lite", status="active", source="admin")
    pub = get_tenant_entitlement_public("sot-lite")
    for key in ENTITLEMENT_KEYS:
        assert key in pub, key
    assert pub["message_billing_active"] is True
    assert pub["included_messages"] == 550
    assert pub["available_messages"] == 550
    assert pub["wallet_unit"] == "messages"
    assert "messages remaining" in pub["speak_as"].lower()


def test_overlay_hides_remaining_until_message_billing_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.dashboard.message_surface import overlay_message_fields

    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    fields = overlay_message_fields("sot-off", "lite")
    for key in USAGE_MESSAGE_KEYS:
        assert key in fields, key
    assert fields["message_billing_active"] is True
    assert fields["available_messages"] is not None
    assert fields["wallet_unit"] == "messages"
