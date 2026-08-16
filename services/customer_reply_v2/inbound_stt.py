"""Real OpenAI speech-to-text for customer inbound audio. Fail closed; never invent transcript."""

from __future__ import annotations

import io
from typing import Any

from services.providers.base import provider_config

MAX_AUDIO_BYTES = 15 * 1024 * 1024


async def transcribe_inbound_audio(*, data: bytes, filename: str = "voice.ogg") -> dict[str, Any]:
    raw = data or b""
    if not raw:
        return {"ok": False, "error": "empty_audio", "text": "", "model": ""}
    if len(raw) > MAX_AUDIO_BYTES:
        return {"ok": False, "error": "audio_too_large", "text": "", "model": ""}
    cfg = provider_config()["stt"]
    if cfg.get("provider") != "openai":
        return {"ok": False, "error": "stt_provider_not_openai", "text": "", "model": str(cfg.get("model") or "")}
    try:
        from services import llm_core_service

        client = getattr(llm_core_service, "client", None)
        if client is None or not hasattr(client, "audio"):
            return {"ok": False, "error": "stt_client_unavailable", "text": "", "model": str(cfg.get("model") or "")}
        buf = io.BytesIO(raw)
        buf.name = filename or "voice.ogg"
        result = await client.audio.transcriptions.create(model=str(cfg["model"]), file=buf)
        text = str(getattr(result, "text", "") or "").strip()
        if not text:
            return {"ok": False, "error": "no_speech_detected", "text": "", "model": str(cfg["model"])}
        return {"ok": True, "text": text, "model": str(cfg["model"]), "error": ""}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"stt_failed:{type(exc).__name__}",
            "text": "",
            "model": str(cfg.get("model") or ""),
        }
