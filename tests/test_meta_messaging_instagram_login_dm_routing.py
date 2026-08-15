"""The App A callback accepts page-linked Instagram, never Direct Instagram Login."""

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

from modules import meta_messaging_webhook
from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential
from services.meta_messaging import InMemoryMessageDeduper
from tests.meta_compliance_helpers import _FakeFirestore

PROD_IG_ID = "17841413184256533"
APP_A_SECRET = "multi-app-a-secret"
INSTAGRAM_LOGIN_SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
    "instagram_business_content_publish",
)
FACEBOOK_LOGIN_IG_SCOPES = (
    "pages_show_list",
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


def _ig_dm_body(account_id: str, *, mid: str) -> bytes:
    payload = {
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
    }
    return json.dumps(payload, separators=(",", ":")).encode()


@pytest.fixture
def registry_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", APP_A_SECRET)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "ig-login-dm-webhook-secret-tests-1234567890")
    firestore = _FakeFirestore()
    monkeypatch.setattr("utils.utils.get_firestore_db", lambda: firestore)
    registry = MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="ig-login-dm-webhook-secret-tests-1234567890",
    )
    monkeypatch.setattr("services.meta_multi_app_router.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.meta_comment_events.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(
        meta_messaging_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(enabled=True, verify_token="", app_secret=""),
    )
    meta_messaging_webhook._message_deduper = InMemoryMessageDeduper(ttl_seconds=60)
    return registry


def _authorize_instagram_login(registry: MetaAppRegistry, *, asset_id: str = PROD_IG_ID) -> None:
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="instagram",
        asset_id=asset_id,
        page_id="",
        instagram_account_id=asset_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="ig-login-token",
            token_app_id="1035856539045307",
            token_profile_id=asset_id,
            scopes=INSTAGRAM_LOGIN_SCOPES,
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


def _authorize_facebook_login_ig(registry: MetaAppRegistry, *, asset_id: str = PROD_IG_ID) -> None:
    page_id = "378696005334409"
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="instagram",
        asset_id=asset_id,
        page_id=page_id,
        instagram_account_id=asset_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="page-linked-ig-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=FACEBOOK_LOGIN_IG_SCOPES,
            authorized_meta_user_id="998877",
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="facebook_login",
    )


async def _post_ig_dm(account_id: str, *, mid: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    processed: list[str] = []

    async def claim(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def finish(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def process(event: dict[str, Any], _settings: Any, **_kwargs: Any) -> dict[str, str]:
        processed.append(str(event.get("meta_auth_flow") or ""))
        return {"delivery": "delivered"}

    monkeypatch.setattr("services.durable_event_claim.try_claim_event", claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", finish)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", finish)
    monkeypatch.setattr(meta_messaging_webhook, "process_meta_social_event", process)
    body = _ig_dm_body(account_id, mid=mid)
    response = await meta_messaging_webhook.receive_meta_messaging_webhook(_request(body, _sign(APP_A_SECRET, body)))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return {"json": json.loads(response.body), "processed": processed}


@pytest.mark.asyncio
async def test_instagram_object_rejects_instagram_login_binding_on_app_a_callback(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authorize_instagram_login(registry_env)
    result = await _post_ig_dm(PROD_IG_ID, mid="ig-login-mid", monkeypatch=monkeypatch)
    assert result["json"]["accepted"] == 0
    assert result["processed"] == []


@pytest.mark.asyncio
async def test_instagram_object_accepts_facebook_login_legacy_binding(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authorize_facebook_login_ig(registry_env)
    result = await _post_ig_dm(PROD_IG_ID, mid="ig-fb-login-mid", monkeypatch=monkeypatch)
    assert result["json"]["accepted"] == 1
    assert result["processed"] == ["facebook_login"]


@pytest.mark.asyncio
async def test_instagram_object_rejects_wrong_account(
    registry_env: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authorize_instagram_login(registry_env)
    result = await _post_ig_dm("17841400000000000", mid="ig-wrong-account", monkeypatch=monkeypatch)
    assert result["json"]["accepted"] == 0
    assert result["processed"] == []


def test_meta_messaging_webhook_uses_callback_auth_flow_boundary() -> None:
    source = Path(meta_messaging_webhook.__file__).read_text(encoding="utf-8")
    assert "registry_auth_flow_for_webhook_object(payload_object)" in source
