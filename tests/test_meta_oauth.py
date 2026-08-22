"""Meta App A Business Login security and asset-validation tests."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
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
from services.meta_oauth_graph import restore_binding_webhook_subscription
from services.meta_oauth_return import mobile_oauth_failure_reason
from services.meta_subject_deletion_guard import meta_deletion_subject_hmac
from tests.meta_compliance_helpers import _FakeFirestore, _set_fake_meta_deletion_request

PAGE_SCOPES = [
    "pages_manage_engagement",
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_read_user_content",
    "pages_messaging",
]
INTEGRATION_SCOPES = ["business_management", *PAGE_SCOPES]
SCOPES = INTEGRATION_SCOPES


@pytest.fixture
def oauth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_B_ID", "998877665544")
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-tests")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b-tests")
    monkeypatch.setenv("META_APP_A_FACEBOOK_LOGIN_CONFIG_ID", "facebook-only-config-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_OAUTH_REDIRECT_URI", "https://www.linasaibot.com/oauth/meta/callback")


@pytest.fixture
def registry(tmp_path: Path, oauth_env: None, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)

    async def _enable_channel_defaults(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "services.channel_capability_toggles.enable_channel_defaults_after_connect",
        _enable_channel_defaults,
    )
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
    page_extra_scopes: tuple[str, ...] = (),
    page_scopes: tuple[str, ...] | None = None,
    integration_scopes: tuple[str, ...] | None = None,
    page_tasks: tuple[str, ...] = ("MESSAGING", "MODERATE"),
    omit_granular_scopes: bool = False,
    granular_scope_targets: dict[str, tuple[str, ...]] | None = None,
    authorized_user_id: str = "112233445566",
    subscription_post_success: bool = True,
    subscription_fail_page_id: str = "",
    verified_subscription_fields: tuple[str, ...] | None = None,
    second_page_id: str = "",
    second_page_scopes: tuple[str, ...] | None = None,
    second_page_tasks: tuple[str, ...] | None = None,
    include_page: bool = True,
    page_access_token: str = "page-token-private",
    subscription_state: dict[str, tuple[str, ...]] | None = None,
    observed_requests: list[httpx.Request] | None = None,
    subscription_hook: Callable[[httpx.Request, str], Awaitable[None]] | None = None,
) -> httpx.MockTransport:
    subscribed_fields = subscription_state if subscription_state is not None else {}
    posted_pages: set[str] = set()
    verification_override_pending: set[str] = set()

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
                "scopes": list(integration_scopes if integration_scopes is not None else INTEGRATION_SCOPES),
                "expires_at": 4102444800,
                "user_id": authorized_user_id,
            }
            inspected_page_id = ""
            inspected_scopes: list[str] = []
            if inspected == "page-token-private":
                inspected_page_id = page_id
                inspected_scopes = list(page_scopes if page_scopes is not None else PAGE_SCOPES)
            elif second_page_id and inspected == "page-token-private-2":
                inspected_page_id = second_page_id
                inspected_scopes = list(second_page_scopes if second_page_scopes is not None else PAGE_SCOPES)
            if inspected_page_id:
                inspected_scopes.extend(page_extra_scopes)
                data["scopes"] = inspected_scopes
                data["profile_id"] = inspected_page_id
                data["type"] = page_type
                if not omit_granular_scopes:
                    default_targets = [inspected_page_id, "000111222"] if extra_target else [inspected_page_id]
                    data["granular_scopes"] = [
                        {
                            "scope": scope,
                            "target_ids": list((granular_scope_targets or {}).get(scope, tuple(default_targets))),
                        }
                        for scope in PAGE_SCOPES
                    ]
            return httpx.Response(200, json={"data": data})
        if path.endswith("/me/accounts"):
            pages = []
            if include_page:
                pages.append(
                    {
                        "id": page_id,
                        "name": "Authorized Clinic",
                        "access_token": page_access_token,
                        "tasks": list(page_tasks),
                        "instagram_business_account": {
                            "id": instagram_id,
                            "username": "authorized_clinic",
                        },
                    }
                )
            if second_page_id:
                pages.append(
                    {
                        "id": second_page_id,
                        "name": "Second Authorized Clinic",
                        "access_token": "page-token-private-2",
                        "tasks": list(second_page_tasks if second_page_tasks is not None else page_tasks),
                        "instagram_business_account": {
                            "id": "17840000999999999",
                            "username": "second_authorized_clinic",
                        },
                    }
                )
            return httpx.Response(
                200,
                json={"data": pages},
            )
        if path.endswith("/subscribed_apps") and request.method == "POST":
            body = (await request.aread()).decode("utf-8")
            request_page_id = path.rstrip("/").split("/")[-2]
            subscribed_fields[request_page_id] = tuple(
                sorted((parse_qs(body).get("subscribed_fields") or [""])[0].split(","))
            )
            if verified_subscription_fields is not None and request_page_id not in posted_pages:
                verification_override_pending.add(request_page_id)
            posted_pages.add(request_page_id)
            success = subscription_post_success and request_page_id != subscription_fail_page_id
            if subscription_hook is not None:
                await subscription_hook(request, request_page_id)
            return httpx.Response(200, json={"success": success})
        if path.endswith("/subscribed_apps") and request.method == "GET":
            request_page_id = path.rstrip("/").split("/")[-2]
            fields = subscribed_fields.get(request_page_id)
            if verified_subscription_fields is not None and request_page_id in verification_override_pending:
                fields = verified_subscription_fields
                verification_override_pending.remove(request_page_id)
            rows = [{"id": "2963733803971681", "subscribed_fields": list(fields)}] if fields is not None else []
            if subscription_hook is not None:
                await subscription_hook(request, request_page_id)
            return httpx.Response(200, json={"data": rows})
        if path.endswith("/subscribed_apps") and request.method == "DELETE":
            request_page_id = path.rstrip("/").split("/")[-2]
            subscribed_fields.pop(request_page_id, None)
            if subscription_hook is not None:
                await subscription_hook(request, request_page_id)
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_oauth_flow_channel_keeps_facebook_and_instagram_separate() -> None:
    assert normalize_oauth_flow_channel("instagram") == "instagram"
    assert normalize_oauth_flow_channel("facebook") == "facebook"
    assert normalize_oauth_flow_channel("unified") == "unified"
    assert normalize_oauth_flow_channel("meta") == "unified"
    assert normalize_oauth_flow_channel("") == "unified"


def test_business_login_url_uses_config_id_without_duplicate_scope_parameter(registry: MetaAppRegistry) -> None:
    url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel="facebook",
        actor_id="owner-a",
        registry=registry,
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.hostname == "www.facebook.com"
    assert query["config_id"] == ["facebook-only-config-tests"]
    assert query["client_id"] == ["2963733803971681"]
    assert query["redirect_uri"] == ["https://www.linasaibot.com/oauth/meta/callback"]
    assert query["response_type"] == ["code"]
    assert query["override_default_response_type"] == ["true"]
    assert query["auth_type"] == ["rerequest"]
    assert query["state"]
    # The reviewed User-token Login Configuration owns its exact permission
    # set; duplicating scope= can make Meta ignore the configuration contract.
    assert "scope" not in query
    assert "app-b-secret-tests" not in url
    assert "owner-a" not in registry.store_path.read_text(encoding="utf-8")


def test_facebook_connect_rejects_instagram_business_login_channel(registry: MetaAppRegistry) -> None:
    with pytest.raises(MetaOAuthError, match="Instagram Login"):
        begin_meta_business_login(
            tenant_id="tenant-a",
            channel="instagram",
            actor_id="owner-a",
            registry=registry,
        )


def test_unified_business_login_uses_facebook_only_config(registry: MetaAppRegistry) -> None:
    url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel="unified",
        actor_id="owner-a",
        registry=registry,
    )
    query = parse_qs(urlparse(url).query)
    assert query["config_id"] == ["facebook-only-config-tests"]
    assert "scope" not in query


def test_facebook_and_instagram_connect_use_separate_auth_paths(
    registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Facebook Connect uses FB Business Login config; Instagram Connect uses Instagram Login."""

    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "ig-login-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv(
        "META_INSTAGRAM_LOGIN_REDIRECT_URI",
        "https://www.linasaibot.com/oauth/instagram/callback",
    )
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")
    from services.meta_instagram_login_oauth import begin_instagram_login

    facebook_url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel="facebook",
        actor_id="owner-a",
        registry=registry,
    )
    instagram_url = begin_instagram_login(
        tenant_id="tenant-a",
        actor_id="owner-a",
        registry=registry,
    )
    facebook_parsed = urlparse(facebook_url)
    instagram_parsed = urlparse(instagram_url)
    facebook_query = parse_qs(facebook_parsed.query)
    instagram_query = parse_qs(instagram_parsed.query)

    assert facebook_parsed.hostname == "www.facebook.com"
    assert facebook_query["config_id"] == ["facebook-only-config-tests"]
    assert "dialog/oauth" in facebook_parsed.path

    assert instagram_parsed.hostname == "www.instagram.com"
    assert "oauth/authorize" in instagram_parsed.path
    assert "config_id" not in instagram_query
    ig_scopes = set((instagram_query.get("scope") or [""])[0].split(","))
    assert "instagram_business_basic" in ig_scopes
    assert "instagram_business_manage_messages" in ig_scopes
    assert "instagram_business_manage_comments" in ig_scopes
    assert "instagram_business_content_publish" not in ig_scopes
    assert "pages_messaging" not in ig_scopes
    assert facebook_url != instagram_url


