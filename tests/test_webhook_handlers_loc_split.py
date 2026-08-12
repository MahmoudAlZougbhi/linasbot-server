"""LOC split: webhook_handlers dedupe/parse/process/media under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_webhook_handlers_modules_under_500_lines() -> None:
    assert _line_count("modules/webhook_handlers.py") < 500
    assert _line_count("modules/webhook_handlers_dedupe.py") < 500
    assert _line_count("modules/webhook_handlers_parse.py") < 500
    assert _line_count("modules/webhook_handlers_process.py") < 500
    assert _line_count("modules/webhook_handlers_photo.py") < 500
    assert _line_count("modules/webhook_handlers_voice.py") < 500


def test_webhook_handlers_preserves_public_api() -> None:
    from modules.webhook_handlers_dedupe import _webhook_text_body_fingerprint

    webhook = Path("modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert "from modules.webhook_handlers_dedupe import" in webhook
    assert "from modules.webhook_handlers_process import" in webhook
    assert "process_parsed_message" in webhook
    assert "handle_message_whatsapp_with_adapter" in webhook
    assert "whatsapp_inbound_ai_disabled" in webhook
    assert callable(_webhook_text_body_fingerprint)
    p = {"type": "text", "content": {"text": "hi"}, "phone_number": "+96171112222", "user_id": "+96171112222"}
    assert _webhook_text_body_fingerprint(p).startswith("bodyfp_")
