"""Instagram Login webhook routing and signature tests."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.requests import Request

from modules import meta_instagram_login_webhook
from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential, get_meta_app_configs
from services.meta_instagram_login_config import (
    META_INSTAGRAM_LOGIN_REQUEST_SCOPES,
    instagram_login_config_status,
    instagram_login_webhook_verify_token,
    verify_instagram_login_challenge_token,
    verify_instagram_login_webhook_signature,
)
from services.meta_messaging import InMemoryMessageDeduper
from services.meta_multi_app_router import resolve_registry_events

INSTAGRAM_SCOPES = tuple(sorted(META_INSTAGRAM_LOGIN_REQUEST_SCOPES))


def _signed_instagram_request(body: bytes, *, secret: str = "app-a-secret-tests") -> Request:
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/instagram-login",
            "query_string": b"",
            "headers": [(b"x-hub-signature-256", signature.encode())],
        },
        receive,
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
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-webhook-registry-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-webhook-registry-secret-tests-1234567890",
    )


def test_instagram_login_webhook_verify_token_requires_dedicated_secret(instagram_env: None) -> None:
    assert instagram_login_webhook_verify_token() == "verify-ig-login-tests"
    assert verify_instagram_login_challenge_token("verify-ig-login-tests")
    assert not verify_instagram_login_challenge_token("verify-a-tests")


def test_instagram_login_webhook_signature_uses_app_a_signing_secret(instagram_env: None) -> None:
    body = b'{"object":"instagram"}'
    app_a_digest = hmac.new(b"app-a-secret-tests", body, hashlib.sha256).hexdigest()
    instagram_digest = hmac.new(b"instagram-app-secret-tests", body, hashlib.sha256).hexdigest()
    assert verify_instagram_login_webhook_signature(body, f"sha256={app_a_digest}")
    assert not verify_instagram_login_webhook_signature(body, f"sha256={instagram_digest}")
    assert not verify_instagram_login_webhook_signature(body, None)


def test_instagram_login_config_status_reports_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.delenv("META_INSTAGRAM_LOGIN_APP_SECRET", raising=False)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    status = instagram_login_config_status()
    assert not status.configured
    assert "META_INSTAGRAM_LOGIN_APP_SECRET" in status.missing


@pytest.mark.asyncio
async def test_resolve_registry_events_filters_instagram_login_bindings(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900001"
    registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="ig-login-token",
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=INSTAGRAM_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
    )
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": instagram_id},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "mid-1", "text": "hello"},
                    }
                ],
            }
        ],
    }
    app_config = get_meta_app_configs()[APP_A_KEY]
    instagram_routed = await resolve_registry_events(
        payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    facebook_routed = await resolve_registry_events(
        payload,
        app_config=app_config,
        registry=registry,
        auth_flow="facebook_login",
    )
    assert len(instagram_routed) == 1
    assert instagram_routed[0].binding.auth_flow == "instagram_login"
    assert instagram_routed[0].settings.graph_base_url == "https://graph.instagram.com"
    assert instagram_routed[0].settings.app_secret == "instagram-app-secret-tests"
    assert facebook_routed == []
    assert "ig-login-token" not in json.dumps(instagram_routed[0].event)


def _authorize_instagram_login_binding(
    registry: MetaAppRegistry,
    *,
    tenant_id: str,
    instagram_id: str,
    token: str = "ig-login-token",
    comments: bool = False,
) -> None:
    registry.authorize_oauth_asset(
        tenant_id=tenant_id,
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=token,
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=INSTAGRAM_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=(
            "messages",
            "messaging_postbacks",
            *(("comments",) if comments else ()),
        ),
    )


@pytest.mark.asyncio
async def test_resolve_registry_events_isolates_cross_tenant_bindings(registry: MetaAppRegistry) -> None:
    tenant_a_ig = "17840000999900001"
    tenant_b_ig = "17840000999900099"
    _authorize_instagram_login_binding(registry, tenant_id="tenant-a", instagram_id=tenant_a_ig)
    _authorize_instagram_login_binding(registry, tenant_id="tenant-b", instagram_id=tenant_b_ig, token="other-token")
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": tenant_a_ig,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": tenant_a_ig},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "mid-tenant", "text": "hello"},
                    }
                ],
            }
        ],
    }
    app_config = get_meta_app_configs()[APP_A_KEY]
    routed = await resolve_registry_events(
        payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    assert len(routed) == 1
    assert routed[0].settings.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_resolve_registry_events_parses_postback_and_comment_fixtures(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900002"
    _authorize_instagram_login_binding(registry, tenant_id="tenant-a", instagram_id=instagram_id)
    postback_payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": "sender-2"},
                        "recipient": {"id": instagram_id},
                        "timestamp": 1_700_000_001_000,
                        "postback": {"mid": "pb-1", "title": "Book", "payload": "BOOK_NOW"},
                    }
                ],
            }
        ],
    }
    comment_payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment-1",
                            "from": {"id": "commenter-1"},
                            "text": "price?",
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }
    app_config = get_meta_app_configs()[APP_A_KEY]
    postback_routed = await resolve_registry_events(
        postback_payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    assert len(postback_routed) == 1
    assert postback_routed[0].event.get("is_postback") is True

    comment_routed = await resolve_registry_events(
        comment_payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    assert comment_routed == []


@pytest.mark.asyncio
async def test_resolve_registry_events_skips_echo_messages(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900003"
    _authorize_instagram_login_binding(registry, tenant_id="tenant-a", instagram_id=instagram_id)
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": instagram_id},
                        "recipient": {"id": "sender-3"},
                        "timestamp": 1_700_000_002_000,
                        "message": {"mid": "echo-1", "text": "bot reply", "is_echo": True},
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
    assert routed == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("delivery", "expect_completed", "expect_released"),
    (
        ("delivered", True, False),
        ("blocked_quota", True, False),
        ("no_text", True, False),
        ("delivery_pending", False, True),
    ),
)
async def test_dedicated_instagram_webhook_tracks_real_dm_delivery_outcome(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    delivery: str,
    expect_completed: bool,
    expect_released: bool,
) -> None:
    instagram_id = "17840000999900044"
    _authorize_instagram_login_binding(registry, tenant_id="tenant-a", instagram_id=instagram_id)
    monkeypatch.setattr("services.meta_multi_app_router.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.meta_comment_events.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(
        meta_instagram_login_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(enabled=True),
    )
    meta_instagram_login_webhook._message_deduper = InMemoryMessageDeduper(ttl_seconds=60)

    completed: list[str] = []
    released: list[str] = []
    state_updates: list[dict[str, Any]] = []
    process_kwargs: list[dict[str, Any]] = []

    async def claim(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def complete(_namespace: str, key: str, **_kwargs: Any) -> None:
        completed.append(key)

    async def release(_namespace: str, key: str, **_kwargs: Any) -> None:
        released.append(key)

    async def process(_event: dict[str, Any], _settings: Any, **kwargs: Any) -> dict[str, str]:
        process_kwargs.append(kwargs)
        return {"delivery": delivery, "logical_reply_id": "reply-1"}

    monkeypatch.setattr("services.durable_event_claim.try_claim_event", claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", release)
    monkeypatch.setattr(
        "services.scale.meta_ingress.persist_meta_dm_accepted",
        lambda *_args, **_kwargs: ("event-dedicated-1", True),
    )
    monkeypatch.setattr("services.scale.meta_ingress.enqueue_meta_inbound_event", lambda *_args, **_kwargs: "inline")
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_processing", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "services.scale.meta_ingress.mark_dm_completed",
        lambda event_id, **_kwargs: state_updates.append({"event_id": event_id, "state": "completed"}),
    )
    monkeypatch.setattr(
        "services.scale.meta_ingress.mark_dm_failed",
        lambda event_id, error: state_updates.append({"event_id": event_id, "state": "failed", "error": error}),
    )
    monkeypatch.setattr(
        "services.scale.inbound_event_store.mark_inbound_state",
        lambda event_id, **kwargs: state_updates.append({"event_id": event_id, **kwargs}),
    )
    monkeypatch.setattr(meta_instagram_login_webhook, "process_meta_social_event", process)

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": "igsid-customer"},
                        "recipient": {"id": instagram_id},
                        "message": {"mid": f"mid-{delivery}", "text": "hello"},
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = await meta_instagram_login_webhook.receive_instagram_login_webhook(_signed_instagram_request(body))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert json.loads(response.body)["accepted"] == 1
    assert len(process_kwargs) == 1
    assert process_kwargs[0]["inbound_event_id"] == "event-dedicated-1"
    assert process_kwargs[0]["tenant_id"] == "tenant-a"
    active_binding = next(
        item for item in registry.list_bindings(include_inactive=False) if item.instagram_account_id == instagram_id
    )
    assert process_kwargs[0]["binding_id"] == active_binding.binding_id
    assert bool(completed) is expect_completed
    assert bool(released) is expect_released
    if expect_completed:
        assert any(item["state"] == "completed" for item in state_updates)
    else:
        assert any(
            item["state"] == "failed" and item["last_error"] == "delivery:delivery_pending" for item in state_updates
        )


@pytest.mark.asyncio
async def test_dedicated_instagram_webhook_accepts_official_direct_comment_shape(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.meta_comment_replies import CommentReplyResult

    instagram_id = "17840000999900055"
    _authorize_instagram_login_binding(
        registry,
        tenant_id="tenant-a",
        instagram_id=instagram_id,
        comments=True,
    )
    monkeypatch.setattr("services.meta_multi_app_router.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.meta_comment_events.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(
        meta_instagram_login_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(enabled=True),
    )
    meta_instagram_login_webhook._comment_deduper = InMemoryMessageDeduper(ttl_seconds=60)

    processed: list[str] = []
    completed: list[str] = []

    async def claim(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def complete(_namespace: str, key: str, **_kwargs: Any) -> None:
        completed.append(key)

    async def release(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def process_comment(resolved: Any, **_kwargs: Any) -> CommentReplyResult:
        processed.append(str(resolved.binding.auth_flow))
        return CommentReplyResult(status="sent", reply_id="reply-1")

    monkeypatch.setattr("services.durable_event_claim.try_claim_event", claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", release)
    monkeypatch.setattr(
        "services.scale.meta_ingress.persist_meta_comment_accepted",
        lambda *_args, **_kwargs: ("event-comment-1", True),
    )
    monkeypatch.setattr("services.scale.meta_ingress.enqueue_meta_inbound_event", lambda *_args, **_kwargs: "inline")
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_processing", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_completed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_failed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(meta_instagram_login_webhook, "process_meta_comment_event", process_comment)

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "time": 1_700_000_000,
                "field": "comments",
                "value": {
                    "id": "comment-direct-1",
                    "text": "price?",
                    "from": {"username": "customer_name"},
                    "media": {"id": "media-1"},
                },
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = await meta_instagram_login_webhook.receive_instagram_login_webhook(_signed_instagram_request(body))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    data = json.loads(response.body)
    assert data["accepted"] == 0
    assert data["comments_accepted"] == 1
    assert processed == ["instagram_login"]
    assert len(completed) == 1
