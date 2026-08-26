"""Signed end-to-end Meta Page feed comment webhook route tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from modules import meta_messaging_webhook
from services.meta_comment_events import ResolvedMetaCommentEvent

APP_A_SECRET = "feed-webhook-test-secret"
PAGE_ID = "page_feed_test_1"


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


def _feed_comment_body(*, comment_id: str = "comment_1") -> bytes:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "time": 1720000000,
                "changes": [
                    {
                        "field": "feed",
                        "value": {
                            "item": "comment",
                            "verb": "add",
                            "comment_id": comment_id,
                            "post_id": "post_1",
                            "message": "hello from feed",
                            "from": {"id": "user_1", "name": "User"},
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _install_feed_mocks(
    monkeypatch: pytest.MonkeyPatch, *, binding: Any, settings: Any, resolved: ResolvedMetaCommentEvent
) -> None:
    monkeypatch.setattr(
        meta_messaging_webhook, "_comment_deduper", meta_messaging_webhook.InMemoryMessageDeduper(ttl_seconds=60)
    )
    monkeypatch.setattr(meta_messaging_webhook, "_background_tasks", set())
    monkeypatch.setattr(meta_messaging_webhook, "meta_multi_app_registry_enabled", lambda: True)
    monkeypatch.setattr(
        meta_messaging_webhook,
        "identify_signed_meta_app",
        lambda _body, _sig: SimpleNamespace(key="linas_first_party", app_secret=APP_A_SECRET),
    )
    monkeypatch.setattr(
        meta_messaging_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(enabled=True, app_secret=APP_A_SECRET),
    )
    monkeypatch.setattr(meta_messaging_webhook, "resolve_registry_comment_events", lambda *a, **k: [resolved])
    monkeypatch.setattr(meta_messaging_webhook, "count_raw_comment_changes", lambda _p: 1)
    monkeypatch.setattr(meta_messaging_webhook, "registry_auth_flow_for_webhook_object", lambda _obj: "facebook_login")
    monkeypatch.setattr(meta_messaging_webhook, "resolve_registry_events", AsyncMock(return_value=[]))
    persist_created = {"n": 0}

    def fake_persist(*_a: object, **_k: object) -> tuple[str, bool]:
        persist_created["n"] += 1
        return ("evt_feed_1", persist_created["n"] == 1)

    monkeypatch.setattr("services.scale.meta_ingress.persist_meta_comment_accepted", fake_persist)
    monkeypatch.setattr("services.scale.meta_ingress.enqueue_meta_inbound_event", lambda *a, **k: "queued")
    monkeypatch.setattr("services.durable_event_claim.meta_claim_binding_digest", lambda _v: "digest")


@pytest.mark.asyncio
async def test_signed_feed_comment_accepted_once(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _feed_comment_body()
    signature = _sign(APP_A_SECRET, body)
    binding = SimpleNamespace(
        binding_id="bind_feed",
        tenant_id="linas",
        channel="facebook",
        app_key="linas_first_party",
        asset_id=PAGE_ID,
        page_id=PAGE_ID,
        auth_flow="facebook_login",
        active=True,
        status="active",
    )
    settings = SimpleNamespace(app_key="linas_first_party", page_id=PAGE_ID)
    resolved = ResolvedMetaCommentEvent(
        event={
            "channel": "facebook",
            "comment_id": "comment_1",
            "post_id": "post_1",
            "author_id": "user_1",
            "text": "hello from feed",
            "message_id": "comment_1",
            "account_id": PAGE_ID,
        },
        settings=settings,
        binding=binding,
    )
    _install_feed_mocks(monkeypatch, binding=binding, settings=settings, resolved=resolved)

    async def fake_claim(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("queued webhook must not await Firestore claim")

    monkeypatch.setattr("services.durable_event_claim.try_claim_event_handle", fake_claim)
    first = await meta_messaging_webhook.receive_meta_messaging_webhook(_request(body, signature))
    second = await meta_messaging_webhook.receive_meta_messaging_webhook(_request(body, signature))
    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = json.loads(first.body)
    second_payload = json.loads(second.body)
    assert first_payload["comments_accepted"] == 1
    assert first_payload["comments_duplicates"] == 0
    assert second_payload["comments_accepted"] == 0
    assert second_payload["comments_duplicates"] == 1


@pytest.mark.asyncio
async def test_invalid_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _feed_comment_body()
    monkeypatch.setattr(meta_messaging_webhook, "meta_multi_app_registry_enabled", lambda: True)
    monkeypatch.setattr(meta_messaging_webhook, "identify_signed_meta_app", lambda *_a, **_k: None)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await meta_messaging_webhook.receive_meta_messaging_webhook(_request(body, "sha256=bad"))
    assert exc.value.status_code == 401
