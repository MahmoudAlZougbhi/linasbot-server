"""FB vs IG comment capability gates must not cross-bundle scopes."""

from __future__ import annotations

from types import SimpleNamespace

from services.channel_capability_state import comment_capability_state
from services.meta_app_registry import APP_A_KEY
from services.meta_oauth import _business_login_request_scopes, normalize_oauth_flow_channel


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


def test_facebook_oauth_scopes_exclude_instagram_manage_comments() -> None:
    assert normalize_oauth_flow_channel("facebook") == "facebook"
    scopes = set(_business_login_request_scopes("facebook").split(","))
    assert "pages_read_user_content" in scopes
    assert "pages_manage_engagement" in scopes
    assert "instagram_manage_comments" not in scopes
    assert "instagram_business_manage_comments" not in scopes


def test_facebook_comment_blocker_message_excludes_instagram_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding()],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _MapRegistry({"fb-b1": _Cred(("pages_messaging",))}),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr("services.channel_capability_state._action_requested", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    state = comment_capability_state("linas", "facebook")
    assert state["permission_present"] is False
    assert state["blocker_code"] == "missing_comment_permissions"
    assert "pages_read_user_content" in (state["blocker_message"] or "")
    assert "pages_manage_engagement" in (state["blocker_message"] or "")
    assert "instagram_manage_comments" not in (state["blocker_message"] or "")
    assert "instagram_manage_comments" not in state["missing_scopes"]
