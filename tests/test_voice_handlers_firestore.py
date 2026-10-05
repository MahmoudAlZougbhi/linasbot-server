"""Voice inbound no longer has a dedicated Firestore handler module."""

from __future__ import annotations

from pathlib import Path


def test_voice_handlers_module_is_gone() -> None:
    assert not Path("services/brain/inbound/voice_handlers.py").exists()
    cloud = Path("modules/whatsapp_cloud_webhook.py").read_text(encoding="utf-8")
    assert "voice_handlers" not in cloud