def test_facebook_default_config_id_is_pages_only_when_env_unset(
    registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("META_APP_A_FACEBOOK_LOGIN_CONFIG_ID", raising=False)
    url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel="facebook",
        actor_id="owner-a",
        registry=registry,
    )
    assert parse_qs(urlparse(url).query)["config_id"] == ["1021840664011530"]
    assert "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID=1021840664011530" in Path(".env.example").read_text(encoding="utf-8")
    assert "Facebook Login for Business configuration: `1021840664011530`" in Path(
        "docs/META_APP_REVIEW_SOCIAL_PACKAGE.md"
    ).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_external_page_login_inspects_encrypts_and_activates_with_subscription(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_legacy_archive(**_kwargs: Any) -> int:
        raise AssertionError("post-activation duplicate archive must not run")

    monkeypatch.setattr(registry, "archive_superseded_duplicate_bindings", fail_legacy_archive)
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
    assert set(credential.scopes) == set(PAGE_SCOPES)
    assert "business_management" not in credential.scopes
    assert credential.authorized_meta_user_id == "112233445566"
    assert result.binding.webhook_subscription_status == "ready"
    assert set(result.binding.webhook_subscribed_fields) == {
        "messages",
        "messaging_postbacks",
        "feed",
        "standby",
    }
    assert "112233445566" not in stored
    assert any(request.url.path.endswith("/subscribed_apps") for request in observed_requests)
    token_exchange = next(request for request in observed_requests if request.url.path.endswith("/oauth/access_token"))
    assert token_exchange.method == "POST"
    page_discovery = next(request for request in observed_requests if request.url.path.endswith("/me/accounts"))
    assert page_discovery.url.params["fields"] == "id,name,access_token,tasks"
    assert "instagram" not in page_discovery.url.params["fields"]
    assert not any("assigned_pages" in request.url.path for request in observed_requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("include_page", "page_access_token"),
    [(False, "page-token-private"), (True, "")],
)
async def test_facebook_page_discovery_without_page_token_is_safe_no_page_failure(
    registry: MetaAppRegistry,
    caplog: pytest.LogCaptureFixture,
    include_page: bool,
    page_access_token: str,
) -> None:
    state = _start_state(registry)
    observed_requests: list[httpx.Request] = []
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(
            include_page=include_page,
            page_access_token=page_access_token,
            observed_requests=observed_requests,
        ),
    ) as client:
        with pytest.raises(MetaOAuthError, match="No eligible Facebook Page") as captured:
            await complete_meta_business_login(
                code="no-page-token-code",
                state=state,
                registry=registry,
                client=client,
            )

    assert mobile_oauth_failure_reason(captured.value) == "no_page"
    assert registry.list_bindings() == []
    assert not any(request.url.path.endswith("/subscribed_apps") for request in observed_requests)
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "page_discovery edge=accounts" in rendered
    assert "eligible=0" in rendered
    assert "Authorized Clinic" not in rendered
    assert "page-token-private" not in rendered
    assert "445566778899" not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deletion_state", "expected_reason"),
    [("pending", "deletion"), ("failed", "deletion_failed")],
)
async def test_deletion_blocks_facebook_before_subscription_or_staging(
    registry: MetaAppRegistry,
    deletion_state: str,
    expected_reason: str,
) -> None:
    import utils.utils

    db = utils.utils.get_firestore_db()
    assert isinstance(db, _FakeFirestore)
    subject_key = meta_deletion_subject_hmac(
        app_key=APP_A_KEY,
        app_id="2963733803971681",
        auth_flow="facebook_login",
        meta_user_id="112233445566",
        app_secret="app-a-secret-tests",
    )
    _set_fake_meta_deletion_request(
        db,
        subject_key=subject_key,
        app_key=APP_A_KEY,
        app_id="2963733803971681",
        auth_flow="facebook_login",
        state=deletion_state,
    )
    oauth_state = _start_state(registry)
    observed_requests: list[httpx.Request] = []
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(observed_requests=observed_requests),
    ) as client:
        with pytest.raises(
            MetaOAuthError,
            match=rf"blocked by a {deletion_state} data deletion request",
        ) as captured:
            await complete_meta_business_login(
                code=f"{deletion_state}-deletion-code",
                state=oauth_state,
                registry=registry,
                client=client,
            )

    assert mobile_oauth_failure_reason(captured.value) == expected_reason
    assert registry.list_bindings() == []
    assert not any(
        request.method == "POST" and request.url.path.endswith("/subscribed_apps") for request in observed_requests
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_scope", INTEGRATION_SCOPES)
async def test_facebook_login_requires_every_config_scope_on_integration_token(
    registry: MetaAppRegistry,
    missing_scope: str,
) -> None:
    state = _start_state(registry)
    observed_requests: list[httpx.Request] = []
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(
            integration_scopes=tuple(scope for scope in INTEGRATION_SCOPES if scope != missing_scope),
            observed_requests=observed_requests,
        ),
    ) as client:
        with pytest.raises(MetaOAuthError, match=rf"integration token.*{missing_scope}") as captured:
            await complete_meta_business_login(
                code="missing-integration-grant-code",
                state=state,
                registry=registry,
                client=client,
            )
    assert mobile_oauth_failure_reason(captured.value) == "scopes"
    assert registry.list_bindings() == []
    assert not any(request.url.path.endswith("/me/accounts") for request in observed_requests)


