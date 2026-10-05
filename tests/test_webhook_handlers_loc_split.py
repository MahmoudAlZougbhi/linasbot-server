"""Legacy /webhook stays a thin verify+ignore route. The process chain stays deleted."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_webhook_museum_modules_are_gone() -> None:
    for rel in (
        "modules/webhook_handlers_dedupe.py",
        "modules/webhook_handlers_parse.py",
        "modules/webhook_handlers_process.py",
        "modules/webhook_handlers_photo.py",
        "modules/webhook_handlers_voice.py",
        "services/brain/inbound/voice_handlers.py",
    ):
        assert not (ROOT / rel).exists(), rel
    webhook = (ROOT / "modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert len(webhook.splitlines()) < 400
    assert "process_parsed_message" not in webhook
    assert "whatsapp_inbound_ai_disabled" in webhook
    assert '@app.get("/webhook")' in webhook
    assert '@app.post("/webhook")' in webhook
    cloud = (ROOT / "modules/whatsapp_cloud_webhook.py").read_text(encoding="utf-8")
    assert "/webhook/whatsapp-cloud" in cloud
