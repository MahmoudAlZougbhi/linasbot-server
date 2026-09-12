"""Comment webhook resolve must match the DM allow-set, not binding-id equality."""

from __future__ import annotations

from unittest import mock

from services.meta_app_registry import APP_A_KEY, MetaBindingCredential
from services.meta_comment_events import resolve_registry_comment_events
from tests.test_meta_comment_replies import (
    _binding,
    _facebook_comment_payload,
    _instagram_comment_payload,
    _official_instagram_login_comment_payload,
)


def _app_config() -> mock.MagicMock:
    app_config = mock.MagicMock()
    app_config.key = APP_A_KEY
    app_config.app_id = "2963733803971681"
    app_config.app_secret = "secret"
    app_config.verify_token = "verify"
    app_config.graph_api_version = "v24.0"
    return app_config


def _registry(binding, credential: MetaBindingCredential) -> mock.MagicMock:
    registry = mock.MagicMock()
    registry.get_active_bindings_for_app.return_value = [binding]
    registry.get_credential.return_value = credential
    registry.list_bindings.return_value = []
    return registry


def _facebook_credential() -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token="token",
        token_app_id="2963733803971681",
        token_profile_id="111",
        scopes=("pages_messaging", "pages_read_user_content", "pages_manage_engagement"),
    )


def _instagram_page_linked_credential() -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token="token",
        token_app_id="2963733803971681",
        token_profile_id="222",
        scopes=("instagram_manage_comments", "instagram_manage_messages"),
    )


def test_instagram_comment_resolves_when_instagram_account_id_empty() -> None:
    binding = _binding(channel="instagram", asset_id="222", page_id="", instagram_id="")
    resolved = resolve_registry_comment_events(
        _instagram_comment_payload(ig_id="222"),
        app_config=_app_config(),
        registry=_registry(binding, _instagram_page_linked_credential()),
    )
    assert len(resolved) == 1
    assert resolved[0].event["comment_id"] == "igc1"
    assert resolved[0].binding.asset_id == "222"


def test_official_instagram_comment_resolves_when_instagram_account_id_empty() -> None:
    binding = _binding(channel="instagram", asset_id="222", page_id="", instagram_id="")
    resolved = resolve_registry_comment_events(
        _official_instagram_login_comment_payload(),
        app_config=_app_config(),
        registry=_registry(binding, _instagram_page_linked_credential()),
    )
    assert len(resolved) == 1
    assert resolved[0].event["comment_id"] == "comment-official-1"


def test_instagram_comment_still_rejects_other_account() -> None:
    binding = _binding(channel="instagram", asset_id="222", page_id="", instagram_id="")
    resolved = resolve_registry_comment_events(
        _instagram_comment_payload(ig_id="999"),
        app_config=_app_config(),
        registry=_registry(binding, _instagram_page_linked_credential()),
    )
    assert resolved == []


def test_facebook_comment_still_resolves_when_page_matches_asset() -> None:
    binding = _binding(tenant_id="linas", asset_id="111", page_id="111")
    resolved = resolve_registry_comment_events(
        _facebook_comment_payload(page_id="111"),
        app_config=_app_config(),
        registry=_registry(binding, _facebook_credential()),
    )
    assert len(resolved) == 1
    assert (
        resolve_registry_comment_events(
            _facebook_comment_payload(page_id="999"),
            app_config=_app_config(),
            registry=_registry(binding, _facebook_credential()),
        )
        == []
    )
