"""Mobile speech-to-text (Whisper via backend — no client secrets)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import File, HTTPException, Request, UploadFile

from modules.api_security import require_session
from modules.core import app
from services.providers.base import provider_config


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
    suffix = Path(audio.filename or "voice.m4a").suffix or ".m4a"
    try:
        from services import llm_core_service

        client = getattr(llm_core_service, "client", None)
        if client is None:
            raise HTTPException(status_code=503, detail="STT unavailable")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(raw)
            tmp.flush()
            with open(tmp.name, "rb") as fh:
                result = await client.audio.transcriptions.create(
                    model=str(cfg["model"]),
                    file=fh,
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
        raise HTTPException(status_code=502, detail=f"Transcription failed: {type(exc).__name__}") from exc
