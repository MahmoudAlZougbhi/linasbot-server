"""Instagram Login lifecycle, capability routing, and subscription recovery tests."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    MetaRegistryError,
    get_meta_graph_api_version,
)
from services.meta_comment_events import resolve_registry_comment_events
from services.meta_cross_flow_dedup import global_comment_claim_key
from services.meta_instagram_login_lifecycle import InstagramLoginLifecycle, get_instagram_login_lifecycle
from services.meta_instagram_login_subscription import (
    COMMENTS_SUBSCRIPTION_FIELD,
    INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    InstagramLoginSubscriptionState,
)
from tests.meta_instagram_login_lifecycle_helpers import (
    DM_SCOPES,
    FULL_SCOPES,
    PAGE_SCOPES,
    _binding,
    _comment_payload,
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
    posted = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posted
        if request.method == "POST":
            assert not str(request.headers.get("content-type") or "").startswith("application/json")
            raw_fields = request.url.params.get("subscribed_fields") or ""
            subscribed.extend(item for item in raw_fields.split(",") if item)
            posted = True
            return httpx.Response(200, json={"success": True})
        fields = ["messages", "messaging_postbacks"]
        if posted:
            fields.append(COMMENTS_SUBSCRIPTION_FIELD)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1035856539045307",
                        "subscribed_fields": fields,
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
    _binding(registry, auth_flow="facebook_login", scopes=PAGE_SCOPES, legacy_duplicate=True)
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


@pytest.mark.asyncio
async def test_cleanup_queue_rotates_poison_rows_and_preserves_active_recovery_budget(
    registry: MetaAppRegistry,
) -> None:
    marker_ids: list[str] = []
    for index in range(21):
        asset_id = str(17840000999901000 + index)
        marker = registry.authorize_oauth_asset(
            tenant_id="tenant-a",
            channel="instagram",
            asset_id=asset_id,
            page_id="",
            instagram_account_id=asset_id,
            app_key=APP_A_KEY,
            credential=MetaBindingCredential(
                access_token=f"cleanup-token-{index}",
                token_app_id="1035856539045307",
                token_profile_id=asset_id,
                scopes=FULL_SCOPES,
                expires_at=int(time.time()) + 30 * 24 * 3600,
                auth_flow="instagram_login",
            ),
            actor_id="owner",
            status="testing",
            auth_flow="instagram_login",
            create_new_binding=True,
        )
        registry.update_instagram_login_webhook_subscription(
            marker.binding_id,
            state=InstagramLoginSubscriptionState(
                status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
                subscribed_fields=(),
                verified_fields=(),
                error=INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
            ),
            actor_id="test",
        )
        marker_ids.append(marker.binding_id)

    active = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="ready",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    attempted: list[str] = []
    refreshed: list[str] = []

    async def poison(binding_id: str, **_kwargs: object) -> None:
        attempted.append(binding_id)
        raise MetaRegistryError("simulated durable poison marker")

    async def refresh(binding: MetaAssetBinding, **_kwargs: object) -> object:
        refreshed.append(binding.binding_id)
        return binding

    lifecycle = InstagramLoginLifecycle()
    with patch("services.meta_instagram_login_lifecycle.get_meta_app_registry", return_value=registry):
        with patch("services.meta_instagram_login_lifecycle.retry_instagram_login_cleanup", side_effect=poison):
            with patch(
                "services.meta_instagram_login_lifecycle.instagram_login_subscription_retry_eligible",
                return_value=False,
            ):
                with patch("services.meta_instagram_login_lifecycle.credential_needs_refresh", return_value=True):
                    with patch(
                        "services.meta_instagram_login_lifecycle.refresh_binding_instagram_login_token",
                        side_effect=refresh,
                    ):
                        first = await lifecycle._run_cycle(actor_id="test", instagram_configured=True)
                        second = await lifecycle._run_cycle(actor_id="test", instagram_configured=True)

    assert first["cleanup_checked"] == 20
    assert second["cleanup_checked"] == 20
    assert attempted[:20] == marker_ids[:20]
    assert attempted[20] == marker_ids[20]
    assert refreshed == [active.binding_id, active.binding_id]


@pytest.mark.asyncio
async def test_start_returns_while_first_recovery_cycle_is_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = InstagramLoginLifecycle()
    entered = asyncio.Event()
    never = asyncio.Event()

    async def slow_run_once(*, actor_id: str = "test") -> dict[str, int]:
        _ = actor_id
        entered.set()
        await never.wait()
        return {}

    monkeypatch.setattr(lifecycle, "run_once", slow_run_once)
    await asyncio.wait_for(lifecycle.start(), timeout=0.1)
    await asyncio.wait_for(entered.wait(), timeout=0.1)
    assert lifecycle.running
    await asyncio.wait_for(lifecycle.stop(), timeout=0.2)
    assert lifecycle.running is False


@pytest.mark.asyncio
async def test_orphan_cleanup_queue_durably_rotates_twenty_poison_rows(
    registry: MetaAppRegistry,
) -> None:
    orphan_ids: list[str] = []
    for index in range(21):
        asset_id = str(17840000999902000 + index)
        orphan = registry.authorize_oauth_asset(
            tenant_id="tenant-a",
            channel="instagram",
            asset_id=asset_id,
            page_id="",
            instagram_account_id=asset_id,
            app_key=APP_A_KEY,
            credential=MetaBindingCredential(
                access_token=f"orphan-token-{index}",
                token_app_id="1035856539045307",
                token_profile_id=asset_id,
                scopes=FULL_SCOPES,
                expires_at=int(time.time()) + 30 * 24 * 3600,
                auth_flow="instagram_login",
            ),
            actor_id="owner",
            status="testing",
            auth_flow="instagram_login",
            webhook_subscription_status="pending",
            create_new_binding=True,
        )
        orphan_ids.append(orphan.binding_id)

    attempted: list[str] = []

    async def poison(binding_id: str, **_kwargs: object) -> None:
        attempted.append(binding_id)
        raise MetaRegistryError("simulated orphan provider outage")

    lifecycle = InstagramLoginLifecycle()
    with patch("services.meta_instagram_login_lifecycle.get_meta_app_registry", return_value=registry):
        with patch(
            "services.meta_instagram_login_lifecycle.retry_instagram_login_orphan_cleanup",
            side_effect=poison,
        ):
            first = await lifecycle._run_cycle(actor_id="test", instagram_configured=False)
            second = await lifecycle._run_cycle(actor_id="test", instagram_configured=False)

    assert first["orphan_checked"] == 20
    assert second["orphan_checked"] == 20
    assert attempted[:20] == orphan_ids[:20]
    assert attempted[20] == orphan_ids[20]


@pytest.mark.asyncio
async def test_expired_poison_binding_does_not_abort_later_active_work(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _binding(registry, auth_flow="instagram_login")
    second_asset = "17840000999900022"
    second = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=second_asset,
        page_id="",
        instagram_account_id=second_asset,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="second-expired-token",
            token_app_id="1035856539045307",
            token_profile_id=second_asset,
            scopes=FULL_SCOPES,
            expires_at=int(time.time()) - 1,
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        status="active",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
    )
    with registry._locked():
        state = registry._read_unlocked()
        first_credential = dict(state["credentials"][first.credential_id])
        decoded = registry._cipher.open(first_credential["sealed"], aad=first_credential["aad"])
        decoded["expires_at"] = int(time.time()) - 1
        first_credential["sealed"] = registry._cipher.seal(decoded, aad=first_credential["aad"])
        state["credentials"][first.credential_id] = first_credential
        registry._write_unlocked(state)

    original_set = registry.set_binding_status
    settled: list[str] = []

    def fail_first(binding_id: str, **kwargs: object) -> object:
        if binding_id == first.binding_id:
            raise MetaRegistryError("simulated one-row status failure")
        settled.append(binding_id)
        return original_set(binding_id, **kwargs)

    monkeypatch.setattr(registry, "set_binding_status", fail_first)
    lifecycle = InstagramLoginLifecycle()
    with patch("services.meta_instagram_login_lifecycle.get_meta_app_registry", return_value=registry):
        await lifecycle._run_cycle(actor_id="test", instagram_configured=True)

    assert settled == [second.binding_id]
    assert next(item for item in registry.list_bindings() if item.binding_id == first.binding_id).active
    assert (
        next(item for item in registry.list_bindings() if item.binding_id == second.binding_id).status == "disconnected"
    )
