"""Meta Business Login scope, grant, and replay tests."""

from __future__ import annotations

import json

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
)
from services.meta_oauth_graph import restore_binding_webhook_subscription
from tests.meta_oauth_support import (
    PAGE_SCOPES,
    _start_state,
    _transport,
)

pytest_plugins = ("tests.meta_oauth_support",)


@pytest.mark.asyncio
async def test_webhook_compensation_refuses_state_not_owned_by_callback(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        connected = await complete_meta_business_login(
            code="cas-baseline-code",
            state=state,
            registry=registry,
            client=client,
        )

    requests: list[httpx.Request] = []

    async def changed_state_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path.endswith("/subscribed_apps"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "2963733803971681",
                            "subscribed_fields": ["feed", "mention", "messages", "messaging_postbacks"],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=httpx.MockTransport(changed_state_handler),
    ) as client:
        with pytest.raises(MetaOAuthError, match="refusing stale compensation"):
            await restore_binding_webhook_subscription(
                connected.binding,
                ("messages", "messaging_postbacks"),
                expected_current=("feed", "messages", "messaging_postbacks"),
                registry=registry,
                client=client,
            )

    assert [request.method for request in requests] == ["GET"]


@pytest.mark.asyncio
async def test_facebook_page_login_strips_whatsapp_coexistence_scopes(
    registry: MetaAppRegistry,
) -> None:
    """App A Page tokens often still list WA scopes; must not fail Manage Meta Access."""

    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(
            page_extra_scopes=(
                "whatsapp_business_management",
                "whatsapp_business_messaging",
            ),
        ),
    ) as client:
        result = await complete_meta_business_login(
            code="single-use-code",
            state=state,
            registry=registry,
            client=client,
        )
    credential = registry.get_credential(result.binding)
    assert "whatsapp_business_management" not in credential.scopes
    assert "whatsapp_business_messaging" not in credential.scopes
    assert set(credential.scopes) == set(PAGE_SCOPES)


@pytest.mark.asyncio
async def test_facebook_page_login_strips_default_public_profile_scope(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_extra_scopes=("public_profile",)),
    ) as client:
        result = await complete_meta_business_login(
            code="public-profile-default-code",
            state=state,
            registry=registry,
            client=client,
        )

    credential = registry.get_credential(result.binding)
    assert "public_profile" not in credential.scopes
    assert set(credential.scopes) == set(PAGE_SCOPES)


@pytest.mark.asyncio
async def test_facebook_page_login_rejects_legacy_instagram_scope(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_extra_scopes=("instagram_manage_comments",)),
    ) as client:
        with pytest.raises(MetaOAuthError, match="instagram_manage_comments"):
            await complete_meta_business_login(
                code="legacy-instagram-scope-code",
                state=state,
                registry=registry,
                client=client,
            )

    assert registry.list_bindings() == []


@pytest.mark.asyncio
async def test_facebook_page_login_rejects_unreviewed_extra_page_authority(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_extra_scopes=("pages_manage_posts",)),
    ) as client:
        with pytest.raises(MetaOAuthError, match="pages_manage_posts"):
            await complete_meta_business_login(
                code="unreviewed-extra-scope-code",
                state=state,
                registry=registry,
                client=client,
            )

    assert registry.list_bindings() == []


@pytest.mark.asyncio
async def test_facebook_page_login_allows_missing_granular_scopes(
    registry: MetaAppRegistry,
) -> None:
    """Meta sometimes omits granular_scopes; profile_id match must still authorize."""

    state = _start_state(registry, channel="facebook")
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(omit_granular_scopes=True),
    ) as client:
        result = await complete_meta_business_login(
            code="no-granular-code",
            state=state,
            registry=registry,
            client=client,
        )
    assert result.binding.status == "active"
    assert result.binding.channel == "facebook"


@pytest.mark.asyncio
async def test_business_login_instagram_channel_cannot_complete_oauth(registry: MetaAppRegistry) -> None:
    with pytest.raises(MetaOAuthError, match="Instagram Login"):
        begin_meta_business_login(
            tenant_id="tenant-a",
            channel="instagram",
            actor_id="owner-a",
            registry=registry,
        )


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
@pytest.mark.parametrize(
    "targets",
    [
        {"pages_manage_engagement": ("000111222",)},
        {"pages_read_user_content": ("17840000123456789",)},
    ],
)
async def test_comment_granular_grants_require_selected_page_target(
    registry: MetaAppRegistry,
    targets: dict[str, tuple[str, ...]],
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(granular_scope_targets=targets),
    ) as client:
        with pytest.raises(MetaOAuthError, match="another asset"):
            await complete_meta_business_login(
                code="invalid-comment-target-code",
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
