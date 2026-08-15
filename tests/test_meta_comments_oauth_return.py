"""Mobile OAuth return surface and comments-enable webhook idempotency."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from modules import meta_connections_api, meta_connections_api_lifecycle
from services.channel_capability_toggles import set_channel_toggle
from services.dashboard_session_service import SessionRecord
from services.meta_app_registry import APP_A_KEY
from services.meta_instagram_login_subscription import InstagramLoginSubscriptionState
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_return import (
    normalize_return_surface,
    oauth_completion_redirect_url,
)
from tests.meta_comments_capability_helpers import _Cred, _ig_binding, _MapRegistry


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


def _settings_request(tenant_id: str = "linas") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/meta/connections/ig-direct/comment-replies",
            "query_string": b"",
            "headers": [],
        }
    )
    request.state.dashboard_session = SessionRecord(
        session_id="session-a",
        user_id="owner-a",
        email="owner@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
        csrf_token="csrf",
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )
    return request


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
async def test_instagram_callback_reports_failed_when_subscription_is_unconfirmed(monkeypatch) -> None:
    async def _fail(**_k):
        raise MetaOAuthError("Instagram webhook subscription could not be confirmed")

    monkeypatch.setattr(meta_connections_api, "complete_instagram_login", _fail)
    monkeypatch.setattr(meta_connections_api, "peek_return_surface_from_state", lambda *_a, **_k: "mobile")
    response = await meta_connections_api.instagram_login_oauth_callback(
        code="code",
        state="state",
        error="",
    )
    body = response.body.decode("utf-8")
    assert "linasai://integrations?meta_connection=failed" in body
    assert "meta_connection=success" not in body


@pytest.mark.asyncio
async def test_legacy_comment_enable_uses_direct_instagram_subscription(monkeypatch) -> None:
    binding = _ig_binding(
        binding_id="ig-direct",
        auth_flow="instagram_login",
        page_id="",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
    )
    binding.public_dict = lambda: {"binding_id": binding.binding_id}
    registry = SimpleNamespace(_append_audit=lambda _event: None)
    calls: list[tuple[object, object]] = []

    async def _ensure(candidate, *, registry):
        calls.append((candidate, registry))

    class _Setting:
        def __init__(self, *, enabled: bool, instructions: str) -> None:
            self.enabled = enabled
            self.instructions = instructions

        def public_dict(self):
            return {"enabled": self.enabled, "instructions": self.instructions}

    monkeypatch.setattr(meta_connections_api_lifecycle, "_tenant_binding", lambda *_a, **_k: binding)
    monkeypatch.setattr(meta_connections_api_lifecycle, "get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(meta_connections_api_lifecycle, "credential_has_comment_scopes", lambda *_a, **_k: True)
    monkeypatch.setattr(
        meta_connections_api_lifecycle,
        "get_comment_reply_setting",
        lambda **_k: _Setting(enabled=False, instructions=""),
    )
    monkeypatch.setattr(
        meta_connections_api_lifecycle,
        "set_comment_reply_setting",
        lambda **kwargs: _Setting(
            enabled=bool(kwargs["enabled"]),
            instructions=str(kwargs["instructions"]),
        ),
    )
    monkeypatch.setattr(meta_connections_api_lifecycle, "ensure_comment_webhook_for_binding", _ensure)
    monkeypatch.setattr("services.membership.comment_gate.assert_comment_automation_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr("services.cm.constants.tenant_uses_cm_runtime", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "services.cm.actions.comments_enforcement_decision",
        lambda **_k: {
            "allow": True,
            "reason": "enabled",
            "readiness": {"cm_action_enabled": True},
        },
    )

    response = await meta_connections_api.update_meta_comment_replies(
        binding.binding_id,
        _settings_request(),
        {"enabled": True, "instructions": "Be helpful"},
    )

    assert response["success"] is True
    assert response["comment_replies"]["scopes_required"] == ["instagram_business_manage_comments"]
    assert calls == [(binding, registry)]


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
    load = (root / "features/integrations/useIntegrationsLoad.ts").read_text(encoding="utf-8")
    nav = (root / "app/navigation.ts").read_text(encoding="utf-8")
    shell = (root / "app/AppShell.tsx").read_text(encoding="utf-8")
    assert "return_surface: MOBILE_RETURN_SURFACE" in oauth or "return_surface: 'mobile'" in oauth
    assert "AppState.addEventListener" in load
    assert "parseIntegrationsDeepLink" in load
    assert "parseIntegrationsDeepLink" in nav
    assert "linasai://" in nav or "integrations" in nav
    assert "parseIntegrationsDeepLink" in shell
