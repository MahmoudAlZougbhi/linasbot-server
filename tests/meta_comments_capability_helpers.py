"""Builders for Meta comments capability and OAuth-return tests."""

from __future__ import annotations

from types import SimpleNamespace

from services.meta_app_registry import APP_A_KEY


def _fb_binding(**kwargs):
    base = dict(
        tenant_id="linas",
        channel="facebook",
        status="active",
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
        asset_id="page1",
        binding_id="fb-b1",
        page_id="page1",
        updated_at=10.0,
        created_at=10.0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ig_binding(**kwargs):
    base = dict(
        tenant_id="linas",
        channel="instagram",
        status="active",
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
        asset_id="ig1",
        binding_id="ig-legacy",
        page_id="page1",
        updated_at=5.0,
        created_at=5.0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class _Cred:
    def __init__(self, scopes, *, token="tok", expires_at=None):
        self.scopes = scopes
        self.access_token = token
        self.expires_at = expires_at


class _MapRegistry:
    def __init__(self, by_id: dict[str, _Cred]):
        self._by_id = by_id

    def get_credential(self, binding):
        return self._by_id[binding.binding_id]
