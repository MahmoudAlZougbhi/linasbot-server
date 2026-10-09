from __future__ import annotations

from pathlib import Path

from services.scale.sensitive_request_logging import redact_pii


def test_pii_redaction_masks_email_and_phone() -> None:
    cleaned = redact_pii("mail ada@example.com phone +15551212000 token=secret")
    assert "ada@example.com" not in cleaned
    assert "+15551212000" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned
    assert "[REDACTED_PHONE]" in cleaned


def test_load_scripts_refuse_production() -> None:
    names = ("owner_api.js", "sse.js", "webhook.js", "webchat.js", "ai_reply.js", "copilot.js")
    for name in names:
        text = Path("loadtest/k6", name).read_text(encoding="utf-8")
        assert "linasaibot.com" in text
        assert "refusing" in text


def test_bootstrap_bucket_is_not_shared() -> None:
    text = Path("modules/web_chat_public_routes.py").read_text(encoding="utf-8")
    assert 'session_id="bootstrap"' not in text
    assert "bootstrap:{client}" in text
