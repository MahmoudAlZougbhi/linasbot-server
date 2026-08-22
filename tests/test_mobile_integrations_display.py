"""Tests for mobile integrations display enrichment."""

from __future__ import annotations

from typing import Any

import pytest

from services.mobile_integrations_display import enrich_mobile_integration_row


def _base_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "platform": "facebook",
        "label": "Facebook",
        "connected": True,
        "toggles": {"dm": True, "comments": False},
        "binding_ids": ["binding-secret"],
        "granted_scopes": ["pages_messaging"],
        "capabilities": {"dm_read": {"level": "connected"}},
        "dm_state": {
            "connection_healthy": True,
            "blocker_code": None,
            "requested_enabled": True,
            "permission_present": True,
            "webhook_subscribed": True,
            "effective_enabled": True,
            "live_verified": True,
        },
        "comments_state": {
            "connection_healthy": True,
            "blocker_code": None,
            "requested_enabled": False,
            "permission_present": True,
            "webhook_subscribed": True,
            "effective_enabled": False,
            "live_verified": False,
        },
    }
    row.update(overrides)
    return row


def test_enrich_strips_technical_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Binding:
        status = "active"
        updated_at = 1_700_000_000.0
        webhook_subscription_checked_at = 1_700_000_100.0
        page_name = "Clinic Page"
        instagram_username = ""

    monkeypatch.setattr(
        "services.mobile_integrations_display.canonical_channel_bindings",
        lambda tenant_id, platform: [_Binding()],
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display.get_meta_app_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display._binding_connection_healthy",
        lambda binding, registry=None: True,
    )

    enriched = enrich_mobile_integration_row(_base_row(), tenant_id="linas")

    assert "binding_ids" not in enriched
    assert "granted_scopes" not in enriched
    assert "capabilities" not in enriched
    assert enriched["connection_status"] == "connected"
    assert enriched["features"] == {"dm_replies": True, "comment_replies": False}
    assert enriched["account"]["display_name"] == "Clinic Page"
    assert enriched["account"]["profile_image_url"] is None
    assert enriched["last_synced_at"] == 1_700_000_100.0


def test_enrich_stays_connected_when_comment_scopes_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Binding:
        status = "active"
        updated_at = 1_700_000_000.0
        webhook_subscription_checked_at = 1_700_000_100.0
        page_name = "Clinic Page"
        instagram_username = ""

    monkeypatch.setattr(
        "services.mobile_integrations_display.canonical_channel_bindings",
        lambda tenant_id, platform: [_Binding()],
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display.get_meta_app_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display._binding_connection_healthy",
        lambda binding, registry=None: True,
    )

    row = _base_row(
        toggles={"dm": True, "comments": True},
        comments_state={
            "connection_healthy": True,
            "blocker_code": "missing_comment_permissions",
            "requested_enabled": True,
            "permission_present": False,
            "webhook_subscribed": False,
            "effective_enabled": False,
            "live_verified": False,
        },
    )
    enriched = enrich_mobile_integration_row(row, tenant_id="linas")
    assert enriched["connection_status"] == "connected"
    assert enriched["toggles"]["comments"] is True


def test_enrich_marks_needs_reconnect_when_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Binding:
        status = "active"
        updated_at = 1_700_000_000.0
        webhook_subscription_checked_at = 0.0
        page_name = "Clinic Page"
        instagram_username = ""

    monkeypatch.setattr(
        "services.mobile_integrations_display.canonical_channel_bindings",
        lambda tenant_id, platform: [_Binding()],
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display.get_meta_app_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display._binding_connection_healthy",
        lambda binding, registry=None: False,
    )

    row = _base_row(
        dm_state={
            "connection_healthy": False,
            "blocker_code": "connection_unhealthy",
            "requested_enabled": True,
            "permission_present": True,
            "webhook_subscribed": True,
            "effective_enabled": False,
            "live_verified": False,
        },
    )
    enriched = enrich_mobile_integration_row(row, tenant_id="linas")
    assert enriched["connection_status"] == "needs_reconnect"
    assert enriched["account"]["connection_status"] == "needs_reconnect"


def test_enrich_instagram_username_display(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Binding:
        status = "active"
        updated_at = 1_700_000_000.0
        webhook_subscription_checked_at = 0.0
        page_name = ""
        instagram_username = "clinic_ig"

    monkeypatch.setattr(
        "services.mobile_integrations_display.canonical_channel_bindings",
        lambda tenant_id, platform: [_Binding()],
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display.get_meta_app_registry",
        lambda: object(),
    )
    monkeypatch.setattr(
        "services.mobile_integrations_display._binding_connection_healthy",
        lambda binding, registry=None: True,
    )

    row = _base_row(platform="instagram", label="Instagram")
    enriched = enrich_mobile_integration_row(row, tenant_id="linas")
    assert enriched["account"]["display_name"] == "@clinic_ig"
    assert enriched["account"]["username"] == "clinic_ig"


def test_enrich_tiktok_omits_null_account() -> None:
    enriched = enrich_mobile_integration_row(
        {
            "platform": "tiktok",
            "label": "TikTok",
            "connected": False,
            "account": None,
            "accounts": [],
            "capabilities": {"comment_read": {"level": "available"}},
        },
        tenant_id="linas",
    )
    assert "account" not in enriched
