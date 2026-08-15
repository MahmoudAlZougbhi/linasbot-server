"""Instagram Login lifecycle, capability routing, and subscription recovery tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
    get_meta_graph_api_version,
)
from services.meta_comment_events import resolve_registry_comment_events
from services.meta_cross_flow_dedup import global_comment_claim_key
from services.meta_graph_routing import graph_api_url
from services.meta_instagram_login_capabilities import (
    binding_ready_for_comments,
    binding_ready_for_publish,
    facebook_login_binding_superseded_for_capability,
    instagram_login_subscription_retry_eligible,
    select_instagram_binding_for_capability,
)
from services.meta_instagram_login_lifecycle import InstagramLoginLifecycle, get_instagram_login_lifecycle
from services.meta_instagram_login_subscription import (
    COMMENTS_SUBSCRIPTION_FIELD,
    subscribed_fields_for_granted_scopes,
)
from services.meta_multi_app_router import resolve_registry_events
from tests.meta_instagram_login_lifecycle_helpers import (
    DM_SCOPES,
    FULL_SCOPES,
    INSTAGRAM_ID,
    PAGE_SCOPES,
    _binding,
    _comment_payload,
    _dm_payload,
)


@pytest.fixture
def instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-lifecycle-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-lifecycle-secret-tests-1234567890",
    )


@pytest.mark.asyncio
async def test_startup_recovers_failed_subscription_without_webhook(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=DM_SCOPES,
        webhook_status="failed",
        webhook_fields=(),
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1035856539045307",
                        "subscribed_fields": ["messages", "messaging_postbacks"],
                    }
                ]
            },
        )

    lifecycle = InstagramLoginLifecycle()
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=f"https://graph.instagram.com/{get_meta_graph_api_version()}",
    )

    async def _retry(binding_id: str, **kwargs: object) -> object:
        from services.meta_instagram_login_subscription_recovery import retry_instagram_login_webhook_subscription

        return await retry_instagram_login_webhook_subscription(
            binding_id,
            registry=registry,
            client=mock_client,
        )

    with patch("services.meta_instagram_login_lifecycle.get_meta_app_registry", return_value=registry):
        with patch("services.meta_instagram_login_lifecycle.instagram_login_config_status") as status:
            status.return_value = SimpleNamespace(configured=True)
            with patch("services.meta_instagram_login_lifecycle.try_acquire_job_lock", return_value=True):
                with patch("services.meta_instagram_login_lifecycle.release_job_lock"):
                    with patch(
                        "services.meta_instagram_login_lifecycle.retry_instagram_login_webhook_subscription",
                        side_effect=_retry,
                    ):
                        await lifecycle.run_once(actor_id="instagram-login-startup")

    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.webhook_subscription_status == "ready"
    await lifecycle.stop()
    assert lifecycle.running is False


@pytest.mark.asyncio
async def test_lifecycle_tick_skipped_when_worker_lock_held(registry: MetaAppRegistry) -> None:
    _binding(registry, auth_flow="instagram_login", webhook_status="failed", webhook_fields=())
    lifecycle = InstagramLoginLifecycle()
    with patch("services.meta_instagram_login_lifecycle.get_meta_app_registry", return_value=registry):
        with patch("services.meta_instagram_login_lifecycle.try_acquire_job_lock", return_value=False):
            with patch("services.meta_instagram_login_lifecycle.instagram_login_config_status") as status:
                status.return_value = SimpleNamespace(configured=True)
                result = await lifecycle.run_once()
    assert result.get("skipped") == 1


@pytest.mark.asyncio
async def test_lifecycle_stops_cleanly_without_orphan_task(registry: MetaAppRegistry) -> None:
    lifecycle = InstagramLoginLifecycle()
    with patch("services.meta_instagram_login_lifecycle.instagram_login_config_status") as status:
        status.return_value = SimpleNamespace(configured=True)
        with patch("services.meta_instagram_login_lifecycle.try_acquire_job_lock", return_value=True):
            with patch("services.meta_instagram_login_lifecycle.release_job_lock"):
                await lifecycle.start()
    assert lifecycle.running is True
    await lifecycle.stop()
    await asyncio.sleep(0)
    assert lifecycle.running is False
    assert lifecycle._task is None


@pytest.mark.asyncio
async def test_lifecycle_schedules_token_refresh(registry: MetaAppRegistry) -> None:
    _binding(
        registry,
        auth_flow="instagram_login",
        scopes=DM_SCOPES,
        webhook_fields=("messages", "messaging_postbacks"),
    )
    lifecycle = InstagramLoginLifecycle()
    with patch("services.meta_instagram_login_lifecycle.get_meta_app_registry", return_value=registry):
        with patch("services.meta_instagram_login_lifecycle.instagram_login_config_status") as status:
            status.return_value = SimpleNamespace(configured=True)
            with patch("services.meta_instagram_login_lifecycle.try_acquire_job_lock", return_value=True):
                with patch("services.meta_instagram_login_lifecycle.release_job_lock"):
                    with patch("services.meta_instagram_login_lifecycle.credential_needs_refresh", return_value=True):
                        with patch(
                            "services.meta_instagram_login_lifecycle.refresh_binding_instagram_login_token",
                            return_value=registry.list_bindings()[0],
                        ) as refresh:
                            result = await lifecycle.run_once()
    assert refresh.called
    assert result.get("tokens_refreshed") == 1


@pytest.mark.asyncio
async def test_dm_ready_direct_comments_fallback_to_page_linked(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _binding(
        registry,
        auth_flow="instagram_login",
        scopes=DM_SCOPES,
        webhook_fields=("messages", "messaging_postbacks"),
    )
    _binding(registry, auth_flow="facebook_login", scopes=PAGE_SCOPES)
    resolved = resolve_registry_comment_events(
        _comment_payload(),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow="facebook_login",
    )
    assert len(resolved) == 1
    assert resolved[0].binding.auth_flow == "facebook_login"


@pytest.mark.asyncio
async def test_direct_comments_ready_dedupes_duplicate_delivery(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_fields=("messages", "messaging_postbacks", COMMENTS_SUBSCRIPTION_FIELD),
    )
    _binding(registry, auth_flow="facebook_login", scopes=PAGE_SCOPES)
    app_config = get_meta_app_configs()[APP_A_KEY]
    direct = resolve_registry_comment_events(
        _comment_payload(),
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    page = resolve_registry_comment_events(
        _comment_payload(),
        app_config=app_config,
        registry=registry,
        auth_flow="facebook_login",
    )
    assert len(direct) == 1
    assert direct[0].binding.auth_flow == "instagram_login"
    assert page == []
    key = global_comment_claim_key(direct[0].event)
    assert key == f"instagram:{INSTAGRAM_ID}:comment-1"


def test_ineligible_facebook_login_does_not_supersede_when_direct_lacks_comments(registry: MetaAppRegistry) -> None:
    direct = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=DM_SCOPES,
        webhook_fields=("messages", "messaging_postbacks"),
    )
    page = _binding(registry, auth_flow="facebook_login", scopes=PAGE_SCOPES)
    assert facebook_login_binding_superseded_for_capability(page, "comments", registry=registry) is False
    assert facebook_login_binding_superseded_for_capability(page, "dm", registry=registry) is True
    assert facebook_login_binding_superseded_for_capability(page, "dm", registry=registry)
    _ = direct


def test_permission_upgrade_adds_comments_without_removing_dm_fields() -> None:
    fields = subscribed_fields_for_granted_scopes(FULL_SCOPES)
    assert "messages" in fields
    assert "messaging_postbacks" in fields
    assert COMMENTS_SUBSCRIPTION_FIELD in fields


def test_revoked_comment_permission_is_not_ready(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=DM_SCOPES,
        webhook_fields=("messages", "messaging_postbacks"),
    )
    credential = registry.get_credential(binding)
    assert binding_ready_for_comments(binding, credential) is False


def test_publish_binding_selection_prefers_capable_direct_login(registry: MetaAppRegistry) -> None:
    _binding(registry, auth_flow="facebook_login", scopes=("instagram_basic", "instagram_content_publish"))
    direct = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=("instagram_business_basic", "instagram_business_content_publish"),
    )
    bindings = list(registry.list_bindings(include_inactive=False))
    selected = select_instagram_binding_for_capability(bindings, "publish", registry=registry)
    assert selected is not None
    assert selected.binding_id == direct.binding_id
    credential = registry.get_credential(selected)
    assert binding_ready_for_publish(selected, credential) is True


def test_subscription_retry_respects_bounded_backoff(registry: MetaAppRegistry) -> None:
    from services.meta_instagram_login_subscription import InstagramLoginSubscriptionState

    binding = _binding(registry, auth_flow="instagram_login", webhook_status="failed", webhook_fields=())
    credential = registry.get_credential(binding)
    registry.update_instagram_login_webhook_subscription(
        binding.binding_id,
        state=InstagramLoginSubscriptionState(
            status="failed",
            subscribed_fields=("messages", "messaging_postbacks"),
            verified_fields=(),
            error="subscription_verify_failed",
        ),
        actor_id="test",
    )
    binding = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    now = binding.webhook_subscription_checked_at
    assert instagram_login_subscription_retry_eligible(binding, credential, now=now + 10) is False
    assert instagram_login_subscription_retry_eligible(binding, credential, now=now + 400) is True


def test_graph_version_applied_to_both_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.meta_app_registry import APP_A_KEY, MetaAssetBinding

    monkeypatch.setenv("META_GRAPH_API_VERSION", "v25.0")
    version = get_meta_graph_api_version()
    assert version == "v25.0"
    direct = MetaAssetBinding(
        binding_id="ig-direct",
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential_id="cred-ig",
        status="active",
        generation=1,
        created_at=0.0,
        updated_at=0.0,
        auth_flow="instagram_login",
    )
    page_linked = MetaAssetBinding(
        binding_id="ig-page",
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="112233",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential_id="cred-fb",
        status="active",
        generation=1,
        created_at=0.0,
        updated_at=0.0,
        auth_flow="facebook_login",
    )
    assert graph_api_url(direct, graph_api_version=version, path=f"{INSTAGRAM_ID}/messages").startswith(
        f"https://graph.instagram.com/{version}/"
    )
    assert graph_api_url(page_linked, graph_api_version=version, path="112233/feed").startswith(
        f"https://graph.facebook.com/{version}/"
    )


@pytest.mark.asyncio
async def test_resolve_dm_prefers_direct_when_ready(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    _binding(registry, auth_flow="facebook_login", scopes=PAGE_SCOPES)
    _binding(
        registry, auth_flow="instagram_login", scopes=DM_SCOPES, webhook_fields=("messages", "messaging_postbacks")
    )
    routed = await resolve_registry_events(
        _dm_payload(),
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
    )
    assert len(routed) == 1
    assert routed[0].binding.auth_flow == "instagram_login"


@pytest.mark.asyncio
async def test_permission_upgrade_adds_comments_without_removing_dm_subscription(registry: MetaAppRegistry) -> None:
    from services.meta_instagram_login_subscription import ensure_instagram_login_webhook_subscription

    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=DM_SCOPES,
        webhook_status="ready",
        webhook_fields=("messages", "messaging_postbacks"),
    )
    credential = registry.get_credential(binding)
    subscribed: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            from urllib.parse import unquote_plus

            body = request.content.decode()
            raw_fields = body.split("subscribed_fields=", 1)[-1].split("&", 1)[0]
            subscribed.extend(unquote_plus(raw_fields).split(","))
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1035856539045307",
                        "subscribed_fields": ["messages", "messaging_postbacks", COMMENTS_SUBSCRIPTION_FIELD],
                    }
                ]
            },
        )

    upgraded_credential = MetaBindingCredential(
        access_token=credential.access_token,
        token_app_id=credential.token_app_id,
        token_profile_id=credential.token_profile_id,
        scopes=FULL_SCOPES,
        expires_at=credential.expires_at,
        authorized_meta_user_id=credential.authorized_meta_user_id,
        auth_flow=credential.auth_flow,
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=f"https://graph.instagram.com/{get_meta_graph_api_version()}",
    )
    state = await ensure_instagram_login_webhook_subscription(
        binding,
        upgraded_credential,
        registry=registry,
        graph_api_version=get_meta_graph_api_version(),
        client=client,
    )
    assert "messages" in subscribed
    assert "messaging_postbacks" in subscribed
    assert COMMENTS_SUBSCRIPTION_FIELD in subscribed
    assert state.ready_for_dm is True
    assert state.ready_for_comments is True


def test_ineligible_direct_login_does_not_poison_global_comment_dedup(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs
    from services.meta_messaging import InMemoryMessageDeduper

    _binding(
        registry,
        auth_flow="instagram_login",
        scopes=DM_SCOPES,
        webhook_fields=("messages", "messaging_postbacks"),
    )
    _binding(registry, auth_flow="facebook_login", scopes=PAGE_SCOPES)
    app_config = get_meta_app_configs()[APP_A_KEY]
    ineligible = resolve_registry_comment_events(
        _comment_payload(),
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    eligible = resolve_registry_comment_events(
        _comment_payload(),
        app_config=app_config,
        registry=registry,
        auth_flow="facebook_login",
    )
    assert ineligible == []
    assert len(eligible) == 1
    deduper = InMemoryMessageDeduper()
    claim_key = global_comment_claim_key(eligible[0].event)
    assert deduper.claim(claim_key) is True
    assert deduper.claim(claim_key) is False


def test_get_instagram_login_lifecycle_is_singleton() -> None:
    assert get_instagram_login_lifecycle() is get_instagram_login_lifecycle()