@pytest.mark.asyncio
async def test_page_grants_never_fall_back_to_integration_token(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    missing_page_scope = tuple(scope for scope in PAGE_SCOPES if scope != "pages_manage_engagement")
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(
            integration_scopes=tuple(SCOPES),
            page_scopes=missing_page_scope,
        ),
    ) as client:
        with pytest.raises(MetaOAuthError, match="Page token.*pages_manage_engagement") as captured:
            await complete_meta_business_login(
                code="integration-cannot-fill-page-grant-code",
                state=state,
                registry=registry,
                client=client,
            )
    assert mobile_oauth_failure_reason(captured.value) == "scopes"
    assert "business_management" not in str(captured.value)
    assert registry.list_bindings() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page_tasks", "missing_task"),
    [
        (("MODERATE",), "MESSAGING"),
        (("MESSAGING",), "MODERATE"),
        ((), "MESSAGING"),
    ],
)
async def test_facebook_page_requires_messaging_and_moderate_tasks(
    registry: MetaAppRegistry,
    page_tasks: tuple[str, ...],
    missing_task: str,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_tasks=page_tasks),
    ) as client:
        with pytest.raises(MetaOAuthError, match=missing_task):
            await complete_meta_business_login(
                code="insufficient-page-task-code",
                state=state,
                registry=registry,
                client=client,
            )
    assert registry.list_bindings() == []


