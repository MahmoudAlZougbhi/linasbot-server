"""Regression coverage for Meta Comments capability selection and blockers."""

from __future__ import annotations

from services.channel_capability_state import (
    canonical_channel_bindings,
    comment_capability_state,
)
from services.meta_app_registry import APP_B_KEY
from tests.meta_comments_capability_helpers import _Cred, _fb_binding, _ig_binding, _MapRegistry


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


def test_app_a_approval_never_unlocks_dedicated_instagram_app(monkeypatch) -> None:
    """Each Meta App Review decision unlocks only its own signing domain."""

    binding = _ig_binding(
        tenant_id="customer_a",
        auth_flow="instagram_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [binding],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _MapRegistry(
            {
                binding.binding_id: _Cred(
                    (
                        "instagram_business_basic",
                        "instagram_business_manage_messages",
                        "instagram_business_manage_comments",
                    )
                )
            }
        ),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: True)
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "false")

    blocked = comment_capability_state("customer_a", "instagram")

    assert blocked["blocker_code"] == "meta_approval_required"
    assert blocked["app_review"] == {
        "advanced_access_approved": False,
        "approval_domain": "instagram_login",
        "scopes_required": ["instagram_business_manage_comments"],
        "scopes_missing": [],
        "live_verified": False,
    }

    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "true")
    ready = comment_capability_state("customer_a", "instagram")
    assert ready["status"] == "ready"
    assert ready["app_review"]["advanced_access_approved"] is True


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
