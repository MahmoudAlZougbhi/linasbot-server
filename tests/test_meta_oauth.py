"""Meta App A Business Login security and asset-validation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaOAuthStateError,
)
from services.meta_oauth import (
    MetaOAuthError,
    begin_meta_business_login,
    complete_meta_business_login,
    normalize_oauth_flow_channel,
)

SCOPES = [
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
]


@pytest.fixture
def oauth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_B_ID", "998877665544")
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-tests")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b-tests")
    monkeypatch.setenv("META_APP_A_LOGIN_CONFIG_ID", "business-login-config-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_OAUTH_REDIRECT_URI", "https://www.linasaibot.com/oauth/meta/callback")


@pytest.fixture
def registry(tmp_path: Path, oauth_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="oauth-registry-master-secret-tests-1234567890",
    )


def _start_state(registry: MetaAppRegistry, *, channel: str = "facebook") -> str:
    url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel=channel,  # type: ignore[arg-type]
        actor_id="owner-a",
        registry=registry,
    )
    query = parse_qs(urlparse(url).query)
    return query["state"][0]


def _transport(
    *,
    page_id: str = "445566778899",
    instagram_id: str = "17840000123456789",
    wrong_app: bool = False,
    extra_target: bool = False,
    page_type: str = "PAGE",
    observed_requests: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        if observed_requests is not None:
            observed_requests.append(request)
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "integration-token-private"})
        if path.endswith("/debug_token"):
            inspected = request.url.params.get("input_token")
            data: dict[str, Any] = {
                "is_valid": True,
                "app_id": "000000000000" if wrong_app else "2963733803971681",
                "scopes": SCOPES,
                "expires_at": 4102444800,
                "user_id": "112233445566",
            }
            if inspected == "page-token-private":
                data["profile_id"] = page_id
                data["type"] = page_type
                target_ids = [page_id, "000111222"] if extra_target else [page_id]
                data["granular_scopes"] = [{"scope": scope, "target_ids": target_ids} for scope in SCOPES]
            return httpx.Response(200, json={"data": data})
        if path.endswith("/me/accounts"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": page_id,
                            "name": "Authorized Clinic",
                            "access_token": "page-token-private",
                            "instagram_business_account": {
                                "id": instagram_id,
                                "username": "authorized_clinic",
                            },
                        }
                    ]
                },
            )
        if path.endswith("/subscribed_apps") and request.method == "POST":
            body = (await request.aread()).decode("utf-8")
            assert "messages%2Cmessaging_postbacks" in body or "messages%2Cmessaging_postbacks" in str(request.content)
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_oauth_flow_channel_keeps_facebook_and_instagram_separate() -> None:
    assert normalize_oauth_flow_channel("instagram") == "instagram"
    assert normalize_oauth_flow_channel("facebook") == "facebook"
    assert normalize_oauth_flow_channel("unified") == "unified"
    assert normalize_oauth_flow_channel("meta") == "unified"
    assert normalize_oauth_flow_channel("") == "unified"


def test_business_login_url_uses_config_id_rerequests_comment_scopes(registry: MetaAppRegistry) -> None:
    url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel="facebook",
        actor_id="owner-a",
        registry=registry,
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.hostname == "www.facebook.com"
    assert query["config_id"] == ["business-login-config-tests"]
    assert query["client_id"] == ["2963733803971681"]
    assert query["redirect_uri"] == ["https://www.linasaibot.com/oauth/meta/callback"]
    assert query["response_type"] == ["code"]
    assert query["override_default_response_type"] == ["true"]
    assert query["auth_type"] == ["rerequest"]
    assert query["state"]
    scopes = set((query.get("scope") or [""])[0].split(","))
    assert "pages_messaging" in scopes
    assert "pages_read_user_content" in scopes
    assert "pages_manage_engagement" in scopes
    # Facebook Manage Meta Access must not bundle Instagram comment scopes.
    assert "instagram_manage_comments" not in scopes
    assert "app-b-secret-tests" not in url
    assert "business_management" not in url
    assert "owner-a" not in registry.store_path.read_text(encoding="utf-8")


def test_instagram_business_login_url_can_request_instagram_comment_scope(registry: MetaAppRegistry) -> None:
    url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel="instagram",
        actor_id="owner-a",
        registry=registry,
    )
    scopes = set((parse_qs(urlparse(url).query).get("scope") or [""])[0].split(","))
    assert "instagram_manage_comments" in scopes
    assert "pages_manage_engagement" not in scopes
    assert "pages_read_user_content" not in scopes


@pytest.mark.asyncio
async def test_external_page_login_inspects_encrypts_and_activates_with_subscription(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    observed_requests: list[httpx.Request] = []
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(observed_requests=observed_requests),
    ) as client:
        result = await complete_meta_business_login(
            code="single-use-code",
            state=state,
            registry=registry,
            client=client,
        )
    assert result.binding.status == "active"
    assert result.binding.app_key == APP_A_KEY
    assert result.binding.tenant_id == "tenant-a"
    facebook_bindings = [item for item in result.bindings if item.channel == "facebook"]
    instagram_bindings = [item for item in result.bindings if item.channel == "instagram"]
    assert len(facebook_bindings) == 1
    # Facebook-only Manage Meta Access must not auto-bind Instagram (IG Login is separate).
    assert len(instagram_bindings) == 0
    stored = registry.store_path.read_text(encoding="utf-8")
    assert "page-token-private" not in stored
    assert "single-use-code" not in stored
    credential = registry.get_credential(result.binding)
    assert credential.token_app_id == "2963733803971681"
    assert set(SCOPES).issubset(credential.scopes)
    assert credential.authorized_meta_user_id == "112233445566"
    assert "112233445566" not in stored
    assert any(request.url.path.endswith("/subscribed_apps") for request in observed_requests)
    token_exchange = next(request for request in observed_requests if request.url.path.endswith("/oauth/access_token"))
    assert token_exchange.method == "POST"


@pytest.mark.asyncio
async def test_instagram_login_resolves_linked_professional_account(registry: MetaAppRegistry) -> None:
    state = _start_state(registry, channel="instagram")
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        result = await complete_meta_business_login(
            code="ig-code",
            state=state,
            registry=registry,
            client=client,
        )
    assert result.binding.status == "active"
    instagram_binding = next(item for item in result.bindings if item.channel == "instagram")
    assert instagram_binding.channel == "instagram"
    assert instagram_binding.asset_id == "17840000123456789"
    assert instagram_binding.instagram_account_id == "17840000123456789"
    instagram_bindings = [item for item in result.bindings if item.channel == "instagram"]
    assert len(instagram_bindings) == 1


@pytest.mark.asyncio
async def test_lina_page_connect_activates_and_subscribes(registry: MetaAppRegistry) -> None:
    state = _start_state(registry, channel="facebook")
    requests: list[str] = []
    base_transport = _transport(page_id="378696005334409", instagram_id="17841413184256533")

    async def record(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return await base_transport.handle_async_request(request)

    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=httpx.MockTransport(record),
    ) as client:
        result = await complete_meta_business_login(
            code="review-demo-code",
            state=state,
            registry=registry,
            client=client,
        )
    assert result.binding.status == "active"
    assert result.binding.app_key == APP_A_KEY
    assert any(path.endswith("/subscribed_apps") for path in requests)


@pytest.mark.asyncio
async def test_wrong_app_token_is_rejected_without_binding(registry: MetaAppRegistry) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(wrong_app=True),
    ) as client:
        with pytest.raises(MetaOAuthError, match="does not belong"):
            await complete_meta_business_login(
                code="bad-app-code",
                state=state,
                registry=registry,
                client=client,
            )
    assert registry.list_bindings() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport", "message"),
    [
        (_transport(extra_target=True), "another asset"),
        (_transport(page_type="USER"), "not a Page access token"),
    ],
)
async def test_wrong_token_type_or_extra_granular_target_is_rejected(
    registry: MetaAppRegistry,
    transport: httpx.MockTransport,
    message: str,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=transport,
    ) as client:
        with pytest.raises(MetaOAuthError, match=message):
            await complete_meta_business_login(
                code="invalid-page-token-code",
                state=state,
                registry=registry,
                client=client,
            )
    assert registry.list_bindings() == []


@pytest.mark.asyncio
async def test_oauth_state_replay_is_rejected(registry: MetaAppRegistry) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        await complete_meta_business_login(
            code="first-code",
            state=state,
            registry=registry,
            client=client,
        )
        with pytest.raises(MetaOAuthStateError):
            await complete_meta_business_login(
                code="replay-code",
                state=state,
                registry=registry,
                client=client,
            )
    assert "integration-token-private" not in json.dumps(
        [binding.public_dict() for binding in registry.list_bindings()]
    )