@pytest.mark.asyncio
async def test_facebook_page_accepts_new_pages_experience_task_names(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_tasks=("PROFILE_PLUS_MESSAGING", "PROFILE_PLUS_MODERATE")),
    ) as client:
        result = await complete_meta_business_login(
            code="profile-plus-page-task-code",
            state=state,
            registry=registry,
            client=client,
        )
    assert result.binding.active


@pytest.mark.asyncio
async def test_facebook_page_full_control_label_does_not_infer_specific_tasks(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_tasks=("PROFILE_PLUS_FULL_CONTROL",)),
    ) as client:
        with pytest.raises(MetaOAuthError, match="MESSAGING"):
            await complete_meta_business_login(
                code="full-control-label-only-code",
                state=state,
                registry=registry,
                client=client,
            )


@pytest.mark.asyncio
async def test_different_facebook_authorizer_gets_versioned_binding_lineage(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="112233445566"),
    ) as client:
        first = await complete_meta_business_login(
            code="first-owner-code",
            state=first_state,
            registry=registry,
            client=client,
        )

    second_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="998877665544"),
    ) as client:
        second = await complete_meta_business_login(
            code="second-owner-code",
            state=second_state,
            registry=registry,
            client=client,
        )

    assert first.binding.binding_id != second.binding.binding_id
    assert second.binding.previous_binding_id == first.binding.binding_id
    by_id = {binding.binding_id: binding for binding in registry.list_bindings()}
    assert by_id[first.binding.binding_id].active is False
    assert by_id[first.binding.binding_id].superseded_by_binding_id == second.binding.binding_id
    assert by_id[second.binding.binding_id].active is True
    old_owner = registry.find_authorization_bindings(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )
    new_owner = registry.find_authorization_bindings(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="998877665544",
    )
    assert [binding.binding_id for binding in old_owner] == [first.binding.binding_id]
    assert [binding.binding_id for binding in new_owner] == [second.binding.binding_id]

    third_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="998877665544"),
    ) as client:
        same_owner = await complete_meta_business_login(
            code="same-second-owner-code",
            state=third_state,
            registry=registry,
            client=client,
        )
    assert same_owner.binding.binding_id != second.binding.binding_id
    assert same_owner.binding.previous_binding_id == second.binding.binding_id


