"""Meta App A Business Login security and asset-validation tests."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
)
from services.meta_oauth import (
    MetaOAuthError,
    begin_meta_business_login,
    complete_meta_business_login,
    normalize_oauth_flow_channel,
)
from services.meta_oauth_return import mobile_oauth_failure_reason
from services.meta_subject_deletion_guard import meta_deletion_subject_hmac
from tests.meta_compliance_helpers import _FakeFirestore, _set_fake_meta_deletion_request
from tests.meta_oauth_support import (
    INTEGRATION_SCOPES,
    PAGE_SCOPES,
    SCOPES,
    _start_state,
    _transport,
)

pytest_plugins = ('tests.meta_oauth_support',)

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
