"""Instagram/Facebook webhook isolation: signatures, routing, and no FB fallback."""

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
from fastapi import HTTPException
from starlette.requests import Request

from modules import meta_instagram_login_webhook, meta_messaging_webhook
from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential
from services.meta_instagram_login_config import verify_instagram_login_webhook_signature
from services.meta_messaging import InMemoryMessageDeduper
from tests.meta_compliance_helpers import _FakeFirestore

IG_ID = "17841413184256533"
PAGE_ID = "378696005334409"
APP_A_SECRET = "multi-app-a-secret"
IG_SECRET = "instagram-app-secret-tests"
IG_SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
    "instagram_business_content_publish",
)
FB_SCOPES = ("pages_show_list", "pages_messaging", "pages_manage_metadata")


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _request(path: str, body: bytes, signature: str) -> Request:
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
            "path": path,
            "query_string": b"",
            "headers": [(b"x-hub-signature-256", signature.encode())],
        },
        receive,
    )


def _ig_dm(account_id: str, *, mid: str) -> bytes:
    return json.dumps(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": account_id,
                    "messaging": [
                        {
                            "sender": {"id": "igsid-reviewer"},
                            "recipient": {"id": account_id},
                            "message": {"mid": mid, "text": "مرحبا"},
                        }
                    ],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _page_dm(*, mid: str) -> bytes:
    return json.dumps(
        {
            "object": "page",
            "entry": [
                {
                    "id": PAGE_ID,
                    "messaging": [
                        {
                            "sender": {"id": "psid-reviewer"},
                            "recipient": {"id": PAGE_ID},
                            "message": {"mid": mid, "text": "hello"},
                        }
                    ],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


@pytest.fixture
def registry_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", APP_A_SECRET)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", IG_SECRET)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "ig-dm-isolation-secret-tests-1234567890")
    monkeypatch.setattr("utils.utils.get_firestore_db", lambda: _FakeFirestore())
    registry = MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="ig-dm-isolation-secret-tests-1234567890",
    )
    monkeypatch.setattr("services.meta_multi_app_router.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.meta_comment_events.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(
        meta_messaging_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(enabled=True, verify_token="", app_secret=""),
    )
    monkeypatch.setattr(
        meta_instagram_login_webhook, "get_meta_messaging_settings", lambda: SimpleNamespace(enabled=True)
    )
    meta_messaging_webhook._message_deduper = InMemoryMessageDeduper(ttl_seconds=60)
    meta_instagram_login_webhook._message_deduper = InMemoryMessageDeduper(ttl_seconds=60)
    return registry


def _ig_login(registry: MetaAppRegistry, *, token: str = "ig-login-token") -> None:
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="instagram",
        asset_id=IG_ID,
        page_id="",
        instagram_account_id=IG_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=token,
            token_app_id="1035856539045307",
            token_profile_id=IG_ID,
            scopes=IG_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("comments", "messages", "messaging_postbacks"),
    )


def _facebook_page(registry: MetaAppRegistry) -> None:
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=PAGE_ID,
        page_id=PAGE_ID,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="page-token",
            token_app_id="2963733803971681",
            token_profile_id=PAGE_ID,
            scopes=FB_SCOPES,
            authorized_meta_user_id="998877",
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        auth_flow="facebook_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
    )