@pytest.mark.asyncio
async def test_disconnected_facebook_authorizer_gets_fresh_binding_id(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="112233445566"),
    ) as client:
        first = await complete_meta_business_login(
            code="first-authorization-code",
            state=first_state,
            registry=registry,
            client=client,
        )
    registry.revoke_authorization(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )

    reconnect_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="112233445566"),
    ) as client:
        reconnected = await complete_meta_business_login(
            code="fresh-authorization-code",
            state=reconnect_state,
            registry=registry,
            client=client,
        )

    assert reconnected.binding.binding_id != first.binding.binding_id
    assert reconnected.binding.active is True


@pytest.mark.asyncio
async def test_facebook_connect_requires_all_review_scopes_without_replacing_active(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        first = await complete_meta_business_login(
            code="first-authorization-code",
            state=first_state,
            registry=registry,
            client=client,
        )

    missing_scope_state = _start_state(registry)
    without_comments = tuple(
        scope for scope in PAGE_SCOPES if scope not in {"pages_read_user_content", "pages_manage_engagement"}
    )
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_scopes=without_comments),
    ) as client:
        with pytest.raises(MetaOAuthError, match="required review permissions"):
            await complete_meta_business_login(
                code="missing-comments-code",
                state=missing_scope_state,
                registry=registry,
                client=client,
            )

    active = registry.find_bindings_for_asset_key(
        tenant_id="tenant-a",
        app_key=APP_A_KEY,
        channel="facebook",
        asset_id="445566778899",
    )
    assert [binding.binding_id for binding in active if binding.active] == [first.binding.binding_id]


@pytest.mark.asyncio
async def test_facebook_reconnect_preserves_active_binding_when_subscription_verify_fails(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        first = await complete_meta_business_login(
            code="first-authorization-code",
            state=first_state,
            registry=registry,
            client=client,
        )

    reconnect_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(verified_subscription_fields=("messages", "messaging_postbacks")),
    ) as client:
        with pytest.raises(MetaOAuthError, match="approved state"):
            await complete_meta_business_login(
                code="unverified-subscription-code",
                state=reconnect_state,
                registry=registry,
                client=client,
            )

    active = registry.find_bindings_for_asset_key(
        tenant_id="tenant-a",
        app_key=APP_A_KEY,
        channel="facebook",
        asset_id="445566778899",
    )
    assert [binding.binding_id for binding in active if binding.active] == [first.binding.binding_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["validation", "subscription"])
