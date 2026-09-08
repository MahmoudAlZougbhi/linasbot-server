"""Instagram Login Send API must use /me user id, not the stored IGSID."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.meta_graph_routing import (
    build_messaging_settings_for_binding,
    instagram_login_send_account_id,
)
from services.meta_messaging import MetaMessagingAdapter, MetaMessagingSettings, resolve_meta_send_account_id

IGSID = "17841413184256533"
LOGIN_USER_ID = "17841400001112223"


def _credential(*, authorized_meta_user_id: str = LOGIN_USER_ID) -> SimpleNamespace:
    return SimpleNamespace(authorized_meta_user_id=authorized_meta_user_id, access_token="ig-token")


def _binding() -> SimpleNamespace:
    return SimpleNamespace(
        instagram_account_id=IGSID,
        asset_id=IGSID,
        page_id="",
        app_key="linas_first_party",
        tenant_id="linas",
        binding_id="bind-1",
        auth_flow="instagram_login",
        channel="instagram",
    )


def test_instagram_login_send_account_prefers_authorized_user_id() -> None:
    assert instagram_login_send_account_id(credential=_credential(), binding=_binding()) == LOGIN_USER_ID


def test_instagram_login_send_account_falls_back_to_igsid() -> None:
    assert (
        instagram_login_send_account_id(credential=_credential(authorized_meta_user_id=""), binding=_binding()) == IGSID
    )


def test_resolve_send_account_uses_login_user_id_not_igsid() -> None:
    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id="",
        page_access_token="token",
        instagram_account_id=IGSID,
        verify_token="verify",
        graph_api_version="v26.0",
        auth_flow="instagram_login",
        graph_base_url="https://graph.instagram.com",
        instagram_login_user_id=LOGIN_USER_ID,
    )
    event = {"account_id": IGSID, "recipient_id": IGSID}
    assert resolve_meta_send_account_id("instagram", event, settings) == LOGIN_USER_ID


def test_resolve_send_account_keeps_igsid_when_login_user_missing() -> None:
    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id="",
        page_access_token="token",
        instagram_account_id=IGSID,
        verify_token="verify",
        graph_api_version="v26.0",
        auth_flow="instagram_login",
        graph_base_url="https://graph.instagram.com",
    )
    event = {"account_id": IGSID, "recipient_id": IGSID}
    assert resolve_meta_send_account_id("instagram", event, settings) == IGSID


def test_production_shaped_ig_login_messages_url_uses_me_id_not_igsid() -> None:
    """Live linas shape: webhook IGSID != Graph /me id. Send must use /me."""

    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id="",
        page_access_token="token",
        instagram_account_id=IGSID,
        verify_token="verify",
        graph_api_version="v26.0",
        auth_flow="instagram_login",
        graph_base_url="https://graph.instagram.com",
        instagram_login_user_id=LOGIN_USER_ID,
    )
    account_id = resolve_meta_send_account_id("instagram", {"account_id": IGSID, "recipient_id": IGSID}, settings)
    adapter = MetaMessagingAdapter(
        access_token="token",
        account_id=account_id,
        channel="instagram",
        graph_api_version="v26.0",
        graph_base_url="https://graph.instagram.com",
    )
    assert adapter.messages_url == f"https://graph.instagram.com/v26.0/{LOGIN_USER_ID}/messages"
    assert IGSID not in adapter.messages_url


def test_facebook_dm_messages_url_stays_on_page_id() -> None:
    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id="378696005334409",
        page_access_token="token",
        instagram_account_id=IGSID,
        verify_token="verify",
        graph_api_version="v24.0",
        auth_flow="facebook_login",
        graph_base_url="https://graph.facebook.com",
        instagram_login_user_id=LOGIN_USER_ID,
    )
    account_id = resolve_meta_send_account_id("facebook", {"account_id": "378696005334409"}, settings)
    adapter = MetaMessagingAdapter(
        access_token="token",
        account_id=account_id,
        channel="facebook",
        graph_api_version="v24.0",
        graph_base_url="https://graph.facebook.com",
    )
    assert adapter.messages_url == "https://graph.facebook.com/v24.0/378696005334409/messages"
    assert LOGIN_USER_ID not in adapter.messages_url


def test_facebook_login_instagram_still_sends_via_page_id() -> None:
    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id="378696005334409",
        page_access_token="token",
        instagram_account_id=IGSID,
        verify_token="verify",
        graph_api_version="v24.0",
        auth_flow="facebook_login",
        instagram_login_user_id=LOGIN_USER_ID,
    )
    event = {"account_id": IGSID}
    assert resolve_meta_send_account_id("instagram", event, settings) == "378696005334409"


@pytest.mark.usefixtures("instagram_login_env")
def test_built_settings_keep_igsid_and_expose_login_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.meta_app_registry import APP_A_KEY, MetaBindingCredential, get_meta_app_configs
    from services.meta_app_registry_common import MetaAssetBinding

    binding = MetaAssetBinding(
        binding_id="b35f221a73fc0000",
        tenant_id="linas",
        channel="instagram",
        asset_id=IGSID,
        page_id="",
        instagram_account_id=IGSID,
        app_key=APP_A_KEY,
        credential_id="cred-1",
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
        auth_flow="instagram_login",
    )
    credential = MetaBindingCredential(
        access_token="ig-login-token",
        token_app_id="1035856539045307",
        token_profile_id=IGSID,
        scopes=("instagram_business_basic", "instagram_business_manage_messages"),
        authorized_meta_user_id=LOGIN_USER_ID,
        auth_flow="instagram_login",
    )
    settings = build_messaging_settings_for_binding(
        binding,
        credential=credential,
        app_config=get_meta_app_configs()[APP_A_KEY],
    )
    assert settings.instagram_account_id == IGSID
    assert settings.instagram_login_user_id == LOGIN_USER_ID
    assert resolve_meta_send_account_id("instagram", {"account_id": IGSID}, settings) == LOGIN_USER_ID


@pytest.fixture
def instagram_login_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_A_ENABLED", "true")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
