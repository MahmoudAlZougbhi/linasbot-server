"""Mobile speech-to-text (Whisper via backend — no client secrets)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import File, HTTPException, Request, UploadFile

from modules.api_security import require_session
from modules.core import app
from services.providers.base import provider_config


def _safe_audio_filename(filename: str | None, content_type: str | None) -> str:
    raw_name = (filename or "").strip() or "voice.m4a"
    suffix = Path(raw_name).suffix.lower()
    if suffix in {".m4a", ".mp4", ".aac", ".mp3", ".wav", ".webm", ".ogg", ".3gp", ".caf"}:
        return f"voice{suffix}"
    ct = (content_type or "").lower()
    if "webm" in ct:
        return "voice.webm"
    if "wav" in ct:
        return "voice.wav"
    if "mpeg" in ct or "mp3" in ct:
        return "voice.mp3"
    if "3gpp" in ct or "3gp" in ct:
        return "voice.3gp"
    return "voice.m4a"


@app.post("/api/mobile/transcribe")
async def mobile_transcribe(
    request: Request,
    audio: UploadFile = File(...),
) -> Any:
    require_session(request)
    cfg = provider_config()["stt"]
    if cfg.get("provider") != "openai":
        raise HTTPException(status_code=503, detail="Speech-to-text provider not configured")
    content_type = (audio.content_type or "").lower()
    if content_type and not (
        content_type.startswith("audio/") or content_type in {"application/octet-stream", "video/mp4"}
    ):
        raise HTTPException(status_code=400, detail="Expected an audio upload")
    raw = await audio.read()
    if not raw or len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Invalid audio payload")
    filename = _safe_audio_filename(audio.filename, content_type)
    try:
        from services import llm_core_service

        client = getattr(llm_core_service, "client", None)
        if client is None:
            raise HTTPException(status_code=503, detail="STT unavailable")
        # OpenAI SDK uses fileobj.name for format detection (same pattern as voice_handlers).
        buf = io.BytesIO(raw)
        buf.name = filename
        result = await client.audio.transcriptions.create(
            model=str(cfg["model"]),
            file=buf,
        )
        text = str(getattr(result, "text", "") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="No speech detected")
        return {
            "success": True,
            "text": text,
            "model": cfg["model"],
            "provider": cfg["provider"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Transcription failed: {type(exc).__name__}",
        ) from exc