async def test_multi_page_oauth_failure_never_partially_cuts_over_first_page(
    registry: MetaAppRegistry,
    failure_mode: str,
) -> None:
    initial_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        original = await complete_meta_business_login(
            code="initial-page-code",
            state=initial_state,
            registry=registry,
            client=client,
        )

    prior_fields = ("feed", "mention", "messages", "messaging_postbacks")
    external_subscriptions = {"445566778899": prior_fields}
    observed_requests: list[httpx.Request] = []
    failure_transport = _transport(
        second_page_id="556677889900",
        second_page_scopes=(
            tuple(scope for scope in PAGE_SCOPES if scope != "pages_manage_engagement")
            if failure_mode == "validation"
            else None
        ),
        subscription_fail_page_id="556677889900" if failure_mode == "subscription" else "",
        subscription_state=external_subscriptions,
        observed_requests=observed_requests,
    )
    message = "Page token.*pages_manage_engagement" if failure_mode == "validation" else "did not confirm"
    reconnect_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=failure_transport,
    ) as client:
        with pytest.raises(MetaOAuthError, match=message):
            await complete_meta_business_login(
                code="multi-page-failure-code",
                state=reconnect_state,
                registry=registry,
                client=client,
            )

    active = registry.list_bindings(include_inactive=False)
    assert [binding.binding_id for binding in active] == [original.binding.binding_id]
    assert active[0].asset_id == "445566778899"
    assert all(binding.asset_id != "556677889900" for binding in active)
    assert external_subscriptions == {"445566778899": prior_fields}
    if failure_mode == "subscription":
        assert any(
            request.method == "DELETE" and "556677889900/subscribed_apps" in request.url.path
            for request in observed_requests
        )


@pytest.mark.asyncio
async def test_concurrent_failing_callback_cannot_undo_successful_page_subscription(
    registry: MetaAppRegistry,
) -> None:
    """The whole provider transaction is serialized, including compensation."""

    page_id = "445566778899"
    second_page_id = "556677889900"
    prior_fields = ("mention", "messages", "messaging_postbacks")
    desired_fields = ("feed", "messages", "messaging_postbacks", "standby")
    external_subscriptions = {page_id: prior_fields}
    first_reached_failure = asyncio.Event()
    allow_first_to_fail = asyncio.Event()
    operations: list[tuple[str, str, str]] = []
    paused = False

    async def first_hook(request: httpx.Request, request_page_id: str) -> None:
        nonlocal paused
        operations.append(("first", request.method, request_page_id))
        if request.method == "POST" and request_page_id == second_page_id and not paused:
            paused = True
            first_reached_failure.set()
            await allow_first_to_fail.wait()

    async def second_hook(request: httpx.Request, request_page_id: str) -> None:
        operations.append(("second", request.method, request_page_id))

    first_state = _start_state(registry)
    second_state = _start_state(registry)
    async with (
        httpx.AsyncClient(
            base_url="https://graph.facebook.com/v24.0/",
            transport=_transport(
                second_page_id=second_page_id,
                subscription_fail_page_id=second_page_id,
                subscription_state=external_subscriptions,
                subscription_hook=first_hook,
            ),
        ) as first_client,
        httpx.AsyncClient(
            base_url="https://graph.facebook.com/v24.0/",
            transport=_transport(
                subscription_state=external_subscriptions,
                subscription_hook=second_hook,
            ),
        ) as second_client,
    ):
        first_task = asyncio.create_task(
            complete_meta_business_login(
                code="concurrent-failing-code",
                state=first_state,
                registry=registry,
                client=first_client,
            )
        )
        await asyncio.wait_for(first_reached_failure.wait(), timeout=2.0)

        second_task = asyncio.create_task(
            complete_meta_business_login(
                code="concurrent-success-code",
                state=second_state,
                registry=registry,
                client=second_client,
            )
        )
        await asyncio.sleep(0.05)
        assert not any(owner == "second" for owner, _method, _page in operations)

        allow_first_to_fail.set()
        with pytest.raises(MetaOAuthError, match="did not confirm"):
            await asyncio.wait_for(first_task, timeout=2.0)
        successful = await asyncio.wait_for(second_task, timeout=2.0)

    assert successful.binding.active
    assert external_subscriptions == {page_id: desired_fields}
    first_second_operation = next(index for index, item in enumerate(operations) if item[0] == "second")
    assert all(owner == "first" for owner, _method, _page in operations[:first_second_operation])
    assert all(owner == "second" for owner, _method, _page in operations[first_second_operation:])


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
