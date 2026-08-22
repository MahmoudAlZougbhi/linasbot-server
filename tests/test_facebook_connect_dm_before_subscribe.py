"""Facebook Connect must turn Messages ON before Page webhooks go live."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.channel_capability_toggles import (
    ChannelToggleError,
    enable_channel_defaults_after_connect,
)
from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_activation import ValidatedFacebookPage, activate_validated_facebook_pages
from tests.meta_compliance_helpers import _FakeFirestore


def _registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    import utils.utils

    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    db = _FakeFirestore()
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="facebook-dm-ready-registry-secret-tests-12",
    )


def _credential(page_id: str) -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token="page-token-private",
        token_app_id="2963733803971681",
        token_profile_id=page_id,
        scopes=(
            "pages_manage_engagement",
            "pages_manage_metadata",
            "pages_messaging",
            "pages_read_engagement",
            "pages_read_user_content",
            "pages_show_list",
        ),
        authorized_meta_user_id="123456789",
    )


def _validated_page(page_id: str) -> ValidatedFacebookPage:
    return ValidatedFacebookPage(
        page_id=page_id,
        page_name="Clinic Page",
        instagram_id="",
        instagram_username="",
        channels=("facebook",),
        credential=_credential(page_id),
    )


@pytest.mark.asyncio
async def test_enable_channel_defaults_dm_only_allows_testing_binding(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def _set(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr("services.channel_capability_toggles.set_channel_toggle", _set)
    await enable_channel_defaults_after_connect(
        tenant_id="linas",
        platform="facebook",
        actor="oauth",
        include_comments=False,
    )
    assert len(calls) == 1
    assert calls[0]["toggle"] == "dm"
    assert calls[0]["enabled"] is True
    assert calls[0]["allow_testing_binding"] is True


@pytest.mark.asyncio
async def test_enable_channel_defaults_raises_when_dm_toggle_fails(monkeypatch) -> None:
    async def _set(**_kwargs: Any) -> dict[str, Any]:
        raise ChannelToggleError("Connect this channel first.", status_code=409, code="CONNECT_REQUIRED")

    monkeypatch.setattr("services.channel_capability_toggles.set_channel_toggle", _set)
    with pytest.raises(ChannelToggleError) as exc:
        await enable_channel_defaults_after_connect(
            tenant_id="linas",
            platform="facebook",
            actor="oauth",
            include_comments=False,
        )
    assert exc.value.code == "CONNECT_REQUIRED"


@pytest.mark.asyncio
async def test_facebook_activation_enables_dm_before_subscribe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import meta_oauth_activation

    registry = _registry(tmp_path, monkeypatch)
    order: list[str] = []

    async def inspect(*_args: Any, **_kwargs: Any) -> None:
        order.append("inspect")

    async def enable(**_kwargs: Any) -> None:
        order.append("enable")

    async def subscribe(*_args: Any, **_kwargs: Any) -> None:
        order.append("subscribe")

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(
        "services.channel_capability_toggles.enable_channel_defaults_after_connect",
        enable,
    )
    monkeypatch.setattr(meta_oauth_activation, "subscribe_binding_webhook", subscribe)

    await activate_validated_facebook_pages(
        [_validated_page("378696005334409")],
        tenant_id="linas",
        app_key=APP_A_KEY,
        actor_id="owner",
        registry=registry,
        client=SimpleNamespace(),
    )
    assert order == ["inspect", "enable", "subscribe"]


@pytest.mark.asyncio
async def test_facebook_activation_does_not_subscribe_when_dm_enable_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import meta_oauth_activation

    registry = _registry(tmp_path, monkeypatch)
    subscribed = False

    async def inspect(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def enable(**_kwargs: Any) -> None:
        raise ChannelToggleError("Connect this channel first.", status_code=409, code="CONNECT_REQUIRED")

    async def subscribe(*_args: Any, **_kwargs: Any) -> None:
        nonlocal subscribed
        subscribed = True

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(
        "services.channel_capability_toggles.enable_channel_defaults_after_connect",
        enable,
    )
    monkeypatch.setattr(meta_oauth_activation, "subscribe_binding_webhook", subscribe)

    with pytest.raises(MetaOAuthError, match="Messages could not be enabled"):
        await activate_validated_facebook_pages(
            [_validated_page("378696005334409")],
            tenant_id="linas",
            app_key=APP_A_KEY,
            actor_id="owner",
            registry=registry,
            client=SimpleNamespace(),
        )
    assert subscribed is False
