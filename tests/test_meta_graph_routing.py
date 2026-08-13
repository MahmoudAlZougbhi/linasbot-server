"""Graph routing and cross-flow deduplication tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential, get_meta_graph_api_version
from services.meta_cross_flow_dedup import global_dm_claim_key
from services.meta_graph_routing import (
    graph_api_url,
    graph_base_url_for_binding,
    required_comment_scopes_for_binding,
    required_publish_scopes_for_binding,
)
from services.meta_instagram_login_capabilities import (
    binding_ready_for_dm,
    select_instagram_binding_for_capability,
)
from services.meta_instagram_login_subscription_recovery import (
    reconcile_pending_instagram_login_subscriptions,
    retry_instagram_login_webhook_subscription,
)
from services.meta_multi_app_router import registry_auth_flow_for_webhook_object, resolve_registry_events
from services.meta_social_publish import publish_instagram_post

INSTAGRAM_ID = "17840000999900021"
MESSAGING_SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
    "instagram_business_content_publish",
)


@pytest.fixture
def instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-routing-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-routing-secret-tests-1234567890",
    )


def _instagram_binding(
    registry: MetaAppRegistry,
    *,
    auth_flow: str,
    webhook_status: str = "ready",
) -> object:
    return registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="112233" if auth_flow == "facebook_login" else "",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="token-a" if auth_flow == "facebook_login" else "token-b",
            token_app_id="2963733803971681" if auth_flow == "facebook_login" else "1035856539045307",
            token_profile_id="112233" if auth_flow == "facebook_login" else INSTAGRAM_ID,
            scopes=MESSAGING_SCOPES
            if auth_flow == "instagram_login"
            else ("instagram_basic", "instagram_manage_messages"),
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="998877",
            auth_flow=auth_flow,
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow=auth_flow,
        webhook_subscription_status=webhook_status,
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
    )


def test_instagram_login_scopes_exclude_insights() -> None:
    from services.meta_instagram_login_config import META_INSTAGRAM_LOGIN_REQUEST_SCOPES

    assert "instagram_business_manage_insights" not in META_INSTAGRAM_LOGIN_REQUEST_SCOPES
    assert "instagram_business_content_publish" in META_INSTAGRAM_LOGIN_REQUEST_SCOPES


def test_graph_routing_uses_instagram_host_for_direct_login(registry: MetaAppRegistry) -> None:
    binding = _instagram_binding(registry, auth_flow="instagram_login")
    version = get_meta_graph_api_version()
    assert graph_base_url_for_binding(binding) == "https://graph.instagram.com"
    assert graph_api_url(binding, graph_api_version=version, path=f"{INSTAGRAM_ID}/messages").startswith(
        f"https://graph.instagram.com/{version}/"
    )
    assert required_comment_scopes_for_binding(binding) == frozenset({"instagram_business_manage_comments"})
    assert required_publish_scopes_for_binding(binding) == frozenset({"instagram_business_content_publish"})


def test_select_instagram_binding_prefers_direct_login_for_dm(registry: MetaAppRegistry) -> None:
    _instagram_binding(registry, auth_flow="facebook_login")
    direct = _instagram_binding(registry, auth_flow="instagram_login")
    bindings = list(registry.list_bindings(include_inactive=False))
    selected = select_instagram_binding_for_capability(bindings, "dm", registry=registry)
    assert selected is not None
    assert selected.binding_id == direct.binding_id


@pytest.mark.asyncio
async def test_resolve_registry_events_prefers_instagram_login_binding(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _instagram_binding(registry, auth_flow="facebook_login")
    _instagram_binding(registry, auth_flow="instagram_login")
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": INSTAGRAM_ID,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": INSTAGRAM_ID},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "mid-dup", "text": "hello"},
                    }
                ],
            }
        ],
    }
    routed = await resolve_registry_events(
        payload,
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow="instagram_login",
    )
    assert len(routed) == 1
    assert routed[0].binding.auth_flow == "instagram_login"
    assert routed[0].settings.graph_base_url == "https://graph.instagram.com"


@pytest.mark.asyncio
async def test_publish_instagram_post_uses_graph_instagram_host(registry: MetaAppRegistry, tmp_path: Path) -> None:
    _instagram_binding(registry, auth_flow="instagram_login")
    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    media_path = tmp_path / "photo.jpg"
    media_path.write_bytes(b"fakejpeg")
    captured: list[str] = []
    version = get_meta_graph_api_version()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "container-1"})
        if "container-1" in request.url.path:
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if request.url.path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "published-1"})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=f"https://graph.instagram.com/{version}"
    )
    with patch("services.meta_social_publish.public_media_url", return_value="https://example.com/media.jpg"):
        result = await publish_instagram_post(
            binding,
            tenant_id="tenant-a",
            caption="hello",
            media_path=media_path,
            registry=registry,
            client=client,
        )
    assert result.success is True
    assert any(url.startswith(f"https://graph.instagram.com/{version}/") for url in captured)


@pytest.mark.asyncio
async def test_reconcile_pending_subscription_recovers_failed_binding(registry: MetaAppRegistry) -> None:
    binding = _instagram_binding(registry, auth_flow="instagram_login", webhook_status="failed")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"data": [{"subscribed_fields": ["messages", "messaging_postbacks"]}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://graph.instagram.com")
    state = await retry_instagram_login_webhook_subscription(binding.binding_id, registry=registry, client=client)
    assert state.ready_for_dm is True
    with patch("services.meta_instagram_login_lifecycle.try_acquire_job_lock", return_value=True):
        with patch("services.meta_instagram_login_lifecycle.release_job_lock"):
            recovered = await reconcile_pending_instagram_login_subscriptions(registry=registry, limit=5)
    assert recovered == 0
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.webhook_subscription_status in {"ready", "partial"}
    assert refreshed.webhook_subscribed_fields and "messages" in refreshed.webhook_subscribed_fields


def test_global_dm_claim_key_is_auth_flow_agnostic() -> None:
    event = {"channel": "instagram", "account_id": INSTAGRAM_ID, "message_id": "mid-1"}
    assert global_dm_claim_key(event) == f"instagram:{INSTAGRAM_ID}:mid-1"


def test_facebook_login_binding_ready_for_dm_when_no_direct_login(registry: MetaAppRegistry) -> None:
    binding = _instagram_binding(registry, auth_flow="facebook_login")
    credential = registry.get_credential(binding)
    assert binding_ready_for_dm(binding, credential) is True


def test_registry_auth_flow_unrestricted_for_instagram_object() -> None:
    assert registry_auth_flow_for_webhook_object("instagram") is None
    assert registry_auth_flow_for_webhook_object("page") == "facebook_login"


def _instagram_dm_payload(account_id: str, *, mid: str = "mid-1") -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": account_id,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": account_id},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": mid, "text": "hello"},
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_resolve_unrestricted_accepts_instagram_login_binding(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _instagram_binding(registry, auth_flow="instagram_login")
    routed = await resolve_registry_events(
        _instagram_dm_payload(INSTAGRAM_ID),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow=registry_auth_flow_for_webhook_object("instagram"),
    )
    assert len(routed) == 1
    assert routed[0].binding.auth_flow == "instagram_login"


@pytest.mark.asyncio
async def test_resolve_unrestricted_accepts_facebook_login_legacy_binding(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _instagram_binding(registry, auth_flow="facebook_login")
    routed = await resolve_registry_events(
        _instagram_dm_payload(INSTAGRAM_ID),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow=registry_auth_flow_for_webhook_object("instagram"),
    )
    assert len(routed) == 1
    assert routed[0].binding.auth_flow == "facebook_login"


@pytest.mark.asyncio
async def test_resolve_unrestricted_rejects_wrong_instagram_account(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _instagram_binding(registry, auth_flow="instagram_login")
    routed = await resolve_registry_events(
        _instagram_dm_payload("17840000000000000"),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow=registry_auth_flow_for_webhook_object("instagram"),
    )
    assert routed == []


@pytest.mark.asyncio
async def test_facebook_login_filter_drops_instagram_login_only_binding(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _instagram_binding(registry, auth_flow="instagram_login")
    routed = await resolve_registry_events(
        _instagram_dm_payload(INSTAGRAM_ID),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow="facebook_login",
    )
    assert routed == []