async def _capture_process(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def claim(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def finish(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def process(event: dict[str, Any], settings: Any, **kwargs: Any) -> dict[str, str]:
        seen.append(
            {
                "auth_flow": str(event.get("meta_auth_flow") or ""),
                "binding_id": str(kwargs.get("binding_id") or ""),
                "token": str(getattr(settings, "page_access_token", "") or ""),
                "graph": str(getattr(settings, "graph_base_url", "") or ""),
            }
        )
        return {"delivery": "delivered"}

    monkeypatch.setattr("services.durable_event_claim.try_claim_event", claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", finish)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", finish)
    monkeypatch.setattr(
        "services.scale.meta_ingress.persist_meta_dm_accepted",
        lambda *_args, **_kwargs: ("event-iso-1", True),
    )
    monkeypatch.setattr("services.scale.meta_ingress.enqueue_meta_inbound_event", lambda *_args, **_kwargs: "inline")
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_processing", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_completed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_failed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(meta_messaging_webhook, "process_meta_social_event", process)
    monkeypatch.setattr(meta_instagram_login_webhook, "process_meta_social_event", process)
    return seen


@pytest.mark.asyncio
async def test_a_instagram_login_callback_accepts_valid_ig_signature(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ig_login(registry_env)
    seen = await _capture_process(monkeypatch)
    body = _ig_dm(IG_ID, mid="ig-normal-mid")
    response = await meta_instagram_login_webhook.receive_instagram_login_webhook(
        _request("/webhook/instagram-login", body, _sign(IG_SECRET, body))
    )
    await asyncio.sleep(0)
    data = json.loads(response.body)
    assert data["accepted"] == 1
    assert seen[0]["auth_flow"] == "instagram_login"
    assert seen[0]["token"] == "ig-login-token"
    assert "graph.instagram.com" in seen[0]["graph"]


@pytest.mark.asyncio
async def test_f_instagram_object_on_meta_messaging_uses_app_a_secret(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ig_login(registry_env)
    seen = await _capture_process(monkeypatch)
    body = _ig_dm(IG_ID, mid="ig-on-app-a")
    response = await meta_messaging_webhook.receive_meta_messaging_webhook(
        _request("/webhook/meta-messaging", body, _sign(APP_A_SECRET, body))
    )
    await asyncio.sleep(0)
    data = json.loads(response.body)
    assert data["accepted"] == 1
    assert seen[0]["auth_flow"] == "instagram_login"
    assert seen[0]["token"] == "ig-login-token"
    assert seen[0]["token"] != "page-token"


@pytest.mark.asyncio
async def test_g_facebook_page_on_meta_messaging(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _facebook_page(registry_env)
    seen = await _capture_process(monkeypatch)
    body = _page_dm(mid="fb-page-mid")
    response = await meta_messaging_webhook.receive_meta_messaging_webhook(
        _request("/webhook/meta-messaging", body, _sign(APP_A_SECRET, body))
    )
    await asyncio.sleep(0)
    data = json.loads(response.body)
    assert data["accepted"] == 1
    assert seen[0]["auth_flow"] == "facebook_login"
    assert seen[0]["token"] == "page-token"


@pytest.mark.asyncio
async def test_h_signature_isolation_rejects_cross_app_secrets(
    registry_env: MetaAppRegistry,
) -> None:
    body = _ig_dm(IG_ID, mid="sig-iso")
    assert verify_instagram_login_webhook_signature(body, _sign(IG_SECRET, body))
    assert not verify_instagram_login_webhook_signature(body, _sign(APP_A_SECRET, body))
    with pytest.raises(HTTPException) as ig_exc:
        await meta_instagram_login_webhook.receive_instagram_login_webhook(
            _request("/webhook/instagram-login", body, _sign(APP_A_SECRET, body))
        )
    assert ig_exc.value.status_code == 401
    with pytest.raises(HTTPException) as fb_exc:
        await meta_messaging_webhook.receive_meta_messaging_webhook(
            _request("/webhook/meta-messaging", body, _sign(IG_SECRET, body))
        )
    assert fb_exc.value.status_code == 401


@pytest.mark.asyncio
async def test_i_no_active_instagram_binding_has_no_facebook_fallback(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _facebook_page(registry_env)
    seen = await _capture_process(monkeypatch)
    body = _ig_dm(IG_ID, mid="no-ig-binding")
    response = await meta_instagram_login_webhook.receive_instagram_login_webhook(
        _request("/webhook/instagram-login", body, _sign(IG_SECRET, body))
    )
    await asyncio.sleep(0)
    data = json.loads(response.body)
    assert data["accepted"] == 0
    assert seen == []


@pytest.mark.asyncio
async def test_k_instagram_comments_still_accepted(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.meta_comment_replies import CommentReplyResult

    _ig_login(registry_env)
    processed: list[str] = []

    async def claim(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def finish(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def process_comment(resolved: Any, **_kwargs: Any) -> CommentReplyResult:
        processed.append(str(resolved.binding.auth_flow))
        return CommentReplyResult(status="sent", reply_id="reply-1")

    monkeypatch.setattr("services.durable_event_claim.try_claim_event", claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", finish)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", finish)
    monkeypatch.setattr(
        "services.scale.meta_ingress.persist_meta_comment_accepted",
        lambda *_args, **_kwargs: ("event-comment-1", True),
    )
    monkeypatch.setattr("services.scale.meta_ingress.enqueue_meta_inbound_event", lambda *_args, **_kwargs: "inline")
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_processing", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_completed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(meta_instagram_login_webhook, "process_meta_comment_event", process_comment)
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": IG_ID,
                "time": 1_700_000_000,
                "field": "comments",
                "value": {
                    "id": "comment-1",
                    "text": "price?",
                    "from": {"username": "customer"},
                    "media": {"id": "media-1"},
                },
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = await meta_instagram_login_webhook.receive_instagram_login_webhook(
        _request("/webhook/instagram-login", body, _sign(IG_SECRET, body))
    )
    await asyncio.sleep(0)
    data = json.loads(response.body)
    assert data["comments_accepted"] == 1
    assert processed == ["instagram_login"]


@pytest.mark.asyncio
async def test_m_duplicate_webhook_does_not_process_twice(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ig_login(registry_env)
    seen = await _capture_process(monkeypatch)
    created = {"n": 0}

    def persist(*_args: Any, **_kwargs: Any) -> tuple[str, bool]:
        created["n"] += 1
        return ("event-dup-1", created["n"] == 1)

    monkeypatch.setattr("services.scale.meta_ingress.persist_meta_dm_accepted", persist)
    body = _ig_dm(IG_ID, mid="dup-mid")
    first = await meta_instagram_login_webhook.receive_instagram_login_webhook(
        _request("/webhook/instagram-login", body, _sign(IG_SECRET, body))
    )
    second = await meta_instagram_login_webhook.receive_instagram_login_webhook(
        _request("/webhook/instagram-login", body, _sign(IG_SECRET, body))
    )
    await asyncio.sleep(0)
    assert json.loads(first.body)["accepted"] == 1
    assert json.loads(second.body)["duplicates"] == 1
    assert len(seen) == 1
