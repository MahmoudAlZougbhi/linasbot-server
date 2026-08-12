"""Tests for Resend mail transport, templates, webhooks, and auth email security."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from modules.api_security import is_public_api
from services.auth_email_tokens import AuthEmailTokenService
from services.email_delivery_store import EmailDeliveryStore
from services.email_dispatch import dispatch_template_email, oauth_email_policy
from services.email_templates_catalog import list_template_ids
from services.email_templates_render import render_transactional_email
from services.resend_webhook_verify import WebhookSignatureError, verify_resend_webhook


@pytest.fixture()
def token_svc(tmp_path: Path) -> AuthEmailTokenService:
    return AuthEmailTokenService(store_dir=tmp_path / "tokens")


@pytest.fixture(scope="module")
def app_client() -> TestClient:
    import main  # noqa: F401
    from modules.core import app

    return TestClient(app)


def _sign(secret: str, msg_id: str, timestamp: str, body: str) -> str:
    raw = secret[len("whsec_") :] if secret.startswith("whsec_") else secret
    key = base64.b64decode(raw)
    digest = hmac.new(key, f"{msg_id}.{timestamp}.{body}".encode(), hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode("ascii")


def test_resend_webhook_is_public() -> None:
    assert is_public_api("POST", "/api/webhooks/resend")
    assert is_public_api("POST", "/api/auth/confirm-email-change")


def test_templates_cover_auth_and_billing() -> None:
    ids = set(list_template_ids())
    for required in (
        "verify_email",
        "reset_password",
        "password_changed",
        "email_change_confirm",
        "email_changed_notice",
        "welcome",
        "billing_subscription_started",
        "billing_credits_purchased",
    ):
        assert required in ids


def test_render_blocks_open_redirect() -> None:
    bad = render_transactional_email(
        template_id="verify_email",
        action_url="https://evil.example/phish",
        locale="en",
    )
    assert "evil.example" not in bad.html_body
    assert "evil.example" not in bad.text_body

    good = render_transactional_email(
        template_id="verify_email",
        action_url="https://www.linasaibot.com/verify-email?token=abc",
        locale="en",
    )
    assert "www.linasaibot.com/verify-email" in good.html_body
    assert "Linas AI" in good.html_body


def test_render_ar_rtl() -> None:
    rendered = render_transactional_email(
        template_id="reset_password",
        action_url="https://linasaibot.com/reset-password?token=x",
        locale="ar",
    )
    assert 'dir="rtl"' in rendered.html_body
    assert rendered.locale == "ar"


def test_email_change_token_meta(token_svc: AuthEmailTokenService) -> None:
    raw = token_svc.issue(
        purpose="email_change",
        user_id="u9",
        email="new@example.com",
        tenant_id="acme",
        meta={"previous_email": "old@example.com"},
    )
    peeked = token_svc.peek(raw, "email_change")
    assert peeked is not None
    assert peeked.meta is not None
    assert peeked.meta["previous_email"] == "old@example.com"
    assert token_svc.consume(raw, "email_change") is not None
    assert token_svc.consume(raw, "email_change") is None


def test_oauth_email_policy_apple_google() -> None:
    apple = oauth_email_policy(provider="apple", email_verified_by_provider=True)
    assert apple["skip_verification_email"] is True
    assert apple["accepts_private_relay"] is True
    google = oauth_email_policy(provider="google", email_verified_by_provider=True)
    assert google["skip_verification_email"] is True
    assert oauth_email_policy(provider="apple", email_verified_by_provider=False)["skip_verification_email"] is False


def test_dispatch_idempotency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "")
    monkeypatch.setenv("RESEND_API_KEY_SENDING", "")
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("MAIL_LOG_LINKS", "true")
    from services import email_dispatch as ed

    ed._idempotency = ed._IdempotencyStore(store_dir=tmp_path / "idem")  # type: ignore[attr-defined]
    with mock.patch("services.email_dispatch.send_email") as send_mock:
        send_mock.return_value = mock.Mock(sent=True, reason="ok", provider="resend", message_id="msg_1")
        first = dispatch_template_email(
            template_id="welcome",
            to_email="a@example.com",
            action_path="/login",
            idempotency_key="welcome:u1",
        )
        second = dispatch_template_email(
            template_id="welcome",
            to_email="a@example.com",
            action_path="/login",
            idempotency_key="welcome:u1",
        )
    assert first.sent is True
    assert second.idempotent_replay is True
    assert send_mock.call_count == 1


def test_webhook_signature_and_idempotency(tmp_path: Path) -> None:
    secret = "whsec_" + base64.b64encode(b"test-secret-bytes-123456").decode("ascii")
    body_obj = {"type": "email.bounced", "data": {"email_id": "re_123", "to": ["ab@example.com"]}}
    body = json.dumps(body_obj, separators=(",", ":"))
    msg_id = "msg_test_1"
    ts = str(int(time.time()))
    sig = _sign(secret, msg_id, ts, body)
    parsed = verify_resend_webhook(
        payload=body,
        headers={"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": sig},
        secret=secret,
    )
    assert parsed["type"] == "email.bounced"

    with pytest.raises(WebhookSignatureError):
        verify_resend_webhook(
            payload=body,
            headers={"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": "v1,bad"},
            secret=secret,
        )

    store = EmailDeliveryStore(store_dir=tmp_path / "delivery")
    first = store.record_event(svix_id=msg_id, payload=parsed)
    second = store.record_event(svix_id=msg_id, payload=parsed)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert first["record"]["state"] == "bounced"


def test_resend_webhook_endpoint_rejects_bad_signature(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RESEND_WEBHOOK_SECRET",
        "whsec_" + base64.b64encode(b"endpoint-secret-bytes-xyz").decode("ascii"),
    )
    response = app_client.post(
        "/api/webhooks/resend",
        content=b'{"type":"email.delivered","data":{}}',
        headers={"svix-id": "x", "svix-timestamp": str(int(time.time())), "svix-signature": "v1,nope"},
    )
    assert response.status_code == 400


def test_mail_service_prefers_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_not_real")
    from services import mail_service as ms

    with mock.patch("services.resend_client.resend_configured", return_value=True):
        with mock.patch("services.resend_client.send_resend_email") as inner:
            inner.return_value = mock.Mock(ok=True, reason="ok", message_id="m1", status_code=200)
            result = ms.send_email(to_email="t@example.com", subject="Hi", text_body="Hello")
    assert result.sent is True
    assert result.provider == "resend"
    assert result.message_id == "m1"
    inner.assert_called_once()
