"""Authenticated multi-app webhook routing and duplicate-reply proofs."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.requests import Request

from modules import meta_messaging_webhook
from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
)
from services.meta_messaging import InMemoryMessageDeduper

SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
)


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _request(body: bytes, signature: str) -> Request:
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/meta-messaging",
            "query_string": b"",
            "headers": [(b"x-hub-signature-256", signature.encode())],
        },
        receive,
    )


@pytest.fixture
def configured_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "multi-app-a-secret")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a")
    monkeypatch.setenv("META_APP_B_ID", "777888999")
    monkeypatch.setenv("META_APP_B_SECRET", "multi-app-b-secret")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b")
    monkeypatch.setenv("META_APP_B_LOGIN_CONFIG_ID", "config-b")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "webhook-registry-credential-encryption-key-tests")
    registry = MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="webhook-registry-secret-for-tests-123456789",
    )
    page_id = "378696005334409"
    registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="17841413184256533",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="encrypted-page-token-test",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=SCOPES,
        ),
        actor_id="owner",
    )
    registry.activate_binding(
        tenant_id="linas",
        channel="instagram",
        asset_id="17841413184256533",
        page_id=page_id,
        instagram_account_id="17841413184256533",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="encrypted-instagram-token-test",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=SCOPES,
        ),
        actor_id="owner",
    )
    monkeypatch.setattr("services.meta_multi_app_router.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(
        meta_messaging_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(enabled=True, verify_token="", app_secret=""),
    )
    meta_messaging_webhook._message_deduper = InMemoryMessageDeduper(ttl_seconds=60)
    return registry


@pytest.mark.asyncio
async def test_receiving_app_and_asset_binding_route_exactly_once(
    configured_registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processed: list[tuple[str, str, str]] = []
    claimed: set[str] = set()

    async def try_claim(_namespace: str, key: str, **_kwargs: Any) -> bool:
        if key in claimed:
            return False
        claimed.add(key)
        return True

    async def complete(_namespace: str, _key: str, **_kwargs: Any) -> None:
        return None

    async def release(_namespace: str, key: str, **_kwargs: Any) -> None:
        claimed.discard(key)

    async def process(event: dict[str, Any], settings: Any) -> None:
        processed.append((settings.app_key, settings.tenant_id, str(event["message_id"])))

    monkeypatch.setattr("services.durable_event_claim.try_claim_event", try_claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", release)
    monkeypatch.setattr(meta_messaging_webhook, "process_meta_social_event", process)

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "378696005334409",
                "messaging": [
                    {
                        "sender": {"id": "psid-reviewer"},
                        "recipient": {"id": "378696005334409"},
                        "message": {"mid": "multi-mid-1", "text": "Hello"},
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    first = await meta_messaging_webhook.receive_meta_messaging_webhook(
        _request(body, _sign("multi-app-a-secret", body))
    )
    duplicate = await meta_messaging_webhook.receive_meta_messaging_webhook(
        _request(body, _sign("multi-app-a-secret", body))
    )
    app_b = await meta_messaging_webhook.receive_meta_messaging_webhook(
        _request(body, _sign("multi-app-b-secret", body))
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert json.loads(first.body) == {
        "status": "received",
        "accepted": 1,
        "duplicates": 0,
        "comments_accepted": 0,
        "comments_duplicates": 0,
    }
    assert json.loads(duplicate.body) == {
        "status": "received",
        "accepted": 0,
        "duplicates": 1,
        "comments_accepted": 0,
        "comments_duplicates": 0,
    }
    assert json.loads(app_b.body) == {
        "status": "received",
        "accepted": 0,
        "duplicates": 0,
        "comments_accepted": 0,
        "comments_duplicates": 0,
    }
    assert processed == [(APP_A_KEY, "linas", "multi-mid-1")]


@pytest.mark.asyncio
async def test_instagram_object_routes_only_linked_instagram_binding(
    configured_registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processed: list[str] = []

    async def claim(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def finish(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def process(event: dict[str, Any], _settings: Any) -> None:
        processed.append(str(event["channel"]))

    monkeypatch.setattr("services.durable_event_claim.try_claim_event", claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", finish)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", finish)
    monkeypatch.setattr(meta_messaging_webhook, "process_meta_social_event", process)

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "17841413184256533",
                "messaging": [
                    {
                        "sender": {"id": "igsid-reviewer"},
                        "recipient": {"id": "17841413184256533"},
                        "message": {"mid": "ig-multi-mid", "text": "مرحبا"},
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = await meta_messaging_webhook.receive_meta_messaging_webhook(
        _request(body, _sign("multi-app-a-secret", body))
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert json.loads(response.body)["accepted"] == 1
    assert processed == ["instagram"]


@pytest.mark.asyncio
async def test_wrong_or_missing_multi_app_signature_is_401(
    configured_registry: MetaAppRegistry,
) -> None:
    from fastapi import HTTPException

    body = b'{"object":"page","entry":[]}'
    with pytest.raises(HTTPException) as wrong:
        await meta_messaging_webhook.receive_meta_messaging_webhook(_request(body, "sha256=deadbeef"))
    assert wrong.value.status_code == 401
