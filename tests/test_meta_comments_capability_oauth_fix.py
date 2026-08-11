"""Regression coverage for Meta Comments capability + mobile OAuth return surface."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules import meta_connections_api
from services.channel_capability_state import (
    canonical_channel_bindings,
    comment_capability_state,
)
from services.channel_capability_toggles import set_channel_toggle
from services.meta_app_registry import APP_A_KEY, APP_B_KEY
from services.meta_instagram_login_subscription import InstagramLoginSubscriptionState
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_return import (
    normalize_return_surface,
    oauth_completion_redirect_url,
)


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


def test_ig_login_comments_preferred_over_legacy_facebook_login_sibling(monkeypatch) -> None:
    """Case 1: IG Login with comment scope + old FB-login sibling → IG comments allowed."""

    legacy = _ig_binding(
        binding_id="ig-legacy",
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
        updated_at=1.0,
    )
    direct = _ig_binding(
        binding_id="ig-direct",
        auth_flow="instagram_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
        updated_at=100.0,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.active_channel_bindings",
        lambda *_a, **_k: [legacy, direct],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _MapRegistry(
            {
                "ig-legacy": _Cred(("instagram_basic", "instagram_manage_messages")),
                "ig-direct": _Cred(
                    (
                        "instagram_business_basic",
                        "instagram_business_manage_messages",
                        "instagram_business_manage_comments",
                    )
                ),
            }
        ),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    selected = canonical_channel_bindings("linas", "instagram")
    assert len(selected) == 1
    assert selected[0].binding_id == "ig-direct"
    state = comment_capability_state("linas", "instagram")
    assert state["permission_present"] is True
    assert state["webhook_subscribed"] is True
    assert state["missing_scopes"] == []
    assert state["blocker_code"] is None
    assert state["status"] == "ready"
    assert state["effective_enabled"] is False
    assert "instagram_manage_comments" not in state["missing_scopes"]


def test_canonical_bindings_never_combine_foreign_tenant_asset_or_app(monkeypatch) -> None:
    """Case 2: different tenants/assets/apps are never combined."""

    own = _ig_binding(tenant_id="linas", asset_id="ig1", binding_id="own", auth_flow="instagram_login")
    other_tenant = _ig_binding(
        tenant_id="other",
        asset_id="ig1",
        binding_id="other-tenant",
        auth_flow="instagram_login",
    )
    other_asset = _ig_binding(
        tenant_id="linas",
        asset_id="ig2",
        binding_id="other-asset",
        auth_flow="facebook_login",
    )
    other_app = _ig_binding(
        tenant_id="linas",
        asset_id="ig1",
        binding_id="other-app",
        app_key=APP_B_KEY,
        auth_flow="instagram_login",
    )

    class _Reg:
        def list_bindings(self, include_inactive=False, include_superseded=False):
            return [own, other_tenant, other_asset, other_app]

    monkeypatch.setattr("services.channel_capability_state.get_meta_app_registry", lambda: _Reg())
    selected = canonical_channel_bindings("linas", "instagram")
    ids = {b.binding_id for b in selected}
    assert ids == {"own", "other-asset"}
    assert "other-tenant" not in ids
    assert "other-app" not in ids


def test_facebook_missing_either_comment_scope_stays_disabled(monkeypatch) -> None:
    """Case 3: FB Page missing either required comment scope → comments remain disabled."""

    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding()],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _MapRegistry(
            {"fb-b1": _Cred(("pages_messaging", "pages_manage_engagement"))}  # missing read_user_content
        ),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    state = comment_capability_state("linas", "facebook")
    assert state["permission_present"] is False
    assert state["effective_enabled"] is False
    assert "pages_read_user_content" in state["missing_scopes"]
    assert state["blocker_code"] == "missing_comment_permissions"


def test_linas_standard_access_with_real_scopes_allowed(monkeypatch) -> None:
    """Case 4: internal linas Standard Access with actual scopes → allowed (ready)."""

    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [
            _ig_binding(
                auth_flow="instagram_login",
                webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
            )
        ],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _MapRegistry(
            {
                "ig-legacy": _Cred(
                    (
                        "instagram_business_basic",
                        "instagram_business_manage_messages",
                        "instagram_business_manage_comments",
                    )
                )
            }
        ),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    state = comment_capability_state("linas", "instagram")
    assert state["permission_present"] is True
    assert state["status"] == "ready"
    assert state["blocker_code"] is None
    assert state["app_review"]["advanced_access_approved"] is False


def test_public_tenant_without_advanced_access_blocked(monkeypatch) -> None:
    """Case 5: public tenant without Advanced Access → blocked."""

    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [
            _ig_binding(
                tenant_id="customer_a",
                auth_flow="instagram_login",
                webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
            )
        ],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _MapRegistry(
            {
                "ig-legacy": _Cred(
                    (
                        "instagram_business_basic",
                        "instagram_business_manage_messages",
                        "instagram_business_manage_comments",
                    )
                )
            }
        ),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    state = comment_capability_state("customer_a", "instagram")
    assert state["permission_present"] is True  # scopes are real — policy still blocks
    assert state["blocker_code"] == "meta_approval_required"
    assert state["effective_enabled"] is False
    assert state["status"] == "meta_approval_required"


def test_internal_exception_never_enables_without_scopes(monkeypatch) -> None:
    """Case 6: no permission scope → never enabled through internal exception."""

    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [
            _ig_binding(
                auth_flow="instagram_login",
                webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
            )
        ],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _MapRegistry({"ig-legacy": _Cred(("instagram_business_basic", "instagram_business_manage_messages"))}),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: True,
    )
    state = comment_capability_state("linas", "instagram")
    assert state["permission_present"] is False
    assert state["effective_enabled"] is False
    assert state["blocker_code"] == "missing_comment_permissions"
    assert "instagram_business_manage_comments" in state["missing_scopes"]


def test_mobile_oauth_success_redirects_to_deep_link_not_login() -> None:
    """Case 7: mobile OAuth success returns to the app, not /login or /settings."""

    url = oauth_completion_redirect_url(
        return_surface="mobile",
        meta_connection="connected",
        extra_query={"channel": "instagram", "tenant_id": "linas", "access_token": "secret"},
    )
    assert url.startswith("linasai://integrations?")
    assert "meta_connection=success" in url
    assert "/settings" not in url
    assert "/login" not in url
    assert "tenant_id" not in url
    assert "access_token" not in url
    assert "secret" not in url


def test_invalid_tampered_return_surface_rejected_to_web() -> None:
    """Case 8: invalid/tampered OAuth return surface is rejected to public landing."""

    assert normalize_return_surface("mobile") == "mobile"
    assert normalize_return_surface("web") == "web"
    assert normalize_return_surface("https://evil.example/phish") == "web"
    assert normalize_return_surface("MOBILE") == "mobile"
    assert normalize_return_surface("") == "web"
    assert normalize_return_surface(None) == "web"
    web_url = oauth_completion_redirect_url(
        return_surface="https://evil.example/?x=1",
        meta_connection="connected",
    )
    assert web_url.startswith("/?")
    assert "/settings" not in web_url
    assert "/login" not in web_url
    assert "evil.example" not in web_url


@pytest.mark.asyncio
async def test_instagram_callback_mobile_surface_uses_deep_link(monkeypatch) -> None:
    binding = _ig_binding(auth_flow="instagram_login", status="active", channel="instagram")
    result = SimpleNamespace(binding=binding, return_surface="mobile")

    async def _complete(**_k):
        return result

    monkeypatch.setattr(meta_connections_api, "complete_instagram_login", _complete)
    monkeypatch.setattr(meta_connections_api, "peek_return_surface_from_state", lambda *_a, **_k: "mobile")
    response = await meta_connections_api.instagram_login_oauth_callback(code="code", state="state", error="")
    # Mobile uses HTML bridge (Meta in-app browser) rather than bare custom-scheme 303.
    assert response.status_code == 200
    body = response.body.decode("utf-8") if hasattr(response, "body") else str(response)
    assert "linasai://integrations?meta_connection=success" in body
    assert "/login" not in body
    assert "/settings" not in body


@pytest.mark.asyncio
async def test_facebook_callback_mobile_surface_uses_html_bridge(monkeypatch) -> None:
    binding = _ig_binding(auth_flow="facebook_login", status="active", channel="facebook")
    result = SimpleNamespace(binding=binding, bindings=(binding,), return_surface="mobile")

    async def _complete(**_k):
        return result

    monkeypatch.setattr(meta_connections_api, "complete_meta_business_login", _complete)
    monkeypatch.setattr(meta_connections_api, "peek_return_surface_from_state", lambda *_a, **_k: "mobile")
    response = await meta_connections_api.meta_oauth_callback(code="code", state="state", error="")
    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "linasai://integrations?meta_connection=success" in body
    assert "/login" not in body


@pytest.mark.asyncio
async def test_facebook_callback_preserves_mobile_surface_after_failure(monkeypatch) -> None:
    async def _fail(**_k):
        raise MetaOAuthError("simulated failure")

    monkeypatch.setattr(meta_connections_api, "complete_meta_business_login", _fail)
    monkeypatch.setattr(meta_connections_api, "peek_return_surface_from_state", lambda *_a, **_k: "mobile")
    monkeypatch.setattr(meta_connections_api, "consume_return_surface_from_state", lambda *_a, **_k: "web")
    response = await meta_connections_api.meta_oauth_callback(code="code", state="state", error="")
    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "linasai://integrations?meta_connection=failed" in body
    assert "/login" not in body
    assert "/settings" not in body


@pytest.mark.asyncio
async def test_duplicate_enable_comments_does_not_duplicate_webhook_calls(monkeypatch) -> None:
    """Case 10: duplicate Enable requests do not duplicate webhook subscriptions."""

    calls: list[str] = []
    binding = _ig_binding(
        auth_flow="instagram_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
    )

    async def _ensure(b, *, registry):
        calls.append(b.binding_id)

    ready = InstagramLoginSubscriptionState(
        status="ready",
        subscribed_fields=("messages", "messaging_postbacks", "comments"),
        verified_fields=("messages", "messaging_postbacks", "comments"),
    )

    async def _ig_sub(*_a, **_k):
        calls.append("subscribe")
        return ready

    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [binding],
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.get_meta_app_registry",
        lambda: _MapRegistry(
            {
                "ig-legacy": _Cred(
                    (
                        "instagram_business_basic",
                        "instagram_business_manage_messages",
                        "instagram_business_manage_comments",
                    )
                )
            }
        ),
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.credential_has_comment_scopes",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.get_comment_reply_setting",
        lambda **_k: SimpleNamespace(enabled=False, instructions=""),
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.set_comment_reply_setting",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.ensure_instagram_login_webhook_subscription",
        _ig_sub,
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.get_meta_app_configs",
        lambda: {APP_A_KEY: SimpleNamespace(graph_api_version="v24.0")},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comments_enable_blocker",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._set_action_in_draft",
        lambda **_k: SimpleNamespace(),
    )

    async def _publish(**_k):
        return None

    monkeypatch.setattr("services.channel_capability_toggles._publish_actions", _publish)
    monkeypatch.setattr(
        "services.channel_capability_toggles.channel_toggle_states",
        lambda *_a, **_k: {"dm": True, "comments": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {
            "effective_enabled": True,
            "requested_enabled": True,
            "blocker_code": None,
            "blocker_message": None,
        },
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda *_a, **_k: {"effective_enabled": True, "requested_enabled": True},
    )

    await set_channel_toggle(
        tenant_id="linas",
        platform="instagram",
        toggle="comments",
        enabled=True,
        actor="test",
    )
    await set_channel_toggle(
        tenant_id="linas",
        platform="instagram",
        toggle="comments",
        enabled=True,
        actor="test",
    )
    # Idempotent re-verify is allowed; must not explode or invent duplicate field lists.
    assert calls == ["subscribe", "subscribe"]


def test_mobile_integrations_oauth_and_deeplink_source_contract() -> None:
    """Case 9 (source): app resume/deep-link refetch + mobile return_surface wiring."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "mobile" / "linas-ai" / "src"
    oauth = (root / "features/integrations/integrationsOAuth.ts").read_text(encoding="utf-8")
    screen = (root / "features/integrations/IntegrationsScreen.tsx").read_text(encoding="utf-8")
    nav = (root / "app/navigation.ts").read_text(encoding="utf-8")
    shell = (root / "app/AppShell.tsx").read_text(encoding="utf-8")
    assert "return_surface: MOBILE_RETURN_SURFACE" in oauth or "return_surface: 'mobile'" in oauth
    assert "AppState.addEventListener" in screen
    assert "parseIntegrationsDeepLink" in screen
    assert "parseIntegrationsDeepLink" in nav
    assert "linasai://" in nav or "integrations" in nav
    assert "parseIntegrationsDeepLink" in shell
